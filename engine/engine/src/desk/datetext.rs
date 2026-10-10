//! The app's one short and one long way to write a date. English names, day before month, all in
//! the tables below, so another language means changing them. `today` always comes in as an
//! argument: the year is written only when it is not today's, and the engine never reads a clock.

use chrono::{Datelike, NaiveDate};

use crate::desk::pydate::from_iso;
use crate::error::EngineResult;

const DAYS_SHORT: [&str; 7] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAYS_LONG: [&str; 7] = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
];
const MONTHS_SHORT: [&str; 12] = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];
const MONTHS_LONG: [&str; 12] = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
];

/// A day as the app stores it, `YYYY-MM-DD`, for callers outside the crate.
pub fn day_of(iso: &str) -> EngineResult<NaiveDate> {
    from_iso(iso)
}

fn month_name(date: NaiveDate, short: bool) -> &'static str {
    let names = if short { &MONTHS_SHORT } else { &MONTHS_LONG };
    names[date.month0() as usize]
}

fn with_year(text: String, date: NaiveDate, today: NaiveDate) -> String {
    if date.year() == today.year() {
        text
    } else {
        format!("{text} {}", date.year())
    }
}

/// "Thu 1 Oct", or "Fri 8 Jan 2027" outside the current year.
pub fn day_short(date: NaiveDate, today: NaiveDate) -> String {
    let weekday = DAYS_SHORT[date.weekday().num_days_from_monday() as usize];
    with_year(
        format!("{weekday} {} {}", date.day(), month_name(date, true)),
        date,
        today,
    )
}

/// "Thursday 1 October", or "Friday 8 January 2027" outside the current year.
pub fn day_long(date: NaiveDate, today: NaiveDate) -> String {
    let weekday = DAYS_LONG[date.weekday().num_days_from_monday() as usize];
    with_year(
        format!("{weekday} {} {}", date.day(), month_name(date, false)),
        date,
        today,
    )
}

/// The week that starts on `start`: "5 – 11 Oct", "28 Sep – 4 Oct", and the end date carries its
/// year when the week crosses New Year ("28 Dec – 3 Jan 2027") or lies outside the current year.
pub fn week_range(start: NaiveDate, today: NaiveDate) -> EngineResult<String> {
    let end = crate::stored::add_days(start, 6)?;
    let crosses = start.year() != end.year();
    let first = if start.month() == end.month() && !crosses {
        start.day().to_string()
    } else {
        format!("{} {}", start.day(), month_name(start, true))
    };
    let last = format!("{} {}", end.day(), month_name(end, true));
    let last = if crosses {
        format!("{last} {}", end.year())
    } else {
        with_year(last, end, today)
    };
    Ok(format!("{first} – {last}"))
}

/// "October 2026", or "Oct 2026" where space is short. The year is always there.
pub fn month_title(date: NaiveDate, short: bool) -> String {
    format!("{} {}", month_name(date, short), date.year())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn on(year: i32, month: u32, day: u32) -> NaiveDate {
        NaiveDate::from_ymd_opt(year, month, day).expect("a real date")
    }

    #[test]
    fn a_short_day_has_no_year_in_the_current_year() {
        assert_eq!(day_short(on(2026, 10, 1), on(2026, 10, 9)), "Thu 1 Oct");
    }

    #[test]
    fn a_short_day_in_another_year_carries_the_year() {
        assert_eq!(day_short(on(2027, 1, 8), on(2026, 10, 9)), "Fri 8 Jan 2027");
        assert_eq!(
            day_short(on(2025, 12, 31), on(2026, 1, 2)),
            "Wed 31 Dec 2025"
        );
    }

    #[test]
    fn a_long_day_has_no_comma_and_a_year_only_outside_the_current_year() {
        assert_eq!(
            day_long(on(2026, 10, 1), on(2026, 10, 9)),
            "Thursday 1 October"
        );
        assert_eq!(
            day_long(on(2027, 1, 8), on(2026, 10, 9)),
            "Friday 8 January 2027"
        );
    }

    #[test]
    fn a_week_inside_one_month_names_the_month_once() {
        assert_eq!(
            week_range(on(2026, 10, 5), on(2026, 10, 9)).unwrap(),
            "5 – 11 Oct"
        );
    }

    #[test]
    fn a_week_across_two_months_names_both() {
        assert_eq!(
            week_range(on(2026, 9, 28), on(2026, 10, 9)).unwrap(),
            "28 Sep – 4 Oct"
        );
    }

    #[test]
    fn a_new_year_week_puts_the_year_on_its_end_date() {
        assert_eq!(
            week_range(on(2026, 12, 28), on(2026, 12, 30)).unwrap(),
            "28 Dec – 3 Jan 2027"
        );
        assert_eq!(
            week_range(on(2026, 12, 28), on(2027, 1, 1)).unwrap(),
            "28 Dec – 3 Jan 2027"
        );
    }

    #[test]
    fn a_week_in_another_year_carries_that_year() {
        assert_eq!(
            week_range(on(2027, 1, 4), on(2026, 10, 9)).unwrap(),
            "4 – 10 Jan 2027"
        );
    }

    #[test]
    fn a_month_title_always_has_its_year() {
        assert_eq!(month_title(on(2026, 10, 1), false), "October 2026");
        assert_eq!(month_title(on(2026, 10, 1), true), "Oct 2026");
        assert_eq!(month_title(on(2027, 3, 31), false), "March 2027");
    }
}
