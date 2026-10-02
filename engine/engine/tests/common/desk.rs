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

/// Milliseconds since the epoch of a wall-clock time read as UTC. The engine is handed the local
/// clock by its caller and never reads a time zone, so these tests pick UTC as "local".
pub fn utc_ms(year: i32, month: u32, day: u32, hour: u32, minute: u32) -> i64 {
    chrono::NaiveDate::from_ymd_opt(year, month, day)
        .and_then(|date| date.and_hms_opt(hour, minute, 0))
        .expect("a real date and time")
        .and_utc()
        .timestamp_millis()
}

/// Python's `str.title()`: each run of letters starts with a capital and goes on in lower case.
pub fn py_title(text: &str) -> String {
    let mut out = String::new();
    let mut in_word = false;
    for ch in text.chars() {
        if ch.is_alphabetic() {
            if in_word {
                out.extend(ch.to_lowercase());
            } else {
                out.extend(ch.to_uppercase());
            }
            in_word = true;
        } else {
            out.push(ch);
            in_word = false;
        }
    }
    out
}

/// Tests that switch the engine's one global clock (24-hour or 12-hour) share this lock, so two of
/// them never run side by side, and each starts and ends on the 24-hour clock Python's tests expect.
pub struct ClockGuard(std::sync::MutexGuard<'static, ()>);

pub fn clock_lock() -> ClockGuard {
    static LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
    let held = LOCK
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    flexweek_engine::desk::weekmodel::set_clock_24h(true);
    ClockGuard(held)
}

impl Drop for ClockGuard {
    fn drop(&mut self) {
        flexweek_engine::desk::weekmodel::set_clock_24h(true);
    }
}
