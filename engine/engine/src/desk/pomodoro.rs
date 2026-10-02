//! Pomodoro splitting from `desktop/native/pomodoro.py`.

use serde_json::{Value, json};

use crate::desk::calendar::deep_copy;
use crate::time::{DAY_END_MIN, SLOT_MIN, hhmm_to_minutes, minutes_to_hhmm};

pub const TITLE_MAX: usize = 80;
pub const MAX_BLOCKS: usize = 100;
pub const BREAK_TITLE: &str = "Pomodoro break";
pub const GRID_REFUSAL: &str = "Grid splitting needs positive 15-minute work and break lengths.";

pub fn timers(prefs: Option<&serde_json::Map<String, Value>>) -> (i64, i64, i64, i64) {
    let settings = prefs.cloned().unwrap_or_default();
    let every = settings
        .get("timer_long_break_every")
        .and_then(Value::as_i64)
        .unwrap_or(4);
    (
        settings
            .get("timer_work_min")
            .and_then(Value::as_i64)
            .unwrap_or(30),
        settings
            .get("timer_break_min")
            .and_then(Value::as_i64)
            .unwrap_or(15),
        settings
            .get("timer_long_break_min")
            .and_then(Value::as_i64)
            .unwrap_or(30),
        every.clamp(2, 12),
    )
}

pub fn split_plan(
    duration_min: i64,
    work_min: i64,
    break_min: i64,
    long_break_min: i64,
    cadence: i64,
) -> (Vec<Value>, i64) {
    let mut remaining = duration_min;
    let mut work_index = 0i64;
    let mut segments = Vec::new();
    while remaining > 0 {
        work_index += 1;
        let length = work_min.min(remaining);
        segments.push(json!({
            "role": "work",
            "duration_min": length,
            "index": work_index,
        }));
        remaining -= length;
        if remaining > 0 {
            let long = work_index % cadence == 0;
            segments.push(json!({
                "role": "break",
                "duration_min": if long { long_break_min } else { break_min },
                "index": work_index,
            }));
        }
    }
    let total_min: i64 = segments
        .iter()
        .map(|s| s.get("duration_min").and_then(Value::as_i64).unwrap_or(0))
        .sum();
    (segments, total_min)
}

pub fn plan_for(duration_min: i64, prefs: Option<&serde_json::Map<String, Value>>) -> Value {
    let (work, brk, long_break, cadence) = timers(prefs);
    let values = [duration_min, work, brk, long_break];
    if values
        .iter()
        .any(|value| *value <= 0 || *value % SLOT_MIN != 0)
    {
        return json!({"error": GRID_REFUSAL, "segments": [], "total_min": 0});
    }
    let (segments, total_min) = split_plan(duration_min, work, brk, long_break, cadence);
    json!({"error": Value::Null, "segments": segments, "total_min": total_min})
}

pub fn child_title(title: &str, index: i64, total: i64) -> String {
    let suffix = format!(" · focus {index}/{total}");
    // Python `len` counts code points. The middle dot is one character and two bytes.
    let room = TITLE_MAX.saturating_sub(suffix.chars().count());
    let head: String = title.chars().take(room).collect();
    format!("{head}{suffix}")
}

pub fn split_children(
    source: &Value,
    placed: &Value,
    plan: &Value,
    mut next_id: impl FnMut() -> String,
) -> Vec<Value> {
    let parent_id = source
        .get("pomodoro_parent_id")
        .and_then(Value::as_str)
        .or_else(|| source.get("id").and_then(Value::as_str))
        .unwrap_or("");
    let mut cursor =
        hhmm_to_minutes(placed.get("start").and_then(Value::as_str).unwrap_or("")).unwrap_or(0);
    let segments = plan
        .get("segments")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let total_work = segments
        .iter()
        .filter(|s| s.get("role").and_then(Value::as_str) == Some("work"))
        .count();
    let mut first_work = true;
    let mut children = Vec::new();
    for segment in segments {
        let work = segment.get("role").and_then(Value::as_str) == Some("work");
        let carry = work && first_work;
        let mut child = deep_copy(source);
        if let Some(obj) = child.as_object_mut() {
            obj.insert("id".into(), json!(next_id()));
            let index = segment.get("index").and_then(Value::as_i64).unwrap_or(0);
            obj.insert(
                "title".into(),
                json!(if work {
                    child_title(
                        source.get("title").and_then(Value::as_str).unwrap_or(""),
                        index,
                        total_work as i64,
                    )
                } else {
                    BREAK_TITLE.to_string()
                }),
            );
            obj.insert("kind".into(), json!("locked"));
            obj.insert(
                "days".into(),
                json!([placed
                    .get("days")
                    .and_then(Value::as_array)
                    .and_then(|d| d.first())
                    .and_then(Value::as_i64)
                    .unwrap_or(0)]),
            );
            obj.insert("start".into(), json!(minutes_to_hhmm(cursor)));
            obj.insert(
                "duration_min".into(),
                json!(
                    segment
                        .get("duration_min")
                        .and_then(Value::as_i64)
                        .unwrap_or(0)
                ),
            );
            obj.insert("completed".into(), json!(false));
            obj.insert("missed_days".into(), json!([]));
            obj.insert(
                "focus_sessions".into(),
                json!(if carry {
                    source
                        .get("focus_sessions")
                        .and_then(Value::as_i64)
                        .unwrap_or(0)
                } else {
                    0
                }),
            );
            obj.insert(
                "focus_minutes".into(),
                json!(if carry {
                    source
                        .get("focus_minutes")
                        .and_then(Value::as_i64)
                        .unwrap_or(0)
                } else {
                    0
                }),
            );
            obj.insert("pomodoro_parent_id".into(), json!(parent_id));
            obj.insert(
                "pomodoro_role".into(),
                segment.get("role").cloned().unwrap_or(Value::Null),
            );
            obj.insert("pomodoro_index".into(), json!(index));
            obj.insert(
                "category".into(),
                json!(if work {
                    source.get("category").cloned().unwrap_or(Value::Null)
                } else {
                    json!("free")
                }),
            );
            obj.insert(
                "course".into(),
                json!(if work {
                    source.get("course").cloned().unwrap_or(Value::Null)
                } else {
                    Value::Null
                }),
            );
            obj.insert(
                "spotify_url".into(),
                json!(if work {
                    source.get("spotify_url").cloned().unwrap_or(Value::Null)
                } else {
                    Value::Null
                }),
            );
            obj.insert("earliest".into(), Value::Null);
            obj.insert("latest".into(), Value::Null);
            if crate::stored::truthy(source.get("assignment_id")) {
                obj.insert("focus_sessions".into(), json!(0));
                obj.insert("focus_minutes".into(), json!(0));
                if !work {
                    obj.shift_remove("assignment_id");
                }
            }
            obj.shift_remove("completed_day");
        }
        if work {
            first_work = false;
        }
        cursor += segment
            .get("duration_min")
            .and_then(Value::as_i64)
            .unwrap_or(0);
        children.push(child);
    }
    children
}

pub fn splittable(block: &Value, prefs: Option<&serde_json::Map<String, Value>>) -> bool {
    let work = timers(prefs).0;
    block.get("kind").and_then(Value::as_str) == Some("flexible")
        && block.get("completed").and_then(Value::as_bool) != Some(true)
        && !crate::stored::truthy(block.get("pomodoro_role"))
        && block
            .get("duration_min")
            .and_then(Value::as_i64)
            .unwrap_or(0)
            > work
}

pub fn inflate_for_solve(
    blocks: &[Value],
    prefs: Option<&serde_json::Map<String, Value>>,
) -> Vec<Value> {
    if prefs
        .and_then(|p| p.get("auto_split_pomodoro"))
        .and_then(Value::as_bool)
        != Some(true)
    {
        return blocks.to_vec();
    }
    blocks
        .iter()
        .map(|block| {
            if !splittable(block, prefs) {
                return block.clone();
            }
            let plan = plan_for(
                block
                    .get("duration_min")
                    .and_then(Value::as_i64)
                    .unwrap_or(0),
                prefs,
            );
            if plan.get("error").and_then(Value::as_str).is_some() {
                return block.clone();
            }
            let mut copy = block.clone();
            if let Some(obj) = copy.as_object_mut() {
                obj.insert(
                    "duration_min".into(),
                    json!(plan.get("total_min").and_then(Value::as_i64).unwrap_or(0)),
                );
            }
            copy
        })
        .collect()
}

pub fn split_solved(
    blocks: &[Value],
    trace: Option<&Value>,
    prefs: Option<&serde_json::Map<String, Value>>,
    mut next_id: impl FnMut() -> String,
) -> (Vec<Value>, i64) {
    if prefs
        .and_then(|p| p.get("auto_split_pomodoro"))
        .and_then(Value::as_bool)
        != Some(true)
        || trace.is_none()
    {
        return (blocks.to_vec(), 0);
    }
    let trace = trace.unwrap();
    let placements: std::collections::HashMap<String, Value> = trace
        .get("placed")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter(|item| super::has_start(item))
                .filter_map(|item| Some((item.get("id")?.as_str()?.to_string(), item.clone())))
                .collect()
        })
        .unwrap_or_default();
    let mut replacements: std::collections::HashMap<String, Vec<Value>> =
        std::collections::HashMap::new();
    let mut final_count = blocks.len();
    for source in blocks {
        let Some(placed) = source
            .get("id")
            .and_then(Value::as_str)
            .and_then(|id| placements.get(id))
        else {
            continue;
        };
        if !splittable(source, prefs) {
            continue;
        }
        let plan = plan_for(
            source
                .get("duration_min")
                .and_then(Value::as_i64)
                .unwrap_or(0),
            prefs,
        );
        if plan.get("error").and_then(Value::as_str).is_some()
            || plan
                .get("segments")
                .and_then(Value::as_array)
                .is_none_or(|s| s.is_empty())
        {
            continue;
        }
        let start =
            hhmm_to_minutes(placed.get("start").and_then(Value::as_str).unwrap_or("")).unwrap_or(0);
        let total = plan.get("total_min").and_then(Value::as_i64).unwrap_or(0);
        if start + total > DAY_END_MIN {
            continue;
        }
        let children = split_children(source, placed, &plan, &mut next_id);
        final_count += children.len().saturating_sub(1);
        if let Some(id) = source.get("id").and_then(Value::as_str) {
            replacements.insert(id.to_string(), children);
        }
    }
    if replacements.is_empty() || final_count > MAX_BLOCKS {
        return (blocks.to_vec(), 0);
    }
    let mut split = Vec::new();
    for block in blocks {
        if let Some(id) = block.get("id").and_then(Value::as_str)
            && let Some(children) = replacements.get(id)
        {
            split.extend(children.clone());
            continue;
        }
        split.push(block.clone());
    }
    (split, replacements.len() as i64)
}
