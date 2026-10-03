//! Rust twin of the Qt-free tests in `desktop/tests/test_custom_look.py`.
//!
//! The other tests in that file draw a look through `look.py` (`resolved_palette`, `pack_stylesheet`,
//! `category_paint`, `block_paint`, `look_measures`) and have no twin: `readability` and `apply_fix`
//! take a palette that only `look.py` makes.

mod common;

use common::desk::{object, with};
use flexweek_engine::desk::custom_look::{
    FILE_VERSION, ImportedLook, ReadabilityPalette, delete_look, duplicate_look, export_look,
    free_name, import_look, readability, rename_look, reset_look, sanitize_saved, save_look,
    start_custom, wear,
};
use flexweek_engine::{EngineResult, ErrorKind};
use serde_json::{Map, Value, json};

fn names(saved: &[Value]) -> Vec<&str> {
    saved
        .iter()
        .map(|look| look["name"].as_str().expect("name"))
        .collect()
}

/// `pytest.raises(LookNameError, match=words)`: the call is refused as a LookNameError is (the engine's `LookName` kind), in a
/// sentence with `words` in it.
fn refused<T: std::fmt::Debug>(result: EngineResult<T>, words: &str) {
    let error = result.expect_err(&format!("expected a refusal containing {words:?}"));
    assert_eq!(error.kind, ErrorKind::LookName, "{error:?}");
    assert!(
        error.message.contains(words),
        "{words:?} not in {:?}",
        error.message
    );
}

fn saved_as(saved: &[Value], custom: Value, name: &str) -> Vec<Value> {
    save_look(&json!(saved), &custom, name).expect("saved")
}

#[test]
fn test_saved_looks_are_named_saved_renamed_duplicated_deleted_and_reset() {
    let night = json!({"base": "nocturne", "accent": "sea", "spacing": "compact"});
    let mut saved = saved_as(&[], night.clone(), "Night study");
    saved = saved_as(&saved, json!({"base": "paper"}), "  Exams ");
    assert_eq!(names(&saved), ["Night study", "Exams"]);
    // Saving under a name that exists replaces that look.
    saved = saved_as(&saved, json!({"base": "slate"}), "exams");
    assert_eq!(names(&saved), ["Night study", "exams"]);
    assert_eq!(saved[1]["base"], "slate");
    saved = rename_look(&json!(saved), "Night study", "Late night").expect("renamed");
    let copy;
    let second;
    (saved, copy) = duplicate_look(&json!(saved), "Late night").expect("duplicated");
    (saved, second) = duplicate_look(&json!(saved), "Late night").expect("duplicated");
    assert_eq!(
        (copy.as_str(), second.as_str()),
        ("Late night copy", "Late night copy 2")
    );
    assert_eq!(
        names(&saved),
        [
            "Late night",
            "Late night copy 2",
            "Late night copy",
            "exams"
        ]
    );
    assert_eq!(
        saved[1],
        with(night.clone(), json!({"name": "Late night copy 2"}))
    );
    saved = delete_look(&json!(saved), "late night copy 2").expect("deleted");
    assert_eq!(names(&saved), ["Late night", "Late night copy", "exams"]);
    assert_eq!(
        reset_look(&saved[0]).expect("reset"),
        object(json!({"name": "Late night", "base": "nocturne"}))
    );
    for (bad, words) in [
        ("", "needs a name"),
        ("Paper", "one of FlexWeek's own looks"),
        (&"x".repeat(41), "40 letters"),
    ] {
        refused(save_look(&json!(saved), &night, bad), words);
    }
    refused(
        rename_look(&json!(saved), "Late night", "Exams"),
        "already a look called Exams",
    );
    refused(delete_look(&json!(saved), "Nope"), "No saved look");
    // What the look file holds is read back whole, and a broken or doubled entry left out.
    let mut stored = saved.clone();
    stored.push(json!({"base": "neon", "name": "Bad"}));
    stored.push(saved[0].clone());
    stored.push(json!("junk"));
    let read: Vec<Value> = sanitize_saved(&Value::Array(stored))
        .expect("sanitised")
        .into_iter()
        .map(Value::Object)
        .collect();
    assert_eq!(read, saved);
    // The wrapper hands the engine [] for anything that is not a list; the engine is given the text.
    assert_eq!(
        sanitize_saved(&json!("junk")).expect("sanitised"),
        Vec::<Map<String, Value>>::new()
    );
}

#[test]
fn test_a_new_look_is_numbered_past_the_saved_looks_rather_than_replacing_one() {
    // Save as new, Done on a new look and Import keep every saved look: save_look puts a look of the
    // same name in its place, so a new one takes the next free name.
    let first = saved_as(&[], json!({"base": "light"}), "My look");
    let saved = saved_as(&first, json!({"base": "dark"}), "My look 2");
    let free = |saved: &[Value], name: &str| free_name(&json!(saved), name);
    assert_eq!(
        free(&saved, "  Exams  week ").expect("a name"),
        "Exams week"
    );
    assert_eq!(free(&saved, "my look").expect("a name"), "my look 3");
    let fresh = free(&saved, "My look").expect("a name");
    let kept = saved_as(&saved, json!({"base": "paper"}), &fresh);
    assert_eq!(names(&kept), ["My look", "My look 2", "My look 3"]);
    assert_eq!(
        kept[0]["base"], "light",
        "the look already saved under the name is untouched"
    );
    let long = "x".repeat(40);
    let one = saved_as(&[], json!({"base": "light"}), &long);
    let numbered = free(&one, &long).expect("a name");
    assert_eq!(numbered, format!("{} 2", "x".repeat(37)));
    assert!(numbered.chars().count() <= 40);
    refused(free(&saved, "Paper"), "one of FlexWeek's own looks");
}

#[test]
fn test_starting_from_the_look_on_screen_keeps_what_the_student_had_moved() {
    let custom = start_custom(
        &json!("slate"),
        &json!({"preset": "default", "knobs": {"density": "compact"}}),
        &json!("gold"),
    );
    assert_eq!(
        custom,
        object(json!({"name": "My look", "base": "slate", "accent": "gold", "spacing": "compact"}))
    );
    let poster = start_custom(
        &json!("dark-frost"),
        &json!({"preset": "poster", "knobs": {}}),
        &json!("default"),
    );
    assert_eq!(poster["base"], "poster");
    assert_eq!(
        start_custom(&json!("light-frost"), &Value::Null, &json!("default"))["base"],
        "light"
    );
    let look = wear(
        &json!({"preset": "ink", "knobs": {"text": "large"}}),
        &Value::Object(custom.clone()),
    );
    assert_eq!(look["preset"], "ink");
    assert_eq!(look["knobs"], json!({"text": "large"}));
    assert_eq!(look["custom"], Value::Object(custom.clone()));
    assert_eq!(
        start_custom(&json!("system"), &Value::Object(look), &json!("default")),
        custom
    );
}

/// JSON text as `json.loads` would give the engine. Size is counted here; NaN and Infinity are
/// `import_look`'s (`readable`).
fn look_from(text: &str) -> ImportedLook {
    let raw: Option<Value> = serde_json::from_str(text).ok();
    import_look(text.chars().count(), raw.as_ref())
}

#[test]
fn test_a_look_is_exported_as_a_small_versioned_file_and_imported_back() {
    let custom = json!({
        "name": "Night study",
        "base": "nocturne",
        "accent": "#e8590c",
        "corners": 12,
        "categories": {"class": {"hue": 200.0}},
    });
    let text = export_look(&custom);
    let file: Value = serde_json::from_str(&text).expect("a JSON file");
    assert_eq!(file["version"], FILE_VERSION);
    assert_eq!(file["kind"], "FlexWeek look");
    assert!(text.len() < 1024);
    let back = look_from(&text);
    assert_eq!(back.look, Some(object(custom)));
    assert!(back.problems.is_empty(), "{:?}", back.problems);
}

#[test]
fn test_an_import_says_plainly_what_was_wrong() {
    let huge = format!("{{{}}}", " ".repeat(70000));
    let cases = [
        ("not json at all", "could not be read"),
        ("[1, 2]", "not a FlexWeek look"),
        (r#"{"base": "paper"}"#, "not a FlexWeek look"),
        (
            r#"{"kind": "FlexWeek look", "base": "paper"}"#,
            "no version",
        ),
        (
            r#"{"kind": "FlexWeek look", "version": 99, "base": "paper"}"#,
            "newer FlexWeek",
        ),
        (
            r#"{"kind": "FlexWeek look", "version": 1, "base": "neon"}"#,
            "does not have: 'neon'",
        ),
        (huge.as_str(), "too large"),
    ];
    for (text, said) in cases {
        let got = look_from(text);
        let shown = &text[..text.len().min(60)];
        assert_eq!(got.look, None, "{shown:?}");
        assert_eq!(got.problems.len(), 1, "{shown:?}: {:?}", got.problems);
        assert!(
            got.problems[0].contains(said),
            "{shown:?}: {said:?} not in {:?}",
            got.problems[0]
        );
    }
}

#[test]
fn test_an_import_keeps_what_it_can_and_says_what_it_left_out() {
    let got = look_from(
        r#"{"kind": "FlexWeek look", "version": 1, "base": "poster", "corners": 99, "x": 1}"#,
    );
    assert_eq!(
        got.look,
        Some(object(json!({"base": "poster", "name": "My look"})))
    );
    assert_eq!(got.problems.len(), 2, "{:?}", got.problems);
}

/// A high-contrast look with a green card has a calendar (`grid`) of its own, dark green on a black
/// page and card. The accent's Fix must read on that calendar too: the palette and both Fix colours
/// are `desk_ref.custom_look.readability` (at v0.18.0, since deleted) run on `custom`, with `resolved_palette`'s palette. Blocks
/// are left out; they only move the text's Fix.
#[test]
fn test_an_accent_fix_reads_on_the_calendar_as_well_as_the_page_and_cards() {
    let custom = object(json!({
        "base": "high-contrast",
        "accent": "#ea899d",
        "colours": {"card": "#84e637"},
    }));
    let palette = ReadabilityPalette {
        window: "#000000".into(),
        panel: "#000000".into(),
        grid: "#376117".into(),
        text: "#ffffff".into(),
        muted: "#ffffff".into(),
        accent: "#ea899d".into(),
        accent_ink: "#000000".into(),
    };
    let found = readability(&custom, &palette, &[]).expect("checked");
    let fixes: Vec<(&str, &str)> = found
        .iter()
        .filter(|problem| problem.field == ["accent"])
        .map(|problem| (problem.words.as_str(), problem.fixed.as_str()))
        .collect();
    assert_eq!(
        fixes,
        [("Today's day name", "#ffb9cc"), ("Now line", "#eb8a9d")]
    );
}
