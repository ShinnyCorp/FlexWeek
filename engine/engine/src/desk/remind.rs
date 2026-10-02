//! Reminder due checks from `desktop/native/remind.py`.

use chrono::{Datelike, NaiveDate, Timelike};
use serde_json::{Map, Value, json};

use crate::desk::calendar::{DAYS, date_for_day, monday_of};
use crate::desk::reuse::occurrence_days;
use crate::desk::weekmodel::hhmm_text;
use crate::time::hhmm_to_minutes;

pub const REMINDER_WINDOW_MIN: i64 = 2;
pub const REMINDER_POLL_MS: i64 = 30_000;
pub const ALARM_SNOOZE_MIN: i64 = 5;
pub const ALARM_SNOOZE_MS: i64 = ALARM_SNOOZE_MIN * 60_000;

pub fn reminder_lead_min(prefs: Option<&Map<String, Value>>, default: i64) -> i64 {
    prefs
        .and_then(|p| p.get("reminder_lead_min"))
        .and_then(Value::as_i64)
        .unwrap_or(default)
}

pub fn clock_parts(now_ms: i64) -> Map<String, Value> {
    let secs = now_ms / 1000;
    let moment = chrono::DateTime::from_timestamp(secs, 0).expect("timestamp");
    let local = moment.naive_local();
    let midnight = local.date().and_hms_opt(0, 0, 0).expect("midnight");
    let mut out = Map::new();
    let date = local.date();
    out.insert(
        "iso".into(),
        json!(format!(
            "{:04}-{:02}-{:02}",
            date.year(),
            date.month(),
            date.day()
        )),
    );
    out.insert(
        "day".into(),
        json!(i64::from(local.weekday().num_days_from_monday())),
    );
    out.insert(
        "minute".into(),
        json!(i64::from(local.hour()) * 60 + i64::from(local.minute())),
    );
    out.insert(
        "midnight_ms".into(),
        json!(midnight.and_utc().timestamp_millis()),
    );
    out.insert("now_ms".into(), json!(now_ms));
    out
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

pub fn alarm_key(iso_date: &str, alarm: &Map<String, Value>) -> String {
    [
        iso_date,
        alarm.get("id").and_then(Value::as_str).unwrap_or(""),
        alarm.get("time").and_then(Value::as_str).unwrap_or(""),
    ]
    .join("|")
}

pub fn reminder_blocks(blocks: &[Value], trace: Option<&Value>) -> Vec<Value> {
    let sources: std::collections::HashMap<String, Value> = blocks
        .iter()
        .filter_map(|b| Some((b.get("id")?.as_str()?.to_string(), b.clone())))
        .collect();
    // Python treats None and an empty trace as "there is no plan", so the saved blocks stand.
    let trace = trace.filter(|value| match value {
        Value::Null | Value::Bool(false) => false,
        Value::Object(map) if map.is_empty() => false,
        Value::Array(items) if items.is_empty() => false,
        Value::String(text) if text.is_empty() => false,
        _ => true,
    });
    let Some(trace) = trace else {
        return blocks.to_vec();
    };
    let locked: Vec<Value> = blocks
        .iter()
        .filter(|b| b.get("kind").and_then(Value::as_str) == Some("locked"))
        .cloned()
        .collect();
    let mut placed = Vec::new();
    for item in trace
        .get("placed")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        if item.get("kind").and_then(Value::as_str) != Some("flexible") {
            continue;
        }
        let Some(source) = item
            .get("id")
            .and_then(Value::as_str)
            .and_then(|id| sources.get(id))
        else {
            placed.push(item.clone());
            continue;
        };
        let mut merged = item.as_object().cloned().unwrap_or_default();
        merged.insert(
            "completed".into(),
            source.get("completed").cloned().unwrap_or(Value::Null),
        );
        merged.insert(
            "missed_days".into(),
            json!(
                source
                    .get("missed_days")
                    .and_then(Value::as_array)
                    .cloned()
                    .unwrap_or_default()
            ),
        );
        merged.insert(
            "title".into(),
            json!(
                source
                    .get("title")
                    .and_then(Value::as_str)
                    .or_else(|| item.get("title").and_then(Value::as_str))
                    .unwrap_or("")
            ),
        );
        placed.push(Value::Object(merged));
    }
    let mut out = locked;
    out.extend(placed);
    out
}

pub fn todays_starts(
    blocks: &[Value],
    trace: Option<&Value>,
    today_iso: &str,
) -> Vec<(Value, i64, i64, String)> {
    let week_start = monday_of(today_iso);
    let mut rows = Vec::new();
    for block in reminder_blocks(blocks, trace) {
        let Some(start) = block
            .get("start")
            .and_then(Value::as_str)
            .filter(|start| !start.is_empty())
        else {
            continue;
        };
        if block.get("completed").and_then(Value::as_bool) == Some(true) {
            continue;
        }
        for day in occurrence_days(&block) {
            if block
                .get("missed_days")
                .and_then(Value::as_array)
                .is_some_and(|m| m.iter().any(|v| v.as_i64() == Some(day)))
            {
                continue;
            }
            if date_for_day(&week_start, day) != today_iso {
                continue;
            }
            let start_min = hhmm_to_minutes(start).unwrap_or(0);
            let key = reminder_key(
                &week_start,
                block.get("id").and_then(Value::as_str).unwrap_or(""),
                day,
                start,
            );
            rows.push((block.clone(), day, start_min, key));
        }
    }
    rows
}

pub fn due_reminders(
    blocks: &[Value],
    trace: Option<&Value>,
    today_iso: &str,
    now_min: i64,
    lead_min: i64,
    fired: &std::collections::HashSet<String>,
) -> Vec<Value> {
    let mut due = Vec::new();
    for (block, day, start_min, key) in todays_starts(blocks, trace, today_iso) {
        if fired.contains(&key) || !start_alert_due(start_min, now_min, lead_min) {
            continue;
        }
        let started = now_min >= start_min;
        let has_song = block
            .get("spotify_url")
            .and_then(Value::as_str)
            .is_some_and(|link| !link.is_empty());
        if started && has_song {
            continue;
        }
        let title = block.get("title").and_then(Value::as_str).unwrap_or("");
        due.push(json!({
            "key": key,
            "title": format!("{title} {}", if started { "starts now" } else { "starts soon" }),
            "body": format!("{} · {}", hhmm_text(block.get("start").and_then(Value::as_str).unwrap_or("00:00")), DAYS[day as usize]),
        }));
    }
    due
}

pub fn due_songs(
    blocks: &[Value],
    trace: Option<&Value>,
    today_iso: &str,
    now_min: i64,
    played: &std::collections::HashSet<String>,
) -> Vec<Value> {
    let mut due = Vec::new();
    for (block, _day, start_min, key) in todays_starts(blocks, trace, today_iso) {
        let Some(link) = block
            .get("spotify_url")
            .and_then(Value::as_str)
            .filter(|link| !link.is_empty())
        else {
            continue;
        };
        if played.contains(&key) || !song_due(start_min, now_min) {
            continue;
        }
        due.push(json!({
            "id": key,
            "name": block.get("title"),
            "time": block.get("start"),
            "days": [],
            "enabled": true,
            "sound": "spotify",
            "spotify_url": link,
            "block": true,
        }));
    }
    due
}

pub fn due_alarms(
    alarms: &[Value],
    today_iso: &str,
    weekday: i64,
    now_ms: i64,
    _midnight_ms: i64,
    last_check_ms: Option<i64>,
    fired: &mut std::collections::HashSet<String>,
    snoozed: &mut std::collections::HashMap<String, i64>,
) -> (Vec<Value>, i64) {
    let start_ms = last_check_ms.unwrap_or(now_ms - REMINDER_WINDOW_MIN * 60_000);
    let mut queued = Vec::new();
    let remaining_snooze = snoozed.clone();
    for alarm in alarms {
        let Some(obj) = alarm.as_object() else {
            continue;
        };
        if obj.get("enabled").and_then(Value::as_bool) != Some(true) {
            continue;
        }
        if !obj
            .get("days")
            .and_then(Value::as_array)
            .is_some_and(|d| d.iter().any(|v| v.as_i64() == Some(weekday)))
        {
            continue;
        }
        let time = obj.get("time").and_then(Value::as_str).unwrap_or("0:0");
        let parts: Vec<i64> = time.split(':').filter_map(|p| p.parse().ok()).collect();
        let (hour, minute) = (
            parts.first().copied().unwrap_or(0),
            parts.get(1).copied().unwrap_or(0),
        );
        let day = NaiveDate::parse_from_str(today_iso, "%Y-%m-%d").expect("today");
        let due_at = day.and_hms_opt(hour as u32, minute as u32, 0).expect("due");
        let due_ms = due_at.and_utc().timestamp_millis();
        let key = alarm_key(today_iso, obj);
        if start_ms < due_ms && due_ms <= now_ms && !fired.contains(&key) {
            fired.insert(key);
            queued.push(alarm.clone());
        }
    }
    for (alarm_id, due_ms) in remaining_snooze.clone() {
        if !(start_ms < due_ms && due_ms <= now_ms) {
            continue;
        }
        snoozed.remove(&alarm_id);
        if let Some(alarm) = alarms.iter().find(|a| {
            a.get("id").and_then(Value::as_str) == Some(alarm_id.as_str())
                && a.get("enabled").and_then(Value::as_bool) == Some(true)
        }) {
            queued.push(alarm.clone());
        }
    }
    (queued, now_ms)
}

pub fn snooze_until(now_ms: i64) -> i64 {
    now_ms + ALARM_SNOOZE_MS
}
