//! Rust twin of `desktop/tests/test_pomodoro.py`: splitting a placed block into focus chunks and breaks.

mod common;

use common::desk::{fresh_ids, object, with};
use flexweek_engine::desk::pomodoro::{
    BREAK_TITLE, MAX_BLOCKS, TITLE_MAX, child_title, inflate_for_solve, plan_for, split_children,
    split_solved, splittable,
};
use serde_json::{Map, Value, json};
use std::collections::BTreeSet;

fn prefs() -> Map<String, Value> {
    object(json!({
        "auto_split_pomodoro": true,
        "timer_work_min": 30,
        "timer_break_min": 15,
        "timer_long_break_min": 30,
        "timer_long_break_every": 4,
    }))
}

fn prefs_with(over: Value) -> Map<String, Value> {
    object(with(Value::Object(prefs()), over))
}

fn essay(fields: Value) -> Value {
    with(
        json!({
            "id": "essay",
            "title": "Essay",
            "kind": "flexible",
            "duration_min": 90,
            "days": [0, 1, 2, 3, 4],
            "category": "assignments",
        }),
        fields,
    )
}

fn placed_at(start: &str, day: i64) -> Value {
    json!({"id": "essay", "start": start, "days": [day], "kind": "flexible"})
}

fn children_of(source: &Value, placed: &Value, duration_min: i64) -> Vec<Value> {
    split_children(
        source,
        placed,
        &plan_for(duration_min, Some(&prefs())),
        fresh_ids(),
    )
}

fn role(child: &Value) -> &str {
    child["pomodoro_role"].as_str().expect("pomodoro_role")
}

#[test]
fn test_a_plan_alternates_work_and_breaks() {
    let plan = plan_for(90, Some(&prefs()));
    assert_eq!(plan.get("error"), Some(&Value::Null));
    let segments: Vec<(&str, i64)> = plan["segments"]
        .as_array()
        .expect("segments")
        .iter()
        .map(|s| {
            (
                s["role"].as_str().expect("role"),
                s["duration_min"].as_i64().expect("minutes"),
            )
        })
        .collect();
    assert_eq!(
        segments,
        [
            ("work", 30),
            ("break", 15),
            ("work", 30),
            ("break", 15),
            ("work", 30)
        ]
    );
    assert_eq!(plan["total_min"], 120);
}

#[test]
fn test_off_grid_lengths_are_refused_rather_than_making_starts_the_server_rejects() {
    let plan = plan_for(90, Some(&prefs_with(json!({"timer_work_min": 25}))));
    assert!(plan["error"].as_str().is_some_and(|text| !text.is_empty()));
    assert_eq!(plan["segments"], json!([]));
}

#[test]
fn test_a_long_break_arrives_on_the_cadence() {
    let plan = plan_for(300, Some(&prefs_with(json!({"timer_long_break_every": 2}))));
    let breaks: Vec<i64> = plan["segments"]
        .as_array()
        .expect("segments")
        .iter()
        .filter(|s| s["role"] == "break")
        .map(|s| s["duration_min"].as_i64().expect("minutes"))
        .collect();
    assert_eq!(
        breaks[1],
        prefs()["timer_long_break_min"].as_i64().expect("minutes")
    );
}

#[test]
fn test_chunks_are_laid_end_to_end_from_where_the_solver_put_the_block() {
    let children = children_of(&essay(json!({})), &placed_at("16:00", 3), 90);
    let laid: Vec<(&str, i64)> = children
        .iter()
        .map(|c| {
            (
                c["start"].as_str().expect("start"),
                c["duration_min"].as_i64().expect("minutes"),
            )
        })
        .collect();
    assert_eq!(
        laid,
        [
            ("16:00", 30),
            ("16:30", 15),
            ("16:45", 30),
            ("17:15", 15),
            ("17:30", 30)
        ]
    );
}

#[test]
fn test_every_chunk_lands_on_the_one_day_the_solver_chose() {
    // The source is a flexible block with five candidate days; a chunk has a real place.
    let children = children_of(&essay(json!({})), &placed_at("16:00", 3), 90);
    let days: BTreeSet<String> = children.iter().map(|c| c["days"].to_string()).collect();
    assert_eq!(days, BTreeSet::from(["[3]".to_string()]));
    let kinds: BTreeSet<&str> = children
        .iter()
        .map(|c| c["kind"].as_str().expect("kind"))
        .collect();
    assert_eq!(kinds, BTreeSet::from(["locked"]));
}

#[test]
fn test_a_chunk_is_numbered_and_a_break_is_named() {
    let children = children_of(&essay(json!({})), &placed_at("16:00", 3), 90);
    let works: Vec<&str> = children
        .iter()
        .filter(|c| role(c) == "work")
        .map(|c| c["title"].as_str().expect("title"))
        .collect();
    assert_eq!(
        works,
        [
            "Essay · focus 1/3",
            "Essay · focus 2/3",
            "Essay · focus 3/3"
        ]
    );
    let breaks: BTreeSet<&str> = children
        .iter()
        .filter(|c| role(c) == "break")
        .map(|c| c["title"].as_str().expect("title"))
        .collect();
    assert_eq!(breaks, BTreeSet::from([BREAK_TITLE]));
}

#[test]
fn test_a_title_at_the_limit_still_produces_one_the_server_accepts() {
    // The week is changed before it is saved, so a title the save rejects strands the split.
    assert!(child_title(&"x".repeat(TITLE_MAX), 2, 9).chars().count() <= TITLE_MAX);
}

#[test]
fn test_only_the_first_chunk_inherits_the_focus_history() {
    // Copying it onto every chunk would count the same minutes once per chunk.
    let source = essay(json!({"focus_minutes": 45, "focus_sessions": 2}));
    let children = children_of(&source, &placed_at("16:00", 3), 90);
    let minutes: Vec<i64> = children
        .iter()
        .map(|c| c["focus_minutes"].as_i64().expect("minutes"))
        .collect();
    assert_eq!(minutes, [45, 0, 0, 0, 0]);
}

#[test]
fn test_progress_on_an_assignment_is_never_copied_onto_a_chunk() {
    // It lives on the assignment, so a chunk carrying it would double-count on credit.
    let source = essay(json!({"assignment_id": "a1", "focus_minutes": 45}));
    let children = children_of(&source, &placed_at("16:00", 3), 90);
    let minutes: BTreeSet<i64> = children
        .iter()
        .map(|c| c["focus_minutes"].as_i64().expect("minutes"))
        .collect();
    assert_eq!(minutes, BTreeSet::from([0]));
    assert!(
        children
            .iter()
            .filter(|c| role(c) == "break")
            .all(|c| c.get("assignment_id").is_none())
    );
}

#[test]
fn test_a_break_carries_none_of_the_work_details() {
    let source =
        essay(json!({"course": "English", "spotify_url": "https://open.spotify.com/track/a"}));
    let children = children_of(&source, &placed_at("16:00", 3), 90);
    let breaks: Vec<&Value> = children.iter().filter(|c| role(c) == "break").collect();
    assert!(breaks.iter().all(
        |c| c.get("course") == Some(&Value::Null) && c.get("spotify_url") == Some(&Value::Null)
    ));
    assert!(breaks.iter().all(|c| c["category"] == "free"));
}

#[test]
fn test_the_solver_is_asked_for_the_time_the_breaks_need_as_well() {
    // Without this the solver reserves 90 minutes and the 120 minutes of chunks land on top of
    // whatever it put next.
    assert_eq!(
        inflate_for_solve(&[essay(json!({}))], Some(&prefs()))[0]["duration_min"],
        120
    );
}

#[test]
fn test_nothing_is_inflated_when_the_setting_is_off() {
    let off = prefs_with(json!({"auto_split_pomodoro": false}));
    assert_eq!(
        inflate_for_solve(&[essay(json!({}))], Some(&off))[0]["duration_min"],
        90
    );
}

#[test]
fn test_a_block_no_longer_than_one_chunk_is_left_alone() {
    let short = essay(json!({"duration_min": 30}));
    assert!(!splittable(&short, Some(&prefs())));
    assert_eq!(
        inflate_for_solve(&[short], Some(&prefs()))[0]["duration_min"],
        30
    );
}

#[test]
fn test_finished_already_split_and_fixed_blocks_are_left_alone() {
    for fields in [
        json!({"completed": true}),
        json!({"pomodoro_role": "work"}),
        json!({"kind": "locked"}),
    ] {
        assert!(
            !splittable(&essay(fields.clone()), Some(&prefs())),
            "{fields}"
        );
    }
}

#[test]
fn test_the_week_is_rebuilt_with_the_chunks_in_place_of_the_block() {
    let other = json!({"id": "dinner", "title": "Dinner", "kind": "locked", "duration_min": 60, "days": [3]});
    let blocks = [essay(json!({})), other];
    let (split, count) = split_solved(
        &blocks,
        Some(&json!({"placed": [placed_at("16:00", 3)]})),
        Some(&prefs()),
        fresh_ids(),
    );
    assert_eq!(count, 1);
    assert_eq!(split[split.len() - 1]["id"], "dinner");
    assert_eq!(split.len(), 6);
}

#[test]
fn test_a_block_the_solver_could_not_place_is_not_split() {
    let (split, count) = split_solved(
        &[essay(json!({}))],
        Some(&json!({"placed": [], "unplaced": [{"id": "essay"}]})),
        Some(&prefs()),
        fresh_ids(),
    );
    assert_eq!(count, 0);
    assert_eq!(split[0]["id"], "essay");
}

#[test]
fn test_chunks_that_would_run_past_the_end_of_the_day_leave_the_block_whole() {
    let (split, count) = split_solved(
        &[essay(json!({}))],
        Some(&json!({"placed": [placed_at("23:00", 3)]})),
        Some(&prefs()),
        fresh_ids(),
    );
    assert_eq!(count, 0);
    assert_eq!(split.len(), 1);
}

#[test]
fn test_a_split_that_would_break_the_week_limit_is_skipped_whole() {
    // The server caps a week at 100 blocks, and a partial split is worse than none.
    let mut blocks = vec![essay(json!({}))];
    blocks.extend((0..MAX_BLOCKS - 2).map(|i| {
        json!({"id": format!("f{i}"), "title": "x", "kind": "locked", "duration_min": 30, "days": [0]})
    }));
    let (split, count) = split_solved(
        &blocks,
        Some(&json!({"placed": [placed_at("16:00", 3)]})),
        Some(&prefs()),
        fresh_ids(),
    );
    assert_eq!(count, 0);
    assert_eq!(split.len(), MAX_BLOCKS - 1);
}

#[test]
fn test_nothing_is_split_when_the_setting_is_off() {
    let off = prefs_with(json!({"auto_split_pomodoro": false}));
    let (split, count) = split_solved(
        &[essay(json!({}))],
        Some(&json!({"placed": [placed_at("16:00", 3)]})),
        Some(&off),
        fresh_ids(),
    );
    assert_eq!(count, 0);
    assert_eq!(split.len(), 1);
}
