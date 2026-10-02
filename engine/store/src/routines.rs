//! Routines. The clock stamp is passed in; this crate does not read the time.

use rusqlite::{Connection, OptionalExtension, params};
use serde_json::{Value, json};

use crate::{StoreError, StoreResult, defer_write};

pub struct RoutineWrite<'a> {
    pub id: &'a str,
    pub name: &'a str,
    pub body: &'a str,
    pub revision: i64,
    pub stamp: &'a str,
    pub max_count: i64,
}

#[derive(Debug, PartialEq, Eq)]
pub enum RoutineSave {
    Conflict,
    OverLimit,
    Stored(String),
}

#[derive(Debug, PartialEq, Eq)]
pub enum RoutineDelete {
    Missing,
    Conflict,
    Deleted,
}

pub fn save_routine(
    conn: &Connection,
    user_id: i64,
    write: RoutineWrite<'_>,
) -> StoreResult<RoutineSave> {
    let existing = load_routine(conn, user_id, write.id)?;
    let stored_revision = existing.as_ref().map(|row| row.revision).unwrap_or(0);
    if let Some(row) = &existing
        && row.name == write.name
        && row.body == write.body
    {
        return Ok(RoutineSave::Stored(row.json()));
    }
    if write.revision != stored_revision {
        return Ok(RoutineSave::Conflict);
    }
    if existing.is_none() {
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM routines WHERE user_id = ?1",
            params![user_id],
            |row| row.get(0),
        )?;
        if count >= write.max_count {
            return Ok(RoutineSave::OverLimit);
        }
        defer_write(
            conn,
            "INSERT INTO routines(user_id, id, name, body, revision, created_at, updated_at)
            VALUES (?1, ?2, ?3, ?4, 1, ?5, ?6)",
            params![
                user_id,
                write.id,
                write.name,
                write.body,
                write.stamp,
                write.stamp
            ],
        )?;
    } else {
        defer_write(
            conn,
            "UPDATE routines SET name = ?1, body = ?2, revision = revision + 1, updated_at = ?3
            WHERE user_id = ?4 AND id = ?5",
            params![write.name, write.body, write.stamp, user_id, write.id],
        )?;
    }
    let stored = load_routine(conn, user_id, write.id)?.ok_or_else(|| {
        StoreError::Engine(flexweek_engine::EngineError::value(
            "routine row missing after write",
        ))
    })?;
    Ok(RoutineSave::Stored(stored.json()))
}

/// `revision` is None when the caller's integer does not fit in `i64`; no stored row has that
/// revision, so it conflicts exactly as any other wrong revision does.
pub fn delete_routine(
    conn: &Connection,
    user_id: i64,
    routine_id: &str,
    revision: Option<i64>,
) -> StoreResult<RoutineDelete> {
    let existing = load_routine(conn, user_id, routine_id)?;
    let Some(row) = existing else {
        return Ok(RoutineDelete::Missing);
    };
    if revision != Some(row.revision) {
        return Ok(RoutineDelete::Conflict);
    }
    defer_write(
        conn,
        "DELETE FROM routines WHERE user_id = ?1 AND id = ?2",
        params![user_id, routine_id],
    )?;
    Ok(RoutineDelete::Deleted)
}

pub fn list_routines(conn: &Connection, user_id: i64) -> StoreResult<String> {
    let mut stmt = conn.prepare(
        "SELECT id, name, body, revision, created_at, updated_at FROM routines
        WHERE user_id = ?1 ORDER BY name, id",
    )?;
    let rows = stmt
        .query_map(params![user_id], RoutineRow::from_row)?
        .collect::<Result<Vec<_>, _>>()?;
    let payload = Value::Array(rows.into_iter().map(|row| row.value()).collect());
    Ok(payload.to_string())
}

pub fn replace_routines(conn: &Connection, user_id: i64, rows_json: &str) -> StoreResult<()> {
    let rows: Vec<Value> = serde_json::from_str(rows_json).map_err(|error| StoreError::Json {
        text: rows_json.to_string(),
        error,
    })?;
    defer_write(
        conn,
        "DELETE FROM routines WHERE user_id = ?1",
        params![user_id],
    )?;
    for row in rows {
        defer_write(
            conn,
            "INSERT INTO routines(user_id, id, name, body, revision, created_at, updated_at)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                user_id,
                crate::json_str(&row, "id")?,
                crate::json_str(&row, "name")?,
                crate::json_str(&row, "body")?,
                crate::json_i64(&row, "revision")?,
                crate::json_str(&row, "created_at")?,
                crate::json_str(&row, "updated_at")?,
            ],
        )?;
    }
    Ok(())
}

struct RoutineRow {
    id: String,
    name: String,
    body: String,
    revision: i64,
    created_at: String,
    updated_at: String,
}

impl RoutineRow {
    fn from_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<Self> {
        Ok(Self {
            id: row.get(0)?,
            name: row.get(1)?,
            body: row.get(2)?,
            revision: row.get(3)?,
            created_at: row.get(4)?,
            updated_at: row.get(5)?,
        })
    }

    fn json(&self) -> String {
        self.value().to_string()
    }

    fn value(&self) -> Value {
        json!({
            "id": self.id,
            "name": self.name,
            "body": self.body,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        })
    }
}

fn load_routine(conn: &Connection, user_id: i64, id: &str) -> StoreResult<Option<RoutineRow>> {
    conn.query_row(
        "SELECT id, name, body, revision, created_at, updated_at FROM routines
        WHERE user_id = ?1 AND id = ?2",
        params![user_id, id],
        RoutineRow::from_row,
    )
    .optional()
    .map_err(StoreError::from)
}
