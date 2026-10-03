mod common;

use std::path::Path;

use common::{
    Dump, by_id, ids, miss_legacy, no_overlaps, placed_interval, real_clock, solve_legacy,
    solve_open, solve_with, work_span,
};
use flexweek_engine::solver::{SOLVE_BUDGET_MS, TimeBlock, block_from_value};
use flexweek_engine::time::hhmm_to_minutes;
use serde_json::Value;

fn locked(id: &str, title: &str, start: &str, duration_min: i64, days: &[i64]) -> TimeBlock {
    Dump::locked(id, title, duration_min, days, start).into_block()
}

// Mirrors the Python helper's kwargs. The engine crate allows the same lint.
#[allow(clippy::too_many_arguments)]
fn flex(
    id: &str,
    title: &str,
    duration_min: i64,
    days: &[i64],
    priority: i64,
    energy: &str,
    latest: Option<&str>,
    earliest: Option<&str>,
) -> TimeBlock {
    let mut block = Dump::flex(id, title, duration_min, days)
        .priority(priority)
        .energy(energy);
    if let Some(latest) = latest {
        block = block.latest(latest);
    }
    if let Some(earliest) = earliest {
        block = block.earliest(earliest);
    }
    block.into_block()
}

#[test]
fn test_empty_week_is_complete() {
    let trace = solve_legacy(&[]);
    assert!(trace.complete);
    assert!(trace.placed.is_empty());
    assert!(trace.unplaced.is_empty());
    assert!(trace.moves.is_empty());
    assert!(trace.solve_ms < SOLVE_BUDGET_MS);
}

#[test]
fn test_t1_only_locked_is_identity() {
    let school = locked("school", "School", "08:00", 390, &[0, 1, 2, 3, 4]);
    let trace = solve_legacy(&[school]);
    assert!(trace.complete);
    assert!(trace.moves.is_empty());
    assert_eq!(ids(&trace.placed), ["school"]);
    assert!(trace.unplaced.is_empty());
    assert_eq!(trace.placed[0].start.as_deref(), Some("08:00"));
}

#[test]
fn test_t2_one_homework_with_room_is_placed() {
    let school = locked("school", "School", "08:00", 390, &[0]);
    let hw = flex("hw", "Math homework", 60, &[0], 3, "high", None, None);
    let trace = solve_legacy(&[school, hw]);
    let placed = by_id(&trace.placed, "hw");
    assert!(placed.start.is_some());
    assert!(trace.unplaced.is_empty());
    assert!(trace.complete);
    let start = hhmm_to_minutes(placed.start.as_deref().unwrap()).unwrap();
    assert!((6 * 60..8 * 60).contains(&start));
}

#[test]
fn test_t3_test_beats_reading_for_one_slot() {
    let wind = locked("wind", "Wind-down", "07:00", 960, &[0]);
    let test = flex("test", "Chem test review", 60, &[0], 1, "high", None, None);
    let reading = flex("read", "History reading", 60, &[0], 4, "low", None, None);
    let trace = solve_legacy(&[wind, test, reading]);
    assert_eq!(by_id(&trace.placed, "test").start.as_deref(), Some("06:00"));
    assert!(trace.unplaced.iter().any(|block| block.id == "read"));
    assert!(
        trace
            .moves
            .iter()
            .any(|item| item.reason == "PRIORITY_PREEMPT")
    );
    assert!(
        trace
            .failed_constraints
            .iter()
            .any(|item| item == "PRIORITY_PREEMPT")
    );
    assert!(!trace.complete);
}

#[test]
fn test_t4_six_hour_task_into_two_hour_gap() {
    let school = locked("school", "School", "08:00", 390, &[0]);
    let evening = locked("eve", "Evening", "16:30", 390, &[0]);
    let paper = flex(
        "paper",
        "Long paper",
        360,
        &[0],
        3,
        "medium",
        Some("Monday 23:00"),
        None,
    );
    let trace = solve_legacy(&[school, evening, paper]);
    assert!(trace.unplaced.iter().any(|block| block.id == "paper"));
    assert!(
        trace
            .failed_constraints
            .iter()
            .any(|item| item == "NO_SLOT_LEFT")
    );
    assert!(!trace.complete);
}

#[test]
fn test_t5_deadline_before_any_legal_window() {
    let school = locked("school", "School", "08:00", 390, &[0]);
    let quiz = flex(
        "quiz",
        "Spanish quiz prep",
        75,
        &[0],
        1,
        "medium",
        Some("Monday 07:00"),
        None,
    );
    let trace = solve_legacy(&[school, quiz]);
    assert_eq!(ids(&trace.unplaced), ["quiz"]);
    assert!(
        trace
            .failed_constraints
            .iter()
            .any(|item| item == "DEADLINE_MISS")
    );
    assert!(!trace.complete);
}

#[test]
fn test_t6_homework_domain_excludes_sport() {
    let sport = locked("sport", "Soccer", "16:00", 120, &[1]);
    let hw = flex(
        "hw",
        "Physics set",
        60,
        &[1],
        3,
        "medium",
        Some("Tuesday 21:00"),
        None,
    );
    let trace = solve_legacy(&[sport, hw]);
    let (day, start, end) = placed_interval(by_id(&trace.placed, "hw"));
    assert_eq!(day, 1);
    assert!(!flexweek_engine::time::overlaps(
        start,
        end,
        16 * 60,
        18 * 60
    ));
}

#[test]
fn test_t7_packed_fixture_under_budget() {
    let mut blocks = vec![
        locked("school", "School", "08:00", 390, &[0, 1, 2, 3, 4]),
        locked("sleep", "Sleep guard", "22:00", 60, &[0, 1, 2, 3, 4, 5, 6]),
    ];
    for index in 0..12 {
        blocks.push(flex(
            &format!("t{index}"),
            &format!("Task {index}"),
            45,
            &[0, 1, 2, 3, 4, 5, 6],
            3,
            "medium",
            Some("Sunday 21:00"),
            None,
        ));
    }
    let trace = solve_legacy(&blocks);
    assert!(trace.solve_ms < SOLVE_BUDGET_MS);
    assert!(
        trace
            .failed_constraints
            .iter()
            .any(|item| item == "NO_SLOT_LEFT")
            || trace.complete
    );
    assert!(no_overlaps(&trace.placed));
}

#[test]
fn test_paper_due_tomorrow_is_placed_before_deadline() {
    let school = locked("school", "School", "08:00", 390, &[0]);
    let paper = flex(
        "paper",
        "3-hour paper",
        180,
        &[0, 1],
        3,
        "medium",
        Some("Tuesday 08:00"),
        None,
    );
    let trace = solve_legacy(&[school, paper]);
    let (day, _start, end) = placed_interval(by_id(&trace.placed, "paper"));
    assert!((day, end) <= (1, 8 * 60));
}

#[test]
fn test_impossible_oversize_task_is_unplaced() {
    let school = locked("school", "School", "08:00", 390, &[0]);
    let sleep = locked("sleep", "Sleep guard", "22:00", 60, &[0]);
    let giant = flex("giant", "Impossible", 600, &[0], 3, "medium", None, None);
    let trace = solve_legacy(&[school, sleep, giant]);
    assert_eq!(ids(&trace.unplaced), ["giant"]);
    assert!(
        trace
            .failed_constraints
            .iter()
            .any(|item| item == "NO_SLOT_LEFT")
    );
    assert!(!trace.complete);
}

#[test]
fn test_two_homeworks_both_placed() {
    let school = locked("school", "School", "08:00", 390, &[0]);
    let a = flex("a", "Math", 60, &[0], 3, "medium", None, None);
    let b = flex("b", "English", 45, &[0], 3, "medium", None, None);
    let trace = solve_legacy(&[school, a, b]);
    let placed: std::collections::BTreeSet<_> =
        trace.placed.iter().map(|block| block.id.as_str()).collect();
    assert!(placed.contains("school") && placed.contains("a") && placed.contains("b"));
    assert!(trace.complete);
    assert!(no_overlaps(&trace.placed));
}

#[test]
fn test_touching_endpoints_do_not_overlap() {
    let first = flex(
        "first",
        "First",
        60,
        &[0],
        3,
        "medium",
        Some("Monday 12:00"),
        None,
    );
    let second = flex(
        "second",
        "Second",
        60,
        &[0],
        3,
        "medium",
        Some("Monday 12:00"),
        None,
    );
    let trace = solve_legacy(&[first, second]);
    assert!(trace.complete);
    assert!(no_overlaps(&trace.placed));
    let mut starts: Vec<i64> = trace
        .placed
        .iter()
        .filter_map(|block| block.start.as_deref())
        .map(|start| hhmm_to_minutes(start).unwrap())
        .collect();
    starts.sort_unstable();
    assert_eq!(starts, vec![6 * 60, 7 * 60]);
}

#[test]
fn test_sleep_guard_rejects_overflow_past_the_day() {
    let late = flex(
        "late",
        "Too late",
        120,
        &[0],
        3,
        "medium",
        None,
        Some("Monday 23:00"),
    );
    let trace = solve_open(&[late]);
    assert_eq!(ids(&trace.unplaced), ["late"]);
    assert!(
        trace
            .failed_constraints
            .iter()
            .any(|item| item == "SLEEP_GUARD")
    );
}

#[test]
fn test_a_session_that_runs_past_work_windows_is_unplaced() {
    let late = flex(
        "late",
        "Too late",
        120,
        &[0],
        3,
        "medium",
        None,
        Some("Monday 22:00"),
    );
    let trace = solve_legacy(&[late]);
    assert_eq!(ids(&trace.unplaced), ["late"]);
    assert!(
        trace
            .failed_constraints
            .iter()
            .any(|item| item == "WORK_WINDOW_MISS")
    );
}

#[test]
fn test_block_may_end_at_23() {
    let last = flex(
        "last",
        "Wind-down homework",
        60,
        &[0],
        3,
        "medium",
        None,
        Some("Monday 22:00"),
    );
    let trace = solve_legacy(&[last]);
    assert_eq!(by_id(&trace.placed, "last").start.as_deref(), Some("22:00"));
    assert!(trace.complete);
}

#[test]
fn test_placed_flexible_never_starts_after_deadline() {
    let hw = flex(
        "hw",
        "Due noon",
        60,
        &[0, 1, 2],
        3,
        "medium",
        Some("Monday 12:00"),
        None,
    );
    let trace = solve_legacy(&[hw]);
    let (day, start, _end) = placed_interval(by_id(&trace.placed, "hw"));
    assert!((day, start) <= (0, 12 * 60));
}

#[test]
fn test_property_no_output_overlaps_on_demos() {
    for name in ["demo_alex.json", "demo_jordan.json"] {
        let path = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../backend/data")
            .join(name);
        let text = std::fs::read_to_string(&path).unwrap_or_else(|err| panic!("{name}: {err}"));
        let value: Value = serde_json::from_str(&text).unwrap();
        let blocks: Vec<TimeBlock> = value
            .as_array()
            .unwrap()
            .iter()
            .map(|item| block_from_value(item).unwrap())
            .collect();
        let trace = solve_legacy(&blocks);
        assert!(no_overlaps(&trace.placed), "{name}");
        assert!(trace.solve_ms < SOLVE_BUDGET_MS, "{name}");
        for block in &trace.placed {
            if block.kind == "flexible" {
                assert!(block.start.is_some(), "{name} {}", block.id);
            }
        }
    }
}

#[test]
fn test_earliest_is_respected() {
    let hw = flex(
        "hw",
        "Afternoon only",
        60,
        &[0],
        3,
        "medium",
        None,
        Some("Monday 15:00"),
    );
    let trace = solve_legacy(&[hw]);
    let start = hhmm_to_minutes(
        by_id(&trace.placed, "hw")
            .start
            .as_deref()
            .unwrap_or("00:00"),
    )
    .unwrap();
    assert!(start >= 15 * 60);
}

#[test]
fn test_locked_without_start_is_ignored_as_occupancy() {
    let broken = Dump::new("broken", "Broken lock", "locked", 60, &[0]).into_block();
    let hw = flex("hw", "Homework", 30, &[0], 3, "medium", None, None);
    let trace = solve_legacy(&[broken, hw]);
    assert!(trace.placed.iter().any(|block| block.id == "hw"));
}

#[test]
fn test_unsolvable_week_returns_partial_not_error() {
    let school = locked("school", "School", "06:00", 1020, &[0]);
    let hw = flex(
        "hw",
        "Homework",
        60,
        &[0],
        3,
        "medium",
        Some("Monday 21:00"),
        None,
    );
    let other = flex("sat", "Weekend reading", 30, &[5], 3, "medium", None, None);
    let trace = solve_legacy(&[school, hw, other]);
    let placed: std::collections::BTreeSet<_> =
        trace.placed.iter().map(|block| block.id.as_str()).collect();
    let unplaced: std::collections::BTreeSet<_> = trace
        .unplaced
        .iter()
        .map(|block| block.id.as_str())
        .collect();
    assert!(placed.contains("sat"));
    assert!(unplaced.contains("hw"));
    assert!(!trace.complete);
    assert!(!trace.failed_constraints.is_empty());
}

#[test]
fn test_moves_record_unplaced_reasons() {
    let quiz = flex(
        "quiz",
        "Quiz",
        75,
        &[0],
        3,
        "medium",
        Some("Monday 07:00"),
        None,
    );
    let trace = solve_legacy(&[quiz]);
    assert!(
        trace
            .moves
            .iter()
            .any(|item| item.block_id == "quiz" && item.reason == "DEADLINE_MISS")
    );
    assert!(trace.explanations.iter().any(|item| {
        item.block_id == "quiz"
            && item.reason.as_deref() == Some("DEADLINE_MISS")
            && item.message
                == "There is not enough time left before it is due, even with nothing else planned."
    }));
}

#[test]
fn test_deadline_slack_is_classified_from_the_placed_block_end() {
    for (latest, expected_minutes, expected_status) in [
        ("Monday 07:00", 0, "danger"),
        ("Monday 09:00", 120, "tight"),
        ("Monday 12:00", 300, "ok"),
    ] {
        let trace = solve_legacy(&[flex(
            "task",
            "Task",
            60,
            &[0],
            3,
            "high",
            Some(latest),
            None,
        )]);
        let item = trace
            .explanations
            .iter()
            .find(|item| item.slack_min.is_some())
            .unwrap_or_else(|| panic!("{latest}"));
        assert_eq!(item.slack_min, Some(expected_minutes), "{latest}");
        assert_eq!(
            item.slack_status.as_deref(),
            Some(expected_status),
            "{latest}"
        );
    }
}

#[test]
fn test_placed_task_explains_an_energy_mismatch() {
    let trace = solve_legacy(&[flex(
        "task",
        "Task",
        60,
        &[0],
        3,
        "low",
        Some("Monday 07:00"),
        None,
    )]);
    assert!(trace.explanations.iter().any(|item| {
        item.block_id == "task" && item.reason.as_deref() == Some("ENERGY_MISMATCH")
    }));
}

#[test]
fn test_reschedule_after_one_missed_occurrence_records_a_cross_day_move() {
    let school = locked("school", "School", "06:00", 1020, &[0]);
    let homework = flex("homework", "Homework", 60, &[0, 1], 3, "high", None, None);
    let blocks = [school.clone(), homework];
    let before = solve_legacy(&blocks);
    assert_eq!(by_id(&before.placed, "homework").days, vec![1]);

    let after = miss_legacy(&blocks, "school", 0, &before.placed);
    assert!(school.missed_days.is_empty());
    assert!(after.placed.iter().all(|block| block.id != "school"));
    assert_eq!(by_id(&after.placed, "homework").days, vec![0]);
    let move_ = after
        .moves
        .iter()
        .find(|item| item.reason == "RESHUFFLE_AFTER_MISS")
        .expect("move");
    assert_eq!(
        (
            move_.block_id.as_str(),
            move_.from_day,
            move_.from_start.as_deref()
        ),
        ("homework", Some(1), Some("06:00"))
    );
    assert_eq!(
        (move_.to_day, move_.to_start.as_deref()),
        (Some(0), Some("06:00"))
    );
    assert!(after.explanations.iter().any(|item| {
        item.block_id == "homework" && item.reason.as_deref() == Some("RESHUFFLE_AFTER_MISS")
    }));
}

#[test]
fn test_missing_one_day_of_a_repeating_lock_keeps_its_other_occurrences() {
    let school = Dump::locked("school", "School", 60, &[0, 1, 2], "08:00")
        .missed(&[1])
        .into_block();
    let trace = solve_legacy(&[school]);
    assert_eq!(by_id(&trace.placed, "school").days, vec![0, 2]);
}

#[test]
fn test_a_pinned_session_keeps_its_time_and_nothing_is_booked_over_it() {
    let school = locked("school", "School", "08:00", 390, &[0]);
    let pinned = Dump::flex("mine", "Essay", 120, &[0])
        .start("15:00")
        .pinned()
        .into_block();
    let mut blocks = vec![school, pinned];
    for index in 0..3 {
        blocks.push(flex(
            &format!("hw{index}"),
            &format!("Homework {index}"),
            60,
            &[0],
            3,
            "medium",
            None,
            None,
        ));
    }
    let trace = solve_legacy(&blocks);
    let mine = by_id(&trace.placed, "mine");
    assert_eq!(
        (mine.days.clone(), mine.start.as_deref(), mine.pinned),
        (vec![0], Some("15:00"), true)
    );
    assert!(trace.unplaced.is_empty());
    assert!(no_overlaps(&trace.placed));
    let mine_span = placed_interval(mine);
    for index in 0..3 {
        let (_day, start, end) = placed_interval(by_id(&trace.placed, &format!("hw{index}")));
        assert!(end <= mine_span.1 || start >= mine_span.2);
    }
}

#[test]
fn test_a_low_session_skips_midnight_when_the_morning_is_free() {
    let evening = locked(
        "evening",
        "Evening",
        "17:00",
        6 * 60,
        &[0, 1, 2, 3, 4, 5, 6],
    );
    let reading = flex(
        "read",
        "History reading",
        60,
        &[0, 1, 2],
        3,
        "low",
        None,
        None,
    );
    let trace = solve_open(&[evening, reading]);
    let placed = by_id(&trace.placed, "read");
    assert_eq!(placed.days, vec![0]);
    assert_eq!(placed.start.as_deref(), Some("06:00"));
}

#[test]
fn test_a_session_uses_the_night_when_the_day_is_full() {
    let occupied = locked("day", "Day", "06:00", 17 * 60, &[0, 1, 2]);
    let reading = flex(
        "read",
        "History reading",
        60,
        &[0, 1, 2],
        3,
        "medium",
        None,
        None,
    );
    let trace = solve_open(&[occupied, reading]);
    let placed = by_id(&trace.placed, "read");
    let start = hhmm_to_minutes(placed.start.as_deref().expect("start")).unwrap();
    assert_eq!(placed.days, vec![0]);
    assert!(!(6 * 60..23 * 60).contains(&start));
}

#[test]
fn test_homework_is_never_planned_in_a_quarter_hour_a_block_at_any_minute_touches() {
    let lesson = locked("lesson", "Lesson", "17:37", 45, &[0]);
    let mut blocks = vec![lesson];
    for index in 0..4 {
        blocks.push(flex(
            &format!("hw-{index}"),
            "Homework",
            15,
            &[0],
            3,
            "medium",
            None,
            None,
        ));
    }
    let evening = vec![work_span(&[0], "17:30", "18:45", None)];
    let trace = solve_with(&blocks, None, None, Some(&evening), &real_clock());
    let starts: Vec<_> = trace
        .placed
        .iter()
        .filter(|block| block.kind == "flexible")
        .map(|block| block.start.clone())
        .collect();
    assert_eq!(starts, vec![Some("18:30".to_string())]);
}
