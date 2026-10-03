//! Undo/redo snapshots from `desktop/native/history.py`.

use serde_json::{Map, Value, json};

use crate::desk::pyops::{PyDict, eq, get, iterate, or_default};
use crate::desk::pyval::subscript;
use crate::error::{EngineError, EngineResult};
use crate::stored::truthy;

pub const HISTORY_LIMIT: usize = 50;

/// `len(stack) > HISTORY_LIMIT`: one step is dropped from the front when a push leaves it longer.
pub fn over_limit(length: usize) -> bool {
    length > HISTORY_LIMIT
}

/// The caller retains its objects; append and removal happen in Python's original order.
pub fn push_step<T, E>(
    step: T,
    append: impl FnOnce(T) -> Result<(), E>,
    length: impl FnOnce() -> Result<usize, E>,
    remove_oldest: impl FnOnce() -> Result<(), E>,
) -> Result<(), E> {
    append(step)?;
    if over_limit(length()?) {
        remove_oldest()?;
    }
    Ok(())
}

/// Read each JSON snapshot only when reached, so later errors preserve earlier updates.
pub fn mark_stale<H, E>(
    items: impl IntoIterator<Item = Result<(Value, Value, H), E>>,
    mut mark: impl FnMut(H) -> Result<(), E>,
    mut map_error: impl FnMut(EngineError) -> E,
) -> Result<(), E> {
    for item in items {
        let (step, week_start, handle) = item?;
        if touches(&step, &week_start).map_err(&mut map_error)? {
            mark(handle)?;
        }
    }
    Ok(())
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
    let mut changed_ids = changed_ids.to_vec();
    changed_ids.sort();
    let mut weeks = Vec::new();
    let mut assignments = Vec::new();
    if !same_value(before_blocks, after_blocks) {
        weeks.push(json!({
            "week_start": week_start,
            "before": before_blocks,
            "after": after_blocks,
        }));
    }
    for item_id in &changed_ids {
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
            Some(known) if truthy(Some(&known)) => {
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

/// What `join_step` does with the newest step: fold `step` into it, or `None` when it is stale and
/// `step` is pushed after it instead.
pub fn join_into(newest: &Value, step: &Value) -> EngineResult<Option<Value>> {
    if truthy(get(newest, "stale")?) {
        return Ok(None);
    }
    joined_step(newest, step).map(Some)
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;

    #[test]
    fn pushed_steps_drop_only_the_oldest_at_the_limit() {
        let stack = RefCell::new((0..HISTORY_LIMIT).map(|at| json!(at)).collect::<Vec<_>>());
        push_step(
            json!(50),
            |step| {
                stack.borrow_mut().push(step);
                Ok::<_, EngineError>(())
            },
            || Ok(stack.borrow().len()),
            || {
                stack.borrow_mut().remove(0);
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(stack.borrow().len(), 50);
        assert_eq!(stack.borrow()[0], json!(1));
        assert_eq!(stack.borrow()[49], json!(50));
    }

    #[test]
    fn stale_marking_preserves_updates_before_a_later_error() {
        let marked = RefCell::new(Vec::new());
        let items = [
            Ok((json!({"weeks": [{"week_start": "w"}]}), json!("w"), 0)),
            Ok((json!({"weeks": [{}]}), json!("w"), 1)),
            Ok((json!({"weeks": [{"week_start": "w"}]}), json!("w"), 2)),
        ];
        let error = mark_stale(
            items,
            |at| {
                marked.borrow_mut().push(at);
                Ok(())
            },
            |error| error,
        )
        .unwrap_err();
        assert_eq!(error, EngineError::key("week_start"));
        assert_eq!(*marked.borrow(), [0]);
    }

    fn step(week_start: &str, before: Value, after: Value, stale: bool) -> Value {
        json!({
            "label": week_start,
            "weeks": [{"week_start": week_start, "before": before, "after": after}],
            "assignments": [],
            "stale": stale,
        })
    }

    #[test]
    fn assignments_are_listed_in_sorted_id_order() {
        let before = json!({"b": {"title": "old"}, "a": {"title": "old"}});
        let after = json!({"b": {"title": "new"}, "a": {"title": "new"}});
        let ids = ["b".to_string(), "a".to_string()];
        let made = capture_step("x", "w", &json!([]), &json!([]), &before, &after, &ids)
            .unwrap()
            .unwrap();
        let listed: Vec<&str> = made["assignments"]
            .as_array()
            .unwrap()
            .iter()
            .map(|entry| entry["id"].as_str().unwrap())
            .collect();
        assert_eq!(listed, ["a", "b"]);
    }

    #[test]
    fn a_step_folds_into_the_newest_and_keeps_the_earlier_before() {
        let newest = step("w1", json!([1]), json!([2]), false);
        let later = step("w1", json!([2]), json!([3]), false);
        let joined = join_into(&newest, &later).unwrap().unwrap();
        assert_eq!(joined["label"], "w1");
        assert_eq!(
            joined["weeks"],
            json!([{"week_start": "w1", "before": [1], "after": [3]}])
        );
    }

    #[test]
    fn a_stale_newest_step_is_not_folded_into() {
        let newest = step("w1", json!([1]), json!([2]), true);
        assert_eq!(
            join_into(&newest, &step("w1", json!([2]), json!([3]), false)).unwrap(),
            None
        );
    }

    #[test]
    fn a_newest_step_that_is_not_a_dict_has_no_get() {
        let error = join_into(&json!(5), &json!({})).unwrap_err();
        assert_eq!(error.message, "'int' object has no attribute 'get'");
    }
}
