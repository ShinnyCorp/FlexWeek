//! Week-grid edits and calendar helpers from `desktop/native/calendar.py`.

use chrono::NaiveDate;

use serde_json::Value;

use crate::error::{EngineError, EngineResult};
use crate::time;

pub const LOCKED_CATEGORIES: [&str; 6] = ["class", "exercise", "extra", "meals", "sleep", "free"];
pub const FLEX_CATEGORIES: [&str; 2] = ["assignments", "study"];
pub const WEEKDAYS: [i64; 5] = [0, 1, 2, 3, 4];
pub const DAYS: [&str; 7] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
pub const DAY_FULL: [&str; 7] = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
];
pub const FIRST_MONTH: &str = "2000-01";
pub const LAST_MONTH: &str = "2099-12";
pub const SERIES_DRAG_MESSAGE: &str = "{title} repeats on {count} days, so dragging it is ambiguous. Edit the occurrence or the series.";
pub const SETUP_SCHOOL_ID: &str = "school";
pub const SETUP_ACTIVITY_PREFIX: &str = "activity-";

pub fn category_title(category: Option<&str>) -> &'static str {
    CATEGORIES
        .iter()
        .find(|(key, _)| Some(*key) == category)
        .map(|(_, info)| info.label)
        .unwrap_or("Fixed time")
}

/// `block.get("kind") == "locked" and len(block.get("days") or []) > 1`.
pub fn is_series_checked(block: &Value) -> EngineResult<bool> {
    use crate::desk::pyops::{get, length};
    use crate::stored::truthy;
    if get(block, "kind")?.and_then(Value::as_str) != Some("locked") {
        return Ok(false);
    }
    match get(block, "days")? {
        Some(days) if truthy(Some(days)) => Ok(length(days)? > 1),
        _ => Ok(false),
    }
}

pub fn is_series(block: &Value) -> bool {
    block.get("kind").and_then(Value::as_str) == Some("locked")
        && block
            .get("days")
            .and_then(Value::as_array)
            .map(|d| d.len() > 1)
            .unwrap_or(false)
}

fn parse_iso_day(value: &str) -> Option<NaiveDate> {
    NaiveDate::parse_from_str(value, "%Y-%m-%d").ok()
}

pub fn local_stamp(now_iso_minute: Option<&str>) -> String {
    if let Some(stamp) = now_iso_minute {
        return stamp.to_string();
    }
    String::new()
}

pub fn days_through(due_day: Option<i64>, first_day: i64) -> Vec<i64> {
    let last = due_day.map(|d| d.min(6)).unwrap_or(6);
    if last < 0 {
        return Vec::new();
    }
    if last < first_day {
        return vec![last];
    }
    (0..7)
        .filter(|day| first_day <= *day && *day <= last)
        .collect()
}

pub fn is_work_session(block: &Value) -> bool {
    block.get("kind").and_then(Value::as_str) == Some("flexible")
        || (block.get("kind").and_then(Value::as_str) == Some("locked")
            && block.get("pomodoro_role").and_then(Value::as_str) == Some("work")
            && crate::stored::truthy(block.get("assignment_id")))
}

pub fn category_icon(category: Option<&str>) -> Option<&'static str> {
    if category == Some("homework") {
        return Some("book-open");
    }
    CATEGORIES
        .iter()
        .find(|(key, _)| Some(*key) == category)
        .and_then(|(_, info)| info.icon)
}

// --- due parsing (from backend.models, used by weekmodel and reuse) ---

pub const END_OF_DAY_MIN: i64 = 24 * 60;
pub const END_OF_DAY_CLOCK: &str = "23:59";

pub fn parse_due(value: &str) -> EngineResult<(NaiveDate, i64)> {
    if value.len() == 10 && value.as_bytes().get(4) == Some(&b'-') {
        let day = parse_iso_day(value).ok_or_else(|| {
            EngineError::value("must be YYYY-MM-DD or YYYY-MM-DDTHH:MM with no seconds or timezone")
        })?;
        return Ok((day, END_OF_DAY_MIN));
    }
    if value.len() >= 16 && value.as_bytes().get(10) == Some(&b'T') {
        let day = parse_iso_day(&value[..10]).ok_or_else(|| {
            EngineError::value("must be YYYY-MM-DD or YYYY-MM-DDTHH:MM with no seconds or timezone")
        })?;
        let clock = &value[11..16];
        if clock == END_OF_DAY_CLOCK {
            return Ok((day, END_OF_DAY_MIN));
        }
        let minutes = time::hhmm_to_minutes(clock)?;
        return Ok((day, minutes));
    }
    Err(EngineError::value(
        "must be YYYY-MM-DD or YYYY-MM-DDTHH:MM with no seconds or timezone",
    ))
}

pub fn due_is_timed(value: &str) -> bool {
    value.len() >= 16
        && value.as_bytes().get(10) == Some(&b'T')
        && &value[11..16] != END_OF_DAY_CLOCK
}

pub fn due_sort_key(due: Option<&str>, item_id: &str) -> (NaiveDate, i64, String) {
    if let Some(due) = due
        && let Ok((day, minute)) = parse_due(due)
    {
        return (day, minute, item_id.to_string());
    }
    (
        NaiveDate::from_ymd_opt(9999, 12, 31).expect("max date"),
        END_OF_DAY_MIN,
        item_id.to_string(),
    )
}

pub struct CategoryInfo {
    pub icon: Option<&'static str>,
    pub label: &'static str,
    pub hue: i64,
    pub color: &'static str,
    pub mark: &'static str,
    pub kind: &'static str,
}

pub static CATEGORIES: [(&str, CategoryInfo); 8] = [
    (
        "class",
        CategoryInfo {
            icon: Some("school"),
            label: "School",
            hue: 250,
            color: "#cfe8ff",
            mark: "#398ad6",
            kind: "locked",
        },
    ),
    (
        "assignments",
        CategoryInfo {
            icon: Some("book-open"),
            label: "Homework",
            hue: 25,
            color: "#ffdad6",
            mark: "#831a1d",
            kind: "flexible",
        },
    ),
    (
        "study",
        CategoryInfo {
            icon: Some("pencil"),
            label: "Study",
            hue: 320,
            color: "#f2dbf8",
            mark: "#ab68ba",
            kind: "flexible",
        },
    ),
    (
        "exercise",
        CategoryInfo {
            icon: Some("target"),
            label: "Sports",
            hue: 150,
            color: "#d0eed5",
            mark: "#399d57",
            kind: "locked",
        },
    ),
    (
        "extra",
        CategoryInfo {
            icon: Some("sparkles"),
            label: "Activity",
            hue: 200,
            color: "#c3eef0",
            mark: "#009ea7",
            kind: "locked",
        },
    ),
    (
        "meals",
        CategoryInfo {
            icon: Some("clock"),
            label: "Meals",
            hue: 70,
            color: "#f9e0c5",
            mark: "#bb7400",
            kind: "locked",
        },
    ),
    (
        "sleep",
        CategoryInfo {
            icon: Some("moon"),
            label: "Sleep",
            hue: 280,
            color: "#c4c8e8",
            mark: "#5656b0",
            kind: "locked",
        },
    ),
    (
        "free",
        CategoryInfo {
            icon: None,
            label: "Free",
            hue: 250,
            color: "#e0e5eb",
            mark: "#82878c",
            kind: "locked",
        },
    ),
];

pub fn deep_copy(value: &Value) -> Value {
    serde_json::from_str(&value.to_string()).unwrap_or(Value::Null)
}
