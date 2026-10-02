//! One account's rows stay invisible to another, and a failure halfway through a
//! multi-step write leaves the account as it was.

mod common;

use common::scratch;
use flexweek_store::{
    Recall, RoutineWrite, assignment_bodies, assignment_body, assignment_exists, availability_json,
    capture_account, count_assignments, count_recovery_codes, create_session_row, delete_account,
    initialize, insert_preferences, insert_restore_point, insert_user, list_account_weeks,
    list_assignment_rows, list_restore_points, list_routines, load_assignment_rows,
    open_connection, own_assignment_rows, preference_row, read_week, recall_operation,
    recovery_hashes, remember_operation, replace_account, replace_recovery_codes, replace_routines,
    restore_point_body, save_routine, session_user, week_blocks, week_starts,
};
use rusqlite::Connection;

fn commit(conn: &Connection) {
    if !conn.is_autocommit() {
        conn.execute("COMMIT", []).unwrap();
    }
}

fn rollback(conn: &Connection) {
    if !conn.is_autocommit() {
        conn.execute("ROLLBACK", []).unwrap();
    }
}

fn two_accounts(name: &str) -> (Connection, i64, i64) {
    let path = scratch(name);
    initialize(&path, "2026-09-14").unwrap();
    let conn = open_connection(&path).unwrap();
    let ada = insert_user(&conn, "ada", "hash-ada").unwrap();
    let bea = insert_user(&conn, "bea", "hash-bea").unwrap();
    conn.execute(
        "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?1, '2026-09-14', ?2, 2)",
        rusqlite::params![ada, r#"[{"id":"ada-week"}]"#],
    )
    .unwrap();
    conn.execute(
        "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?1, '2026-09-14', ?2, 4)",
        rusqlite::params![bea, r#"[{"id":"bea-week"}]"#],
    )
    .unwrap();
    conn.execute(
        "INSERT INTO assignments(user_id, id, body, revision) VALUES (?1, 'hw-ada', ?2, 1)",
        rusqlite::params![ada, r#"{"title":"ada-hw"}"#],
    )
    .unwrap();
    conn.execute(
        "INSERT INTO assignments(user_id, id, body, revision) VALUES (?1, 'hw-bea', ?2, 1)",
        rusqlite::params![bea, r#"{"title":"bea-hw"}"#],
    )
    .unwrap();
    save_routine(
        &conn,
        ada,
        RoutineWrite {
            id: "routine-ada",
            name: "Ada routine",
            body: r#"{"mark":"ada"}"#,
            revision: 0,
            stamp: "2026-09-14T09:00",
            max_count: 10,
        },
    )
    .unwrap();
    insert_restore_point(
        &conn,
        ada,
        "rp-ada",
        "Ada point",
        "2026-09-14T09:00",
        1,
        1,
        r#"{"mark":"ada"}"#,
        &[],
        10,
    )
    .unwrap();
    remember_operation(&conn, ada, "op-ada", "digest-ada", "ada-op", 10).unwrap();
    replace_recovery_codes(&conn, ada, &["ada-hash".to_string()]).unwrap();
    insert_preferences(&conn, ada, 1).unwrap();
    insert_preferences(&conn, bea, 1).unwrap();
    conn.execute(
        "UPDATE preferences SET theme = 'slate', availability_json = ?1 WHERE user_id = ?2",
        rusqlite::params![r#"{"mark":"ada"}"#, ada],
    )
    .unwrap();
    create_session_row(&conn, "token-ada", ada, 2_000, 1_000).unwrap();
    create_session_row(&conn, "token-bea", bea, 2_000, 1_000).unwrap();
    commit(&conn);
    (conn, ada, bea)
}

#[test]
fn another_account_cannot_read_this_accounts_rows() {
    let (conn, ada, bea) = two_accounts("isolation");

    let weeks = list_account_weeks(&conn, bea).unwrap();
    assert_eq!(
        weeks,
        vec![(
            "2026-09-14".to_string(),
            r#"[{"id":"bea-week"}]"#.to_string()
        )]
    );
    assert_eq!(
        week_starts(&conn, bea).unwrap(),
        vec!["2026-09-14".to_string()]
    );
    assert_eq!(
        week_blocks(&conn, bea, "2026-09-14").unwrap().as_deref(),
        Some(r#"[{"id":"bea-week"}]"#)
    );
    assert!(read_week(&conn, bea, "2026-09-21").unwrap().is_none());
    let (blocks, revision) = read_week(&conn, bea, "2026-09-14").unwrap().unwrap();
    assert_eq!((blocks.as_str(), revision), (r#"[{"id":"bea-week"}]"#, 4));

    assert!(!assignment_exists(&conn, bea, "hw-ada").unwrap());
    assert!(assignment_body(&conn, bea, "hw-ada").unwrap().is_none());
    assert!(
        load_assignment_rows(&conn, bea, &["hw-ada".to_string()])
            .unwrap()
            .is_empty()
    );
    let (owned, rows) = own_assignment_rows(&conn, bea, &["hw-ada".to_string()]).unwrap();
    assert!(!owned);
    assert!(rows.is_empty());
    assert_eq!(count_assignments(&conn, bea).unwrap(), 1);
    assert_eq!(
        list_assignment_rows(&conn, bea).unwrap(),
        vec![("hw-bea".to_string(), r#"{"title":"bea-hw"}"#.to_string(), 1)]
    );
    assert_eq!(
        assignment_bodies(&conn, bea).unwrap(),
        vec![(r#"{"title":"bea-hw"}"#.to_string(), 1)]
    );

    assert_eq!(list_routines(&conn, bea).unwrap(), "[]");
    assert_eq!(list_restore_points(&conn, bea).unwrap(), "[]");
    assert!(restore_point_body(&conn, bea, "rp-ada").unwrap().is_none());
    assert_eq!(
        recall_operation(&conn, bea, "op-ada", "digest-ada").unwrap(),
        Recall::Missing
    );
    assert!(recovery_hashes(&conn, bea).unwrap().is_empty());
    assert_eq!(count_recovery_codes(&conn, bea).unwrap(), 0);
    let prefs = preference_row(&conn, bea).unwrap().unwrap();
    assert!(!prefs.contains("slate"));
    assert_eq!(
        availability_json(&conn, bea).unwrap().as_deref(),
        Some("{}")
    );
    let captured = capture_account(&conn, bea).unwrap();
    assert!(!captured.contains("ada-week"));
    assert!(!captured.contains("ada-hw"));
    assert_eq!(
        session_user(&conn, "token-bea", 1_500).unwrap().unwrap().0,
        bea
    );
    assert_ne!(
        session_user(&conn, "token-ada", 1_500).unwrap().unwrap().0,
        bea
    );

    let ada_weeks = list_account_weeks(&conn, ada).unwrap();
    assert_eq!(ada_weeks[0].1, r#"[{"id":"ada-week"}]"#);
}

#[test]
fn a_failed_account_delete_keeps_the_account() {
    let (conn, ada, _bea) = two_accounts("delete-rollback");
    conn.execute_batch(
        "CREATE TRIGGER abort_assignment_delete BEFORE DELETE ON assignments
         BEGIN SELECT RAISE(ABORT, 'stop halfway'); END",
    )
    .unwrap();
    let failed = delete_account(&conn, ada);
    assert!(
        failed.is_err(),
        "the delete must stop on the assignment table"
    );
    rollback(&conn);
    let left: i64 = conn
        .query_row("SELECT COUNT(*) FROM users WHERE id = ?1", [ada], |row| {
            row.get(0)
        })
        .unwrap();
    assert_eq!(left, 1);
    assert_eq!(
        week_blocks(&conn, ada, "2026-09-14").unwrap().as_deref(),
        Some(r#"[{"id":"ada-week"}]"#)
    );
    assert_eq!(
        assignment_body(&conn, ada, "hw-ada").unwrap().as_deref(),
        Some(r#"{"title":"ada-hw"}"#)
    );
}

#[test]
fn a_failed_account_replace_keeps_the_old_rows() {
    let (conn, ada, _bea) = two_accounts("replace-rollback");
    let failed = replace_account(
        &conn,
        ada,
        &[
            ("2026-10-05".to_string(), "[]".to_string(), 1),
            ("2026-10-05".to_string(), "[]".to_string(), 1),
        ],
        &[("hw-new".to_string(), "{}".to_string(), 1)],
    );
    assert!(failed.is_err(), "the second week collides with the first");
    rollback(&conn);
    assert_eq!(
        week_blocks(&conn, ada, "2026-09-14").unwrap().as_deref(),
        Some(r#"[{"id":"ada-week"}]"#)
    );
    assert!(week_blocks(&conn, ada, "2026-10-05").unwrap().is_none());
    assert_eq!(
        assignment_body(&conn, ada, "hw-ada").unwrap().as_deref(),
        Some(r#"{"title":"ada-hw"}"#)
    );
    assert!(assignment_body(&conn, ada, "hw-new").unwrap().is_none());
}

#[test]
fn a_failed_routine_replace_keeps_the_old_routines() {
    let (conn, ada, _bea) = two_accounts("routines-rollback");
    let failed = replace_routines(
        &conn,
        ada,
        r#"[
            {"id":"new","name":"New","body":"{}","revision":1,"created_at":"t","updated_at":"t"},
            {"id":"bad","body":"{}","revision":1,"created_at":"t","updated_at":"t"}
        ]"#,
    );
    assert!(failed.is_err(), "the second routine has no name");
    rollback(&conn);
    let listed = list_routines(&conn, ada).unwrap();
    assert!(listed.contains("routine-ada"));
    assert!(listed.contains("Ada routine"));
    assert!(!listed.contains("\"new\""));
}
