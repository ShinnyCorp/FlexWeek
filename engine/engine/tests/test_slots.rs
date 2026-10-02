use flexweek_engine::ErrorKind;
use flexweek_engine::time::{
    SLOTS_PER_DAY, hhmm_to_minutes, hhmm_to_slot, minutes_to_hhmm, overlaps, parse_deadline,
    slot_to_hhmm,
};

fn value_error<T>(result: Result<T, flexweek_engine::EngineError>, case: &str) {
    match result {
        Err(err) if err.kind == ErrorKind::Value => {}
        Err(err) => panic!("{case}: {err:?}"),
        Ok(_) => panic!("{case}: expected a value error"),
    }
}

#[test]
fn test_slots_per_day_is_96() {
    assert_eq!(SLOTS_PER_DAY, 96);
}

#[test]
fn test_hhmm_roundtrip() {
    assert_eq!(minutes_to_hhmm(hhmm_to_minutes("00:00").unwrap()), "00:00");
    assert_eq!(minutes_to_hhmm(hhmm_to_minutes("06:00").unwrap()), "06:00");
    assert_eq!(minutes_to_hhmm(hhmm_to_minutes("23:00").unwrap()), "23:00");
    assert_eq!(minutes_to_hhmm(1440), "24:00");
    assert_eq!(
        slot_to_hhmm(hhmm_to_slot("00:00").unwrap()).unwrap(),
        "00:00"
    );
    assert_eq!(
        slot_to_hhmm(hhmm_to_slot("06:00").unwrap()).unwrap(),
        "06:00"
    );
    assert_eq!(
        slot_to_hhmm(hhmm_to_slot("16:00").unwrap()).unwrap(),
        "16:00"
    );
    assert_eq!(
        slot_to_hhmm(hhmm_to_slot("23:45").unwrap()).unwrap(),
        "23:45"
    );
}

#[test]
fn test_rejects_off_grid_time() {
    value_error(hhmm_to_slot("08:10"), "08:10");
}

#[test]
fn test_midnight_is_a_legal_start() {
    assert_eq!(hhmm_to_slot("00:00").unwrap(), 0);
    assert_eq!(hhmm_to_slot("05:45").unwrap(), 23);
}

#[test]
fn test_rejects_day_end_as_start() {
    value_error(hhmm_to_minutes("24:00"), "24:00");
    value_error(slot_to_hhmm(SLOTS_PER_DAY), "slot 96");
}

#[test]
fn test_rejects_bad_hhmm() {
    value_error(hhmm_to_minutes("8"), "8");
    value_error(hhmm_to_minutes("24:00"), "24:00");
}

#[test]
fn test_overlaps_half_open() {
    assert!(overlaps(8 * 60, 9 * 60, 8 * 60 + 30, 9 * 60 + 30));
    assert!(!overlaps(8 * 60, 9 * 60, 9 * 60, 10 * 60));
    assert!(!overlaps(10 * 60, 11 * 60, 8 * 60, 9 * 60));
}

#[test]
fn test_parse_deadline_english_weekday() {
    assert_eq!(
        parse_deadline(Some("Thursday 21:00"), &[0, 1, 2, 3, 4]).unwrap(),
        Some((3, 21 * 60))
    );
    assert_eq!(
        parse_deadline(Some("Wednesday 07:45"), &[0, 1, 2]).unwrap(),
        Some((2, 7 * 60 + 45))
    );
}

#[test]
fn test_parse_deadline_iso_timestamp_uses_time_only() {
    assert_eq!(
        parse_deadline(Some("2026-09-10T21:00"), &[0, 1, 2, 3]).unwrap(),
        Some((3, 21 * 60))
    );
}

#[test]
fn test_parse_deadline_bare_time_uses_last_day() {
    assert_eq!(
        parse_deadline(Some("21:00"), &[0, 1, 4]).unwrap(),
        Some((4, 21 * 60))
    );
}

#[test]
fn test_parse_deadline_none() {
    assert_eq!(parse_deadline(None, &[0]).unwrap(), None);
    assert_eq!(parse_deadline(Some(""), &[0]).unwrap(), None);
}
