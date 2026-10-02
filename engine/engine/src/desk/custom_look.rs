//! What a student does with a look of their own: start one, check it reads, keep it by name, share
//! it. From `desktop/native/custom_look.py` and the look rules in `desktop/native/look.py` it
//! reads (`sanitize_custom`, `sanitize_look`, `effective_look`, `known_pack`).

use serde_json::{Map, Value, json};

use crate::casefold::casefold;
use crate::desk::calendar::CATEGORIES;
use crate::desk::pyops::{contains, eq, get, hashable, iterate, py_dict};
use crate::desk::pyval::{subscript, type_error};
use crate::desk::tokens::{contrast, fit_lightness, luminance, mix};
use crate::error::{EngineError, EngineResult};
use crate::stored::{Dict, attribute_error, nonfinite, py_str, type_name};
use crate::time::{py_repr, py_space};

pub const UNNAMED: &str = "My look";
pub const FILE_KIND: &str = "FlexWeek look";
pub const FILE_VERSION: i64 = 1;
pub const FILE_MAX_BYTES: usize = 64 * 1024;
pub const AA_TEXT: f64 = 4.5;
pub const AA_GRAPHIC: f64 = 3.0;
pub const MID_GREY: f64 = 0.18;
pub const NAME_MAX: usize = 40;

/// Each base as the (pack, preset) it stands for.
pub const LOOK_BASES: [(&str, &str, &str); 11] = [
    ("light", "light-frost", "default"),
    ("dark", "dark-frost", "default"),
    ("system", "system", "default"),
    ("high-contrast", "system", "high-contrast"),
    ("slate", "slate", "default"),
    ("nocturne", "nocturne", "default"),
    ("paper", "system", "paper"),
    ("ink", "system", "ink"),
    ("terminal", "system", "terminal"),
    ("poster", "system", "poster"),
    ("pastel", "system", "pastel"),
];

pub const BASE_LABELS: [&str; 11] = [
    "Light",
    "Dark",
    "System",
    "High contrast",
    "Slate",
    "Nocturne",
    "Paper",
    "Ink",
    "Terminal",
    "Poster",
    "Pastel",
];
pub const PACK_LABELS: [&str; 5] = ["System", "Light", "Dark", "Nocturne", "Slate"];
pub const PRESET_LABELS: [&str; 7] = [
    "Pack default",
    "Terminal",
    "Poster",
    "Ink",
    "High contrast",
    "Paper",
    "Pastel",
];
pub const PACKS: [&str; 5] = ["system", "light-frost", "dark-frost", "nocturne", "slate"];
pub const ACCENTS: [&str; 5] = ["default", "sky", "gold", "sea", "sand"];

/// The knobs, each with the values Settings offers in order.
pub const LOOK_KNOBS: [(&str, &[&str]); 7] = [
    ("surface", &["flat", "layered"]),
    ("corners", &["soft", "sharp", "rounded"]),
    ("depth", &["none", "soft", "bold"]),
    ("font", &["sans", "serif", "mono"]),
    ("blocks", &["edge", "filled", "outline"]),
    ("density", &["comfortable", "compact"]),
    ("text", &["small", "normal", "large"]),
];
/// 0.16's names for the values that were renamed.
const LEGACY_KNOBS: [(&str, &str, &str); 6] = [
    ("surface", "frost", "layered"),
    ("corners", "round", "soft"),
    ("corners", "pill", "rounded"),
    ("depth", "flat", "none"),
    ("depth", "hard", "bold"),
    ("blocks", "outlined", "outline"),
];
pub const LOOK_DEFAULTS: [(&str, &str); 7] = [
    ("surface", "layered"),
    ("corners", "soft"),
    ("depth", "soft"),
    ("font", "sans"),
    ("blocks", "edge"),
    ("density", "comfortable"),
    ("text", "normal"),
];
/// The knobs each preset sets, over the defaults.
pub const LOOK_PRESETS: [(&str, &[(&str, &str)]); 7] = [
    ("default", &[]),
    (
        "high-contrast",
        &[
            ("surface", "flat"),
            ("corners", "sharp"),
            ("depth", "bold"),
            ("font", "sans"),
            ("blocks", "outline"),
            ("density", "comfortable"),
            ("text", "large"),
        ],
    ),
    (
        "paper",
        &[
            ("surface", "layered"),
            ("corners", "soft"),
            ("depth", "none"),
            ("font", "serif"),
        ],
    ),
    (
        "ink",
        &[
            ("surface", "layered"),
            ("corners", "soft"),
            ("depth", "soft"),
            ("font", "serif"),
        ],
    ),
    (
        "terminal",
        &[
            ("surface", "layered"),
            ("corners", "sharp"),
            ("depth", "soft"),
            ("font", "mono"),
        ],
    ),
    (
        "poster",
        &[
            ("surface", "layered"),
            ("corners", "sharp"),
            ("depth", "bold"),
            ("font", "sans"),
        ],
    ),
    (
        "pastel",
        &[
            ("surface", "layered"),
            ("corners", "rounded"),
            ("depth", "soft"),
            ("font", "sans"),
        ],
    ),
];
const FONT_NAMES: &[&str] = &["sans", "serif", "mono"];
/// The settings a custom look takes from a list, each with its values.
const CUSTOM_CHOICES: [(&str, &[&str]); 8] = [
    ("spacing", &["comfortable", "compact"]),
    ("shadows", &["none", "soft", "bold"]),
    ("body_font", FONT_NAMES),
    ("heading_font", FONT_NAMES),
    ("blocks", &["edge", "filled", "outline"]),
    ("hour_lines", &["none", "faint", "clear"]),
    ("now_line", &["accent", "text"]),
    ("motion", &["normal", "extra", "reduce", "off"]),
];
const CUSTOM_SWITCHES: [&str; 3] = ["show_times", "show_lengths", "today_highlight"];
/// The least and the most of each measure, and whether it is whole pixels.
const CUSTOM_RANGES: [(&str, f64, f64, bool); 3] = [
    ("corners", 0.0, 16.0, true),
    ("text_scale", 0.9, 1.3, false),
    ("edge_width", 2.0, 6.0, true),
];
const CUSTOM_COLOURS: [&str; 5] = ["page", "card", "text", "line", "muted"];

pub struct LookNameError {
    pub message: String,
}

impl LookNameError {
    pub fn into_engine(self) -> EngineError {
        EngineError::value(self.message)
    }
}

pub struct ImportedLook {
    pub look: Option<Map<String, Value>>,
    pub problems: Vec<String>,
}

pub struct ReadabilityPalette {
    pub window: String,
    pub panel: String,
    pub grid: String,
    pub text: String,
    pub muted: String,
    pub accent: String,
    pub accent_ink: String,
}

pub struct BlockInk {
    pub key: String,
    pub label: String,
    pub fill: String,
    pub ink: String,
}

#[derive(Clone, Debug)]
pub struct ReadabilityProblem {
    pub words: String,
    pub ink: String,
    pub ground: String,
    pub ratio: f64,
    pub field: Vec<String>,
    pub fixed: String,
}

/// `look_tables()`: the constants above as Python holds them, so a test can hold the two copies
/// to each other.
pub fn tables() -> Value {
    let knob_list = |rows: &[(&str, &[&str])]| -> Value {
        Value::Object(
            rows.iter()
                .map(|(name, values)| ((*name).to_string(), json!(values)))
                .collect(),
        )
    };
    let pair_map = |rows: &[(&str, &str)]| -> Value {
        Value::Object(
            rows.iter()
                .map(|(name, value)| ((*name).to_string(), json!(value)))
                .collect(),
        )
    };
    json!({
        "LOOK_BASES": Value::Object(LOOK_BASES.iter().map(|(base, pack, preset)| ((*base).to_string(), json!([pack, preset]))).collect()),
        "BASE_LABELS": BASE_LABELS,
        "PACK_LABELS": PACK_LABELS,
        "PRESET_LABELS": PRESET_LABELS,
        "PACKS": PACKS,
        "ACCENTS": ACCENTS,
        "LOOK_KNOBS": knob_list(&LOOK_KNOBS),
        "LOOK_DEFAULTS": pair_map(&LOOK_DEFAULTS),
        "LOOK_PRESETS": Value::Object(LOOK_PRESETS.iter().map(|(name, rows)| ((*name).to_string(), pair_map(rows))).collect()),
        "CUSTOM_CHOICES": knob_list(&CUSTOM_CHOICES),
        "CUSTOM_SWITCHES": CUSTOM_SWITCHES,
        "CUSTOM_RANGES": Value::Object(CUSTOM_RANGES.iter().map(|(name, low, high, whole)| ((*name).to_string(), json!([low, high, whole]))).collect()),
        "CUSTOM_COLOURS": CUSTOM_COLOURS,
        "CATEGORIES": CATEGORIES.iter().map(|(key, info)| json!([key, info.label, info.kind])).collect::<Vec<_>>(),
    })
}

fn is_hex(value: &str) -> bool {
    let mut chars = value.chars();
    chars.next() == Some('#')
        && value.chars().count() == 7
        && chars.all(|ch| ch.is_ascii_hexdigit())
}

/// `_hex(value)`: a six-digit colour in lower case, or None.
fn hex(value: Option<&Value>) -> Option<String> {
    match value {
        Some(Value::String(text)) if is_hex(text) => Some(text.to_ascii_lowercase()),
        _ => None,
    }
}

/// `isinstance(value, int | float) and not isinstance(value, bool)`, as a float.
fn number(value: Option<&Value>) -> Option<f64> {
    match value {
        Some(Value::Number(found)) => found.as_f64(),
        _ => None,
    }
}

fn first(text: &str, count: usize) -> String {
    text.chars().take(count).collect()
}

/// `" ".join(name.split())`, with Python's idea of white space.
fn tidy(name: &str) -> String {
    name.split(py_space)
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

fn said(key: &str) -> String {
    let spaced = key.replace('_', " ");
    let mut chars = spaced.chars();
    match chars.next() {
        Some(head) => head
            .to_uppercase()
            .chain(chars.flat_map(char::to_lowercase))
            .collect(),
        None => String::new(),
    }
}

/// A category's colour as the student set it: `{"hue": degrees}` on the family, or `{"colour": hex}`.
fn category_spec(value: &Value) -> Option<(&'static str, Value)> {
    let Value::Object(spec) = value else {
        return None;
    };
    if let Some(hue) = number(spec.get("hue"))
        && hue.is_finite()
    {
        return Some(("hue", json!(hue.rem_euclid(360.0))));
    }
    hex(spec.get("colour")).map(|colour| ("colour", json!(colour)))
}

/// `round(float(value), 2)`: the nearest hundredth, by the number's exact value.
fn round_hundredths(value: f64) -> f64 {
    format!("{value:.2}").parse().unwrap_or(value)
}

pub fn sanitize_custom(raw: &Value) -> (Option<Map<String, Value>>, Vec<String>) {
    let Value::Object(raw) = raw else {
        return (
            None,
            vec!["A look has to be a set of named settings.".to_string()],
        );
    };
    let base = match raw.get("base") {
        Some(Value::String(base)) if LOOK_BASES.iter().any(|(known, _, _)| known == base) => base,
        other => {
            let shown = other.map_or_else(|| "None".to_string(), py_str);
            return (
                None,
                vec![format!(
                    "It starts from a look FlexWeek does not have: {}.",
                    py_repr(&first(&shown, 40))
                )],
            );
        }
    };
    let mut clean = Map::new();
    clean.insert("base".into(), json!(base));
    let mut problems = Vec::new();
    for key in raw.keys() {
        let known = matches!(
            key.as_str(),
            "name" | "base" | "accent" | "colours" | "categories"
        ) || CUSTOM_CHOICES.iter().any(|(name, _)| name == key)
            || CUSTOM_SWITCHES.contains(&key.as_str())
            || CUSTOM_RANGES.iter().any(|(name, ..)| name == key);
        if !known {
            problems.push(format!(
                "{} is not a look setting, so it was left out.",
                py_repr(&first(key, 40))
            ));
        }
    }
    match raw.get("name") {
        Some(Value::String(name)) if !name.trim_matches(py_space).is_empty() => {
            clean.insert("name".into(), json!(first(&tidy(name), NAME_MAX)));
        }
        Some(_) => problems.push("The name was not text, so it was left out.".to_string()),
        None => {}
    }
    if let Some(accent) = raw.get("accent") {
        let swatch = matches!(accent, Value::String(text) if ACCENTS.contains(&text.as_str()));
        match (hex(Some(accent)), swatch) {
            (Some(colour), _) => {
                clean.insert("accent".into(), json!(colour));
            }
            (None, true) => {
                clean.insert("accent".into(), accent.clone());
            }
            (None, false) => problems.push(
                "The accent was not a swatch or a colour like #3d6fc4, so it was left out."
                    .to_string(),
            ),
        }
    }
    let mut colours = Map::new();
    match raw.get("colours") {
        None => {}
        Some(Value::Object(given)) => colours = given.clone(),
        Some(_) => problems.push(
            "The colours were not a set of named colours, so they were left out.".to_string(),
        ),
    }
    let mut kept = Map::new();
    for key in CUSTOM_COLOURS {
        if let Some(colour) = hex(colours.get(key)) {
            kept.insert(key.into(), json!(colour));
        }
    }
    for key in colours.keys() {
        if !kept.contains_key(key) {
            problems.push(format!(
                "The {key} colour was not a colour like #3d6fc4, so it was left out."
            ));
        }
    }
    if !kept.is_empty() {
        clean.insert("colours".into(), Value::Object(kept));
    }
    let mut categories = Map::new();
    match raw.get("categories") {
        None => {}
        Some(Value::Object(given)) => categories = given.clone(),
        Some(_) => {
            problems.push("The category colours were not a set, so they were left out.".to_string())
        }
    }
    let mut specs = Map::new();
    for (key, value) in &categories {
        if CATEGORIES.iter().any(|(name, _)| name == key)
            && let Some((field, found)) = category_spec(value)
        {
            specs.insert(key.clone(), json!({ field: found }));
        }
    }
    for key in categories.keys() {
        if !specs.contains_key(key) {
            problems.push(format!(
                "The colour for {} was left out: no such category or no colour.",
                py_repr(&first(key, 40))
            ));
        }
    }
    if !specs.is_empty() {
        clean.insert("categories".into(), Value::Object(specs));
    }
    for (key, values) in CUSTOM_CHOICES {
        if let Some(given) = raw.get(key) {
            match given {
                Value::String(text) if values.contains(&text.as_str()) => {
                    clean.insert(key.into(), given.clone());
                }
                _ => problems.push(format!(
                    "{} was not one of {}.",
                    said(key),
                    values.join(", ")
                )),
            }
        }
    }
    for key in CUSTOM_SWITCHES {
        if let Some(given) = raw.get(key) {
            if given.is_boolean() {
                clean.insert(key.into(), given.clone());
            } else {
                problems.push(format!(
                    "{} was not on or off, so it was left out.",
                    said(key)
                ));
            }
        }
    }
    for (key, low, high, whole) in CUSTOM_RANGES {
        if let Some(given) = raw.get(key) {
            match number(Some(given)).filter(|value| low <= *value && *value <= high) {
                Some(value) if whole => {
                    clean.insert(key.into(), json!(value.round_ties_even() as i64));
                }
                Some(value) => {
                    clean.insert(key.into(), json!(round_hundredths(value)));
                }
                None => problems.push(format!(
                    "{} was not between {} and {}.",
                    said(key),
                    py_number_text(low),
                    py_number_text(high)
                )),
            }
        }
    }
    (Some(clean), problems)
}

/// A bound as Python prints it: `0`, `16`, `0.9`, `1.3`.
fn py_number_text(value: f64) -> String {
    if value.fract() == 0.0 {
        format!("{}", value as i64)
    } else {
        format!("{value}")
    }
}

/// `pack if pack in PACKS else "system"`.
pub fn known_pack(pack: &Value) -> Value {
    match pack {
        Value::String(name) if PACKS.contains(&name.as_str()) => pack.clone(),
        _ => json!("system"),
    }
}

fn preset_knobs(preset: &str) -> &'static [(&'static str, &'static str)] {
    LOOK_PRESETS
        .iter()
        .find(|(name, _)| *name == preset)
        .map_or(&[], |(_, knobs)| *knobs)
}

/// The device's look: a preset and the knobs moved on it, 0.16's knob names read as today's, and a
/// custom look when the student made one.
pub fn sanitize_look(raw: &Value) -> Dict {
    let mut clean = Map::new();
    clean.insert("preset".into(), json!("default"));
    let mut moved = Map::new();
    let Value::Object(raw) = raw else {
        clean.insert("knobs".into(), Value::Object(moved));
        return clean;
    };
    if let Some(Value::String(preset)) = raw.get("preset")
        && LOOK_PRESETS.iter().any(|(name, _)| name == preset)
    {
        clean.insert("preset".into(), json!(preset));
    }
    if let Some(Value::Object(stored)) = raw.get("knobs") {
        for (knob, values) in LOOK_KNOBS {
            let Some(Value::String(given)) = stored.get(knob) else {
                continue;
            };
            let value = LEGACY_KNOBS
                .iter()
                .find(|(name, old, _)| *name == knob && old == given)
                .map_or(given.as_str(), |(_, _, new)| new);
            if values.contains(&value) {
                moved.insert(knob.into(), json!(value));
            }
        }
    }
    clean.insert("knobs".into(), Value::Object(moved));
    if let Some(custom) = raw.get("custom")
        && let (Some(custom), _) = sanitize_custom(custom)
    {
        clean.insert("custom".into(), Value::Object(custom));
    }
    clean
}

/// Every knob as it is drawn, for a look with no custom look worn: the defaults, the preset's, then
/// the knobs the student moved. (`start_custom` only asks this of such a look.)
fn effective_knobs(selected: &Dict) -> Dict {
    let preset = selected
        .get("preset")
        .and_then(Value::as_str)
        .unwrap_or("default");
    let mut knobs = Map::new();
    for (knob, value) in LOOK_DEFAULTS {
        knobs.insert(knob.into(), json!(value));
    }
    for (knob, value) in preset_knobs(preset) {
        knobs.insert((*knob).into(), json!(value));
    }
    if let Some(Value::Object(moved)) = selected.get("knobs") {
        for (knob, value) in moved {
            knobs.insert(knob.clone(), value.clone());
        }
    }
    knobs
}

/// The id of the look on screen, as a custom look's base: its preset, or else its pack.
pub fn base_of(pack: &Value, look: &Value) -> Value {
    let selected = sanitize_look(look);
    if let Some(Value::Object(custom)) = selected.get("custom") {
        return custom.get("base").cloned().unwrap_or(Value::Null);
    }
    match selected.get("preset").and_then(Value::as_str) {
        Some(preset) if preset != "default" => json!(preset),
        _ => {
            let pack = known_pack(pack);
            match pack.as_str() {
                Some("light-frost") => json!("light"),
                Some("dark-frost") => json!("dark"),
                _ => pack,
            }
        }
    }
}

/// A custom look that draws as the look on screen does, to be changed from there.
pub fn start_custom(pack: &Value, look: &Value, accent: &Value) -> Dict {
    let selected = sanitize_look(look);
    if let Some(Value::Object(custom)) = selected.get("custom") {
        return custom.clone();
    }
    let base = base_of(pack, &Value::Object(selected.clone()));
    let mut custom = Map::new();
    custom.insert("name".into(), json!(UNNAMED));
    custom.insert("base".into(), base.clone());
    if accent != &json!("default") {
        custom.insert("accent".into(), accent.clone());
    }
    let knobs = effective_knobs(&selected);
    let base_preset = LOOK_BASES
        .iter()
        .find(|(name, _, _)| Some(*name) == base.as_str())
        .map_or("default", |(_, _, preset)| preset);
    let mut base_look = Map::new();
    base_look.insert("preset".into(), json!(base_preset));
    let base_knobs = effective_knobs(&base_look);
    for (knob, field) in [
        ("density", "spacing"),
        ("depth", "shadows"),
        ("blocks", "blocks"),
    ] {
        if knobs.get(knob) != base_knobs.get(knob) {
            custom.insert(
                field.into(),
                knobs.get(knob).cloned().unwrap_or(Value::Null),
            );
        }
    }
    sanitize_custom(&Value::Object(custom.clone()))
        .0
        .unwrap_or(custom)
}

/// The device look with `custom` worn, its preset and knobs kept for when it is taken off.
pub fn wear(look: &Value, custom: &Value) -> Dict {
    let mut selected = sanitize_look(look);
    selected.insert("custom".into(), custom.clone());
    sanitize_look(&Value::Object(selected))
}

/// `_name(name)`: the name tidied, or the sentence saying why it cannot be a saved look's.
pub fn name_valid(name: Option<&str>) -> EngineResult<String> {
    let Some(name) = name.filter(|text| !text.trim_matches(py_space).is_empty()) else {
        return Err(EngineError::look_name("A look needs a name."));
    };
    let clean = tidy(name);
    if clean.chars().count() > NAME_MAX {
        return Err(EngineError::look_name(format!(
            "A look\'s name can be {NAME_MAX} letters at most."
        )));
    }
    let folded = casefold(&clean);
    let built_in = BASE_LABELS
        .iter()
        .chain(PACK_LABELS.iter())
        .chain(PRESET_LABELS.iter())
        .any(|label| casefold(label) == folded);
    if built_in {
        return Err(EngineError::look_name(format!(
            "{clean} is one of FlexWeek's own looks. Choose another name."
        )));
    }
    Ok(clean)
}

fn same_name(shown: &Value, wanted: &str) -> EngineResult<bool> {
    let Value::String(shown) = shown else {
        return Err(attribute_error(shown, "casefold"));
    };
    Ok(casefold(shown) == wanted)
}

/// `_find(saved, name)`: where a look of that name sits, ignoring case.
pub fn find_index(saved: &[Dict], name: &str) -> EngineResult<Option<usize>> {
    let wanted = casefold(name);
    for (index, look) in saved.iter().enumerate() {
        let shown = look.get("name").ok_or_else(|| EngineError::key("name"))?;
        if same_name(shown, &wanted)? {
            return Ok(Some(index));
        }
    }
    Ok(None)
}

pub fn sanitize_saved(raw: &Value) -> EngineResult<Vec<Dict>> {
    let mut kept: Vec<Dict> = Vec::new();
    let Value::Array(items) = raw else {
        return Ok(kept);
    };
    for item in items {
        let (Some(mut custom), _) = sanitize_custom(item) else {
            continue;
        };
        let Ok(name) = name_valid(custom.get("name").and_then(Value::as_str)) else {
            continue;
        };
        custom.insert("name".into(), json!(name));
        if find_index(&kept, &name)?.is_none() {
            kept.push(custom);
        }
    }
    Ok(kept)
}

/// A small file to share a look: what kind of file it is, its version, and the look.
/// `_find` on the list as it came, so a saved look of the wrong type fails as Python's would.
pub fn find_index_of(saved: &Value, name: &str) -> EngineResult<Option<usize>> {
    let wanted = casefold(name);
    for (index, look) in iterate(saved)?.iter().enumerate() {
        if same_name(subscript(look, "name")?, &wanted)? {
            return Ok(Some(index));
        }
    }
    Ok(None)
}

/// `{**value, ...}`: only a dict can be spread.
fn spread(value: &Value) -> EngineResult<Dict> {
    match value {
        Value::Object(map) if crate::stored::nonfinite(value).is_none() => Ok(map.clone()),
        other => Err(type_error(format!(
            "'{}' object is not a mapping",
            type_name(other)
        ))),
    }
}

/// `[dict(look) for look in saved]`.
fn copies(saved: &Value) -> EngineResult<Vec<Value>> {
    let mut kept = Vec::new();
    for look in iterate(saved)? {
        kept.push(Value::Object(py_dict(&look)?));
    }
    Ok(kept)
}

pub fn save_look(saved: &Value, custom: &Value, name: &str) -> EngineResult<Vec<Value>> {
    let clean = name_valid(Some(name))?;
    let mut kept = copies(saved)?;
    let mut look = spread(custom)?;
    look.insert("name".into(), json!(clean));
    match find_index_of(&Value::Array(kept.clone()), &clean)? {
        Some(at) => kept[at] = Value::Object(look),
        None => kept.push(Value::Object(look)),
    }
    Ok(kept)
}

pub fn reset_look(custom: &Value) -> EngineResult<Dict> {
    let mut out = Map::new();
    for key in ["name", "base"] {
        if contains(custom, &json!(key))? {
            out.insert(key.to_string(), subscript(custom, key)?.clone());
        }
    }
    Ok(out)
}

pub fn free_name(saved: &Value, name: &str) -> EngineResult<String> {
    let clean = name_valid(Some(name))?;
    let stem = first(&clean, NAME_MAX - 3);
    let mut free = clean;
    let mut count = 2i64;
    while find_index_of(saved, &free)?.is_some() {
        free = format!("{stem} {count}");
        count += 1;
    }
    Ok(free)
}

pub fn rename_look(saved: &Value, old: &str, new_name: &str) -> EngineResult<Vec<Value>> {
    let Some(at) = find_index_of(saved, old)? else {
        return Err(EngineError::look_name(format!(
            "No saved look is called {old}."
        )));
    };
    let clean = name_valid(Some(new_name))?;
    if let Some(other) = find_index_of(saved, &clean)?
        && other != at
    {
        return Err(EngineError::look_name(format!(
            "There is already a look called {clean}."
        )));
    }
    let mut kept = copies(saved)?;
    let Value::Object(fields) = &mut kept[at] else {
        return Err(type_error("saved look is not a dict"));
    };
    fields.insert("name".into(), json!(clean));
    Ok(kept)
}

pub fn duplicate_look(saved: &Value, name: &str) -> EngineResult<(Vec<Value>, String)> {
    let Some(at) = find_index_of(saved, name)? else {
        return Err(EngineError::look_name(format!(
            "No saved look is called {name}."
        )));
    };
    let held = iterate(saved)?;
    let original = py_str(subscript(&held[at], "name")?);
    let stem = format!("{} copy", first(&original, NAME_MAX - 8));
    let mut copy = stem.clone();
    let mut count = 2i64;
    while find_index_of(saved, &copy)?.is_some() {
        copy = format!("{stem} {count}");
        count += 1;
    }
    let mut kept = copies(saved)?;
    let mut twin = spread(&held[at])?;
    twin.insert("name".into(), json!(copy));
    kept.insert(at + 1, Value::Object(twin));
    Ok((kept, copy))
}

pub fn delete_look(saved: &Value, name: &str) -> EngineResult<Vec<Value>> {
    if find_index_of(saved, name)?.is_none() {
        return Err(EngineError::look_name(format!(
            "No saved look is called {name}."
        )));
    }
    let wanted = casefold(name);
    let mut kept = Vec::new();
    for look in iterate(saved)? {
        if !same_name(subscript(&look, "name")?, &wanted)? {
            kept.push(Value::Object(py_dict(&look)?));
        }
    }
    Ok(kept)
}

/// `custom` with the problem's colour moved. `field` and `fixed` are read from the problem only
/// when the Python code read them, after `dict(custom)`.
pub fn apply_fix(
    custom: &Value,
    field: &mut dyn FnMut() -> EngineResult<Value>,
    fixed_colour: &mut dyn FnMut() -> EngineResult<Value>,
) -> EngineResult<Dict> {
    let mut fixed = py_dict(custom)?;
    let mut pieces = iterate(&field()?)?;
    pieces.push(json!(""));
    pieces.truncate(2);
    if pieces.len() < 2 {
        return Err(EngineError::value(
            "not enough values to unpack (expected 2, got 1)",
        ));
    }
    let group = pieces[0].clone();
    let key = pieces[1].clone();
    let colour = fixed_colour()?;
    if eq(&group, &json!("accent")) {
        fixed.insert("accent".into(), colour);
    } else if eq(&group, &json!("colours")) {
        let mut colours = spread(
            &get(custom, "colours")?
                .cloned()
                .unwrap_or_else(|| json!({})),
        )?;
        hashable(&key, "dict key")?;
        colours.insert(py_str(&key), colour);
        fixed.insert("colours".into(), Value::Object(colours));
    } else {
        let mut categories = spread(
            &get(custom, "categories")?
                .cloned()
                .unwrap_or_else(|| json!({})),
        )?;
        hashable(&key, "dict key")?;
        categories.insert(py_str(&key), json!({"colour": colour}));
        fixed.insert("categories".into(), Value::Object(categories));
    }
    Ok(fixed)
}

pub fn export_look(custom: &Value) -> String {
    let mut body = Map::new();
    body.insert("kind".into(), json!(FILE_KIND));
    body.insert("version".into(), json!(FILE_VERSION));
    if let (Some(clean), _) = sanitize_custom(custom) {
        for (key, value) in clean {
            body.insert(key, value);
        }
    }
    format!(
        "{}\n",
        crate::snapshot::dumps_indent(&Value::Object(body), 2)
    )
}

/// A look read from a file. `size` is the length of the text as Python counts it, and `raw` what
/// `json.loads` made of it, or None when it could not be read.
pub fn import_look(size: usize, raw: Option<&Value>) -> ImportedLook {
    let raw = raw.map(readable);
    let raw = raw.as_ref();
    let refused = |sentence: &str| ImportedLook {
        look: None,
        problems: vec![sentence.to_string()],
    };
    if size > FILE_MAX_BYTES {
        return refused("This file is too large to be a FlexWeek look.");
    }
    let Some(raw) = raw else {
        return refused("This file is not a FlexWeek look: it could not be read as one.");
    };
    let Value::Object(fields) = raw else {
        return refused("This file is not a FlexWeek look.");
    };
    if fields.get("kind") != Some(&json!(FILE_KIND)) {
        return refused("This file is not a FlexWeek look.");
    }
    let version = match fields.get("version") {
        Some(Value::Number(found)) if !found.to_string().contains(['.', 'e', 'E']) => {
            let digits = found.to_string();
            // Past 128 bits only the sign still matters.
            Some(
                digits
                    .parse::<i128>()
                    .unwrap_or(if digits.starts_with('-') {
                        i128::MIN
                    } else {
                        i128::MAX
                    }),
            )
        }
        _ => None,
    };
    let Some(version) = version.filter(|version| *version >= 1) else {
        return refused("This look file has no version FlexWeek can read.");
    };
    if version > i128::from(FILE_VERSION) {
        return refused("This look was made by a newer FlexWeek. Update FlexWeek to open it.");
    }
    let body: Map<String, Value> = fields
        .iter()
        .filter(|(key, _)| key.as_str() != "kind" && key.as_str() != "version")
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect();
    let (mut custom, problems) = sanitize_custom(&Value::Object(body));
    if let Some(custom) = &mut custom {
        custom
            .entry("name".to_string())
            .or_insert_with(|| json!(UNNAMED));
    }
    ImportedLook {
        look: custom,
        problems,
    }
}

/// `value` with each NaN and Infinity turned into an empty list: no look setting takes either, and
/// a list is turned away, with the same sentence, wherever a number is.
fn finite(value: &Value) -> Value {
    if nonfinite(value).is_some() {
        return json!([]);
    }
    match value {
        Value::Array(items) => Value::Array(items.iter().map(finite).collect()),
        Value::Object(fields) => Value::Object(
            fields
                .iter()
                .map(|(key, item)| (key.clone(), finite(item)))
                .collect(),
        ),
        other => other.clone(),
    }
}

/// What the rest of the import reads: `base` is the one setting whose value is printed back, so it
/// keeps its NaN and Infinity to be printed as Python prints them.
fn readable(raw: &Value) -> Value {
    match raw {
        Value::Object(fields) if fields.contains_key("base") => Value::Object(
            fields
                .iter()
                .map(|(key, item)| {
                    let kept = if key == "base" {
                        item.clone()
                    } else {
                        finite(item)
                    };
                    (key.clone(), kept)
                })
                .collect(),
        ),
        other => finite(other),
    }
}

/// A category as the look on screen paints it: the fill its colour family gives it, the fill the
/// block is drawn with, and the ink drawn on that.
pub struct PaintedCategory {
    pub key: String,
    pub fill: String,
    pub drawn_fill: String,
    pub ink: String,
}

/// The blocks whose fill is the category's own (a block drawn outlined or in another fill is the
/// text on the calendar), each named as the Customise mock-up names it.
pub fn filled_blocks(painted: &[PaintedCategory]) -> Vec<BlockInk> {
    painted
        .iter()
        .filter(|block| block.drawn_fill == block.fill)
        .filter_map(|block| {
            let (_, info) = CATEGORIES.iter().find(|(key, _)| *key == block.key)?;
            Some(BlockInk {
                key: block.key.clone(),
                label: info.label.to_string(),
                fill: block.fill.clone(),
                ink: block.ink.clone(),
            })
        })
        .collect()
}

pub fn readability(
    custom: &Map<String, Value>,
    palette: &ReadabilityPalette,
    filled_blocks: &[BlockInk],
) -> EngineResult<Vec<ReadabilityProblem>> {
    let grounds_of =
        |names: &[&str]| -> Vec<Value> { names.iter().map(|name| json!(name)).collect() };
    let w = palette.window.as_str();
    let p = palette.panel.as_str();
    let g = palette.grid.as_str();
    let surfaces = [w, p, g];
    let own_accent = custom
        .get("accent")
        .and_then(Value::as_str)
        .is_some_and(|a| a.starts_with('#'));
    let tint = mix(&palette.accent, &palette.window, 0.10)?;
    let dark_page = luminance(&palette.window)? < MID_GREY;
    let mut alike: Vec<&str> = Vec::new();
    for block in filled_blocks {
        if (luminance(&block.fill)? < MID_GREY) == dark_page {
            alike.push(block.fill.as_str());
        }
    }
    let mut under: Vec<&str> = surfaces.to_vec();
    under.extend(alike.iter().copied());
    let mut text_fixed = fit_lightness(&palette.text, &grounds_of(&under), AA_TEXT)?;
    let mut unreadable = false;
    for under_ground in &under {
        if contrast(&text_fixed, under_ground)? < AA_TEXT {
            unreadable = true;
            break;
        }
    }
    if unreadable {
        text_fixed = fit_lightness(&palette.text, &grounds_of(&surfaces), AA_TEXT)?;
    }
    let mut found = Vec::new();
    let checks = [
        (
            "Text on the page",
            palette.text.as_str(),
            palette.window.as_str(),
            "text",
        ),
        (
            "Text on cards",
            palette.text.as_str(),
            palette.panel.as_str(),
            "text",
        ),
        (
            "Text on the calendar",
            palette.text.as_str(),
            palette.grid.as_str(),
            "text",
        ),
        (
            "Muted text on the page",
            palette.muted.as_str(),
            palette.window.as_str(),
            "muted",
        ),
        (
            "Muted text on cards",
            palette.muted.as_str(),
            palette.panel.as_str(),
            "muted",
        ),
        (
            "Accent text on cards",
            palette.accent.as_str(),
            palette.panel.as_str(),
            "accent",
        ),
        (
            "Plan button words",
            palette.accent.as_str(),
            tint.as_str(),
            "accent",
        ),
        (
            "Today's day name",
            palette.accent.as_str(),
            palette.grid.as_str(),
            "accent",
        ),
        (
            "Now line",
            if custom.get("now_line").and_then(Value::as_str) == Some("text") {
                palette.text.as_str()
            } else {
                palette.accent.as_str()
            },
            palette.grid.as_str(),
            "accent",
        ),
        (
            "Text on accent buttons",
            palette.accent_ink.as_str(),
            palette.accent.as_str(),
            "accent",
        ),
    ];
    for (words, ink, ground, field) in checks {
        if field == "accent" && !own_accent {
            continue;
        }
        let need = if words == "Now line" {
            AA_GRAPHIC
        } else {
            AA_TEXT
        };
        let ratio = contrast(ink, ground)?;
        if ratio < need {
            let fixed = if field == "accent" {
                fit_lightness(
                    &palette.accent,
                    &grounds_of(&[surfaces[0], surfaces[1], tint.as_str()]),
                    need,
                )?
            } else if field == "text" {
                text_fixed.clone()
            } else {
                fit_lightness(ink, &grounds_of(&surfaces), AA_TEXT)?
            };
            let field_vec = if field == "accent" {
                vec!["accent".to_string()]
            } else {
                vec!["colours".to_string(), field.to_string()]
            };
            found.push(ReadabilityProblem {
                words: words.to_string(),
                ink: ink.to_string(),
                ground: ground.to_string(),
                ratio,
                field: field_vec,
                fixed,
            });
        }
    }
    for block in filled_blocks {
        let ratio = contrast(&block.ink, &block.fill)?;
        if ratio < AA_TEXT {
            found.push(ReadabilityProblem {
                words: format!("Text on {} blocks", block.label),
                ink: block.ink.clone(),
                ground: block.fill.clone(),
                ratio,
                field: vec!["categories".to_string(), block.key.clone()],
                fixed: fit_lightness(&block.fill, &grounds_of(&[block.ink.as_str()]), AA_TEXT)?,
            });
        }
    }
    Ok(found)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_import_reads_a_nan_set_as_the_colours_as_not_a_set() {
        let raw = json!({
            "kind": FILE_KIND,
            "version": 1,
            "base": "poster",
            "colours": {crate::stored::NONFINITE: "nan"},
        });
        let got = import_look(0, Some(&raw));
        assert_eq!(
            got.problems,
            vec!["The colours were not a set of named colours, so they were left out."]
        );
        assert_eq!(
            Value::Object(got.look.unwrap()),
            json!({"base": "poster", "name": UNNAMED})
        );
    }

    #[test]
    fn an_import_prints_a_nan_base_as_python_does() {
        let raw =
            json!({"kind": FILE_KIND, "version": 1, "base": {crate::stored::NONFINITE: "nan"}});
        let got = import_look(0, Some(&raw));
        assert!(got.look.is_none());
        assert_eq!(
            got.problems,
            vec!["It starts from a look FlexWeek does not have: 'nan'."]
        );
    }

    #[test]
    fn only_blocks_drawn_in_their_own_fill_are_checked() {
        let painted = |key: &str, drawn: &str| PaintedCategory {
            key: key.to_string(),
            fill: "#aaaaaa".to_string(),
            drawn_fill: drawn.to_string(),
            ink: "#000000".to_string(),
        };
        let kept = filled_blocks(&[
            painted("class", "#aaaaaa"),
            painted("assignments", "#bbbbbb"),
            painted("nowhere", "#aaaaaa"),
        ]);
        assert_eq!(kept.len(), 1);
        assert_eq!(
            (kept[0].key.as_str(), kept[0].label.as_str()),
            ("class", "School")
        );
    }
}
