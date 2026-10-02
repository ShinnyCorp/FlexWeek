//! Rust twin of the one Qt-free test in `desktop/tests/test_words_on_screen.py`.
//!
//! The rest of that file reads labels and buttons off a window and stays Python.

use flexweek_engine::desk::focus::{now_and_next, now_next_line};
use serde_json::json;

#[test]
fn test_the_next_line_says_min_like_every_design() {
    let blocks = [
        json!({"title": "Soccer practice", "start": "16:00", "duration_min": 90, "days": [3], "completed": false}),
    ];
    let line = |minute: i64| now_next_line(&now_and_next(&blocks, 3, minute), minute);
    assert_eq!(
        line(15 * 60 + 40),
        "Next: Soccer practice at 16:00 (in 20 min)"
    );
    assert_eq!(
        line(14 * 60 + 30),
        "Next: Soccer practice at 16:00 (in 1 h 30 min)"
    );
    assert_eq!(line(16 * 60 + 10), "Now: Soccer practice · 1 h 20 min left");
}
