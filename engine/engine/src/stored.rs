//! Stored rows read as the Python code read them: values from `json.loads`, used with Python's
//! truth, `str()`, `int()`, `list()`, `max()` and `date + timedelta(days=...)`, raising what Python raised.

use chrono::NaiveDate;
use serde_json::{Map, Value};

use crate::error::{EngineError, EngineResult, ErrorKind};
use crate::time::{py_repr, shift_days};

pub type Dict = Map<String, Value>;

const C_INT: &str = "Python int too large to convert to C int";

pub fn type_name(value: &Value) -> &'static str {
    match value {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(number) if is_float(number) => "float",
        Value::Number(_) => "int",
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

/// `json.loads` makes a float of any number written with a point or an exponent.
fn is_float(number: &serde_json::Number) -> bool {
    number.to_string().contains(['.', 'e', 'E'])
}

fn float_of(number: &serde_json::Number) -> f64 {
    number.to_string().parse().unwrap_or(f64::NAN)
}

/// A JSON integer as Python holds it, or None when it is beyond 64 bits.
fn int_of(number: &serde_json::Number) -> Option<i64> {
    number.to_string().parse().ok()
}

/// `bool(value)`, with a missing key read as `None`.
pub fn truthy(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) => false,
        Some(Value::Bool(flag)) => *flag,
        Some(Value::Number(number)) if is_float(number) => float_of(number) != 0.0,
        Some(Value::Number(number)) => number.to_string().trim_start_matches('-') != "0",
        Some(Value::String(text)) => !text.is_empty(),
        Some(Value::Array(items)) => !items.is_empty(),
        Some(Value::Object(map)) => !map.is_empty(),
    }
}

pub fn attribute_error(value: &Value, name: &str) -> EngineError {
    EngineError {
        kind: ErrorKind::Attribute,
        message: format!("'{}' object has no attribute '{name}'", type_name(value)),
    }
}

fn type_error(message: String) -> EngineError {
    EngineError {
        kind: ErrorKind::Type,
        message,
    }
}

/// The row a value must be for `value.get(...)` to work.
pub fn dict(value: &Value) -> EngineResult<&Dict> {
    value
        .as_object()
        .ok_or_else(|| attribute_error(value, "get"))
}

/// The dicts `for block in blocks: block.get(...)` walks. A str or dict iterates as text, so
/// only an empty one gets through.
pub fn rows(blocks: &Value) -> EngineResult<Vec<Dict>> {
    match blocks {
        Value::Array(items) => items.iter().map(|item| dict(item).cloned()).collect(),
        Value::String(text) if text.is_empty() => Ok(Vec::new()),
        Value::Object(map) if map.is_empty() => Ok(Vec::new()),
        Value::String(_) | Value::Object(_) => Err(attribute_error(&Value::from(""), "get")),
        other => Err(type_error(format!(
            "'{}' object is not iterable",
            type_name(other)
        ))),
    }
}

/// `block[key]`.
pub fn item<'a>(block: &'a Dict, key: &str) -> EngineResult<&'a Value> {
    block.get(key).ok_or_else(|| EngineError::key(key))
}

/// `str(value)`. A dict prints its keys sorted, where Python kept the order they were written in.
pub fn py_str(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        other => py_repr_value(other),
    }
}

fn py_repr_value(value: &Value) -> String {
    match value {
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::Number(number) if is_float(number) => {
            crate::snapshot::py_float_repr(float_of(number))
        }
        Value::Number(number) => match int_of(number) {
            Some(whole) => whole.to_string(),
            None => number.to_string(),
        },
        Value::String(text) => py_repr(text),
        Value::Array(items) => {
            let parts: Vec<String> = items.iter().map(py_repr_value).collect();
            format!("[{}]", parts.join(", "))
        }
        Value::Object(map) => {
            let parts: Vec<String> = map
                .iter()
                .map(|(key, item)| format!("{}: {}", py_repr(key), py_repr_value(item)))
                .collect();
            format!("{{{}}}", parts.join(", "))
        }
    }
}

/// `int(value)`. Python's ints have no limit; past 64 bits this raises the error Python's
/// `timedelta` would raise on the same number.
pub fn py_int(value: &Value) -> EngineResult<i64> {
    match value {
        Value::Bool(flag) => Ok(i64::from(*flag)),
        Value::Number(number) if is_float(number) => float_to_int(float_of(number)),
        Value::Number(number) => int_of(number).ok_or_else(|| EngineError::overflow(C_INT)),
        Value::String(text) => crate::time::py_int(text),
        other => Err(type_error(format!(
            "int() argument must be a string, a bytes-like object or a real number, not '{}'",
            type_name(other)
        ))),
    }
}

fn float_to_int(value: f64) -> EngineResult<i64> {
    if value.is_nan() {
        return Err(EngineError::value("cannot convert float NaN to integer"));
    }
    if value.is_infinite() {
        return Err(EngineError::overflow(
            "cannot convert float infinity to integer",
        ));
    }
    let whole = value.trunc();
    if whole < i64::MIN as f64 || whole >= i64::MAX as f64 {
        return Err(EngineError::overflow(C_INT));
    }
    Ok(whole as i64)
}

/// `int(value or 0)`.
pub fn int_or_zero(value: Option<&Value>) -> EngineResult<i64> {
    match value {
        Some(value) if truthy(Some(value)) => py_int(value),
        _ => Ok(0),
    }
}

/// `list(value or [])`. A dict lists its keys sorted, where Python kept their written order.
pub fn py_list(value: Option<&Value>) -> EngineResult<Vec<Value>> {
    let Some(value) = value.filter(|value| truthy(Some(value))) else {
        return Ok(Vec::new());
    };
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

/// `value.split(":")` and `value.strip()` need a str.
pub fn text<'a>(value: &'a Value, method: &str) -> EngineResult<&'a str> {
    value.as_str().ok_or_else(|| attribute_error(value, method))
}

enum Real {
    Int(i64),
    Float(f64),
}

fn real(value: &Value) -> Option<Real> {
    match value {
        Value::Bool(flag) => Some(Real::Int(i64::from(*flag))),
        Value::Number(number) if is_float(number) => Some(Real::Float(float_of(number))),
        Value::Number(number) => {
            Some(int_of(number).map_or(Real::Float(float_of(number)), Real::Int))
        }
        _ => None,
    }
}

fn greater(left: &Value, right: &Value) -> EngineResult<bool> {
    let unsupported = || {
        type_error(format!(
            "'>' not supported between instances of '{}' and '{}'",
            type_name(left),
            type_name(right)
        ))
    };
    match (real(left), real(right), left, right) {
        (Some(Real::Int(a)), Some(Real::Int(b)), _, _) => Ok(a > b),
        (Some(a), Some(b), _, _) => {
            let as_float = |x: Real| match x {
                Real::Int(whole) => whole as f64,
                Real::Float(float) => float,
            };
            Ok(as_float(a) > as_float(b))
        }
        (_, _, Value::String(a), Value::String(b)) => Ok(a > b),
        _ => Err(unsupported()),
    }
}

/// `max(values)` on a non-empty list: the first of the largest, comparing as `>` does.
pub fn py_max(values: &[Value]) -> EngineResult<Value> {
    let mut best = &values[0];
    for value in &values[1..] {
        if greater(value, best)? {
            best = value;
        }
    }
    Ok(best.clone())
}

/// `day + timedelta(days=count)` for a whole number of days.
pub fn add_days(day: NaiveDate, count: i64) -> EngineResult<NaiveDate> {
    if i32::try_from(count).is_err() {
        return Err(EngineError::overflow(C_INT));
    }
    if count.abs() > 999_999_999 {
        return Err(EngineError::overflow(format!(
            "days={count}; must have magnitude <= 999999999"
        )));
    }
    shift_days(day, count)
}

/// `day + timedelta(days=value)`: a float keeps whole days only, after rounding to microseconds.
pub fn add_days_of(day: NaiveDate, value: &Value) -> EngineResult<NaiveDate> {
    match real(value) {
        Some(Real::Int(whole)) => add_days(day, whole),
        Some(Real::Float(float)) => {
            if float.is_nan() || float.is_infinite() {
                return float_to_int(float).map(|_| day);
            }
            let mut whole = float.floor();
            if ((float - whole) * 86_400e6).round() >= 86_400e6 {
                whole += 1.0;
            }
            if !(f64::from(i32::MIN)..=f64::from(i32::MAX)).contains(&whole) {
                return Err(EngineError::overflow(C_INT));
            }
            add_days(day, whole as i64)
        }
        None => Err(type_error(format!(
            "unsupported type for timedelta days component: {}",
            type_name(value)
        ))),
    }
}
