//! Rules the backend's helper functions in `app.py` used to decide in Python. Python keeps the
//! HTTP errors, the clock, the random draw and the pydantic checks; a check that has to run in
//! the middle of a rule arrives as a function the rule calls.

use flexweek_engine::plan;
use flexweek_engine::snapshot::canonical;
use flexweek_engine::stored;
use flexweek_engine::{EngineError, EngineResult, ErrorKind};
use serde_json::{Value, json};

use crate::{StoreError, digest};

/// Either the rule failed, or the function it called did, and that failure goes back untouched.
pub enum Relay<E> {
    Store(StoreError),
    Caller(E),
}

impl<E> From<StoreError> for Relay<E> {
    fn from(error: StoreError) -> Self {
        Self::Store(error)
    }
}

impl<E> From<EngineError> for Relay<E> {
    fn from(error: EngineError) -> Self {
        Self::Store(StoreError::Engine(error))
    }
}

fn type_error(message: String) -> EngineError {
    EngineError {
        kind: ErrorKind::Type,
        message,
    }
}

/// SHA-256 of the canonical text of `value`: what the operation ledger compares payloads by.
pub fn payload_digest(value: &Value) -> String {
    digest(&canonical(value))
}

/// An assignment as the list shows it: the stored body, then the revision and the minutes
/// still unplanned. A key the body already has keeps its place.
pub fn assignment_view(body: &Value, revision: i64, planned: i64) -> EngineResult<Value> {
    let Value::Object(fields) = body else {
        return Err(type_error(format!(
            "'{}' object is not a mapping",
            stored::type_name(body)
        )));
    };
    let estimate = stored::py_int(stored::item(fields, "estimate_min")?)?;
    let focus = stored::py_int(stored::item(fields, "focus_minutes")?)?;
    let mut view = fields.clone();
    view.insert("revision".into(), json!(revision));
    view.insert("planned_min".into(), json!(planned));
    view.insert(
        "unplanned_min".into(),
        json!(plan::unplanned_minutes(estimate, focus, planned)),
    );
    Ok(Value::Object(view))
}

fn assignment_of<'a>(assignments: &'a Value, id: &str) -> EngineResult<&'a Value> {
    assignments
        .get(id)
        .ok_or_else(|| EngineError::key(id.to_string()))
}

/// Every block that names an assignment takes that assignment's title, priority and the rest.
pub fn rewrite_blocks(blocks: &Value, assignments: &Value) -> EngineResult<Vec<Value>> {
    let Value::Array(items) = blocks else {
        return Err(type_error(format!(
            "'{}' object is not iterable",
            stored::type_name(blocks)
        )));
    };
    let mut rewritten = Vec::with_capacity(items.len());
    for block in items {
        let named = block
            .get("assignment_id")
            .filter(|id| stored::truthy(Some(id)));
        match named {
            Some(id) => {
                let assignment = assignment_of(assignments, &stored::py_str(id))?;
                rewritten.push(plan::rewrite_session(block, assignment));
            }
            None => rewritten.push(block.clone()),
        }
    }
    Ok(rewritten)
}

fn membership(id: &Value, assignments: &Value) -> EngineResult<bool> {
    match id {
        Value::String(text) => Ok(assignments.get(text.as_str()).is_some()),
        Value::Array(_) | Value::Object(_) => Err(type_error(format!(
            "unhashable type: '{}'",
            stored::type_name(id)
        ))),
        _ => Ok(false),
    }
}

/// Stored blocks that name one of `assignments` take its fields. `normalize` is the pydantic
/// pass: it reads a block and hands back the block with every default filled in.
pub fn rewrite_stored_blocks<E>(
    blocks: &Value,
    assignments: &Value,
    mut normalize: impl FnMut(&Value) -> Result<Value, E>,
) -> Result<Vec<Value>, Relay<E>> {
    let items: Vec<Value> = match blocks {
        Value::Array(items) => items.clone(),
        other => stored::rows(other)?
            .into_iter()
            .map(Value::Object)
            .collect(),
    };
    let mut rewritten = Vec::with_capacity(items.len());
    for raw in items {
        let row = stored::dict(&raw)?;
        let named = row
            .get("assignment_id")
            .filter(|id| stored::truthy(Some(id)));
        let Some(id) = named else {
            rewritten.push(raw);
            continue;
        };
        if !membership(id, assignments)? {
            rewritten.push(raw);
            continue;
        }
        let block = normalize(&raw).map_err(Relay::Caller)?;
        let assignment = assignment_of(assignments, &stored::py_str(id))?;
        let swapped = plan::rewrite_session(&block, assignment);
        rewritten.push(normalize(&swapped).map_err(Relay::Caller)?);
    }
    Ok(rewritten)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn text(value: &str) -> Value {
        serde_json::from_str(value).unwrap()
    }

    #[test]
    fn payload_digest_hashes_the_canonical_text() {
        // hashlib.sha256(b'{"a":[true,null],"b":1}').hexdigest()
        assert_eq!(
            payload_digest(&text(r#"{"b": 1, "a": [true, null]}"#)),
            "51705a2c9eb3e7e410a58f696a770c3ac3885a0cf43eb7fc88f5e47c11d4d30d"
        );
    }

    #[test]
    fn assignment_view_keeps_a_key_the_body_has_in_place() {
        // {**body, "revision": 3, "planned_min": 45, "unplanned_min": max(0, 90 - 30 - 45)}
        let body = text(r#"{"id": "a", "estimate_min": 90, "focus_minutes": 30, "revision": 9}"#);
        assert_eq!(
            assignment_view(&body, 3, 45).unwrap().to_string(),
            r#"{"id":"a","estimate_min":90,"focus_minutes":30,"revision":3,"planned_min":45,"unplanned_min":15}"#
        );
        let done = text(r#"{"estimate_min": 30, "focus_minutes": 60}"#);
        assert_eq!(
            assignment_view(&done, 1, 0).unwrap().to_string(),
            r#"{"estimate_min":30,"focus_minutes":60,"revision":1,"planned_min":0,"unplanned_min":0}"#
        );
    }

    #[test]
    fn assignment_view_raises_what_python_raised() {
        let missing = assignment_view(&text(r#"{"focus_minutes": 1}"#), 1, 0).unwrap_err();
        assert_eq!(
            (missing.kind, missing.message.as_str()),
            (ErrorKind::Key, "estimate_min")
        );
        let none = assignment_view(&text(r#"{"estimate_min": null, "focus_minutes": 1}"#), 1, 0)
            .unwrap_err();
        assert_eq!(none.kind, ErrorKind::Type);
        assert_eq!(
            none.message,
            "int() argument must be a string, a bytes-like object or a real number, not 'NoneType'"
        );
        let list = assignment_view(&text("[1]"), 1, 0).unwrap_err();
        assert_eq!(list.message, "'list' object is not a mapping");
    }

    const ASSIGNMENTS: &str = r#"{"a": {"title": "New", "priority": 1, "energy": "low", "course": null,
        "category": "c", "spotify_url": null}}"#;

    #[test]
    fn rewrite_blocks_changes_only_blocks_that_name_an_assignment() {
        let blocks = text(
            r#"[{"id": "s1", "assignment_id": "a", "title": "Old"},
                {"id": "s2", "assignment_id": null, "title": "Keep"},
                {"id": "s3", "assignment_id": "", "title": "Keep too"}]"#,
        );
        let out = rewrite_blocks(&blocks, &text(ASSIGNMENTS)).unwrap();
        assert_eq!(
            Value::Array(out).to_string(),
            r#"[{"id":"s1","assignment_id":"a","title":"New","priority":1,"energy":"low","course":null,"category":"c","spotify_url":null},{"id":"s2","assignment_id":null,"title":"Keep"},{"id":"s3","assignment_id":"","title":"Keep too"}]"#
        );
    }

    #[test]
    fn rewrite_blocks_names_the_assignment_it_cannot_find() {
        let blocks = text(r#"[{"id": "s1", "assignment_id": "zz"}]"#);
        let error = rewrite_blocks(&blocks, &text(ASSIGNMENTS)).unwrap_err();
        assert_eq!((error.kind, error.message.as_str()), (ErrorKind::Key, "zz"));
    }

    fn pad(block: &Value) -> Result<Value, String> {
        let mut block = block.clone();
        block
            .as_object_mut()
            .unwrap()
            .entry("pad")
            .or_insert(json!(0));
        Ok(block)
    }

    #[test]
    fn rewrite_stored_blocks_normalizes_a_rewritten_block_before_and_after() {
        let blocks = text(
            r#"[{"id": "s1", "assignment_id": "a", "title": "Old"},
                {"id": "s2", "assignment_id": "zz"},
                {"id": "s3"},
                {"id": "s4", "assignment_id": 7}]"#,
        );
        let mut calls = 0;
        let out = rewrite_stored_blocks(&blocks, &text(ASSIGNMENTS), |block| {
            calls += 1;
            pad(block)
        })
        .ok()
        .unwrap();
        assert_eq!(calls, 2);
        assert_eq!(
            Value::Array(out).to_string(),
            r#"[{"id":"s1","assignment_id":"a","title":"New","pad":0,"priority":1,"energy":"low","course":null,"category":"c","spotify_url":null},{"id":"s2","assignment_id":"zz"},{"id":"s3"},{"id":"s4","assignment_id":7}]"#
        );
    }

    #[test]
    fn rewrite_stored_blocks_gives_back_the_callers_failure_and_python_type_errors() {
        let blocks = text(r#"[{"id": "s1", "assignment_id": "a"}]"#);
        let failed = rewrite_stored_blocks(&blocks, &text(ASSIGNMENTS), |_| Err::<Value, _>("no"));
        assert!(matches!(failed, Err(Relay::Caller("no"))));
        let unhashable = text(r#"[{"id": "s1", "assignment_id": [1]}]"#);
        match rewrite_stored_blocks(&unhashable, &text(ASSIGNMENTS), pad) {
            Err(Relay::Store(StoreError::Engine(error))) => {
                assert_eq!(error.message, "unhashable type: 'list'");
            }
            _ => panic!("a list id must be an unhashable-type error"),
        }
        match rewrite_stored_blocks(&text(r#"["x"]"#), &text(ASSIGNMENTS), pad) {
            Err(Relay::Store(StoreError::Engine(error))) => {
                assert_eq!(error.message, "'str' object has no attribute 'get'");
            }
            _ => panic!("a block that is not a dict must fail on .get"),
        }
    }
}
