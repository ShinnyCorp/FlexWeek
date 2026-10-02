mod common;

use std::collections::BTreeMap;

use common::{assignment_id, scratch};
use flexweek_engine::plan::migrated_assignment_id;
use flexweek_store::initialize;
use serde_json::{Value, json};

const WEEK: &str = "2026-09-07";

fn flex(id: &str, extra: Value) -> Value {
    let mut block = json!({
        "id": id,
        "title": id,
        "kind": "flexible",
        "duration_min": 60,
        "days": [0],
        "priority": 3,
        "energy": "medium",
        "earliest": null,
        "latest": null,
        "start": null,
        "course": null
    });
    if let (Some(block), Some(extra)) = (block.as_object_mut(), extra.as_object()) {
        for (key, value) in extra {
            block.insert(key.clone(), value.clone());
        }
    }
    block
}

fn locked(id: &str, extra: Value) -> Value {
    let mut block = json!({
        "id": id,
        "title": id,
        "kind": "locked",
        "duration_min": 60,
        "days": [0],
        "priority": 3,
        "energy": "medium",
        "start": "08:00"
    });
    if let (Some(block), Some(extra)) = (block.as_object_mut(), extra.as_object()) {
        for (key, value) in extra {
            block.insert(key.clone(), value.clone());
        }
    }
    block
}

// Mirrors the assignment row the migration writes. The engine crate allows the same lint.
#[allow(clippy::too_many_arguments)]
fn open_assignment(
    source_id: &str,
    title: &str,
    due: &str,
    estimate_min: i64,
    focus_minutes: i64,
    focus_sessions: i64,
    course: Option<&str>,
    priority: i64,
    energy: &str,
) -> Value {
    json!({
        "id": assignment_id(WEEK, source_id),
        "title": title,
        "course": course,
        "category": null,
        "priority": priority,
        "energy": energy,
        "spotify_url": null,
        "due": due,
        "estimate_min": estimate_min,
        "focus_minutes": focus_minutes,
        "focus_sessions": focus_sessions,
        "completed": false,
        "completed_at": null
    })
}

fn seed_week(name: &str, blocks: &[Value], revision: i64) -> std::path::PathBuf {
    let path = scratch(name);
    let db = rusqlite::Connection::open(&path).unwrap();
    db.execute_batch(
        "
        CREATE TABLE users (
            id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL
        );
        CREATE TABLE weeks (
            user_id INTEGER NOT NULL REFERENCES users(id), week_start TEXT NOT NULL,
            blocks TEXT NOT NULL DEFAULT '[]', revision INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, week_start)
        );
        ",
    )
    .unwrap();
    db.execute(
        "INSERT INTO users VALUES (1, 'legacy-student', 'scrypt$placeholder-hash')",
        [],
    )
    .unwrap();
    db.execute(
        "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (1, ?1, ?2, ?3)",
        rusqlite::params![
            WEEK,
            serde_json::to_string(&Value::Array(blocks.to_vec())).unwrap(),
            revision
        ],
    )
    .unwrap();
    drop(db);
    path
}

fn load_week(path: &std::path::Path) -> (Vec<Value>, i64) {
    let db = rusqlite::Connection::open(path).unwrap();
    let (blocks, revision): (String, i64) = db
        .query_row(
            "SELECT blocks, revision FROM weeks WHERE user_id = 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    let parsed: Vec<Value> = serde_json::from_str(&blocks).unwrap();
    (parsed, revision)
}

fn load_assignments(path: &std::path::Path) -> BTreeMap<String, (Value, i64)> {
    let db = rusqlite::Connection::open(path).unwrap();
    let mut stmt = db
        .prepare("SELECT id, body, revision FROM assignments WHERE user_id = 1")
        .unwrap();
    let rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, i64>(2)?,
            ))
        })
        .unwrap();
    let mut out = BTreeMap::new();
    for row in rows {
        let (id, body, revision) = row.unwrap();
        out.insert(id, (serde_json::from_str(&body).unwrap(), revision));
    }
    out
}

#[test]
fn test_hashes_match_the_contract_formula() {
    let cases = [
        ("essay", "a-4c3275a3fa104726ed3f39fbfb7dcdbf"),
        ("quiz", "a-cb75f030f402ef48877b456efdb9ffbe"),
        ("paper", "a-565243ab50671f3773b5cccdd8d0dec6"),
        ("reading", "a-3dc020065cc419a613b1878c191ea6d7"),
        ("done", "a-a92997b6be1715c9968386adf510f5a1"),
        ("ghost", "a-4e852842aa145742b42b0be3a95989cf"),
    ];
    for (source, literal) in cases {
        let digest = assignment_id(WEEK, source);
        assert_eq!(digest, literal, "{source}");
        assert_eq!(migrated_assignment_id(WEEK, source), digest, "{source}");
    }
}

#[test]
fn test_weekday_bare_iso_and_missing_latest_become_exact_dues() {
    let blocks = [
        flex(
            "essay",
            json!({
                "title": "History essay",
                "duration_min": 90,
                "days": [0, 1, 2, 3, 4],
                "latest": "Thursday 21:00",
                "focus_minutes": 15,
                "focus_sessions": 1,
                "course": "History",
                "priority": 2,
                "energy": "low"
            }),
        ),
        flex(
            "quiz",
            json!({"title": "Spanish quiz", "duration_min": 45, "days": [0, 1, 2], "latest": "21:00"}),
        ),
        flex(
            "paper",
            json!({"title": "Lab paper", "days": [1, 2], "latest": "2026-09-10T16:30"}),
        ),
        flex(
            "reading",
            json!({"title": "Weekend reading", "duration_min": 30, "days": [5]}),
        ),
        locked(
            "school",
            json!({"title": "School", "duration_min": 390, "days": [0, 1, 2, 3, 4], "start": "08:00"}),
        ),
    ];
    let path = seed_week("shapes", &blocks, 4);
    initialize(&path, WEEK).unwrap();
    initialize(&path, WEEK).unwrap();

    let (saved, revision) = load_week(&path);
    let by_id: BTreeMap<_, _> = saved
        .iter()
        .map(|block| (block["id"].as_str().unwrap(), block))
        .collect();
    let assignments = load_assignments(&path);

    assert_eq!(revision, 4);
    assert!(by_id["essay"].get("latest").is_none());
    assert_eq!(
        by_id["essay"]["assignment_id"],
        assignment_id(WEEK, "essay")
    );
    assert_eq!(
        by_id["essay"]
            .get("focus_minutes")
            .and_then(Value::as_i64)
            .unwrap_or(0),
        0
    );
    assert_eq!(
        by_id["essay"]
            .get("focus_sessions")
            .and_then(Value::as_i64)
            .unwrap_or(0),
        0
    );
    assert_eq!(by_id["quiz"]["assignment_id"], assignment_id(WEEK, "quiz"));
    assert_eq!(
        by_id["paper"]["assignment_id"],
        assignment_id(WEEK, "paper")
    );
    assert_eq!(
        by_id["reading"]["assignment_id"],
        assignment_id(WEEK, "reading")
    );
    assert!(by_id["school"].get("assignment_id").is_none());
    assert_eq!(by_id["school"]["start"], "08:00");
    assert_eq!(by_id["school"]["duration_min"], 390);

    let (essay_body, essay_rev) = &assignments[&assignment_id(WEEK, "essay")];
    assert_eq!(*essay_rev, 1);
    assert_eq!(
        essay_body,
        &open_assignment(
            "essay",
            "History essay",
            "2026-09-10T21:00",
            90,
            15,
            1,
            Some("History"),
            2,
            "low"
        )
    );
    assert_eq!(
        assignments[&assignment_id(WEEK, "quiz")],
        (
            open_assignment(
                "quiz",
                "Spanish quiz",
                "2026-09-09T21:00",
                45,
                0,
                0,
                None,
                3,
                "medium"
            ),
            1
        )
    );
    assert_eq!(
        assignments[&assignment_id(WEEK, "paper")],
        (
            open_assignment(
                "paper",
                "Lab paper",
                "2026-09-09T16:30",
                60,
                0,
                0,
                None,
                3,
                "medium"
            ),
            1
        )
    );
    assert_eq!(
        assignments[&assignment_id(WEEK, "reading")],
        (
            open_assignment(
                "reading",
                "Weekend reading",
                "2026-09-13T23:59",
                30,
                0,
                0,
                None,
                3,
                "medium"
            ),
            1
        )
    );
    let ids: std::collections::BTreeSet<_> = assignments.keys().cloned().collect();
    assert_eq!(
        ids,
        std::collections::BTreeSet::from([
            assignment_id(WEEK, "essay"),
            assignment_id(WEEK, "quiz"),
            assignment_id(WEEK, "paper"),
            assignment_id(WEEK, "reading"),
        ])
    );
}

#[test]
fn test_completed_with_and_without_a_slot() {
    let blocks = [
        flex(
            "done",
            json!({
                "title": "Finished quiz",
                "days": [2],
                "latest": "Wednesday 18:00",
                "start": "15:00",
                "completed": true,
                "completed_day": 2
            }),
        ),
        flex(
            "ghost",
            json!({"title": "Dropped reading", "days": [0, 1], "completed": true}),
        ),
    ];
    let path = seed_week("completed-migrate", &blocks, 4);
    initialize(&path, WEEK).unwrap();
    let (saved, revision) = load_week(&path);
    let by_id: BTreeMap<_, _> = saved
        .iter()
        .map(|block| (block["id"].as_str().unwrap(), block))
        .collect();
    let assignments = load_assignments(&path);
    assert_eq!(revision, 4);
    assert_eq!(by_id["done"]["start"], "15:00");
    assert_eq!(by_id["done"]["completed"], true);
    assert_eq!(by_id["done"]["completed_day"], 2);
    assert_eq!(by_id["ghost"]["completed"], true);
    assert!(by_id["ghost"].get("start").is_none_or(Value::is_null));

    let (done_body, done_rev) = &assignments[&assignment_id(WEEK, "done")];
    assert_eq!(*done_rev, 1);
    let mut done_expected = open_assignment(
        "done",
        "Finished quiz",
        "2026-09-09T18:00",
        60,
        0,
        0,
        None,
        3,
        "medium",
    );
    done_expected["completed"] = json!(true);
    done_expected["completed_at"] = json!("2026-09-09T16:00");
    assert_eq!(done_body, &done_expected);
    let mut ghost_expected = open_assignment(
        "ghost",
        "Dropped reading",
        "2026-09-13T23:59",
        60,
        0,
        0,
        None,
        3,
        "medium",
    );
    ghost_expected["completed"] = json!(true);
    ghost_expected["completed_at"] = json!("2026-09-13T23:59");
    assert_eq!(assignments[&assignment_id(WEEK, "ghost")].0, ghost_expected);
}

#[test]
fn test_pomodoro_chunks_share_one_assignment_keyed_by_parent_id() {
    let blocks = [
        locked(
            "essay-1",
            json!({
                "title": "Essay 1/2",
                "duration_min": 30,
                "start": "16:00",
                "focus_minutes": 30,
                "focus_sessions": 1,
                "completed": true,
                "pomodoro_parent_id": "essay",
                "pomodoro_role": "work",
                "pomodoro_index": 1
            }),
        ),
        locked(
            "essay-2",
            json!({
                "title": "Essay 2/2",
                "duration_min": 30,
                "start": "16:45",
                "pomodoro_parent_id": "essay",
                "pomodoro_role": "work",
                "pomodoro_index": 2
            }),
        ),
        locked(
            "essay-b",
            json!({
                "title": "Break",
                "duration_min": 15,
                "start": "16:30",
                "pomodoro_parent_id": "essay",
                "pomodoro_role": "break",
                "pomodoro_index": 1
            }),
        ),
    ];
    let path = seed_week("pomo", &blocks, 7);
    initialize(&path, WEEK).unwrap();
    initialize(&path, WEEK).unwrap();
    let (saved, revision) = load_week(&path);
    let by_id: BTreeMap<_, _> = saved
        .iter()
        .map(|block| (block["id"].as_str().unwrap(), block))
        .collect();
    let assignments = load_assignments(&path);
    let parent = assignment_id(WEEK, "essay");
    assert_eq!(revision, 7);
    assert_eq!(by_id["essay-1"]["assignment_id"], parent);
    assert_eq!(by_id["essay-2"]["assignment_id"], parent);
    assert!(by_id["essay-b"].get("assignment_id").is_none());
    assert_eq!(
        by_id["essay-1"]
            .get("focus_minutes")
            .and_then(Value::as_i64)
            .unwrap_or(0),
        0
    );
    assert_eq!(
        by_id["essay-1"]
            .get("focus_sessions")
            .and_then(Value::as_i64)
            .unwrap_or(0),
        0
    );
    assert_eq!(by_id["essay-1"]["completed"], true);
    assert_eq!(by_id["essay-1"]["start"], "16:00");
    assert_eq!(by_id["essay-b"]["duration_min"], 15);
    assert_eq!(
        assignments[&parent],
        (
            open_assignment(
                "essay",
                "Essay 1/2",
                "2026-09-13T23:59",
                60,
                30,
                1,
                None,
                3,
                "medium"
            ),
            1
        )
    );
}

#[test]
fn test_already_linked_sessions_and_existing_assignments_are_left_alone() {
    let aid = assignment_id(WEEK, "essay");
    let blocks = [
        flex(
            "essay",
            json!({"title": "History essay", "days": [3], "assignment_id": aid}),
        ),
        flex(
            "quiz",
            json!({"title": "Quiz", "days": [1], "latest": "Tuesday 20:00"}),
        ),
    ];
    let path = seed_week("linked", &blocks, 2);
    {
        let db = rusqlite::Connection::open(&path).unwrap();
        db.execute_batch(
            "
            CREATE TABLE assignments (
                user_id INTEGER NOT NULL REFERENCES users(id), id TEXT NOT NULL,
                body TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, id)
            )
            ",
        )
        .unwrap();
        let body = json!({"id": aid, "title": "Do not touch", "due": "2026-09-10T21:00"});
        db.execute(
            "INSERT INTO assignments VALUES (1, ?1, ?2, 6)",
            rusqlite::params![aid, serde_json::to_string(&body).unwrap()],
        )
        .unwrap();
    }
    initialize(&path, WEEK).unwrap();
    let (saved, revision) = load_week(&path);
    let by_id: BTreeMap<_, _> = saved
        .iter()
        .map(|block| (block["id"].as_str().unwrap(), block))
        .collect();
    let assignments = load_assignments(&path);
    assert_eq!(revision, 2);
    assert_eq!(by_id["essay"]["assignment_id"], aid);
    assert_eq!(by_id["essay"]["title"], "History essay");
    assert_eq!(
        assignments[&aid],
        (
            json!({"id": aid, "title": "Do not touch", "due": "2026-09-10T21:00"}),
            6
        )
    );
    assert_eq!(by_id["quiz"]["assignment_id"], assignment_id(WEEK, "quiz"));
    assert_eq!(assignments[&assignment_id(WEEK, "quiz")].1, 1);
}
