//! Standing-week rows: one per standing block and the week it starts standing from. A row with no
//! body stops that block from its week on, so weeks before a change keep what stood then.

use flexweek_engine::snapshot::canonical;
use flexweek_engine::standing::{derive_standing, restand, standing_body, with_standing};
use rusqlite::{Connection, params};
use serde_json::{Value, json};

use crate::{StoreError, StoreResult, defer_write};

pub(crate) const STANDING_TABLE: &str = r#"
    CREATE TABLE IF NOT EXISTS standing_blocks (
        user_id INTEGER NOT NULL REFERENCES users(id),
        id TEXT NOT NULL,
        from_week TEXT NOT NULL,
        position INTEGER NOT NULL DEFAULT 0,
        body TEXT,
        PRIMARY KEY (user_id, id, from_week)
    )
"#;

fn parse(text: &str) -> StoreResult<Value> {
    serde_json::from_str(text).map_err(|error| StoreError::Json {
        text: text.to_string(),
        error,
    })
}

fn parse_list(text: &str) -> StoreResult<Vec<Value>> {
    match parse(text)? {
        Value::Array(items) => Ok(items),
        other => Ok(vec![other]),
    }
}

/// The blocks standing in `week_start`, in Setup's order.
pub fn standing_blocks(
    conn: &Connection,
    user_id: i64,
    week_start: &str,
) -> StoreResult<Vec<Value>> {
    let mut stmt = conn.prepare(
        "SELECT s.body FROM standing_blocks s
        WHERE s.user_id = ?1 AND s.body IS NOT NULL
            AND s.from_week = (
                SELECT MAX(t.from_week) FROM standing_blocks t
                WHERE t.user_id = s.user_id AND t.id = s.id AND t.from_week <= ?2
            )
        ORDER BY s.position, s.id",
    )?;
    let bodies = stmt
        .query_map(params![user_id, week_start], |row| row.get::<_, String>(0))?
        .collect::<Result<Vec<_>, _>>()?;
    bodies.iter().map(|body| parse(body)).collect()
}

/// A week's stored block list (`"[]"` for one nobody saved) as the student sees it.
pub fn week_with_standing(
    conn: &Connection,
    user_id: i64,
    week_start: &str,
    blocks: &str,
) -> StoreResult<String> {
    let stored = parse_list(blocks)?;
    let standing = standing_blocks(conn, user_id, week_start)?;
    Ok(canonical(&Value::Array(with_standing(&stored, &standing))))
}

fn insert_row(
    conn: &Connection,
    user_id: i64,
    id: &str,
    from_week: &str,
    position: i64,
    body: Option<&str>,
) -> StoreResult<()> {
    defer_write(
        conn,
        "INSERT INTO standing_blocks(user_id, id, from_week, position, body)
        VALUES (?1, ?2, ?3, ?4, ?5)
        ON CONFLICT(user_id, id, from_week)
        DO UPDATE SET position = excluded.position, body = excluded.body",
        params![user_id, id, from_week, position, body],
    )?;
    Ok(())
}

/// The standing week from `from_week` on becomes `blocks` (a JSON list), replacing any change made
/// for a later week. Saved weeks after `from_week` take the new days and times; the open week itself
/// is the client's to save, so its change stays one Undo step. Returns the weeks rewritten.
pub fn set_standing(
    conn: &Connection,
    user_id: i64,
    from_week: &str,
    blocks: &str,
) -> StoreResult<Vec<String>> {
    let blocks: Vec<Value> = parse_list(blocks)?.iter().map(standing_body).collect();
    defer_write(
        conn,
        "DELETE FROM standing_blocks WHERE user_id = ?1 AND from_week >= ?2",
        params![user_id, from_week],
    )?;
    let new_ids: Vec<&str> = blocks.iter().filter_map(|b| b["id"].as_str()).collect();
    let before = standing_blocks(conn, user_id, from_week)?;
    for block in &before {
        if let Some(id) = block["id"].as_str()
            && !new_ids.contains(&id)
        {
            insert_row(conn, user_id, id, from_week, 0, None)?;
        }
    }
    // A block that stands as it did, in the same place, gets no row: a change is only what it changed.
    for (position, block) in blocks.iter().enumerate() {
        if before.get(position) == Some(block) {
            continue;
        }
        let id = block["id"].as_str().unwrap_or_default();
        insert_row(
            conn,
            user_id,
            id,
            from_week,
            position as i64,
            Some(&canonical(block)),
        )?;
    }
    let mut stmt = conn.prepare(
        "SELECT week_start, blocks FROM weeks WHERE user_id = ?1 AND week_start > ?2
        ORDER BY week_start",
    )?;
    let later = stmt
        .query_map(params![user_id, from_week], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<Result<Vec<_>, _>>()?;
    let mut changed = Vec::new();
    for (week_start, text) in later {
        let stored = parse_list(&text)?;
        let updated = restand(&stored, &blocks)?;
        if updated != stored {
            defer_write(
                conn,
                "UPDATE weeks SET blocks = ?1, revision = revision + 1
                WHERE user_id = ?2 AND week_start = ?3",
                params![canonical(&Value::Array(updated)), user_id, week_start],
            )?;
            changed.push(week_start);
        }
    }
    Ok(changed)
}

/// Every standing row, for an account export: `[{id, from_week, position, body}]`, body null for a stop.
pub fn standing_rows(conn: &Connection, user_id: i64) -> StoreResult<String> {
    let mut stmt = conn.prepare(
        "SELECT id, from_week, position, body FROM standing_blocks WHERE user_id = ?1
        ORDER BY from_week, position, id",
    )?;
    let rows = stmt
        .query_map(params![user_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, Option<String>>(3)?,
            ))
        })?
        .collect::<Result<Vec<_>, _>>()?;
    let mut out = Vec::with_capacity(rows.len());
    for (id, from_week, position, body) in rows {
        let body = match body {
            Some(text) => parse(&text)?,
            None => Value::Null,
        };
        out.push(json!({"id": id, "from_week": from_week, "position": position, "body": body}));
    }
    Ok(canonical(&Value::Array(out)))
}

/// An import's standing rows in place of the account's own.
pub fn replace_standing(conn: &Connection, user_id: i64, rows: &str) -> StoreResult<()> {
    defer_write(
        conn,
        "DELETE FROM standing_blocks WHERE user_id = ?1",
        params![user_id],
    )?;
    for row in parse_list(rows)? {
        let body = match &row["body"] {
            Value::Null => None,
            body => Some(canonical(&standing_body(body))),
        };
        insert_row(
            conn,
            user_id,
            row["id"].as_str().unwrap_or_default(),
            row["from_week"].as_str().unwrap_or_default(),
            row["position"].as_i64().unwrap_or(0),
            body.as_deref(),
        )?;
    }
    Ok(())
}

/// An account from before the standing week (or a file exported then) gets one, built from the Setup
/// blocks of its newest saved week that has any. An account that already has rows is left alone.
pub fn adopt_standing(conn: &Connection, user_id: i64) -> StoreResult<()> {
    let has_rows: bool = conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM standing_blocks WHERE user_id = ?1)",
        params![user_id],
        |row| row.get(0),
    )?;
    if has_rows {
        return Ok(());
    }
    let mut weeks = Vec::new();
    for (week_start, text) in crate::list_account_weeks(conn, user_id)? {
        weeks.push((week_start, parse_list(&text)?));
    }
    if let Some((from_week, blocks)) = derive_standing(&weeks)? {
        for (position, block) in blocks.iter().enumerate() {
            let id = block["id"].as_str().unwrap_or_default();
            insert_row(
                conn,
                user_id,
                id,
                &from_week,
                position as i64,
                Some(&canonical(block)),
            )?;
        }
    }
    Ok(())
}
