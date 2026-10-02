mod common;

use common::{Dump, by_id, ids, miss_open, no_overlaps, solve_legacy};
use flexweek_engine::solver::TimeBlock;

fn locked(
    id: &str,
    title: &str,
    start: &str,
    duration_min: i64,
    days: &[i64],
    completed: bool,
) -> TimeBlock {
    let block = Dump::locked(id, title, duration_min, days, start);
    if completed { block.finished() } else { block }.into_block()
}

// Mirrors the Python helper's kwargs. The engine crate allows the same lint.
#[allow(clippy::too_many_arguments)]
fn flex_done(
    id: &str,
    title: &str,
    duration_min: i64,
    days: &[i64],
    priority: i64,
    energy: &str,
    start: Option<&str>,
    completed: bool,
    completed_day: Option<i64>,
    earliest: Option<&str>,
    latest: Option<&str>,
) -> TimeBlock {
    let mut block = Dump::flex(id, title, duration_min, days)
        .priority(priority)
        .energy(energy);
    if let Some(start) = start {
        block = block.start(start);
    }
    if let Some(day) = completed_day {
        block = block.completed_on(day);
    } else if completed {
        block = block.finished();
    }
    if let Some(earliest) = earliest {
        block = block.earliest(earliest);
    }
    if let Some(latest) = latest {
        block = block.latest(latest);
    }
    block.into_block()
}

#[test]
fn test_pending_task_wins_the_free_hour_over_a_completed_task_without_start() {
    let wind = locked("wind", "Wind-down", "07:00", 960, &[0], false);
    let done = flex_done(
        "done",
        "Finished quiz",
        60,
        &[0],
        1,
        "high",
        None,
        true,
        None,
        None,
        None,
    );
    let pending = flex_done(
        "pending",
        "History reading",
        60,
        &[0],
        3,
        "high",
        None,
        false,
        None,
        None,
        None,
    );
    let trace = solve_legacy(&[wind, done, pending]);
    assert_eq!(ids(&trace.placed), ["wind", "pending"]);
    assert_eq!(
        by_id(&trace.placed, "pending").start.as_deref(),
        Some("06:00")
    );
    assert!(trace.unplaced.is_empty());
    assert!(trace.moves.is_empty());
    assert!(trace.complete);
}

#[test]
fn test_completed_flexible_without_start_appears_nowhere_in_the_trace() {
    let wind = locked("wind", "Wind-down", "07:00", 960, &[0], false);
    let done = flex_done(
        "done",
        "Finished quiz",
        60,
        &[0],
        1,
        "high",
        None,
        true,
        None,
        None,
        None,
    );
    let pending = flex_done(
        "pending",
        "History reading",
        60,
        &[0],
        3,
        "high",
        None,
        false,
        None,
        None,
        None,
    );
    let trace = solve_legacy(&[wind, done, pending]);
    assert_eq!(ids(&trace.placed), ["wind", "pending"]);
    assert!(trace.unplaced.is_empty());
    assert!(trace.moves.is_empty());
    assert!(trace.explanations.is_empty());
    assert!(trace.complete);
}

#[test]
fn test_completed_with_start_keeps_its_slot_and_starves_the_pending_task() {
    let wind = locked("wind", "Wind-down", "07:00", 960, &[0], false);
    let done = flex_done(
        "done",
        "Finished quiz",
        60,
        &[0],
        1,
        "high",
        Some("06:00"),
        true,
        None,
        None,
        None,
    );
    let pending = flex_done(
        "pending",
        "History reading",
        60,
        &[0],
        3,
        "high",
        None,
        false,
        None,
        None,
        None,
    );
    let trace = solve_legacy(&[wind, done, pending]);
    assert_eq!(ids(&trace.placed), ["wind", "done"]);
    assert_eq!(by_id(&trace.placed, "done").start.as_deref(), Some("06:00"));
    assert_eq!(by_id(&trace.placed, "done").days, vec![0]);
    assert_eq!(ids(&trace.unplaced), ["pending"]);
    let reasons: std::collections::BTreeSet<_> = trace
        .moves
        .iter()
        .map(|item| item.reason.as_str())
        .collect();
    assert_eq!(reasons, std::collections::BTreeSet::from(["NO_SLOT_LEFT"]));
    assert!(
        trace
            .failed_constraints
            .iter()
            .any(|item| item == "NO_SLOT_LEFT")
    );
    assert!(!trace.complete);
    assert!(no_overlaps(&trace.placed));
}

#[test]
fn test_completed_locked_block_still_occupies_its_time() {
    let rest = locked("rest", "Evening wind-down", "07:00", 960, &[0], false);
    let lesson = locked("lesson", "Finished lesson", "06:00", 60, &[0], true);
    let pending = flex_done(
        "pending",
        "History reading",
        60,
        &[0],
        3,
        "high",
        None,
        false,
        None,
        None,
        None,
    );
    let trace = solve_legacy(&[rest, lesson, pending]);
    assert_eq!(ids(&trace.placed), ["rest", "lesson"]);
    assert_eq!(
        by_id(&trace.placed, "lesson").start.as_deref(),
        Some("06:00")
    );
    assert_eq!(by_id(&trace.placed, "lesson").days, vec![0]);
    assert_eq!(ids(&trace.unplaced), ["pending"]);
    let reasons: std::collections::BTreeSet<_> = trace
        .moves
        .iter()
        .map(|item| item.reason.as_str())
        .collect();
    assert_eq!(reasons, std::collections::BTreeSet::from(["NO_SLOT_LEFT"]));
    assert!(!trace.complete);
}

#[test]
fn test_missed_day_recovery_leaves_a_completed_flexible_task_alone() {
    let school = Dump::locked("school", "School", 390, &[0, 1], "08:00")
        .missed(&[0])
        .into_block();
    let done = flex_done(
        "done",
        "Finished quiz",
        60,
        &[1],
        3,
        "medium",
        Some("10:00"),
        true,
        None,
        None,
        None,
    );
    let pending = flex_done(
        "pending",
        "Makeup reading",
        60,
        &[0],
        3,
        "high",
        None,
        false,
        None,
        None,
        None,
    );
    let trace = solve_legacy(&[school, done, pending]);
    assert_eq!(ids(&trace.placed), ["school", "done", "pending"]);
    assert_eq!(by_id(&trace.placed, "school").days, vec![1]);
    assert_eq!(by_id(&trace.placed, "pending").days, vec![0]);
    assert_eq!(
        by_id(&trace.placed, "pending").start.as_deref(),
        Some("06:00")
    );
    assert_eq!(by_id(&trace.placed, "done").start.as_deref(), Some("10:00"));
    assert_eq!(by_id(&trace.placed, "done").days, vec![1]);
    assert!(trace.unplaced.is_empty());
    assert!(trace.moves.is_empty());
    assert!(trace.complete);
}

#[test]
fn test_solve_leaves_its_input_blocks_unmodified() {
    let blocks = [
        locked("school", "School", "08:00", 390, &[0], false),
        flex_done(
            "spent",
            "Finished quiz",
            60,
            &[1],
            3,
            "medium",
            Some("10:00"),
            true,
            None,
            None,
            None,
        ),
        flex_done(
            "ghost",
            "Unstarted finish",
            60,
            &[2],
            3,
            "medium",
            None,
            true,
            None,
            None,
            None,
        ),
        flex_done(
            "pending",
            "Homework",
            60,
            &[0],
            3,
            "high",
            None,
            false,
            None,
            None,
            None,
        ),
    ];
    let snapshot = blocks.clone();
    let trace = solve_legacy(&blocks);
    assert_eq!(ids(&trace.placed), ["school", "spent", "pending"]);
    assert_eq!(
        blocks
            .iter()
            .map(|block| block.completed)
            .collect::<Vec<_>>(),
        vec![false, true, true, false]
    );
    assert_eq!(
        blocks
            .iter()
            .map(|block| block.start.clone())
            .collect::<Vec<_>>(),
        vec![Some("08:00".into()), Some("10:00".into()), None, None]
    );
    assert_eq!(
        blocks
            .iter()
            .map(|block| block.days.clone())
            .collect::<Vec<_>>(),
        vec![vec![0], vec![1], vec![2], vec![0]]
    );
    assert_eq!(blocks.as_slice(), snapshot.as_slice());
}

#[test]
fn test_a_finished_task_is_not_reported_as_reshuffled_after_a_miss() {
    let practice = locked("practice", "Practice", "16:00", 60, &[0], false);
    let previously = [flex_done(
        "essay",
        "Essay",
        60,
        &[0],
        3,
        "medium",
        Some("09:00"),
        false,
        None,
        None,
        None,
    )];
    let now = [
        practice,
        flex_done(
            "essay",
            "Essay",
            60,
            &[0],
            3,
            "medium",
            None,
            true,
            None,
            None,
            None,
        ),
    ];
    let trace = miss_open(&now, "practice", 0, &previously);
    assert!(trace.moves.is_empty());
    assert!(trace.unplaced.is_empty());
}

#[test]
fn test_a_finished_task_on_several_candidate_days_holds_no_slot() {
    let done = flex_done(
        "done",
        "Reading",
        60,
        &[0, 1, 2],
        3,
        "medium",
        Some("09:00"),
        true,
        None,
        None,
        None,
    );
    let names = ["Monday", "Tuesday", "Wednesday"];
    let wants: Vec<TimeBlock> = (0..3)
        .map(|day| {
            flex_done(
                &format!("w{day}"),
                &format!("Task {day}"),
                60,
                &[day],
                3,
                "medium",
                None,
                false,
                None,
                Some(&format!("{} 09:00", names[day as usize])),
                Some(&format!("{} 10:00", names[day as usize])),
            )
        })
        .collect();
    let mut blocks = vec![done];
    blocks.extend(wants);
    let trace = solve_legacy(&blocks);
    assert_eq!(ids(&trace.placed), ["w0", "w1", "w2"]);
    let starts: Vec<_> = trace
        .placed
        .iter()
        .map(|block| block.start.as_deref())
        .collect();
    assert_eq!(starts, vec![Some("09:00"), Some("09:00"), Some("09:00")]);
    assert!(trace.unplaced.is_empty());
    assert!(trace.complete);
}

#[test]
fn test_completed_day_keeps_candidate_days_but_occupies_only_the_finished_slot() {
    let done = flex_done(
        "done",
        "Reading",
        60,
        &[0, 1, 2],
        3,
        "medium",
        Some("09:00"),
        true,
        Some(1),
        None,
        None,
    );
    let names = ["Monday", "Tuesday", "Wednesday"];
    let wants: Vec<TimeBlock> = (0..3)
        .map(|day| {
            flex_done(
                &format!("w{day}"),
                &format!("Task {day}"),
                60,
                &[day],
                3,
                "medium",
                None,
                false,
                None,
                Some(&format!("{} 09:00", names[day as usize])),
                Some(&format!("{} 10:00", names[day as usize])),
            )
        })
        .collect();
    let mut blocks = vec![done.clone()];
    blocks.extend(wants);
    let trace = solve_legacy(&blocks);
    assert_eq!(by_id(&trace.placed, "done").days, vec![1]);
    assert_eq!(by_id(&trace.placed, "done").completed_day, Some(1));
    let placed: std::collections::BTreeSet<_> =
        trace.placed.iter().map(|block| block.id.as_str()).collect();
    assert_eq!(
        placed,
        std::collections::BTreeSet::from(["done", "w0", "w2"])
    );
    assert_eq!(ids(&trace.unplaced), ["w1"]);
    assert_eq!(done.days, vec![0, 1, 2]);
}

#[test]
fn test_a_finished_task_placed_on_one_day_still_holds_that_slot() {
    let done = flex_done(
        "done",
        "Reading",
        60,
        &[0],
        3,
        "medium",
        Some("09:00"),
        true,
        None,
        None,
        None,
    );
    let wants = flex_done(
        "wants",
        "Maths",
        60,
        &[0],
        3,
        "medium",
        None,
        false,
        None,
        Some("Monday 09:00"),
        Some("Monday 10:00"),
    );
    let trace = solve_legacy(&[done, wants]);
    assert_eq!(ids(&trace.placed), ["done"]);
    assert_eq!(ids(&trace.unplaced), ["wants"]);
    assert!(!trace.complete);
}

#[test]
fn test_a_collision_with_finished_work_does_not_blame_school_sports_or_sleep() {
    let done = flex_done(
        "done",
        "Essay",
        60,
        &[0],
        3,
        "medium",
        Some("09:00"),
        true,
        None,
        None,
        None,
    );
    let wants = flex_done(
        "wants",
        "Maths",
        60,
        &[0],
        3,
        "medium",
        None,
        false,
        None,
        Some("Monday 09:00"),
        Some("Monday 10:00"),
    );
    let trace = solve_legacy(&[done, wants]);
    let reasons: Vec<_> = trace
        .explanations
        .iter()
        .map(|item| item.reason.as_deref())
        .collect();
    assert_eq!(reasons, vec![Some("LOCKED_OVERLAP")]);
    assert_eq!(trace.explanations.len(), 1);
    let message = trace.explanations[0].message.to_lowercase();
    for blamed in ["school", "sports", "sleep"] {
        assert!(!message.contains(blamed), "{message}");
    }
    assert!(message.contains("finished"), "{message}");
}
