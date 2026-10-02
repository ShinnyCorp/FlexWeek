//! Python's own reading of a JSON value: `value[key]`, `list(value)`, dict lookups, with the
//! errors Python raised on a value of the wrong type.

use serde_json::Value;

use crate::error::{EngineError, EngineResult, ErrorKind};
use crate::stored::{Dict, type_name};

pub(crate) fn type_error(message: impl Into<String>) -> EngineError {
    EngineError {
        kind: ErrorKind::Type,
        message: message.into(),
    }
}

/// `value[key]` for a string key.
pub(crate) fn subscript<'a>(value: &'a Value, key: &str) -> EngineResult<&'a Value> {
    match value {
        Value::Object(map) => map.get(key).ok_or_else(|| EngineError::key(key)),
        Value::Array(_) => Err(type_error(
            "list indices must be integers or slices, not str",
        )),
        Value::String(_) => Err(type_error("string indices must be integers, not 'str'")),
        other => Err(type_error(format!(
            "'{}' object is not subscriptable",
            type_name(other)
        ))),
    }
}

/// `list(value)`. A string lists its characters and a dict its keys.
pub(crate) fn list_of(value: &Value) -> EngineResult<Vec<Value>> {
    match value {
        Value::Array(items) => Ok(items.clone()),
        Value::String(text) => Ok(text.chars().map(|ch| Value::from(ch.to_string())).collect()),
        Value::Object(map) => Ok(map.keys().map(|key| Value::from(key.as_str())).collect()),
        other => Err(type_error(format!(
            "'{}' object is not iterable",
            type_name(other)
        ))),
    }
}

/// What Python says of a list or dict used as a dict key (`"dict key"`) or a set element
/// (`"set element"`).
pub(crate) fn unhashable(value: &Value, place: &str) -> EngineError {
    type_error(format!(
        "cannot use '{0}' as a {place} (unhashable type: '{0}')",
        type_name(value)
    ))
}

/// `table.get(key)` where the key is any value: a string finds its entry, a number or null finds
/// none, and a list or dict cannot be a key.
pub(crate) fn lookup<'a>(table: &'a Dict, key: &Value) -> EngineResult<Option<&'a Value>> {
    match key {
        Value::String(name) => Ok(table.get(name)),
        Value::Array(_) | Value::Object(_) => {
            Err(type_error(format!("unhashable type: '{}'", type_name(key))))
        }
        _ => Ok(None),
    }
}
