//! Undo/redo snapshots from `desktop/native/history.py`.

use serde_json::{json, Map, Value};

use crate::desk::calendar::deep_copy;

pub const HISTORY_LIMIT: usize = 50;

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
    sort_value(left).to_string() == sort_value(right).to_string()
}

pub fn capture_step(
    label: &str,
    week_start: &str,
    before_blocks: &[Value],
    after_blocks: &[Value],
    before_assignments: &Map<String, Value>,
    after_assignments: &Map<String, Value>,
    changed_ids: &std::collections::HashSet<String>,
) -> Option<Map<String, Value>> {
    let mut step = Map::new();
    step.insert("label".into(), Value::String(label.to_string()));
    step.insert("weeks".into(), Value::Array(Vec::new()));
    step.insert("assignments".into(), Value::Array(Vec::new()));
    step.insert("stale".into(), Value::Bool(false));
    if !same_value(&Value::Array(before_blocks.to_vec()), &Value::Array(after_blocks.to_vec())) {
        let mut entry = Map::new();
        entry.insert("week_start".into(), json!(week_start));
        entry.insert(
            "before".into(),
            Value::Array(before_blocks.iter().map(deep_copy).collect()),
        );
        entry.insert(
            "after".into(),
            Value::Array(after_blocks.iter().map(deep_copy).collect()),
        );
        step.get_mut("weeks")
            .and_then(Value::as_array_mut)
            .unwrap()
            .push(Value::Object(entry));
    }
    let mut ids: Vec<_> = changed_ids.iter().cloned().collect();
    ids.sort();
    for item_id in ids {
        let prior = before_assignments.get(&item_id);
        let after = after_assignments.get(&item_id);
        if same_value(
            &prior.cloned().unwrap_or(Value::Null),
            &after.cloned().unwrap_or(Value::Null),
        ) {
            continue;
        }
        let mut entry = Map::new();
        entry.insert("id".into(), json!(item_id));
        entry.insert(
            "before".into(),
            prior.map(deep_copy).unwrap_or(Value::Null),
        );
        entry.insert(
            "after".into(),
            after.map(deep_copy).unwrap_or(Value::Null),
        );
        step.get_mut("assignments")
            .and_then(Value::as_array_mut)
            .unwrap()
            .push(Value::Object(entry));
    }
    let weeks = step.get("weeks").and_then(Value::as_array).cloned().unwrap_or_default();
    let assignments = step
        .get("assignments")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    if weeks.is_empty() && assignments.is_empty() {
        return None;
    }
    Some(step)
}

pub fn push_step(stack: &mut Vec<Map<String, Value>>, step: Map<String, Value>) {
    stack.push(step);
    if stack.len() > HISTORY_LIMIT {
        stack.remove(0);
    }
}

pub fn join_step(stack: &mut Vec<Map<String, Value>>, step: Map<String, Value>) {
    if stack.is_empty() || stack.last().and_then(|s| s.get("stale")).and_then(Value::as_bool) == Some(true) {
        push_step(stack, step);
        return;
    }
    let earlier = stack.pop().expect("step");
    let mut weeks: std::collections::BTreeMap<String, Map<String, Value>> = earlier
        .get("weeks")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|entry| {
            let obj = entry.as_object()?;
            Some((
                obj.get("week_start")?.as_str()?.to_string(),
                obj.clone(),
            ))
        })
        .collect();
    for entry in step.get("weeks").and_then(Value::as_array).into_iter().flatten() {
        let Some(obj) = entry.as_object() else {
            continue;
        };
        let week_start = obj.get("week_start").and_then(Value::as_str).unwrap_or("");
        if let Some(known) = weeks.get(week_start) {
            let mut merged = obj.clone();
            merged.insert("before".into(), known.get("before").cloned().unwrap_or(Value::Null));
            weeks.insert(week_start.to_string(), merged);
        } else {
            weeks.insert(week_start.to_string(), obj.clone());
        }
    }
    let mut assignments: std::collections::BTreeMap<String, Map<String, Value>> = earlier
        .get("assignments")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|entry| {
            let obj = entry.as_object()?;
            Some((obj.get("id")?.as_str()?.to_string(), obj.clone()))
        })
        .collect();
    for entry in step
        .get("assignments")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let Some(obj) = entry.as_object() else {
            continue;
        };
        let id = obj.get("id").and_then(Value::as_str).unwrap_or("");
        if let Some(known) = assignments.get(id) {
            let mut merged = obj.clone();
            merged.insert("before".into(), known.get("before").cloned().unwrap_or(Value::Null));
            assignments.insert(id.to_string(), merged);
        } else {
            assignments.insert(id.to_string(), obj.clone());
        }
    }
    let mut combined = earlier;
    combined.insert(
        "weeks".into(),
        Value::Array(weeks.into_values().map(Value::Object).collect()),
    );
    combined.insert(
        "assignments".into(),
        Value::Array(assignments.into_values().map(Value::Object).collect()),
    );
    stack.push(combined);
}

pub fn mark_stale(steps: &mut [Map<String, Value>], week_start: &str) {
    for step in steps.iter_mut() {
        if step
            .get("weeks")
            .and_then(Value::as_array)
            .is_some_and(|weeks| {
                weeks.iter().any(|entry| {
                    entry.get("week_start").and_then(Value::as_str) == Some(week_start)
                })
            })
        {
            step.insert("stale".into(), Value::Bool(true));
        }
    }
}
