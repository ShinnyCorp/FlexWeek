//! Week reading model from `desktop/native/weekmodel.py`.

use chrono::NaiveDate;
use serde_json::{Map, Value, json};

use std::sync::atomic::{AtomicBool, Ordering};

use crate::desk::calendar::{DAY_FULL, DAYS, is_series_checked};
use crate::desk::datetext::day_short;
use crate::desk::grid::work_session;
use crate::desk::pydate::{from_iso, iso_text};
use crate::desk::pyops::{
    Cmp, PyDict, compare, contains, eq, get, head, int_json, iterate, length, or_default,
    slice_chars, to_int, tuple_index,
};
use crate::desk::pyval::{subscript, type_error};
use crate::error::{EngineError, EngineResult};
use crate::stored::{py_str, text, truthy, type_name};
use crate::time::py_int as text_int;

static CLOCK_24H: AtomicBool = AtomicBool::new(true);

pub const SLACK_WORDS: [(&str, &str); 3] = [
    ("danger", "Cutting it close"),
    ("tight", "Tight"),
    ("ok", "Plenty of time"),
];
pub const NOT_PLANNED: &str = "Not planned yet.";
pub const HOMEWORK: &str = "assignments";
pub const END_OF_DAY: i64 = 24 * 60;
pub const LEFTOVER: [(&str, &str); 4] = [
    ("needs_time", "Not placed yet"),
    ("no_homework", "No homework added"),
    ("all_finished", "All homework finished"),
    ("calendar_only", "Nothing else scheduled today"),
];

pub fn set_clock_24h(on: bool) {
    CLOCK_24H.store(on, Ordering::Relaxed);
}

fn clock_24h() -> bool {
    CLOCK_24H.load(Ordering::Relaxed)
}

/// `hhmm.split(":")[:2]` read as hours and minutes.
pub fn minute_of(hhmm: &str) -> EngineResult<i128> {
    let parts: Vec<&str> = hhmm.split(':').take(2).collect();
    let [hours, minutes] = parts.as_slice() else {
        return Err(EngineError::value(format!(
            "not enough values to unpack (expected 2, got {})",
            parts.len()
        )));
    };
    Ok(i128::from(text_int(hours)?) * 60 + i128::from(text_int(minutes)?))
}

/// `minute_of` of a value the caller may not have made text of.
pub fn minute_of_value(hhmm: &Value) -> EngineResult<i128> {
    minute_of(text(hhmm, "split")?)
}

/// `hours % 24 < 12`, `hours % 12 or 12`, with Python's `%` on negative hours.
fn half_of(hours: i128) -> &'static str {
    if hours.rem_euclid(24) < 12 {
        "AM"
    } else {
        "PM"
    }
}

fn on_twelve(hours: i128) -> i128 {
    match hours.rem_euclid(12) {
        0 => 12,
        shown => shown,
    }
}

pub fn clock_text(minute: i64) -> String {
    clock_of(i128::from(minute))
}

pub fn clock_of(minute: i128) -> String {
    let hours = minute.div_euclid(60);
    let minutes = minute.rem_euclid(60);
    if clock_24h() {
        return format!("{hours:02}:{minutes:02}");
    }
    format!("{}:{minutes:02} {}", on_twelve(hours), half_of(hours))
}

/// `clock_text` of whatever the caller passed: `divmod(minute, 60)` and the `d` format take whole
/// numbers only.
pub fn clock_text_value(minute: &Value) -> EngineResult<String> {
    match minute {
        Value::Bool(_) => Ok(clock_of(to_int(minute)?)),
        Value::Number(_) if crate::desk::pyops::is_int(minute) => Ok(clock_of(to_int(minute)?)),
        Value::Number(_) => Err(EngineError::value(
            "Unknown format code 'd' for object of type 'float'",
        )),
        other => Err(type_error(format!(
            "unsupported operand type(s) for divmod(): '{}' and 'int'",
            type_name(other)
        ))),
    }
}

pub fn hhmm_text(hhmm: &str) -> EngineResult<String> {
    Ok(clock_of(minute_of(hhmm)?))
}

pub fn hhmm_text_value(hhmm: &Value) -> EngineResult<String> {
    Ok(clock_of(minute_of_value(hhmm)?))
}

pub fn time_format() -> &'static str {
    if clock_24h() { "HH:mm" } else { "h:mm AP" }
}

pub fn clock_label(minute: i64) -> String {
    clock_text(minute)
}

fn twelve(minute: i64) -> (String, &'static str) {
    let hours = i128::from(minute).div_euclid(60);
    let minutes = i128::from(minute).rem_euclid(60);
    let h = on_twelve(hours);
    let shown = if minutes == 0 {
        format!("{h}")
    } else {
        format!("{h}:{minutes:02}")
    };
    (shown, half_of(hours))
}

pub fn short_clock(minute: i64) -> String {
    if clock_24h() {
        return clock_text(minute);
    }
    let (shown, half) = twelve(minute);
    format!("{shown} {half}")
}

pub fn range_label(start: i64, end: i64) -> String {
    if clock_24h() {
        return format!("{}–{}", clock_text(start), clock_text(end));
    }
    let (first, first_half) = twelve(start);
    let (last, last_half) = twelve(end);
    if first_half == last_half {
        format!("{first}–{last} {last_half}")
    } else {
        format!("{first} {first_half}–{last} {last_half}")
    }
}

pub fn length_label(minutes: i64) -> String {
    let minutes = minutes.max(0);
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

pub fn planned_line(planned_min: i64, done_min: i64) -> String {
    if planned_min <= 0 {
        return "Nothing planned yet".to_string();
    }
    let done = if done_min <= 0 {
        "0 done".to_string()
    } else {
        format!("{} done", length_label(done_min))
    };
    format!("{} planned · {done}", length_label(planned_min))
}

/// `due_label`: a falsy `due` is no label; the rest must be a date, with a time after it when the
/// stamp names one.
pub fn due_label(due: &Value, today: NaiveDate) -> EngineResult<String> {
    if !truthy(Some(due)) {
        return Ok(String::new());
    }
    let day = match head(due, 10)? {
        Value::String(found) => from_iso(&found)?,
        _ => return Err(type_error("fromisoformat: argument must be str")),
    };
    let mut words = day_short(day, today);
    let due = due.as_str().unwrap_or_default();
    if crate::model::due_is_timed(due) {
        words.push_str(&format!(
            ", {}",
            hhmm_text(&slice_chars(due, Some(11), Some(16)))?
        ));
    }
    Ok(words)
}

/// `due_label` for a day text the caller held as text.
pub fn due_label_text(due: Option<&str>, today: NaiveDate) -> EngineResult<String> {
    due_label(&due.map_or(Value::Null, |found| json!(found)), today)
}

pub fn moved_words(
    block: &Value,
    from_day: i64,
    day: i64,
    start: i64,
    end: i64,
) -> EngineResult<String> {
    let day_name =
        || -> EngineResult<&'static str> { Ok(DAYS[tuple_index(DAYS.len(), &Value::from(day))?]) };
    let mut title = or_default(get(block, "title")?, json!("the block"));
    if !truthy(get(block, "start")?) {
        return Ok(format!(
            "Placed {} on {} {}.",
            py_str(&title),
            day_name()?,
            clock_label(start)
        ));
    }
    if is_series_checked(block)? {
        let full = DAY_FULL[tuple_index(DAY_FULL.len(), &Value::from(from_day))?];
        title = json!(format!("{full}'s {}", py_str(&title)));
    }
    let was = minute_of_value(subscript(block, "start")?)?;
    let was_end = was + to_int(subscript(block, "duration_min")?)?;
    let (start_at, end_at) = (i128::from(start), i128::from(end));
    let title = py_str(&title);
    if day == from_day && start_at == was && end_at != was_end {
        return Ok(format!("{title} now ends at {}.", clock_label(end)));
    }
    if day == from_day && end_at == was_end && start_at != was {
        return Ok(format!("{title} now starts at {}.", clock_label(start)));
    }
    Ok(format!(
        "Moved {title} to {} {}.",
        day_name()?,
        clock_label(start)
    ))
}

/// `days[0]` on whatever `days` is.
fn first_day(days: &Value) -> EngineResult<Value> {
    match days {
        Value::Object(_) if crate::stored::nonfinite(days).is_none() => {
            Err(EngineError::key_repr("0"))
        }
        other => crate::desk::pyops::first_of(other),
    }
}

pub fn added_words(block: &Value) -> EngineResult<String> {
    let title = or_default(get(block, "title")?, json!("a block"));
    let days = or_default(get(block, "days")?, json!([]));
    if truthy(get(block, "start")?) && length(&days)? == 1 {
        let name = DAYS[tuple_index(DAYS.len(), &first_day(&days)?)?];
        return Ok(format!(
            "Added {} on {name} {}.",
            py_str(&title),
            hhmm_text_value(subscript(block, "start")?)?
        ));
    }
    Ok(format!("Added {}.", py_str(&title)))
}

pub fn dated_words(title: &Value, iso: &Value, today: NaiveDate) -> EngineResult<String> {
    Ok(format!(
        "Moved {} to {}.",
        py_str(title),
        due_label(iso, today)?
    ))
}

/// `lookup.get(key)` on the dict the caller passed in.
fn dict_get<'a>(held: &'a Value, key: &Value) -> EngineResult<Option<&'a Value>> {
    let Value::Object(map) = held else {
        return Err(crate::stored::attribute_error(held, "get"));
    };
    crate::desk::pyops::hashable(key, "dict key")?;
    Ok(key.as_str().and_then(|name| map.get(name)))
}

/// `value.get(name)` as a value, None for a missing key.
fn field(holder: &Value, name: &str) -> EngineResult<Value> {
    Ok(get(holder, name)?.cloned().unwrap_or(Value::Null))
}

/// `sorted`'s order on keys that Python compares as tuples, which may refuse to.
fn key_less(left: &[Value], right: &[Value]) -> EngineResult<bool> {
    for (a, b) in left.iter().zip(right) {
        if !eq(a, b) {
            return compare(Cmp::Lt, a, b);
        }
    }
    Ok(left.len() < right.len())
}

/// `rows.sort(key=...)` for keys already made: CPython's binary insertion sort on a short list, so
/// the first pair it cannot compare is the one it names.
fn sort_by_key(rows: &mut [(Vec<Value>, Value)]) -> EngineResult<()> {
    let count = rows.len();
    if count < 2 {
        return Ok(());
    }
    if count > 64 {
        let mut failure = None;
        rows.sort_by(|left, right| {
            if failure.is_some() {
                return std::cmp::Ordering::Equal;
            }
            match key_less(&left.0, &right.0) {
                Ok(true) => std::cmp::Ordering::Less,
                Ok(false) => match key_less(&right.0, &left.0) {
                    Ok(true) => std::cmp::Ordering::Greater,
                    Ok(false) => std::cmp::Ordering::Equal,
                    Err(error) => {
                        failure = Some(error);
                        std::cmp::Ordering::Equal
                    }
                },
                Err(error) => {
                    failure = Some(error);
                    std::cmp::Ordering::Equal
                }
            }
        });
        return failure.map_or(Ok(()), Err);
    }
    let mut run = 2;
    if key_less(&rows[1].0, &rows[0].0)? {
        while run < count && key_less(&rows[run].0, &rows[run - 1].0)? {
            run += 1;
        }
        rows[..run].reverse();
    } else {
        while run < count && !key_less(&rows[run].0, &rows[run - 1].0)? {
            run += 1;
        }
    }
    for at in run..count {
        let mut low = 0;
        let mut high = at;
        while low < high {
            let middle = low + ((high - low) >> 1);
            if key_less(&rows[at].0, &rows[middle].0)? {
                high = middle;
            } else {
                low = middle + 1;
            }
        }
        rows[low..=at].rotate_right(1);
    }
    Ok(())
}

/// `due_sort_key(due, title)` as a comparable row of values.
fn due_key(due: &Value, title: &Value) -> EngineResult<Vec<Value>> {
    if !truthy(Some(due)) {
        return Ok(vec![
            json!("9999-12-31"),
            Value::from(END_OF_DAY),
            title.clone(),
        ]);
    }
    let Value::String(text) = due else {
        return Err(type_error(format!(
            "expected string or bytes-like object, got '{}'",
            type_name(due)
        )));
    };
    let (day, minute) = crate::model::parse_due(text)?;
    Ok(vec![
        json!(iso_text(day)),
        Value::from(minute),
        title.clone(),
    ])
}

/// `build_week`, as the JSON of the `WeekModel` it makes: every field holds what the blocks held.
pub fn build_week(
    week_start: &Value,
    blocks: &Value,
    assignments: &Value,
    trace: &Value,
) -> EngineResult<Value> {
    let homework = if truthy(Some(assignments)) {
        assignments.clone()
    } else {
        json!({})
    };
    let source = if truthy(Some(trace)) {
        trace.clone()
    } else {
        json!({})
    };
    let mut placed = PyDict::new();
    for item in iterate(&or_default(get(&source, "placed")?, json!([])))? {
        placed.set(subscript(&item, "id")?.clone(), item.clone())?;
    }
    let mut notes = PyDict::new();
    for item in iterate(&or_default(get(&source, "explanations")?, json!([])))? {
        notes.set(subscript(&item, "block_id")?.clone(), item.clone())?;
    }
    let mut occurrences: Vec<(Vec<Value>, Value)> = Vec::new();
    let mut waiting: Vec<(Value, Value, Value)> = Vec::new();
    for original in iterate(blocks)? {
        let block = if truthy(get(&original, "completed")?) {
            original.clone()
        } else {
            match placed.get(subscript(&original, "id")?)? {
                Some(item) => item.clone(),
                None => original.clone(),
            }
        };
        let assignment = or_default(
            dict_get(
                &homework,
                &or_default(get(&original, "assignment_id")?, json!("")),
            )?,
            json!({}),
        );
        let work = work_session(&original)?;
        let done = truthy(get(&block, "completed")?) || truthy(get(&assignment, "completed")?);
        let note = or_default(notes.get(subscript(&original, "id")?)?, json!({}));
        if !truthy(get(&block, "start")?) {
            if work && !done {
                let block_id = subscript(&original, "id")?.clone();
                let title = or_default(get(&original, "title")?, json!("Untitled"));
                let category = or_default(get(&original, "category")?, json!(HOMEWORK));
                let minutes = to_int(&or_default(get(&original, "duration_min")?, json!(0)))?;
                let assignment_id = field(&original, "assignment_id")?;
                let due = field(&assignment, "due")?;
                let reason = or_default(get(&note, "message")?, json!(NOT_PLANNED));
                let row = json!({
                    "block_id": block_id,
                    "title": title,
                    "category": category,
                    "minutes": int_json(minutes),
                    "assignment_id": assignment_id,
                    "due": due,
                    "reason": reason,
                });
                waiting.push((due_of(&row)?, title_of(&row)?, row));
            }
            continue;
        }
        let mut days = or_default(get(&block, "days")?, json!([]));
        if truthy(get(&block, "completed")?)
            && !matches!(get(&block, "completed_day")?, None | Some(Value::Null))
        {
            days = json!([subscript(&block, "completed_day")?]);
        }
        let start = minute_of_value(subscript(&block, "start")?)?;
        let span = to_int(&or_default(get(&block, "duration_min")?, json!(0)))?;
        let end = (start + span).min(i128::from(END_OF_DAY));
        for day in iterate(&days)? {
            let block_id = subscript(&original, "id")?.clone();
            let title = or_default(get(&block, "title")?, json!("Untitled"));
            let category = or_default(
                get(&block, "category")?,
                json!(if work { HOMEWORK } else { "" }),
            );
            let missed = contains(&or_default(get(&original, "missed_days")?, json!([])), &day)?;
            let assignment_id = field(&original, "assignment_id")?;
            let due = field(&assignment, "due")?;
            let slack = field(&note, "slack_status")?;
            let pinned = truthy(get(&block, "pinned")?);
            let key = vec![day.clone(), int_json(start), block_id.clone()];
            occurrences.push((
                key,
                json!({
                    "block_id": block_id,
                    "title": title,
                    "category": category,
                    "day": day,
                    "start": int_json(start),
                    "end": int_json(end),
                    "work": work,
                    "done": done,
                    "missed": missed,
                    "assignment_id": assignment_id,
                    "due": due,
                    "slack": slack,
                    "pinned": pinned,
                }),
            ));
        }
    }
    sort_by_key(&mut occurrences)?;
    let mut keyed = Vec::new();
    for (due, title, row) in waiting {
        let mut key = due_key(&due, &title)?;
        key.push(subscript(&row, "block_id")?.clone());
        keyed.push((key, row));
    }
    sort_by_key(&mut keyed)?;
    let mut worked: Vec<Value> = Vec::new();
    for block in iterate(blocks)? {
        let key = field(&block, "assignment_id")?;
        crate::desk::pyops::hashable(&key, "set element")?;
        if !key.is_null() && !worked.iter().any(|held| eq(held, &key)) {
            worked.push(key);
        }
    }
    let mut focus: i128 = 0;
    for key in &worked {
        let entry = or_default(dict_get(&homework, key)?, json!({}));
        focus += to_int(&or_default(get(&entry, "focus_minutes")?, json!(0)))?;
    }
    for block in iterate(blocks)? {
        if !truthy(get(&block, "assignment_id")?) {
            focus += to_int(&or_default(get(&block, "focus_minutes")?, json!(0)))?;
        }
    }
    let mut out = Map::new();
    out.insert("week_start".into(), week_start.clone());
    out.insert(
        "occurrences".into(),
        Value::Array(occurrences.into_iter().map(|(_, row)| row).collect()),
    );
    out.insert(
        "waiting".into(),
        Value::Array(keyed.into_iter().map(|(_, row)| row).collect()),
    );
    out.insert("focus_min".into(), int_json(focus));
    Ok(Value::Object(out))
}

fn due_of(row: &Value) -> EngineResult<Value> {
    Ok(subscript(row, "due")?.clone())
}

fn title_of(row: &Value) -> EngineResult<Value> {
    Ok(subscript(row, "title")?.clone())
}
