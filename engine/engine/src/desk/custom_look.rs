//! Custom look saved-name and readability helpers from `desktop/native/custom_look.py`.

use regex::Regex;
use serde_json::{Map, Value, json};
use std::sync::LazyLock;

use crate::desk::tokens::{contrast, fit_lightness, luminance, mix};
use crate::error::{EngineError, EngineResult};

pub const UNNAMED: &str = "My look";
pub const FILE_KIND: &str = "FlexWeek look";
pub const FILE_VERSION: i64 = 1;
pub const FILE_MAX_BYTES: usize = 64 * 1024;
pub const AA_TEXT: f64 = 4.5;
pub const AA_GRAPHIC: f64 = 3.0;
pub const MID_GREY: f64 = 0.18;
pub const NAME_MAX: usize = 40;

static HEX: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"((?i)^#[0-9a-f]{6}$)").expect("hex pattern"));

static LOOK_BASES: [&str; 11] = [
    "light",
    "dark",
    "system",
    "high-contrast",
    "slate",
    "nocturne",
    "paper",
    "ink",
    "terminal",
    "poster",
    "pastel",
];

static BASE_LABELS: [&str; 11] = [
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
static PACK_LABELS: [&str; 5] = ["System", "Light", "Dark", "Nocturne", "Slate"];
static PRESET_LABELS: [&str; 7] = [
    "Pack default",
    "Terminal",
    "Poster",
    "Ink",
    "High contrast",
    "Paper",
    "Pastel",
];
static ACCENTS: [&str; 5] = ["default", "sky", "gold", "sea", "sand"];

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

fn hex(value: &str) -> Option<String> {
    if HEX.is_match(value) {
        Some(value.to_lowercase())
    } else {
        None
    }
}

pub fn sanitize_custom(raw: &Value) -> (Option<Map<String, Value>>, Vec<String>) {
    let Some(raw) = raw.as_object() else {
        return (
            None,
            vec!["A look has to be a set of named settings.".to_string()],
        );
    };
    let base = raw.get("base").and_then(Value::as_str);
    if !base.is_some_and(|b| LOOK_BASES.contains(&b)) {
        return (
            None,
            vec![format!(
                "It starts from a look FlexWeek does not have: {:?}.",
                raw.get("base")
                    .map(|v| v.to_string())
                    .unwrap_or_default()
                    .chars()
                    .take(40)
                    .collect::<String>()
            )],
        );
    }
    let mut clean = Map::new();
    clean.insert("base".into(), json!(base.unwrap()));
    let mut problems = Vec::new();
    if let Some(name) = raw.get("name").and_then(Value::as_str) {
        if !name.trim().is_empty() {
            clean.insert(
                "name".into(),
                json!(
                    name.split_whitespace()
                        .collect::<Vec<_>>()
                        .join(" ")
                        .chars()
                        .take(NAME_MAX)
                        .collect::<String>()
                ),
            );
        } else {
            problems.push("The name was not text, so it was left out.".to_string());
        }
    }
    if let Some(accent) = raw.get("accent")
        && let Some(accent) = accent.as_str()
    {
        if ACCENTS.contains(&accent) || hex(accent).is_some() {
            clean.insert(
                "accent".into(),
                json!(hex(accent).unwrap_or_else(|| accent.to_string())),
            );
        } else {
            problems.push(
                "The accent was not a swatch or a colour like #3d6fc4, so it was left out."
                    .to_string(),
            );
        }
    }
    (Some(clean), problems)
}

fn name_valid(name: &str) -> EngineResult<String> {
    if name.trim().is_empty() {
        return Err(EngineError::value("A look needs a name."));
    }
    let clean = name.split_whitespace().collect::<Vec<_>>().join(" ");
    if clean.len() > NAME_MAX {
        return Err(EngineError::value(format!(
            "A look's name can be {NAME_MAX} letters at most."
        )));
    }
    let mut built_in: Vec<String> = BASE_LABELS
        .iter()
        .chain(PACK_LABELS.iter())
        .chain(PRESET_LABELS.iter())
        .map(|s| s.to_lowercase())
        .collect();
    built_in.sort();
    if built_in.binary_search(&clean.to_lowercase()).is_ok() {
        return Err(EngineError::value(format!(
            "{clean} is one of FlexWeek's own looks. Choose another name."
        )));
    }
    Ok(clean)
}

fn find_index(saved: &[Map<String, Value>], name: &str) -> Option<usize> {
    saved.iter().position(|look| {
        look.get("name")
            .and_then(Value::as_str)
            .is_some_and(|n| n.eq_ignore_ascii_case(name))
    })
}

pub fn sanitize_saved(raw: &Value) -> Vec<Map<String, Value>> {
    let mut kept = Vec::new();
    let items = raw.as_array().cloned().unwrap_or_default();
    for item in items {
        let (Some(mut custom), _) = sanitize_custom(&item) else {
            continue;
        };
        let Some(name) = custom.get("name").and_then(Value::as_str) else {
            continue;
        };
        if name_valid(name).is_err() {
            continue;
        }
        if let Ok(clean) = name_valid(name) {
            custom.insert("name".into(), json!(clean));
        }
        if find_index(
            &kept,
            custom.get("name").and_then(Value::as_str).unwrap_or(""),
        )
        .is_none()
        {
            kept.push(custom);
        }
    }
    kept
}

pub fn save_look(
    saved: &[Map<String, Value>],
    custom: &Map<String, Value>,
    name: &str,
) -> EngineResult<Vec<Map<String, Value>>> {
    let clean = name_valid(name)?;
    let mut kept: Vec<Map<String, Value>> = saved.to_vec();
    let mut look = custom.clone();
    look.insert("name".into(), json!(clean));
    if let Some(at) = find_index(&kept, &clean) {
        kept[at] = look;
    } else {
        kept.push(look);
    }
    Ok(kept)
}

pub fn reset_look(custom: &Map<String, Value>) -> Map<String, Value> {
    let mut out = Map::new();
    for key in ["name", "base"] {
        if let Some(value) = custom.get(key) {
            out.insert(key.to_string(), value.clone());
        }
    }
    out
}

pub fn free_name(saved: &[Map<String, Value>], name: &str) -> EngineResult<String> {
    let clean = name_valid(name)?;
    let stem: String = clean.chars().take(NAME_MAX.saturating_sub(3)).collect();
    let mut free = clean.clone();
    let mut count = 2i64;
    while find_index(saved, &free).is_some() {
        free = format!("{stem} {count}");
        count += 1;
    }
    Ok(free)
}

pub fn rename_look(
    saved: &[Map<String, Value>],
    old: &str,
    new_name: &str,
) -> EngineResult<Vec<Map<String, Value>>> {
    let Some(at) = find_index(saved, old) else {
        return Err(EngineError::value(format!(
            "No saved look is called {old}."
        )));
    };
    let clean = name_valid(new_name)?;
    if let Some(other) = find_index(saved, &clean)
        && other != at
    {
        return Err(EngineError::value(format!(
            "There is already a look called {clean}."
        )));
    }
    let mut kept = saved.to_vec();
    kept[at].insert("name".into(), json!(clean));
    Ok(kept)
}

pub fn duplicate_look(
    saved: &[Map<String, Value>],
    name: &str,
) -> EngineResult<(Vec<Map<String, Value>>, String)> {
    let Some(at) = find_index(saved, name) else {
        return Err(EngineError::value(format!(
            "No saved look is called {name}."
        )));
    };
    let original = saved[at]
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or(name);
    let stem: String = format!(
        "{} copy",
        original
            .chars()
            .take(NAME_MAX.saturating_sub(8))
            .collect::<String>()
    );
    let mut copy = stem.clone();
    let mut count = 2i64;
    while find_index(saved, &copy).is_some() {
        copy = format!("{stem} {count}");
        count += 1;
    }
    let mut kept = saved.to_vec();
    let mut twin = saved[at].clone();
    twin.insert("name".into(), json!(copy));
    kept.insert(at + 1, twin);
    let given = kept[at + 1]
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    Ok((kept, given))
}

pub fn delete_look(
    saved: &[Map<String, Value>],
    name: &str,
) -> EngineResult<Vec<Map<String, Value>>> {
    if find_index(saved, name).is_none() {
        return Err(EngineError::value(format!(
            "No saved look is called {name}."
        )));
    }
    Ok(saved
        .iter()
        .filter(|look| {
            look.get("name")
                .and_then(Value::as_str)
                .is_none_or(|existing| !existing.eq_ignore_ascii_case(name))
        })
        .cloned()
        .collect())
}

pub fn export_look(custom: &Value) -> String {
    let (clean, _) = sanitize_custom(custom);
    let mut body = Map::new();
    body.insert("kind".into(), json!(FILE_KIND));
    body.insert("version".into(), json!(FILE_VERSION));
    if let Some(clean) = clean {
        for (k, v) in clean {
            body.insert(k, v);
        }
    }
    format!(
        "{}\n",
        serde_json::to_string_pretty(&body).unwrap_or_default()
    )
}

pub fn import_look(text: &[u8]) -> ImportedLook {
    if text.len() > FILE_MAX_BYTES {
        return ImportedLook {
            look: None,
            problems: vec!["This file is too large to be a FlexWeek look.".to_string()],
        };
    }
    let raw: Value = match serde_json::from_slice(text) {
        Ok(v) => v,
        Err(_) => {
            return ImportedLook {
                look: None,
                problems: vec![
                    "This file is not a FlexWeek look: it could not be read as one.".to_string(),
                ],
            };
        }
    };
    let Some(obj) = raw.as_object() else {
        return ImportedLook {
            look: None,
            problems: vec!["This file is not a FlexWeek look.".to_string()],
        };
    };
    if obj.get("kind").and_then(Value::as_str) != Some(FILE_KIND) {
        return ImportedLook {
            look: None,
            problems: vec!["This file is not a FlexWeek look.".to_string()],
        };
    }
    let version = obj.get("version").and_then(Value::as_i64);
    if version.is_none() || version == Some(0) {
        return ImportedLook {
            look: None,
            problems: vec!["This look file has no version FlexWeek can read.".to_string()],
        };
    }
    if version.unwrap_or(0) > FILE_VERSION {
        return ImportedLook {
            look: None,
            problems: vec![
                "This look was made by a newer FlexWeek. Update FlexWeek to open it.".to_string(),
            ],
        };
    }
    let body: Map<String, Value> = obj
        .iter()
        .filter(|(k, _)| *k != "kind" && *k != "version")
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();
    let (mut custom, problems) = sanitize_custom(&Value::Object(body));
    if let Some(ref mut custom) = custom {
        custom.entry("name".to_string()).or_insert(json!(UNNAMED));
    }
    ImportedLook {
        look: custom,
        problems,
    }
}

pub fn readability(
    custom: &Map<String, Value>,
    palette: &ReadabilityPalette,
    filled_blocks: &[BlockInk],
) -> Vec<ReadabilityProblem> {
    let w = palette.window.as_str();
    let p = palette.panel.as_str();
    let g = palette.grid.as_str();
    let surfaces = [w, p, g];
    let own_accent = custom
        .get("accent")
        .and_then(Value::as_str)
        .is_some_and(|a| a.starts_with('#'));
    let tint = mix(&palette.accent, &palette.window, 0.10);
    let dark_page = luminance(&palette.window) < MID_GREY;
    let alike: Vec<&str> = filled_blocks
        .iter()
        .filter(|b| (luminance(&b.fill) < MID_GREY) == dark_page)
        .map(|b| b.fill.as_str())
        .collect();
    let mut under: Vec<&str> = surfaces.to_vec();
    under.extend(alike.iter().copied());
    let mut text_fixed = fit_lightness(&palette.text, &under, AA_TEXT);
    if under
        .iter()
        .any(|ground| contrast(&text_fixed, ground) < AA_TEXT)
    {
        text_fixed = fit_lightness(&palette.text, &surfaces, AA_TEXT);
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
        let ratio = contrast(ink, ground);
        if ratio < need {
            let fixed = if field == "accent" {
                fit_lightness(
                    &palette.accent,
                    &[surfaces[0], surfaces[1], tint.as_str()],
                    need,
                )
            } else if field == "text" {
                text_fixed.clone()
            } else {
                fit_lightness(ink, &surfaces, AA_TEXT)
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
        let ratio = contrast(&block.ink, &block.fill);
        if ratio < AA_TEXT {
            found.push(ReadabilityProblem {
                words: format!("Text on {} blocks", block.label),
                ink: block.ink.clone(),
                ground: block.fill.clone(),
                ratio,
                field: vec!["categories".to_string(), block.key.clone()],
                fixed: fit_lightness(&block.fill, &[block.ink.as_str()], AA_TEXT),
            });
        }
    }
    found
}

pub fn apply_fix(custom: &Map<String, Value>, problem: &ReadabilityProblem) -> Map<String, Value> {
    let mut fixed = custom.clone();
    let group = problem.field.first().map(String::as_str).unwrap_or("");
    let key = problem.field.get(1).map(String::as_str).unwrap_or("");
    if group == "accent" {
        fixed.insert("accent".into(), json!(problem.fixed));
    } else if group == "colours" {
        let mut colours = custom
            .get("colours")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        colours.insert(key.to_string(), json!(problem.fixed));
        fixed.insert("colours".into(), Value::Object(colours));
    } else if group == "categories" {
        let mut categories = custom
            .get("categories")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        categories.insert(key.to_string(), json!({"colour": problem.fixed}));
        fixed.insert("categories".into(), Value::Object(categories));
    }
    fixed
}
