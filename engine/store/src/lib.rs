//! SQLite store matching `backend/storage.py`. Disk I/O lives here; no clock or RNG.

use std::collections::HashSet;
use std::path::Path;

use flexweek_engine::plan;
use flexweek_engine::snapshot::canonical;
use rusqlite::{Connection, OptionalExtension, params};
use scrypt::{Params, scrypt};
use serde_json::Value;
use sha2::{Digest, Sha256};

const PREFERENCES_TABLE: &str = r#"
    CREATE TABLE IF NOT EXISTS preferences (
        user_id INTEGER PRIMARY KEY REFERENCES users(id),
        theme TEXT NOT NULL DEFAULT 'system' CHECK(theme IN ('system', 'slate', 'nocturne')),
        reminders_enabled INTEGER NOT NULL DEFAULT 1
            CHECK(reminders_enabled IN (0, 1)),
        reminder_lead_min INTEGER NOT NULL DEFAULT 5
            CHECK(reminder_lead_min >= 0 AND reminder_lead_min <= 120),
        reminder_sound INTEGER NOT NULL DEFAULT 1
            CHECK(reminder_sound IN (0, 1)),
        reminder_dnd_override INTEGER NOT NULL DEFAULT 0
            CHECK(reminder_dnd_override IN (0, 1)),
        timer_work_min INTEGER NOT NULL DEFAULT 30,
        timer_break_min INTEGER NOT NULL DEFAULT 15,
        timer_long_break_min INTEGER NOT NULL DEFAULT 30,
        timer_long_break_every INTEGER NOT NULL DEFAULT 4,
        auto_split_pomodoro INTEGER NOT NULL DEFAULT 0
            CHECK(auto_split_pomodoro IN (0, 1)),
        default_spotify_url TEXT,
        alarms_json TEXT NOT NULL DEFAULT '[]',
        availability_json TEXT NOT NULL DEFAULT '{}',
        comfort_json TEXT NOT NULL DEFAULT '{}',
        prefs_version INTEGER NOT NULL DEFAULT 0
    )
"#;

const WEEKS_TABLE: &str = r#"
    CREATE TABLE IF NOT EXISTS weeks (
        user_id INTEGER NOT NULL REFERENCES users(id), week_start TEXT NOT NULL,
        blocks TEXT NOT NULL DEFAULT '[]', revision INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, week_start)
    )
"#;

const ASSIGNMENTS_TABLE: &str = r#"
    CREATE TABLE IF NOT EXISTS assignments (
        user_id INTEGER NOT NULL REFERENCES users(id), id TEXT NOT NULL,
        body TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, id)
    )
"#;

const ROUTINES_TABLE: &str = r#"
    CREATE TABLE IF NOT EXISTS routines (
        user_id INTEGER NOT NULL REFERENCES users(id), id TEXT NOT NULL,
        name TEXT NOT NULL, body TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, id)
    )
"#;

const RESTORE_POINTS_TABLE: &str = r#"
    CREATE TABLE IF NOT EXISTS restore_points (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        id TEXT NOT NULL,
        label TEXT NOT NULL,
        created_at TEXT NOT NULL,
        weeks_count INTEGER NOT NULL,
        assignments_count INTEGER NOT NULL,
        body TEXT NOT NULL,
        UNIQUE(user_id, id)
    )
"#;

const RECOVERY_CODES_TABLE: &str = r#"
    CREATE TABLE IF NOT EXISTS recovery_codes (
        user_id INTEGER NOT NULL REFERENCES users(id),
        code_hash TEXT NOT NULL,
        PRIMARY KEY (user_id, code_hash)
    )
"#;

const OPERATIONS_TABLE: &str = r#"
    CREATE TABLE IF NOT EXISTS operations (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        operation_id TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        response TEXT NOT NULL,
        UNIQUE(user_id, operation_id)
    )
"#;

#[derive(Debug)]
pub enum StoreError {
    Sqlite(rusqlite::Error),
    Engine(flexweek_engine::EngineError),
    /// Stored text `json.loads` would not read. The Python module raises Python's own error for it.
    Json {
        text: String,
        error: serde_json::Error,
    },
    Io(std::io::Error),
    Date(String),
}

impl std::fmt::Display for StoreError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Sqlite(e) => write!(f, "{e}"),
            Self::Engine(e) => write!(f, "{}", e.message),
            Self::Json { error, .. } => write!(f, "{error}"),
            Self::Io(e) => write!(f, "{e}"),
            Self::Date(msg) => write!(f, "{msg}"),
        }
    }
}

impl std::error::Error for StoreError {}

impl From<rusqlite::Error> for StoreError {
    fn from(value: rusqlite::Error) -> Self {
        Self::Sqlite(value)
    }
}

impl From<std::io::Error> for StoreError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}

pub type StoreResult<T> = Result<T, StoreError>;

mod accounts;
mod assignments;
mod ledger;
mod prefs;
mod routines;
mod weeks;

pub use accounts::{
    count_recovery_codes, delete_session, find_user, insert_user, password_hash_of,
    recovery_hashes, rotate_password, session_user, use_recovery_code,
};
pub use assignments::{
    AssignmentDelete, AssignmentSave, assignment_bodies, assignment_body, assignment_exists,
    count_assignments, delete_assignment, insert_assignment, list_assignment_rows,
    load_assignment_rows, save_assignment,
};
pub use ledger::{
    Recall, capture_account, insert_restore_point, list_restore_points, prune_operations,
    prune_restore_points, recall_operation, remember_operation, replace_account,
    replace_recovery_codes, restore_point_body,
};
pub use prefs::{
    availability_json, create_session_row, delete_account, insert_preferences, preference_row,
    write_preferences,
};
pub use routines::{
    RoutineDelete, RoutineSave, RoutineWrite, delete_routine, list_routines, replace_routines,
    save_routine,
};
pub use weeks::{WeekSave, list_account_weeks, read_week, save_week, week_blocks, week_starts};

/// A write joins the caller's transaction. The first one begins it, as `Connection.execute` does,
/// and leaves it open so the Python `with` block can commit or roll it back.
pub(crate) fn defer_write(
    conn: &Connection,
    sql: &str,
    params: impl rusqlite::Params,
) -> StoreResult<usize> {
    if conn.is_autocommit() {
        conn.execute("BEGIN DEFERRED", [])?;
    }
    Ok(conn.execute(sql, params)?)
}

/// The routes' own `BEGIN IMMEDIATE` and `BEGIN`, run at the same point they were.
pub fn begin_immediate(conn: &Connection) -> StoreResult<()> {
    conn.execute("BEGIN IMMEDIATE", [])?;
    Ok(())
}

pub fn begin(conn: &Connection) -> StoreResult<()> {
    conn.execute("BEGIN", [])?;
    Ok(())
}

pub fn enforce_foreign_keys(conn: &Connection) -> StoreResult<()> {
    conn.execute("PRAGMA foreign_keys = ON", [])?;
    Ok(())
}

pub(crate) fn json_str<'a>(value: &'a Value, key: &str) -> StoreResult<&'a str> {
    value.get(key).and_then(Value::as_str).ok_or_else(|| {
        StoreError::Engine(flexweek_engine::EngineError::value(format!(
            "missing {key}"
        )))
    })
}

pub(crate) fn json_opt_str<'a>(value: &'a Value, key: &str) -> StoreResult<Option<&'a str>> {
    match value.get(key) {
        Some(Value::Null) => Ok(None),
        Some(Value::String(text)) => Ok(Some(text.as_str())),
        _ => Err(StoreError::Engine(flexweek_engine::EngineError::value(
            format!("missing {key}"),
        ))),
    }
}

pub(crate) fn json_i64(value: &Value, key: &str) -> StoreResult<i64> {
    value.get(key).and_then(Value::as_i64).ok_or_else(|| {
        StoreError::Engine(flexweek_engine::EngineError::value(format!(
            "missing {key}"
        )))
    })
}

pub fn digest(value: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(value.as_bytes());
    hex::encode(hasher.finalize())
}

fn decode_salt(salt: &str) -> StoreResult<Vec<u8>> {
    if !salt.len().is_multiple_of(2) {
        return Err(StoreError::Date(
            "fromhex() arg must contain an even number of hexadecimal digits".into(),
        ));
    }
    let bytes = salt.as_bytes();
    let mut out = Vec::with_capacity(bytes.len() / 2);
    let mut index = 0;
    while index < bytes.len() {
        let high = hex_digit(bytes[index]);
        let low = hex_digit(bytes[index + 1]);
        match (high, low) {
            (Some(high), Some(low)) => out.push((high << 4) | low),
            (None, _) => {
                return Err(StoreError::Date(format!(
                    "non-hexadecimal number found in fromhex() arg at position {index}"
                )));
            }
            (_, None) => {
                return Err(StoreError::Date(format!(
                    "non-hexadecimal number found in fromhex() arg at position {}",
                    index + 1
                )));
            }
        }
        index += 2;
    }
    Ok(out)
}

fn hex_digit(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}

pub fn password_hash(password: &str, salt: &str) -> StoreResult<String> {
    let salt_bytes = decode_salt(salt)?;
    let params = Params::new(15, 8, 3, 32).map_err(|e| StoreError::Date(e.to_string()))?;
    let mut key = [0u8; 32];
    scrypt(password.as_bytes(), &salt_bytes, &params, &mut key)
        .map_err(|e| StoreError::Date(e.to_string()))?;
    Ok(format!("scrypt$32768$8$3${salt}${}", hex::encode(key)))
}

pub fn password_matches(password: &str, encoded: &str) -> StoreResult<bool> {
    let salt = encoded
        .split('$')
        .nth_back(1)
        .ok_or_else(|| StoreError::Date("invalid password hash".into()))?;
    let computed = password_hash(password, salt)?;
    Ok(constant_time_eq(computed.as_bytes(), encoded.as_bytes()))
}

fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff = 0u8;
    for (x, y) in a.iter().zip(b.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}

pub fn open_connection(path: &Path) -> StoreResult<Connection> {
    let db = Connection::open(path)?;
    db.busy_timeout(std::time::Duration::from_secs(10))?;
    db.execute("PRAGMA foreign_keys = ON", [])?;
    Ok(db)
}

pub fn date_legacy_weeks(db: &Connection, current_week_start: &str) -> StoreResult<()> {
    let tables: HashSet<String> = db
        .prepare("SELECT name FROM sqlite_master WHERE type = 'table'")?
        .query_map([], |row| row.get(0))?
        .collect::<Result<_, _>>()?;
    if !tables.contains("weeks") {
        return Ok(());
    }
    let columns: HashSet<String> = db
        .prepare("PRAGMA table_info('weeks')")?
        .query_map([], |row| row.get::<_, String>(1))?
        .collect::<Result<_, _>>()?;
    if columns.contains("week_start") {
        return Ok(());
    }
    db.execute_batch("BEGIN IMMEDIATE")?;
    db.execute("ALTER TABLE weeks RENAME TO weeks_legacy", [])?;
    db.execute_batch(WEEKS_TABLE)?;
    db.execute(
        "INSERT INTO weeks(user_id, week_start, blocks, revision)
        SELECT user_id, ?1, blocks, revision FROM weeks_legacy",
        params![current_week_start],
    )?;
    db.execute("DROP TABLE weeks_legacy", [])?;
    db.execute_batch("COMMIT")?;
    Ok(())
}

pub fn migrate_preferences(db: &Connection) -> StoreResult<()> {
    let cols: HashSet<String> = db
        .prepare("PRAGMA table_info(preferences)")?
        .query_map([], |row| row.get::<_, String>(1))?
        .collect::<Result<_, _>>()?;
    if !cols.contains("reminders_enabled") {
        db.execute(
            "ALTER TABLE preferences ADD COLUMN reminders_enabled INTEGER NOT NULL DEFAULT 0",
            [],
        )?;
    }
    if !cols.contains("reminder_lead_min") {
        db.execute(
            "ALTER TABLE preferences ADD COLUMN reminder_lead_min INTEGER NOT NULL DEFAULT 5",
            [],
        )?;
    }
    if !cols.contains("reminder_sound") {
        db.execute(
            "ALTER TABLE preferences ADD COLUMN reminder_sound INTEGER NOT NULL DEFAULT 1",
            [],
        )?;
    }
    let phase7_columns = [
        ("reminder_dnd_override", "INTEGER NOT NULL DEFAULT 0"),
        ("timer_work_min", "INTEGER NOT NULL DEFAULT 30"),
        ("timer_break_min", "INTEGER NOT NULL DEFAULT 15"),
        ("timer_long_break_min", "INTEGER NOT NULL DEFAULT 30"),
        ("timer_long_break_every", "INTEGER NOT NULL DEFAULT 4"),
        ("auto_split_pomodoro", "INTEGER NOT NULL DEFAULT 0"),
        ("default_spotify_url", "TEXT"),
        ("alarms_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("availability_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("comfort_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("prefs_version", "INTEGER NOT NULL DEFAULT 0"),
    ];
    for (name, declaration) in phase7_columns {
        if !cols.contains(name) {
            db.execute(
                &format!("ALTER TABLE preferences ADD COLUMN {name} {declaration}"),
                [],
            )?;
        }
    }
    Ok(())
}

pub fn allow_system_theme(db: &Connection) -> StoreResult<()> {
    let row: Option<String> = db
        .query_row(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'preferences'",
            [],
            |row| row.get(0),
        )
        .optional()?;
    let Some(sql) = row else {
        return Ok(());
    };
    if sql.contains("'system'") {
        return Ok(());
    }
    let kept: Vec<String> = db
        .prepare("PRAGMA table_info('preferences')")?
        .query_map([], |row| row.get::<_, String>(1))?
        .filter_map(|r| r.ok())
        .filter(|name| name != "theme")
        .collect();
    let columns = kept.join(", ");
    db.execute_batch("BEGIN IMMEDIATE")?;
    db.execute("ALTER TABLE preferences RENAME TO preferences_legacy", [])?;
    db.execute_batch(PREFERENCES_TABLE)?;
    db.execute(
        &format!(
            "INSERT INTO preferences(theme, {columns})
        SELECT CASE WHEN theme IN ('slate', 'nocturne') THEN theme ELSE 'system' END, {columns}
        FROM preferences_legacy"
        ),
        [],
    )?;
    db.execute("DROP TABLE preferences_legacy", [])?;
    db.execute_batch("COMMIT")?;
    Ok(())
}

pub fn upgrade_preferences(db: &Connection) -> StoreResult<()> {
    db.execute_batch("BEGIN IMMEDIATE")?;
    db.execute(
        "UPDATE preferences SET reminders_enabled = 1, prefs_version = 1 WHERE prefs_version < 1",
        [],
    )?;
    db.execute_batch("COMMIT")?;
    Ok(())
}

pub fn migrate_assignments(db: &Connection) -> StoreResult<()> {
    let tables: HashSet<String> = db
        .prepare("SELECT name FROM sqlite_master WHERE type = 'table'")?
        .query_map([], |row| row.get(0))?
        .collect::<Result<_, _>>()?;
    if !tables.contains("weeks") {
        return Ok(());
    }
    db.execute_batch("BEGIN IMMEDIATE")?;
    let mut stmt = db.prepare("SELECT user_id, week_start, blocks FROM weeks")?;
    let rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })?
        .collect::<Result<Vec<_>, _>>()?;
    for (user_id, week_start, blocks_text) in rows {
        let blocks: Value = match serde_json::from_str(&blocks_text) {
            Ok(blocks) => blocks,
            Err(error) => {
                return Err(StoreError::Json {
                    text: blocks_text,
                    error,
                });
            }
        };
        let (updated, created) =
            plan::migrate_blocks(&week_start, &blocks).map_err(StoreError::Engine)?;
        for body in created {
            db.execute(
                "INSERT INTO assignments(user_id, id, body, revision) VALUES (?1, ?2, ?3, 1)
                ON CONFLICT(user_id, id) DO NOTHING",
                params![user_id, body["id"].as_str(), canonical(&body)],
            )?;
        }
        if updated != blocks {
            db.execute(
                "UPDATE weeks SET blocks = ?1 WHERE user_id = ?2 AND week_start = ?3",
                params![canonical(&updated), user_id, week_start],
            )?;
        }
    }
    db.execute_batch("COMMIT")?;
    Ok(())
}

#[cfg(unix)]
fn prepare_db_path(path: &Path) -> StoreResult<()> {
    use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
    if let Some(parent) = path.parent() {
        std::fs::DirBuilder::new()
            .recursive(true)
            .mode(0o700)
            .create(parent)?;
    }
    touch(path)?;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?;
    Ok(())
}

#[cfg(not(unix))]
fn prepare_db_path(path: &Path) -> StoreResult<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    touch(path)
}

/// `path.touch(mode=0o600, exist_ok=True)`: a start that finds the file already made, even by
/// another start a moment earlier, opens it as it is.
fn touch(path: &Path) -> StoreResult<()> {
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create(true).truncate(false);
    #[cfg(unix)]
    std::os::unix::fs::OpenOptionsExt::mode(&mut options, 0o600);
    options.open(path)?;
    Ok(())
}

pub fn initialize(path: &Path, current_week_start: &str) -> StoreResult<()> {
    prepare_db_path(path)?;
    let db = open_connection(path)?;
    let init_script = format!(
        r#"
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                expires INTEGER NOT NULL
            );
            {WEEKS_TABLE};
            {ASSIGNMENTS_TABLE};
            {ROUTINES_TABLE};
            {RESTORE_POINTS_TABLE};
            {OPERATIONS_TABLE};
            {PREFERENCES_TABLE};
            {RECOVERY_CODES_TABLE};
            CREATE TABLE IF NOT EXISTS auth_attempts (
                key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL
            );
        "#
    );
    db.execute_batch(&init_script)?;
    date_legacy_weeks(&db, current_week_start)?;
    migrate_preferences(&db)?;
    allow_system_theme(&db)?;
    upgrade_preferences(&db)?;
    migrate_assignments(&db)?;
    Ok(())
}

pub fn throttle(path: &Path, address: &str, username: &str, now_unix: i64) -> StoreResult<bool> {
    let db = open_connection(path)?;
    db.execute_batch("BEGIN IMMEDIATE")?;
    db.execute(
        "DELETE FROM auth_attempts WHERE expires <= ?1",
        params![now_unix],
    )?;
    for (key, limit) in [
        (digest(&format!("ip:{address}")), 30),
        (digest(&format!("user:{username}")), 10),
    ] {
        let count: Option<i64> = db
            .query_row(
                "SELECT count FROM auth_attempts WHERE key = ?1",
                params![key],
                |row| row.get(0),
            )
            .optional()?;
        if count.is_some_and(|c| c >= limit) {
            db.execute_batch("COMMIT")?;
            return Ok(false);
        }
    }
    for key in [
        digest(&format!("ip:{address}")),
        digest(&format!("user:{username}")),
    ] {
        db.execute(
            "INSERT INTO auth_attempts VALUES (?1, 1, ?2)
                ON CONFLICT(key) DO UPDATE SET count = count + 1",
            params![key, now_unix + 300],
        )?;
    }
    db.execute_batch("COMMIT")?;
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn password_hash_vector() {
        let encoded = password_hash("secret", "00112233445566778899aabbccddeeff").unwrap();
        assert_eq!(
            encoded,
            "scrypt$32768$8$3$00112233445566778899aabbccddeeff$acfa1ad8d5c639d068e6988715f03dd7b1acdb99c998707b1632762596fd2b16"
        );
    }

    #[test]
    fn digest_vector() {
        assert_eq!(
            digest("flexweek"),
            "62613e7e087bc908bd61b5f08e4f59237a54929ef1310ec5868762c37c633e24"
        );
    }

    #[test]
    fn initialize_uses_temp_path() {
        let scratch = std::env::temp_dir();
        let path = scratch.join(format!("flexweek-store-test-{}.sqlite", std::process::id()));
        let _ = std::fs::remove_file(&path);
        initialize(&path, "2026-09-29").unwrap();
        assert!(path.exists());
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn creating_a_file_another_start_just_made_keeps_it() {
        let folder = Path::new(env!("CARGO_MANIFEST_DIR")).join("../target/store-tests");
        std::fs::create_dir_all(&folder).unwrap();
        let path = folder.join(format!("touch-{}.sqlite", std::process::id()));
        std::fs::write(&path, b"made by the first start").unwrap();
        touch(&path).expect("a file that already exists is fine");
        assert_eq!(std::fs::read(&path).unwrap(), b"made by the first start");
        std::fs::remove_file(path).unwrap();
    }
}
