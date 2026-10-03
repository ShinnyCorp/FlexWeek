//! Users, sign-in sessions and recovery codes as the routes read and write them.

use rusqlite::{Connection, OptionalExtension, params};

use crate::{StoreResult, defer_write};

pub fn session_user(
    conn: &Connection,
    token_hash: &str,
    now: i64,
) -> StoreResult<Option<(i64, String)>> {
    Ok(conn
        .query_row(
            "SELECT users.id, users.username FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE token_hash = ?1 AND expires > ?2",
            params![token_hash, now],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?)
}

/// The new row's id. A taken name is SQLite's own constraint error, which the caller maps to 409.
pub fn insert_user(conn: &Connection, username: &str, password_hash: &str) -> StoreResult<i64> {
    defer_write(
        conn,
        "INSERT INTO users(username, password_hash) VALUES (?1, ?2)",
        params![username, password_hash],
    )?;
    Ok(conn.last_insert_rowid())
}

/// `(id, username, password_hash)`.
pub fn find_user(conn: &Connection, username: &str) -> StoreResult<Option<(i64, String, String)>> {
    Ok(conn
        .query_row(
            "SELECT id, username, password_hash FROM users WHERE username = ?1",
            params![username],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()?)
}

pub fn password_hash_of(conn: &Connection, user_id: i64) -> StoreResult<Option<String>> {
    Ok(conn
        .query_row(
            "SELECT password_hash FROM users WHERE id = ?1",
            params![user_id],
            |row| row.get(0),
        )
        .optional()?)
}

pub fn delete_session(conn: &Connection, token_hash: &str) -> StoreResult<()> {
    defer_write(
        conn,
        "DELETE FROM sessions WHERE token_hash = ?1",
        params![token_hash],
    )?;
    Ok(())
}

pub fn recovery_hashes(conn: &Connection, user_id: i64) -> StoreResult<Vec<String>> {
    let mut stmt = conn.prepare("SELECT code_hash FROM recovery_codes WHERE user_id = ?1")?;
    let rows = stmt
        .query_map(params![user_id], |row| row.get(0))?
        .collect::<Result<Vec<_>, _>>()?;
    Ok(rows)
}

pub fn count_recovery_codes(conn: &Connection, user_id: i64) -> StoreResult<i64> {
    Ok(conn.query_row(
        "SELECT COUNT(*) AS n FROM recovery_codes WHERE user_id = ?1",
        params![user_id],
        |row| row.get(0),
    )?)
}

pub fn use_recovery_code(conn: &Connection, user_id: i64, code_hash: &str) -> StoreResult<()> {
    defer_write(
        conn,
        "DELETE FROM recovery_codes WHERE user_id = ?1 AND code_hash = ?2",
        params![user_id, code_hash],
    )?;
    Ok(())
}

/// A new password signs every session of the account out.
pub fn rotate_password(conn: &Connection, user_id: i64, new_hash: &str) -> StoreResult<()> {
    defer_write(
        conn,
        "UPDATE users SET password_hash = ?1 WHERE id = ?2",
        params![new_hash, user_id],
    )?;
    defer_write(
        conn,
        "DELETE FROM sessions WHERE user_id = ?1",
        params![user_id],
    )?;
    Ok(())
}
