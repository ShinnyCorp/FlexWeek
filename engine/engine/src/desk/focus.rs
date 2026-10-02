//! Focus timer logic from `desktop/native/focus.py`, on the values as the Python code held them, so
//! a wrong kind of value raises what Python raised.

use serde_json::{Map, Value, json};

use crate::desk::planning::occurrence_days;
use crate::desk::pyops::{
    contains, eq, get, int_json, is_int, is_number, iterate, or_default, to_int,
};
use crate::desk::pyval::subscript;
use crate::desk::weekmodel::hhmm_text;
use crate::error::{EngineError, EngineResult};
use crate::stored::{py_str, text, truthy};
use crate::time::{hhmm_to_minutes, is_week_start};

pub const FOCUS_PHASES: [&str; 4] = ["work", "break", "long_break", "ended"];
pub const MAX_ESTIMATE_MIN: i128 = 24 * 60;
pub const MAX_FOCUS_MINUTES: i128 = 71400;
pub const MAX_FOCUS_SESSIONS: i128 = 9999;
pub const MORE_TIME_CHOICES: [i128; 8] = [15, 30, 45, 60, 90, 120, 180, 240];

fn null() -> &'static Value {
    static NULL: Value = Value::Null;
    &NULL
}

/// `int(source.get(key) or default)`.
fn timer(source: &Value, key: &str, default: i128) -> EngineResult<i128> {
    match get(source, key)? {
        Some(value) if truthy(Some(value)) => to_int(value),
        _ => Ok(default),
    }
}

pub fn phase_duration_ms(phase: &Value, prefs: &Value) -> EngineResult<i128> {
    let source = or_default(Some(prefs), json!({}));
    let minutes = if eq(phase, &json!("work")) {
        timer(&source, "timer_work_min", 30)?
    } else if eq(phase, &json!("long_break")) {
        timer(&source, "timer_long_break_min", 30)?
    } else {
        timer(&source, "timer_break_min", 15)?
    };
    Ok(minutes * 60_000)
}

pub fn format_countdown(milliseconds: i64) -> String {
    let seconds = ((i128::from(milliseconds) + 999).div_euclid(1000)).max(0);
    format!(
        "{:02}:{:02}",
        seconds.div_euclid(60),
        seconds.rem_euclid(60)
    )
}

pub fn remaining_ms(state: &Value, now_ms: i64) -> EngineResult<i128> {
    if truthy(get(state, "running")?) {
        let ends = to_int(&or_default(get(state, "endsAt")?, json!(0)))?;
        return Ok((ends - i128::from(now_ms)).max(0));
    }
    Ok(to_int(&or_default(get(state, "remainingMs")?, json!(0)))?.max(0))
}

pub fn focus_now(state: &Value) -> EngineResult<&'static str> {
    if state.is_null() {
        return Ok("");
    }
    let phase = get(state, "phase")?.unwrap_or(null());
    if phase.is_null() || eq(phase, &json!("ended")) {
        return Ok("");
    }
    if !eq(phase, &json!("work")) {
        return Ok("break");
    }
    Ok(if truthy(get(state, "running")?) {
        "focusing"
    } else {
        "paused"
    })
}

pub fn more_time_choices(estimate_min: i64) -> Vec<i64> {
    MORE_TIME_CHOICES
        .iter()
        .filter(|minutes| i128::from(estimate_min) + **minutes <= MAX_ESTIMATE_MIN)
        .map(|minutes| *minutes as i64)
        .collect()
}

pub fn persist_payload(state: &Value) -> EngineResult<Option<Value>> {
    if state.is_null() {
        return Ok(None);
    }
    let running = truthy(get(state, "running")?);
    let field = |name: &str| -> EngineResult<Value> {
        Ok(get(state, name)?.cloned().unwrap_or(Value::Null))
    };
    Ok(Some(json!({
        "assignmentId": field("assignmentId")?,
        "sessionId": field("blockId")?,
        "weekStart": field("weekStart")?,
        "day": field("day")?,
        "start": field("start")?,
        "phase": field("phase")?,
        "cycles": int_json(to_int(&or_default(get(state, "cycles")?, json!(0)))?),
        "endsAt": if running { field("endsAt")? } else { Value::Null },
        "remainingMs": if running { Value::Null } else { field("remainingMs")? },
    })))
}

fn text_or_none(value: Option<&Value>) -> Value {
    match value {
        Some(Value::String(found)) => json!(found),
        _ => Value::Null,
    }
}

pub fn restore_state(
    saved: &Value,
    assignments: &Value,
    blocks: &Value,
    now_ms: i64,
) -> EngineResult<Option<Value>> {
    if !matches!(saved, Value::Object(_)) || crate::stored::nonfinite(saved).is_some() {
        return Ok(None);
    }
    let phase = get(saved, "phase")?.unwrap_or(null());
    let week_start = get(saved, "weekStart")?.unwrap_or(null());
    let cycles = get(saved, "cycles")?.unwrap_or(null());
    let phase_ok = FOCUS_PHASES.iter().any(|name| eq(phase, &json!(name)));
    let week_ok = match week_start {
        Value::String(found) => is_week_start(found),
        _ => false,
    };
    if !phase_ok || !week_ok || !is_int(cycles) {
        return Ok(None);
    }
    let ends = get(saved, "endsAt")?.unwrap_or(null());
    let remaining = get(saved, "remainingMs")?.unwrap_or(null());
    let has_end = is_number(ends);
    if !has_end && !is_number(remaining) {
        return Ok(None);
    }
    let assignment_id = text_or_none(get(saved, "assignmentId")?);
    let assignment = if truthy(Some(&assignment_id)) {
        match assignments {
            Value::Object(map) => assignment_id.as_str().and_then(|name| map.get(name)),
            other => return Err(crate::stored::attribute_error(other, "get")),
        }
    } else {
        None
    };
    if truthy(Some(&assignment_id))
        && (assignment.is_none() || truthy(get(assignment.unwrap_or(null()), "completed")?))
    {
        return Ok(None);
    }
    let block_id = text_or_none(get(saved, "sessionId")?);
    let mut block = None;
    if truthy(Some(&block_id)) {
        for item in iterate(blocks)? {
            if eq(subscript(&item, "id")?, &block_id) {
                block = Some(item);
                break;
            }
        }
    }
    let mut title = json!("Quick focus");
    if truthy(Some(&block_id)) {
        let source = match assignment {
            Some(found) if truthy(Some(found)) => found.clone(),
            _ => match &block {
                Some(found) if truthy(Some(found)) => found.clone(),
                _ => json!({"title": "Focus session"}),
            },
        };
        title = subscript(&source, "title")?.clone();
    }
    let day = get(saved, "day")?.filter(|value| is_int(value)).cloned();
    let ends_at = to_int(&or_default(Some(ends), json!(0)))?;
    let mut state = json!({
        "weekStart": week_start,
        "blockId": block_id,
        "assignmentId": match assignment {
            Some(found) if truthy(Some(found)) => subscript(found, "id")?.clone(),
            _ => Value::Null,
        },
        "day": day.unwrap_or(Value::Null),
        "start": text_or_none(get(saved, "start")?),
        "title": title,
        "phase": phase,
        "cycles": cycles,
        "running": has_end,
        "endsAt": int_json(ends_at),
        "remainingMs": int_json(to_int(&or_default(Some(remaining), json!(0)))?),
    });
    if has_end
        && ends_at <= i128::from(now_ms)
        && let Value::Object(fields) = &mut state
    {
        fields.insert("running".into(), json!(false));
        fields.insert("remainingMs".into(), json!(0));
        fields.insert("expired".into(), json!(true));
    }
    Ok(Some(state))
}

pub fn begin_state(target: &Value, prefs: &Value, now_ms: i64) -> EngineResult<Value> {
    let duration = phase_duration_ms(&json!("work"), prefs)?;
    let mut state = spread(target)?;
    state.insert("phase".into(), json!("work"));
    state.insert("cycles".into(), json!(0));
    state.insert("running".into(), json!(true));
    state.insert("remainingMs".into(), int_json(duration));
    state.insert("endsAt".into(), int_json(i128::from(now_ms) + duration));
    Ok(Value::Object(state))
}

/// `{**value}`: only a dict can be spread.
fn spread(value: &Value) -> EngineResult<Map<String, Value>> {
    match value {
        Value::Object(map) if crate::stored::nonfinite(value).is_none() => Ok(map.clone()),
        other => Err(crate::desk::pyval::type_error(format!(
            "'{}' object is not a mapping",
            crate::stored::type_name(other)
        ))),
    }
}

fn changing(state: &Value) -> EngineResult<Map<String, Value>> {
    match state {
        Value::Object(map) if crate::stored::nonfinite(state).is_none() => Ok(map.clone()),
        other => Err(crate::stored::attribute_error(other, "get")),
    }
}

pub fn pause_state(state: &Value, now_ms: i64) -> EngineResult<Value> {
    let mut next = changing(state)?;
    let held = Value::Object(next.clone());
    if eq(get(&held, "phase")?.unwrap_or(null()), &json!("ended")) {
        return Ok(held);
    }
    if truthy(get(&held, "running")?) {
        next.insert("remainingMs".into(), int_json(remaining_ms(&held, now_ms)?));
        next.insert("running".into(), json!(false));
    } else {
        next.insert("running".into(), json!(true));
        let rest = to_int(&or_default(get(&held, "remainingMs")?, json!(0)))?;
        next.insert("endsAt".into(), int_json(i128::from(now_ms) + rest));
    }
    Ok(Value::Object(next))
}

pub fn set_phase(state: &Value, phase: &Value, prefs: &Value, now_ms: i64) -> EngineResult<Value> {
    let duration = phase_duration_ms(phase, prefs)?;
    let mut next = crate::desk::pyops::assigning(state)?;
    next.insert("phase".into(), phase.clone());
    next.insert("running".into(), json!(true));
    next.insert("remainingMs".into(), int_json(duration));
    next.insert("endsAt".into(), int_json(i128::from(now_ms) + duration));
    Ok(Value::Object(next))
}

pub fn break_phase(cycles: i64, prefs: &Value) -> EngineResult<&'static str> {
    let source = or_default(Some(prefs), json!({}));
    let every = timer(&source, "timer_long_break_every", 4)?;
    if cycles > 0 {
        if every == 0 {
            return Err(EngineError::zero_division("integer modulo by zero"));
        }
        if i128::from(cycles) % every == 0 {
            return Ok("long_break");
        }
    }
    Ok("break")
}

/// One finished work phase credited to `target`: a session more, and the minutes.
fn credited(target: &Value, amount: i128) -> EngineResult<Value> {
    let mut updated = changing(target)?;
    let held = Value::Object(updated.clone());
    let sessions = to_int(&or_default(get(&held, "focus_sessions")?, json!(0)))? + 1;
    updated.insert(
        "focus_sessions".into(),
        int_json(sessions.min(MAX_FOCUS_SESSIONS)),
    );
    let minutes = to_int(&or_default(get(&held, "focus_minutes")?, json!(0)))? + amount;
    updated.insert(
        "focus_minutes".into(),
        int_json(minutes.min(MAX_FOCUS_MINUTES)),
    );
    Ok(Value::Object(updated))
}

pub fn credit_target(
    state: &Value,
    assignment: &Value,
    block: &Value,
    work_min: i64,
) -> EngineResult<Option<Value>> {
    if !truthy(get(state, "blockId")?) {
        return Ok(None);
    }
    let amount = MAX_FOCUS_MINUTES.min(i128::from(work_min));
    if truthy(get(state, "assignmentId")?) {
        if assignment.is_null() {
            return Ok(None);
        }
        return credited(assignment, amount).map(Some);
    }
    if block.is_null() {
        return Ok(None);
    }
    credited(block, amount).map(Some)
}

pub fn focus_candidates(
    blocks: &Value,
    assignments: &Value,
    trace: &Value,
) -> EngineResult<Vec<Value>> {
    let mut placed = crate::desk::pyops::PyDict::new();
    let source = or_default(Some(trace), json!({}));
    for item in iterate(&or_default(get(&source, "placed")?, json!([])))? {
        placed.set(subscript(&item, "id")?.clone(), item.clone())?;
    }
    let mut result = Vec::new();
    for block in iterate(blocks)? {
        let work = eq(get(&block, "kind")?.unwrap_or(null()), &json!("flexible"))
            || eq(
                get(&block, "pomodoro_role")?.unwrap_or(null()),
                &json!("work"),
            );
        if !work || truthy(get(&block, "completed")?) {
            continue;
        }
        let Value::Object(table) = assignments else {
            return Err(crate::stored::attribute_error(assignments, "get"));
        };
        let link = get(&block, "assignment_id")?
            .cloned()
            .unwrap_or(Value::Null);
        crate::desk::pyops::hashable(&link, "dict key")?;
        let assignment = link.as_str().and_then(|name| table.get(name));
        if let Some(found) = assignment
            && truthy(Some(found))
            && truthy(get(found, "completed")?)
        {
            continue;
        }
        let own = if truthy(get(&block, "start")?) {
            block.clone()
        } else {
            Value::Null
        };
        let placement = placed
            .get(subscript(&block, "id")?)?
            .cloned()
            .unwrap_or(own);
        if placement.is_null() || !truthy(get(&placement, "start")?) {
            continue;
        }
        let days = or_default(get(&placement, "days")?, json!([null]));
        let first_day = crate::desk::pyops::first_of(&days)?;
        let owner = match assignment {
            Some(found) if truthy(Some(found)) => found.clone(),
            _ => block.clone(),
        };
        result.push(json!({
            "id": subscript(&block, "id")?,
            "title": subscript(&block, "title")?,
            "day": first_day,
            "start": subscript(&placement, "start")?,
            "focus_sessions": int_json(to_int(&or_default(get(&owner, "focus_sessions")?, json!(0)))?),
            "focus_minutes": int_json(to_int(&or_default(get(&owner, "focus_minutes")?, json!(0)))?),
        }));
    }
    Ok(result)
}

pub fn now_and_next(blocks: &Value, day: &Value, minute: i64) -> EngineResult<Value> {
    let mut active: Vec<(i64, Value)> = Vec::new();
    for block in iterate(&or_default(Some(blocks), json!([])))? {
        if !truthy(get(&block, "start")?) || truthy(get(&block, "completed")?) {
            continue;
        }
        if contains(&or_default(get(&block, "missed_days")?, json!([])), day)? {
            continue;
        }
        if !contains(&Value::Array(occurrence_days(&block)?), day)? {
            continue;
        }
        active.push((0, block));
    }
    for entry in &mut active {
        entry.0 = hhmm_to_minutes(text(subscript(&entry.1, "start")?, "split")?)?;
    }
    active.sort_by_key(|entry| entry.0);
    let mut current = None;
    let mut following = None;
    for (start, block) in &active {
        let end = i128::from(*start) + to_int(subscript(block, "duration_min")?)?;
        if current.is_none() && i128::from(*start) <= i128::from(minute) && i128::from(minute) < end
        {
            current = Some(block.clone());
        }
        if following.is_none() && i128::from(*start) > i128::from(minute) {
            following = Some(block.clone());
        }
    }
    Ok(json!({
        "current": current.unwrap_or(Value::Null),
        "next": following.unwrap_or(Value::Null),
    }))
}

fn length_words(minutes: i128) -> String {
    let positive = minutes.max(0);
    let (hours, rest) = (positive.div_euclid(60), positive.rem_euclid(60));
    if hours == 0 {
        format!("{rest} min")
    } else if rest == 0 {
        format!("{hours} h")
    } else {
        format!("{hours} h {rest} min")
    }
}

pub fn now_next_line(result: &Value, minute: i64) -> EngineResult<String> {
    let mut parts = Vec::new();
    let current = get(result, "current")?.cloned().unwrap_or(Value::Null);
    let following = get(result, "next")?.cloned().unwrap_or(Value::Null);
    if truthy(Some(&current)) {
        let end = i128::from(hhmm_to_minutes(text(
            subscript(&current, "start")?,
            "split",
        )?)?)
            + to_int(subscript(&current, "duration_min")?)?;
        parts.push(format!(
            "Now: {} · {} left",
            py_str(subscript(&current, "title")?),
            length_words(end - i128::from(minute))
        ));
    }
    if truthy(Some(&following)) {
        let wait = i128::from(hhmm_to_minutes(text(
            subscript(&following, "start")?,
            "split",
        )?)?)
            - i128::from(minute);
        let suffix = if truthy(Some(&current)) {
            String::new()
        } else {
            format!(" (in {})", length_words(wait))
        };
        parts.push(format!(
            "Next: {} at {}{suffix}",
            py_str(subscript(&following, "title")?),
            hhmm_text(text(subscript(&following, "start")?, "split")?)?
        ));
    }
    Ok(parts.join("  →  "))
}
