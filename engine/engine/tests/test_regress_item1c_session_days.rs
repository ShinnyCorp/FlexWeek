//! Regression for fix-specs.md item 1c, part A: Plan is offered every day up to the real due date in
//! the open week, weekend included. `desk::planning::session_days` returns Mon-Fri (`[0, 1, 2, 3, 4]`)
//! for anything due after this Sunday, so on a Friday the only day left is Friday.
//!
//! Run from `engine/`: `cargo test -p flexweek-engine --test test_regress_item1c_session_days`;
//! known failures: add `-- --include-ignored`. The solver-level guards (week 17, week 2, Timmy's
//! 18 weeks) are in `backend/tests/test_regress_item1c_spread.py`.

use flexweek_engine::desk::planning::session_days;
use serde_json::json;

const WEEK: &str = "2026-10-05"; // Monday

fn days(due: &str) -> Vec<i64> {
    session_days(WEEK, &json!(due)).expect("days")
}

#[test]
fn due_inside_the_week_offers_monday_through_the_due_day() {
    assert_eq!(days("2026-10-07T23:59"), vec![0, 1, 2]);
    assert_eq!(days("2026-10-11T21:00"), vec![0, 1, 2, 3, 4, 5, 6]);
}

#[test]
fn due_before_the_week_offers_monday_only() {
    assert_eq!(days("2026-10-01T08:00"), vec![0]);
}

#[test]
fn due_after_sunday_offers_the_whole_week_weekend_included() {
    for due in [
        "2026-10-14T08:00",
        "2026-10-15T23:59",
        "2026-10-16T08:00",
        "2026-11-02T08:00",
    ] {
        assert_eq!(days(due), vec![0, 1, 2, 3, 4, 5, 6], "due {due}");
    }
}
