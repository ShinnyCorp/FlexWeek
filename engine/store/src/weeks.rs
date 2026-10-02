//! Week rows. Python still encodes the block list and maps a conflict to HTTP.

use rusqlite::{Connection, OptionalExtension, params};

use crate::{StoreResult, defer_write};

#[derive(Debug, PartialEq, Eq)]
pub enum WeekSave {
    Ready(i64),
    Conflict,
}

pub fn list_account_weeks(conn: &Connection, user_id: i64) -> StoreResult<Vec<(String, String)>> {
    let mut stmt = conn.prepare("SELECT week_start, blocks FROM weeks WHERE user_id = ?1")?;
    let rows = stmt
        .query_map(params![user_id], |row| Ok((row.get(0)?, row.get(1)?)))?
        .collect::<Result<Vec<_>, _>>()?;
    Ok(rows)
}

/// Missing row is stored text `"[]"` at revision 0, so an empty save does not insert.
pub fn save_week(
    conn: &Connection,
    user_id: i64,
    week_start: &str,
    encoded: &str,
    revision: i64,
) -> StoreResult<WeekSave> {
    let stored: Option<(String, i64)> = conn
        .query_row(
            "SELECT blocks, revision FROM weeks WHERE user_id = ?1 AND week_start = ?2",
            params![user_id, week_start],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    let (stored_blocks, stored_revision) = stored.unwrap_or_else(|| ("[]".to_string(), 0));
    if encoded == stored_blocks {
        return Ok(WeekSave::Ready(stored_revision));
    }
    if revision != stored_revision {
        return Ok(WeekSave::Conflict);
    }
    defer_write(
        conn,
        "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?1, ?2, ?3, 1)
        ON CONFLICT(user_id, week_start)
        DO UPDATE SET blocks = excluded.blocks, revision = revision + 1",
        params![user_id, week_start, encoded],
    )?;
    Ok(WeekSave::Ready(revision + 1))
}
