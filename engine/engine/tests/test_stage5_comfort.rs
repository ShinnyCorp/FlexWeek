use flexweek_engine::plan::{preview_split, snap_minutes, split_plan};
use serde_json::json;

#[test]
fn test_snap_sends_25_to_30_and_5_to_15() {
    assert_eq!(snap_minutes(25, 1, 180), 30);
    assert_eq!(snap_minutes(5, 1, 60), 15);
    assert_eq!(snap_minutes(1, 1, 180), 15);
    assert_eq!(snap_minutes(30, 1, 180), 30);
}

#[test]
fn test_split_plan_matches_a_90_minute_task_after_grid_snap() {
    let plan = split_plan(90, 30, 15, 15, 4).unwrap();
    assert_eq!(
        plan,
        json!({
            "segments": [
                {"role": "work", "duration_min": 30, "index": 1},
                {"role": "break", "duration_min": 15, "index": 1},
                {"role": "work", "duration_min": 30, "index": 2},
                {"role": "break", "duration_min": 15, "index": 2},
                {"role": "work", "duration_min": 30, "index": 3},
            ],
            "total_min": 120,
        })
    );
}

#[test]
fn test_preview_reports_each_rounded_length() {
    let body = preview_split(Some(90), 25, 5, 15, 4).unwrap();
    assert_eq!(body["timer_work_min"], 30);
    assert_eq!(body["timer_break_min"], 15);
    assert_eq!(body["timer_long_break_min"], 15);
    assert_eq!(body["rounded"], true);
    assert_eq!(
        body["message"],
        "Work length 25 minutes becomes 30 on the 15-minute grid. Break length 5 minutes becomes 15 on the 15-minute grid."
    );
    assert_eq!(body["total_min"], 120);
    assert_eq!(
        body["segments"][0],
        json!({"role": "work", "duration_min": 30, "index": 1})
    );
}

#[test]
fn test_preview_without_duration_has_empty_segments() {
    let body = preview_split(None, 30, 15, 30, 4).unwrap();
    assert_eq!(
        body,
        json!({
            "timer_work_min": 30,
            "timer_break_min": 15,
            "timer_long_break_min": 30,
            "timer_long_break_every": 4,
            "rounded": false,
            "message": "",
            "segments": [],
            "total_min": 0,
        })
    );
}
