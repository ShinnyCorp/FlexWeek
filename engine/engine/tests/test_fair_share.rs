//! Item 1c, part C: work due after this Sunday gets a fair share of this week, and the rest waits
//! for next week's Plan.

use flexweek_engine::desk::planning::fair_share;
use serde_json::{Map, Value, json};

const WEEK: &str = "2026-10-05"; // Monday

fn science(due: &str, estimate: i64) -> Map<String, Value> {
    let mut table = Map::new();
    table.insert(
        "sci".into(),
        json!({"id": "sci", "title": "Science project", "due": due, "estimate_min": estimate,
               "focus_minutes": 0}),
    );
    table
}

fn session(id: &str, minutes: i64) -> Value {
    json!({"id": id, "title": "Science project", "kind": "flexible", "assignment_id": "sci",
           "duration_min": minutes, "days": [0, 1, 2, 3, 4, 5, 6]})
}

fn share(
    blocks: &[Value],
    due: &str,
    estimate: i64,
    first_day: i64,
    targets: &[&str],
) -> (Vec<Value>, Vec<Value>) {
    let targets: Vec<String> = targets.iter().map(|t| t.to_string()).collect();
    fair_share(
        blocks,
        &science(due, estimate),
        &json!([]),
        WEEK,
        first_day,
        &targets,
    )
    .unwrap()
}

#[test]
fn due_next_wednesday_planned_on_saturday_gets_two_of_its_four_days() {
    // Sat and Sun this week, Mon and Tue next week: 2 h over 4 days is 1 h this week.
    let (blocks, notes) = share(&[session("s1", 120)], "2026-10-14T23:59", 120, 5, &["s1"]);
    assert_eq!(blocks[0]["duration_min"], json!(60));
    assert_eq!(
        notes,
        vec![
            json!({"assignment_id": "sci", "title": "Science project", "this_week_min": 60, "left_min": 60})
        ]
    );
}

#[test]
fn the_share_rounds_up_to_the_quarter_hour() {
    // Monday plan, due Wednesday next week: 7 of 9 days, 105 min * 7 / 9 = 81.7, so 90.
    let (blocks, _) = share(&[session("s1", 105)], "2026-10-14T23:59", 105, 0, &["s1"]);
    assert_eq!(blocks[0]["duration_min"], json!(90));
}

#[test]
fn work_due_this_week_is_left_whole() {
    let (blocks, notes) = share(&[session("s1", 120)], "2026-10-09T23:59", 120, 5, &["s1"]);
    assert_eq!(blocks[0]["duration_min"], json!(120));
    assert!(notes.is_empty());
}

#[test]
fn due_next_monday_keeps_all_of_it_this_week() {
    // Every plannable day before it is in this week.
    let (blocks, notes) = share(&[session("s1", 120)], "2026-10-12T08:00", 120, 5, &["s1"]);
    assert_eq!(blocks[0]["duration_min"], json!(120));
    assert!(notes.is_empty());
}

#[test]
fn time_already_held_this_week_counts_toward_the_share() {
    let mut held = session("held", 45);
    held["start"] = json!("16:00");
    held["days"] = json!([5]);
    let (blocks, notes) = share(
        &[held.clone(), session("s1", 75)],
        "2026-10-14T23:59",
        120,
        5,
        &["s1"],
    );
    assert_eq!(blocks[1]["duration_min"], json!(15));
    assert_eq!(notes[0]["this_week_min"], json!(60));
}

#[test]
fn a_session_with_no_share_left_leaves_the_week() {
    let mut held = session("held", 60);
    held["start"] = json!("16:00");
    let (blocks, notes) = share(
        &[held, session("s1", 60)],
        "2026-10-14T23:59",
        120,
        5,
        &["s1"],
    );
    assert_eq!(
        blocks
            .iter()
            .map(|b| b["id"].as_str().unwrap())
            .collect::<Vec<_>>(),
        vec!["held"]
    );
    assert_eq!(notes[0]["left_min"], json!(60));
}

#[test]
fn planning_again_does_not_shrink_it_further() {
    // The first plan left a 60 min session; the second plan is worked out from the 120 min left.
    let (blocks, _) = share(&[session("s1", 60)], "2026-10-14T23:59", 120, 5, &["s1"]);
    assert_eq!(blocks[0]["duration_min"], json!(60));
}
