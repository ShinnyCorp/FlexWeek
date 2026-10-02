//! Python's operators on JSON values: `==`, `in`, iteration, `len`, slicing, `value.get(key)`,
//! with the errors Python raised on a value of the wrong type.

use serde_json::Value;

use crate::desk::pyval::{type_error, unhashable};
use crate::error::{EngineError, EngineResult};
use crate::snapshot::py_float_repr;
use crate::stored::{attribute_error, nonfinite, type_name};

enum Num {
    Int(i128),
    Big(String),
    Float(f64),
}

fn num(value: &Value) -> Option<Num> {
    if let Some(float) = nonfinite(value) {
        return Some(Num::Float(float));
    }
    match value {
        Value::Bool(flag) => Some(Num::Int(i128::from(*flag))),
        Value::Number(number) => {
            let text = number.to_string();
            if text.contains(['.', 'e', 'E']) {
                Some(Num::Float(text.parse().unwrap_or(f64::NAN)))
            } else {
                Some(text.parse::<i128>().map_or(Num::Big(text), Num::Int))
            }
        }
        _ => None,
    }
}

/// Python `==`.
pub fn eq(left: &Value, right: &Value) -> bool {
    match (num(left), num(right)) {
        (Some(a), Some(b)) => match (a, b) {
            (Num::Int(a), Num::Int(b)) => a == b,
            (Num::Big(a), Num::Big(b)) => a == b,
            (Num::Float(a), Num::Float(b)) => a == b,
            (Num::Int(a), Num::Float(b)) | (Num::Float(b), Num::Int(a)) => (a as f64) == b,
            (Num::Big(a), Num::Float(b)) | (Num::Float(b), Num::Big(a)) => {
                a.parse::<f64>().is_ok_and(|a| a == b)
            }
            _ => false,
        },
        (Some(_), None) | (None, Some(_)) => false,
        (None, None) => match (left, right) {
            (Value::Null, Value::Null) => true,
            (Value::String(a), Value::String(b)) => a == b,
            (Value::Array(a), Value::Array(b)) => {
                a.len() == b.len() && a.iter().zip(b).all(|(x, y)| eq(x, y))
            }
            (Value::Object(a), Value::Object(b)) => {
                a.len() == b.len()
                    && a.iter()
                        .all(|(key, value)| b.get(key).is_some_and(|other| eq(value, other)))
            }
            _ => false,
        },
    }
}

/// `for item in value`: a list's items, a string's characters, a dict's keys.
pub fn iterate(value: &Value) -> EngineResult<Vec<Value>> {
    match value {
        Value::Array(items) => Ok(items.clone()),
        Value::String(text) => Ok(text.chars().map(|ch| Value::from(ch.to_string())).collect()),
        Value::Object(map) if nonfinite(value).is_none() => {
            Ok(map.keys().map(|key| Value::from(key.as_str())).collect())
        }
        other => Err(type_error(format!(
            "'{}' object is not iterable",
            type_name(other)
        ))),
    }
}

/// `value.get(key)`: only a dict has `get`.
pub fn get<'a>(value: &'a Value, key: &str) -> EngineResult<Option<&'a Value>> {
    match value {
        Value::Object(map) if nonfinite(value).is_none() => Ok(map.get(key)),
        other => Err(attribute_error(other, "get")),
    }
}

/// The error of using `value` as a dict key or a set element.
pub fn hashable(value: &Value, place: &str) -> EngineResult<()> {
    match value {
        Value::Array(_) => Err(unhashable(value, place)),
        Value::Object(_) if nonfinite(value).is_none() => Err(unhashable(value, place)),
        _ => Ok(()),
    }
}

/// `item in container`.
pub fn contains(container: &Value, item: &Value) -> EngineResult<bool> {
    match container {
        Value::Array(items) => Ok(items.iter().any(|held| eq(held, item))),
        Value::Object(map) if nonfinite(container).is_none() => {
            hashable(item, "dict key")?;
            Ok(item.as_str().is_some_and(|key| map.contains_key(key)))
        }
        Value::String(text) => match item {
            Value::String(part) => Ok(text.contains(part.as_str())),
            other => Err(type_error(format!(
                "'in <string>' requires string as left operand, not {}",
                type_name(other)
            ))),
        },
        other => Err(type_error(format!(
            "argument of type '{}' is not a container or iterable",
            type_name(other)
        ))),
    }
}

/// `len(value)`.
pub fn length(value: &Value) -> EngineResult<usize> {
    match value {
        Value::Array(items) => Ok(items.len()),
        Value::String(text) => Ok(text.chars().count()),
        Value::Object(map) if nonfinite(value).is_none() => Ok(map.len()),
        other => Err(type_error(format!(
            "object of type '{}' has no len()",
            type_name(other)
        ))),
    }
}

/// `text[:end]` and `text[start:end]` on code points, with Python's negative counts.
pub fn slice_chars(text: &str, start: Option<i64>, end: Option<i64>) -> String {
    let chars: Vec<char> = text.chars().collect();
    let len = chars.len() as i64;
    let clamp = |at: i64| -> usize {
        let at = if at < 0 { at + len } else { at };
        at.clamp(0, len) as usize
    };
    let from = start.map_or(0, clamp);
    let to = end.map_or(chars.len(), clamp);
    if from >= to {
        return String::new();
    }
    chars[from..to].iter().collect()
}

/// A dict as Python keeps one: keys of any hashable kind, in the order they were first set.
#[derive(Default)]
pub struct PyDict {
    items: Vec<(Value, Value)>,
}

impl PyDict {
    pub fn new() -> Self {
        Self::default()
    }

    fn position(&self, key: &Value) -> EngineResult<Option<usize>> {
        hashable(key, "dict key")?;
        Ok(self.items.iter().position(|(held, _)| eq(held, key)))
    }

    pub fn get(&self, key: &Value) -> EngineResult<Option<&Value>> {
        Ok(self.position(key)?.map(|at| &self.items[at].1))
    }

    pub fn contains(&self, key: &Value) -> EngineResult<bool> {
        Ok(self.position(key)?.is_some())
    }

    pub fn set(&mut self, key: Value, value: Value) -> EngineResult<()> {
        match self.position(&key)? {
            Some(at) => self.items[at].1 = value,
            None => self.items.push((key, value)),
        }
        Ok(())
    }

    pub fn pop(&mut self, key: &Value) -> EngineResult<Option<Value>> {
        Ok(self.position(key)?.map(|at| self.items.remove(at).1))
    }

    pub fn len(&self) -> usize {
        self.items.len()
    }

    pub fn is_empty(&self) -> bool {
        self.items.is_empty()
    }

    pub fn into_values(self) -> Vec<Value> {
        self.items.into_iter().map(|(_, value)| value).collect()
    }
}

/// `isinstance(value, int)`: a bool is one too.
pub fn is_int(value: &Value) -> bool {
    match value {
        Value::Bool(_) => true,
        Value::Number(number) => !number.to_string().contains(['.', 'e', 'E']),
        _ => false,
    }
}

/// `text + other` where `other` must be text.
pub fn concat(left: &str, right: &Value) -> EngineResult<String> {
    match right {
        Value::String(text) => Ok(format!("{left}{text}")),
        other => Err(type_error(format!(
            "can only concatenate str (not \"{}\") to str",
            type_name(other)
        ))),
    }
}

fn from_num(number: Num) -> Value {
    match number {
        Num::Int(whole) => serde_json::Number::from_i128(whole).map_or(Value::Null, Value::Number),
        Num::Big(text) => text
            .parse::<serde_json::Number>()
            .map_or(Value::Null, Value::Number),
        Num::Float(float) => serde_json::Number::from_f64(float).map_or_else(
            || serde_json::json!({ crate::stored::NONFINITE: py_float_repr(float) }),
            Value::Number,
        ),
    }
}

fn float_of(number: &Num) -> f64 {
    match number {
        Num::Int(whole) => *whole as f64,
        Num::Big(text) => text.parse().unwrap_or(f64::NAN),
        Num::Float(float) => *float,
    }
}

fn operand_error(symbol: &str, left: &Value, right: &Value) -> EngineError {
    type_error(format!(
        "unsupported operand type(s) for {symbol}: '{}' and '{}'",
        type_name(left),
        type_name(right)
    ))
}

/// Python `left + right` on numbers, text and lists.
pub fn add(left: &Value, right: &Value) -> EngineResult<Value> {
    if let (Value::String(a), Value::String(b)) = (left, right) {
        return Ok(Value::String(format!("{a}{b}")));
    }
    if let (Value::Array(a), Value::Array(b)) = (left, right) {
        return Ok(Value::Array(a.iter().chain(b).cloned().collect()));
    }
    match (num(left), num(right)) {
        (Some(Num::Int(a)), Some(Num::Int(b))) => a
            .checked_add(b)
            .map(|sum| from_num(Num::Int(sum)))
            .ok_or_else(|| EngineError::overflow("integer too large for the engine")),
        (Some(a), Some(b)) => Ok(from_num(Num::Float(float_of(&a) + float_of(&b)))),
        _ => Err(operand_error("+", left, right)),
    }
}

/// Python `left - right` on numbers.
pub fn sub(left: &Value, right: &Value) -> EngineResult<Value> {
    match (num(left), num(right)) {
        (Some(Num::Int(a)), Some(Num::Int(b))) => a
            .checked_sub(b)
            .map(|difference| from_num(Num::Int(difference)))
            .ok_or_else(|| EngineError::overflow("integer too large for the engine")),
        (Some(a), Some(b)) => Ok(from_num(Num::Float(float_of(&a) - float_of(&b)))),
        _ => Err(operand_error("-", left, right)),
    }
}

#[derive(Clone, Copy)]
pub enum Cmp {
    Lt,
    Le,
    Gt,
    Ge,
}

impl Cmp {
    fn symbol(self) -> &'static str {
        match self {
            Cmp::Lt => "<",
            Cmp::Le => "<=",
            Cmp::Gt => ">",
            Cmp::Ge => ">=",
        }
    }

    fn holds(self, order: std::cmp::Ordering) -> bool {
        use std::cmp::Ordering::{Greater, Less};
        match self {
            Cmp::Lt => order == Less,
            Cmp::Le => order != Greater,
            Cmp::Gt => order == Greater,
            Cmp::Ge => order != Less,
        }
    }
}

/// How Python orders two values, or an error when it cannot.
pub fn order(left: &Value, right: &Value, op: Cmp) -> EngineResult<std::cmp::Ordering> {
    use std::cmp::Ordering;
    let fail = || {
        type_error(format!(
            "'{}' not supported between instances of '{}' and '{}'",
            op.symbol(),
            type_name(left),
            type_name(right)
        ))
    };
    match (num(left), num(right)) {
        (Some(Num::Int(a)), Some(Num::Int(b))) => return Ok(a.cmp(&b)),
        (Some(a), Some(b)) => {
            let (x, y) = (float_of(&a), float_of(&b));
            // NaN is unordered: report an order no operator accepts.
            return Ok(x.partial_cmp(&y).unwrap_or(match op {
                Cmp::Lt | Cmp::Le => Ordering::Greater,
                Cmp::Gt | Cmp::Ge => Ordering::Less,
            }));
        }
        _ => {}
    }
    match (left, right) {
        (Value::String(a), Value::String(b)) => Ok(a.cmp(b)),
        (Value::Array(a), Value::Array(b)) => {
            for (x, y) in a.iter().zip(b) {
                if !eq(x, y) {
                    return order(x, y, op);
                }
            }
            Ok(a.len().cmp(&b.len()))
        }
        _ => Err(fail()),
    }
}

/// Python `left < right` and the other three.
pub fn compare(op: Cmp, left: &Value, right: &Value) -> EngineResult<bool> {
    Ok(op.holds(order(left, right, op)?))
}

/// `value[:10]`, which a list or a string takes and nothing else does.
pub fn head(value: &Value, count: usize) -> EngineResult<Value> {
    match value {
        Value::String(text) => Ok(Value::String(text.chars().take(count).collect())),
        Value::Array(items) => Ok(Value::Array(items.iter().take(count).cloned().collect())),
        other => Err(type_error(format!(
            "'{}' object is not subscriptable",
            type_name(other)
        ))),
    }
}

/// `value or default`.
pub fn or_default(value: Option<&Value>, default: Value) -> Value {
    match value {
        Some(found) if crate::stored::truthy(Some(found)) => found.clone(),
        _ => default,
    }
}

/// `date.fromisoformat(value)` for a value that may not be text.
pub fn iso_day_of(value: &Value) -> EngineResult<chrono::NaiveDate> {
    match value {
        Value::String(text) => crate::desk::pydate::from_iso(text),
        _ => Err(type_error("fromisoformat: argument must be str")),
    }
}

/// `dict(value)`: a dict, or pairs.
pub fn py_dict(value: &Value) -> EngineResult<serde_json::Map<String, Value>> {
    match value {
        Value::Object(map) if nonfinite(value).is_none() => Ok(map.clone()),
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::Object(_) => Err(type_error(
            format!("'{}' object is not iterable", type_name(value)),
        )),
        other => {
            let mut map = serde_json::Map::new();
            for (at, element) in iterate(other)?.into_iter().enumerate() {
                let pair = match &element {
                    Value::Null | Value::Bool(_) | Value::Number(_) => {
                        return Err(type_error("object is not iterable"));
                    }
                    found => iterate(found)?,
                };
                if pair.len() != 2 {
                    return Err(EngineError::value(format!(
                        "dictionary update sequence element #{at} has length {}; 2 is required",
                        pair.len()
                    )));
                }
                hashable(&pair[0], "dict key")?;
                let Value::String(key) = &pair[0] else {
                    return Err(EngineError::value(
                        "the engine keeps text keys only in a dict made from pairs",
                    ));
                };
                map.insert(key.clone(), pair[1].clone());
            }
            Ok(map)
        }
    }
}

/// `names[index]` on a tuple the code owns.
pub fn tuple_index(length: usize, index: &Value) -> EngineResult<usize> {
    let whole = match index {
        Value::Bool(flag) => i128::from(*flag),
        Value::Number(_) if is_int(index) => match num(index) {
            Some(Num::Int(found)) => found,
            _ => i128::MAX,
        },
        other => {
            return Err(type_error(format!(
                "tuple indices must be integers or slices, not {}",
                type_name(other)
            )));
        }
    };
    if i128::from(i64::MIN) > whole || whole > i128::from(i64::MAX) {
        return Err(EngineError::index(
            "cannot fit 'int' into an index-sized integer",
        ));
    }
    let shifted = if whole < 0 {
        whole + length as i128
    } else {
        whole
    };
    if shifted < 0 || shifted >= length as i128 {
        return Err(EngineError::index("tuple index out of range"));
    }
    Ok(shifted as usize)
}

/// `items[0]` on a list or string held as a value.
pub fn first_of(value: &Value) -> EngineResult<Value> {
    match value {
        Value::Array(items) => items
            .first()
            .cloned()
            .ok_or_else(|| EngineError::index("list index out of range")),
        Value::String(text) => text
            .chars()
            .next()
            .map(|ch| Value::from(ch.to_string()))
            .ok_or_else(|| EngineError::index("string index out of range")),
        other => Err(type_error(format!(
            "'{}' object is not subscriptable",
            type_name(other)
        ))),
    }
}

/// `item in items` for a set the code built: unhashable items are refused as set elements.
pub fn in_set(items: &[Value], item: &Value) -> EngineResult<bool> {
    hashable(item, "set element")?;
    Ok(items.iter().any(|held| eq(held, item)))
}

/// `int(value)` that keeps the value as a number.
pub fn int_of(value: &Value) -> EngineResult<i64> {
    crate::stored::py_int(value)
}

/// `f"{hour:02d}:{minute:02d}"` of `divmod(minutes, 60)`.
pub fn hhmm_of(minutes: &Value) -> EngineResult<String> {
    match minutes {
        Value::Bool(_) | Value::Number(_) if is_int(minutes) => {
            let whole = int_of(minutes)?;
            Ok(crate::time::minutes_to_hhmm(whole))
        }
        Value::Number(_) => Err(EngineError::value(
            "Unknown format code 'd' for object of type 'float'",
        )),
        other => Err(type_error(format!(
            "unsupported operand type(s) for divmod(): '{}' and 'int'",
            type_name(other)
        ))),
    }
}

/// `int(value)` with room for what Python's unbounded ints hold in practice.
pub fn to_int(value: &Value) -> EngineResult<i128> {
    if nonfinite(value).is_some() {
        return crate::stored::py_int(value).map(i128::from);
    }
    match value {
        Value::Number(number) if !number.to_string().contains(['.', 'e', 'E']) => number
            .to_string()
            .parse::<i128>()
            .map_err(|_| EngineError::overflow("integer too large for the engine")),
        Value::Number(_) => {
            let whole = crate::stored::py_int(value)?;
            Ok(i128::from(whole))
        }
        other => crate::stored::py_int(other).map(i128::from),
    }
}

/// An integer as a JSON number.
pub fn int_json(value: i128) -> Value {
    serde_json::Number::from_i128(value).map_or(Value::Null, Value::Number)
}

/// `isinstance(value, (int, float))`: a bool and a non-finite float count.
pub fn is_number(value: &Value) -> bool {
    matches!(value, Value::Bool(_) | Value::Number(_)) || nonfinite(value).is_some()
}

/// `value[key] = ...` on a value that is not a dict.
pub fn item_assignment(value: &Value) -> EngineError {
    match value {
        Value::Array(_) => type_error("list indices must be integers or slices, not str"),
        other => type_error(format!(
            "'{}' object does not support item assignment",
            type_name(other)
        )),
    }
}

/// A copy of a dict that the code is about to assign into.
pub fn assigning(value: &Value) -> EngineResult<serde_json::Map<String, Value>> {
    match value {
        Value::Object(map) if nonfinite(value).is_none() => Ok(map.clone()),
        other => Err(item_assignment(other)),
    }
}
