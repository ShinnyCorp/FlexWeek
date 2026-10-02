//! Reminder due checks from `desktop/native/remind.py`.

use std::collections::{HashMap, HashSet};

use chrono::Datelike;
use serde_json::{Map, Value, json};

use crate::desk::calendar::DAYS;
use crate::desk::pydate::{add_days_text, calendar_date, monday_text};
use crate::desk::reuse::occurrence_days;
use crate::desk::weekmodel::hhmm_text;
use crate::error::{EngineError, EngineResult, ErrorKind};
use crate::stored::{Dict, dict, item, py_int, py_list, py_str, text, truthy, type_name};
use crate::time::{hhmm_to_minutes, py_int as text_int};

pub const REMINDER_WINDOW_MIN: i64 = 2;
pub const REMINDER_POLL_MS: i64 = 30_000;
pub const ALARM_SNOOZE_MIN: i64 = 5;
pub const ALARM_SNOOZE_MS: i64 = ALARM_SNOOZE_MIN * 60_000;

/// `int(prefs["reminder_lead_min"])`, or the default when there are no prefs or the key is None.
pub fn reminder_lead_min(prefs: Option<&Dict>, default: i64) -> EngineResult<i64> {
    match prefs.and_then(|prefs| prefs.get("reminder_lead_min")) {
        Some(value) if !value.is_null() && prefs.is_some_and(|prefs| !prefs.is_empty()) => {
            py_int(value)
        }
        _ => Ok(default),
    }
}

/// The local wall clock the caller read (never converted here), as the reminder poll wants it.
pub fn clock_parts(
    now_ms: i64,
    local: (i32, u32, u32, i64, i64),
    midnight_ms: i64,
) -> EngineResult<Dict> {
    let (year, month, day, hour, minute) = local;
    let date = calendar_date(year, month, day)?;
    let mut out = Map::new();
    out.insert(
        "iso".into(),
        json!(format!("{:04}-{:02}-{:02}", year, month, day)),
    );
    out.insert(
        "day".into(),
        json!(i64::from(date.weekday().num_days_from_monday())),
    );
    out.insert("minute".into(), json!(hour * 60 + minute));
    out.insert("midnight_ms".into(), json!(midnight_ms));
    out.insert("now_ms".into(), json!(now_ms));
    Ok(out)
}

pub fn start_alert_due(start_min: i64, now_min: i64, lead: i64) -> bool {
    let start = start_min;
    let lead = lead.max(0);
    start - lead <= now_min && now_min <= start
}

pub fn song_due(start_min: i64, now_min: i64) -> bool {
    start_min <= now_min && now_min <= start_min + REMINDER_WINDOW_MIN
}

pub fn reminder_key(week_start: &str, block_id: &str, day: i64, start: &str) -> String {
    [week_start, block_id, &day.to_string(), start].join("|")
}

pub fn alarm_key(iso_date: &str, alarm: &Dict) -> String {
    let shown = |name: &str| {
        alarm
            .get(name)
            .filter(|value| truthy(Some(value)))
            .map(py_str)
            .unwrap_or_default()
    };
    [iso_date, &shown("id"), &shown("time")].join("|")
}

/// `item["id"]`, as Python reads a row of any type.
fn type_error(message: impl Into<String>) -> EngineError {
    EngineError {
        kind: ErrorKind::Type,
        message: message.into(),
    }
}

fn row_id(row: &Value) -> EngineResult<&Value> {
    match row {
        Value::Object(map) => item(map, "id"),
        Value::Array(_) => Err(type_error(
            "list indices must be integers or slices, not str",
        )),
        other => Err(type_error(format!(
            "'{}' object is not subscriptable",
            type_name(other)
        ))),
    }
}

pub fn reminder_blocks(blocks: &[Value], trace: Option<&Value>) -> EngineResult<Vec<Value>> {
    let mut sources: HashMap<String, &Value> = HashMap::new();
    for block in blocks {
        sources.insert(row_id(block)?.to_string(), block);
    }
    let Some(trace) = trace.filter(|value| truthy(Some(value))) else {
        return Ok(blocks.to_vec());
    };
    let mut out = Vec::new();
    for block in blocks {
        if dict(block)?.get("kind").and_then(Value::as_str) == Some("locked") {
            out.push(block.clone());
        }
    }
    let trace = dict(trace)?;
    for placed in py_list(trace.get("placed"))? {
        let fields = dict(&placed)?;
        if fields.get("kind").and_then(Value::as_str) != Some("flexible") {
            continue;
        }
        let Some(source) = sources.get(&item(fields, "id")?.to_string()) else {
            out.push(placed.clone());
            continue;
        };
        let source = dict(source)?;
        let mut merged = fields.clone();
        merged.insert(
            "completed".into(),
            source.get("completed").cloned().unwrap_or(Value::Null),
        );
        merged.insert(
            "missed_days".into(),
            Value::Array(py_list(source.get("missed_days"))?),
        );
        let title = match source.get("title") {
            Some(title) if truthy(Some(title)) => title.clone(),
            _ => fields.get("title").cloned().unwrap_or(Value::Null),
        };
        merged.insert("title".into(), title);
        out.push(Value::Object(merged));
    }
    Ok(out)
}

fn day_index(day: i64) -> EngineResult<usize> {
    let shifted = if day < 0 { day + 7 } else { day };
    usize::try_from(shifted)
        .ok()
        .filter(|at| *at < DAYS.len())
        .ok_or_else(|| EngineError::index("tuple index out of range"))
}

/// A reminder key built from a block's id: `"|".join` takes strings only.
fn key_part<'a>(block: &'a Dict, name: &str, position: usize) -> EngineResult<&'a str> {
    match item(block, name)? {
        Value::String(text) => Ok(text),
        other => Err(type_error(format!(
            "sequence item {position}: expected str instance, {} found",
            type_name(other)
        ))),
    }
}

pub fn todays_starts(
    blocks: &[Value],
    trace: Option<&Value>,
    today_iso: &str,
) -> EngineResult<Vec<(Value, i64, i64, String)>> {
    let week_start = monday_text(today_iso)?;
    let mut rows = Vec::new();
    for block in reminder_blocks(blocks, trace)? {
        let fields = dict(&block)?;
        let start = fields.get("start");
        if !truthy(start) || truthy(fields.get("completed")) {
            continue;
        }
        let start = start.unwrap_or(&Value::Null);
        for day in occurrence_days(&block) {
            let missed = match fields.get("missed_days") {
                Some(value) if truthy(Some(value)) => value.as_array().cloned().unwrap_or_default(),
                _ => Vec::new(),
            };
            if missed.iter().any(|value| value.as_i64() == Some(day)) {
                continue;
            }
            if add_days_text(&week_start, day)? != today_iso {
                continue;
            }
            let start = text(start, "split")?;
            let start_min = hhmm_to_minutes(start)?;
            let key = [
                week_start.as_str(),
                key_part(fields, "id", 1)?,
                &day.to_string(),
                start,
            ]
            .join("|");
            rows.push((block.clone(), day, start_min, key));
        }
    }
    Ok(rows)
}

pub fn due_reminders(
    blocks: &[Value],
    trace: Option<&Value>,
    today_iso: &str,
    now_min: i64,
    lead_min: i64,
    fired: &HashSet<String>,
) -> EngineResult<Vec<Value>> {
    let mut due = Vec::new();
    for (block, day, start_min, key) in todays_starts(blocks, trace, today_iso)? {
        if fired.contains(&key) || !start_alert_due(start_min, now_min, lead_min) {
            continue;
        }
        let fields = dict(&block)?;
        let started = now_min >= start_min;
        if started && truthy(fields.get("spotify_url")) {
            continue;
        }
        let title = py_str(item(fields, "title")?);
        let start = text(item(fields, "start")?, "split")?;
        due.push(json!({
            "key": key,
            "title": format!("{title} {}", if started { "starts now" } else { "starts soon" }),
            "body": format!("{} · {}", hhmm_text(start), DAYS[day_index(day)?]),
        }));
    }
    Ok(due)
}

pub fn due_songs(
    blocks: &[Value],
    trace: Option<&Value>,
    today_iso: &str,
    now_min: i64,
    played: &HashSet<String>,
) -> EngineResult<Vec<Value>> {
    let mut due = Vec::new();
    for (block, _day, start_min, key) in todays_starts(blocks, trace, today_iso)? {
        let fields = dict(&block)?;
        let link = fields.get("spotify_url");
        if !truthy(link) || played.contains(&key) || !song_due(start_min, now_min) {
            continue;
        }
        due.push(json!({
            "id": key,
            "name": item(fields, "title")?,
            "time": item(fields, "start")?,
            "days": [],
            "enabled": true,
            "sound": "spotify",
            "spotify_url": link,
            "block": true,
        }));
    }
    Ok(due)
}

/// `hour, minute = (int(part) for part in str(alarm["time"]).split(":"))`: the parts are read one
/// at a time, so a bad third part is reported before the count is.
fn hour_and_minute(time: &str) -> EngineResult<(i64, i64)> {
    let mut read = Vec::new();
    for part in time.split(':') {
        let number = text_int(part)?;
        if read.len() == 2 {
            return Err(EngineError::value("too many values to unpack (expected 2)"));
        }
        read.push(number);
    }
    match read.as_slice() {
        [hour, minute] => Ok((*hour, *minute)),
        other => Err(EngineError::value(format!(
            "not enough values to unpack (expected 2, got {})",
            other.len()
        ))),
    }
}

/// The alarms that rang since the last look. `due_ms_of` turns an hour and minute of today into
/// milliseconds on the caller's local clock, as `datetime.timestamp()` does, so no zone is known
/// here. `fired` is changed as it goes, as the caller's set was.
#[allow(clippy::too_many_arguments)]
pub fn due_alarms(
    alarms: &[Value],
    today_iso: &str,
    weekday: i64,
    now_ms: i64,
    last_check_ms: Option<i64>,
    fired: &mut HashSet<String>,
    snoozed: &[(String, i64)],
    due_ms_of: &mut dyn FnMut(i64, i64) -> EngineResult<i64>,
) -> EngineResult<(Vec<Value>, Vec<(String, i64)>, i64)> {
    let start_ms = last_check_ms.unwrap_or(now_ms - REMINDER_WINDOW_MIN * 60_000);
    let mut queued = Vec::new();
    let mut remaining: Vec<(String, i64)> = snoozed.to_vec();
    for alarm in alarms {
        let fields = dict(alarm)?;
        if !truthy(fields.get("enabled")) {
            continue;
        }
        let days = match fields.get("days") {
            Some(value) if truthy(Some(value)) => value.as_array().cloned().unwrap_or_default(),
            _ => Vec::new(),
        };
        if !days.iter().any(|value| value.as_i64() == Some(weekday)) {
            continue;
        }
        let (hour, minute) = hour_and_minute(&py_str(item(fields, "time")?))?;
        let due_ms = due_ms_of(hour, minute)?;
        let key = alarm_key(today_iso, fields);
        if start_ms < due_ms && due_ms <= now_ms && !fired.contains(&key) {
            fired.insert(key);
            queued.push(alarm.clone());
        }
    }
    let waiting = remaining.clone();
    for (alarm_id, due_ms) in waiting {
        if !(start_ms < due_ms && due_ms <= now_ms) {
            continue;
        }
        remaining.retain(|(id, _)| *id != alarm_id);
        let found = alarms
            .iter()
            .find(|candidate| {
                candidate
                    .as_object()
                    .and_then(|map| map.get("id"))
                    .and_then(Value::as_str)
                    == Some(alarm_id.as_str())
            })
            .filter(|candidate| truthy(candidate.get("enabled")));
        if let Some(alarm) = found {
            queued.push(alarm.clone());
        }
    }
    Ok((queued, remaining, now_ms))
}

pub fn snooze_until(now_ms: i64) -> i64 {
    now_ms + ALARM_SNOOZE_MS
}
