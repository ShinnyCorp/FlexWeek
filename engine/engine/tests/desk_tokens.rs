//! Rust twin of the Qt-free tests in `desktop/tests/test_tokens.py`.
//!
//! The rest of that file measures stylesheets and palettes that `look.py` and the layouts draw, or
//! scans the Python sources; none of it reaches the engine, so none of it has a twin here.

use flexweek_engine::desk::tokens::{TYPE_PT, TextScale, family_colours, type_pt};
use std::collections::BTreeMap;

type Pair = (&'static str, &'static str);

// `CATEGORIES` in desktop/native/calendar.py, which holds the light, dark and contrast colours the
// engine's table does not: key, hue, light fill, light mark, dark pair, contrast pair.
const CATEGORIES: [(&str, f64, &str, &str, Pair, Pair); 8] = [
    (
        "class",
        250.0,
        "#cfe8ff",
        "#398ad6",
        ("#59aaf8", "#59aaf8"),
        ("#5ebdff", "#5ebdff"),
    ),
    (
        "assignments",
        25.0,
        "#ffdad6",
        "#831a1d",
        ("#f07f77", "#a43b38"),
        ("#ff8a82", "#c04442"),
    ),
    (
        "study",
        320.0,
        "#f2dbf8",
        "#ab68ba",
        ("#cb86db", "#cb86db"),
        ("#e493f6", "#e493f6"),
    ),
    (
        "exercise",
        150.0,
        "#d0eed5",
        "#399d57",
        ("#5bbd74", "#5bbd74"),
        ("#5fd37f", "#5fd37f"),
    ),
    (
        "extra",
        200.0,
        "#c3eef0",
        "#009ea7",
        ("#00bec7", "#00bec7"),
        ("#00d4df", "#00d4df"),
    ),
    (
        "meals",
        70.0,
        "#f9e0c5",
        "#bb7400",
        ("#dc932e", "#dc932e"),
        ("#f7a224", "#f7a224"),
    ),
    (
        "sleep",
        280.0,
        "#c4c8e8",
        "#5656b0",
        ("#7174d1", "#7174d1"),
        ("#8184f1", "#8184f1"),
    ),
    (
        "free",
        250.0,
        "#e0e5eb",
        "#82878c",
        ("#a0a5ab", "#a0a5ab"),
        ("#b3b8be", "#b3b8be"),
    ),
];

fn owned(pair: Pair) -> (String, String) {
    (pair.0.to_string(), pair.1.to_string())
}

#[test]
fn test_the_category_colours_are_the_family_worked_out_from_their_hues() {
    // The hex values in calendar.py are what the family's OKLCH gives, so none drifts by hand.
    for (key, hue, color, mark, dark, contrast) in CATEGORIES {
        let worked: BTreeMap<String, (String, String)> =
            family_colours(hue, key == "free", key == "assignments", key == "sleep")
                .expect("colours")
                .into_iter()
                .collect();
        let held = BTreeMap::from([
            ("light".to_string(), owned((color, mark))),
            ("dark".to_string(), owned(dark)),
            ("contrast".to_string(), owned(contrast)),
        ]);
        assert_eq!(held, worked, "{key}");
    }
}

#[test]
fn test_the_text_knob_scales_all_five_sizes() {
    // Small and Large move every size together, so a heading stays a heading at any text size.
    for (role, _) in TYPE_PT {
        let size = |name: &str| type_pt(role, &TextScale::Named(name.to_string())).expect("a size");
        let (small, normal, large) = (size("small"), size("normal"), size("large"));
        assert!(
            small < normal && normal < large,
            "{role}: {small} {normal} {large}"
        );
    }
    let normal: Vec<f64> = TYPE_PT
        .iter()
        .map(|(role, _)| type_pt(role, &TextScale::Named("normal".to_string())).expect("a size"))
        .collect();
    assert_eq!(normal, [11.0, 13.0, 15.0, 20.0, 28.0]);
}
