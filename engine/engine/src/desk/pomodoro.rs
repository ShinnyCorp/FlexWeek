//! Pomodoro splitting from `desktop/native/pomodoro.py`, on the values as the Python code held
//! them, so a wrong kind of value raises what Python raised.

use serde_json::{Value, json};

use crate::desk::pyops::{
    PyDict, add, eq, first_of, get, hhmm_of, int_json, iterate, length, or_default, slice_chars,
    to_int,
};
use crate::desk::pyval::{list_of, subscript};
use crate::error::{EngineError, EngineResult};
use crate::stored::{py_str, text, truthy};
use crate::time::{DAY_END_MIN, SLOT_MIN, hhmm_to_minutes};

pub const TITLE_MAX: i64 = 80;
pub const MAX_BLOCKS: i128 = 100;
pub const BREAK_TITLE: &str = "Pomodoro break";
pub const GRID_REFUSAL: &str = "Grid splitting needs positive 15-minute work and break lengths.";

fn null() -> &'static Value {
    static NULL: Value = Value::Null;
    &NULL
}

/// `int(settings.get(key) or default)`.
fn setting(settings: &Value, key: &str, default: i128) -> EngineResult<i128> {
    match get(settings, key)? {
        Some(value) if truthy(Some(value)) => to_int(value),
        _ => Ok(default),
    }
}

pub fn timers(prefs: &Value) -> EngineResult<(i128, i128, i128, i128)> {
    let settings = or_default(Some(prefs), json!({}));
    Ok((
        setting(&settings, "timer_work_min", 30)?,
        setting(&settings, "timer_break_min", 15)?,
        setting(&settings, "timer_long_break_min", 30)?,
        setting(&settings, "timer_long_break_every", 4)?.clamp(2, 12),
    ))
}

/// `split_plan` from the backend: chunks and the breaks between them.
fn split_plan(
    duration: i128,
    work: i128,
    rest: i128,
    long_rest: i128,
    cadence: i128,
) -> EngineResult<(Vec<Value>, i128)> {
    let mut remaining = duration;
    let mut index = 0i128;
    let mut segments = Vec::new();
    let mut total = 0i128;
    while remaining > 0 {
        index += 1;
        let span = work.min(remaining);
        segments.push(
            json!({"role": "work", "duration_min": int_json(span), "index": int_json(index)}),
        );
        total += span;
        remaining -= span;
        if remaining > 0 {
            if cadence == 0 {
                return Err(EngineError::zero_division("integer modulo by zero"));
            }
            let length = if index % cadence == 0 {
                long_rest
            } else {
                rest
            };
            segments.push(json!({"role": "break", "duration_min": int_json(length), "index": int_json(index)}));
            total += length;
        }
    }
    Ok((segments, total))
}

pub fn plan_for(duration_min: i64, prefs: &Value) -> EngineResult<Value> {
    let (work, rest, long_rest, cadence) = timers(prefs)?;
    let duration = i128::from(duration_min);
    let slot = i128::from(SLOT_MIN);
    if [duration, work, rest, long_rest]
        .iter()
        .any(|value| *value <= 0 || value % slot != 0)
    {
        return Ok(json!({"error": GRID_REFUSAL, "segments": [], "total_min": 0}));
    }
    let (segments, total) = split_plan(duration, work, rest, long_rest, cadence)?;
    Ok(json!({"error": null, "segments": segments, "total_min": int_json(total)}))
}

pub fn child_title(title: &str, index: i64, total: i64) -> String {
    let suffix = format!(" · focus {index}/{total}");
    let room = TITLE_MAX - suffix.chars().count() as i64;
    let held = title.chars().count() as i64;
    let head = if held > room {
        slice_chars(title, None, Some(room))
    } else {
        title.to_string()
    };
    format!("{head}{suffix}")
}

pub fn split_children(
    source: &Value,
    placed: &Value,
    plan: &Value,
    mut next_id: impl FnMut() -> String,
) -> EngineResult<Vec<Value>> {
    let own = get(source, "pomodoro_parent_id")?
        .cloned()
        .unwrap_or(Value::Null);
    let parent_id = if truthy(Some(&own)) {
        own
    } else {
        subscript(source, "id")?.clone()
    };
    let mut cursor = Value::from(hhmm_to_minutes(text(
        subscript(placed, "start")?,
        "split",
    )?)?);
    let mut total_work = 0usize;
    for segment in iterate(subscript(plan, "segments")?)? {
        if eq(subscript(&segment, "role")?, &json!("work")) {
            total_work += 1;
        }
    }
    let mut first_work = true;
    let mut children = Vec::new();
    for segment in iterate(subscript(plan, "segments")?)? {
        let work = eq(subscript(&segment, "role")?, &json!("work"));
        let carry = work && first_work;
        let mut child = match source {
            Value::Object(fields) => fields.clone(),
            other => return Err(crate::stored::attribute_error(other, "update")),
        };
        child.insert("id".into(), json!(next_id()));
        let title = if work {
            let index = subscript(&segment, "index")?;
            json!(child_title_of(
                subscript(source, "title")?,
                index,
                total_work
            )?)
        } else {
            json!(BREAK_TITLE)
        };
        child.insert("title".into(), title);
        child.insert("kind".into(), json!("locked"));
        child.insert(
            "days".into(),
            json!([first_of(subscript(placed, "days")?)?]),
        );
        child.insert("start".into(), json!(hhmm_of(&cursor)?));
        child.insert(
            "duration_min".into(),
            subscript(&segment, "duration_min")?.clone(),
        );
        child.insert("completed".into(), json!(false));
        child.insert("missed_days".into(), json!([]));
        let kept = |name: &str| -> EngineResult<Value> {
            Ok(if carry {
                or_default(get(source, name)?, json!(0))
            } else {
                json!(0)
            })
        };
        child.insert("focus_sessions".into(), kept("focus_sessions")?);
        child.insert("focus_minutes".into(), kept("focus_minutes")?);
        child.insert("pomodoro_parent_id".into(), parent_id.clone());
        child.insert("pomodoro_role".into(), subscript(&segment, "role")?.clone());
        child.insert(
            "pomodoro_index".into(),
            subscript(&segment, "index")?.clone(),
        );
        let from_source = |name: &str| -> EngineResult<Value> {
            Ok(if work {
                get(source, name)?.cloned().unwrap_or(Value::Null)
            } else {
                Value::Null
            })
        };
        child.insert(
            "category".into(),
            if work {
                from_source("category")?
            } else {
                json!("free")
            },
        );
        child.insert("course".into(), from_source("course")?);
        child.insert("spotify_url".into(), from_source("spotify_url")?);
        child.insert("earliest".into(), Value::Null);
        child.insert("latest".into(), Value::Null);
        if truthy(get(source, "assignment_id")?) {
            child.insert("focus_sessions".into(), json!(0));
            child.insert("focus_minutes".into(), json!(0));
            if !work {
                child.shift_remove("assignment_id");
            }
        }
        child.shift_remove("completed_day");
        if work {
            first_work = false;
        }
        cursor = add(&cursor, subscript(&segment, "duration_min")?)?;
        children.push(Value::Object(child));
    }
    Ok(children)
}

/// `child_title(source["title"], segment["index"], total_work)` with the index as held.
fn child_title_of(title: &Value, index: &Value, total: usize) -> EngineResult<String> {
    let suffix = format!(" · focus {}/{total}", py_str(index));
    let room = TITLE_MAX - suffix.chars().count() as i64;
    let held = py_str(title);
    let head = if held.chars().count() as i64 > room {
        slice_chars(&held, None, Some(room))
    } else {
        held
    };
    Ok(format!("{head}{suffix}"))
}

pub fn splittable(block: &Value, prefs: &Value) -> EngineResult<bool> {
    let work = timers(prefs)?.0;
    if !eq(get(block, "kind")?.unwrap_or(null()), &json!("flexible")) {
        return Ok(false);
    }
    if truthy(get(block, "completed")?) || truthy(get(block, "pomodoro_role")?) {
        return Ok(false);
    }
    Ok(to_int(&or_default(get(block, "duration_min")?, json!(0)))? > work)
}

fn auto_split(prefs: &Value) -> EngineResult<bool> {
    let source = or_default(Some(prefs), json!({}));
    Ok(truthy(get(&source, "auto_split_pomodoro")?))
}

pub fn inflate_for_solve(blocks: &Value, prefs: &Value) -> EngineResult<Value> {
    if !auto_split(prefs)? {
        return Ok(blocks.clone());
    }
    let mut inflated = Vec::new();
    for block in iterate(blocks)? {
        let plan = if splittable(&block, prefs)? {
            let minutes = to_int(&or_default(get(&block, "duration_min")?, json!(0)))?;
            Some(plan_for(
                i64::try_from(minutes).map_err(|_| {
                    EngineError::overflow("Python int too large to convert to C long")
                })?,
                prefs,
            )?)
        } else {
            None
        };
        match plan {
            Some(plan) if !truthy(Some(subscript(&plan, "error")?)) => {
                let mut changed = match &block {
                    Value::Object(fields) => fields.clone(),
                    other => {
                        return Err(crate::desk::pyval::type_error(format!(
                            "'{}' object is not a mapping",
                            crate::stored::type_name(other)
                        )));
                    }
                };
                changed.insert(
                    "duration_min".into(),
                    int_json(to_int(subscript(&plan, "total_min")?)?),
                );
                inflated.push(Value::Object(changed));
            }
            _ => inflated.push(block),
        }
    }
    Ok(Value::Array(inflated))
}

pub fn split_solved(
    blocks: &Value,
    trace: &Value,
    prefs: &Value,
    mut next_id: impl FnMut() -> String,
) -> EngineResult<(Value, i64)> {
    if !auto_split(prefs)? || !truthy(Some(trace)) {
        return Ok((blocks.clone(), 0));
    }
    let mut placements = PyDict::new();
    for item in iterate(&or_default(get(trace, "placed")?, json!([])))? {
        if truthy(get(&item, "start")?) {
            placements.set(subscript(&item, "id")?.clone(), item.clone())?;
        }
    }
    let mut replacements = PyDict::new();
    let mut final_count = length(blocks)? as i128;
    for source in iterate(blocks)? {
        let found = placements.get(subscript(&source, "id")?)?.cloned();
        let Some(placed) = found else { continue };
        if !splittable(&source, prefs)? {
            continue;
        }
        let minutes = to_int(&or_default(get(&source, "duration_min")?, json!(0)))?;
        let plan = plan_for(
            i64::try_from(minutes)
                .map_err(|_| EngineError::overflow("Python int too large to convert to C long"))?,
            prefs,
        )?;
        if truthy(Some(subscript(&plan, "error")?)) || !truthy(Some(subscript(&plan, "segments")?))
        {
            continue;
        }
        let start = hhmm_to_minutes(text(subscript(&placed, "start")?, "split")?)?;
        if i128::from(start) + to_int(subscript(&plan, "total_min")?)? > i128::from(DAY_END_MIN) {
            continue;
        }
        let children = split_children(&source, &placed, &plan, &mut next_id)?;
        final_count += children.len() as i128 - 1;
        replacements.set(subscript(&source, "id")?.clone(), Value::Array(children))?;
    }
    if replacements.is_empty() || final_count > MAX_BLOCKS {
        return Ok((blocks.clone(), 0));
    }
    let mut split = Vec::new();
    for block in iterate(blocks)? {
        match replacements.get(subscript(&block, "id")?)? {
            Some(children) => split.extend(list_of(children)?),
            None => split.push(block.clone()),
        }
    }
    Ok((Value::Array(split), replacements.len() as i64))
}
