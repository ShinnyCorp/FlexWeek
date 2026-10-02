mod common;

use std::collections::BTreeMap;

use common::{Dump, by_id, ids, late_legacy, solve_legacy, solve_studied, study_span};
use flexweek_engine::plan::{occupancy_from_windows, prepare_solve, spread_sessions, study_rank};
use flexweek_engine::solver::{SOLVE_BUDGET_MS, TimeBlock};
use flexweek_engine::time::hhmm_to_minutes;
use serde_json::json;

const CLUSTER_MESSAGE: &str = "Several tasks are short on time. Shorten a session, pick another day, or free some protected hours. Work that cannot fit stays unplaced.";
const LATE_MESSAGE: &str = "Moved after you ran late so the rest of the day still fits.";

fn locked(id: &str, start: &str, duration_min: i64, days: &[i64]) -> TimeBlock {
    Dump::locked(id, id, duration_min, days, start).into_block()
}

fn flex(
    id: &str,
    duration_min: i64,
    days: &[i64],
    energy: &str,
    latest: Option<&str>,
) -> TimeBlock {
    let mut block = Dump::flex(id, id, duration_min, days).energy(energy);
    if let Some(latest) = latest {
        block = block.latest(latest);
    }
    block.into_block()
}

fn protected(kind: &str, days: &[i64], start: &str, duration_min: i64) -> serde_json::Value {
    json!({"kind": kind, "days": days, "start": start, "duration_min": duration_min})
}

#[test]
fn test_protected_hours_leave_locked_blocks_and_unplace_overflow() {
    let wind = locked("wind", "07:00", 960, &[0]);
    let homework = flex("hw", 60, &[0], "high", None);
    let open_trace = solve_legacy(&[wind.clone(), homework.clone()]);
    assert_eq!(
        by_id(&open_trace.placed, "hw").start.as_deref(),
        Some("06:00")
    );
    let window = protected("downtime", &[0], "06:00", 60);
    let occ = occupancy_from_windows(&[window], None).unwrap();
    let work = common::windows_legacy();
    let trace = common::solve_with(&[wind, homework], Some(&occ), None, Some(&work), &|| 0.0);
    assert_eq!(by_id(&trace.placed, "wind").start.as_deref(), Some("07:00"));
    assert_eq!(by_id(&trace.placed, "wind").days, vec![0]);
    assert_eq!(ids(&trace.unplaced), ["hw"]);
    assert!(!trace.complete);
}

#[test]
fn test_running_late_keeps_sleep_and_reports_overflow_unplaced() {
    let wind = locked("wind", "07:00", 960, &[0]);
    let sleep = locked("sleep", "22:00", 60, &[0, 1, 2, 3, 4, 5, 6]);
    let homework = flex("hw", 60, &[0], "high", None);
    let blocks = [wind, sleep, homework];
    let before = solve_legacy(&blocks);
    assert_eq!(by_id(&before.placed, "hw").start.as_deref(), Some("06:00"));
    let after = late_legacy(&blocks, 0, 60, "06:00", &before.placed);
    assert_eq!(by_id(&after.placed, "wind").start.as_deref(), Some("07:00"));
    assert_eq!(
        by_id(&after.placed, "sleep").start.as_deref(),
        Some("22:00")
    );
    assert_eq!(
        by_id(&after.placed, "sleep").days,
        vec![0, 1, 2, 3, 4, 5, 6]
    );
    assert_eq!(ids(&after.unplaced), ["hw"]);
    assert!(!after.complete);
}

#[test]
fn test_running_late_move_uses_late_copy_not_the_missed_class_sentence() {
    let school = locked("school", "08:00", 390, &[0]);
    let homework = flex("hw", 60, &[0, 1], "high", None);
    let blocks = [school, homework];
    let before = solve_legacy(&blocks);
    assert_eq!(by_id(&before.placed, "hw").days, vec![0]);
    assert_eq!(by_id(&before.placed, "hw").start.as_deref(), Some("06:00"));
    let after = late_legacy(&blocks, 0, 30, "06:00", &before.placed);
    assert_eq!(
        by_id(&after.placed, "school").start.as_deref(),
        Some("08:00")
    );
    assert_eq!(by_id(&after.placed, "hw").days, vec![0]);
    assert_eq!(by_id(&after.placed, "hw").start.as_deref(), Some("06:30"));
    let explanation = after
        .explanations
        .iter()
        .find(|item| {
            item.block_id == "hw" && item.reason.as_deref() == Some("RESHUFFLE_AFTER_MISS")
        })
        .expect("late explanation");
    assert_eq!(explanation.message, LATE_MESSAGE);
}

#[test]
fn test_packed_fixture_stays_under_budget_with_protected_hours() {
    let mut blocks = vec![
        locked("school", "08:00", 390, &[0, 1, 2, 3, 4]),
        locked("sleep", "22:00", 60, &[0, 1, 2, 3, 4, 5, 6]),
    ];
    for index in 0..12 {
        blocks.push(flex(
            &format!("t{index}"),
            45,
            &[0, 1, 2, 3, 4, 5, 6],
            "medium",
            Some("Sunday 21:00"),
        ));
    }
    let meal = protected("meal", &[0, 1, 2, 3, 4, 5, 6], "18:00", 60);
    let occ = occupancy_from_windows(&[meal], Some("21:00")).unwrap();
    let windows = [study_span(&[0, 1, 2, 3, 4], "15:00", 120, None)];
    let trace = solve_studied(&blocks, Some(&occ), &windows);
    assert!(trace.solve_ms < SOLVE_BUDGET_MS);
}

#[test]
fn test_spread_chunks_remaining_minutes_before_the_due_date() {
    let (sessions, remaining) =
        spread_sessions(120, 0, 0, "2026-09-15T23:59", 60, "2026-09-14").unwrap();
    assert_eq!(remaining, 0);
    assert_eq!(
        sessions,
        vec![
            json!({"week_start": "2026-09-14", "date": "2026-09-14", "days": [0], "duration_min": 60}),
            json!({"week_start": "2026-09-14", "date": "2026-09-15", "days": [1], "duration_min": 60}),
        ]
    );
}

#[test]
fn test_spread_keeps_unplaced_remaining_when_the_start_is_after_the_due_date() {
    let (sessions, remaining) =
        spread_sessions(90, 0, 0, "2026-09-15T23:59", 45, "2026-09-16").unwrap();
    assert!(sessions.is_empty());
    assert_eq!(remaining, 90);
}

#[test]
fn test_spread_snaps_a_focus_remainder_down_to_the_grid() {
    let (sessions, remaining) =
        spread_sessions(120, 7, 0, "2026-09-15T23:59", 60, "2026-09-14").unwrap();
    assert_eq!(remaining, 8);
    let durations: Vec<_> = sessions
        .iter()
        .map(|item| item["duration_min"].as_i64().unwrap())
        .collect();
    assert_eq!(durations, vec![60, 45]);
}

#[test]
fn test_spread_reports_a_remainder_that_fits_no_grid_session() {
    let (sessions, remaining) =
        spread_sessions(60, 53, 0, "2026-09-15T23:59", 60, "2026-09-14").unwrap();
    assert!(sessions.is_empty());
    assert_eq!(remaining, 7);
}

#[test]
fn test_study_windows_are_preferred_before_energy() {
    let homework = flex("hw", 60, &[0], "high", None);
    let windows = [study_span(&[0], "18:00", 120, None)];
    let trace = solve_studied(&[homework], None, &windows);
    let placed = by_id(&trace.placed, "hw");
    assert_eq!(placed.start.as_deref(), Some("18:00"));
    assert!(hhmm_to_minutes(placed.start.as_deref().unwrap()).unwrap() >= 18 * 60);
}

#[test]
fn test_a_short_study_window_does_not_claim_a_longer_session() {
    let homework = flex("hw", 60, &[0], "high", None);
    let windows = [study_span(&[0], "21:00", 30, None)];
    let trace = solve_studied(&[homework], None, &windows);
    assert_eq!(by_id(&trace.placed, "hw").start.as_deref(), Some("06:00"));
}

#[test]
fn test_cutoff_occupancy_blocks_starts_that_would_finish_after_it() {
    let homework = flex("hw", 60, &[0], "high", None);
    let occ = occupancy_from_windows(&[], Some("06:15")).unwrap();
    let work = common::windows_legacy();
    let trace = common::solve_with(&[homework], Some(&occ), None, Some(&work), &|| 0.0);
    assert_eq!(ids(&trace.unplaced), ["hw"]);
}

#[test]
fn test_cluster_explanation_only_when_two_tasks_are_in_trouble() {
    let wind = locked("wind", "08:00", 900, &[0]);
    let one = flex("one", 360, &[0], "medium", Some("Monday 23:00"));
    let two = flex("two", 360, &[0], "medium", Some("Monday 23:00"));
    let crowded = solve_legacy(&[wind.clone(), one.clone(), two]);
    let cluster: Vec<_> = crowded
        .explanations
        .iter()
        .filter(|item| item.message == CLUSTER_MESSAGE)
        .collect();
    assert_eq!(cluster.len(), 1);
    assert!(cluster[0].reason.is_none());
    assert!(cluster[0].block_id == "one" || cluster[0].block_id == "two");
    let lonely = solve_legacy(&[wind, one]);
    assert!(
        lonely
            .explanations
            .iter()
            .all(|item| item.message != CLUSTER_MESSAGE)
    );
}

#[test]
fn test_a_subject_window_is_kept_for_that_subject() {
    let math = Dump::flex("math", "math", 60, &[0])
        .energy("high")
        .course("Math")
        .into_block();
    let reading = Dump::flex("reading", "reading", 60, &[0])
        .energy("high")
        .course("reading")
        .into_block();
    let windows = [
        study_span(&[0], "15:30", 90, Some("Math")),
        study_span(&[0], "19:00", 120, Some("Reading")),
    ];
    let trace = solve_studied(&[math, reading], None, &windows);
    assert_eq!(by_id(&trace.placed, "math").start.as_deref(), Some("15:30"));
    assert_eq!(
        by_id(&trace.placed, "reading").start.as_deref(),
        Some("19:00")
    );
}

#[test]
fn test_homework_without_its_own_window_prefers_an_untagged_one() {
    let history = Dump::flex("history", "history", 60, &[0])
        .energy("high")
        .course("History")
        .into_block();
    let windows = [
        study_span(&[0], "15:30", 90, Some("Math")),
        study_span(&[0], "19:00", 120, None),
    ];
    let trace = solve_studied(&[history], None, &windows);
    assert_eq!(
        by_id(&trace.placed, "history").start.as_deref(),
        Some("19:00")
    );
}

#[test]
fn test_another_subjects_window_is_not_a_preference() {
    let reading = Dump::flex("reading", "reading", 60, &[0])
        .energy("high")
        .course("Reading")
        .into_block();
    let windows = [study_span(&[0], "15:30", 90, Some("Math"))];
    let trace = solve_studied(&[reading], None, &windows);
    assert_eq!(
        by_id(&trace.placed, "reading").start.as_deref(),
        Some("06:00")
    );
}

#[test]
fn test_solving_takes_the_subject_from_the_assignment() {
    let session = Dump::flex("s1", "s1", 60, &[0])
        .assignment_id("hw-math")
        .into_value();
    let mut assignments = BTreeMap::new();
    assignments.insert(
        "hw-math".into(),
        json!({"completed": false, "due": "2026-09-18T23:59", "course": "Math"}),
    );
    let (keep, _deadlines, _slack) = prepare_solve(&[session], "2026-09-14", &assignments).unwrap();
    assert_eq!(keep[0]["course"], "Math");
}

#[test]
fn test_a_subjects_own_window_beats_an_earlier_untagged_one() {
    let math = Dump::flex("math", "math", 60, &[0])
        .energy("high")
        .course("Math")
        .into_block();
    let windows = [
        study_span(&[0], "15:30", 90, None),
        study_span(&[0], "19:00", 90, Some("Math")),
    ];
    let trace = solve_studied(&[math], None, &windows);
    assert_eq!(by_id(&trace.placed, "math").start.as_deref(), Some("19:00"));
}

#[test]
fn test_a_window_start_in_other_digits_is_read_as_python_reads_it() {
    // The StudyWindow pattern's `\d` takes any Unicode digit, and Python's int() reads
    // "1٩" as 19, so this window keeps 19:00 to 20:30 for Math.
    let math = Dump::flex("math", "math", 60, &[0])
        .energy("high")
        .course("Math")
        .into_block();
    let windows = [study_span(&[0], "1\u{0669}:00", 90, Some("Math"))];
    let trace = solve_studied(&[math], None, &windows);
    assert_eq!(by_id(&trace.placed, "math").start.as_deref(), Some("19:00"));
}

#[test]
fn test_a_window_start_that_is_not_a_time_is_an_error_not_midnight() {
    let windows = [json!({"days": [0], "start": "bad", "duration_min": 90})];
    assert!(study_rank(&windows, None, 0, 0, 60).is_err());
}
