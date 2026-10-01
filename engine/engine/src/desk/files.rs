//! Import/export payloads from `desktop/native/files.py`.

use serde_json::{json, Map, Value};

use crate::desk::calendar::{date_for_day, deep_copy, is_series};
use crate::desk::reuse::{occurrence_days, MAX_WEEK_BLOCKS};
use crate::error::{EngineError, EngineResult};
use crate::time::is_week_start;

pub const EXPORT_FORMAT: &str = "flexweek-week";
pub const DAY_FORMAT: &str = "flexweek-day";
pub const EXPORT_VERSION: i64 = 2;

pub fn export_week_payload(week_start: &str, blocks: &[Value], assignments: &Map<String, Value>) -> Value {
    let exported: Vec<Value> = blocks
        .iter()
        .map(|block| exportable_block(block, assignments))
        .collect();
    json!({
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "week_start": week_start,
        "blocks": exported,
        "assignments": referenced_assignments(&exported, assignments),
    })
}

pub fn export_day_payload(
    week_start: &str,
    day: i64,
    blocks: &[Value],
    assignments: &Map<String, Value>,
) -> Value {
    let mut day_blocks = Vec::new();
    for block in blocks {
        if !occurrence_days(block).contains(&day) {
            continue;
        }
        let mut copy = exportable_block(block, assignments);
        if let Some(obj) = copy.as_object_mut() {
            obj.insert("days".into(), json!([day]));
            if let Some(missed) = obj.get("missed_days").and_then(Value::as_array) {
                obj.insert(
                    "missed_days".into(),
                    json!(missed.iter().filter(|v| v.as_i64() == Some(day)).collect::<Vec<_>>()),
                );
            }
        }
        day_blocks.push(copy);
    }
    json!({
        "format": DAY_FORMAT,
        "version": EXPORT_VERSION,
        "week_start": week_start,
        "date": date_for_day(week_start, day),
        "day": day,
        "blocks": day_blocks,
        "assignments": referenced_assignments(&day_blocks, assignments),
    })
}

fn exportable_block(block: &Value, assignments: &Map<String, Value>) -> Value {
    let mut copy = deep_copy(block);
    if let Some(id) = copy.get("assignment_id").and_then(Value::as_str) {
        if !assignments.contains_key(id) {
            if let Some(obj) = copy.as_object_mut() {
                obj.remove("assignment_id");
            }
        }
    }
    copy
}

fn referenced_assignments(blocks: &[Value], assignments: &Map<String, Value>) -> Vec<Value> {
    let mut unique = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for block in blocks {
        let Some(id) = block.get("assignment_id").and_then(Value::as_str) else {
            continue;
        };
        if seen.contains(id) || !assignments.contains_key(id) {
            continue;
        }
        seen.insert(id.to_string());
        unique.push(assignment_body(assignments.get(id).expect("assignment")));
    }
    unique
}

fn assignment_body(item: &Value) -> Value {
    // Caller is expected to pass assignment objects already validated; keep known fields only.
    let keep = [
        "id", "title", "course", "category", "priority", "energy", "spotify_url", "due",
        "estimate_min", "focus_minutes", "focus_sessions", "completed", "completed_at", "notes",
        "links", "checklist",
    ];
    let mut out = Map::new();
    if let Some(obj) = item.as_object() {
        for key in keep {
            if let Some(value) = obj.get(key) {
                out.insert(key.to_string(), value.clone());
            }
        }
    }
    Value::Object(out)
}

pub fn parse_import_payload(raw: &str) -> Value {
    let text = raw.trim();
    if text.is_empty() {
        return json!({"error": "Empty file."});
    }
    let data: Value = match serde_json::from_str(text) {
        Ok(v) => v,
        Err(_) => return json!({"error": "Not valid JSON. Plain-text import is export-only."}),
    };
    let Some(data) = data.as_object() else {
        return json!({"error": "Invalid FlexWeek export."});
    };
    let format = data.get("format").and_then(Value::as_str);
    if format != Some(EXPORT_FORMAT) && format != Some(DAY_FORMAT) {
        return json!({"error": "Unrecognized export format."});
    }
    let version = data.get("version").and_then(Value::as_i64);
    if version.is_none() || version.unwrap_or(0) < 1 {
        return json!({"error": "Export has no version."});
    }
    if version.unwrap_or(0) > EXPORT_VERSION {
        return json!({"error": format!("Export came from a newer FlexWeek (version {}).", version.unwrap_or(0))});
    }
    if !data.get("blocks").and_then(Value::as_array).is_some() {
        return json!({"error": "Export is missing blocks."});
    }
    let homework = if version.unwrap_or(0) >= 2 {
        data.get("assignments").and_then(Value::as_array).cloned()
    } else {
        Some(Vec::new())
    };
    if homework.is_none() {
        return json!({"error": "Export is missing its homework list."});
    }
    let week_start = data.get("week_start").and_then(Value::as_str);
    if week_start.is_some_and(|ws| !is_week_start(ws)) {
        return json!({"error": "Export week_start must be a Monday."});
    }
    let blocks = data.get("blocks").and_then(Value::as_array).cloned().unwrap_or_default();
    let assignments: Vec<Value> = homework.unwrap();
    if format == Some(DAY_FORMAT) {
        let day = data.get("day").and_then(Value::as_i64);
        if day.is_none() || ! (0..=6).contains(&day.unwrap_or(-1)) {
            return json!({"error": "Day export must contain only its day in 0..6. Nothing was imported."});
        }
        let day = day.unwrap();
        if blocks.iter().any(|b| b.get("days").and_then(Value::as_array) != Some(&vec![json!(day)])) {
            return json!({"error": "Day export must contain only its day in 0..6. Nothing was imported."});
        }
    }
    let ids: Vec<String> = blocks
        .iter()
        .filter_map(|b| b.get("id").and_then(Value::as_str).map(str::to_string))
        .collect();
    if ids.len() as i64 > MAX_WEEK_BLOCKS {
        return json!({"error": format!("Export has more than {MAX_WEEK_BLOCKS} blocks. Nothing was imported.")});
    }
    let mut seen = std::collections::HashSet::new();
    for id in &ids {
        if !seen.insert(id.clone()) {
            return json!({"error": format!("Export repeats the id {id}.")});
        }
    }
    if blocks.iter().any(|b| {
        b.get("pomodoro_parent_id")
            .and_then(Value::as_str)
            .is_some_and(|pid| seen.contains(pid))
    }) {
        return json!({"error": "Export includes a task together with the focus chunks split from it. Nothing was imported."});
    }
    let homework_ids: Vec<String> = assignments
        .iter()
        .filter_map(|a| a.get("id").and_then(Value::as_str).map(str::to_string))
        .collect();
    if version.unwrap_or(0) >= 2 {
        if homework_ids.len() as i64 > MAX_WEEK_BLOCKS {
            return json!({"error": format!("Export has more than {MAX_WEEK_BLOCKS} homework items. Nothing was imported.")});
        }
        let mut hseen = std::collections::HashSet::new();
        for id in &homework_ids {
            if !hseen.insert(id.clone()) {
                return json!({"error": format!("Export repeats the homework id {id}.")});
            }
        }
        for (index, block) in blocks.iter().enumerate() {
            if let Some(aid) = block.get("assignment_id").and_then(Value::as_str) {
                if !hseen.contains(aid) {
                    return json!({"error": format!(
                        "Block {} points at homework the file does not include. Nothing was imported.",
                        index + 1
                    )});
                }
            }
        }
    }
    json!({
        "format": format,
        "week_start": week_start,
        "day": data.get("day"),
        "blocks": blocks,
        "assignments": assignments,
        "error": Value::Null,
    })
}

pub fn occurrence_import_id(day: i64, block_id: &str) -> String {
    let prefix = format!("occ-{day}-");
    let legacy = format!("{prefix}{block_id}");
    if legacy.len() <= 80 {
        return legacy;
    }
    let mut hash_val: u32 = 2166136261;
    for ch in block_id.chars() {
        hash_val ^= u32::from(ch);
        hash_val = hash_val.wrapping_mul(16777619);
    }
    let suffix = format!("-{hash_val:08x}");
    let available = 80usize.saturating_sub(prefix.len() + suffix.len());
    format!("{}{}{}", prefix, &block_id[..block_id.len().min(available)], suffix)
}

pub fn migrated_assignment_id(week_start: &str, source_id: &str) -> String {
    let digest = crate::desk::update::sha256_hex_for_migration(&format!("{week_start}:{source_id}"));
    format!("a-{}", &digest[..32])
}

pub fn plan_imported_homework(
    homework: &[Value],
    blocks: &[Value],
    week_start: &str,
    assignments: &Map<String, Value>,
) -> Value {
    let mut id_for: std::collections::BTreeMap<String, String> = std::collections::BTreeMap::new();
    let mut create = Vec::new();
    for item in homework {
        let Some(item_id) = item.get("id").and_then(Value::as_str) else {
            continue;
        };
        if let Some(own) = assignments.get(item_id) {
            if own.get("title") == item.get("title") && own.get("due") == item.get("due") {
                id_for.insert(item_id.to_string(), item_id.to_string());
                continue;
            }
        }
        let new_id = migrated_assignment_id(week_start, item_id);
        if !assignments.contains_key(&new_id) {
            let mut created = deep_copy(item);
            if let Some(obj) = created.as_object_mut() {
                obj.insert("id".into(), json!(new_id));
            }
            create.push(created);
        }
        id_for.insert(item_id.to_string(), new_id);
    }
    let mut remapped = Vec::new();
    for block in blocks {
        let mut copy = deep_copy(block);
        if let Some(source) = copy.get("assignment_id").and_then(Value::as_str) {
            if let Some(mapped) = id_for.get(source) {
                if let Some(obj) = copy.as_object_mut() {
                    obj.insert("assignment_id".into(), json!(mapped));
                }
            }
        }
        remapped.push(copy);
    }
    json!({"blocks": remapped, "create": create})
}

pub fn merge_imported_blocks(
    existing: &[Value],
    incoming: &[Value],
    mode: &str,
    day: Option<i64>,
) -> EngineResult<Vec<Value>> {
    if mode == "replace" {
        return Ok(incoming.iter().map(deep_copy).collect());
    }
    let mut by_id: std::collections::BTreeMap<String, Value> = existing
        .iter()
        .filter_map(|b| {
            Some((
                b.get("id")?.as_str()?.to_string(),
                deep_copy(b),
            ))
        })
        .collect();
    for block in incoming {
        if block.is_null() || block.get("id").is_none() {
            continue;
        }
        let block_id = block.get("id").and_then(Value::as_str).unwrap_or("");
        let current = by_id.get(block_id).cloned();
        let split_id = day.map(|d| occurrence_import_id(d, block_id)).unwrap_or_default();
        let prior_split = by_id.get(&split_id).cloned();
        let imports_one_day = day.is_some()
            && block.get("days").and_then(Value::as_array) == Some(&vec![json!(day.unwrap())]);
        if let Some(current) = current.clone() {
            if imports_one_day
                && current.get("kind").and_then(Value::as_str) == Some("flexible")
                && current.get("days").and_then(Value::as_array).map(|d| d.len()).unwrap_or(0) > 1
            {
                return Err(EngineError::value(format!(
                    "Day import cannot merge multi-day task {block_id}. Import the full week instead."
                )));
            }
            if block.get("kind").and_then(Value::as_str) == Some("locked")
                && current.get("kind").and_then(Value::as_str) == Some("locked")
                && imports_one_day
                && day.is_some_and(|d| {
                    current
                        .get("days")
                        .and_then(Value::as_array)
                        .is_some_and(|days| days.iter().any(|v| v.as_i64() == Some(d)))
                })
                && is_series(&current)
            {
                if prior_split.is_some() {
                    return Err(EngineError::value(format!(
                        "Import would overwrite existing block {split_id}."
                    )));
                }
                let day = day.unwrap();
                let kept_days: Vec<i64> = current
                    .get("days")
                    .and_then(Value::as_array)
                    .map(|d| {
                        d.iter()
                            .filter_map(Value::as_i64)
                            .filter(|dd| *dd != day)
                            .collect()
                    })
                    .unwrap_or_default();
                let missed_split: Vec<i64> = block
                    .get("missed_days")
                    .and_then(Value::as_array)
                    .map(|m| {
                        m.iter()
                            .filter_map(Value::as_i64)
                            .filter(|d| *d == day)
                            .collect()
                    })
                    .unwrap_or_default();
                let mut split = deep_copy(block);
                if let Some(obj) = split.as_object_mut() {
                    obj.insert("id".into(), json!(split_id));
                    obj.insert("days".into(), json!([day]));
                    obj.insert("missed_days".into(), json!(missed_split));
                }
                if !kept_days.is_empty() {
                    let missed_kept: Vec<i64> = current
                        .get("missed_days")
                        .and_then(Value::as_array)
                        .map(|m| {
                            m.iter()
                                .filter_map(Value::as_i64)
                                .filter(|d| kept_days.contains(d))
                                .collect()
                        })
                        .unwrap_or_default();
                    let mut kept = deep_copy(&current);
                    if let Some(obj) = kept.as_object_mut() {
                        obj.insert("days".into(), json!(kept_days.clone()));
                        obj.insert("missed_days".into(), json!(missed_kept));
                    }
                    by_id.insert(block_id.to_string(), kept);
                } else {
                    by_id.remove(block_id);
                }
                by_id.insert(split_id, split);
                continue;
            }
        }
        if let (Some(current), Some(day)) = (current, day) {
            if block.get("kind").and_then(Value::as_str) == Some("locked")
                && current.get("kind").and_then(Value::as_str) == Some("locked")
                && imports_one_day
                && !current
                    .get("days")
                    .and_then(Value::as_array)
                    .is_some_and(|days| days.iter().any(|v| v.as_i64() == Some(day)))
                && prior_split.as_ref().is_some_and(|p| {
                    p.get("days").and_then(Value::as_array) == Some(&vec![json!(day)])
                })
            {
                let mut split = deep_copy(block);
                if let Some(obj) = split.as_object_mut() {
                    obj.insert("id".into(), json!(split_id));
                }
                by_id.insert(split_id, split);
                continue;
            }
        }
        by_id.insert(block_id.to_string(), deep_copy(block));
    }
    Ok(by_id.into_values().collect())
}
