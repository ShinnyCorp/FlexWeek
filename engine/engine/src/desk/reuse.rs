//! Planning and clipboard helpers from `desktop/native/reuse.py`.

use chrono::{Datelike, Duration, NaiveDate};
use serde_json::{Value, json};

use crate::desk::pydate::from_iso;
use crate::desk::pyval::{subscript, type_error};
use crate::error::{EngineError, EngineResult};
use crate::stored::{truthy, type_name};

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

pub fn intervals_overlap(start_a: i64, end_a: i64, start_b: i64, end_b: i64) -> bool {
    start_a < end_b && start_b < end_a
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

/// Where you are, in words. The session's own `selected_day` and `selected_month` come in as
/// they were read; `today` gives the caller's local date and is asked only for My Day.
pub fn planner_title(
    week_start: &str,
    session_day: Option<&str>,
    session_month: Option<&str>,
    view: &str,
    short: bool,
    selected_day: Option<&str>,
    today: &mut dyn FnMut() -> EngineResult<String>,
) -> EngineResult<String> {
    let name = |names: &[&str], index: usize, short: bool| -> String {
        if short {
            names[index].chars().take(3).collect()
        } else {
            names[index].to_string()
        }
    };
    fn given(value: Option<&str>) -> Option<&str> {
        value.filter(|text| !text.is_empty())
    }
    let start = from_iso(week_start)?;
    let chosen_iso = given(selected_day)
        .or(given(session_day))
        .unwrap_or(week_start);
    let chosen = from_iso(chosen_iso).unwrap_or(start);
    if view == "month" {
        let anchor_iso = given(session_month).unwrap_or(chosen_iso);
        let anchor = if anchor_iso.chars().count() == 7 {
            from_iso(&format!("{anchor_iso}-01"))
        } else {
            from_iso(anchor_iso)
        }
        .unwrap_or(chosen);
        return Ok(format!(
            "{} {}",
            name(&MONTHS, anchor.month0() as usize, short),
            anchor.year()
        ));
    }
    let mut chosen = chosen;
    if view == "myday" && selected_day.is_none() {
        chosen = from_iso(&today()?)?;
    }
    if view == "day" || view == "myday" {
        return Ok(format!(
            "{} {} {}",
            name(
                &DAYS_LONG,
                chosen.weekday().num_days_from_monday() as usize,
                short
            ),
            chosen.day(),
            name(&MONTHS, chosen.month0() as usize, short)
        ));
    }
    let end = crate::stored::add_days(start, 6)?;
    Ok(if start.month() == end.month() {
        format!(
            "{} – {} {}",
            start.day(),
            end.day(),
            name(&MONTHS, start.month0() as usize, true)
        )
    } else {
        format!(
            "{} {} – {} {}",
            start.day(),
            name(&MONTHS, start.month0() as usize, true),
            end.day(),
            name(&MONTHS, end.month0() as usize, true)
        )
    })
}

/// `copy[key] = value` on a value that is not a dict.
fn item_assignment(value: &Value) -> EngineError {
    match value {
        Value::Array(_) => type_error("list indices must be integers or slices, not str"),
        other => type_error(format!(
            "'{}' object does not support item assignment",
            type_name(other)
        )),
    }
}

/// `copied_fixed_block` with the days and the id as the caller holds them.
pub fn copied_fixed_block_of(
    source: &Value,
    days: Vec<Value>,
    block_id: &Value,
) -> EngineResult<Value> {
    let Value::Object(source) = source else {
        return Err(item_assignment(source));
    };
    let mut copy = source.clone();
    copy.insert("id".into(), block_id.clone());
    copy.insert("kind".into(), json!("locked"));
    copy.insert("days".into(), Value::Array(days));
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
        copy.shift_remove(key);
    }
    Ok(Value::Object(copy))
}

/// `copied_fixed_block(source, days, block_id)` with the days as the caller held them: the copy is
/// made first, so a source that cannot be changed is refused before `list(days)` is read.
pub fn copied_fixed_block_listing(
    source: &Value,
    days: &Value,
    block_id: &Value,
) -> EngineResult<Value> {
    if !matches!(source, Value::Object(_)) {
        return Err(item_assignment(source));
    }
    copied_fixed_block_of(source, crate::desk::pyval::list_of(days)?, block_id)
}

pub fn copied_fixed_block(source: &Value, days: &[i64], block_id: &str) -> EngineResult<Value> {
    copied_fixed_block_of(
        source,
        days.iter().map(|day| json!(day)).collect(),
        &json!(block_id),
    )
}

pub fn copied_homework_block_of(
    assignment: &Value,
    day: i64,
    duration: &Value,
    block_id: &Value,
) -> EngineResult<Value> {
    let or = |name: &str, fallback: Value| match assignment.get(name) {
        Some(value) if truthy(Some(value)) => value.clone(),
        _ => fallback,
    };
    let field = |name: &str| assignment.get(name).cloned().unwrap_or(Value::Null);
    let title = subscript(assignment, "title")?.clone();
    let priority = or("priority", json!(3));
    let energy = or("energy", json!("medium"));
    Ok(json!({
        "id": block_id,
        "kind": "flexible",
        "title": title,
        "duration_min": duration,
        "days": [day],
        "start": Value::Null,
        "earliest": Value::Null,
        "latest": Value::Null,
        "priority": priority,
        "energy": energy,
        "course": field("course"),
        "category": field("category"),
        "spotify_url": field("spotify_url"),
        "completed": false,
        "completed_day": Value::Null,
        "missed_days": [],
        "assignment_id": subscript(assignment, "id")?,
    }))
}

pub fn copied_homework_block(
    assignment: &Value,
    day: i64,
    duration: i64,
    block_id: &str,
) -> EngineResult<Value> {
    copied_homework_block_of(assignment, day, &json!(duration), &json!(block_id))
}

pub fn clipboard_item(block: &Value, source_day: i64, scope: &str, group_id: &str) -> Value {
    json!({
        "block": block,
        "source_day": source_day,
        "scope": scope,
        "group_id": group_id,
    })
}
