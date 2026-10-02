//! Undo/redo snapshots from `desktop/native/history.py`.

use serde_json::{Map, Value, json};

use crate::desk::pyops::{PyDict, eq, get, iterate, or_default};
use crate::desk::pyval::subscript;
use crate::error::EngineResult;

pub const HISTORY_LIMIT: usize = 50;

/// `len(stack) > HISTORY_LIMIT`: one step is dropped from the front when a push leaves it longer.
pub fn over_limit(length: usize) -> bool {
    length > HISTORY_LIMIT
}

fn sort_value(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut keys: Vec<_> = map.keys().cloned().collect();
            keys.sort();
            let mut out = Map::new();
            for key in keys {
                out.insert(key.clone(), sort_value(&map[&key]));
            }
            Value::Object(out)
        }
        Value::Array(items) => Value::Array(items.iter().map(sort_value).collect()),
        other => other.clone(),
    }
}

pub fn same_value(left: &Value, right: &Value) -> bool {
    sort_value(left) == sort_value(right)
}

pub fn capture_step(
    label: &str,
    week_start: &str,
    before_blocks: &Value,
    after_blocks: &Value,
    before_assignments: &Value,
    after_assignments: &Value,
    changed_ids: &[String],
) -> EngineResult<Option<Value>> {
    let mut weeks = Vec::new();
    let mut assignments = Vec::new();
    if !same_value(before_blocks, after_blocks) {
        weeks.push(json!({
            "week_start": week_start,
            "before": before_blocks,
            "after": after_blocks,
        }));
    }
    for item_id in changed_ids {
        let prior = get(before_assignments, item_id)?
            .cloned()
            .unwrap_or(Value::Null);
        let after = get(after_assignments, item_id)?
            .cloned()
            .unwrap_or(Value::Null);
        if same_value(&prior, &after) {
            continue;
        }
        assignments.push(json!({"id": item_id, "before": prior, "after": after}));
    }
    if weeks.is_empty() && assignments.is_empty() {
        return Ok(None);
    }
    Ok(Some(json!({
        "label": label,
        "weeks": weeks,
        "assignments": assignments,
        "stale": false,
    })))
}

/// `{entry[key]: dict(entry) ...}` folded with a later step's entries: each key keeps the earlier
/// `before` and the later entry otherwise.
fn merged(earlier: &Value, step: &Value, list: &str, key: &str) -> EngineResult<Vec<Value>> {
    let mut table = PyDict::new();
    for entry in iterate(subscript(earlier, list)?)? {
        let name = subscript(&entry, key)?.clone();
        table.set(name, Value::Object(crate::desk::pyops::py_dict(&entry)?))?;
    }
    for entry in iterate(subscript(step, list)?)? {
        let name = subscript(&entry, key)?.clone();
        let known = table.get(&name)?.cloned();
        let value = match known {
            Some(known) if crate::stored::truthy(Some(&known)) => {
                let mut combined = crate::desk::pyops::py_dict(&entry)?;
                combined.insert("before".into(), subscript(&known, "before")?.clone());
                Value::Object(combined)
            }
            _ => Value::Object(crate::desk::pyops::py_dict(&entry)?),
        };
        table.set(name, value)?;
    }
    Ok(table.into_values())
}

/// The last step with `step` folded into it, so one Undo takes both back.
pub fn joined_step(earlier: &Value, step: &Value) -> EngineResult<Value> {
    let weeks = merged(earlier, step, "weeks", "week_start")?;
    let assignments = merged(earlier, step, "assignments", "id")?;
    let mut out = crate::desk::pyops::py_dict(earlier)?;
    out.insert("weeks".into(), Value::Array(weeks));
    out.insert("assignments".into(), Value::Array(assignments));
    Ok(Value::Object(out))
}

/// Whether `step` holds a week of `week_start`, which a reload of that week makes stale.
pub fn touches(step: &Value, week_start: &Value) -> EngineResult<bool> {
    let weeks = or_default(get(step, "weeks")?, json!([]));
    for entry in iterate(&weeks)? {
        if eq(subscript(&entry, "week_start")?, week_start) {
            return Ok(true);
        }
    }
    Ok(false)
}
