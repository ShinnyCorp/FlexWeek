use flexweek_engine::ErrorKind;
use flexweek_engine::time::{is_month_label, is_week_start, monday_of, month_grid, parse_month};

fn value_error<T>(result: Result<T, flexweek_engine::EngineError>, case: &str) {
    match result {
        Err(err) if err.kind == ErrorKind::Value => {}
        Err(err) => panic!("{case}: {err:?}"),
        Ok(_) => panic!("{case}: expected a value error"),
    }
}

#[test]
fn test_monday_of_maps_every_day_of_one_week_to_its_monday() {
    for day in [
        "2026-09-07",
        "2026-09-08",
        "2026-09-09",
        "2026-09-10",
        "2026-09-11",
        "2026-09-12",
        "2026-09-13",
    ] {
        assert_eq!(monday_of(day).unwrap(), "2026-09-07", "{day}");
    }
}

#[test]
fn test_monday_of_rejects_malformed_and_non_calendar_shapes() {
    for value in [
        "",
        "2026-09-7",
        "not-a-date",
        "2026-13-40",
        "20260907",
        "2026-W37-1",
    ] {
        value_error(monday_of(value), value);
    }
}

#[test]
fn test_monday_of_accepts_the_range_boundaries_and_rejects_outside_them() {
    assert_eq!(monday_of("2000-01-01").unwrap(), "1999-12-27");
    assert_eq!(monday_of("2000-01-03").unwrap(), "2000-01-03");
    assert_eq!(monday_of("2099-12-31").unwrap(), "2099-12-28");
    value_error(monday_of("1999-12-31"), "1999-12-31");
    value_error(monday_of("2100-01-01"), "2100-01-01");
}

#[test]
fn test_is_week_start_is_true_only_for_an_in_range_monday() {
    assert!(is_week_start("2026-09-07"));
    assert!(is_week_start("1999-12-27"));
    for value in [
        "2026-09-08",
        "2026-09-13",
        "2026-9-7",
        "20260907",
        "2026-W37-1",
        "1999-12-20",
        "1999-12-28",
        "2100-01-04",
    ] {
        assert!(!is_week_start(value), "{value}");
    }
}

#[test]
fn test_monday_of_crosses_month_and_year_boundaries() {
    assert_eq!(monday_of("2026-10-01").unwrap(), "2026-09-28");
    assert_eq!(monday_of("2027-01-01").unwrap(), "2026-12-28");
}

#[test]
fn test_parse_month_returns_first_and_last_calendar_dates() {
    assert_eq!(
        parse_month("2026-09").unwrap(),
        ("2026-09-01".into(), "2026-09-30".into())
    );
    assert_eq!(
        parse_month("2026-02").unwrap(),
        ("2026-02-01".into(), "2026-02-28".into())
    );
    assert_eq!(
        parse_month("2000-01").unwrap(),
        ("2000-01-01".into(), "2000-01-31".into())
    );
    assert_eq!(
        parse_month("2099-12").unwrap(),
        ("2099-12-01".into(), "2099-12-31".into())
    );
}

#[test]
fn test_parse_month_rejects_malformed_and_out_of_range_labels() {
    for value in [
        "",
        "2026-9",
        "2026-09-01",
        "2026-13",
        "1999-12",
        "2100-01",
        "202609",
    ] {
        value_error(parse_month(value), value);
        assert!(!is_month_label(value), "{value}");
    }
    assert!(is_month_label("2026-09"));
}

#[test]
fn test_month_grid_pads_complete_weeks_and_clips_the_supported_range() {
    assert_eq!(
        month_grid("2026-09-01", "2026-09-30").unwrap(),
        ("2026-08-31".into(), "2026-10-04".into())
    );
    assert_eq!(
        month_grid("2000-01-01", "2000-01-31").unwrap(),
        ("2000-01-01".into(), "2000-02-06".into())
    );
    assert_eq!(
        month_grid("2099-12-01", "2099-12-31").unwrap(),
        ("2099-11-30".into(), "2099-12-31".into())
    );
}
