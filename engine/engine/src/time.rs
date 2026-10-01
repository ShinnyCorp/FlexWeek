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

fn py_repr(text: &str) -> String {
    let mut out = String::from("'");
    for ch in text.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '\'' => out.push_str("\\'"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            other => out.push(other),
        }
    }
    out.push('\'');
    out
}

fn parse_int(raw: &str) -> EngineResult<i64> {
    let trimmed = raw.trim();
    let fail = || {
        EngineError::value(format!(
            "invalid literal for int() with base 10: {}",
            py_repr(raw)
        ))
    };
    if trimmed.is_empty() {
        return Err(fail());
    }
    let (sign, rest) = match trimmed.as_bytes()[0] {
        b'+' => (1i64, &trimmed[1..]),
        b'-' => (-1i64, &trimmed[1..]),
        _ => (1i64, trimmed),
    };
    if rest.is_empty() || rest.starts_with('_') || rest.ends_with('_') {
        return Err(fail());
    }
    let mut digits = String::new();
    let mut prev_underscore = false;
    for byte in rest.bytes() {
        if byte == b'_' {
            if prev_underscore {
                return Err(fail());
            }
            prev_underscore = true;
            continue;
        }
        if !byte.is_ascii_digit() {
            return Err(fail());
        }
        prev_underscore = false;
        digits.push(byte as char);
    }
    if digits.is_empty() {
        return Err(fail());
    }
    let magnitude: i64 = digits.parse().map_err(|_| fail())?;
    Ok(sign * magnitude)
}

pub fn hhmm_to_minutes(hhmm: &str) -> EngineResult<i64> {
    let parts: Vec<&str> = hhmm.split(':').collect();
    if parts.len() != 2 {
        return Err(EngineError::value(format!(
            "expected HH:MM, got {}",
            py_repr(hhmm)
        )));
    }
    let hour = parse_int(parts[0])?;
    let minute = parse_int(parts[1])?;
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
    let Some(latest) = latest else {
        return Ok(None);
    };
    let trimmed = latest.trim();
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
    let parts: Vec<&str> = cleaned.split_whitespace().collect();
    if parts.is_empty() {
        return Ok(None);
    }
    let time_part = parts[parts.len() - 1];
    let mut day = days.iter().copied().max().unwrap_or(0);
    if parts.len() >= 2 {
        let name = parts[0].to_lowercase();
        if let Some((_, index)) = day_name_to_index()
            .into_iter()
            .find(|(key, _)| *key == name)
        {
            day = index;
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
