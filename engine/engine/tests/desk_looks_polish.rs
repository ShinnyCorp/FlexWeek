//! Rust twin of the two Qt-free tests in `desktop/tests/test_looks_polish.py` that reach only the
//! engine. The rest draw looks through `look.py` or need a palette that only it makes, so they stay
//! Python; that includes `test_stock_accents_have_no_readability_warning`, whose `readability` wrapper
//! resolves the palette in Python before it calls the engine.

use flexweek_engine::desk::calendar::CATEGORIES;
use flexweek_engine::desk::tokens::oklab;

#[test]
fn test_the_categories_use_the_hues_in_the_approved_mockup() {
    for (category, hue) in [
        ("class", 250),
        ("assignments", 25),
        ("study", 320),
        ("exercise", 150),
        ("extra", 200),
        ("meals", 70),
        ("sleep", 280),
    ] {
        let info = CATEGORIES
            .iter()
            .find(|(key, _)| *key == category)
            .map(|(_, info)| info)
            .unwrap_or_else(|| panic!("no category {category}"));
        assert_eq!(info.hue, hue, "{category}");
    }
}

#[test]
fn test_sleep_is_darker_than_the_other_light_fills() {
    let sleep = oklab(
        CATEGORIES
            .iter()
            .find(|(key, _)| *key == "sleep")
            .map(|(_, info)| info.color)
            .expect("sleep"),
    )
    .expect("a colour")
    .0;
    for (key, info) in CATEGORIES.iter().filter(|(key, _)| *key != "sleep") {
        let gap = oklab(info.color).expect("a colour").0 - sleep;
        assert!(gap >= 0.05, "{key}: {gap}");
    }
}
