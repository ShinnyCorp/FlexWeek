mod common;

use common::{assignment_id, scratch};
use flexweek_store::initialize;
use serde_json::{Value, json};

const WEEK: &str = "2026-09-14";

fn sorted_compact(value: &Value) -> String {
    fn sort(value: &Value) -> Value {
        match value {
            Value::Array(items) => Value::Array(items.iter().map(sort).collect()),
            Value::Object(map) => {
                let mut keys: Vec<_> = map.keys().cloned().collect();
                keys.sort();
                let mut out = serde_json::Map::new();
                for key in keys {
                    out.insert(key.clone(), sort(&map[&key]));
                }
                Value::Object(out)
            }
            other => other.clone(),
        }
    }
    serde_json::to_string(&sort(value)).unwrap()
}

#[test]
fn test_initialize_twice_migrates_a_legacy_week_without_losing_it() {
    let path = scratch("legacy-week");
    {
        let db = rusqlite::Connection::open(&path).unwrap();
        db.execute_batch(
            "
            CREATE TABLE users (
                id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );
            CREATE TABLE weeks (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                blocks TEXT NOT NULL DEFAULT '[]',
                revision INTEGER NOT NULL DEFAULT 0
            );
            ",
        )
        .unwrap();
        db.execute(
            "INSERT INTO users VALUES (1, 'legacy-student', 'scrypt$placeholder-hash')",
            [],
        )
        .unwrap();
        let blocks = json!([{
            "id": "hw-tuesday",
            "title": "History essay",
            "kind": "flexible",
            "duration_min": 45,
            "days": [1],
            "priority": 2,
            "energy": "low",
            "earliest": null,
            "latest": "Tuesday 20:00",
            "start": null,
            "course": "History"
        }]);
        db.execute(
            "INSERT INTO weeks(user_id, blocks, revision) VALUES (1, ?1, 4)",
            [serde_json::to_string(&blocks).unwrap()],
        )
        .unwrap();
    }

    initialize(&path, WEEK).unwrap();
    initialize(&path, WEEK).unwrap();

    let db = rusqlite::Connection::open(&path).unwrap();
    let (user_id, week_start, blocks, revision): (i64, String, String, i64) = db
        .query_row(
            "SELECT user_id, week_start, blocks, revision FROM weeks",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    let count: i64 = db
        .query_row("SELECT COUNT(*) FROM weeks", [], |row| row.get(0))
        .unwrap();
    assert_eq!(count, 1);
    let legacy: i64 = db
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'weeks_legacy'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    let (stored_id, stored_body, stored_rev): (String, String, i64) = db
        .query_row(
            "SELECT id, body, revision FROM assignments WHERE user_id = 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();

    let aid = assignment_id(&week_start, "hw-tuesday");
    assert_eq!((user_id, revision), (1, 4));
    assert_eq!(week_start, WEEK);
    assert_eq!(
        serde_json::from_str::<Value>(&blocks).unwrap(),
        json!([{
            "id": "hw-tuesday",
            "title": "History essay",
            "kind": "flexible",
            "duration_min": 45,
            "days": [1],
            "priority": 2,
            "energy": "low",
            "earliest": null,
            "start": null,
            "course": "History",
            "assignment_id": aid
        }])
    );
    let due = "2026-09-15T20:00";
    let expected_body = json!({
        "category": null,
        "completed": false,
        "completed_at": null,
        "course": "History",
        "due": due,
        "energy": "low",
        "estimate_min": 45,
        "focus_minutes": 0,
        "focus_sessions": 0,
        "id": aid,
        "priority": 2,
        "spotify_url": null,
        "title": "History essay"
    });
    assert_eq!(stored_id, aid);
    assert_eq!(stored_body, sorted_compact(&expected_body));
    assert_eq!(stored_rev, 1);
    assert_eq!(legacy, 0);
    assert_eq!(
        flexweek_engine::plan::migrated_assignment_id(&week_start, "hw-tuesday"),
        aid
    );
}

#[test]
fn test_system_theme_migration_keeps_chosen_themes_and_defaults_new_rows_to_system() {
    let path = scratch("theme-system");
    {
        let db = rusqlite::Connection::open(&path).unwrap();
        db.execute_batch(
            "
            CREATE TABLE users (
                id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );
            CREATE TABLE preferences (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                theme TEXT NOT NULL DEFAULT 'nocturne' CHECK(theme IN ('nocturne', 'slate')),
                reminders_enabled INTEGER NOT NULL DEFAULT 0 CHECK(reminders_enabled IN (0, 1)),
                reminder_lead_min INTEGER NOT NULL DEFAULT 5 CHECK(reminder_lead_min >= 0 AND reminder_lead_min <= 120),
                reminder_sound INTEGER NOT NULL DEFAULT 1 CHECK(reminder_sound IN (0, 1)),
                reminder_dnd_override INTEGER NOT NULL DEFAULT 0 CHECK(reminder_dnd_override IN (0, 1)),
                timer_work_min INTEGER NOT NULL DEFAULT 30,
                timer_break_min INTEGER NOT NULL DEFAULT 15,
                timer_long_break_min INTEGER NOT NULL DEFAULT 30,
                timer_long_break_every INTEGER NOT NULL DEFAULT 4,
                auto_split_pomodoro INTEGER NOT NULL DEFAULT 0 CHECK(auto_split_pomodoro IN (0, 1)),
                default_spotify_url TEXT,
                alarms_json TEXT NOT NULL DEFAULT '[]'
            );
            ",
        )
        .unwrap();
        for (user_id, name) in [
            (1, "light-student"),
            (2, "dark-student"),
            (3, "new-student"),
        ] {
            db.execute(
                "INSERT INTO users VALUES (?1, ?2, 'scrypt$placeholder-hash')",
                rusqlite::params![user_id, name],
            )
            .unwrap();
        }
        db.execute(
            "INSERT INTO preferences(user_id, theme, reminder_lead_min, alarms_json) VALUES (1, 'slate', 15, ?1)",
            [r#"[{"id":"a"}]"#],
        )
        .unwrap();
        db.execute(
            "INSERT INTO preferences(user_id, theme) VALUES (2, 'nocturne')",
            [],
        )
        .unwrap();
    }

    initialize(&path, WEEK).unwrap();
    initialize(&path, WEEK).unwrap();

    let db = rusqlite::Connection::open(&path).unwrap();
    db.execute("INSERT INTO preferences(user_id) VALUES (3)", [])
        .unwrap();
    let mut themes = std::collections::BTreeMap::new();
    let mut stmt = db
        .prepare("SELECT user_id, theme FROM preferences")
        .unwrap();
    let rows = stmt
        .query_map([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })
        .unwrap();
    for row in rows {
        let (user_id, theme) = row.unwrap();
        themes.insert(user_id, theme);
    }
    let kept: (i64, String) = db
        .query_row(
            "SELECT reminder_lead_min, alarms_json FROM preferences WHERE user_id = 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    db.execute(
        "UPDATE preferences SET theme = 'system' WHERE user_id = 1",
        [],
    )
    .unwrap();
    let leftovers: i64 = db
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name LIKE 'preferences_%'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    let dark = db.execute(
        "UPDATE preferences SET theme = 'dark' WHERE user_id = 2",
        [],
    );

    assert_eq!(
        themes,
        std::collections::BTreeMap::from([
            (1, "slate".into()),
            (2, "nocturne".into()),
            (3, "system".into())
        ])
    );
    assert_eq!(kept, (15, r#"[{"id":"a"}]"#.into()));
    assert_eq!(leftovers, 0);
    match dark {
        Err(rusqlite::Error::SqliteFailure(err, _))
            if err.code == rusqlite::ErrorCode::ConstraintViolation => {}
        other => panic!("dark theme should violate the check: {other:?}"),
    }
}

#[test]
fn test_an_unconstrained_legacy_theme_value_becomes_system() {
    let path = scratch("theme-purple");
    {
        let db = rusqlite::Connection::open(&path).unwrap();
        db.execute_batch(
            "
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL);
            CREATE TABLE preferences (user_id INTEGER PRIMARY KEY, theme TEXT NOT NULL DEFAULT 'nocturne');
            ",
        )
        .unwrap();
        db.execute(
            "INSERT INTO users VALUES (1, 'old-student', 'scrypt$placeholder-hash')",
            [],
        )
        .unwrap();
        db.execute("INSERT INTO preferences VALUES (1, 'purple')", [])
            .unwrap();
    }
    initialize(&path, WEEK).unwrap();
    let db = rusqlite::Connection::open(&path).unwrap();
    let theme: String = db
        .query_row(
            "SELECT theme FROM preferences WHERE user_id = 1",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(theme, "system");
}
