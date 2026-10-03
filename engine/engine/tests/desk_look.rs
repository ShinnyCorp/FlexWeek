//! Rust twin of the one Qt-free test in `desktop/tests/test_look.py` that reaches only the engine.
//!
//! The other tests there draw looks through `look.py` and stay Python.

use flexweek_engine::desk::calendar::CATEGORIES;
use std::collections::BTreeSet;

#[test]
fn test_every_category_has_a_mark_of_its_own() {
    // These began as the retired web client's category colours. What has to hold now that they live
    // only here is that there are eight and no two are the same, or two kinds of block look alike.
    let marks: Vec<(&str, &str)> = CATEGORIES
        .iter()
        .map(|(name, info)| (*name, info.mark))
        .collect();
    assert_eq!(marks.len(), 8);
    let distinct: BTreeSet<&str> = marks.iter().map(|(_, mark)| *mark).collect();
    assert_eq!(distinct.len(), 8, "{marks:?}");
}
