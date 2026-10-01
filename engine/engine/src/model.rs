//! `backend/models.py` validation helpers (not the pydantic models).

use std::sync::LazyLock;

use chrono::NaiveDate;
use regex::Regex;

use crate::error::{EngineError, EngineResult};

pub const END_OF_DAY_MIN: i64 = 24 * 60;
pub const END_OF_DAY_CLOCK: &str = "23:59";
pub const ESTIMATE_MAX_MIN: i64 = 24 * 60;

const FIRST_DAY: (i32, u32, u32) = (2000, 1, 1);
const LAST_DAY: (i32, u32, u32) = (2099, 12, 31);
pub const LAST_DAY_ISO: &str = "2099-12-31";

fn naive_stamp() -> &'static Regex {
    static PATTERN: LazyLock<Regex> = LazyLock::new(|| {
        Regex::new(r"\A(\d{4}-\d{2}-\d{2})T((?:[01]\d|2[0-3]):[0-5]\d)\z").expect("naive stamp")
    });
    &PATTERN
}

fn naive_date() -> &'static Regex {
    static PATTERN: LazyLock<Regex> =
        LazyLock::new(|| Regex::new(r"\A(\d{4}-\d{2}-\d{2})\z").expect("naive date"));
    &PATTERN
}

fn spotify_share() -> &'static Regex {
    static PATTERN: LazyLock<Regex> = LazyLock::new(|| {
        Regex::new(
            r"\Ahttps://open\.spotify\.com/(track|playlist|album|episode|show)/[A-Za-z0-9]+/?(?:[?#].*)?\z",
        )
        .expect("spotify")
    });
    &PATTERN
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

fn leap(year: i32) -> bool {
    year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
}

fn last_day_of_month(year: i32, month: u32) -> u32 {
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

fn from_isoformat(text: &str) -> EngineResult<NaiveDate> {
    if text.len() != 10 || text.as_bytes()[4] != b'-' || text.as_bytes()[7] != b'-' {
        return Err(EngineError::value(format!(
            "Invalid isoformat string: {}",
            py_repr(text)
        )));
    }
    let year: i32 = text[0..4]
        .parse()
        .map_err(|_| EngineError::value(format!("Invalid isoformat string: {}", py_repr(text))))?;
    let month: u32 = text[5..7]
        .parse()
        .map_err(|_| EngineError::value(format!("Invalid isoformat string: {}", py_repr(text))))?;
    let day: u32 = text[8..10]
        .parse()
        .map_err(|_| EngineError::value(format!("Invalid isoformat string: {}", py_repr(text))))?;
    if !(1..=12).contains(&month) {
        return Err(EngineError::value(format!(
            "month must be in 1..12, not {month}"
        )));
    }
    let last = last_day_of_month(year, month);
    if day < 1 || day > last {
        return Err(EngineError::value(format!(
            "day {day} must be in range 1..{last} for month {month} in year {year}"
        )));
    }
    NaiveDate::from_ymd_opt(year, month, day)
        .ok_or_else(|| EngineError::value(format!("Invalid isoformat string: {}", py_repr(text))))
}

fn in_supported_range(day: NaiveDate) -> bool {
    let first = NaiveDate::from_ymd_opt(FIRST_DAY.0, FIRST_DAY.1, FIRST_DAY.2).expect("first");
    let last = NaiveDate::from_ymd_opt(LAST_DAY.0, LAST_DAY.1, LAST_DAY.2).expect("last");
    first <= day && day <= last
}

pub fn iso_day(text: &str) -> EngineResult<NaiveDate> {
    let day = from_isoformat(text)?;
    if !in_supported_range(day) {
        return Err(EngineError::value(
            "date must be between 2000-01-01 and 2099-12-31",
        ));
    }
    Ok(day)
}

pub fn parse_naive_stamp(value: &str) -> EngineResult<(NaiveDate, i64)> {
    let caps = naive_stamp().captures(value).ok_or_else(|| {
        EngineError::value("must be YYYY-MM-DDTHH:MM with no seconds or timezone")
    })?;
    let hour_minute = caps.get(2).expect("time").as_str();
    let parts: Vec<&str> = hour_minute.split(':').collect();
    let hour: i64 = parts[0].parse().unwrap();
    let minute: i64 = parts[1].parse().unwrap();
    Ok((
        iso_day(caps.get(1).expect("date").as_str())?,
        hour * 60 + minute,
    ))
}

pub fn parse_due(value: &str) -> EngineResult<(NaiveDate, i64)> {
    if naive_date().is_match(value) {
        return Ok((iso_day(value)?, END_OF_DAY_MIN));
    }
    let caps = naive_stamp().captures(value).ok_or_else(|| {
        EngineError::value("must be YYYY-MM-DD or YYYY-MM-DDTHH:MM with no seconds or timezone")
    })?;
    let day = iso_day(caps.get(1).expect("date").as_str())?;
    let clock = caps.get(2).expect("time").as_str();
    if clock == END_OF_DAY_CLOCK {
        return Ok((day, END_OF_DAY_MIN));
    }
    let parts: Vec<&str> = clock.split(':').collect();
    let hour: i64 = parts[0].parse().unwrap();
    let minute: i64 = parts[1].parse().unwrap();
    Ok((day, hour * 60 + minute))
}

pub fn due_is_timed(value: &str) -> bool {
    naive_stamp()
        .captures(value)
        .is_some_and(|caps| caps.get(2).expect("time").as_str() != END_OF_DAY_CLOCK)
}

pub fn due_sort_key(due: Option<&str>, item_id: &str) -> EngineResult<(NaiveDate, i64, String)> {
    let Some(due) = due.filter(|s| !s.is_empty()) else {
        let max = NaiveDate::from_ymd_opt(9999, 12, 31).expect("max date");
        return Ok((max, END_OF_DAY_MIN, item_id.to_string()));
    };
    let (day, minute) = parse_due(due)?;
    Ok((day, minute, item_id.to_string()))
}

pub fn valid_naive_stamp(value: &str) -> EngineResult<String> {
    parse_naive_stamp(value)?;
    Ok(value.to_string())
}

pub fn valid_due(value: &str) -> EngineResult<String> {
    parse_due(value)?;
    Ok(value.to_string())
}

struct UrlParts {
    scheme: Option<String>,
    hostname: Option<String>,
    username: Option<String>,
    password: Option<String>,
    port: Option<u16>,
}

fn urlsplit(value: &str) -> UrlParts {
    let mut scheme = None;
    let mut rest = value;
    if let Some((left, right)) = value.split_once("://") {
        scheme = Some(left.to_ascii_lowercase());
        rest = right;
    }
    let (authority, _) = rest
        .split_once('/')
        .map(|(a, b)| (a, Some(b)))
        .unwrap_or((rest, None));
    let (userinfo, hostport) = authority
        .rsplit_once('@')
        .map(|(u, h)| (Some(u), h))
        .unwrap_or((None, authority));
    let (username, password) = userinfo
        .map(|ui| {
            ui.split_once(':')
                .map(|(u, p)| (Some(u.to_string()), Some(p.to_string())))
                .unwrap_or((Some(ui.to_string()), None))
        })
        .unwrap_or((None, None));
    let (hostname, port) = if hostport.starts_with('[') {
        if let Some((inside, after)) = hostport.split_once(']') {
            let host = inside.trim_start_matches('[');
            let port = after.strip_prefix(':').and_then(|p| p.parse().ok());
            (Some(host.to_string()), port)
        } else {
            (Some(hostport.to_string()), None)
        }
    } else if let Some((host, port_str)) = hostport.rsplit_once(':') {
        if host.contains(':') || port_str.parse::<u16>().is_err() {
            (Some(hostport.to_ascii_lowercase()), None)
        } else {
            (Some(host.to_ascii_lowercase()), port_str.parse().ok())
        }
    } else {
        (Some(hostport.to_ascii_lowercase()), None)
    };
    UrlParts {
        scheme,
        hostname,
        username,
        password,
        port,
    }
}

const SPOTIFY_ERR: &str = "spotify_url must be an open.spotify.com share link";
const HTTP_ERR: &str = "link url must be an http or https URL";

pub fn valid_spotify_url(value: Option<&str>) -> EngineResult<Option<String>> {
    let Some(value) = value.filter(|s| !s.is_empty()) else {
        return Ok(None);
    };
    if !spotify_share().is_match(value) {
        return Err(EngineError::value(SPOTIFY_ERR));
    }
    let parsed = urlsplit(value);
    if parsed.username.is_some() || parsed.password.is_some() || parsed.port.is_some() {
        return Err(EngineError::value(SPOTIFY_ERR));
    }
    Ok(Some(value.to_string()))
}

pub fn valid_http_url(value: &str) -> EngineResult<String> {
    let parsed = urlsplit(value);
    let scheme_ok = parsed
        .scheme
        .as_deref()
        .is_some_and(|s| s == "http" || s == "https");
    if !scheme_ok || parsed.hostname.as_deref().is_none_or(|h| h.is_empty()) {
        return Err(EngineError::value(HTTP_ERR));
    }
    if parsed.username.is_some() || parsed.password.is_some() {
        return Err(EngineError::value(HTTP_ERR));
    }
    Ok(value.to_string())
}

#[cfg(test)]
mod tests {
    use chrono::Datelike;

    use super::*;

    #[test]
    fn parse_naive_stamp_matches_python() {
        let (day, min) = parse_naive_stamp("2024-06-15T14:30").unwrap();
        assert_eq!(day.year(), 2024);
        assert_eq!(day.month(), 6);
        assert_eq!(day.day(), 15);
        assert_eq!(min, 870);
    }

    #[test]
    fn parse_due_shapes_match_python() {
        let (d, m) = parse_due("2024-06-15").unwrap();
        assert_eq!(d.to_string(), "2024-06-15");
        assert_eq!(m, 1440);
        let (_, m) = parse_due("2024-06-15T23:59").unwrap();
        assert_eq!(m, 1440);
        let (_, m) = parse_due("2024-06-15T09:00").unwrap();
        assert_eq!(m, 540);
    }

    #[test]
    fn due_is_timed_matches_python() {
        assert!(!due_is_timed("2024-06-15"));
        assert!(due_is_timed("2024-06-15T09:00"));
        assert!(!due_is_timed("2024-06-15T23:59"));
    }

    #[test]
    fn due_sort_key_matches_python() {
        let (d, m, id) = due_sort_key(None, "x").unwrap();
        assert_eq!(d.to_string(), "9999-12-31");
        assert_eq!(m, 1440);
        assert_eq!(id, "x");
        let (d, m, id) = due_sort_key(Some("2024-06-15"), "abc").unwrap();
        assert_eq!(d.to_string(), "2024-06-15");
        assert_eq!(m, 1440);
        assert_eq!(id, "abc");
    }

    #[test]
    fn spotify_and_http_validation() {
        assert_eq!(
            valid_spotify_url(Some("https://open.spotify.com/track/abc123")).unwrap(),
            Some("https://open.spotify.com/track/abc123".to_string())
        );
        assert_eq!(valid_spotify_url(None).unwrap(), None);
        assert!(
            valid_spotify_url(Some("https://user:pass@open.spotify.com/track/abc123")).is_err()
        );
        assert_eq!(
            valid_http_url("https://example.com/path").unwrap(),
            "https://example.com/path"
        );
        assert!(valid_http_url("ftp://x.com").is_err());
    }
}
