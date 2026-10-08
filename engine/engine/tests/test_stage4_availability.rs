mod common;

use std::collections::BTreeMap;

use common::{Dump, by_id, ids, late_legacy, solve_legacy, work_span};
use flexweek_engine::plan::{
    WINDOW_LIMIT, build_day, build_month, fold_study_windows, occupancy_from_windows,
    prepare_solve, spread_sessions, study_rank,
};
use flexweek_engine::solver::{SOLVE_BUDGET_MS, SolveTrace, TimeBlock, WorkWindow};
use flexweek_engine::time::hhmm_to_minutes;
use serde_json::json;

const CLUSTER_MESSAGE: &str = "Several tasks are short on time. Shorten a session, pick another day, or free some protected hours. Work that cannot fit stays unplaced.";
const LATE_MESSAGE: &str = "Moved after you ran late so the rest of the day still fits.";

/// The planner with one Study hours list and nothing else.
fn solve_in_hours(blocks: &[TimeBlock], hours: &[WorkWindow]) -> SolveTrace {
    common::solve_with(blocks, None, Some(hours), &common::real_clock())
}

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
    let trace = common::solve_with(
        &[wind, homework],
        Some(&occ),
        Some(&work),
        &common::real_clock(),
    );
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
    let mut hours = common::windows_legacy();
    hours.push(work_span(&[0, 1, 2, 3, 4], "15:00", "17:00", Some("Math")));
    let trace = common::solve_with(&blocks, Some(&occ), Some(&hours), &common::real_clock());
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
fn test_study_hours_win_over_energy() {
    // A high-energy session would go in the morning; the one list keeps it in the evening.
    let homework = flex("hw", 60, &[0], "high", None);
    let trace = solve_in_hours(&[homework], &[work_span(&[0], "18:00", "20:00", None)]);
    let placed = by_id(&trace.placed, "hw");
    assert_eq!(placed.start.as_deref(), Some("18:00"));
    assert!(hhmm_to_minutes(placed.start.as_deref().unwrap()).unwrap() >= 18 * 60);
}

#[test]
fn test_cutoff_occupancy_blocks_starts_that_would_finish_after_it() {
    let homework = flex("hw", 60, &[0], "high", None);
    let occ = occupancy_from_windows(&[], Some("06:15")).unwrap();
    let work = common::windows_legacy();
    let trace = common::solve_with(&[homework], Some(&occ), Some(&work), &common::real_clock());
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
        work_span(&[0], "15:30", "17:00", Some("Math")),
        work_span(&[0], "19:00", "21:00", Some("Reading")),
    ];
    let trace = solve_in_hours(&[math, reading], &windows);
    assert_eq!(by_id(&trace.placed, "math").start.as_deref(), Some("15:30"));
    assert_eq!(
        by_id(&trace.placed, "reading").start.as_deref(),
        Some("19:00")
    );
}

#[test]
fn test_homework_without_its_own_window_takes_an_untagged_one() {
    let history = Dump::flex("history", "history", 60, &[0])
        .energy("high")
        .course("History")
        .into_block();
    let windows = [
        work_span(&[0], "15:30", "17:00", Some("Math")),
        work_span(&[0], "19:00", "21:00", None),
    ];
    let trace = solve_in_hours(&[history], &windows);
    assert_eq!(
        by_id(&trace.placed, "history").start.as_deref(),
        Some("19:00")
    );
}

#[test]
fn test_another_subjects_window_is_closed_to_it() {
    let reading = Dump::flex("reading", "reading", 60, &[0])
        .energy("high")
        .course("Reading")
        .into_block();
    let trace = solve_in_hours(
        &[reading],
        &[work_span(&[0], "15:30", "17:00", Some("Math"))],
    );
    assert_eq!(ids(&trace.unplaced), ["reading"]);
    assert_eq!(trace.moves[0].reason, "WORK_WINDOW_MISS");
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
        work_span(&[0], "15:30", "17:00", None),
        work_span(&[0], "19:00", "20:30", Some("Math")),
    ];
    let trace = solve_in_hours(&[math], &windows);
    assert_eq!(by_id(&trace.placed, "math").start.as_deref(), Some("19:00"));
}

#[test]
fn test_a_window_start_in_other_digits_is_read_as_python_reads_it() {
    // The WorkWindow pattern's `\d` takes any Unicode digit, and Python's int() reads
    // "1٩" as 19, so this window keeps 19:00 to 20:30 for Math, ahead of the earlier one.
    let math = Dump::flex("math", "math", 60, &[0])
        .energy("high")
        .course("Math")
        .into_block();
    let windows = [
        work_span(&[0], "15:30", "17:00", None),
        work_span(&[0], "1\u{0669}:00", "20:30", Some("Math")),
    ];
    let trace = solve_in_hours(&[math], &windows);
    assert_eq!(by_id(&trace.placed, "math").start.as_deref(), Some("19:00"));
}

#[test]
fn test_a_window_start_that_is_not_a_time_is_an_error_not_midnight() {
    let windows = [json!({"days": [0], "start": "bad", "end": "12:00"})];
    assert!(study_rank(&windows, None, 0, 0, 60).is_err());
}

// J7: preferred study hours saved by older builds join the one Study hours list.

#[test]
fn test_preferred_hours_join_the_list_as_a_start_and_an_end() {
    let hours = [json!({"days": [0, 1, 2, 3, 4], "start": "16:00", "end": "21:00"})];
    let preferred = [
        json!({"days": [5, 6], "start": "10:00", "duration_min": 120}),
        json!({"days": [0], "start": "23:00", "duration_min": 60, "subject": "Math"}),
    ];
    assert_eq!(
        fold_study_windows(&hours, &preferred).unwrap(),
        vec![
            hours[0].clone(),
            json!({"days": [5, 6], "start": "10:00", "end": "12:00"}),
            json!({"days": [0], "start": "23:00", "end": "24:00", "subject": "Math"}),
        ]
    );
}

#[test]
fn test_preferred_hours_already_in_the_list_add_nothing() {
    let hours = [json!({"days": [0, 1, 2, 3, 4], "start": "16:00", "end": "21:00"})];
    let inside = json!({"days": [0, 1], "start": "17:00", "duration_min": 60});
    let twice = [
        json!({"days": [5], "start": "10:00", "duration_min": 60}),
        json!({"days": [5], "start": "10:00", "duration_min": 60}),
    ];
    assert_eq!(
        fold_study_windows(&hours, std::slice::from_ref(&inside)).unwrap(),
        hours.to_vec()
    );
    assert_eq!(fold_study_windows(&hours, &twice).unwrap().len(), 2);
    // Inside on Monday but not on Saturday: Saturday has no such hours yet, so it is carried.
    let half = json!({"days": [0, 5], "start": "17:00", "duration_min": 60});
    assert_eq!(
        fold_study_windows(&hours, std::slice::from_ref(&half)).unwrap()[1],
        json!({"days": [0, 5], "start": "17:00", "end": "18:00"})
    );
}

#[test]
fn test_a_subjects_preferred_hours_stay_kept_for_it() {
    // Inside hours for any subject, but those do not put Math first; its own window does.
    let hours = [json!({"days": [0], "start": "16:00", "end": "21:00"})];
    let math = json!({"days": [0], "start": "19:00", "duration_min": 90, "subject": "Math"});
    assert_eq!(
        fold_study_windows(&hours, std::slice::from_ref(&math)).unwrap()[1],
        json!({"days": [0], "start": "19:00", "end": "20:30", "subject": "Math"})
    );
}

#[test]
fn test_preferred_hours_alone_become_the_list() {
    let preferred = [json!({"days": [0, 2], "start": "18:00", "duration_min": 120})];
    assert_eq!(
        fold_study_windows(&[], &preferred).unwrap(),
        vec![json!({"days": [0, 2], "start": "18:00", "end": "20:00"})]
    );
}

#[test]
fn test_the_list_never_grows_past_what_can_be_saved() {
    let hours: Vec<_> = (0..WINDOW_LIMIT)
        .map(|index| json!({"days": [index % 7], "start": format!("{:02}:00", index), "end": format!("{:02}:30", index)}))
        .collect();
    let preferred = [json!({"days": [6], "start": "23:00", "duration_min": 60})];
    assert_eq!(fold_study_windows(&hours, &preferred).unwrap(), hours);
}

// Expected values below come from running the Python reference (`backend/tests/engine_ref` at v0.18.0, since deleted) on the
// same blocks. Python tests `not block.get("start")`, so "" means not placed yet, like a missing start.
fn unplaced_essay() -> serde_json::Value {
    json!({
        "id": "s1", "title": "Essay", "kind": "flexible", "days": [0],
        "duration_min": 60, "start": "", "assignment_id": "a1",
    })
}

fn read_at_nine() -> serde_json::Value {
    json!({
        "id": "s0", "title": "Read", "kind": "flexible", "days": [0],
        "duration_min": 60, "start": "09:00", "assignment_id": "a1",
    })
}

#[test]
fn test_a_session_with_an_empty_start_is_not_placed_on_the_day_agenda() {
    let day = build_day("2026-09-07", "2026-09-07", &[unplaced_essay()], &[], &[]).unwrap();
    assert_eq!(day["next_action"], json!({"kind": "add"}));
    assert_eq!(day["workload"]["available_min"], 1440);
    assert_eq!(day["workload"]["scheduled_min"], 0);
    assert_eq!(day["workload"]["by_category"], json!([]));
    assert_eq!(day["sessions"].as_array().unwrap().len(), 1);
}

#[test]
fn test_an_empty_start_does_not_outrank_a_real_start_for_the_next_action() {
    let blocks = [unplaced_essay(), read_at_nine()];
    let day = build_day("2026-09-07", "2026-09-07", &blocks, &[], &[]).unwrap();
    assert_eq!(
        day["next_action"],
        json!({"kind": "start", "block_id": "s0"})
    );
    assert_eq!(day["workload"]["scheduled_min"], 60);
    assert_eq!(day["workload"]["available_min"], 1380);
    assert_eq!(
        day["workload"]["by_category"],
        json!([{"category": null, "scheduled_min": 60, "focus_min": 0}])
    );
}

#[test]
fn test_a_session_with_an_empty_start_is_unscheduled_on_the_month_grid() {
    let weeks = [("2026-09-07".to_string(), vec![unplaced_essay()])];
    let month = build_month("2026-09", &[], &weeks).unwrap();
    assert_eq!(
        month["unscheduled"],
        json!({"session_count": 1, "minutes": 60})
    );
    let day = month["days"]
        .as_array()
        .unwrap()
        .iter()
        .find(|day| day["date"] == "2026-09-07")
        .unwrap();
    assert_eq!(day["session_count"], 0);
    assert_eq!(day["scheduled_min"], 0);
    assert_eq!(day["blocks"], json!([]));
}

#[test]
fn test_an_empty_start_is_not_a_plan_beside_a_placed_session_on_the_month_grid() {
    let weeks = [(
        "2026-09-07".to_string(),
        vec![unplaced_essay(), read_at_nine()],
    )];
    let month = build_month("2026-09", &[], &weeks).unwrap();
    assert_eq!(
        month["unscheduled"],
        json!({"session_count": 1, "minutes": 60})
    );
    let day = month["days"]
        .as_array()
        .unwrap()
        .iter()
        .find(|day| day["date"] == "2026-09-07")
        .unwrap();
    assert_eq!(day["session_count"], 1);
    assert_eq!(day["scheduled_min"], 60);
    assert_eq!(day["blocks"].as_array().unwrap().len(), 1);
    assert_eq!(day["blocks"][0]["id"], "s0");
}
