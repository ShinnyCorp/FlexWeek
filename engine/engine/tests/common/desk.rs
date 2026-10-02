//! Builders shared by the Rust twins of the desktop tests (`desk_*.rs`).

use serde_json::{Map, Value};

/// A JSON object literal as a `Value`; panics if `value` is not an object, which would be a typo in a test.
pub fn object(value: Value) -> Map<String, Value> {
    match value {
        Value::Object(map) => map,
        other => panic!("expected a JSON object, got {other}"),
    }
}

/// Python's `{**base, **over}`: `over` wins key by key, and new keys go at the end.
pub fn with(base: Value, over: Value) -> Value {
    let mut merged = object(base);
    for (key, value) in object(over) {
        merged.insert(key, value);
    }
    Value::Object(merged)
}

/// Ids "id-1", "id-2", ... in place of the wrapper's `uuid4()`; no test depends on their form.
pub fn fresh_ids() -> impl FnMut() -> String {
    let mut count = 0;
    move || {
        count += 1;
        format!("id-{count}")
    }
}
