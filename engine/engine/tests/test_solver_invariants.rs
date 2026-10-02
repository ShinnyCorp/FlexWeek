mod common;

use std::cell::Cell;

use common::{Dump, real_clock, solve_legacy, solve_with, windows_legacy, windows_open};
use flexweek_engine::solver::TimeBlock;

/// Seeded LCG, not Python's `random.Random`: this crate cannot add a property-testing crate.
/// Twenty seeds times two windows is the same case count, and the invariants are the same.
struct Lcg(u64);

impl Lcg {
    fn new(seed: u64) -> Self {
        Self(seed.wrapping_add(1))
    }

    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_mul(1664525).wrapping_add(1013904223);
        self.0
    }

    fn randrange(&mut self, start: u64, end: u64) -> u64 {
        start + self.next() % (end - start)
    }

    fn randint(&mut self, start: u64, end: u64) -> u64 {
        self.randrange(start, end + 1)
    }

    fn choice(&mut self, values: &[i64]) -> i64 {
        values[self.randrange(0, values.len() as u64) as usize]
    }

    fn sample_days(&mut self) -> Vec<i64> {
        let count = self.randint(1, 2);
        if count == 2 {
            vec![0, 1]
        } else if self.randrange(0, 2) == 0 {
            vec![0]
        } else {
            vec![1]
        }
    }
}

fn raw_locked(id: &str, title: &str, start: &str, duration_min: i64, days: &[i64]) -> TimeBlock {
    Dump::new(id, title, "locked", duration_min, days)
        .start(start)
        .into_block()
}

#[test]
fn test_generated_weeks_preserve_grid_bounds_occupancy_and_input() {
    let names = ["Monday", "Tuesday"];
    for seed in 0..20 {
        for (mode, day_first, day_last, open) in [
            ("legacy-hours", 6 * 60, 23 * 60, false),
            ("open-day", 0, 24 * 60, true),
        ] {
            let mut rng = Lcg::new(seed);
            let mut blocks = vec![
                Dump::new("school", "School", "locked", 180, &[0, 1])
                    .start("08:00")
                    .missed(&[0])
                    .into_block(),
                Dump::flex("spent", "Finished work", 60, &[1])
                    .start("12:00")
                    .finished()
                    .into_block(),
                Dump::flex("done", "Done without placement", 60, &[0])
                    .finished()
                    .into_block(),
            ];
            for index in 0..6 {
                let day = rng.randrange(0, 2) as usize;
                let days = rng.sample_days();
                let earliest = rng.randrange(6, 10);
                let latest = rng.randrange(11, 18);
                let duration = rng.choice(&[15, 30, 60, 90]);
                blocks.push(
                    Dump::flex(
                        &format!("task-{index}"),
                        &format!("Task {index}"),
                        duration,
                        &days,
                    )
                    .earliest(&format!("{} {earliest:02}:00", names[day]))
                    .latest(&format!("{} {latest:02}:00", names[day]))
                    .into_block(),
                );
            }
            let before = blocks.clone();
            let windows = if open {
                windows_open()
            } else {
                windows_legacy()
            };
            let trace = solve_with(&blocks, None, None, Some(&windows), &real_clock());
            assert_eq!(blocks, before, "seed {seed} {mode} input");
            let school = trace
                .placed
                .iter()
                .find(|block| block.id == "school")
                .expect("school");
            assert_eq!(school.days, vec![1], "seed {seed} {mode}");
            let spent = trace
                .placed
                .iter()
                .find(|block| block.id == "spent")
                .expect("spent");
            assert_eq!(spent.start.as_deref(), Some("12:00"), "seed {seed} {mode}");
            assert_eq!(spent.days, vec![1], "seed {seed} {mode}");
            let pending: std::collections::BTreeSet<_> = blocks
                .iter()
                .filter(|block| block.kind == "flexible" && !block.completed)
                .map(|block| block.id.clone())
                .collect();
            let mut covered: std::collections::BTreeSet<_> = trace
                .placed
                .iter()
                .map(|block| block.id.clone())
                .filter(|id| id != "school" && id != "spent")
                .collect();
            covered.extend(trace.unplaced.iter().map(|block| block.id.clone()));
            assert_eq!(covered, pending, "seed {seed} {mode}");
            let placed_ids: std::collections::BTreeSet<_> =
                trace.placed.iter().map(|block| &block.id).collect();
            assert!(
                trace
                    .unplaced
                    .iter()
                    .all(|block| !placed_ids.contains(&block.id)),
                "seed {seed} {mode}"
            );
            assert_eq!(
                trace.complete,
                trace.unplaced.is_empty(),
                "seed {seed} {mode}"
            );
            let mut occupied = std::collections::BTreeSet::new();
            for block in &trace.placed {
                let start_text = block
                    .start
                    .as_deref()
                    .unwrap_or_else(|| panic!("seed {seed} {mode} {}", block.id));
                let (hour, minute) = start_text.split_once(':').unwrap();
                let start = hour.parse::<i64>().unwrap() * 60 + minute.parse::<i64>().unwrap();
                assert_eq!(start % 15, 0, "seed {seed} {mode} {}", block.id);
                assert!(
                    day_first <= start && start + block.duration_min <= day_last,
                    "seed {seed} {mode} {}",
                    block.id
                );
                for day in &block.days {
                    for slot in (start..start + block.duration_min).step_by(15) {
                        assert!(
                            occupied.insert((*day, slot)),
                            "seed {seed} {mode} {}",
                            block.id
                        );
                    }
                }
                if !pending.contains(&block.id) {
                    continue;
                }
                let original = before.iter().find(|item| item.id == block.id).unwrap();
                assert_eq!(block.days.len(), 1, "seed {seed} {mode}");
                assert!(original.days.contains(&block.days[0]), "seed {seed} {mode}");
                let earliest = original.earliest.as_deref().unwrap();
                let latest = original.latest.as_deref().unwrap();
                let (first_day, first_time) = earliest.split_once(' ').unwrap();
                let (last_day, last_time) = latest.split_once(' ').unwrap();
                let first = (
                    names.iter().position(|name| *name == first_day).unwrap() as i64,
                    first_time[..2].parse::<i64>().unwrap() * 60,
                );
                let last = (
                    names.iter().position(|name| *name == last_day).unwrap() as i64,
                    last_time[..2].parse::<i64>().unwrap() * 60,
                );
                assert!(first <= (block.days[0], start), "seed {seed} {mode}");
                assert!(
                    (block.days[0], start + block.duration_min) <= last,
                    "seed {seed} {mode}"
                );
            }
            let reasons: std::collections::BTreeSet<_> = trace
                .explanations
                .iter()
                .filter(|item| item.reason.is_some())
                .map(|item| item.block_id.as_str())
                .collect();
            assert!(
                trace
                    .unplaced
                    .iter()
                    .all(|block| reasons.contains(block.id.as_str())),
                "seed {seed} {mode}"
            );
        }
    }
}

#[test]
fn test_priority_wins_even_when_reading_has_fewer_candidate_slots() {
    let blocks = [
        raw_locked("rest", "Rest", "07:15", 945, &[0]),
        Dump::flex("exam", "Exam prep", 60, &[0])
            .priority(1)
            .into_block(),
        Dump::flex("reading", "Reading", 75, &[0])
            .priority(4)
            .into_block(),
    ];
    let trace = solve_legacy(&blocks);
    let placed: std::collections::BTreeSet<_> =
        trace.placed.iter().map(|block| block.id.as_str()).collect();
    assert_eq!(placed, std::collections::BTreeSet::from(["rest", "exam"]));
    assert_eq!(
        trace
            .unplaced
            .iter()
            .map(|block| block.id.as_str())
            .collect::<Vec<_>>(),
        vec!["reading"]
    );
    let reason = trace
        .moves
        .iter()
        .find(|item| item.block_id == "reading")
        .expect("reading move")
        .reason
        .as_str();
    assert_eq!(reason, "PRIORITY_PREEMPT");
}

#[test]
fn test_one_exam_block_wins_capacity_over_two_reading_blocks() {
    let blocks = [
        raw_locked("rest", "Rest", "07:00", 960, &[0]),
        Dump::flex("exam", "Exam prep", 60, &[0])
            .priority(1)
            .energy("high")
            .into_block(),
        Dump::flex("read-1", "Read one", 30, &[0])
            .priority(4)
            .energy("high")
            .into_block(),
        Dump::flex("read-2", "Read two", 30, &[0])
            .priority(4)
            .energy("high")
            .into_block(),
    ];
    let trace = solve_legacy(&blocks);
    let placed: std::collections::BTreeSet<_> =
        trace.placed.iter().map(|block| block.id.as_str()).collect();
    let unplaced: std::collections::BTreeSet<_> = trace
        .unplaced
        .iter()
        .map(|block| block.id.as_str())
        .collect();
    assert_eq!(placed, std::collections::BTreeSet::from(["rest", "exam"]));
    assert_eq!(
        unplaced,
        std::collections::BTreeSet::from(["read-1", "read-2"])
    );
    let reasons: std::collections::BTreeSet<_> = trace
        .moves
        .iter()
        .map(|item| item.reason.as_str())
        .collect();
    assert_eq!(
        reasons,
        std::collections::BTreeSet::from(["PRIORITY_PREEMPT"])
    );
}

#[test]
fn test_budget_expiry_returns_the_best_partial_placement() {
    // The wrapper consumes the first perf_counter tick as its start. The engine then sees 0, 0, 0, 151.
    let ticks = Cell::new(0u32);
    let elapsed = || {
        let step = ticks.get();
        ticks.set(step + 1);
        if step < 3 { 0.0 } else { 151.0 }
    };
    let blocks = [
        Dump::flex("exam", "Exam", 60, &[0])
            .priority(1)
            .energy("high")
            .into_block(),
        Dump::flex("reading", "Reading", 60, &[0])
            .priority(4)
            .into_block(),
    ];
    let trace = solve_with(&blocks, None, None, Some(&windows_legacy()), &elapsed);
    let placed: Vec<_> = trace
        .placed
        .iter()
        .map(|block| {
            (
                block.id.as_str(),
                block.start.as_deref(),
                block.days.clone(),
            )
        })
        .collect();
    assert_eq!(placed, vec![("exam", Some("06:00"), vec![0])]);
    assert_eq!(
        trace
            .unplaced
            .iter()
            .map(|block| block.id.as_str())
            .collect::<Vec<_>>(),
        vec!["reading"]
    );
    assert!(!trace.complete);
    let explained: Vec<_> = trace
        .explanations
        .iter()
        .filter(|item| item.reason.is_some())
        .map(|item| item.block_id.as_str())
        .collect();
    assert_eq!(explained, vec!["reading"]);
    assert!(blocks[0].start.is_none() && blocks[1].start.is_none());
}

#[test]
fn test_feasible_mixed_priorities_finish_within_budget() {
    let cases = [
        (180, 3, vec![0, 1, 2, 3, 4], 4, 870),
        (60, 4, vec![0], 0, 360),
        (60, 1, vec![1, 2, 3, 4], 1, 360),
        (180, 2, vec![1, 4], 1, 870),
        (180, 1, vec![0, 2, 4], 2, 870),
        (90, 2, vec![0, 2, 3], 0, 1050),
        (90, 1, vec![0, 1, 2, 4], 2, 1050),
        (180, 1, vec![0, 1, 3], 0, 870),
        (60, 3, vec![0, 1, 2, 3], 2, 1140),
        (60, 3, vec![2], 2, 360),
        (90, 3, vec![1, 4], 1, 1050),
        (60, 3, vec![1, 2, 3], 3, 360),
        (60, 4, vec![0, 1, 4], 0, 1140),
        (60, 3, vec![0, 2, 3], 0, 1200),
        (180, 2, vec![0, 3, 4], 3, 870),
        (90, 2, vec![0, 2, 3, 4], 3, 1050),
    ];
    let mut occupied = std::collections::BTreeSet::new();
    for day in 0..5 {
        for minute in (480..870).step_by(15) {
            occupied.insert((day, minute));
        }
    }
    let mut blocks = vec![raw_locked(
        "school",
        "School",
        "08:00",
        390,
        &[0, 1, 2, 3, 4],
    )];
    for (index, (duration, priority, days, day, start)) in cases.iter().enumerate() {
        assert!(days.contains(day) && 360 <= *start && *start + duration <= 1260);
        let slots: std::collections::BTreeSet<_> = (*start..*start + duration)
            .step_by(15)
            .map(|minute| (*day, minute))
            .collect();
        assert!(occupied.is_disjoint(&slots));
        occupied.extend(slots);
        blocks.push(
            Dump::flex(
                &format!("t{index}"),
                &format!("Task {index}"),
                *duration,
                days,
            )
            .priority(*priority)
            .latest("Friday 21:00")
            .into_block(),
        );
    }
    let trace = solve_legacy(&blocks);
    assert!(trace.complete);
    let placed: std::collections::BTreeSet<_> =
        trace.placed.iter().map(|block| block.id.clone()).collect();
    let mut expected = std::collections::BTreeSet::from(["school".to_string()]);
    for index in 0..16 {
        expected.insert(format!("t{index}"));
    }
    assert_eq!(placed, expected);
    assert!(trace.solve_ms < flexweek_engine::solver::SOLVE_BUDGET_MS);
}

#[test]
fn test_feasible_energy_ordering_does_not_spend_budget_on_optional_skips() {
    let mut blocks = Vec::new();
    for day in 0..3 {
        blocks.push(raw_locked(&format!("am{day}"), "AM", "06:00", 510, &[day]));
        blocks.push(raw_locked(&format!("pm{day}"), "PM", "18:30", 270, &[day]));
    }
    let cases = [
        ("t0", 150, vec![0], 4, "medium"),
        ("t1", 30, vec![0], 2, "low"),
        ("t2", 60, vec![0, 1, 2], 1, "medium"),
        ("t3", 120, vec![1], 4, "low"),
        ("t4", 30, vec![1], 3, "low"),
        ("t5", 90, vec![0, 1, 2], 3, "high"),
        ("t6", 90, vec![1, 2], 4, "low"),
        ("t7", 30, vec![2], 3, "high"),
        ("t8", 30, vec![0, 1, 2], 4, "high"),
        ("t9", 90, vec![0, 1, 2], 2, "low"),
    ];
    for (id, duration, days, priority, energy) in cases {
        blocks.push(
            Dump::flex(id, id, duration, &days)
                .priority(priority)
                .energy(energy)
                .latest("Wednesday 18:30")
                .into_block(),
        );
    }
    let trace = solve_legacy(&blocks);
    assert!(trace.complete);
    let flexible: std::collections::BTreeSet<_> = trace
        .placed
        .iter()
        .filter(|block| block.kind == "flexible")
        .map(|block| block.id.as_str())
        .collect();
    assert_eq!(
        flexible,
        std::collections::BTreeSet::from([
            "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9"
        ])
    );
    assert!(trace.solve_ms < flexweek_engine::solver::SOLVE_BUDGET_MS);
}
