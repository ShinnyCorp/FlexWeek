//! Planning and clipboard helpers from `desktop/native/reuse.py`.

use chrono::{Datelike, Duration, NaiveDate};
use serde_json::{Map, Value, json};

use crate::desk::calendar::{DAY_FULL, parse_due};
use crate::desk::weekmodel::clock_text;
use crate::time::{DAY_END_MIN, DAY_START_MIN, SLOT_MIN, hhmm_to_minutes, minutes_to_hhmm};

pub const MAX_WEEK_BLOCKS: i64 = 100;
pub const AVAILABILITY_LIMIT: i64 = 21;

pub fn restore_point_label(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    if chars.len() <= 80 {
        return text.to_string();
    }
    format!("{}…", chars.iter().take(79).collect::<String>())
}

pub fn week_label(week_start: &str) -> String {
    format!("Week of {week_start}")
}

pub fn floor_slot(minutes: i64) -> i64 {
    (minutes.max(0) / SLOT_MIN) * SLOT_MIN
}

pub fn is_homework_session(block: &Value) -> bool {
    block.get("assignment_id").is_some()
}

pub fn session_days(week_start: &str, due: &str) -> Vec<i64> {
    let monday = NaiveDate::parse_from_str(week_start, "%Y-%m-%d").expect("week");
    let due_day = NaiveDate::parse_from_str(&due[..10], "%Y-%m-%d").expect("due");
    let last = monday + Duration::days(6);
    if due_day < monday {
        return vec![0];
    }
    if due_day > last {
        return vec![0, 1, 2, 3, 4];
    }
    (0..=due_day.weekday().num_days_from_monday() as i64).collect()
}

pub fn is_planned(block: &Value) -> bool {
    block.get("kind").and_then(Value::as_str) == Some("flexible")
        && block.get("start").is_some()
        && block.get("completed").and_then(Value::as_bool) != Some(true)
        && block.get("days").and_then(Value::as_array).map(|d| d.len()) == Some(1)
}

pub fn planning_days(
    block: &Value,
    assignments: &Map<String, Value>,
    week_start: &str,
) -> Vec<i64> {
    if let Some(id) = block.get("assignment_id").and_then(Value::as_str)
        && let Some(assignment) = assignments.get(id)
        && let Some(due) = assignment.get("due").and_then(Value::as_str)
    {
        return session_days(week_start, due);
    }
    block
        .get("days")
        .and_then(Value::as_array)
        .map(|d| d.iter().filter_map(Value::as_i64).collect())
        .unwrap_or_else(|| vec![0])
}

pub fn apply_plan(
    blocks: &[Value],
    trace: Option<&Value>,
    targets: Option<&std::collections::HashSet<String>>,
    assignments: Option<&Map<String, Value>>,
    week_start: Option<&str>,
) -> Vec<Value> {
    let placed: std::collections::HashMap<String, Value> = trace
        .and_then(|t| t.get("placed"))
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| Some((item.get("id")?.as_str()?.to_string(), item.clone())))
                .collect()
        })
        .unwrap_or_default();
    let unplaced_ids: std::collections::HashSet<String> = trace
        .and_then(|t| t.get("unplaced"))
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.get("id").and_then(Value::as_str).map(str::to_string))
                .collect()
        })
        .unwrap_or_default();
    let mut out = Vec::new();
    for block in blocks {
        let mut copy = block.as_object().cloned().unwrap_or_default();
        let unplanned_work = copy.get("kind").and_then(Value::as_str) == Some("flexible")
            && copy.get("completed").and_then(Value::as_bool) != Some(true);
        let id = copy.get("id").and_then(Value::as_str).unwrap_or("");
        if !unplanned_work || targets.is_some_and(|t| !t.contains(id)) {
            out.push(Value::Object(copy));
            continue;
        }
        if let Some(winner) = placed.get(id) {
            if winner.get("start").is_some() {
                copy.insert(
                    "start".into(),
                    winner.get("start").cloned().unwrap_or(Value::Null),
                );
                if let Some(days) = winner.get("days").and_then(Value::as_array) {
                    copy.insert("days".into(), Value::Array(days.clone()));
                }
            }
        } else if unplaced_ids.contains(id) {
            copy.remove("pinned");
            if copy.remove("start").is_some()
                && let (Some(assignments), Some(week_start)) = (assignments, week_start)
            {
                copy.insert(
                    "days".into(),
                    json!(planning_days(
                        &Value::Object(copy.clone()),
                        assignments,
                        week_start
                    )),
                );
            }
        }
        out.push(Value::Object(copy));
    }
    out
}

pub fn clear_stale_pins(blocks: &[Value]) -> Vec<Value> {
    blocks
        .iter()
        .map(|block| {
            let mut copy = block.as_object().cloned().unwrap_or_default();
            if copy.get("pinned").and_then(Value::as_bool) == Some(true)
                && !(copy.get("start").is_some()
                    && copy.get("days").and_then(Value::as_array).map(|d| d.len()) == Some(1))
            {
                copy.remove("pinned");
            }
            Value::Object(copy)
        })
        .collect()
}

pub fn held_in_place(block: &Value) -> Value {
    json!({
        "id": block.get("id"),
        "title": block.get("title").cloned().unwrap_or(json!("Homework")),
        "kind": "locked",
        "duration_min": block.get("duration_min"),
        "days": block.get("days"),
        "start": block.get("start"),
    })
}

pub fn plan_start(
    week_start: &str,
    now_iso: &str,
    now_minute: i64,
    now_has_subminute: bool,
) -> Option<(i64, i64)> {
    let week = NaiveDate::parse_from_str(week_start, "%Y-%m-%d").ok()?;
    let today = NaiveDate::parse_from_str(now_iso, "%Y-%m-%d").ok()?;
    let day = (today - week).num_days();
    if day < 0 {
        return None;
    }
    let mut minute = now_minute + if now_has_subminute { 1 } else { 0 };
    minute = (-(-minute / SLOT_MIN)) * SLOT_MIN;
    if minute >= DAY_END_MIN {
        return Some((day + 1, DAY_START_MIN));
    }
    Some((day, minute))
}

pub fn occurrence_days(block: &Value) -> Vec<i64> {
    if block.get("kind").and_then(Value::as_str) == Some("flexible")
        && block.get("completed").and_then(Value::as_bool) == Some(true)
    {
        if let Some(day) = block.get("completed_day").and_then(Value::as_i64) {
            return vec![day];
        }
        if block
            .get("days")
            .and_then(Value::as_array)
            .map(|d| d.len())
            .unwrap_or(0)
            > 1
        {
            return Vec::new();
        }
    }
    block
        .get("days")
        .and_then(Value::as_array)
        .map(|d| d.iter().filter_map(Value::as_i64).collect())
        .unwrap_or_default()
}

pub fn session_minutes(blocks: &[Value], assignment_id: &str) -> i64 {
    blocks
        .iter()
        .filter(|b| {
            b.get("assignment_id").and_then(Value::as_str) == Some(assignment_id)
                && b.get("completed").and_then(Value::as_bool) != Some(true)
        })
        .map(|b| b.get("duration_min").and_then(Value::as_i64).unwrap_or(0))
        .sum()
}

pub fn available_homework_minutes(
    assignment: Option<&Value>,
    blocks: &[Value],
    committed_blocks: Option<&[Value]>,
) -> i64 {
    let Some(assignment) = assignment else {
        return 0;
    };
    if assignment.get("completed").and_then(Value::as_bool) == Some(true) {
        return 0;
    }
    let id = assignment.get("id").and_then(Value::as_str).unwrap_or("");
    let here = session_minutes(blocks, id);
    let committed = session_minutes(committed_blocks.unwrap_or(&[]), id);
    if assignment.get("unplanned_min").is_none() {
        let remaining = (assignment
            .get("estimate_min")
            .and_then(Value::as_i64)
            .unwrap_or(0)
            - assignment
                .get("focus_minutes")
                .and_then(Value::as_i64)
                .unwrap_or(0))
        .max(0);
        return floor_slot(remaining - here);
    }
    floor_slot(
        assignment
            .get("unplanned_min")
            .and_then(Value::as_i64)
            .unwrap_or(0)
            + committed
            - here,
    )
}

pub fn capacity_problem(existing_count: i64, added_count: i64, label: &str) -> String {
    if existing_count + added_count > MAX_WEEK_BLOCKS {
        return format!(
            "{label} would exceed 100 blocks. Uncheck an item or remove a block first."
        );
    }
    String::new()
}

pub fn intervals_overlap(start_a: i64, end_a: i64, start_b: i64, end_b: i64) -> bool {
    start_a < end_b && start_b < end_a
}

pub fn late_from_start(minute: i64) -> String {
    let mut snapped = (minute / SLOT_MIN) * SLOT_MIN;
    snapped = snapped.clamp(DAY_START_MIN, DAY_END_MIN - SLOT_MIN);
    minutes_to_hhmm(snapped)
}

pub fn running_late_block(day: i64, from_start: &str, minutes: i64, block_id: &str) -> Value {
    let start = hhmm_to_minutes(from_start).unwrap_or(0);
    let duration = minutes.min(DAY_END_MIN - start);
    json!({
        "id": block_id,
        "kind": "locked",
        "title": "Running late",
        "duration_min": duration,
        "days": [day],
        "start": from_start,
        "priority": 1,
        "energy": "medium",
        "category": "downtime",
        "completed": false,
        "missed_days": [],
    })
}

pub fn running_late_refusal(
    week_start: &str,
    today_iso: &str,
    dirty: bool,
    conflict: bool,
    block_count: i64,
) -> Option<&'static str> {
    let today = NaiveDate::parse_from_str(today_iso, "%Y-%m-%d").ok()?;
    let this_week = today - Duration::days(i64::from(today.weekday().num_days_from_monday()));
    if week_start
        != format!(
            "{:04}-{:02}-{:02}",
            this_week.year(),
            this_week.month(),
            this_week.day()
        )
    {
        return Some("Open this week before using Running late.");
    }
    if conflict {
        return Some("This week was changed somewhere else. Reload it first.");
    }
    if dirty {
        return Some("Your last change is still saving. Try again in a moment.");
    }
    if block_count >= MAX_WEEK_BLOCKS {
        return Some("This week already has 100 blocks. Remove one before recording a late start.");
    }
    None
}

pub fn late_locked_line(block: &Value, moved: i64) -> String {
    let start = hhmm_to_minutes(
        block
            .get("start")
            .and_then(Value::as_str)
            .unwrap_or("00:00"),
    )
    .unwrap_or(0);
    let end = start
        + block
            .get("duration_min")
            .and_then(Value::as_i64)
            .unwrap_or(0);
    let extra = if moved == 0 {
        "Nothing had to move.".to_string()
    } else {
        format!("{moved} moved.")
    };
    format!(
        "Running late: {}–{} is now locked. {extra}",
        clock_text(start),
        clock_text(end)
    )
}

pub fn late_id(operation_id: &str) -> String {
    format!(
        "b-late-{}",
        operation_id
            .replace('-', "")
            .chars()
            .take(24)
            .collect::<String>()
    )
}

pub fn copy_label(block: &Value, source_day: i64, scope: &str) -> String {
    let title = block.get("title").and_then(Value::as_str).unwrap_or("");
    let series = block.get("kind").and_then(Value::as_str) == Some("locked")
        && block
            .get("days")
            .and_then(Value::as_array)
            .map(|d| d.len())
            .unwrap_or(0)
            > 1;
    if scope == "series" {
        return format!("{title} (all days)");
    }
    if series {
        return format!("{title} ({})", DAY_FULL[source_day as usize]);
    }
    title.to_string()
}

const DAYS_LONG: [&str; 7] = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
];

const MONTHS: [&str; 12] = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
];

pub struct PlannerSession<'a> {
    pub week_start: &'a str,
    pub now_ms: i64,
    pub selected_day: Option<&'a str>,
    pub selected_month: Option<&'a str>,
}

pub fn planner_title(
    session: &PlannerSession<'_>,
    view: &str,
    short: bool,
    selected_day: Option<&str>,
) -> String {
    fn name(names: &[&str], index: usize, short: bool) -> String {
        if short {
            names[index][..3.min(names[index].len())].to_string()
        } else {
            names[index].to_string()
        }
    }
    let start = NaiveDate::parse_from_str(session.week_start, "%Y-%m-%d").expect("week");
    let chosen_iso = selected_day
        .or(session.selected_day)
        .unwrap_or(session.week_start);
    let chosen = NaiveDate::parse_from_str(chosen_iso, "%Y-%m-%d").unwrap_or(start);
    if view == "month" {
        let anchor_iso = session.selected_month.unwrap_or(chosen_iso);
        let anchor = if anchor_iso.len() == 7 {
            NaiveDate::parse_from_str(&format!("{anchor_iso}-01"), "%Y-%m-%d").unwrap_or(chosen)
        } else {
            NaiveDate::parse_from_str(anchor_iso, "%Y-%m-%d").unwrap_or(chosen)
        };
        return format!(
            "{} {}",
            name(&MONTHS, anchor.month() as usize - 1, short),
            anchor.year()
        );
    }
    let mut chosen = chosen;
    if view == "myday" && selected_day.is_none() {
        let secs = session.now_ms / 1000;
        chosen = chrono::DateTime::from_timestamp(secs, 0)
            .expect("now")
            .naive_local()
            .date();
    }
    if view == "day" || view == "myday" {
        return format!(
            "{} {} {}",
            name(
                &DAYS_LONG,
                chosen.weekday().num_days_from_monday() as usize,
                short
            ),
            chosen.day(),
            name(&MONTHS, chosen.month() as usize - 1, short)
        );
    }
    let short = true;
    let end = start + Duration::days(6);
    if start.month() == end.month() {
        format!(
            "{} – {} {}",
            start.day(),
            end.day(),
            name(&MONTHS, start.month() as usize - 1, short)
        )
    } else {
        format!(
            "{} {} – {} {}",
            start.day(),
            name(&MONTHS, start.month() as usize - 1, short),
            end.day(),
            name(&MONTHS, end.month() as usize - 1, short)
        )
    }
}

pub fn due_point(due: Option<&str>, week_start: &str) -> Option<(i64, i64)> {
    let due = due?;
    let (due_day, minutes) = parse_due(due).ok()?;
    let week = NaiveDate::parse_from_str(week_start, "%Y-%m-%d").ok()?;
    let offset = (due_day - week).num_days();
    if offset > 6 {
        return None;
    }
    Some((offset, minutes))
}

fn object(value: &Value) -> Map<String, Value> {
    value.as_object().cloned().unwrap_or_default()
}

fn i64_of(value: &Value, key: &str) -> i64 {
    value.get(key).and_then(Value::as_i64).unwrap_or(0)
}

pub fn copied_fixed_block(source: &Value, days: &[i64], block_id: &str) -> Value {
    let mut copy = object(source);
    copy.insert("id".into(), json!(block_id));
    copy.insert("kind".into(), json!("locked"));
    copy.insert("days".into(), json!(days));
    copy.insert("completed".into(), json!(false));
    copy.insert("completed_day".into(), Value::Null);
    copy.insert("missed_days".into(), json!([]));
    copy.insert("focus_minutes".into(), json!(0));
    copy.insert("focus_sessions".into(), json!(0));
    for key in [
        "assignment_id",
        "pomodoro_parent_id",
        "pomodoro_role",
        "pomodoro_index",
        "template_id",
    ] {
        copy.remove(key);
    }
    Value::Object(copy)
}

pub fn copied_homework_block(assignment: &Value, day: i64, duration: i64, block_id: &str) -> Value {
    json!({
        "id": block_id,
        "kind": "flexible",
        "title": assignment.get("title").cloned().unwrap_or(Value::Null),
        "duration_min": duration,
        "days": [day],
        "start": Value::Null,
        "earliest": Value::Null,
        "latest": Value::Null,
        "priority": assignment.get("priority").cloned().unwrap_or(json!(3)),
        "energy": assignment.get("energy").cloned().unwrap_or(json!("medium")),
        "course": assignment.get("course").cloned().unwrap_or(Value::Null),
        "category": assignment.get("category").cloned().unwrap_or(Value::Null),
        "spotify_url": assignment.get("spotify_url").cloned().unwrap_or(Value::Null),
        "completed": false,
        "completed_day": Value::Null,
        "missed_days": [],
        "assignment_id": assignment.get("id").cloned().unwrap_or(Value::Null),
    })
}

pub fn clipboard_item(block: &Value, source_day: i64, scope: &str, group_id: &str) -> Value {
    json!({
        "block": block,
        "source_day": source_day,
        "scope": scope,
        "group_id": group_id,
    })
}

pub fn clipboard_fingerprint(items: &[Value]) -> String {
    let payload: Vec<Value> = items
        .iter()
        .map(|item| {
            json!({
                "block": item.get("block").cloned().unwrap_or(Value::Null),
                "source_day": item.get("source_day").cloned().unwrap_or(Value::Null),
                "scope": item.get("scope").cloned().unwrap_or(Value::Null),
            })
        })
        .collect();
    crate::snapshot::canonical(&Value::Array(payload))
}

pub fn block_occurs_on_day(block: &Value, day: i64, placed: Option<&[Value]>) -> bool {
    let flexible =
        is_homework_session(block) || block.get("kind").and_then(Value::as_str) == Some("flexible");
    if flexible {
        let mut source = if block.get("start").is_some() {
            Some(block.clone())
        } else {
            None
        };
        if source.is_none()
            && let Some(placed) = placed
        {
            source = placed
                .iter()
                .find(|item| {
                    item.get("id") == block.get("id") && occurrence_days(item).contains(&day)
                })
                .cloned();
        }
        return source.is_some_and(|item| {
            item.get("start").is_some() && occurrence_days(&item).contains(&day)
        });
    }
    occurrence_days(block).contains(&day)
}

pub fn row_conflict(row: &Value, rows: &[Value], existing: &[Value]) -> Option<String> {
    if row.get("fixed").and_then(Value::as_bool) != Some(true) {
        return None;
    }
    let block = row.get("block")?;
    block.get("start")?;
    let start =
        hhmm_to_minutes(block.get("start").and_then(Value::as_str).unwrap_or("")).unwrap_or(0);
    let end = start + i64_of(block, "duration_min");
    let day = i64_of(row, "day");
    for other in existing {
        if other.get("start").is_none() || !occurrence_days(other).contains(&day) {
            continue;
        }
        let other_start =
            hhmm_to_minutes(other.get("start").and_then(Value::as_str).unwrap_or("")).unwrap_or(0);
        if start < other_start + i64_of(other, "duration_min") && other_start < end {
            return other
                .get("title")
                .and_then(Value::as_str)
                .map(str::to_string);
        }
    }
    for candidate in rows {
        if std::ptr::eq(candidate, row) {
            continue;
        }
        if candidate.get("checked").and_then(Value::as_bool) != Some(true)
            || candidate.get("fixed").and_then(Value::as_bool) != Some(true)
            || i64_of(candidate, "day") != day
            || candidate.get("week_start") != row.get("week_start")
        {
            continue;
        }
        let candidate_block = candidate.get("block").cloned().unwrap_or(Value::Null);
        if candidate_block.get("start").is_none() {
            continue;
        }
        let other_start = hhmm_to_minutes(
            candidate_block
                .get("start")
                .and_then(Value::as_str)
                .unwrap_or(""),
        )
        .unwrap_or(0);
        if start < other_start + i64_of(&candidate_block, "duration_min") && other_start < end {
            return candidate_block
                .get("title")
                .and_then(Value::as_str)
                .map(str::to_string);
        }
    }
    None
}

fn begun(block: &Value, not_before: Option<(i64, i64)>) -> bool {
    let Some((day, minute)) = not_before else {
        return false;
    };
    let Some(start) = block.get("start").and_then(Value::as_str) else {
        return false;
    };
    let block_day = block
        .get("days")
        .and_then(Value::as_array)
        .and_then(|days| days.first())
        .and_then(Value::as_i64)
        .unwrap_or(0);
    let start_min = hhmm_to_minutes(start).unwrap_or(0);
    (block_day, start_min) < (day, minute)
}

pub fn solve_request(
    blocks: &[Value],
    assignments: &Map<String, Value>,
    week_start: &str,
    everything: bool,
    only: Option<&[String]>,
    not_before: Option<(i64, i64)>,
) -> (Vec<Value>, Vec<String>) {
    let mut payload = Vec::new();
    let mut targets = Vec::new();
    for block in blocks {
        if block.get("kind").and_then(Value::as_str) != Some("flexible")
            || block.get("completed").and_then(Value::as_bool) == Some(true)
        {
            payload.push(block.clone());
            continue;
        }
        let planned = is_planned(block);
        let kept = planned
            && (block.get("pinned").and_then(Value::as_bool) == Some(true)
                || begun(block, not_before));
        let id = block
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let wanted = if let Some(only) = only {
            only.iter().any(|item| item == &id)
        } else {
            (everything && !kept) || !planned
        };
        if wanted {
            let mut session = object(block);
            if planned {
                session.remove("start");
                session.insert(
                    "days".into(),
                    json!(planning_days(
                        &Value::Object(session.clone()),
                        assignments,
                        week_start
                    )),
                );
            }
            let session = if let Some(bound) = not_before {
                let day = bound.0;
                let days: Vec<i64> = session
                    .get("days")
                    .and_then(Value::as_array)
                    .map(|items| {
                        items
                            .iter()
                            .filter_map(Value::as_i64)
                            .filter(|item| *item >= day)
                            .collect()
                    })
                    .unwrap_or_default();
                let days = if days.is_empty() { vec![day] } else { days };
                session.insert("days".into(), json!(days));
                session.insert(
                    "earliest".into(),
                    json!(format!(
                        "{} {}",
                        DAY_FULL[day as usize],
                        minutes_to_hhmm(bound.1)
                    )),
                );
                session
            } else {
                session
            };
            targets.push(id);
            payload.push(Value::Object(session));
        } else if planned {
            payload.push(held_in_place(block));
        }
    }
    (payload, targets)
}

pub fn settle_placements(
    blocks: &[Value],
    assignments: &Map<String, Value>,
    week_start: &str,
    keep: &[String],
) -> (Vec<Value>, Vec<Value>) {
    let mut taken: Vec<Vec<(i64, i64, String)>> = vec![Vec::new(); 7];
    for block in blocks {
        if block.get("start").is_none() {
            continue;
        }
        let start =
            hhmm_to_minutes(block.get("start").and_then(Value::as_str).unwrap_or("")).unwrap_or(0);
        let end = start + i64_of(block, "duration_min");
        let title = block
            .get("title")
            .and_then(Value::as_str)
            .unwrap_or(
                if block.get("kind").and_then(Value::as_str) == Some("locked") {
                    "a fixed block"
                } else {
                    "finished work"
                },
            )
            .to_string();
        if block.get("kind").and_then(Value::as_str) == Some("locked") {
            let missed = block
                .get("missed_days")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            for day in occurrence_days(block) {
                if !missed.iter().any(|item| item.as_i64() == Some(day))
                    && let Some(slot) = taken.get_mut(day as usize)
                {
                    slot.push((start, end, title.clone()));
                }
            }
        } else if block.get("completed").and_then(Value::as_bool) == Some(true) {
            let days = occurrence_days(block);
            let day = block
                .get("completed_day")
                .and_then(Value::as_i64)
                .or_else(|| if days.len() == 1 { Some(days[0]) } else { None });
            if let Some(day) = day
                && let Some(slot) = taken.get_mut(day as usize)
            {
                slot.push((start, end, title));
            }
        }
    }
    let mut sessions: Vec<&Value> = blocks.iter().filter(|block| is_planned(block)).collect();
    sessions.sort_by_key(|block| {
        let id = block.get("id").and_then(Value::as_str).unwrap_or("");
        let day = block
            .get("days")
            .and_then(Value::as_array)
            .and_then(|d| d.first())
            .and_then(Value::as_i64)
            .unwrap_or(0);
        let start = block.get("start").and_then(Value::as_str).unwrap_or("");
        (
            !keep.iter().any(|item| item == id),
            day,
            start.to_string(),
            id.to_string(),
        )
    });
    let mut lost: Vec<(String, Value)> = Vec::new();
    for block in &sessions {
        let day = block
            .get("days")
            .and_then(Value::as_array)
            .and_then(|d| d.first())
            .and_then(Value::as_i64)
            .unwrap_or(0);
        let start =
            hhmm_to_minutes(block.get("start").and_then(Value::as_str).unwrap_or("")).unwrap_or(0);
        let end = start + i64_of(block, "duration_min");
        let assignment_id = block
            .get("assignment_id")
            .and_then(Value::as_str)
            .unwrap_or("");
        let assignment = assignments.get(assignment_id);
        let due = assignment
            .and_then(|item| item.get("due").and_then(Value::as_str))
            .and_then(|due| due_point(Some(due), week_start));
        let pinned = block.get("pinned").and_then(Value::as_bool) == Some(true);
        let clash = if pinned {
            None
        } else {
            taken.get(day as usize).and_then(|slots| {
                slots
                    .iter()
                    .find(|(low, high, _)| start < *high && *low < end)
                    .map(|(_, _, title)| title.clone())
            })
        };
        let why = if start < DAY_START_MIN || end > DAY_END_MIN {
            Some("that is outside the hours FlexWeek plans in".to_string())
        } else if due.is_some_and(|(due_day, due_min)| (day, end) > (due_day, due_min)) {
            Some("that is after it is due".to_string())
        } else {
            clash.map(|clash| format!("{clash} is there now"))
        };
        let Some(why) = why else {
            if !pinned {
                let title = block
                    .get("title")
                    .and_then(Value::as_str)
                    .unwrap_or("homework")
                    .to_string();
                if let Some(slot) = taken.get_mut(day as usize) {
                    slot.push((start, end, title));
                }
            }
            continue;
        };
        let title = block
            .get("title")
            .and_then(Value::as_str)
            .unwrap_or("Homework");
        let id = block
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let start_text = block.get("start").and_then(Value::as_str).unwrap_or("");
        lost.push((
            id.clone(),
            json!({
                "block_id": id,
                "assignment_id": block.get("assignment_id").cloned().unwrap_or(Value::Null),
                "title": title,
                "day": day,
                "start": start_text,
                "message": format!("{title} no longer fits {} at {}: {why}.", DAY_FULL[day as usize], crate::desk::weekmodel::hhmm_text(start_text)),
            }),
        ));
    }
    if lost.is_empty() {
        return (blocks.to_vec(), Vec::new());
    }
    let lost_ids: Vec<String> = lost.iter().map(|(id, _)| id.clone()).collect();
    let mut out = Vec::new();
    for block in blocks {
        let id = block.get("id").and_then(Value::as_str).unwrap_or("");
        if lost_ids.iter().any(|lost_id| lost_id == id) {
            let mut copy = object(block);
            copy.remove("start");
            copy.remove("pinned");
            copy.insert(
                "days".into(),
                json!(planning_days(
                    &Value::Object(copy.clone()),
                    assignments,
                    week_start
                )),
            );
            out.push(Value::Object(copy));
        } else {
            out.push(block.clone());
        }
    }
    let reports: Vec<Value> = sessions
        .iter()
        .filter_map(|block| {
            let id = block.get("id").and_then(Value::as_str).unwrap_or("");
            lost.iter()
                .find(|(lost_id, _)| lost_id == id)
                .map(|(_, report)| report.clone())
        })
        .collect();
    (out, reports)
}
