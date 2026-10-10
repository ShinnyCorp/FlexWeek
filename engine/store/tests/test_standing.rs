//! The standing week in the store (fix-specs item 1): the upgrade from a 0.18 database, the read
//! rule, changing it for this week and every later week, and carrying it in an export.

mod common;

use common::scratch;
use flexweek_store::{
    create_restore_point, delete_account, initialize, insert_preferences, open_connection,
    replace_standing, restore_point_body, set_standing, standing_blocks, standing_rows,
    week_with_standing,
};
use rusqlite::{Connection, params};
use serde_json::{Value, json};

const SETUP_WEEK: &str = "2026-10-05";
const WEEK_BEFORE: &str = "2026-09-28";
const NEXT_WEEK: &str = "2026-10-12";
const WEEK_AFTER: &str = "2026-10-19";

fn school() -> Value {
    json!({"category": "class", "days": [0, 1, 2, 3, 4], "duration_min": 405, "id": "school",
           "kind": "locked", "start": "08:30", "title": "School"})
}

fn soccer() -> Value {
    json!({"category": "extra", "days": [1, 3], "duration_min": 90, "id": "activity-1",
           "kind": "locked", "start": "16:00", "title": "Soccer"})
}

fn gym() -> Value {
    json!({"days": [2], "duration_min": 60, "id": "gym", "kind": "locked", "start": "18:00",
           "title": "Gym"})
}

fn text(value: &Value) -> String {
    serde_json::to_string(value).unwrap()
}

fn add_week(conn: &Connection, user_id: i64, week_start: &str, blocks: &Value) {
    conn.execute(
        "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?1, ?2, ?3, 1)",
        params![user_id, week_start, text(blocks)],
    )
    .unwrap();
}

fn week_row(conn: &Connection, user_id: i64, week_start: &str) -> (Value, i64) {
    let (blocks, revision): (String, i64) = conn
        .query_row(
            "SELECT blocks, revision FROM weeks WHERE user_id = ?1 AND week_start = ?2",
            params![user_id, week_start],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    (serde_json::from_str(&blocks).unwrap(), revision)
}

fn seen(conn: &Connection, user_id: i64, week_start: &str) -> Vec<Value> {
    let stored: String = conn
        .query_row(
            "SELECT blocks FROM weeks WHERE user_id = ?1 AND week_start = ?2",
            params![user_id, week_start],
            |row| row.get(0),
        )
        .unwrap_or_else(|_| "[]".to_string());
    let merged = week_with_standing(conn, user_id, week_start, &stored).unwrap();
    serde_json::from_str::<Vec<Value>>(&merged).unwrap()
}

fn ids(blocks: &[Value]) -> Vec<String> {
    blocks
        .iter()
        .map(|b| b["id"].as_str().unwrap().to_string())
        .collect()
}

/// A database as 0.18.5 left it: no standing table, every account at preferences version 2.
fn as_left_by_0_18(name: &str) -> (std::path::PathBuf, i64) {
    let path = scratch(name);
    initialize(&path, SETUP_WEEK).unwrap();
    let conn = open_connection(&path).unwrap();
    conn.execute_batch("DROP TABLE standing_blocks").unwrap();
    conn.execute(
        "INSERT INTO users(username, password_hash) VALUES ('ada', 'x')",
        [],
    )
    .unwrap();
    let user_id = conn.last_insert_rowid();
    insert_preferences(&conn, user_id, 2).unwrap();
    conn.execute_batch("COMMIT").unwrap();
    let mut missed_monday = school();
    missed_monday["missed_days"] = json!([0]);
    add_week(&conn, user_id, WEEK_BEFORE, &json!([gym()]));
    add_week(
        &conn,
        user_id,
        SETUP_WEEK,
        &json!([missed_monday, soccer(), gym()]),
    );
    (path, user_id)
}

fn fresh_account(name: &str) -> (Connection, i64) {
    let path = scratch(name);
    initialize(&path, SETUP_WEEK).unwrap();
    let conn = open_connection(&path).unwrap();
    conn.execute(
        "INSERT INTO users(username, password_hash) VALUES ('ada', 'x')",
        [],
    )
    .unwrap();
    let user_id = conn.last_insert_rowid();
    insert_preferences(&conn, user_id, 3).unwrap();
    conn.execute_batch("COMMIT").unwrap();
    (conn, user_id)
}

#[test]
fn the_upgrade_builds_the_standing_week_from_the_week_setup_ran_in() {
    let (path, user_id) = as_left_by_0_18("standing-upgrade");
    initialize(&path, NEXT_WEEK).unwrap();
    let conn = open_connection(&path).unwrap();
    assert_eq!(
        standing_blocks(&conn, user_id, NEXT_WEEK).unwrap(),
        vec![school(), soccer()]
    );
    assert_eq!(
        ids(&seen(&conn, user_id, "2026-11-02")),
        vec!["school", "activity-1"]
    );
    // The week before Setup is left alone, and Setup's week keeps its own missed Monday.
    assert_eq!(ids(&seen(&conn, user_id, WEEK_BEFORE)), vec!["gym"]);
    let (setup_week, revision) = week_row(&conn, user_id, SETUP_WEEK);
    assert_eq!(setup_week[0]["missed_days"], json!([0]));
    assert_eq!(revision, 1);
    let version: i64 = conn
        .query_row(
            "SELECT prefs_version FROM preferences WHERE user_id = ?1",
            [user_id],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(version, 3);
}

#[test]
fn the_upgrade_runs_once_so_a_standing_week_emptied_later_stays_empty() {
    let (path, user_id) = as_left_by_0_18("standing-once");
    initialize(&path, NEXT_WEEK).unwrap();
    {
        let conn = open_connection(&path).unwrap();
        set_standing(&conn, user_id, NEXT_WEEK, "[]").unwrap();
        conn.execute_batch("COMMIT").unwrap();
    }
    initialize(&path, NEXT_WEEK).unwrap();
    let conn = open_connection(&path).unwrap();
    assert_eq!(
        standing_blocks(&conn, user_id, WEEK_AFTER).unwrap(),
        Vec::<Value>::new()
    );
    // The weeks before the change still have what stood then.
    assert_eq!(
        standing_blocks(&conn, user_id, SETUP_WEEK).unwrap(),
        vec![school(), soccer()]
    );
}

#[test]
fn a_change_reaches_this_week_on_and_leaves_earlier_weeks_as_they_were() {
    let (conn, user_id) = fresh_account("standing-change");
    set_standing(
        &conn,
        user_id,
        SETUP_WEEK,
        &text(&json!([school(), soccer()])),
    )
    .unwrap();
    let mut missed_wednesday = school();
    missed_wednesday["missed_days"] = json!([2, 4]);
    add_week(
        &conn,
        user_id,
        WEEK_AFTER,
        &json!([missed_wednesday, gym()]),
    );

    let mut later = school();
    later["start"] = json!("09:00");
    later["duration_min"] = json!(360);
    later["days"] = json!([0, 1, 2, 3]);
    let changed = set_standing(&conn, user_id, NEXT_WEEK, &text(&json!([later.clone()]))).unwrap();
    assert_eq!(changed, vec![WEEK_AFTER.to_string()]);

    // An unsaved week before the change keeps the old School and Soccer.
    assert_eq!(seen(&conn, user_id, SETUP_WEEK), vec![school(), soccer()]);
    assert_eq!(seen(&conn, user_id, NEXT_WEEK), vec![later.clone()]);
    // The saved later week: new times, Wednesday still missed, Friday no longer a school day.
    let (after, revision) = week_row(&conn, user_id, WEEK_AFTER);
    let mut expected = later;
    expected["missed_days"] = json!([2]);
    assert_eq!(after, json!([expected, gym()]));
    assert_eq!(revision, 2);
}

#[test]
fn every_week_removes_a_block_from_saved_later_weeks_too() {
    let (conn, user_id) = fresh_account("standing-remove");
    set_standing(
        &conn,
        user_id,
        SETUP_WEEK,
        &text(&json!([school(), soccer()])),
    )
    .unwrap();
    add_week(
        &conn,
        user_id,
        WEEK_AFTER,
        &json!([school(), soccer(), gym()]),
    );
    set_standing(&conn, user_id, NEXT_WEEK, &text(&json!([school()]))).unwrap();
    assert_eq!(
        ids(&seen(&conn, user_id, WEEK_AFTER)),
        vec!["school", "gym"]
    );
    assert_eq!(
        ids(&seen(&conn, user_id, SETUP_WEEK)),
        vec!["school", "activity-1"]
    );
}

#[test]
fn a_change_for_an_earlier_week_replaces_a_later_change() {
    let (conn, user_id) = fresh_account("standing-replace");
    set_standing(&conn, user_id, SETUP_WEEK, &text(&json!([school()]))).unwrap();
    set_standing(
        &conn,
        user_id,
        WEEK_AFTER,
        &text(&json!([school(), soccer()])),
    )
    .unwrap();
    set_standing(&conn, user_id, NEXT_WEEK, &text(&json!([school()]))).unwrap();
    assert_eq!(
        standing_blocks(&conn, user_id, "2026-11-30").unwrap(),
        vec![school()]
    );
}

#[test]
fn rows_carry_over_to_another_account_and_go_with_the_account() {
    let (conn, user_id) = fresh_account("standing-export");
    set_standing(
        &conn,
        user_id,
        SETUP_WEEK,
        &text(&json!([school(), soccer()])),
    )
    .unwrap();
    set_standing(&conn, user_id, WEEK_AFTER, &text(&json!([school()]))).unwrap();
    let rows = standing_rows(&conn, user_id).unwrap();
    conn.execute(
        "INSERT INTO users(username, password_hash) VALUES ('bea', 'x')",
        [],
    )
    .unwrap();
    let other = conn.last_insert_rowid();
    replace_standing(&conn, other, &rows).unwrap();
    assert_eq!(standing_rows(&conn, other).unwrap(), rows);
    assert_eq!(
        standing_blocks(&conn, other, NEXT_WEEK).unwrap(),
        vec![school(), soccer()]
    );
    assert_eq!(
        standing_blocks(&conn, other, WEEK_AFTER).unwrap(),
        vec![school()]
    );

    delete_account(&conn, user_id).unwrap();
    assert_eq!(standing_rows(&conn, user_id).unwrap(), "[]");
}

#[test]
fn a_restore_point_holds_the_standing_rows_it_was_made_with() {
    let (conn, user_id) = fresh_account("standing-restore-point");
    set_standing(
        &conn,
        user_id,
        SETUP_WEEK,
        &text(&json!([school(), soccer()])),
    )
    .unwrap();
    set_standing(&conn, user_id, WEEK_AFTER, &text(&json!([school()]))).unwrap();
    let rows: Value = serde_json::from_str(&standing_rows(&conn, user_id).unwrap()).unwrap();
    create_restore_point(&conn, user_id, "abc", "Before", "2026-10-10T09:00", &[], 10).unwrap();
    set_standing(&conn, user_id, NEXT_WEEK, &text(&json!([gym()]))).unwrap();
    let (_, body) = restore_point_body(&conn, user_id, "rp-abc")
        .unwrap()
        .unwrap();
    let body: Value = serde_json::from_str(&body).unwrap();
    assert_eq!(body["standing"], rows);
    assert_eq!(rows.as_array().map(Vec::len), Some(3));
}
