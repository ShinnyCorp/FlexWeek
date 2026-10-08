//! JSON the Python wrappers send: `TimeBlock.model_dump()` keeps nulls for
//! earliest, latest, start and course, and omits exclude-if fields until a
//! method sets them (completed, pinned, missed days, assignment id, focus).
#![allow(dead_code)]

pub mod desk;

use flexweek_engine::solver::{
    DeadlineOverrides, SOLVE_BUDGET_MS, SolveTrace, TimeBlock, WorkWindow, block_from_value,
    reschedule_after_miss, reschedule_running_late, solve, work_window_from_value,
};
use flexweek_engine::time::{hhmm_to_minutes, overlaps};
use serde_json::{Map, Value, json};

pub struct Dump {
    map: Map<String, Value>,
}

impl Dump {
    pub fn new(id: &str, title: &str, kind: &str, duration_min: i64, days: &[i64]) -> Self {
        let mut map = Map::new();
        map.insert("id".into(), json!(id));
        map.insert("title".into(), json!(title));
        map.insert("kind".into(), json!(kind));
        map.insert("duration_min".into(), json!(duration_min));
        map.insert("days".into(), json!(days));
        map.insert("priority".into(), json!(3));
        map.insert("energy".into(), json!("medium"));
        map.insert("earliest".into(), Value::Null);
        map.insert("latest".into(), Value::Null);
        map.insert("start".into(), Value::Null);
        map.insert("course".into(), Value::Null);
        Self { map }
    }

    /// Test helpers named `_locked` set priority 1. A raw `TimeBlock(...)` does not.
    pub fn locked(id: &str, title: &str, duration_min: i64, days: &[i64], start: &str) -> Self {
        Self::new(id, title, "locked", duration_min, days)
            .priority(1)
            .start(start)
    }

    pub fn flex(id: &str, title: &str, duration_min: i64, days: &[i64]) -> Self {
        Self::new(id, title, "flexible", duration_min, days)
    }

    pub fn priority(mut self, priority: i64) -> Self {
        self.map.insert("priority".into(), json!(priority));
        self
    }

    pub fn energy(mut self, energy: &str) -> Self {
        self.map.insert("energy".into(), json!(energy));
        self
    }

    pub fn latest(mut self, latest: &str) -> Self {
        self.map.insert("latest".into(), json!(latest));
        self
    }

    pub fn earliest(mut self, earliest: &str) -> Self {
        self.map.insert("earliest".into(), json!(earliest));
        self
    }

    pub fn start(mut self, start: &str) -> Self {
        self.map.insert("start".into(), json!(start));
        self
    }

    pub fn course(mut self, course: &str) -> Self {
        self.map.insert("course".into(), json!(course));
        self
    }

    pub fn finished(mut self) -> Self {
        self.map.insert("completed".into(), json!(true));
        self
    }

    pub fn completed_on(mut self, day: i64) -> Self {
        self.map.insert("completed".into(), json!(true));
        self.map.insert("completed_day".into(), json!(day));
        self
    }

    pub fn missed(mut self, days: &[i64]) -> Self {
        self.map.insert("missed_days".into(), json!(days));
        self
    }

    pub fn pinned(mut self) -> Self {
        self.map.insert("pinned".into(), json!(true));
        self
    }

    pub fn assignment_id(mut self, id: &str) -> Self {
        self.map.insert("assignment_id".into(), json!(id));
        self
    }

    pub fn into_value(self) -> Value {
        Value::Object(self.map)
    }

    pub fn into_block(self) -> TimeBlock {
        block_from_value(&self.into_value()).expect("block json")
    }
}

pub fn windows_legacy() -> Vec<WorkWindow> {
    vec![work_window_from_value(&json!({
        "days": [0, 1, 2, 3, 4, 5, 6],
        "start": "06:00",
        "end": "23:00",
    }))]
}

pub fn windows_open() -> Vec<WorkWindow> {
    vec![work_window_from_value(&json!({
        "days": [0, 1, 2, 3, 4, 5, 6],
        "start": "00:00",
        "end": "24:00",
    }))]
}

pub fn work_span(days: &[i64], start: &str, end: &str, subject: Option<&str>) -> WorkWindow {
    let mut value = json!({"days": days, "start": start, "end": end});
    if let Some(subject) = subject {
        value["subject"] = json!(subject);
    }
    work_window_from_value(&value)
}

/// The solver wants milliseconds since its own start, so build one per call. A clock that
/// never moves makes `solve_ms` always 0 and the budget can never expire.
pub fn real_clock() -> impl Fn() -> f64 {
    let started = std::time::Instant::now();
    move || started.elapsed().as_secs_f64() * 1000.0
}

pub fn solve_with(
    blocks: &[TimeBlock],
    extra_occ: Option<&[u128]>,
    work: Option<&[WorkWindow]>,
    elapsed_ms: &dyn Fn() -> f64,
) -> SolveTrace {
    solve(
        blocks,
        extra_occ,
        work,
        Some(&DeadlineOverrides::default()),
        SOLVE_BUDGET_MS,
        elapsed_ms,
    )
    .expect("solve")
}

/// `solve()` in the Python tests fills in legacy 06:00–23:00 windows.
pub fn solve_legacy(blocks: &[TimeBlock]) -> SolveTrace {
    let work = windows_legacy();
    solve_with(blocks, None, Some(&work), &real_clock())
}

/// `run_solve()` leaves work windows unset. The binding passes None.
pub fn solve_open(blocks: &[TimeBlock]) -> SolveTrace {
    solve_with(blocks, None, None, &real_clock())
}

pub fn miss_legacy(
    blocks: &[TimeBlock],
    missed_block_id: &str,
    missed_day: i64,
    previous: &[TimeBlock],
) -> SolveTrace {
    let work = windows_legacy();
    reschedule_after_miss(
        blocks,
        missed_block_id,
        missed_day,
        previous,
        None,
        Some(&work),
        Some(&DeadlineOverrides::default()),
        SOLVE_BUDGET_MS,
        &real_clock(),
    )
    .expect("reschedule after miss")
}

/// The completed-task test imports `reschedule_after_miss` directly, so windows stay unset.
pub fn miss_open(
    blocks: &[TimeBlock],
    missed_block_id: &str,
    missed_day: i64,
    previous: &[TimeBlock],
) -> SolveTrace {
    reschedule_after_miss(
        blocks,
        missed_block_id,
        missed_day,
        previous,
        None,
        None,
        Some(&DeadlineOverrides::default()),
        SOLVE_BUDGET_MS,
        &real_clock(),
    )
    .expect("reschedule after miss")
}

pub fn late_legacy(
    blocks: &[TimeBlock],
    day: i64,
    minutes: i64,
    from_start: &str,
    previous: &[TimeBlock],
) -> SolveTrace {
    let work = windows_legacy();
    reschedule_running_late(
        blocks,
        day,
        minutes,
        from_start,
        previous,
        None,
        Some(&work),
        Some(&DeadlineOverrides::default()),
        SOLVE_BUDGET_MS,
        &real_clock(),
    )
    .expect("reschedule running late")
}

pub fn by_id<'a>(blocks: &'a [TimeBlock], id: &str) -> &'a TimeBlock {
    blocks
        .iter()
        .find(|block| block.id == id)
        .unwrap_or_else(|| panic!("missing {id}"))
}

pub fn ids(blocks: &[TimeBlock]) -> Vec<&str> {
    blocks.iter().map(|block| block.id.as_str()).collect()
}

pub fn placed_interval(block: &TimeBlock) -> (i64, i64, i64) {
    let start = hhmm_to_minutes(block.start.as_deref().expect("start")).expect("minutes");
    (block.days[0], start, start + block.duration_min)
}

pub fn no_overlaps(placed: &[TimeBlock]) -> bool {
    let mut intervals = Vec::new();
    for block in placed {
        let Some(start_text) = block.start.as_deref() else {
            continue;
        };
        if start_text.is_empty() {
            continue;
        }
        let start = hhmm_to_minutes(start_text).expect("start");
        let end = start + block.duration_min;
        for day in &block.days {
            intervals.push((*day, start, end));
        }
    }
    for (index, left) in intervals.iter().enumerate() {
        for right in intervals.iter().skip(index + 1) {
            if left.0 == right.0 && overlaps(left.1, left.2, right.1, right.2) {
                return false;
            }
        }
    }
    true
}
