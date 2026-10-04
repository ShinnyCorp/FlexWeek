//! `backend/solver.py` — search order and scoring match Python exactly.
//!
//! Timing: the caller supplies `budget_ms` and `elapsed_ms` (monotonic milliseconds since
//! solve start). No internal clock.

use serde_json::{Map, Value};

use crate::error::{EngineError, EngineResult};
use crate::time::{
    DAY_START_MIN, SLOT_MIN, SLOTS_PER_DAY, duration_to_slots, hhmm_to_minutes, occupancy_between,
    occupancy_mask, parse_deadline, slot_to_hhmm,
};

pub const SOLVE_BUDGET_MS: f64 = 150.0;

const TIGHT_SLACK_MIN: i64 = 3 * 60;
const DANGER_SLACK_MIN: i64 = 60;

const CLUSTER_COPY: &str = "Several tasks are short on time. Shorten a session, pick another day, \
    or free some protected hours. Work that cannot fit stays unplaced.";
const LATE_COPY: &str = "Moved after you ran late so the rest of the day still fits.";

fn energy_window(energy: &str) -> (i64, i64) {
    match energy {
        "high" => (6 * 60, 12 * 60),
        "medium" => (12 * 60, 17 * 60),
        _ => (17 * 60, 23 * 60),
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct TimeBlock {
    pub id: String,
    pub title: String,
    pub kind: String,
    pub duration_min: i64,
    pub days: Vec<i64>,
    pub priority: i64,
    pub energy: String,
    pub earliest: Option<String>,
    pub latest: Option<String>,
    pub start: Option<String>,
    pub course: Option<String>,
    pub completed: bool,
    pub completed_day: Option<i64>,
    pub missed_days: Vec<i64>,
    pub pinned: bool,
    /// Fields the planner does not read. Copied through so a round trip keeps them.
    pub rest: Map<String, Value>,
}

impl Default for TimeBlock {
    fn default() -> Self {
        Self {
            id: String::new(),
            title: String::new(),
            kind: "flexible".into(),
            duration_min: 0,
            days: vec![],
            priority: 3,
            energy: "medium".into(),
            earliest: None,
            latest: None,
            start: None,
            course: None,
            completed: false,
            completed_day: None,
            missed_days: vec![],
            pinned: false,
            rest: Map::new(),
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct WorkWindow {
    pub days: Vec<i64>,
    pub start: String,
    pub end: String,
    pub subject: Option<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct StudyWindow {
    pub days: Vec<i64>,
    pub start: String,
    pub duration_min: i64,
    pub subject: Option<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Move {
    pub block_id: String,
    pub reason: String,
    pub from_day: Option<i64>,
    pub from_start: Option<String>,
    pub to_day: Option<i64>,
    pub to_start: Option<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Explanation {
    pub block_id: String,
    pub message: String,
    pub reason: Option<String>,
    pub slack_min: Option<i64>,
    pub slack_status: Option<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct SolveTrace {
    pub placed: Vec<TimeBlock>,
    pub unplaced: Vec<TimeBlock>,
    pub moves: Vec<Move>,
    pub explanations: Vec<Explanation>,
    pub failed_constraints: Vec<String>,
    pub solve_ms: f64,
    pub complete: bool,
    pub work_windows: Vec<WorkWindow>,
    pub work_windows_defaulted: bool,
}

#[derive(Clone, Debug, Default)]
pub struct DeadlineOverrides {
    pub deadlines: Vec<(String, Option<(i64, i64)>)>,
    pub slack_deadlines: Vec<(String, (i64, i64))>,
}

fn default_work_windows() -> Vec<WorkWindow> {
    vec![WorkWindow {
        days: vec![0, 1, 2, 3, 4, 5, 6],
        start: "00:00".into(),
        end: "24:00".into(),
        subject: None,
    }]
}

// --- `backend/explain.py` ---

fn sentence(code: &str) -> String {
    crate::plan::sentence(code).unwrap_or_else(|_| code.into())
}

fn amount(minutes: i64) -> String {
    let hours = minutes / 60;
    let rest = minutes % 60;
    if hours == 0 {
        return format!("{rest} min");
    }
    if rest == 0 {
        return format!("{hours} h");
    }
    format!("{hours} h {rest} min")
}

fn slack_sentence(slack_min: i64, status: &str) -> String {
    if slack_min == 0 {
        return "Finishes right when it is due.".into();
    }
    let only = if status == "danger" { "only " } else { "" };
    format!("Finishes {only}{} before it is due.", amount(slack_min))
}

// --- `backend/availability.py`, the one copy in `plan` ---

fn work_value(window: &WorkWindow) -> Value {
    let mut value = serde_json::json!({
        "days": window.days,
        "start": window.start,
        "end": window.end,
    });
    if let Some(subject) = &window.subject {
        value["subject"] = serde_json::json!(subject);
    }
    value
}

fn study_value(window: &StudyWindow) -> Value {
    let mut value = serde_json::json!({
        "days": window.days,
        "start": window.start,
        "duration_min": window.duration_min,
    });
    if let Some(subject) = &window.subject {
        value["subject"] = serde_json::json!(subject);
    }
    value
}

fn merge_occupancy(base: &[u128], extra: &[u128]) -> EngineResult<Vec<u128>> {
    crate::plan::merge_occupancy(base, extra)
}

fn resolve_work_windows(windows: Option<&[WorkWindow]>) -> (Vec<WorkWindow>, bool) {
    let values: Option<Vec<Value>> = windows.map(|items| items.iter().map(work_value).collect());
    let (resolved, defaulted) = crate::plan::resolve_work_windows(values.as_deref());
    (
        resolved.iter().map(work_window_from_value).collect(),
        defaulted,
    )
}

fn lateness_occupancy(day: i64, from_start: &str, minutes: i64) -> EngineResult<Vec<u128>> {
    crate::plan::lateness_occupancy(day, from_start, minutes)
}

fn study_rank(
    windows: &[StudyWindow],
    course: Option<&str>,
    day: i64,
    start_min: i64,
    duration_min: i64,
) -> EngineResult<i64> {
    let values: Vec<Value> = windows.iter().map(study_value).collect();
    crate::plan::study_rank(&values, course, day, start_min, duration_min)
}

fn session_inside_work_windows(
    windows: &[WorkWindow],
    course: Option<&str>,
    day: i64,
    start_min: i64,
    duration_min: i64,
) -> EngineResult<bool> {
    let values: Vec<Value> = windows.iter().map(work_value).collect();
    crate::plan::session_inside_work_windows(&values, course, day, start_min, duration_min)
}

// --- solver helpers ---

fn active_locked(blocks: &[TimeBlock]) -> Vec<TimeBlock> {
    let mut active = Vec::new();
    for block in blocks {
        if block.kind != "locked" {
            continue;
        }
        let days: Vec<i64> = block
            .days
            .iter()
            .copied()
            .filter(|day| !block.missed_days.contains(day))
            .collect();
        if !days.is_empty() {
            let mut copy = block.clone();
            copy.days = days;
            copy.missed_days = vec![];
            active.push(copy);
        }
    }
    active
}

fn flex_positions(blocks: &[TimeBlock]) -> Vec<(String, (i64, String))> {
    blocks
        .iter()
        .filter(|block| block.kind == "flexible" && block.start.is_some() && block.days.len() == 1)
        .map(|block| {
            (
                block.id.clone(),
                (block.days[0], block.start.clone().unwrap_or_default()),
            )
        })
        .collect()
}

fn flex_position_get(positions: &[(String, (i64, String))], id: &str) -> Option<(i64, String)> {
    positions
        .iter()
        .find(|(key, _)| key == id)
        .map(|(_, value)| value.clone())
}

fn slack_status(slack_min: i64) -> &'static str {
    if slack_min <= DANGER_SLACK_MIN {
        "danger"
    } else if slack_min <= TIGHT_SLACK_MIN {
        "tight"
    } else {
        "ok"
    }
}

fn locked_occupancy(locked: &[TimeBlock]) -> EngineResult<Vec<u128>> {
    let mut occ = vec![0u128; 7];
    for block in locked {
        let Some(ref start) = block.start else {
            continue;
        };
        let start_min = hhmm_to_minutes(start)?;
        let taken = occupancy_between(start_min, start_min + block.duration_min)?;
        for day in &block.days {
            occ[*day as usize] |= taken;
        }
    }
    Ok(occ)
}

fn domain(
    block: &TimeBlock,
    occ: &[u128],
    deadline: Option<(i64, i64)>,
    earliest: Option<(i64, i64)>,
    work_windows: &[WorkWindow],
) -> EngineResult<Vec<(i64, i64)>> {
    let n = duration_to_slots(block.duration_min)?;
    let mut out = Vec::new();
    for day in &block.days {
        for slot in 0..=(SLOTS_PER_DAY - n) {
            let start_min = DAY_START_MIN + slot * SLOT_MIN;
            let end_min = start_min + block.duration_min;
            if let Some(deadline) = deadline
                && (*day, end_min) > deadline
            {
                continue;
            }
            if let Some(earliest) = earliest
                && (*day, start_min) < earliest
            {
                continue;
            }
            if occ[*day as usize] & occupancy_mask(slot, n)? != 0 {
                continue;
            }
            if !session_inside_work_windows(
                work_windows,
                block.course.as_deref(),
                *day,
                start_min,
                block.duration_min,
            )? {
                continue;
            }
            out.push((*day, slot));
        }
    }
    Ok(out)
}

fn has_slot(
    block: &TimeBlock,
    duration_min: i64,
    occ: &[u128],
    deadline: Option<(i64, i64)>,
    earliest: Option<(i64, i64)>,
    work_windows: &[WorkWindow],
) -> EngineResult<bool> {
    let mut probe = block.clone();
    probe.duration_min = duration_min;
    Ok(!domain(&probe, occ, deadline, earliest, work_windows)?.is_empty())
}

fn order_values(
    block: &TimeBlock,
    values: &[(i64, i64)],
    windows: &[StudyWindow],
) -> EngineResult<Vec<(i64, i64)>> {
    let (low, high) = energy_window(&block.energy);
    let mut keyed: Vec<(i64, i64, i64, i64, i64)> = Vec::with_capacity(values.len());
    for &(day, slot) in values {
        let start_min = DAY_START_MIN + slot * SLOT_MIN;
        let end_min = start_min + block.duration_min;
        let night = if start_min < 6 * 60 || end_min > 23 * 60 {
            1
        } else {
            0
        };
        let study = study_rank(
            windows,
            block.course.as_deref(),
            day,
            start_min,
            block.duration_min,
        )?;
        let match_energy = if low <= start_min && start_min < high {
            0
        } else {
            1
        };
        keyed.push((night, study, match_energy, day, slot));
    }
    keyed.sort();
    Ok(keyed.into_iter().map(|k| (k.3, k.4)).collect())
}

fn assigned_contains(assigned: &[(String, (i64, i64))], id: &str) -> bool {
    assigned.iter().any(|(key, _)| key == id)
}

fn score_assigned(
    assigned: &[(String, (i64, i64))],
    flex: &[TimeBlock],
    ids: &[String],
) -> (i64, i64, i64, i64) {
    let mut s = (0i64, 0i64, 0i64, 0i64);
    for (id, _) in assigned {
        let Some(idx) = ids.iter().position(|x| x == id) else {
            continue;
        };
        match flex[idx].priority {
            1 => s.0 += 1,
            2 => s.1 += 1,
            3 => s.2 += 1,
            4 => s.3 += 1,
            _ => {}
        }
    }
    s
}

fn flex_block<'a>(flex: &'a [TimeBlock], ids: &'a [String], id: &str) -> Option<&'a TimeBlock> {
    let idx = ids.iter().position(|x| x == id)?;
    flex.get(idx).filter(|b| b.id == *id)
}

fn deadline_key(parsed: Option<(i64, i64)>) -> (i64, i64) {
    parsed.unwrap_or((7, 0))
}

struct SearchCtx<'a> {
    ids: &'a [String],
    flex: &'a [TimeBlock],
    lengths: &'a [i64],
    parsed_deadlines: &'a [Option<(i64, i64)>],
    windows: &'a [StudyWindow],
    budget_ms: f64,
    elapsed_ms: &'a dyn Fn() -> f64,
    best_score: (i64, i64, i64, i64),
    best: Vec<(String, (i64, i64))>,
    timed_out: bool,
}

impl<'a> SearchCtx<'a> {
    fn remaining_ms(&self) -> f64 {
        self.budget_ms - (self.elapsed_ms)()
    }

    fn search(
        &mut self,
        occ: &[u128],
        domains: &[Vec<(i64, i64)>],
        assigned: &[(String, (i64, i64))],
        allow_skips: bool,
    ) -> EngineResult<()> {
        if self.remaining_ms() <= 0.0 {
            self.timed_out = true;
            return Ok(());
        }
        let score = score_assigned(assigned, self.flex, self.ids);
        if score > self.best_score {
            self.best_score = score;
            self.best = assigned.to_vec();
        }
        if assigned.len() == self.ids.len() {
            return Ok(());
        }
        let mut live: Vec<usize> = Vec::new();
        for (idx, id) in self.ids.iter().enumerate() {
            if !assigned_contains(assigned, id) && !domains[idx].is_empty() {
                live.push(idx);
            }
        }
        if live.is_empty() {
            return Ok(());
        }
        let var_idx = *live
            .iter()
            .min_by(|&&a, &&b| {
                let id_a = &self.ids[a];
                let id_b = &self.ids[b];
                let da = domains[a].len();
                let db = domains[b].len();
                let pa = self.flex[a].priority;
                let pb = self.flex[b].priority;
                let ka = deadline_key(self.parsed_deadlines[a]);
                let kb = deadline_key(self.parsed_deadlines[b]);
                (da, pa, ka, id_a.as_str())
                    .partial_cmp(&(db, pb, kb, id_b.as_str()))
                    .unwrap()
            })
            .unwrap();
        let var = self.ids[var_idx].clone();
        let n = self.lengths[var_idx];
        let ordered = order_values(&self.flex[var_idx], &domains[var_idx], self.windows)?;
        for (day, slot) in ordered {
            if self.remaining_ms() <= 0.0 {
                self.timed_out = true;
                return Ok(());
            }
            let mask = occupancy_mask(slot, n)?;
            let mut new_occ = occ.to_vec();
            new_occ[day as usize] |= mask;
            let mut new_domains: Vec<Vec<(i64, i64)>> = domains.to_vec();
            new_domains[var_idx] = vec![];
            for (other_idx, vals) in new_domains.iter_mut().enumerate() {
                if other_idx == var_idx || assigned_contains(assigned, &self.ids[other_idx]) {
                    continue;
                }
                let other_n = self.lengths[other_idx];
                let mut filtered = Vec::new();
                for &(other_day, other_slot) in vals.iter() {
                    if other_day != day {
                        filtered.push((other_day, other_slot));
                        continue;
                    }
                    if occupancy_mask(other_slot, other_n)? & mask == 0 {
                        filtered.push((other_day, other_slot));
                    }
                }
                *vals = filtered;
            }
            let mut new_assigned = assigned.to_vec();
            new_assigned.push((var.clone(), (day, slot)));
            self.search(&new_occ, &new_domains, &new_assigned, allow_skips)?;
            if self.timed_out || self.best.len() == self.ids.len() {
                return Ok(());
            }
        }
        if allow_skips {
            let mut skipped_domains: Vec<Vec<(i64, i64)>> = domains.to_vec();
            skipped_domains[var_idx] = vec![];
            self.search(occ, &skipped_domains, assigned, allow_skips)?;
        }
        Ok(())
    }
}

fn has_gap_inside_windows(
    occ_day: u128,
    n: i64,
    block: &TimeBlock,
    day: i64,
    work_windows: &[WorkWindow],
) -> EngineResult<bool> {
    for slot in 0..=(SLOTS_PER_DAY - n) {
        let start_min = DAY_START_MIN + slot * SLOT_MIN;
        if !session_inside_work_windows(
            work_windows,
            block.course.as_deref(),
            day,
            start_min,
            block.duration_min,
        )? {
            continue;
        }
        if occ_day & occupancy_mask(slot, n)? == 0 {
            return Ok(true);
        }
    }
    Ok(false)
}

fn reason_for(
    block: &TimeBlock,
    block_idx: usize,
    occ_locked: &[u128],
    assigned: &[(String, (i64, i64))],
    flex: &[TimeBlock],
    ids: &[String],
    deadlines: &[Option<(i64, i64)>],
    earliest: &[Option<(i64, i64)>],
    work_windows: &[WorkWindow],
) -> EngineResult<String> {
    let deadline = deadlines[block_idx];
    let earliest_pt = earliest[block_idx];
    let empty = vec![0u128; 7];
    let vs_locked = domain(block, occ_locked, deadline, earliest_pt, work_windows)?;
    if !vs_locked.is_empty() {
        if assigned.iter().any(|(id, _)| {
            flex_block(flex, ids, id)
                .map(|other| other.priority < block.priority)
                .unwrap_or(false)
        }) {
            return Ok("PRIORITY_PREEMPT".into());
        }
        return Ok("NO_SLOT_LEFT".into());
    }
    let unconstrained = domain(block, &empty, deadline, earliest_pt, work_windows)?;
    if unconstrained.is_empty() {
        let open = default_work_windows();
        if deadline.is_some()
            && !has_slot(block, SLOT_MIN, &empty, deadline, earliest_pt, &open)?
            && has_slot(block, SLOT_MIN, &empty, None, earliest_pt, &open)?
        {
            return Ok("DEADLINE_PASSED".into());
        }
        if deadline.is_some() && !domain(block, &empty, None, earliest_pt, work_windows)?.is_empty()
        {
            return Ok("DEADLINE_MISS".into());
        }
        if has_slot(
            block,
            block.duration_min,
            &empty,
            deadline,
            earliest_pt,
            &open,
        )? {
            let due_today = matches!(
                (deadline, earliest_pt),
                (Some((due_day, _)), Some((now_day, _))) if due_day == now_day
            );
            if due_today && !has_slot(block, SLOT_MIN, &empty, deadline, earliest_pt, work_windows)?
            {
                return Ok("NO_STUDY_TIME_TODAY".into());
            }
            return Ok("WORK_WINDOW_MISS".into());
        }
        return Ok("SLEEP_GUARD".into());
    }
    let n = duration_to_slots(block.duration_min)?;
    let mut any_gap = false;
    for day in &block.days {
        if has_gap_inside_windows(occ_locked[*day as usize], n, block, *day, work_windows)? {
            any_gap = true;
            break;
        }
    }
    if !any_gap {
        return Ok("NO_SLOT_LEFT".into());
    }
    Ok("LOCKED_OVERLAP".into())
}

fn apply_deadline_overrides(
    parsed: &mut [Option<(i64, i64)>],
    ids: &[String],
    overrides: Option<&DeadlineOverrides>,
) {
    let Some(overrides) = overrides else {
        return;
    };
    for (id, value) in &overrides.deadlines {
        if let Some(idx) = ids.iter().position(|x| x == id) {
            parsed[idx] = *value;
        }
    }
}

fn apply_slack_overrides(
    slack: &mut [Option<(i64, i64)>],
    ids: &[String],
    overrides: Option<&DeadlineOverrides>,
) {
    let Some(overrides) = overrides else {
        return;
    };
    for (id, value) in &overrides.slack_deadlines {
        if let Some(idx) = ids.iter().position(|x| x == id) {
            slack[idx] = Some(*value);
        }
    }
}

pub fn solve(
    blocks: &[TimeBlock],
    extra_occ: Option<&[u128]>,
    study_windows: Option<&[StudyWindow]>,
    work_windows: Option<&[WorkWindow]>,
    overrides: Option<&DeadlineOverrides>,
    budget_ms: f64,
    elapsed_ms: &dyn Fn() -> f64,
) -> EngineResult<SolveTrace> {
    let locked = active_locked(blocks);
    let every_flexible: Vec<TimeBlock> = blocks
        .iter()
        .filter(|b| b.kind == "flexible")
        .cloned()
        .collect();

    let mut spent: Vec<TimeBlock> = Vec::new();
    for block in &every_flexible {
        if !block.completed || block.start.is_none() {
            continue;
        }
        let mut completed_day = block.completed_day;
        if completed_day.is_none() && block.days.len() == 1 {
            completed_day = Some(block.days[0]);
        }
        if let Some(day) = completed_day {
            let mut copy = block.clone();
            copy.days = vec![day];
            spent.push(copy);
        }
    }

    let held: Vec<TimeBlock> = every_flexible
        .iter()
        .filter(|b| {
            b.pinned && !b.completed && b.start.as_ref().is_some_and(|start| !start.is_empty())
        })
        .cloned()
        .collect();
    let flexible: Vec<TimeBlock> = every_flexible
        .iter()
        .filter(|b| !b.completed && !b.pinned)
        .cloned()
        .collect();

    let mut occ_sources = locked.clone();
    occ_sources.extend(spent.clone());
    occ_sources.extend(held.clone());
    let mut occ_locked = locked_occupancy(&occ_sources)?;
    if let Some(extra) = extra_occ {
        occ_locked = merge_occupancy(&occ_locked, extra)?;
    }

    let windows = study_windows.unwrap_or(&[]);
    let (planning_windows, work_windows_defaulted) = resolve_work_windows(work_windows);

    let ids: Vec<String> = flexible.iter().map(|b| b.id.clone()).collect();
    let mut parsed_deadlines: Vec<Option<(i64, i64)>> = flexible
        .iter()
        .map(|b| parse_deadline(b.latest.as_deref(), &b.days))
        .collect::<EngineResult<Vec<_>>>()?;
    apply_deadline_overrides(&mut parsed_deadlines, &ids, overrides);

    let mut slack_points = parsed_deadlines.clone();
    apply_slack_overrides(&mut slack_points, &ids, overrides);

    let earliest: Vec<Option<(i64, i64)>> = flexible
        .iter()
        .map(|b| parse_deadline(b.earliest.as_deref(), &b.days))
        .collect::<EngineResult<Vec<_>>>()?;

    let lengths: Vec<i64> = flexible
        .iter()
        .map(|b| duration_to_slots(b.duration_min))
        .collect::<EngineResult<Vec<_>>>()?;

    let domains0: Vec<Vec<(i64, i64)>> = flexible
        .iter()
        .enumerate()
        .map(|(idx, block)| {
            domain(
                block,
                &occ_locked,
                parsed_deadlines[idx],
                earliest[idx],
                &planning_windows,
            )
        })
        .collect::<EngineResult<Vec<_>>>()?;

    let mut ctx = SearchCtx {
        ids: &ids,
        flex: &flexible,
        lengths: &lengths,
        parsed_deadlines: &parsed_deadlines,
        windows,
        budget_ms,
        elapsed_ms,
        best_score: (-1, -1, -1, -1),
        best: vec![],
        timed_out: false,
    };

    let domains_copy: Vec<Vec<(i64, i64)>> = domains0.to_vec();
    ctx.search(&occ_locked, &domains_copy, &[], false)?;
    if ctx.best.len() != ids.len() && !ctx.timed_out {
        let domains_copy: Vec<Vec<(i64, i64)>> = domains0.to_vec();
        ctx.search(&occ_locked, &domains_copy, &[], true)?;
    }

    let mut placed_flex = Vec::new();
    let mut occ_final = occ_locked.clone();
    for (block_id, (day, slot)) in &ctx.best {
        let idx = ids.iter().position(|id| id == block_id).unwrap();
        let mut placed = flexible[idx].clone();
        placed.start = Some(slot_to_hhmm(*slot)?);
        placed.days = vec![*day];
        placed_flex.push(placed);
        occ_final[*day as usize] |= occupancy_mask(*slot, lengths[idx])?;
    }

    let mut unplaced = Vec::new();
    let mut moves = Vec::new();
    let mut explanations = Vec::new();
    let mut failed: Vec<String> = Vec::new();
    for (idx, block) in flexible.iter().enumerate() {
        if ctx.best.iter().any(|(id, _)| id == &block.id) {
            continue;
        }
        let reason = reason_for(
            block,
            idx,
            &occ_locked,
            &ctx.best,
            &flexible,
            &ids,
            &parsed_deadlines,
            &earliest,
            &planning_windows,
        )?;
        unplaced.push(block.clone());
        moves.push(Move {
            block_id: block.id.clone(),
            reason: reason.clone(),
            from_day: None,
            from_start: None,
            to_day: None,
            to_start: None,
        });
        explanations.push(Explanation {
            block_id: block.id.clone(),
            reason: Some(reason.clone()),
            message: sentence(&reason),
            slack_min: None,
            slack_status: None,
        });
        if !failed.iter().any(|f| f == &reason) {
            failed.push(reason);
        }
    }

    for block in &placed_flex {
        let start = block.start.as_ref().unwrap();
        let start_min = hhmm_to_minutes(start)?;
        let (low, high) = energy_window(&block.energy);
        if !(low <= start_min && start_min < high) {
            let energy_reason = "ENERGY_MISMATCH".to_string();
            explanations.push(Explanation {
                block_id: block.id.clone(),
                reason: Some(energy_reason.clone()),
                message: sentence(&energy_reason),
                slack_min: None,
                slack_status: None,
            });
        }
        let deadline = slack_points[ids.iter().position(|id| id == &block.id).unwrap()];
        if let Some(deadline) = deadline {
            let day = block.days[0];
            let slack_min =
                (deadline.0 - day) * 24 * 60 + deadline.1 - start_min - block.duration_min;
            let status = slack_status(slack_min).to_string();
            explanations.push(Explanation {
                block_id: block.id.clone(),
                reason: None,
                message: slack_sentence(slack_min, &status),
                slack_min: Some(slack_min),
                slack_status: Some(status),
            });
        }
    }

    let danger = explanations
        .iter()
        .filter(|item| item.slack_status.as_deref() == Some("danger"))
        .count();
    if unplaced.len() + danger >= 2 {
        let block_id = if !unplaced.is_empty() {
            unplaced[0].id.clone()
        } else {
            placed_flex[0].id.clone()
        };
        explanations.push(Explanation {
            block_id,
            message: CLUSTER_COPY.into(),
            reason: None,
            slack_min: None,
            slack_status: None,
        });
    }

    let complete = unplaced.is_empty();
    Ok(SolveTrace {
        placed: locked
            .into_iter()
            .chain(spent)
            .chain(held)
            .chain(placed_flex)
            .collect(),
        unplaced,
        moves,
        explanations,
        failed_constraints: failed,
        solve_ms: elapsed_ms(),
        complete,
        work_windows: planning_windows,
        work_windows_defaulted,
    })
}

fn reshape_moves(
    mut trace: SolveTrace,
    blocks: &[TimeBlock],
    previous_placed: &[TimeBlock],
    reason: &str,
    message: &str,
) -> SolveTrace {
    let before = flex_positions(previous_placed);
    let after = flex_positions(&trace.placed);
    let mut changes: Vec<Move> = Vec::new();
    let unplaced_moves: Vec<(String, usize)> = trace
        .moves
        .iter()
        .enumerate()
        .map(|(idx, m)| (m.block_id.clone(), idx))
        .collect();
    for block in blocks {
        if block.kind != "flexible" || block.completed {
            continue;
        }
        let old = flex_position_get(&before, &block.id);
        let new = flex_position_get(&after, &block.id);
        if old == new {
            continue;
        }
        if new.is_none() {
            if let Some(pos) = unplaced_moves.iter().find(|(id, _)| id == &block.id) {
                let idx = pos.1;
                trace.moves[idx].from_day = old.as_ref().map(|(d, _)| *d);
                trace.moves[idx].from_start = old.as_ref().map(|(_, s)| s.clone());
            } else {
                changes.push(Move {
                    block_id: block.id.clone(),
                    reason: reason.into(),
                    from_day: old.as_ref().map(|(d, _)| *d),
                    from_start: old.as_ref().map(|(_, s)| s.clone()),
                    to_day: None,
                    to_start: None,
                });
            }
        } else if let Some((to_day, to_start)) = new.as_ref() {
            changes.push(Move {
                block_id: block.id.clone(),
                reason: reason.into(),
                from_day: old.as_ref().map(|(d, _)| *d),
                from_start: old.as_ref().map(|(_, s)| s.clone()),
                to_day: Some(*to_day),
                to_start: Some(to_start.clone()),
            });
        }
        if new.is_some() {
            trace.explanations.push(Explanation {
                block_id: block.id.clone(),
                reason: Some(reason.into()),
                message: message.into(),
                slack_min: None,
                slack_status: None,
            });
        }
    }
    trace.moves = changes.into_iter().chain(trace.moves).collect();
    trace
}

pub fn reschedule_after_miss(
    blocks: &[TimeBlock],
    missed_block_id: &str,
    missed_day: i64,
    previous_placed: &[TimeBlock],
    extra_occ: Option<&[u128]>,
    study_windows: Option<&[StudyWindow]>,
    work_windows: Option<&[WorkWindow]>,
    overrides: Option<&DeadlineOverrides>,
    budget_ms: f64,
    elapsed_ms: &dyn Fn() -> f64,
) -> EngineResult<SolveTrace> {
    let mut updated: Vec<TimeBlock> = Vec::new();
    let mut found = false;
    for block in blocks {
        let mut copy = block.clone();
        if copy.id == missed_block_id && copy.kind == "locked" && copy.days.contains(&missed_day) {
            found = true;
            if !copy.missed_days.contains(&missed_day) {
                copy.missed_days.push(missed_day);
                copy.missed_days.sort();
            }
        }
        updated.push(copy);
    }
    if !found {
        return Err(EngineError::value(
            "missed occurrence must identify a locked block on that day",
        ));
    }
    let trace = solve(
        &updated,
        extra_occ,
        study_windows,
        work_windows,
        overrides,
        budget_ms,
        elapsed_ms,
    )?;
    Ok(reshape_moves(
        trace,
        blocks,
        previous_placed,
        "RESHUFFLE_AFTER_MISS",
        &sentence("RESHUFFLE_AFTER_MISS"),
    ))
}

pub fn reschedule_running_late(
    blocks: &[TimeBlock],
    day: i64,
    minutes: i64,
    from_start: &str,
    previous_placed: &[TimeBlock],
    extra_occ: Option<&[u128]>,
    study_windows: Option<&[StudyWindow]>,
    work_windows: Option<&[WorkWindow]>,
    overrides: Option<&DeadlineOverrides>,
    budget_ms: f64,
    elapsed_ms: &dyn Fn() -> f64,
) -> EngineResult<SolveTrace> {
    let late = lateness_occupancy(day, from_start, minutes)?;
    let base = extra_occ
        .map(|v| v.to_vec())
        .unwrap_or_else(|| vec![0u128; 7]);
    let combined = merge_occupancy(&base, &late)?;
    let trace = solve(
        blocks,
        Some(&combined),
        study_windows,
        work_windows,
        overrides,
        budget_ms,
        elapsed_ms,
    )?;
    Ok(reshape_moves(
        trace,
        blocks,
        previous_placed,
        "RESHUFFLE_AFTER_MISS",
        LATE_COPY,
    ))
}

fn i64_field(value: &Value, key: &str, default: i64) -> i64 {
    value.get(key).and_then(Value::as_i64).unwrap_or(default)
}

fn opt_string(value: Option<&Value>) -> Option<String> {
    value.and_then(Value::as_str).map(str::to_string)
}

fn i64_list(value: Option<&Value>) -> Vec<i64> {
    value
        .and_then(Value::as_array)
        .map(|items| items.iter().filter_map(Value::as_i64).collect())
        .unwrap_or_default()
}

const BLOCK_FIELDS: &[&str] = &[
    "id",
    "title",
    "kind",
    "duration_min",
    "days",
    "priority",
    "energy",
    "earliest",
    "latest",
    "start",
    "course",
    "completed",
    "completed_day",
    "missed_days",
    "pinned",
];

pub fn block_from_value(value: &Value) -> EngineResult<TimeBlock> {
    let obj = value
        .as_object()
        .ok_or_else(|| EngineError::value("block must be an object"))?;
    let mut rest = Map::new();
    for (key, item) in obj {
        if !BLOCK_FIELDS.contains(&key.as_str()) {
            rest.insert(key.clone(), item.clone());
        }
    }
    Ok(TimeBlock {
        id: obj.get("id").and_then(Value::as_str).unwrap_or("").into(),
        title: obj
            .get("title")
            .and_then(Value::as_str)
            .unwrap_or("")
            .into(),
        kind: obj
            .get("kind")
            .and_then(Value::as_str)
            .unwrap_or("flexible")
            .into(),
        duration_min: i64_field(value, "duration_min", 0),
        days: i64_list(obj.get("days")),
        priority: i64_field(value, "priority", 3),
        energy: obj
            .get("energy")
            .and_then(Value::as_str)
            .unwrap_or("medium")
            .into(),
        earliest: opt_string(obj.get("earliest")),
        latest: opt_string(obj.get("latest")),
        start: opt_string(obj.get("start")),
        course: opt_string(obj.get("course")),
        completed: obj
            .get("completed")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        completed_day: obj.get("completed_day").and_then(Value::as_i64),
        missed_days: i64_list(obj.get("missed_days")),
        pinned: obj.get("pinned").and_then(Value::as_bool).unwrap_or(false),
        rest,
    })
}

fn put_str(map: &mut Map<String, Value>, key: &str, value: &Option<String>) {
    if let Some(value) = value {
        map.insert(key.into(), Value::String(value.clone()));
    }
}

pub fn block_to_value(block: &TimeBlock) -> Value {
    let mut map = block.rest.clone();
    map.insert("id".into(), Value::String(block.id.clone()));
    map.insert("title".into(), Value::String(block.title.clone()));
    map.insert("kind".into(), Value::String(block.kind.clone()));
    map.insert("duration_min".into(), Value::from(block.duration_min));
    map.insert(
        "days".into(),
        Value::Array(block.days.iter().copied().map(Value::from).collect()),
    );
    map.insert("priority".into(), Value::from(block.priority));
    map.insert("energy".into(), Value::String(block.energy.clone()));
    put_str(&mut map, "earliest", &block.earliest);
    put_str(&mut map, "latest", &block.latest);
    put_str(&mut map, "start", &block.start);
    put_str(&mut map, "course", &block.course);
    if block.completed {
        map.insert("completed".into(), Value::Bool(true));
    }
    if let Some(day) = block.completed_day {
        map.insert("completed_day".into(), Value::from(day));
    }
    if !block.missed_days.is_empty() {
        map.insert(
            "missed_days".into(),
            Value::Array(block.missed_days.iter().copied().map(Value::from).collect()),
        );
    }
    if block.pinned {
        map.insert("pinned".into(), Value::Bool(true));
    }
    Value::Object(map)
}

pub fn work_window_from_value(value: &Value) -> WorkWindow {
    WorkWindow {
        days: i64_list(value.get("days")),
        start: value
            .get("start")
            .and_then(Value::as_str)
            .unwrap_or("00:00")
            .into(),
        end: value
            .get("end")
            .and_then(Value::as_str)
            .unwrap_or("24:00")
            .into(),
        subject: opt_string(value.get("subject")),
    }
}

pub fn study_window_from_value(value: &Value) -> StudyWindow {
    StudyWindow {
        days: i64_list(value.get("days")),
        start: value
            .get("start")
            .and_then(Value::as_str)
            .unwrap_or("00:00")
            .into(),
        duration_min: i64_field(value, "duration_min", 0),
        subject: opt_string(value.get("subject")),
    }
}

fn window_to_value(window: &WorkWindow) -> Value {
    let mut map = Map::new();
    map.insert(
        "days".into(),
        Value::Array(window.days.iter().copied().map(Value::from).collect()),
    );
    map.insert("start".into(), Value::String(window.start.clone()));
    map.insert("end".into(), Value::String(window.end.clone()));
    if let Some(subject) = &window.subject {
        map.insert("subject".into(), Value::String(subject.clone()));
    }
    Value::Object(map)
}

fn point_of(value: &Value) -> Option<(i64, i64)> {
    let pair = value.as_array()?;
    Some((pair.first()?.as_i64()?, pair.get(1)?.as_i64()?))
}

pub fn overrides_from(deadlines: Option<&Value>, slack: Option<&Value>) -> DeadlineOverrides {
    let mut out = DeadlineOverrides::default();
    if let Some(map) = deadlines.and_then(Value::as_object) {
        for (key, value) in map {
            out.deadlines.push((key.clone(), point_of(value)));
        }
    }
    if let Some(map) = slack.and_then(Value::as_object) {
        for (key, value) in map {
            if let Some(point) = point_of(value) {
                out.slack_deadlines.push((key.clone(), point));
            }
        }
    }
    out
}

pub fn trace_to_value(trace: &SolveTrace) -> Value {
    let moves: Vec<Value> = trace
        .moves
        .iter()
        .map(|item| {
            serde_json::json!({
                "block_id": item.block_id,
                "reason": item.reason,
                "from_day": item.from_day,
                "from_start": item.from_start,
                "to_day": item.to_day,
                "to_start": item.to_start,
            })
        })
        .collect();
    let explanations: Vec<Value> = trace
        .explanations
        .iter()
        .map(|item| {
            serde_json::json!({
                "block_id": item.block_id,
                "message": item.message,
                "reason": item.reason,
                "slack_min": item.slack_min,
                "slack_status": item.slack_status,
            })
        })
        .collect();
    serde_json::json!({
        "placed": trace.placed.iter().map(block_to_value).collect::<Vec<_>>(),
        "unplaced": trace.unplaced.iter().map(block_to_value).collect::<Vec<_>>(),
        "moves": moves,
        "explanations": explanations,
        "failed_constraints": trace.failed_constraints,
        "solve_ms": trace.solve_ms,
        "complete": trace.complete,
        "work_windows": trace.work_windows.iter().map(window_to_value).collect::<Vec<_>>(),
        "work_windows_defaulted": trace.work_windows_defaulted,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn legacy_work_windows() -> Vec<WorkWindow> {
        vec![WorkWindow {
            days: vec![0, 1, 2, 3, 4, 5, 6],
            start: "06:00".into(),
            end: "23:00".into(),
            subject: None,
        }]
    }

    fn locked(id: &str, title: &str, start: &str, duration_min: i64, days: &[i64]) -> TimeBlock {
        TimeBlock {
            id: id.into(),
            title: title.into(),
            kind: "locked".into(),
            duration_min,
            days: days.to_vec(),
            start: Some(start.into()),
            priority: 1,
            energy: "medium".into(),
            ..Default::default()
        }
    }

    fn flex(id: &str, title: &str, duration_min: i64, days: &[i64], energy: &str) -> TimeBlock {
        TimeBlock {
            id: id.into(),
            title: title.into(),
            kind: "flexible".into(),
            duration_min,
            days: days.to_vec(),
            energy: energy.into(),
            ..Default::default()
        }
    }

    fn noop_elapsed() -> impl Fn() -> f64 {
        || 0.0
    }

    #[test]
    fn t1_only_locked_is_identity() {
        let school = locked("school", "School", "08:00", 390, &[0, 1, 2, 3, 4]);
        let trace = solve(
            &[school],
            None,
            None,
            Some(&legacy_work_windows()),
            None,
            SOLVE_BUDGET_MS,
            &noop_elapsed(),
        )
        .unwrap();
        assert!(trace.complete);
        assert!(trace.moves.is_empty());
        assert_eq!(trace.placed.len(), 1);
        assert_eq!(trace.placed[0].id, "school");
        assert_eq!(trace.placed[0].start.as_deref(), Some("08:00"));
        assert!(trace.unplaced.is_empty());
    }

    #[test]
    fn t2_one_homework_with_room_is_placed() {
        let school = locked("school", "School", "08:00", 390, &[0]);
        let hw = flex("hw", "Math homework", 60, &[0], "high");
        let trace = solve(
            &[school, hw],
            None,
            None,
            Some(&legacy_work_windows()),
            None,
            SOLVE_BUDGET_MS,
            &noop_elapsed(),
        )
        .unwrap();
        let hw_placed = trace.placed.iter().find(|b| b.id == "hw").unwrap();
        assert!(hw_placed.start.is_some());
        assert!(trace.unplaced.is_empty());
        assert!(trace.complete);
        let start = hhmm_to_minutes(hw_placed.start.as_ref().unwrap()).unwrap();
        assert!((6 * 60..8 * 60).contains(&start));
        assert_eq!(hw_placed.start.as_deref(), Some("06:00"));
    }
}
