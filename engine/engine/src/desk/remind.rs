//! Reminder due checks from `desktop/native/remind.py`.

use chrono::Datelike;
use serde_json::{Map, Value, json};

use crate::desk::calendar::DAYS;
use crate::desk::planning::occurrence_days;
use crate::desk::pydate::{calendar_date, monday_text};
use crate::desk::pyops::{
    Cmp, PyDict, compare, contains, eq, get, iterate, or_default, py_dict, to_int, tuple_index,
};
use crate::desk::pyval::{list_of, subscript, type_error};
use crate::desk::weekmodel::hhmm_text;
use crate::error::{EngineError, EngineResult};
use crate::stored::{Dict, attribute_error, py_str, text, truthy, type_name};
use crate::time::{hhmm_to_minutes, py_int as text_int};

pub const REMINDER_WINDOW_MIN: i64 = 2;
pub const REMINDER_POLL_MS: i64 = 30_000;
pub const ALARM_SNOOZE_MIN: i64 = 5;
pub const ALARM_SNOOZE_MS: i64 = ALARM_SNOOZE_MIN * 60_000;
/// Minutes before a block that its reminder comes, until the student chooses another.
pub const REMINDER_LEAD_DEFAULT_MIN: i64 = 5;

/// `int(prefs["reminder_lead_min"])`, or the default when there are no prefs or the key is None.
pub fn reminder_lead_min(prefs: &Value, default: i64) -> EngineResult<i128> {
    if !truthy(Some(prefs)) {
        return Ok(i128::from(default));
    }
    match get(prefs, "reminder_lead_min")? {
        None | Some(Value::Null) => Ok(i128::from(default)),
        Some(_) => to_int(subscript(prefs, "reminder_lead_min")?),
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
    let start = i128::from(start_min);
    let lead = i128::from(lead).max(0);
    start - lead <= i128::from(now_min) && i128::from(now_min) <= start
}

/// A block's song plays from its start for as long as its reminder leads it, so a start the poll
/// reached a few minutes late still plays. A lead under the alarm window gets the window instead.
pub fn song_due(start_min: i64, now_min: i64, lead: i64) -> bool {
    let window = i128::from(lead).max(i128::from(REMINDER_WINDOW_MIN));
    i128::from(start_min) <= i128::from(now_min)
        && i128::from(now_min) <= i128::from(start_min) + window
}

/// What plays when a block starts: its own Spotify link, else the Settings link when the chosen
/// sound is Spotify. None means no song, and the start is announced by a notice instead.
fn start_link(
    block: &Value,
    default_link: &Value,
    sound_is_spotify: bool,
) -> EngineResult<Option<Value>> {
    let own = get(block, "spotify_url")?;
    if truthy(own) {
        return Ok(own.cloned());
    }
    if sound_is_spotify && truthy(Some(default_link)) {
        return Ok(Some(default_link.clone()));
    }
    Ok(None)
}

pub fn reminder_key(week_start: &str, block_id: &str, day: i64, start: &str) -> String {
    [week_start, block_id, &day.to_string(), start].join("|")
}

pub fn alarm_key(iso_date: &str, alarm: &Value) -> EngineResult<String> {
    let shown = |name: &str| -> EngineResult<String> {
        Ok(match get(alarm, name)? {
            Some(value) if truthy(Some(value)) => py_str(value),
            _ => String::new(),
        })
    };
    Ok([iso_date, &shown("id")?, &shown("time")?].join("|"))
}

pub fn reminder_blocks(blocks: &Value, trace: &Value) -> EngineResult<Vec<Value>> {
    let mut sources = PyDict::new();
    for block in iterate(blocks)? {
        sources.set(subscript(&block, "id")?.clone(), block.clone())?;
    }
    if !truthy(Some(trace)) {
        return iterate(blocks);
    }
    let mut locked = Vec::new();
    for block in iterate(blocks)? {
        if eq(
            get(&block, "kind")?.unwrap_or(&Value::Null),
            &json!("locked"),
        ) {
            locked.push(block);
        }
    }
    let mut placed = Vec::new();
    for item in iterate(&or_default(get(trace, "placed")?, json!([])))? {
        if !eq(
            get(&item, "kind")?.unwrap_or(&Value::Null),
            &json!("flexible"),
        ) {
            continue;
        }
        let Some(source) = sources.get(subscript(&item, "id")?)? else {
            placed.push(item);
            continue;
        };
        let completed = get(source, "completed")?.cloned().unwrap_or(Value::Null);
        let missed = Value::Array(list_of(&or_default(
            get(source, "missed_days")?,
            json!([]),
        ))?);
        let title = match get(source, "title")? {
            Some(title) if truthy(Some(title)) => title.clone(),
            _ => get(&item, "title")?.cloned().unwrap_or(Value::Null),
        };
        let mut merged = py_dict(&item)?;
        merged.insert("completed".into(), completed);
        merged.insert("missed_days".into(), missed);
        merged.insert("title".into(), title);
        placed.push(Value::Object(merged));
    }
    locked.extend(placed);
    Ok(locked)
}

/// A reminder key built from a block's id: `"|".join` takes strings only.
fn key_part<'a>(block: &'a Value, name: &str, position: usize) -> EngineResult<&'a str> {
    match subscript(block, name)? {
        Value::String(text) => Ok(text),
        other => Err(type_error(format!(
            "sequence item {position}: expected str instance, {} found",
            type_name(other)
        ))),
    }
}

pub fn todays_starts(
    blocks: &Value,
    trace: &Value,
    today_iso: &str,
) -> EngineResult<Vec<(Value, Value, i64, String)>> {
    let week_start = monday_text(today_iso)?;
    let mut rows = Vec::new();
    for block in reminder_blocks(blocks, trace)? {
        let start = get(&block, "start")?;
        if !truthy(start) || truthy(get(&block, "completed")?) {
            continue;
        }
        let start = start.unwrap_or(&Value::Null);
        for day in occurrence_days(&block)? {
            let missed = or_default(get(&block, "missed_days")?, json!([]));
            if contains(&missed, &day)? {
                continue;
            }
            let shown =
                crate::stored::add_days_of(crate::desk::pydate::from_iso(&week_start)?, &day)?;
            if crate::desk::pydate::iso_text(shown) != today_iso {
                continue;
            }
            let start = text(start, "split")?;
            let start_min = hhmm_to_minutes(start)?;
            let key = [
                week_start.as_str(),
                key_part(&block, "id", 1)?,
                &py_str(&day),
                start,
            ]
            .join("|");
            rows.push((block.clone(), day, start_min, key));
        }
    }
    Ok(rows)
}

/// `key in container` for a set the caller holds, or for whatever it held instead.
fn member(container: &Value, is_set: bool, key: &str) -> EngineResult<bool> {
    let item = json!(key);
    if is_set {
        return Ok(iterate(container)?.iter().any(|held| eq(held, &item)));
    }
    contains(container, &item)
}

#[allow(clippy::too_many_arguments)]
pub fn due_reminders(
    blocks: &Value,
    trace: &Value,
    today_iso: &str,
    now_min: i64,
    lead_min: i64,
    fired: &Value,
    fired_is_set: bool,
    default_link: &Value,
    sound_is_spotify: bool,
) -> EngineResult<Vec<Value>> {
    let mut due = Vec::new();
    for (block, day, start_min, key) in todays_starts(blocks, trace, today_iso)? {
        if member(fired, fired_is_set, &key)? || !start_alert_due(start_min, now_min, lead_min) {
            continue;
        }
        let started = now_min >= start_min;
        if started && start_link(&block, default_link, sound_is_spotify)?.is_some() {
            continue;
        }
        let title = py_str(subscript(&block, "title")?);
        let start = text(subscript(&block, "start")?, "split")?;
        due.push(json!({
            "key": key,
            "title": format!("{title} {}", if started { "starts now" } else { "starts soon" }),
            "body": format!("{} · {}", hhmm_text(start)?, DAYS[tuple_index(DAYS.len(), &day)?]),
        }));
    }
    Ok(due)
}

#[allow(clippy::too_many_arguments)]
pub fn due_songs(
    blocks: &Value,
    trace: &Value,
    today_iso: &str,
    now_min: i64,
    lead_min: i64,
    played: &Value,
    played_is_set: bool,
    default_link: &Value,
    sound_is_spotify: bool,
) -> EngineResult<Vec<Value>> {
    let mut due = Vec::new();
    for (block, _day, start_min, key) in todays_starts(blocks, trace, today_iso)? {
        let Some(link) = start_link(&block, default_link, sound_is_spotify)? else {
            continue;
        };
        if member(played, played_is_set, &key)? || !song_due(start_min, now_min, lead_min) {
            continue;
        }
        due.push(json!({
            "id": key,
            "name": subscript(&block, "title")?,
            "time": subscript(&block, "start")?,
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
/// here. `fired` is the caller's container; the keys this adds to it come back in `added`, whether
/// or not the call goes on to fail, as the caller's set was changed as it went.
#[allow(clippy::too_many_arguments)]
pub fn due_alarms(
    alarms: &Value,
    today_iso: &str,
    weekday: i64,
    now_ms: i64,
    last_check_ms: Option<i64>,
    fired: &Value,
    fired_is_set: bool,
    added: &mut Vec<String>,
    snoozed: &Value,
    due_ms_of: &mut dyn FnMut(i64, i64) -> EngineResult<i64>,
) -> EngineResult<(Vec<Value>, Vec<(Value, Value)>, i64)> {
    let now = Value::from(now_ms);
    let start_ms = match last_check_ms {
        Some(found) => Value::from(found),
        None => Value::from(now_ms - REMINDER_WINDOW_MIN * 60_000),
    };
    let mut queued = Vec::new();
    let mut remaining: Vec<(String, Value)> = py_dict(snoozed)?.into_iter().collect();
    let day = Value::from(weekday);
    for alarm in iterate(alarms)? {
        if !truthy(get(&alarm, "enabled")?) {
            continue;
        }
        if !contains(&or_default(get(&alarm, "days")?, json!([])), &day)? {
            continue;
        }
        let (hour, minute) = hour_and_minute(&py_str(subscript(&alarm, "time")?))?;
        let due_ms = Value::from(due_ms_of(hour, minute)?);
        let key = alarm_key(today_iso, &alarm)?;
        if compare(Cmp::Lt, &start_ms, &due_ms)?
            && compare(Cmp::Le, &due_ms, &now)?
            && !(member(fired, fired_is_set, &key)? || added.contains(&key))
        {
            if !fired_is_set {
                return Err(attribute_error(fired, "add"));
            }
            added.push(key);
            queued.push(Value::Object(py_dict(&alarm)?));
        }
    }
    let alarm_list = iterate(alarms)?;
    for (alarm_id, due_ms) in remaining.clone() {
        if !(compare(Cmp::Lt, &start_ms, &due_ms)? && compare(Cmp::Le, &due_ms, &now)?) {
            continue;
        }
        remaining.retain(|(id, _)| *id != alarm_id);
        let mut found = None;
        for candidate in &alarm_list {
            if eq(
                get(candidate, "id")?.unwrap_or(&Value::Null),
                &json!(alarm_id),
            ) {
                found = Some(candidate);
                break;
            }
        }
        if let Some(alarm) = found
            && truthy(Some(alarm))
            && truthy(get(alarm, "enabled")?)
        {
            queued.push(Value::Object(py_dict(alarm)?));
        }
    }
    Ok((
        queued,
        remaining
            .into_iter()
            .map(|(id, due)| (Value::from(id), due))
            .collect(),
        now_ms,
    ))
}

pub fn snooze_until(now_ms: i64) -> i64 {
    now_ms + ALARM_SNOOZE_MS
}

/// `now_ms / 1000.0`: the seconds the local clock is asked about.
pub fn seconds_of(now_ms: i64) -> f64 {
    now_ms as f64 / 1000.0
}

/// `millis / 1000` for milliseconds a caller reports as a number of either kind.
pub fn seconds_of_millis(millis: f64) -> f64 {
    millis / 1000.0
}

/// `int(seconds * 1000)`: whole milliseconds of a timestamp, cut towards zero.
pub fn millis_of(seconds: f64) -> i64 {
    (seconds * 1000.0).trunc() as i64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn milliseconds_are_asked_of_the_clock_as_seconds() {
        assert_eq!(seconds_of(1_790_000_000_000), 1_790_000_000.0);
        assert_eq!(seconds_of(1_500), 1.5);
        assert_eq!(seconds_of(-1_500), -1.5);
        assert_eq!(seconds_of_millis(1_500.5), 1.5005);
    }

    #[test]
    fn a_timestamp_is_cut_to_whole_milliseconds_towards_zero() {
        assert_eq!(millis_of(1_790_000_000.0), 1_790_000_000_000);
        assert_eq!(millis_of(1.9999), 1_999);
        assert_eq!(millis_of(-1.9999), -1_999);
        assert_eq!(millis_of(-0.0004), 0);
    }
}
