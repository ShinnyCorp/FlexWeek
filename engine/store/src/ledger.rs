//! Account snapshot, restore points, remembered operations, and recovery hashes.

use std::collections::HashSet;

use rusqlite::{Connection, OptionalExtension, params};
use serde_json::json;

use crate::{StoreResult, defer_write};

#[derive(Debug, PartialEq, Eq)]
pub enum Recall {
    Missing,
    Conflict,
    Hit(String),
}

pub fn capture_account(conn: &Connection, user_id: i64) -> StoreResult<String> {
    let mut weeks = conn.prepare(
        "SELECT week_start, blocks, revision FROM weeks WHERE user_id = ?1 ORDER BY week_start",
    )?;
    let week_rows = weeks
        .query_map(params![user_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, i64>(2)?,
            ))
        })?
        .collect::<Result<Vec<_>, _>>()?;
    let mut assignments =
        conn.prepare("SELECT id, body, revision FROM assignments WHERE user_id = ?1 ORDER BY id")?;
    let assignment_rows = assignments
        .query_map(params![user_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, i64>(2)?,
            ))
        })?
        .collect::<Result<Vec<_>, _>>()?;
    let payload = json!({
        "weeks": week_rows
            .into_iter()
            .map(|(week_start, blocks, revision)| json!({
                "week_start": week_start,
                "blocks": blocks,
                "revision": revision,
            }))
            .collect::<Vec<_>>(),
        "assignments": assignment_rows
            .into_iter()
            .map(|(id, body, revision)| json!({
                "id": id,
                "body": body,
                "revision": revision,
            }))
            .collect::<Vec<_>>(),
    });
    Ok(payload.to_string())
}

pub fn replace_account(
    conn: &Connection,
    user_id: i64,
    weeks: &[(String, String, i64)],
    assignments: &[(String, String, i64)],
) -> StoreResult<()> {
    defer_write(
        conn,
        "DELETE FROM weeks WHERE user_id = ?1",
        params![user_id],
    )?;
    defer_write(
        conn,
        "DELETE FROM assignments WHERE user_id = ?1",
        params![user_id],
    )?;
    for (week_start, blocks, revision) in weeks {
        defer_write(
            conn,
            "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?1, ?2, ?3, ?4)",
            params![user_id, week_start, blocks, revision],
        )?;
    }
    for (id, body, revision) in assignments {
        defer_write(
            conn,
            "INSERT INTO assignments(user_id, id, body, revision) VALUES (?1, ?2, ?3, ?4)",
            params![user_id, id, body, revision],
        )?;
    }
    Ok(())
}

pub fn prune_restore_points(
    conn: &Connection,
    user_id: i64,
    keep_ids: &[String],
    keep: i64,
) -> StoreResult<()> {
    let mut stmt =
        conn.prepare("SELECT seq, id FROM restore_points WHERE user_id = ?1 ORDER BY seq ASC")?;
    let rows = stmt
        .query_map(params![user_id], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<Result<Vec<_>, _>>()?;
    let overflow = rows.len() as i64 - keep;
    if overflow <= 0 {
        return Ok(());
    }
    let protected: HashSet<&str> = keep_ids.iter().map(String::as_str).collect();
    let extras: Vec<i64> = rows
        .into_iter()
        .filter(|(_, id)| !protected.contains(id.as_str()))
        .map(|(seq, _)| seq)
        .collect();
    for seq in extras.into_iter().take(overflow as usize) {
        defer_write(
            conn,
            "DELETE FROM restore_points WHERE seq = ?1",
            params![seq],
        )?;
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
pub fn insert_restore_point(
    conn: &Connection,
    user_id: i64,
    point_id: &str,
    label: &str,
    created_at: &str,
    weeks_count: i64,
    assignments_count: i64,
    body: &str,
    keep_ids: &[String],
    keep: i64,
) -> StoreResult<()> {
    defer_write(
        conn,
        "INSERT INTO restore_points(
            user_id, id, label, created_at, weeks_count, assignments_count, body
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
        params![
            user_id,
            point_id,
            label,
            created_at,
            weeks_count,
            assignments_count,
            body
        ],
    )?;
    prune_restore_points(conn, user_id, keep_ids, keep)
}

pub fn prune_operations(conn: &Connection, user_id: i64, keep: i64) -> StoreResult<()> {
    let count: i64 = conn.query_row(
        "SELECT COUNT(*) FROM operations WHERE user_id = ?1",
        params![user_id],
        |row| row.get(0),
    )?;
    let extra = count - keep;
    if extra <= 0 {
        return Ok(());
    }
    defer_write(
        conn,
        "DELETE FROM operations WHERE seq IN (
            SELECT seq FROM operations WHERE user_id = ?1 ORDER BY seq ASC LIMIT ?2
        )",
        params![user_id, extra],
    )?;
    Ok(())
}

pub fn recall_operation(
    conn: &Connection,
    user_id: i64,
    operation_id: &str,
    digest_value: &str,
) -> StoreResult<Recall> {
    let row: Option<(String, String)> = conn
        .query_row(
            "SELECT payload_hash, response FROM operations
            WHERE user_id = ?1 AND operation_id = ?2",
            params![user_id, operation_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    let Some((payload_hash, response)) = row else {
        return Ok(Recall::Missing);
    };
    if payload_hash != digest_value {
        return Ok(Recall::Conflict);
    }
    Ok(Recall::Hit(response))
}

pub fn remember_operation(
    conn: &Connection,
    user_id: i64,
    operation_id: &str,
    digest_value: &str,
    response: &str,
    keep: i64,
) -> StoreResult<()> {
    defer_write(
        conn,
        "INSERT INTO operations(user_id, operation_id, payload_hash, response)
        VALUES (?1, ?2, ?3, ?4)",
        params![user_id, operation_id, digest_value, response],
    )?;
    prune_operations(conn, user_id, keep)
}

pub fn replace_recovery_codes(
    conn: &Connection,
    user_id: i64,
    hashes: &[String],
) -> StoreResult<()> {
    defer_write(
        conn,
        "DELETE FROM recovery_codes WHERE user_id = ?1",
        params![user_id],
    )?;
    for hash in hashes {
        defer_write(
            conn,
            "INSERT INTO recovery_codes(user_id, code_hash) VALUES (?1, ?2)",
            params![user_id, hash],
        )?;
    }
    Ok(())
}

/// The account's restore points, newest first, as a JSON list of objects named by column.
pub fn list_restore_points(conn: &Connection, user_id: i64) -> StoreResult<String> {
    let mut stmt = conn.prepare(
        "SELECT id, label, created_at, weeks_count, assignments_count
        FROM restore_points WHERE user_id = ?1 ORDER BY seq DESC",
    )?;
    let rows = stmt
        .query_map(params![user_id], |row| {
            Ok(json!({
                "id": row.get::<_, String>(0)?,
                "label": row.get::<_, String>(1)?,
                "created_at": row.get::<_, String>(2)?,
                "weeks_count": row.get::<_, i64>(3)?,
                "assignments_count": row.get::<_, i64>(4)?,
            }))
        })?
        .collect::<Result<Vec<_>, _>>()?;
    Ok(serde_json::Value::Array(rows).to_string())
}

/// `(id, body)` of one restore point of the account.
pub fn restore_point_body(
    conn: &Connection,
    user_id: i64,
    point_id: &str,
) -> StoreResult<Option<(String, String)>> {
    Ok(conn
        .query_row(
            "SELECT id, body FROM restore_points WHERE user_id = ?1 AND id = ?2",
            params![user_id, point_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?)
}
