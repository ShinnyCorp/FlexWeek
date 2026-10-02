//! Assignment rows. The Python helpers keep their names and map these outcomes to HTTP.

use flexweek_engine::EngineError;
use flexweek_engine::snapshot::canonical;
use rusqlite::{Connection, OptionalExtension, params, params_from_iter, types::Value as SqlValue};
use serde_json::{Map, Value};

use crate::{StoreError, StoreResult, defer_write};

#[derive(Debug, PartialEq, Eq)]
pub enum AssignmentSave {
    Ready(i64),
    Conflict,
    OverLimit,
}

#[derive(Debug, PartialEq, Eq)]
pub enum AssignmentDelete {
    Missing,
    Conflict,
    Deleted(String),
}

pub fn load_assignment_rows(
    conn: &Connection,
    user_id: i64,
    ids: &[String],
) -> StoreResult<Vec<(String, String, i64)>> {
    if ids.is_empty() {
        return Ok(Vec::new());
    }
    let slots = (2..ids.len() + 2)
        .map(|index| format!("?{index}"))
        .collect::<Vec<_>>()
        .join(",");
    let sql = format!(
        "SELECT id, body, revision FROM assignments WHERE user_id = ?1 AND id IN ({slots})"
    );
    let mut bound = Vec::with_capacity(ids.len() + 1);
    bound.push(SqlValue::Integer(user_id));
    for id in ids {
        bound.push(SqlValue::Text(id.clone()));
    }
    let mut stmt = conn.prepare(&sql)?;
    let rows = stmt
        .query_map(params_from_iter(bound.iter()), |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?))
        })?
        .collect::<Result<Vec<_>, _>>()?;
    Ok(rows)
}

pub fn assignment_exists(conn: &Connection, user_id: i64, id: &str) -> StoreResult<bool> {
    let found: Option<i64> = conn
        .query_row(
            "SELECT 1 FROM assignments WHERE user_id = ?1 AND id = ?2",
            params![user_id, id],
            |row| row.get(0),
        )
        .optional()?;
    Ok(found.is_some())
}

pub fn count_assignments(conn: &Connection, user_id: i64) -> StoreResult<i64> {
    Ok(conn.query_row(
        "SELECT COUNT(*) FROM assignments WHERE user_id = ?1",
        params![user_id],
        |row| row.get(0),
    )?)
}

pub fn insert_assignment(conn: &Connection, user_id: i64, id: &str, body: &str) -> StoreResult<()> {
    defer_write(
        conn,
        "INSERT INTO assignments(user_id, id, body, revision) VALUES (?1, ?2, ?3, 1)",
        params![user_id, id, body],
    )?;
    Ok(())
}

/// The same decisions as `upsert_assignment`: an identical body keeps its revision, a stale
/// revision conflicts before any write, and a new row past `max_count` is refused.
pub fn save_assignment(
    conn: &Connection,
    user_id: i64,
    id: &str,
    encoded: &str,
    revision: i64,
    max_count: i64,
) -> StoreResult<AssignmentSave> {
    let stored: Option<(String, i64)> = conn
        .query_row(
            "SELECT body, revision FROM assignments WHERE user_id = ?1 AND id = ?2",
            params![user_id, id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    let Some((stored_body, stored_revision)) = stored else {
        if revision != 0 {
            return Ok(AssignmentSave::Conflict);
        }
        if count_assignments(conn, user_id)? >= max_count {
            return Ok(AssignmentSave::OverLimit);
        }
        insert_assignment(conn, user_id, id, encoded)?;
        return Ok(AssignmentSave::Ready(1));
    };
    if stored_body == encoded {
        return Ok(AssignmentSave::Ready(stored_revision));
    }
    if revision != stored_revision {
        return Ok(AssignmentSave::Conflict);
    }
    defer_write(
        conn,
        "UPDATE assignments SET body = ?1, revision = revision + 1 WHERE user_id = ?2 AND id = ?3",
        params![encoded, user_id, id],
    )?;
    Ok(AssignmentSave::Ready(revision + 1))
}

/// `revision` is None when the caller's integer does not fit in `i64`; no stored row has that
/// revision, so it conflicts exactly as any other wrong revision does.
pub fn delete_assignment(
    conn: &Connection,
    user_id: i64,
    id: &str,
    revision: Option<i64>,
) -> StoreResult<AssignmentDelete> {
    let stored: Option<i64> = conn
        .query_row(
            "SELECT revision FROM assignments WHERE user_id = ?1 AND id = ?2",
            params![user_id, id],
            |row| row.get(0),
        )
        .optional()?;
    let Some(stored_revision) = stored else {
        return Ok(AssignmentDelete::Missing);
    };
    if revision != Some(stored_revision) {
        return Ok(AssignmentDelete::Conflict);
    }
    let mut stmt = conn.prepare(
        "SELECT week_start, blocks, revision FROM weeks WHERE user_id = ?1 ORDER BY week_start",
    )?;
    let weeks = stmt
        .query_map(params![user_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, i64>(2)?,
            ))
        })?
        .collect::<Result<Vec<_>, _>>()?;
    let mut changed = Vec::new();
    let mut removed_sessions = Map::new();
    for (week_start, blocks, week_revision) in weeks {
        let (kept, removed) = split_sessions(&blocks, id)?;
        if removed.is_empty() {
            continue;
        }
        let new_revision = week_revision + 1;
        let encoded = canonical(&Value::Array(kept));
        defer_write(
            conn,
            "UPDATE weeks SET blocks = ?1, revision = ?2 WHERE user_id = ?3 AND week_start = ?4",
            params![encoded, new_revision, user_id, week_start],
        )?;
        changed.push(format!(
            "{{\"week_start\":{},\"revision\":{new_revision}}}",
            canonical(&Value::String(week_start.clone()))
        ));
        removed_sessions.insert(week_start, Value::Array(removed));
    }
    defer_write(
        conn,
        "DELETE FROM assignments WHERE user_id = ?1 AND id = ?2",
        params![user_id, id],
    )?;
    // Written by hand: `canonical` sorts keys, and a changed week lists `week_start` first.
    Ok(AssignmentDelete::Deleted(format!(
        "{{\"changed_weeks\":[{}],\"removed_sessions\":{}}}",
        changed.join(","),
        canonical(&Value::Object(removed_sessions))
    )))
}

fn split_sessions(blocks: &str, assignment_id: &str) -> StoreResult<(Vec<Value>, Vec<Value>)> {
    let parsed: Value = serde_json::from_str(blocks).map_err(|error| StoreError::Json {
        text: blocks.to_string(),
        error,
    })?;
    // Python looped over whatever `json.loads` gave: an object yields its keys and a string its
    // characters, so an empty one held no sessions and a full one failed on `.get`.
    let items = match parsed {
        Value::Array(items) => items,
        Value::Object(map) if map.is_empty() => Vec::new(),
        Value::String(text) if text.is_empty() => Vec::new(),
        Value::Object(_) | Value::String(_) => return Err(no_get("str")),
        other => {
            return Err(StoreError::Engine(EngineError {
                kind: flexweek_engine::ErrorKind::Type,
                message: format!("'{}' object is not iterable", python_type(&other)),
            }));
        }
    };
    let mut kept = Vec::new();
    let mut removed = Vec::new();
    for block in items {
        if session_matches(&block, assignment_id)? {
            removed.push(block);
        } else {
            kept.push(block);
        }
    }
    Ok((kept, removed))
}

fn session_matches(block: &Value, assignment_id: &str) -> StoreResult<bool> {
    let Value::Object(map) = block else {
        return Err(no_get(python_type(block)));
    };
    Ok(map.get("assignment_id").and_then(Value::as_str) == Some(assignment_id))
}

fn no_get(type_name: &str) -> StoreError {
    StoreError::Engine(EngineError {
        kind: flexweek_engine::ErrorKind::Attribute,
        message: format!("'{type_name}' object has no attribute 'get'"),
    })
}

fn python_type(value: &Value) -> &'static str {
    match value {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(number) if number.is_f64() => "float",
        Value::Number(_) => "int",
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

pub fn assignment_body(conn: &Connection, user_id: i64, id: &str) -> StoreResult<Option<String>> {
    Ok(conn
        .query_row(
            "SELECT body FROM assignments WHERE user_id = ?1 AND id = ?2",
            params![user_id, id],
            |row| row.get(0),
        )
        .optional()?)
}

/// `(body, revision)` of every assignment of the account, in the table's own order.
pub fn assignment_bodies(conn: &Connection, user_id: i64) -> StoreResult<Vec<(String, i64)>> {
    let mut stmt = conn.prepare("SELECT body, revision FROM assignments WHERE user_id = ?1")?;
    let rows = stmt
        .query_map(params![user_id], |row| Ok((row.get(0)?, row.get(1)?)))?
        .collect::<Result<Vec<_>, _>>()?;
    Ok(rows)
}

/// `(id, body, revision)` of every assignment of the account, in the table's own order.
pub fn list_assignment_rows(
    conn: &Connection,
    user_id: i64,
) -> StoreResult<Vec<(String, String, i64)>> {
    let mut stmt = conn.prepare("SELECT id, body, revision FROM assignments WHERE user_id = ?1")?;
    let rows = stmt
        .query_map(params![user_id], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?))
        })?
        .collect::<Result<Vec<_>, _>>()?;
    Ok(rows)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{initialize, open_connection};
    use std::path::Path;

    fn account(name: &str) -> Connection {
        let folder = Path::new(env!("CARGO_MANIFEST_DIR")).join("../target/store-tests");
        std::fs::create_dir_all(&folder).unwrap();
        let path = folder.join(format!("assignments-{}-{name}.sqlite", std::process::id()));
        let _ = std::fs::remove_file(&path);
        initialize(&path, "2026-09-14").unwrap();
        let conn = open_connection(&path).unwrap();
        conn.execute("PRAGMA foreign_keys = ON", []).unwrap();
        conn.execute(
            "INSERT INTO users(username, password_hash) VALUES ('ada', 'x')",
            [],
        )
        .unwrap();
        conn
    }

    #[test]
    fn identical_body_keeps_revision_and_stale_edit_does_not_write() {
        let conn = account("revision");
        assert_eq!(
            save_assignment(&conn, 1, "hw", "one", 0, 10).unwrap(),
            AssignmentSave::Ready(1)
        );
        assert_eq!(
            save_assignment(&conn, 1, "hw", "one", 9, 10).unwrap(),
            AssignmentSave::Ready(1)
        );
        assert_eq!(
            save_assignment(&conn, 1, "hw", "two", 0, 10).unwrap(),
            AssignmentSave::Conflict
        );
        let body: String = conn
            .query_row("SELECT body FROM assignments WHERE id = 'hw'", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(body, "one");
    }

    #[test]
    fn the_cap_is_the_count_before_the_insert() {
        let conn = account("cap");
        insert_assignment(&conn, 1, "hw", "one").unwrap();
        assert_eq!(
            save_assignment(&conn, 1, "other", "x", 0, 1).unwrap(),
            AssignmentSave::OverLimit
        );
        assert!(!assignment_exists(&conn, 1, "other").unwrap());
    }

    #[test]
    fn delete_rewrites_only_weeks_that_held_the_assignment() {
        let conn = account("delete");
        insert_assignment(&conn, 1, "hw", "one").unwrap();
        conn.execute(
            "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (1, '2026-09-14', ?1, 3)",
            [r#"[{"assignment_id":"hw","id":"w1"},{"id":"keep"}]"#],
        )
        .unwrap();
        let AssignmentDelete::Deleted(payload) =
            delete_assignment(&conn, 1, "hw", Some(1)).unwrap()
        else {
            panic!("expected the assignment to be deleted");
        };
        assert!(payload.contains("\"revision\":4"));
        let blocks: String = conn
            .query_row(
                "SELECT blocks FROM weeks WHERE week_start = '2026-09-14'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(blocks, r#"[{"id":"keep"}]"#);
        assert!(!assignment_exists(&conn, 1, "hw").unwrap());
    }

    #[test]
    fn a_revision_beyond_i64_conflicts_like_any_wrong_one() {
        let conn = account("wide");
        assert_eq!(
            delete_assignment(&conn, 1, "hw", None).unwrap(),
            AssignmentDelete::Missing
        );
        insert_assignment(&conn, 1, "hw", "one").unwrap();
        assert_eq!(
            delete_assignment(&conn, 1, "hw", None).unwrap(),
            AssignmentDelete::Conflict
        );
        assert!(assignment_exists(&conn, 1, "hw").unwrap());
    }

    #[test]
    fn a_changed_week_lists_its_start_before_its_revision() {
        let conn = account("order");
        insert_assignment(&conn, 1, "hw", "one").unwrap();
        conn.execute(
            "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (1, '2026-09-14', ?1, 3)",
            [r#"[{"assignment_id":"hw"}]"#],
        )
        .unwrap();
        let AssignmentDelete::Deleted(payload) =
            delete_assignment(&conn, 1, "hw", Some(1)).unwrap()
        else {
            panic!("expected the assignment to be deleted");
        };
        assert!(
            payload.starts_with(r#"{"changed_weeks":[{"week_start":"2026-09-14","revision":4}]"#)
        );
    }

    #[test]
    fn a_failed_insert_can_roll_back_the_first() {
        let conn = account("rollback");
        insert_assignment(&conn, 1, "hw", "one").unwrap();
        assert!(insert_assignment(&conn, 1, "hw", "one").is_err());
        conn.execute("ROLLBACK", []).unwrap();
        assert_eq!(count_assignments(&conn, 1).unwrap(), 0);
    }
}
