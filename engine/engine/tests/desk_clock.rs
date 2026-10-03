//! Rust twin of the Qt-free tests in `desktop/tests/test_clock.py`: the 12-hour clock.
//!
//! The other tests in that file write times through widgets and dialogs (`BlockDialog`, `LateDialog`,
//! `QuarterTime`, `Drawn`, `MonthChip`, the window walk) and stay Python. Every test here switches the
//! engine's one global clock, so each takes `clock_lock` first.

mod common;

use common::desk::{clock_lock, with};
use flexweek_engine::desk::focus::{now_and_next, now_next_line};
use flexweek_engine::desk::planning::late_locked_line;
use flexweek_engine::desk::remind::due_reminders;
use flexweek_engine::desk::weekmodel::{
    added_words, clock_label, clock_text, due_label, hhmm_text, moved_words, set_clock_24h,
    time_format,
};
use serde_json::{Value, json};

fn block() -> Value {
    json!({"id": "soccer", "title": "Soccer practice", "start": "16:00", "duration_min": 90, "days": [3]})
}

/// `set_clock_24h` in the wrapper: `week_set_clock` in the binding keeps what the window last passed,
/// says whether this call differs from it, and tells the engine. The "changed" answer is the
/// binding's, not the engine's: `weekmodel::set_clock_24h` returns nothing.
fn set_clock(last: &mut bool, on: bool) -> bool {
    let changed = *last != on;
    *last = on;
    set_clock_24h(on);
    changed
}

#[test]
fn test_clock_text_on_both_clocks() {
    let _clock = clock_lock();
    for (minute, on_24, on_12) in [
        (16 * 60, "16:00", "4:00 PM"),
        (5, "00:05", "12:05 AM"),
        (12 * 60, "12:00", "12:00 PM"),
        (12 * 60 + 30, "12:30", "12:30 PM"),
        (9 * 60 + 15, "09:15", "9:15 AM"),
        (23 * 60 + 45, "23:45", "11:45 PM"),
        (24 * 60, "24:00", "12:00 AM"),
    ] {
        set_clock_24h(true);
        assert_eq!(clock_text(minute), on_24, "{minute} on the 24-hour clock");
        assert_eq!(clock_label(minute), on_24, "{minute} on the 24-hour clock");
        set_clock_24h(false);
        assert_eq!(clock_text(minute), on_12, "{minute} on the 12-hour clock");
        assert_eq!(clock_label(minute), on_12, "{minute} on the 12-hour clock");
    }
}

#[test]
fn test_set_clock_says_whether_it_changed() {
    let _clock = clock_lock();
    let mut last = true;
    assert!(!set_clock(&mut last, true));
    assert!(set_clock(&mut last, false));
    assert!(!set_clock(&mut last, false));
    assert!(set_clock(&mut last, true));
}

#[test]
fn test_time_boxes_take_the_12_hour_form() {
    let _clock = clock_lock();
    assert_eq!(time_format(), "HH:mm");
    set_clock_24h(false);
    assert_eq!(time_format(), "h:mm AP");
}

#[test]
fn test_the_week_model_words() {
    let _clock = clock_lock();
    set_clock_24h(false);
    let due = |text: &str| due_label(&json!(text)).expect("words");
    assert_eq!(hhmm_text("16:00").expect("words"), "4:00 PM");
    assert_eq!(due("2026-09-24T21:00"), "Thu 24 Sep, 9:00 PM");
    assert_eq!(due("2026-09-24"), "Thu 24 Sep");
    assert_eq!(
        added_words(&block()).expect("words"),
        "Added Soccer practice on Thu 4:00 PM."
    );
    assert_eq!(
        moved_words(&block(), 3, 4, 17 * 60, 18 * 60 + 30).expect("words"),
        "Moved Soccer practice to Fri 5:00 PM."
    );
    assert_eq!(
        moved_words(&block(), 3, 3, 16 * 60, 18 * 60).expect("words"),
        "Soccer practice now ends at 6:00 PM."
    );
}

#[test]
fn test_the_next_line_a_reminder_and_running_late() {
    let _clock = clock_lock();
    set_clock_24h(false);
    let blocks = json!([with(block(), json!({"completed": false}))]);
    let result = now_and_next(&blocks, &json!(3), 15 * 60 + 40).expect("a result");
    assert_eq!(
        now_next_line(&result, 15 * 60 + 40).expect("a line"),
        "Next: Soccer practice at 4:00 PM (in 20 min)"
    );
    let due = due_reminders(
        &json!([with(block(), json!({"kind": "locked"}))]),
        &Value::Null,
        "2026-09-24",
        15 * 60 + 56,
        5,
        &json!([]),
        true,
    )
    .expect("due");
    let bodies: Vec<&Value> = due.iter().map(|item| &item["body"]).collect();
    assert_eq!(bodies, ["4:00 PM · Thu"]);
    assert_eq!(
        late_locked_line(&json!({"start": "16:00", "duration_min": 30}), &json!(0))
            .expect("a line"),
        "Running late: 4:00 PM–4:30 PM is now locked. Nothing had to move."
    );
}
