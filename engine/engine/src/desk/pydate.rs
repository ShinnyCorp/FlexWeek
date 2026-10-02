//! `date.fromisoformat` as Python 3.14 reads it, with its messages.

use chrono::NaiveDate;

use crate::error::{EngineError, EngineResult};
use crate::time::py_repr;

fn digits(text: &str, count: usize) -> Option<u32> {
    (text.len() == count && text.bytes().all(|byte| byte.is_ascii_digit()))
        .then(|| text.parse().ok())
        .flatten()
}

pub(crate) fn calendar_date(year: i32, month: u32, day: u32) -> EngineResult<NaiveDate> {
    if !(1..=9999).contains(&year) {
        return Err(EngineError::value(format!(
            "year must be in 1..9999, not {year}"
        )));
    }
    if !(1..=12).contains(&month) {
        return Err(EngineError::value(format!(
            "month must be in 1..12, not {month}"
        )));
    }
    NaiveDate::from_ymd_opt(year, month, day).ok_or_else(|| {
        let longest = (28..=31)
            .rev()
            .find(|last| NaiveDate::from_ymd_opt(year, month, *last).is_some())
            .unwrap_or(28);
        EngineError::value(format!(
            "day {day} must be in range 1..{longest} for month {month} in year {year}"
        ))
    })
}

fn week_date(year: u32, week: u32, day: u32) -> Option<NaiveDate> {
    let weekday = match day {
        1 => chrono::Weekday::Mon,
        2 => chrono::Weekday::Tue,
        3 => chrono::Weekday::Wed,
        4 => chrono::Weekday::Thu,
        5 => chrono::Weekday::Fri,
        6 => chrono::Weekday::Sat,
        7 => chrono::Weekday::Sun,
        _ => return None,
    };
    NaiveDate::from_isoywd_opt(year as i32, week, weekday)
}

/// The year, month and day of `YYYY-MM-DD` or `YYYYMMDD`.
fn calendar_form(text: &str) -> Option<(u32, u32, u32)> {
    let year = digits(text.get(..4)?, 4)?;
    let rest = &text[4..];
    let (month, day) = match rest.len() {
        6 if rest.starts_with('-') && rest.as_bytes()[3] == b'-' => (&rest[1..3], &rest[4..]),
        4 => (&rest[..2], &rest[2..]),
        _ => return None,
    };
    Some((year, digits(month, 2)?, digits(day, 2)?))
}

/// The year, week and weekday of `YYYY-Www[-D]` or `YYYYWww[D]`.
fn week_form(text: &str) -> Option<(u32, u32, u32)> {
    let year = digits(text.get(..4)?, 4)?;
    let (dashed, rest) = match text[4..].strip_prefix('-') {
        Some(rest) => (true, rest),
        None => (false, &text[4..]),
    };
    let rest = rest.strip_prefix('W')?;
    let (week, day) = match (dashed, rest.len()) {
        (_, 2) => (rest, "1"),
        (true, 4) if rest.as_bytes()[2] == b'-' => (&rest[..2], &rest[3..]),
        (false, 3) => (&rest[..2], &rest[2..]),
        _ => return None,
    };
    Some((year, digits(week, 2)?, digits(day, 1)?))
}

pub(crate) fn from_iso(text: &str) -> EngineResult<NaiveDate> {
    if text.is_ascii() {
        if let Some((year, month, day)) = calendar_form(text) {
            return calendar_date(year as i32, month, day);
        }
        if let Some((year, week, day)) = week_form(text)
            && let Some(found) = week_date(year, week, day)
        {
            return Ok(found);
        }
    }
    Err(EngineError::value(format!(
        "Invalid isoformat string: {}",
        py_repr(text)
    )))
}

pub(crate) fn iso_text(day: NaiveDate) -> String {
    use chrono::Datelike;
    format!("{:04}-{:02}-{:02}", day.year(), day.month(), day.day())
}

/// `(date.fromisoformat(week_start) + timedelta(days=days)).isoformat()`.
pub(crate) fn add_days_text(start: &str, days: i64) -> EngineResult<String> {
    let moved = crate::stored::add_days(from_iso(start)?, days)?;
    Ok(iso_text(moved))
}

/// `monday_of` from `desktop/native/calendar.py`.
pub(crate) fn monday_text(day: &str) -> EngineResult<String> {
    use chrono::Datelike;
    let found = from_iso(day)?;
    Ok(iso_text(
        found - chrono::Duration::days(i64::from(found.weekday().num_days_from_monday())),
    ))
}
