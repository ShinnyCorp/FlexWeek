//! `backend/slots.py` and `backend/weeks.py`. No clock: the caller passes today.

use std::sync::LazyLock;

use chrono::{Datelike, Duration, NaiveDate};
use regex::Regex;

use crate::error::{EngineError, EngineResult};

pub const SLOT_MIN: i64 = 15;
pub const DAY_START_MIN: i64 = 0;
pub const DAY_END_MIN: i64 = 24 * 60;
pub const SLOTS_PER_DAY: i64 = (DAY_END_MIN - DAY_START_MIN) / SLOT_MIN;

const FIRST_DAY: (i32, u32, u32) = (2000, 1, 1);
const LAST_DAY: (i32, u32, u32) = (2099, 12, 31);
const FIRST_WEEK_START: &str = "1999-12-27";

pub fn day_name_to_index() -> Vec<(&'static str, i64)> {
    vec![
        ("monday", 0),
        ("mon", 0),
        ("tuesday", 1),
        ("tue", 1),
        ("tues", 1),
        ("wednesday", 2),
        ("wed", 2),
        ("thursday", 3),
        ("thu", 3),
        ("thur", 3),
        ("thurs", 3),
        ("friday", 4),
        ("fri", 4),
        ("saturday", 5),
        ("sat", 5),
        ("sunday", 6),
        ("sun", 6),
    ]
}

pub(crate) fn py_space(ch: char) -> bool {
    ch.is_whitespace() || matches!(ch, '\u{1c}' | '\u{1d}' | '\u{1e}' | '\u{1f}')
}

pub(crate) fn py_strip(text: &str) -> &str {
    text.trim_matches(py_space)
}

pub(crate) fn py_repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::new();
    out.push(quote);
    for ch in text.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(quote);
            }
            // A lone surrogate crosses as a private-use character (desktop/native/wire.py).
            c if ('\u{10F800}'..='\u{10FFFF}').contains(&c) => {
                out.push_str(&format!("\\u{:04x}", c as u32 - 0x10F800 + 0xD800));
            }
            c if !crate::pyprint::py_printable(c) => {
                let cp = c as u32;
                if cp < 0x100 {
                    out.push_str(&format!("\\x{cp:02x}"));
                } else if cp < 0x10000 {
                    out.push_str(&format!("\\u{cp:04x}"));
                } else {
                    out.push_str(&format!("\\U{cp:08x}"));
                }
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

/// Starts of the Unicode blocks of ten decimal digits (0 through 9).
const DIGIT_BLOCKS: &[u32] = &[
    0x30, 0x660, 0x6F0, 0x7C0, 0x966, 0x9E6, 0xA66, 0xAE6, 0xB66, 0xBE6, 0xC66, 0xCE6, 0xD66,
    0xDE6, 0xE50, 0xED0, 0xF20, 0x1040, 0x1090, 0x17E0, 0x1810, 0x1946, 0x19D0, 0x1A80, 0x1A90,
    0x1B50, 0x1BB0, 0x1C40, 0x1C50, 0xA620, 0xA8D0, 0xA900, 0xA9D0, 0xA9F0, 0xAA50, 0xABF0, 0xFF10,
    0x104A0, 0x10D30, 0x10D40, 0x11066, 0x110F0, 0x11136, 0x111D0, 0x112F0, 0x11450, 0x114D0,
    0x11650, 0x116C0, 0x116D0, 0x116DA, 0x11730, 0x118E0, 0x11950, 0x11BF0, 0x11C50, 0x11D50,
    0x11DA0, 0x11F50, 0x16130, 0x16A60, 0x16AC0, 0x16B50, 0x16D70, 0x1CCF0, 0x1D7CE, 0x1D7D8,
    0x1D7E2, 0x1D7EC, 0x1D7F6, 0x1E140, 0x1E2F0, 0x1E4F0, 0x1E5F1, 0x1E950, 0x1FBF0,
];

pub(crate) fn decimal_digit(ch: char) -> Option<u8> {
    let cp = ch as u32;
    let idx = DIGIT_BLOCKS.partition_point(|start| *start <= cp);
    if idx == 0 {
        return None;
    }
    let offset = cp - DIGIT_BLOCKS[idx - 1];
    if offset < 10 {
        Some(offset as u8)
    } else {
        None
    }
}

/// Python `int()`, including Unicode decimal digits and underscores between digits.
pub fn py_int(raw: &str) -> EngineResult<i64> {
    let fail = || {
        EngineError::value(format!(
            "invalid literal for int() with base 10: {}",
            py_repr(raw)
        ))
    };
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Err(fail());
    }
    let mut chars = trimmed.chars().peekable();
    let sign = match chars.peek() {
        Some('+') => {
            chars.next();
            1i64
        }
        Some('-') => {
            chars.next();
            -1
        }
        _ => 1,
    };
    let mut magnitude: i64 = 0;
    let mut saw_digit = false;
    let mut prev_underscore = false;
    for ch in chars {
        if ch == '_' {
            if !saw_digit || prev_underscore {
                return Err(fail());
            }
            prev_underscore = true;
            continue;
        }
        let Some(digit) = decimal_digit(ch) else {
            return Err(fail());
        };
        prev_underscore = false;
        saw_digit = true;
        magnitude = magnitude
            .checked_mul(10)
            .and_then(|value| value.checked_add(i64::from(digit)))
            .ok_or_else(|| EngineError::overflow("Python int too large to convert to C long"))?;
    }
    if !saw_digit || prev_underscore {
        return Err(fail());
    }
    magnitude
        .checked_mul(sign)
        .ok_or_else(|| EngineError::overflow("Python int too large to convert to C long"))
}

pub fn hhmm_to_minutes(hhmm: &str) -> EngineResult<i64> {
    let parts: Vec<&str> = hhmm.split(':').collect();
    if parts.len() != 2 {
        return Err(EngineError::value(format!(
            "expected HH:MM, got {}",
            py_repr(hhmm)
        )));
    }
    let hour = match py_int(parts[0]) {
        Ok(value) => value,
        Err(error) if error.kind == crate::error::ErrorKind::Overflow => {
            return Err(EngineError::value(format!(
                "invalid time {}",
                py_repr(hhmm)
            )));
        }
        Err(error) => return Err(error),
    };
    let minute = match py_int(parts[1]) {
        Ok(value) => value,
        Err(error) if error.kind == crate::error::ErrorKind::Overflow => {
            return Err(EngineError::value(format!(
                "invalid time {}",
                py_repr(hhmm)
            )));
        }
        Err(error) => return Err(error),
    };
    if !(0..=23).contains(&hour) || !(0..=59).contains(&minute) {
        return Err(EngineError::value(format!(
            "invalid time {}",
            py_repr(hhmm)
        )));
    }
    Ok(hour * 60 + minute)
}

pub fn clock_to_minutes(hhmm: &str) -> EngineResult<i64> {
    if hhmm == "24:00" {
        return Ok(DAY_END_MIN);
    }
    hhmm_to_minutes(hhmm)
}

fn divmod_floor(value: i64, divisor: i64) -> (i64, i64) {
    (value.div_euclid(divisor), value.rem_euclid(divisor))
}

pub fn minutes_to_hhmm(minutes: i64) -> String {
    let (hour, minute) = divmod_floor(minutes, 60);
    format!("{hour:02}:{minute:02}")
}

pub fn start_fits_day(start_min: i64) -> bool {
    (DAY_START_MIN..DAY_END_MIN).contains(&start_min)
}

pub fn span_fits_day(start_min: i64, duration_min: i64) -> bool {
    duration_min > 0 && start_fits_day(start_min) && start_min + duration_min <= DAY_END_MIN
}

pub fn on_slot(minutes: i64) -> bool {
    minutes.rem_euclid(SLOT_MIN) == 0
}

pub fn minutes_to_slot(minutes: i64) -> EngineResult<i64> {
    if !(DAY_START_MIN..DAY_END_MIN).contains(&minutes) {
        return Err(EngineError::value("time is outside 00:00–24:00"));
    }
    let offset = minutes - DAY_START_MIN;
    if offset % SLOT_MIN != 0 {
        return Err(EngineError::value("time must land on a 15-minute slot"));
    }
    Ok(offset / SLOT_MIN)
}

pub fn hhmm_to_slot(hhmm: &str) -> EngineResult<i64> {
    minutes_to_slot(hhmm_to_minutes(hhmm)?)
}

pub fn slot_to_hhmm(slot: i64) -> EngineResult<String> {
    if !(0..SLOTS_PER_DAY).contains(&slot) {
        return Err(EngineError::value("slot out of range"));
    }
    Ok(minutes_to_hhmm(DAY_START_MIN + slot * SLOT_MIN))
}

pub fn duration_to_slots(duration_min: i64) -> EngineResult<i64> {
    if duration_min <= 0 {
        return Err(EngineError::value("duration must be positive"));
    }
    Ok(-(-duration_min).div_euclid(SLOT_MIN))
}

pub fn overlaps(a_start: i64, a_end: i64, b_start: i64, b_end: i64) -> bool {
    a_start < b_end && b_start < a_end
}

pub fn block_interval_on_day(
    days: &[i64],
    start: Option<&str>,
    duration_min: i64,
    day: i64,
) -> EngineResult<Option<(i64, i64)>> {
    if !days.contains(&day) || start.is_none() {
        return Ok(None);
    }
    let start_min = hhmm_to_minutes(start.unwrap_or(""))?;
    Ok(Some((start_min, start_min + duration_min)))
}

pub fn parse_deadline(latest: Option<&str>, days: &[i64]) -> EngineResult<Option<(i64, i64)>> {
    deadline_with(latest, || Ok(days.iter().copied().max().unwrap_or(0)))
}

/// `parse_deadline` with `max(days) if days else 0` left to the caller, which runs it where
/// Python did: after the text is found non-empty, before the time is read.
pub(crate) fn deadline_with<D: From<i64>>(
    latest: Option<&str>,
    last_day: impl FnOnce() -> EngineResult<D>,
) -> EngineResult<Option<(D, i64)>> {
    let Some(latest) = latest else {
        return Ok(None);
    };
    let trimmed = py_strip(latest);
    if trimmed.is_empty() {
        return Ok(None);
    }
    let mut text = trimmed.to_string();
    if text.chars().next().is_some_and(|ch| ch.is_ascii_digit()) && text.contains('T') {
        text = text
            .split_once('T')
            .map(|(_, rest)| rest.to_string())
            .unwrap_or(text);
    }
    let cleaned = text.replace(',', " ");
    let parts: Vec<&str> = cleaned
        .split(py_space)
        .filter(|part| !part.is_empty())
        .collect();
    let Some(time_part) = parts.last().copied() else {
        return Err(EngineError::index("list index out of range"));
    };
    let mut day = last_day()?;
    if parts.len() >= 2 {
        let name = parts[0].to_lowercase();
        if let Some((_, index)) = day_name_to_index()
            .into_iter()
            .find(|(key, _)| *key == name)
        {
            day = D::from(index);
        }
    }
    Ok(Some((day, hhmm_to_minutes(time_part)?)))
}

pub fn occupancy_mask(start_slot: i64, n_slots: i64) -> EngineResult<u128> {
    if n_slots <= 0 || start_slot < 0 || start_slot + n_slots > SLOTS_PER_DAY {
        return Err(EngineError::value(
            "occupancy range is outside the 00:00–24:00 grid",
        ));
    }
    let width = u32::try_from(n_slots)
        .map_err(|_| EngineError::value("occupancy range is outside the 00:00–24:00 grid"))?;
    let shift = u32::try_from(start_slot)
        .map_err(|_| EngineError::value("occupancy range is outside the 00:00–24:00 grid"))?;
    Ok(((1u128 << width) - 1) << shift)
}

pub fn occupancy_between(start_min: i64, end_min: i64) -> EngineResult<u128> {
    let start_min = start_min.max(DAY_START_MIN);
    let end_min = end_min.min(DAY_END_MIN);
    if end_min <= start_min {
        return Ok(0);
    }
    let first = (start_min - DAY_START_MIN).div_euclid(SLOT_MIN);
    let last = -(-(end_min - DAY_START_MIN)).div_euclid(SLOT_MIN);
    occupancy_mask(first, last - first)
}

fn iso_date() -> &'static Regex {
    static PATTERN: LazyLock<Regex> =
        LazyLock::new(|| Regex::new(r"\A\d{4}-\d{2}-\d{2}\z").expect("date pattern"));
    &PATTERN
}

fn iso_month() -> &'static Regex {
    static PATTERN: LazyLock<Regex> =
        LazyLock::new(|| Regex::new(r"\A[0-9]{4}-[0-9]{2}\z").expect("month pattern"));
    &PATTERN
}

fn leap(year: i32) -> bool {
    year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
}

fn last_day(year: i32, month: u32) -> u32 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if leap(year) {
                29
            } else {
                28
            }
        }
        _ => 0,
    }
}

pub(crate) fn date_from_iso(value: &str) -> EngineResult<NaiveDate> {
    if let Some(parsed) = calendar_date(value, true)? {
        return Ok(parsed);
    }
    if let Some(parsed) = week_date(value)? {
        return Ok(parsed);
    }
    if let Some(parsed) = calendar_date(value, false)? {
        return Ok(parsed);
    }
    Err(EngineError::value(format!(
        "Invalid isoformat string: {}",
        py_repr(value)
    )))
}

fn ascii_digits(text: &str, n: usize) -> Option<&str> {
    if text.len() == n && text.bytes().all(|byte| byte.is_ascii_digit()) {
        Some(text)
    } else {
        None
    }
}

fn calendar_date(value: &str, dashed: bool) -> EngineResult<Option<NaiveDate>> {
    let (year, month, day) = if dashed {
        let Some(year) = ascii_digits(value.get(0..4).unwrap_or(""), 4) else {
            return Ok(None);
        };
        if value.as_bytes().get(4) != Some(&b'-') || value.as_bytes().get(7) != Some(&b'-') {
            return Ok(None);
        }
        let Some(month) = ascii_digits(value.get(5..7).unwrap_or(""), 2) else {
            return Ok(None);
        };
        let Some(day) = ascii_digits(value.get(8..10).unwrap_or(""), 2) else {
            return Ok(None);
        };
        if value.len() != 10 {
            return Ok(None);
        }
        (year, month, day)
    } else {
        if value.len() != 8 {
            return Ok(None);
        }
        let Some(year) = ascii_digits(value.get(0..4).unwrap_or(""), 4) else {
            return Ok(None);
        };
        let Some(month) = ascii_digits(value.get(4..6).unwrap_or(""), 2) else {
            return Ok(None);
        };
        let Some(day) = ascii_digits(value.get(6..8).unwrap_or(""), 2) else {
            return Ok(None);
        };
        (year, month, day)
    };
    let joined = format!("{year}-{month}-{day}");
    from_iso(&joined).map(Some)
}

fn week_date(value: &str) -> EngineResult<Option<NaiveDate>> {
    let bytes = value.as_bytes();
    let (year, week, day) =
        if bytes.len() == 8 && bytes.get(4) == Some(&b'-') && bytes.get(5) == Some(&b'W') {
            let Some(year) = ascii_digits(value.get(0..4).unwrap_or(""), 4) else {
                return Ok(None);
            };
            let Some(week) = ascii_digits(value.get(6..8).unwrap_or(""), 2) else {
                return Ok(None);
            };
            (year, week, "1")
        } else if bytes.len() == 10
            && bytes.get(4) == Some(&b'-')
            && bytes.get(5) == Some(&b'W')
            && bytes.get(8) == Some(&b'-')
        {
            let Some(year) = ascii_digits(value.get(0..4).unwrap_or(""), 4) else {
                return Ok(None);
            };
            let Some(week) = ascii_digits(value.get(6..8).unwrap_or(""), 2) else {
                return Ok(None);
            };
            let Some(day) = ascii_digits(value.get(9..10).unwrap_or(""), 1) else {
                return Ok(None);
            };
            (year, week, day)
        } else if bytes.len() == 7 && bytes.get(4) == Some(&b'W') {
            let Some(year) = ascii_digits(value.get(0..4).unwrap_or(""), 4) else {
                return Ok(None);
            };
            let Some(week) = ascii_digits(value.get(5..7).unwrap_or(""), 2) else {
                return Ok(None);
            };
            (year, week, "1")
        } else if bytes.len() == 8 && bytes.get(4) == Some(&b'W') {
            let Some(year) = ascii_digits(value.get(0..4).unwrap_or(""), 4) else {
                return Ok(None);
            };
            let Some(week) = ascii_digits(value.get(5..7).unwrap_or(""), 2) else {
                return Ok(None);
            };
            let Some(day) = ascii_digits(value.get(7..8).unwrap_or(""), 1) else {
                return Ok(None);
            };
            (year, week, day)
        } else {
            return Ok(None);
        };
    let year: i32 = year.parse().unwrap_or(0);
    let week: u32 = week.parse().unwrap_or(0);
    let day: u32 = day.parse().unwrap_or(0);
    let weekday = match day {
        1 => chrono::Weekday::Mon,
        2 => chrono::Weekday::Tue,
        3 => chrono::Weekday::Wed,
        4 => chrono::Weekday::Thu,
        5 => chrono::Weekday::Fri,
        6 => chrono::Weekday::Sat,
        7 => chrono::Weekday::Sun,
        _ => {
            return Err(EngineError::value(format!(
                "Invalid isoformat string: {}",
                py_repr(value)
            )));
        }
    };
    NaiveDate::from_isoywd_opt(year, week, weekday)
        .map(Some)
        .ok_or_else(|| EngineError::value(format!("Invalid isoformat string: {}", py_repr(value))))
}

pub(crate) fn shift_days(day: NaiveDate, days: i64) -> EngineResult<NaiveDate> {
    let next = day
        .checked_add_signed(Duration::days(days))
        .ok_or_else(|| EngineError::overflow("date value out of range"))?;
    if !(1..=9999).contains(&next.year()) {
        return Err(EngineError::overflow("date value out of range"));
    }
    Ok(next)
}

fn from_iso(value: &str) -> EngineResult<NaiveDate> {
    if !value.is_ascii() {
        return Err(EngineError::value(format!(
            "Invalid isoformat string: {}",
            py_repr(value)
        )));
    }
    let year: i32 = value[0..4]
        .parse()
        .map_err(|_| EngineError::value(format!("Invalid isoformat string: {}", py_repr(value))))?;
    if !(1..=9999).contains(&year) {
        return Err(EngineError::value(format!(
            "year must be in 1..9999, not {year}"
        )));
    }
    let month: u32 = value[5..7]
        .parse()
        .map_err(|_| EngineError::value(format!("Invalid isoformat string: {}", py_repr(value))))?;
    let day: u32 = value[8..10]
        .parse()
        .map_err(|_| EngineError::value(format!("Invalid isoformat string: {}", py_repr(value))))?;
    if !(1..=12).contains(&month) {
        return Err(EngineError::value(format!(
            "month must be in 1..12, not {month}"
        )));
    }
    let last = last_day(year, month);
    if day < 1 || day > last {
        return Err(EngineError::value(format!(
            "day {day} must be in range 1..{last} for month {month} in year {year}"
        )));
    }
    NaiveDate::from_ymd_opt(year, month, day)
        .ok_or_else(|| EngineError::value(format!("Invalid isoformat string: {}", py_repr(value))))
}

fn in_supported_range(day: NaiveDate) -> bool {
    let first = NaiveDate::from_ymd_opt(FIRST_DAY.0, FIRST_DAY.1, FIRST_DAY.2).expect("first");
    let last = NaiveDate::from_ymd_opt(LAST_DAY.0, LAST_DAY.1, LAST_DAY.2).expect("last");
    first <= day && day <= last
}

fn parse_supported(value: &str) -> EngineResult<NaiveDate> {
    if !iso_date().is_match(value) {
        return Err(EngineError::value("date must be written YYYY-MM-DD"));
    }
    let day = from_iso(value)?;
    if !in_supported_range(day) {
        return Err(EngineError::value(
            "date must be between 2000-01-01 and 2099-12-31",
        ));
    }
    Ok(day)
}

fn iso(day: NaiveDate) -> String {
    format!("{:04}-{:02}-{:02}", day.year(), day.month(), day.day())
}

pub fn monday_of(date_str: &str) -> EngineResult<String> {
    let day = parse_supported(date_str)?;
    let monday = day - Duration::days(i64::from(day.weekday().num_days_from_monday()));
    Ok(iso(monday))
}

pub fn is_week_start(value: &str) -> bool {
    if !iso_date().is_match(value) {
        return false;
    }
    let Ok(day) = from_iso(value) else {
        return false;
    };
    day.weekday().num_days_from_monday() == 0
        && (in_supported_range(day) || iso(day) == FIRST_WEEK_START)
}

pub fn is_calendar_date(value: &str) -> bool {
    parse_supported(value).is_ok()
}

pub fn parse_month(value: &str) -> EngineResult<(String, String)> {
    if !iso_month().is_match(value) {
        return Err(EngineError::value("month must be written YYYY-MM"));
    }
    let year: i32 = value[0..4].parse().unwrap_or(0);
    let month: u32 = value[5..7].parse().unwrap_or(0);
    if !(1..=9999).contains(&year) {
        return Err(EngineError::value(format!(
            "year must be in 1..9999, not {year}"
        )));
    }
    if !(1..=12).contains(&month) {
        return Err(EngineError::value("month must be written YYYY-MM"));
    }
    let start = NaiveDate::from_ymd_opt(year, month, 1)
        .ok_or_else(|| EngineError::value("month must be written YYYY-MM"))?;
    let end = NaiveDate::from_ymd_opt(year, month, last_day(year, month))
        .ok_or_else(|| EngineError::value("month must be written YYYY-MM"))?;
    let first = NaiveDate::from_ymd_opt(FIRST_DAY.0, FIRST_DAY.1, FIRST_DAY.2).expect("first");
    let last = NaiveDate::from_ymd_opt(LAST_DAY.0, LAST_DAY.1, LAST_DAY.2).expect("last");
    if start < first || start > last {
        return Err(EngineError::value(
            "date must be between 2000-01-01 and 2099-12-31",
        ));
    }
    Ok((iso(start), iso(end)))
}

pub fn is_month_label(value: &str) -> bool {
    parse_month(value).is_ok()
}

pub fn month_grid(start: &str, end: &str) -> EngineResult<(String, String)> {
    let start = from_iso(start)?;
    let end = from_iso(end)?;
    let mut grid_start = start - Duration::days(i64::from(start.weekday().num_days_from_monday()));
    let mut grid_end = end + Duration::days(i64::from(6 - end.weekday().num_days_from_monday()));
    let first = NaiveDate::from_ymd_opt(FIRST_DAY.0, FIRST_DAY.1, FIRST_DAY.2).expect("first");
    let last = NaiveDate::from_ymd_opt(LAST_DAY.0, LAST_DAY.1, LAST_DAY.2).expect("last");
    if grid_start < first {
        grid_start = first;
    }
    if grid_end > last {
        grid_end = last;
    }
    Ok((iso(grid_start), iso(grid_end)))
}

#[cfg(test)]
mod tests {
    use super::monday_of;

    #[test]
    fn new_years_day_2000_belongs_to_the_week_before_the_range() {
        assert_eq!(monday_of("2000-01-01").unwrap(), "1999-12-27");
    }

    #[test]
    fn a_non_monday_is_not_a_week_start_and_the_edge_monday_is() {
        assert!(super::is_week_start("1999-12-27"));
        assert!(!super::is_week_start("1999-12-20"));
        assert_eq!(super::parse_month("2026-02").unwrap().1, "2026-02-28");
    }
}
