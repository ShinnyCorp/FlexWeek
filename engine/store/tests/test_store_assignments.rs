mod common;

use common::scratch;
use flexweek_store::{
    AssignmentDelete, AssignmentSave, assignment_exists, count_assignments, delete_assignment,
    initialize, insert_assignment, open_connection, save_assignment,
};
use serde_json::json;

const MAX_ASSIGNMENTS: i64 = 1000;

/// `encode_assignment`: `json.dumps(content.model_dump(), sort_keys=True, separators=(",", ":"))`.
/// Empty notes, links and checklist are omitted. The other fields stay, nulls included.
fn essay_body(title: &str) -> String {
    serde_json::to_string(&json!({
        "category": null,
        "completed": false,
        "completed_at": null,
        "course": null,
        "due": "2026-09-15T23:59",
        "energy": "low",
        "estimate_min": 120,
        "focus_minutes": 0,
        "focus_sessions": 0,
        "id": "hw-essay",
        "priority": 2,
        "spotify_url": null,
        "title": title
    }))
    .unwrap()
}

fn account(name: &str) -> (std::path::PathBuf, rusqlite::Connection, i64) {
    let path = scratch(name);
    initialize(&path, "2026-09-14").unwrap();
    let conn = open_connection(&path).unwrap();
    conn.execute(
        "INSERT INTO users(username, password_hash) VALUES ('ada', 'x')",
        [],
    )
    .unwrap();
    let user_id: i64 = conn
        .query_row("SELECT id FROM users WHERE username = 'ada'", [], |row| {
            row.get(0)
        })
        .unwrap();
    (path, conn, user_id)
}

#[test]
fn test_same_body_keeps_its_revision_and_a_stale_edit_writes_nothing() {
    let (_path, conn, user_id) = account("essay-revision");
    assert_eq!(
        save_assignment(
            &conn,
            user_id,
            "hw-essay",
            &essay_body("Essay"),
            0,
            MAX_ASSIGNMENTS
        )
        .unwrap(),
        AssignmentSave::Ready(1)
    );
    assert_eq!(
        save_assignment(
            &conn,
            user_id,
            "hw-essay",
            &essay_body("Essay"),
            4,
            MAX_ASSIGNMENTS
        )
        .unwrap(),
        AssignmentSave::Ready(1)
    );
    assert_eq!(
        save_assignment(
            &conn,
            user_id,
            "hw-essay",
            &essay_body("Renamed"),
            0,
            MAX_ASSIGNMENTS
        )
        .unwrap(),
        AssignmentSave::Conflict
    );
    let (body, revision): (String, i64) = conn
        .query_row(
            "SELECT body, revision FROM assignments WHERE user_id = ?1 AND id = 'hw-essay'",
            [user_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(revision, 1);
    assert!(!body.contains("Renamed"));
    assert_eq!(body, essay_body("Essay"));
}

#[test]
fn test_delete_drops_the_assignment_and_its_sessions() {
    let (_path, conn, user_id) = account("essay-delete");
    save_assignment(
        &conn,
        user_id,
        "hw-essay",
        &essay_body("Essay"),
        0,
        MAX_ASSIGNMENTS,
    )
    .unwrap();
    conn.execute(
        "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?1, '2026-09-14', ?2, 3)",
        rusqlite::params![
            user_id,
            r#"[{"assignment_id":"hw-essay","id":"w1"},{"id":"keep"}]"#
        ],
    )
    .unwrap();
    let AssignmentDelete::Deleted(payload) =
        delete_assignment(&conn, user_id, "hw-essay", Some(1)).unwrap()
    else {
        panic!("expected the assignment to be deleted");
    };
    let deleted: serde_json::Value = serde_json::from_str(&payload).unwrap();
    assert_eq!(
        deleted["changed_weeks"],
        json!([{"week_start": "2026-09-14", "revision": 4}])
    );
    assert_eq!(
        deleted["removed_sessions"]["2026-09-14"],
        json!([{"assignment_id": "hw-essay", "id": "w1"}])
    );
    let (blocks, revision): (String, i64) = conn
        .query_row(
            "SELECT blocks, revision FROM weeks WHERE user_id = ?1 AND week_start = '2026-09-14'",
            [user_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(blocks, r#"[{"id":"keep"}]"#);
    assert_eq!(revision, 4);
    let left: Option<i64> = conn
        .query_row(
            "SELECT 1 FROM assignments WHERE user_id = ?1 AND id = 'hw-essay'",
            [user_id],
            |row| row.get(0),
        )
        .ok();
    assert!(left.is_none());
}

#[test]
fn test_the_cap_counts_rows_already_stored() {
    let (_path, conn, user_id) = account("essay-cap");
    insert_assignment(&conn, user_id, "hw-essay", r#"{"id":"hw-essay"}"#).unwrap();
    assert_eq!(
        save_assignment(&conn, user_id, "hw-two", r#"{"id":"hw-two"}"#, 0, 1).unwrap(),
        AssignmentSave::OverLimit
    );
    assert!(!assignment_exists(&conn, user_id, "hw-two").unwrap());
}

#[test]
fn test_a_failed_insert_rolls_the_first_one_back() {
    let (path, conn, user_id) = account("essay-rollback");
    insert_assignment(&conn, user_id, "hw-essay", r#"{"id":"hw-essay"}"#).unwrap();
    let failed = insert_assignment(&conn, user_id, "hw-essay", r#"{"id":"hw-essay"}"#);
    assert!(matches!(failed, Err(flexweek_store::StoreError::Sqlite(_))));
    // `connect()` rolls the open transaction back when the write raises.
    conn.execute("ROLLBACK", []).unwrap();
    drop(conn);
    let again = open_connection(&path).unwrap();
    assert_eq!(count_assignments(&again, user_id).unwrap(), 0);
}
