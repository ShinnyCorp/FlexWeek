//! Copy and paste, collision previews and routines from `desktop/native/reuse.py`.

use std::collections::HashSet;

use serde_json::{Map, Value, json};

use crate::desk::pyval::{list_of, lookup, subscript, type_error};
use crate::desk::reuse::{
    available_homework_minutes, copied_fixed_block_of, copied_homework_block_of, intervals_overlap,
    occurrence_days,
};
use crate::desk::weekmodel::length_label;
use crate::error::EngineResult;
use crate::snapshot::dumps_sorted;
use crate::stored::{Dict, dict, py_int, py_str, truthy, type_name};
use crate::time::{SLOT_MIN, hhmm_to_minutes};

pub const ROUTINE_FIELDS: [&str; 9] = [
    "title",
    "days",
    "start",
    "duration_min",
    "category",
    "course",
    "priority",
    "energy",
    "spotify_url",
];

fn text_of<'a>(value: &'a Value, method: &str) -> EngineResult<&'a str> {
    value
        .as_str()
        .ok_or_else(|| crate::stored::attribute_error(value, method))
}

/// `block.get(key)`: a row of the wrong type has no `get`.
fn field<'a>(row: &'a Value, key: &str) -> EngineResult<Option<&'a Value>> {
    Ok(dict(row)?.get(key))
}

/// `row[key]` where the key is held as a string.
fn require<'a>(row: &'a Value, key: &str) -> EngineResult<&'a Value> {
    subscript(row, key)
}

fn whole(value: &Value) -> EngineResult<i64> {
    py_int(value)
}

fn minutes_of(start: &Value) -> EngineResult<i64> {
    hhmm_to_minutes(text_of(start, "split")?)
}

/// `if not row.get("fixed") or not row["block"].get("start"): return None`, then the first fixed
/// block it overlaps among the saved ones, then among the other checked rows. `skip` is the row's
/// own place in `rows`, which Python knew by identity.
pub fn row_conflict(
    row: &Value,
    rows: &[Value],
    existing: &[Value],
    skip: Option<usize>,
) -> EngineResult<Option<Value>> {
    if !truthy(field(row, "fixed")?) || !truthy(field(require(row, "block")?, "start")?) {
        return Ok(None);
    }
    let block = require(row, "block")?;
    let start = minutes_of(require(block, "start")?)?;
    let end = start + whole(require(block, "duration_min")?)?;
    for saved in existing {
        if !truthy(field(saved, "start")?) {
            continue;
        }
        if !days_hold(&occurrence_days(saved), require(row, "day")?) {
            continue;
        }
        let other = minutes_of(require(saved, "start")?)?;
        if intervals_overlap(
            start,
            end,
            other,
            other + whole(require(saved, "duration_min")?)?,
        ) {
            return Ok(Some(require(saved, "title")?.clone()));
        }
    }
    for (index, candidate) in rows.iter().enumerate() {
        if Some(index) == skip
            || !truthy(field(candidate, "checked")?)
            || !truthy(field(candidate, "fixed")?)
            || require(candidate, "day")? != require(row, "day")?
            || field(candidate, "week_start")? != field(row, "week_start")?
            || !truthy(field(require(candidate, "block")?, "start")?)
        {
            continue;
        }
        let other_block = require(candidate, "block")?;
        let other = minutes_of(require(other_block, "start")?)?;
        if intervals_overlap(
            start,
            end,
            other,
            other + whole(require(other_block, "duration_min")?)?,
        ) {
            return Ok(Some(require(other_block, "title")?.clone()));
        }
    }
    Ok(None)
}

fn days_hold(days: &[i64], day: &Value) -> bool {
    day.as_i64().is_some_and(|day| days.contains(&day))
}

pub fn preview_conflict_message(
    row: &Value,
    rows: &[Value],
    existing: &[Value],
    skip: Option<usize>,
) -> EngineResult<String> {
    if truthy(field(row, "invalid")?) {
        return Ok(py_str(require(row, "invalid")?));
    }
    if let Some(conflict) = row_conflict(row, rows, existing, skip)?
        && truthy(Some(&conflict))
    {
        return Ok(format!(
            "Conflicts with {}. Choose another time.",
            py_str(&conflict)
        ));
    }
    let length = length_label(whole(require(require(row, "block")?, "duration_min")?)?);
    Ok(if truthy(field(row, "fixed")?) {
        format!("{length} · Only this week")
    } else {
        format!("{length} · Time chosen when you plan")
    })
}

#[allow(clippy::too_many_arguments)]
pub fn proposals_from_clipboard(
    items: &[Value],
    kind: &str,
    week_start: &str,
    target_day: i64,
    target_start: Option<&str>,
    assignments: &Dict,
    available: &Dict,
) -> EngineResult<Vec<Value>> {
    let mut rows = Vec::new();
    let mut left = available.clone();
    for (item_index, entry) in items.iter().enumerate() {
        let source = require(entry, "block")?;
        if truthy(field(source, "assignment_id")?) {
            let id = require(source, "assignment_id")?;
            let assignment = lookup(assignments, id)?;
            let remaining = match lookup(&left, id)? {
                Some(value) => value
                    .as_i64()
                    .ok_or_else(|| type_error("unplanned minutes must be whole numbers"))?,
                None => 0,
            };
            let asked = whole(require(source, "duration_min")?)?;
            let duration = asked.min(remaining);
            let usable =
                assignment.is_some_and(|found| truthy(Some(found))) && duration >= SLOT_MIN;
            if usable && let Value::String(name) = id {
                left.insert(name.clone(), json!(remaining - duration));
            }
            let (block, invalid) = if usable {
                let assignment = assignment.unwrap_or(&Value::Null);
                (
                    copied_homework_block_of(
                        assignment,
                        target_day,
                        duration,
                        require(entry, "group_id")?,
                    )?,
                    "",
                )
            } else {
                (
                    source.clone(),
                    if assignment.is_some_and(|found| truthy(Some(found))) {
                        "No unplanned time remains for this homework."
                    } else {
                        "This homework did not load."
                    },
                )
            };
            let mut row = Map::new();
            row.insert("week_start".into(), json!(week_start));
            row.insert("day".into(), json!(target_day));
            row.insert("fixed".into(), json!(false));
            row.insert("block".into(), block);
            row.insert("group_id".into(), require(entry, "group_id")?.clone());
            row.insert("checked".into(), json!(usable));
            row.insert("invalid".into(), json!(invalid));
            row.insert(
                "original_duration".into(),
                json!(whole(require(source, "duration_min")?)?),
            );
            rows.push(Value::Object(row));
            continue;
        }
        let series = require(entry, "scope")? == &json!("series");
        let days = if series {
            list_of(require(source, "days")?)?
        } else {
            vec![json!(target_day)]
        };
        for (day_index, day) in days.into_iter().enumerate() {
            let start = match target_start {
                Some(start) if !start.is_empty() && kind == "block" && !series => json!(start),
                _ => field(source, "start")?.cloned().unwrap_or(Value::Null),
            };
            let mut block =
                copied_fixed_block_of(source, vec![day.clone()], require(entry, "group_id")?)?;
            if let Value::Object(map) = &mut block {
                map.insert("start".into(), start.clone());
            }
            let group_id = if series {
                require(entry, "group_id")?.clone()
            } else {
                json!(format!(
                    "{}-{item_index}-{day_index}",
                    py_str(require(entry, "group_id")?)
                ))
            };
            let mut row = Map::new();
            row.insert("week_start".into(), json!(week_start));
            row.insert("day".into(), day);
            row.insert("fixed".into(), json!(true));
            row.insert("block".into(), block);
            row.insert("group_id".into(), group_id);
            row.insert(
                "original_duration".into(),
                json!(whole(require(source, "duration_min")?)?),
            );
            row.insert("checked".into(), json!(true));
            row.insert(
                "invalid".into(),
                json!(if truthy(Some(&start)) {
                    ""
                } else {
                    "Choose a start time."
                }),
            );
            rows.push(Value::Object(row));
        }
    }
    Ok(rows)
}

/// The rows ticked for paste, merged where one block lands on several days.
pub fn merge_preview_rows(rows: &[Value], operation_id: &str) -> EngineResult<Vec<Value>> {
    struct Group {
        week_start: Value,
        block: Value,
        days: Vec<i64>,
    }
    let mut groups: Vec<(String, Group)> = Vec::new();
    for row in rows {
        if !truthy(field(row, "checked")?) {
            continue;
        }
        let mut block = require(row, "block")?.clone();
        if truthy(field(row, "fixed")?) {
            let Value::Object(map) = &mut block else {
                return Err(crate::stored::attribute_error(&block, "items"));
            };
            map.insert("days".into(), json!([require(row, "day")?]));
        }
        let shape: Dict = dict(&block)?
            .iter()
            .filter(|(key, _)| key.as_str() != "id" && key.as_str() != "days")
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect();
        let key = format!(
            "{}\u{0}{}\u{0}{}",
            require(row, "week_start")?,
            require(row, "group_id")?,
            dumps_sorted(&Value::Object(shape))
        );
        let day = require(row, "day")?
            .as_i64()
            .ok_or_else(|| type_error("days must be whole numbers"))?;
        match groups.iter_mut().find(|(known, _)| *known == key) {
            Some((_, group)) => group.days.push(day),
            None => groups.push((
                key,
                Group {
                    week_start: require(row, "week_start")?.clone(),
                    block,
                    days: vec![day],
                },
            )),
        }
    }
    let stem: String = operation_id.replace('-', "").chars().take(24).collect();
    let mut result = Vec::new();
    for (index, (_, group)) in groups.into_iter().enumerate() {
        let mut block = group.block;
        let mut days = group.days;
        days.sort_unstable();
        days.dedup();
        if let Value::Object(map) = &mut block {
            map.insert("id".into(), json!(format!("b-stage3-{stem}-{index:x}")));
            map.insert("days".into(), json!(days));
        }
        result.push(json!({"week_start": group.week_start, "block": block}));
    }
    Ok(result)
}

pub fn routine_source_blocks(blocks: &[Value]) -> EngineResult<Vec<Value>> {
    let mut kept = Vec::new();
    for block in blocks {
        let fields = dict(block)?;
        if fields.get("kind").and_then(Value::as_str) == Some("locked")
            && !truthy(fields.get("assignment_id"))
            && !truthy(fields.get("pomodoro_role"))
        {
            kept.push(block.clone());
        }
    }
    Ok(kept)
}

pub fn routine_template(block: &Value, template_id: &str) -> EngineResult<Value> {
    let mut body = Map::new();
    body.insert("template_id".into(), json!(template_id));
    body.insert("title".into(), require(block, "title")?.clone());
    body.insert(
        "days".into(),
        Value::Array(list_of(require(block, "days")?)?),
    );
    body.insert("start".into(), require(block, "start")?.clone());
    body.insert(
        "duration_min".into(),
        require(block, "duration_min")?.clone(),
    );
    for name in ROUTINE_FIELDS {
        if matches!(name, "title" | "days" | "start" | "duration_min") {
            continue;
        }
        if let Some(value) = field(block, name)?
            && !value.is_null()
        {
            body.insert(name.into(), value.clone());
        }
    }
    Ok(Value::Object(body))
}

pub fn routine_rows(
    routine: &Value,
    week_start: &str,
    allowed_days: &[Value],
) -> EngineResult<Vec<Value>> {
    let mut rows = Vec::new();
    let allowed: HashSet<String> = allowed_days.iter().map(Value::to_string).collect();
    let blocks = match field(routine, "blocks")? {
        Some(value) if truthy(Some(value)) => list_of(value)?,
        _ => Vec::new(),
    };
    for template in &blocks {
        let group_id = require(template, "template_id")?;
        let days = match field(template, "days")? {
            Some(value) if truthy(Some(value)) => list_of(value)?,
            _ => Vec::new(),
        };
        for day in days {
            if !allowed.contains(&day.to_string()) {
                continue;
            }
            let mut source = dict(template)?.clone();
            source.insert("kind".into(), json!("locked"));
            let mut block =
                copied_fixed_block_of(&Value::Object(source), vec![day.clone()], group_id)?;
            if let Value::Object(map) = &mut block {
                map.shift_remove("template_id");
            }
            rows.push(json!({
                "week_start": week_start,
                "day": day,
                "fixed": true,
                "block": block,
                "group_id": group_id,
                "original_duration": whole(require(template, "duration_min")?)?,
                "checked": true,
                "invalid": "",
            }));
        }
    }
    Ok(rows)
}

/// `due_sort_key(item.get("due"), item["id"])`, as the sort compares it.
fn due_key(assignment: &Value) -> EngineResult<(chrono::NaiveDate, i64, String)> {
    let due = field(assignment, "due")?;
    let due_text = match due {
        Some(Value::String(text)) if !text.is_empty() => Some(text.as_str()),
        Some(value) if truthy(Some(value)) => {
            return Err(type_error(format!(
                "expected string or bytes-like object, got '{}'",
                type_name(value)
            )));
        }
        _ => None,
    };
    let id = require(assignment, "id")?;
    crate::model::due_sort_key(due_text, &py_str(id))
}

pub fn unfinished_items(
    assignments: &Dict,
    saved_weeks: &[Value],
    week_start: &str,
    blocks: &[Value],
    committed_blocks: &[Value],
) -> EngineResult<Vec<Value>> {
    let mut earlier = false;
    for saved in saved_weeks {
        let saved = saved.as_str().ok_or_else(|| {
            type_error(format!(
                "'<' not supported between instances of '{}' and 'str'",
                type_name(saved)
            ))
        })?;
        if saved < week_start {
            earlier = true;
            break;
        }
    }
    if !earlier {
        return Ok(Vec::new());
    }
    let mut items: Vec<(Value, (chrono::NaiveDate, i64, String))> = Vec::new();
    for assignment in assignments.values() {
        let minutes = available_homework_minutes(Some(assignment), blocks, Some(committed_blocks))?;
        if truthy(field(assignment, "completed")?) || minutes < SLOT_MIN {
            continue;
        }
        let mut body = dict(assignment)?.clone();
        body.insert("remaining_min".into(), json!(minutes));
        let value = Value::Object(body);
        let key = due_key(&value)?;
        items.push((value, key));
    }
    items.sort_by(|left, right| left.1.cmp(&right.1));
    Ok(items.into_iter().map(|(value, _)| value).collect())
}
