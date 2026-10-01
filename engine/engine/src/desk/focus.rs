//! Focus timer logic from `desktop/native/focus.py`.

use serde_json::{json, Map, Value};

use crate::desk::calendar::deep_copy;
use crate::desk::reuse::occurrence_days;
use crate::desk::weekmodel::{hhmm_text, length_label};
use crate::time::{hhmm_to_minutes, is_week_start};

pub const FOCUS_PHASES: [&str; 4] = ["work", "break", "long_break", "ended"];
pub const FOCUS_PHASE_LABEL: [(&str, &str); 4] = [
    ("work", "Focus session"),
    ("break", "Break"),
    ("long_break", "Long break"),
    ("ended", "Session finished"),
];
pub const MAX_ESTIMATE_MIN: i64 = 24 * 60;
pub const MAX_FOCUS_MINUTES: i64 = 71400;
pub const MAX_FOCUS_SESSIONS: i64 = 9999;
pub const MORE_TIME_CHOICES: [i64; 8] = [15, 30, 45, 60, 90, 120, 180, 240];

pub struct DefaultTimers {
    pub timer_work_min: i64,
    pub timer_break_min: i64,
    pub timer_long_break_min: i64,
    pub timer_long_break_every: i64,
}

impl Default for DefaultTimers {
    fn default() -> Self {
        Self {
            timer_work_min: 30,
            timer_break_min: 15,
            timer_long_break_min: 30,
            timer_long_break_every: 4,
        }
    }
}

pub fn phase_duration_ms(phase: &str, prefs: Option<&Map<String, Value>>) -> i64 {
    let defaults = DefaultTimers::default();
    let minutes = match phase {
        "work" => prefs
            .and_then(|p| p.get("timer_work_min"))
            .and_then(Value::as_i64)
            .unwrap_or(defaults.timer_work_min),
        "long_break" => prefs
            .and_then(|p| p.get("timer_long_break_min"))
            .and_then(Value::as_i64)
            .unwrap_or(defaults.timer_long_break_min),
        _ => prefs
            .and_then(|p| p.get("timer_break_min"))
            .and_then(Value::as_i64)
            .unwrap_or(defaults.timer_break_min),
    };
    minutes * 60_000
}

pub fn format_countdown(milliseconds: i64) -> String {
    let seconds = ((milliseconds.max(0) + 999) / 1000).max(0);
    format!("{:02}:{:02}", seconds / 60, seconds % 60)
}

pub fn remaining_ms(state: &Map<String, Value>, now_ms: i64) -> i64 {
    if state.get("running").and_then(Value::as_bool) == Some(true) {
        return (state.get("endsAt").and_then(Value::as_i64).unwrap_or(0) - now_ms).max(0);
    }
    state
        .get("remainingMs")
        .and_then(Value::as_i64)
        .unwrap_or(0)
        .max(0)
}

pub fn focus_now(state: Option<&Map<String, Value>>) -> &'static str {
    let Some(state) = state else {
        return "";
    };
    let phase = state.get("phase").and_then(Value::as_str);
    if phase.is_none() || phase == Some("ended") {
        return "";
    }
    if phase != Some("work") {
        return "break";
    }
    if state.get("running").and_then(Value::as_bool) == Some(true) {
        "focusing"
    } else {
        "paused"
    }
}

pub fn more_time_choices(estimate_min: i64) -> Vec<i64> {
    MORE_TIME_CHOICES
        .iter()
        .copied()
        .filter(|minutes| estimate_min + minutes <= MAX_ESTIMATE_MIN)
        .collect()
}

pub fn persist_payload(state: Option<&Map<String, Value>>) -> Option<Value> {
    let state = state?;
    let running = state.get("running").and_then(Value::as_bool).unwrap_or(false);
    Some(json!({
        "assignmentId": state.get("assignmentId"),
        "sessionId": state.get("blockId"),
        "weekStart": state.get("weekStart"),
        "day": state.get("day"),
        "start": state.get("start"),
        "phase": state.get("phase"),
        "cycles": state.get("cycles").and_then(Value::as_i64).unwrap_or(0),
        "endsAt": if running { state.get("endsAt").cloned().unwrap_or(Value::Null) } else { Value::Null },
        "remainingMs": if running { Value::Null } else { state.get("remainingMs").cloned().unwrap_or(Value::Null) },
    }))
}

pub fn restore_state(
    saved: Option<&Value>,
    assignments: &Map<String, Value>,
    blocks: &[Value],
    now_ms: i64,
) -> Option<Map<String, Value>> {
    let saved = saved?.as_object()?;
    let phase = saved.get("phase").and_then(Value::as_str)?;
    if !FOCUS_PHASES.contains(&phase) {
        return None;
    }
    let week_start = saved.get("weekStart").and_then(Value::as_str)?;
    if !is_week_start(week_start) {
        return None;
    }
    let cycles = saved.get("cycles").and_then(Value::as_i64)?;
    let has_end = saved.get("endsAt").and_then(Value::as_f64).is_some()
        || saved.get("endsAt").and_then(Value::as_i64).is_some();
    let has_remaining = saved.get("remainingMs").and_then(Value::as_f64).is_some()
        || saved.get("remainingMs").and_then(Value::as_i64).is_some();
    if !has_end && !has_remaining {
        return None;
    }
    let assignment_id = saved
        .get("assignmentId")
        .and_then(Value::as_str)
        .map(str::to_string);
    let assignment = assignment_id
        .as_ref()
        .and_then(|id| assignments.get(id));
    if assignment_id.is_some()
        && (assignment.is_none()
            || assignment.and_then(|a| a.get("completed")).and_then(Value::as_bool) == Some(true))
    {
        return None;
    }
    let block_id = saved
        .get("sessionId")
        .and_then(Value::as_str)
        .map(str::to_string);
    let block = block_id
        .as_ref()
        .and_then(|id| blocks.iter().find(|b| b.get("id").and_then(Value::as_str) == Some(id.as_str())));
    let running = saved.get("endsAt").and_then(Value::as_f64).is_some()
        || saved.get("endsAt").and_then(Value::as_i64).is_some();
    let mut title = "Quick focus".to_string();
    if block_id.is_some() {
        title = assignment
            .or(block)
            .and_then(|v| v.get("title"))
            .and_then(Value::as_str)
            .unwrap_or("Focus session")
            .to_string();
    }
    let mut state = Map::new();
    state.insert("weekStart".into(), json!(week_start));
    state.insert("blockId".into(), json!(block_id));
    state.insert(
        "assignmentId".into(),
        json!(assignment.and_then(|a| a.get("id").cloned()).unwrap_or(Value::Null)),
    );
    state.insert("day".into(), saved.get("day").cloned().unwrap_or(Value::Null));
    state.insert(
        "start".into(),
        saved.get("start").cloned().unwrap_or(Value::Null),
    );
    state.insert("title".into(), json!(title));
    state.insert("phase".into(), json!(phase));
    state.insert("cycles".into(), json!(cycles));
    state.insert("running".into(), json!(running));
    state.insert(
        "endsAt".into(),
        json!(saved.get("endsAt").and_then(Value::as_i64).unwrap_or(0)),
    );
    state.insert(
        "remainingMs".into(),
        json!(saved.get("remainingMs").and_then(Value::as_i64).unwrap_or(0)),
    );
    if running && state.get("endsAt").and_then(Value::as_i64).unwrap_or(0) <= now_ms {
        state.insert("running".into(), json!(false));
        state.insert("remainingMs".into(), json!(0));
        state.insert("expired".into(), json!(true));
    }
    Some(state)
}

pub fn begin_state(target: Map<String, Value>, prefs: Option<&Map<String, Value>>, now_ms: i64) -> Map<String, Value> {
    let duration = phase_duration_ms("work", prefs);
    let mut state = target;
    state.insert("phase".into(), json!("work"));
    state.insert("cycles".into(), json!(0));
    state.insert("running".into(), json!(true));
    state.insert("remainingMs".into(), json!(duration));
    state.insert("endsAt".into(), json!(now_ms + duration));
    state
}

pub fn pause_state(state: &Map<String, Value>, now_ms: i64) -> Map<String, Value> {
    let mut next = state.clone();
    if next.get("phase").and_then(Value::as_str) == Some("ended") {
        return next;
    }
    if next.get("running").and_then(Value::as_bool) == Some(true) {
        next.insert("remainingMs".into(), json!(remaining_ms(&next, now_ms)));
        next.insert("running".into(), json!(false));
    } else {
        next.insert("running".into(), json!(true));
        next.insert(
            "endsAt".into(),
            json!(now_ms + next.get("remainingMs").and_then(Value::as_i64).unwrap_or(0)),
        );
    }
    next
}

pub fn set_phase(
    state: &Map<String, Value>,
    phase: &str,
    prefs: Option<&Map<String, Value>>,
    now_ms: i64,
) -> Map<String, Value> {
    let duration = phase_duration_ms(phase, prefs);
    let mut next = state.clone();
    next.insert("phase".into(), json!(phase));
    next.insert("running".into(), json!(true));
    next.insert("remainingMs".into(), json!(duration));
    next.insert("endsAt".into(), json!(now_ms + duration));
    next
}

pub fn break_phase(cycles: i64, prefs: Option<&Map<String, Value>>) -> &'static str {
    let every = prefs
        .and_then(|p| p.get("timer_long_break_every"))
        .and_then(Value::as_i64)
        .unwrap_or(DefaultTimers::default().timer_long_break_every);
    if cycles > 0 && cycles % every == 0 {
        "long_break"
    } else {
        "break"
    }
}

pub fn credit_target(
    state: &Map<String, Value>,
    assignment: Option<&Value>,
    block: Option<&Value>,
    work_min: i64,
) -> Option<Value> {
    if state.get("blockId").is_none() {
        return None;
    }
    let amount = work_min.min(MAX_FOCUS_MINUTES);
    if state.get("assignmentId").is_some() {
        let assignment = assignment?;
        let mut updated = deep_copy(assignment);
        if let Some(obj) = updated.as_object_mut() {
            obj.insert(
                "focus_sessions".into(),
                json!((obj.get("focus_sessions").and_then(Value::as_i64).unwrap_or(0) + 1).min(MAX_FOCUS_SESSIONS)),
            );
            obj.insert(
                "focus_minutes".into(),
                json!((obj.get("focus_minutes").and_then(Value::as_i64).unwrap_or(0) + amount).min(MAX_FOCUS_MINUTES)),
            );
        }
        return Some(updated);
    }
    let block = block?;
    let mut updated = deep_copy(block);
    if let Some(obj) = updated.as_object_mut() {
        obj.insert(
            "focus_sessions".into(),
            json!((obj.get("focus_sessions").and_then(Value::as_i64).unwrap_or(0) + 1).min(MAX_FOCUS_SESSIONS)),
        );
        obj.insert(
            "focus_minutes".into(),
            json!((obj.get("focus_minutes").and_then(Value::as_i64).unwrap_or(0) + amount).min(MAX_FOCUS_MINUTES)),
        );
    }
    Some(updated)
}

pub fn focus_candidates(
    blocks: &[Value],
    assignments: &Map<String, Value>,
    trace: Option<&Value>,
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
    let mut result = Vec::new();
    for block in blocks {
        let work = block.get("kind").and_then(Value::as_str) == Some("flexible")
            || block.get("pomodoro_role").and_then(Value::as_str) == Some("work");
        if !work || block.get("completed").and_then(Value::as_bool) == Some(true) {
            continue;
        }
        let assignment = block
            .get("assignment_id")
            .and_then(Value::as_str)
            .and_then(|id| assignments.get(id));
        if assignment.and_then(|a| a.get("completed")).and_then(Value::as_bool) == Some(true) {
            continue;
        }
        let placement = block
            .get("id")
            .and_then(Value::as_str)
            .and_then(|id| placed.get(id))
            .cloned()
            .or_else(|| {
                if block.get("start").is_some() {
                    Some(deep_copy(block))
                } else {
                    None
                }
            });
        let Some(placement) = placement else {
            continue;
        };
        if placement.get("start").is_none() {
            continue;
        }
        let source = assignment.unwrap_or(block);
        result.push(json!({
            "id": block.get("id"),
            "title": block.get("title"),
            "day": placement.get("days").and_then(Value::as_array).and_then(|d| d.first()).cloned(),
            "start": placement.get("start"),
            "focus_sessions": source.get("focus_sessions").and_then(Value::as_i64).unwrap_or(0),
            "focus_minutes": source.get("focus_minutes").and_then(Value::as_i64).unwrap_or(0),
        }));
    }
    result
}

pub fn now_and_next(blocks: &[Value], day: i64, minute: i64) -> Map<String, Value> {
    let mut active = Vec::new();
    for block in blocks {
        if block.get("start").is_none() || block.get("completed").and_then(Value::as_bool) == Some(true) {
            continue;
        }
        if block
            .get("missed_days")
            .and_then(Value::as_array)
            .is_some_and(|m| m.iter().any(|v| v.as_i64() == Some(day)))
        {
            continue;
        }
        if !occurrence_days(block).contains(&day) {
            continue;
        }
        active.push(block.clone());
    }
    active.sort_by(|a, b| {
        hhmm_to_minutes(a.get("start").and_then(Value::as_str).unwrap_or(""))
            .unwrap_or(0)
            .cmp(
                &hhmm_to_minutes(b.get("start").and_then(Value::as_str).unwrap_or(""))
                    .unwrap_or(0),
            )
    });
    let mut current = None;
    let mut following = None;
    for block in &active {
        let start = hhmm_to_minutes(block.get("start").and_then(Value::as_str).unwrap_or(""))
            .unwrap_or(0);
        let end = start + block.get("duration_min").and_then(Value::as_i64).unwrap_or(0);
        if current.is_none() && start <= minute && minute < end {
            current = Some(block.clone());
        }
        if following.is_none() && start > minute {
            following = Some(block.clone());
        }
    }
    let mut out = Map::new();
    out.insert(
        "current".into(),
        current.unwrap_or(Value::Null),
    );
    out.insert(
        "next".into(),
        following.unwrap_or(Value::Null),
    );
    out
}

pub fn now_next_line(result: &Map<String, Value>, minute: i64) -> String {
    let mut parts = Vec::new();
    if let Some(current) = result.get("current").and_then(Value::as_object) {
        let end = hhmm_to_minutes(current.get("start").and_then(Value::as_str).unwrap_or(""))
            .unwrap_or(0)
            + current.get("duration_min").and_then(Value::as_i64).unwrap_or(0);
        parts.push(format!(
            "Now: {} · {} left",
            current.get("title").and_then(Value::as_str).unwrap_or(""),
            length_label(end - minute)
        ));
    }
    if let Some(following) = result.get("next").and_then(Value::as_object) {
        let wait = hhmm_to_minutes(following.get("start").and_then(Value::as_str).unwrap_or(""))
            .unwrap_or(0)
            - minute;
        let suffix = if result.get("current").is_some() {
            String::new()
        } else {
            format!(" (in {})", length_label(wait))
        };
        parts.push(format!(
            "Next: {} at {}{}",
            following.get("title").and_then(Value::as_str).unwrap_or(""),
            hhmm_text(following.get("start").and_then(Value::as_str).unwrap_or("00:00")),
            suffix
        ));
    }
    parts.join("  →  ")
}
