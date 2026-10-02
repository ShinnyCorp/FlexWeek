pub mod calendar;
mod cmath;
pub mod custom_look;
pub mod files;
pub mod focus;
pub mod history;
pub mod pomodoro;
pub mod remind;
pub mod reuse;
pub mod tokens;
pub mod update;
pub mod weekmodel;

use serde_json::Value;

/// A clock time Python would treat as present: a non-empty string. JSON null is not one.
pub(crate) fn has_start(value: &Value) -> bool {
    value
        .get("start")
        .and_then(Value::as_str)
        .is_some_and(|start| !start.is_empty())
}
