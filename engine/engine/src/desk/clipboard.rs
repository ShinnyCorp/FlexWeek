//! Copy and paste, collision previews and routines from `desktop/native/reuse.py`.

use serde_json::{Map, Value, json};

use crate::desk::planning::{available_homework_minutes, occurrence_days};
use crate::desk::pyops::{
    Cmp, PyDict, compare, contains, eq, get, hashable, in_set, iterate, or_default, order, py_dict,
    sub,
};
use crate::desk::pyval::{list_of, subscript, type_error};
use crate::desk::reuse::{copied_fixed_block_of, copied_homework_block_of, intervals_overlap};
use crate::desk::weekmodel::length_label;
use crate::error::EngineResult;
use crate::snapshot::dumps_sorted;
use crate::stored::{attribute_error, py_int, py_str, text, truthy, type_name};
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

fn minutes_of(start: &Value) -> EngineResult<i64> {
    hhmm_to_minutes(text(start, "split")?)
}

fn null() -> &'static Value {
    static NULL: Value = Value::Null;
    &NULL
}

fn whole(value: &Value) -> EngineResult<i64> {
    py_int(value)
}

/// `table.get(key)` for a key of any kind.
fn table_get<'a>(table: &'a Value, key: &Value) -> EngineResult<Option<&'a Value>> {
    let Value::Object(map) = table else {
        return Err(attribute_error(table, "get"));
    };
    hashable(key, "dict key")?;
    Ok(key.as_str().and_then(|name| map.get(name)))
}

/// A tuple of values as a dict key or set element, which a list or dict inside makes unhashable.
fn tuple_hashable(value: &Value) -> EngineResult<()> {
    if matches!(value, Value::Array(_) | Value::Object(_)) {
        return Err(type_error(format!(
            "cannot use 'tuple' as a dict key (unhashable type: '{}')",
            type_name(value)
        )));
    }
    Ok(())
}

/// The first fixed block it overlaps among the saved ones, then among the other checked rows.
/// `skip` is the row's own place in `rows`, which Python knew by identity.
pub fn row_conflict(
    row: &Value,
    rows: &Value,
    existing: &Value,
    skip: Option<usize>,
) -> EngineResult<Option<Value>> {
    if !truthy(get(row, "fixed")?) || !truthy(get(subscript(row, "block")?, "start")?) {
        return Ok(None);
    }
    let block = subscript(row, "block")?;
    let start = minutes_of(subscript(block, "start")?)?;
    let end = start + whole(subscript(block, "duration_min")?)?;
    for saved in iterate(existing)? {
        if !truthy(get(&saved, "start")?) {
            continue;
        }
        if !contains(
            &Value::Array(occurrence_days(&saved)?),
            subscript(row, "day")?,
        )? {
            continue;
        }
        let other = minutes_of(subscript(&saved, "start")?)?;
        let other_end = other + whole(subscript(&saved, "duration_min")?)?;
        if intervals_overlap(start, end, other, other_end) {
            return Ok(Some(subscript(&saved, "title")?.clone()));
        }
    }
    for (index, candidate) in iterate(rows)?.iter().enumerate() {
        if Some(index) == skip
            || !truthy(get(candidate, "checked")?)
            || !truthy(get(candidate, "fixed")?)
            || !eq(subscript(candidate, "day")?, subscript(row, "day")?)
            || !eq(
                get(candidate, "week_start")?.unwrap_or(null()),
                get(row, "week_start")?.unwrap_or(null()),
            )
            || !truthy(get(subscript(candidate, "block")?, "start")?)
        {
            continue;
        }
        let other_block = subscript(candidate, "block")?;
        let other = minutes_of(subscript(other_block, "start")?)?;
        let other_end = other + whole(subscript(other_block, "duration_min")?)?;
        if intervals_overlap(start, end, other, other_end) {
            return Ok(Some(subscript(other_block, "title")?.clone()));
        }
    }
    Ok(None)
}

pub fn preview_conflict_message(
    row: &Value,
    rows: &Value,
    existing: &Value,
    skip: Option<usize>,
) -> EngineResult<Value> {
    if truthy(get(row, "invalid")?) {
        return Ok(subscript(row, "invalid")?.clone());
    }
    if let Some(conflict) = row_conflict(row, rows, existing, skip)?
        && truthy(Some(&conflict))
    {
        return Ok(json!(format!(
            "Conflicts with {}. Choose another time.",
            py_str(&conflict)
        )));
    }
    let length = length_label(whole(subscript(subscript(row, "block")?, "duration_min")?)?);
    Ok(json!(if truthy(get(row, "fixed")?) {
        format!("{length} · Only this week")
    } else {
        format!("{length} · Time chosen when you plan")
    }))
}

pub fn proposals_from_clipboard(
    items: &Value,
    kind: &str,
    week_start: &str,
    target_day: i64,
    target_start: Option<&str>,
    assignments: &Value,
    available: &Value,
) -> EngineResult<Vec<Value>> {
    let mut rows = Vec::new();
    let mut left = PyDict::new();
    for (key, value) in py_dict(available)? {
        left.set(Value::from(key), value)?;
    }
    for (item_index, entry) in iterate(items)?.iter().enumerate() {
        let source = subscript(entry, "block")?;
        if truthy(get(source, "assignment_id")?) {
            // `assignments.get(...)` finds `get` before it reads the id.
            table_get(assignments, &Value::Null)?;
            let id = subscript(source, "assignment_id")?;
            let assignment = table_get(assignments, id)?;
            let remaining = left.get(id)?.cloned().unwrap_or_else(|| json!(0));
            let asked = Value::from(whole(subscript(source, "duration_min")?)?);
            let duration = if compare(Cmp::Lt, &remaining, &asked)? {
                remaining.clone()
            } else {
                asked
            };
            let found = assignment.filter(|value| truthy(Some(value)));
            let usable = found.is_some() && compare(Cmp::Ge, &duration, &json!(SLOT_MIN))?;
            if usable {
                left.set(id.clone(), sub(&remaining, &duration)?)?;
            }
            let (block, invalid) = match (usable, assignment) {
                (true, Some(assignment)) => (
                    copied_homework_block_of(
                        assignment,
                        target_day,
                        &duration,
                        subscript(entry, "group_id")?,
                    )?,
                    "",
                ),
                _ => (
                    source.clone(),
                    if found.is_some() {
                        "No unplanned time remains for this homework."
                    } else {
                        "This homework did not load."
                    },
                ),
            };
            let mut row = Map::new();
            row.insert("week_start".into(), json!(week_start));
            row.insert("day".into(), json!(target_day));
            row.insert("fixed".into(), json!(false));
            row.insert("block".into(), block);
            row.insert("group_id".into(), subscript(entry, "group_id")?.clone());
            row.insert("checked".into(), json!(usable));
            row.insert("invalid".into(), json!(invalid));
            row.insert(
                "original_duration".into(),
                json!(whole(subscript(source, "duration_min")?)?),
            );
            rows.push(Value::Object(row));
            continue;
        }
        let series = eq(subscript(entry, "scope")?, &json!("series"));
        let days = if series {
            list_of(subscript(source, "days")?)?
        } else {
            vec![json!(target_day)]
        };
        for (day_index, day) in days.into_iter().enumerate() {
            let start = match target_start {
                Some(start) if !start.is_empty() && kind == "block" && !series => json!(start),
                _ => get(source, "start")?.cloned().unwrap_or(Value::Null),
            };
            let mut block =
                copied_fixed_block_of(source, vec![day.clone()], subscript(entry, "group_id")?)?;
            if let Value::Object(map) = &mut block {
                map.insert("start".into(), start.clone());
            }
            let group_id = if series {
                subscript(entry, "group_id")?.clone()
            } else {
                json!(format!(
                    "{}-{item_index}-{day_index}",
                    py_str(subscript(entry, "group_id")?)
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
                json!(whole(subscript(source, "duration_min")?)?),
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
pub fn merge_preview_rows(rows: &Value, operation_id: &str) -> EngineResult<Vec<Value>> {
    struct Group {
        week_start: Value,
        block: Value,
        days: Vec<Value>,
    }
    let mut groups: Vec<(String, Group)> = Vec::new();
    for row in iterate(rows)? {
        if !truthy(get(&row, "checked")?) {
            continue;
        }
        let mut block = subscript(&row, "block")?.clone();
        if truthy(get(&row, "fixed")?) {
            let day = subscript(&row, "day")?.clone();
            let Value::Object(map) = &mut block else {
                return Err(crate::desk::pyops::item_assignment(&block));
            };
            map.insert("days".into(), json!([day]));
        }
        let Value::Object(fields) = &block else {
            return Err(attribute_error(&block, "items"));
        };
        let shape: Map<String, Value> = fields
            .iter()
            .filter(|(key, _)| key.as_str() != "id" && key.as_str() != "days")
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect();
        let week = subscript(&row, "week_start")?.clone();
        let group = subscript(&row, "group_id")?.clone();
        tuple_hashable(&week)?;
        tuple_hashable(&group)?;
        let key = format!(
            "{week}\u{0}{group}\u{0}{}",
            dumps_sorted(&Value::Object(shape))
        );
        let day = subscript(&row, "day")?.clone();
        match groups.iter_mut().find(|(known, _)| *known == key) {
            Some((_, found)) => found.days.push(day),
            None => groups.push((
                key,
                Group {
                    week_start: week,
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
        for day in &days {
            hashable(day, "set element")?;
        }
        let mut unique: Vec<Value> = Vec::new();
        for day in days.drain(..) {
            if !unique.iter().any(|held| eq(held, &day)) {
                unique.push(day);
            }
        }
        let mut failure = None;
        unique.sort_by(|left, right| {
            order(left, right, Cmp::Lt).unwrap_or_else(|error| {
                failure.get_or_insert(error);
                std::cmp::Ordering::Equal
            })
        });
        if let Some(error) = failure {
            return Err(error);
        }
        if let Value::Object(map) = &mut block {
            map.insert("id".into(), json!(format!("b-stage3-{stem}-{index:x}")));
            map.insert("days".into(), Value::Array(unique));
        }
        result.push(json!({"week_start": group.week_start, "block": block}));
    }
    Ok(result)
}

pub fn routine_source_blocks(blocks: &Value) -> EngineResult<Vec<Value>> {
    let mut kept = Vec::new();
    for block in iterate(blocks)? {
        if eq(get(&block, "kind")?.unwrap_or(null()), &json!("locked"))
            && !truthy(get(&block, "assignment_id")?)
            && !truthy(get(&block, "pomodoro_role")?)
        {
            kept.push(block);
        }
    }
    Ok(kept)
}

pub fn routine_template(block: &Value, template_id: &str) -> EngineResult<Value> {
    let mut body = Map::new();
    body.insert("template_id".into(), json!(template_id));
    body.insert("title".into(), subscript(block, "title")?.clone());
    body.insert(
        "days".into(),
        Value::Array(list_of(subscript(block, "days")?)?),
    );
    body.insert("start".into(), subscript(block, "start")?.clone());
    body.insert(
        "duration_min".into(),
        subscript(block, "duration_min")?.clone(),
    );
    for name in ROUTINE_FIELDS {
        if matches!(name, "title" | "days" | "start" | "duration_min") {
            continue;
        }
        if let Some(value) = get(block, name)?
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
    allowed_days: &Value,
) -> EngineResult<Vec<Value>> {
    let mut rows = Vec::new();
    let mut allowed: Vec<Value> = Vec::new();
    for day in iterate(allowed_days)? {
        hashable(&day, "set element")?;
        allowed.push(day);
    }
    let blocks = or_default(get(routine, "blocks")?, json!([]));
    for template in iterate(&blocks)? {
        let group_id = subscript(&template, "template_id")?;
        let days = or_default(get(&template, "days")?, json!([]));
        for day in iterate(&days)? {
            if !in_set(&allowed, &day)? {
                continue;
            }
            let mut source = match &template {
                Value::Object(fields) => fields.clone(),
                other => {
                    return Err(type_error(format!(
                        "'{}' object is not a mapping",
                        type_name(other)
                    )));
                }
            };
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
                "original_duration": whole(subscript(&template, "duration_min")?)?,
                "checked": true,
                "invalid": "",
            }));
        }
    }
    Ok(rows)
}

pub fn unfinished_items(
    assignments: &Value,
    saved_weeks: &Value,
    week_start: &str,
    blocks: &Value,
    committed_blocks: &Value,
) -> EngineResult<Vec<Value>> {
    let week = json!(week_start);
    let mut earlier = false;
    for saved in iterate(saved_weeks)? {
        if compare(Cmp::Lt, &saved, &week)? {
            earlier = true;
            break;
        }
    }
    if !earlier {
        return Ok(Vec::new());
    }
    let Value::Object(table) = assignments else {
        return Err(attribute_error(assignments, "values"));
    };
    let mut items: Vec<Value> = Vec::new();
    for assignment in table.values() {
        let minutes = available_homework_minutes(assignment, blocks, committed_blocks)?;
        if truthy(get(assignment, "completed")?) || minutes < SLOT_MIN {
            continue;
        }
        let Value::Object(fields) = assignment else {
            return Err(type_error(format!(
                "'{}' object is not a mapping",
                type_name(assignment)
            )));
        };
        let mut body = fields.clone();
        body.insert("remaining_min".into(), json!(minutes));
        items.push(Value::Object(body));
    }
    let mut keyed: Vec<(((chrono::NaiveDate, i64), Value), Value)> = Vec::new();
    for item in items {
        let due = or_default(get(&item, "due")?, Value::Null);
        let due_text = match &due {
            Value::Null => None,
            Value::String(found) if !found.is_empty() => Some(found.as_str()),
            other if !truthy(Some(other)) => None,
            other => {
                return Err(type_error(format!(
                    "expected string or bytes-like object, got '{}'",
                    type_name(other)
                )));
            }
        };
        let identity = subscript(&item, "id")?.clone();
        let (day, minute, _) = crate::model::due_sort_key(due_text, "")?;
        keyed.push((((day, minute), identity), item));
    }
    let mut failure = None;
    keyed.sort_by(|left, right| match left.0.0.cmp(&right.0.0) {
        std::cmp::Ordering::Equal => {
            order(&left.0.1, &right.0.1, Cmp::Lt).unwrap_or_else(|error| {
                failure.get_or_insert(error);
                std::cmp::Ordering::Equal
            })
        }
        other => other,
    });
    if let Some(error) = failure {
        return Err(error);
    }
    Ok(keyed.into_iter().map(|(_, item)| item).collect())
}
