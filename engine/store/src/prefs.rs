//! Preference rows, new-account defaults, sessions, and deleting an account.

use rusqlite::{Connection, OptionalExtension, params};
use serde_json::{Value, json};

use crate::{StoreError, StoreResult, defer_write};

const ACCOUNT_TABLES: [&str; 8] = [
    "sessions",
    "weeks",
    "assignments",
    "routines",
    "restore_points",
    "operations",
    "preferences",
    "recovery_codes",
];

pub fn preference_row(conn: &Connection, user_id: i64) -> StoreResult<Option<String>> {
    let row = conn
        .query_row(
            "SELECT theme, reminders_enabled, reminder_lead_min, reminder_sound,
                reminder_dnd_override, timer_work_min, timer_break_min,
                timer_long_break_min, timer_long_break_every, auto_split_pomodoro,
                default_spotify_url, alarms_json, availability_json, comfort_json
            FROM preferences WHERE user_id = ?1",
            params![user_id],
            |row| {
                let spotify: Option<String> = row.get(10)?;
                Ok(json!({
                    "theme": row.get::<_, String>(0)?,
                    "reminders_enabled": row.get::<_, i64>(1)?,
                    "reminder_lead_min": row.get::<_, i64>(2)?,
                    "reminder_sound": row.get::<_, i64>(3)?,
                    "reminder_dnd_override": row.get::<_, i64>(4)?,
                    "timer_work_min": row.get::<_, i64>(5)?,
                    "timer_break_min": row.get::<_, i64>(6)?,
                    "timer_long_break_min": row.get::<_, i64>(7)?,
                    "timer_long_break_every": row.get::<_, i64>(8)?,
                    "auto_split_pomodoro": row.get::<_, i64>(9)?,
                    "default_spotify_url": spotify,
                    "alarms_json": row.get::<_, String>(11)?,
                    "availability_json": row.get::<_, String>(12)?,
                    "comfort_json": row.get::<_, String>(13)?,
                }))
            },
        )
        .optional()?;
    Ok(row.map(|value| value.to_string()))
}

pub fn write_preferences(conn: &Connection, user_id: i64, fields_json: &str) -> StoreResult<()> {
    let fields: Value = serde_json::from_str(fields_json).map_err(|error| StoreError::Json {
        text: fields_json.to_string(),
        error,
    })?;
    defer_write(
        conn,
        "UPDATE preferences
        SET theme = ?1, reminders_enabled = ?2, reminder_lead_min = ?3, reminder_sound = ?4,
            reminder_dnd_override = ?5, timer_work_min = ?6, timer_break_min = ?7,
            timer_long_break_min = ?8, timer_long_break_every = ?9, auto_split_pomodoro = ?10,
            default_spotify_url = ?11, alarms_json = ?12, availability_json = ?13, comfort_json = ?14
        WHERE user_id = ?15",
        params![
            crate::json_str(&fields, "theme")?,
            crate::json_i64(&fields, "reminders_enabled")?,
            crate::json_i64(&fields, "reminder_lead_min")?,
            crate::json_i64(&fields, "reminder_sound")?,
            crate::json_i64(&fields, "reminder_dnd_override")?,
            crate::json_i64(&fields, "timer_work_min")?,
            crate::json_i64(&fields, "timer_break_min")?,
            crate::json_i64(&fields, "timer_long_break_min")?,
            crate::json_i64(&fields, "timer_long_break_every")?,
            crate::json_i64(&fields, "auto_split_pomodoro")?,
            crate::json_opt_str(&fields, "default_spotify_url")?,
            crate::json_str(&fields, "alarms_json")?,
            crate::json_str(&fields, "availability_json")?,
            crate::json_str(&fields, "comfort_json")?,
            user_id,
        ],
    )?;
    Ok(())
}

pub fn insert_preferences(conn: &Connection, user_id: i64, prefs_version: i64) -> StoreResult<()> {
    defer_write(
        conn,
        "INSERT INTO preferences(user_id, reminders_enabled, prefs_version) VALUES (?1, 1, ?2)",
        params![user_id, prefs_version],
    )?;
    Ok(())
}

pub fn delete_account(conn: &Connection, user_id: i64) -> StoreResult<()> {
    for table in ACCOUNT_TABLES {
        let sql = format!("DELETE FROM {table} WHERE user_id = ?1");
        defer_write(conn, &sql, params![user_id])?;
    }
    defer_write(conn, "DELETE FROM users WHERE id = ?1", params![user_id])?;
    Ok(())
}

pub fn create_session_row(
    conn: &Connection,
    token_hash: &str,
    user_id: i64,
    expires: i64,
    now: i64,
) -> StoreResult<()> {
    defer_write(
        conn,
        "DELETE FROM sessions WHERE expires <= ?1",
        params![now],
    )?;
    defer_write(
        conn,
        "INSERT INTO sessions VALUES (?1, ?2, ?3)",
        params![token_hash, user_id, expires],
    )?;
    Ok(())
}

/// The stored availability text; None when the account has no preferences row, and an empty
/// string for a NULL column, which the caller reads as no availability.
pub fn availability_json(conn: &Connection, user_id: i64) -> StoreResult<Option<String>> {
    let row: Option<Option<String>> = conn
        .query_row(
            "SELECT availability_json FROM preferences WHERE user_id = ?1",
            params![user_id],
            |row| row.get(0),
        )
        .optional()?;
    Ok(row.map(Option::unwrap_or_default))
}
