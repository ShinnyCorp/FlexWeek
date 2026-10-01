//! SQLite store matching `backend/storage.py`. Disk I/O lives here; no clock or RNG.

use std::collections::{BTreeMap, HashSet};
use std::path::Path;

use base64::Engine as _;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use chrono::{Datelike, Duration, NaiveDate};
use flexweek_engine::time::{hhmm_to_minutes, minutes_to_hhmm, parse_deadline};
use rusqlite::{Connection, OptionalExtension, params};
use scrypt::{Params, scrypt};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

pub const SESSION_SECONDS: i64 = 7 * 24 * 60 * 60;
pub const PREFS_VERSION: i64 = 1;

const LAST_DAY: &str = "2099-12-31";

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

const ACCOUNT_TABLES: &[&str] = &[
    "sessions",
    "weeks",
    "assignments",
    "routines",
    "restore_points",
    "operations",
    "preferences",
    "recovery_codes",
];

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
    Json(serde_json::Error),
    Io(std::io::Error),
    Date(String),
}

impl std::fmt::Display for StoreError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Sqlite(e) => write!(f, "{e}"),
            Self::Engine(e) => write!(f, "{e:?}"),
            Self::Json(e) => write!(f, "{e}"),
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

impl From<serde_json::Error> for StoreError {
    fn from(value: serde_json::Error) -> Self {
        Self::Json(value)
    }
}

impl From<std::io::Error> for StoreError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}

pub type StoreResult<T> = Result<T, StoreError>;

pub fn store_ready() -> bool {
    true
}

pub fn digest(value: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(value.as_bytes());
    hex::encode(hasher.finalize())
}

pub fn make_token(bytes: &[u8; 32]) -> String {
    URL_SAFE_NO_PAD.encode(bytes)
}

pub fn password_hash(password: &str, salt: &str) -> StoreResult<String> {
    let salt_bytes = hex::decode(salt).map_err(|e| StoreError::Date(e.to_string()))?;
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

pub fn normalize_recovery_code(value: &str) -> String {
    value
        .chars()
        .filter(|ch| ch.is_ascii_hexdigit())
        .flat_map(|ch| ch.to_lowercase())
        .collect()
}

pub fn hash_recovery_code(value: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(b"flexweek-recovery:");
    hasher.update(normalize_recovery_code(value).as_bytes());
    hex::encode(hasher.finalize())
}

pub fn recovery_code_matches(presented: &str, stored_hash: &str) -> bool {
    constant_time_eq(
        hash_recovery_code(presented).as_bytes(),
        stored_hash.as_bytes(),
    )
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

pub fn with_connection<T>(
    path: &Path,
    f: impl FnOnce(&Connection) -> StoreResult<T>,
) -> StoreResult<T> {
    let mut db = open_connection(path)?;
    let tx = db.transaction()?;
    let out = f(&tx)?;
    tx.commit()?;
    Ok(out)
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

pub fn new_preferences(db: &Connection, user_id: i64) -> StoreResult<()> {
    db.execute(
        "INSERT INTO preferences(user_id, reminders_enabled, prefs_version) VALUES (?1, 1, ?2)",
        params![user_id, PREFS_VERSION],
    )?;
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
        let blocks: Vec<Value> = serde_json::from_str(&blocks_text)?;
        let before = blocks.clone();
        let (updated, created) = migrate_blocks(&week_start, blocks)?;
        for body in created {
            db.execute(
                "INSERT INTO assignments(user_id, id, body, revision) VALUES (?1, ?2, ?3, 1)
                ON CONFLICT(user_id, id) DO NOTHING",
                params![
                    user_id,
                    body["id"].as_str().unwrap_or_default(),
                    sorted_json(&body)
                ],
            )?;
        }
        if updated != before {
            db.execute(
                "UPDATE weeks SET blocks = ?1 WHERE user_id = ?2 AND week_start = ?3",
                params![sorted_json_array(&updated), user_id, week_start],
            )?;
        }
    }
    db.execute_batch("COMMIT")?;
    Ok(())
}

#[cfg(unix)]
fn prepare_db_path(path: &Path) -> StoreResult<()> {
    use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt};
    if let Some(parent) = path.parent() {
        std::fs::DirBuilder::new()
            .recursive(true)
            .mode(0o700)
            .create(parent)?;
    }
    if !path.exists() {
        std::fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .mode(0o600)
            .open(path)?;
    }
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?;
    Ok(())
}

#[cfg(not(unix))]
fn prepare_db_path(path: &Path) -> StoreResult<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    if !path.exists() {
        std::fs::File::create(path)?;
    }
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

pub fn delete_account(db: &Connection, user_id: i64) -> StoreResult<()> {
    for table in ACCOUNT_TABLES {
        db.execute(
            &format!("DELETE FROM {table} WHERE user_id = ?1"),
            params![user_id],
        )?;
    }
    db.execute("DELETE FROM users WHERE id = ?1", params![user_id])?;
    Ok(())
}

pub fn create_session(
    db: &Connection,
    user_id: i64,
    token: &str,
    now_unix: i64,
) -> StoreResult<()> {
    db.execute(
        "DELETE FROM sessions WHERE expires <= ?1",
        params![now_unix],
    )?;
    db.execute(
        "INSERT INTO sessions VALUES (?1, ?2, ?3)",
        params![digest(token), user_id, now_unix + SESSION_SECONDS],
    )?;
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

fn sorted_json(value: &Value) -> String {
    match value {
        Value::Object(map) => {
            let ordered: BTreeMap<_, _> = map.iter().collect();
            let inner: Vec<String> = ordered
                .iter()
                .map(|(k, v)| format!("\"{k}\":{}", sorted_json(v)))
                .collect();
            format!("{{{}}}", inner.join(","))
        }
        Value::Array(items) => {
            let inner: Vec<String> = items.iter().map(sorted_json).collect();
            format!("[{}]", inner.join(","))
        }
        _ => value.to_string(),
    }
}

fn sorted_json_array(values: &[Value]) -> String {
    let inner: Vec<String> = values.iter().map(sorted_json).collect();
    format!("[{}]", inner.join(","))
}

fn parse_iso_date(value: &str) -> StoreResult<NaiveDate> {
    NaiveDate::parse_from_str(value, "%Y-%m-%d")
        .map_err(|e| StoreError::Date(format!("invalid date {value}: {e}")))
}

fn migrated_assignment_id(week_start: &str, source_id: &str) -> String {
    format!("a-{}", &digest(&format!("{week_start}:{source_id}"))[..32])
}

fn due_from_latest(week_start: &str, latest: Option<&str>, days: &[i64]) -> StoreResult<String> {
    let monday = parse_iso_date(week_start)?;
    let parsed = parse_deadline(latest, days).map_err(StoreError::Engine)?;
    if let Some((day_index, minutes)) = parsed {
        let day = monday + Duration::days(day_index);
        return Ok(format!("{}T{}", iso(day), minutes_to_hhmm(minutes)));
    }
    let sunday = monday + Duration::days(6);
    Ok(format!("{}T23:59", iso(sunday)))
}

fn completed_at_for_block(week_start: &str, block: &Value) -> StoreResult<String> {
    let monday = parse_iso_date(week_start)?;
    let start = block.get("start").and_then(Value::as_str);
    let days: Vec<i64> = block
        .get("days")
        .and_then(Value::as_array)
        .map(|items| items.iter().filter_map(|v| v.as_i64()).collect::<Vec<_>>())
        .unwrap_or_default();
    let mut day = block.get("completed_day").and_then(Value::as_i64);
    if start.is_some() {
        if day.is_none() && days.len() == 1 {
            day = Some(days[0]);
        }
        if let (Some(start_hhmm), Some(day_index)) = (start, day) {
            let end = hhmm_to_minutes(start_hhmm).map_err(StoreError::Engine)?
                + block
                    .get("duration_min")
                    .and_then(Value::as_i64)
                    .unwrap_or(0);
            let mut day_date = monday + Duration::days(day_index);
            let mut end_min = end;
            if end_min >= 24 * 60 {
                day_date += Duration::days(end_min / (24 * 60));
                end_min %= 24 * 60;
            }
            let last = parse_iso_date(LAST_DAY)?;
            if day_date > last {
                return Ok(format!("{LAST_DAY}T23:59"));
            }
            return Ok(format!("{}T{}", iso(day_date), minutes_to_hhmm(end_min)));
        }
    }
    let sunday = monday + Duration::days(6);
    Ok(format!("{}T23:59", iso(sunday)))
}

#[allow(clippy::too_many_arguments)]
fn assignment_body(
    assignment_id: &str,
    block: &Value,
    due: &str,
    estimate_min: i64,
    focus_minutes: i64,
    focus_sessions: i64,
    completed: bool,
    completed_at: Option<&str>,
) -> Value {
    json!({
        "id": assignment_id,
        "title": block.get("title").and_then(Value::as_str).unwrap_or(assignment_id),
        "course": block.get("course"),
        "category": block.get("category"),
        "priority": block.get("priority").and_then(Value::as_i64).unwrap_or(3),
        "energy": block.get("energy").and_then(Value::as_str).unwrap_or("medium"),
        "spotify_url": block.get("spotify_url"),
        "due": due,
        "estimate_min": estimate_min,
        "focus_minutes": focus_minutes,
        "focus_sessions": focus_sessions,
        "completed": completed,
        "completed_at": completed_at,
    })
}

fn as_session(block: &mut Value, assignment_id: &str) {
    if let Some(obj) = block.as_object_mut() {
        obj.insert("assignment_id".into(), json!(assignment_id));
        obj.remove("latest");
        obj.remove("focus_minutes");
        obj.remove("focus_sessions");
    }
}

fn migrate_blocks(week_start: &str, blocks: Vec<Value>) -> StoreResult<(Vec<Value>, Vec<Value>)> {
    let mut updated = blocks;
    let mut created: Vec<Value> = Vec::new();
    let mut grouped: BTreeMap<String, Vec<usize>> = BTreeMap::new();
    for (index, block) in updated.iter().enumerate() {
        if block.get("kind").and_then(Value::as_str) == Some("locked")
            && let Some(parent) = block.get("pomodoro_parent_id").and_then(Value::as_str)
        {
            grouped.entry(parent.to_string()).or_default().push(index);
        }
    }
    let mut claimed: HashSet<usize> = HashSet::new();
    let sunday_due = {
        let monday = parse_iso_date(week_start)?;
        format!("{}T23:59", iso(monday + Duration::days(6)))
    };
    for (parent, indices) in grouped {
        let work_indices: Vec<usize> = indices
            .iter()
            .copied()
            .filter(|index| {
                updated[*index].get("pomodoro_role").and_then(Value::as_str) == Some("work")
            })
            .collect();
        if work_indices.is_empty()
            || work_indices.iter().any(|index| {
                updated[*index]
                    .get("assignment_id")
                    .and_then(Value::as_str)
                    .is_some()
            })
        {
            continue;
        }
        let work: Vec<Value> = work_indices.iter().map(|i| updated[*i].clone()).collect();
        let aid = migrated_assignment_id(week_start, &parent);
        let completed = work.iter().all(|block| {
            block
                .get("completed")
                .and_then(Value::as_bool)
                .unwrap_or(false)
        });
        let completed_at = if completed {
            let ends: Vec<String> = work
                .iter()
                .filter(|block| block.get("start").and_then(Value::as_str).is_some())
                .map(|block| completed_at_for_block(week_start, block))
                .collect::<StoreResult<Vec<_>>>()?;
            if ends.is_empty() {
                Some(sunday_due.clone())
            } else {
                Some(ends.into_iter().max().unwrap())
            }
        } else {
            None
        };
        created.push(assignment_body(
            &aid,
            &work[0],
            &sunday_due,
            work.iter()
                .map(|b| b.get("duration_min").and_then(Value::as_i64).unwrap_or(0))
                .sum(),
            work.iter()
                .map(|b| b.get("focus_minutes").and_then(Value::as_i64).unwrap_or(0))
                .sum(),
            work.iter()
                .map(|b| b.get("focus_sessions").and_then(Value::as_i64).unwrap_or(0))
                .sum(),
            completed,
            completed_at.as_deref(),
        ));
        for index in work_indices {
            as_session(&mut updated[index], &aid);
            claimed.insert(index);
        }
    }
    for (index, block) in updated.iter_mut().enumerate() {
        if claimed.contains(&index)
            || block.get("assignment_id").and_then(Value::as_str).is_some()
            || block.get("kind").and_then(Value::as_str) != Some("flexible")
        {
            continue;
        }
        let block_id = block
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        let aid = migrated_assignment_id(week_start, &block_id);
        let completed = block
            .get("completed")
            .and_then(Value::as_bool)
            .unwrap_or(false);
        let days: Vec<i64> = block
            .get("days")
            .and_then(Value::as_array)
            .map(|items| items.iter().filter_map(|v| v.as_i64()).collect())
            .unwrap_or_default();
        let due = due_from_latest(
            week_start,
            block.get("latest").and_then(Value::as_str),
            &days,
        )?;
        let completed_at = if completed {
            Some(completed_at_for_block(week_start, block)?)
        } else {
            None
        };
        created.push(assignment_body(
            &aid,
            block,
            &due,
            block
                .get("duration_min")
                .and_then(Value::as_i64)
                .unwrap_or(0),
            block
                .get("focus_minutes")
                .and_then(Value::as_i64)
                .unwrap_or(0),
            block
                .get("focus_sessions")
                .and_then(Value::as_i64)
                .unwrap_or(0),
            completed,
            completed_at.as_deref(),
        ));
        as_session(block, &aid);
    }
    Ok((updated, created))
}

fn iso(day: NaiveDate) -> String {
    format!("{:04}-{:02}-{:02}", day.year(), day.month(), day.day())
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
    fn hash_recovery_code_vector() {
        assert_eq!(
            hash_recovery_code("abcd-ef01-2345-6789"),
            "56c4c7208e7f5650f4a7e7294df7536eae58143eb59c7abed85674e674fcb5b3"
        );
    }

    #[test]
    fn initialize_uses_temp_path() {
        let scratch = Path::new("/home/jonathans/.flexweek-ui-harness/scratch/engine-grok");
        std::fs::create_dir_all(scratch).unwrap();
        let path = scratch.join(format!("store-test-{}.sqlite", std::process::id()));
        let _ = std::fs::remove_file(&path);
        initialize(&path, "2026-09-29").unwrap();
        assert!(path.exists());
        let _ = std::fs::remove_file(path);
    }
}
