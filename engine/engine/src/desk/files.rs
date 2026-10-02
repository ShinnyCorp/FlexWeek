//! Import and export of week and day files from `desktop/native/files.py`.
//!
//! The pydantic models stay in Python (`TimeBlock`, `AssignmentContent`); the Python wrappers run
//! them at the points the original did. What is here is everything around them.

use serde_json::{Value, json};

use crate::desk::calendar::is_series_checked;
use crate::desk::pyops::{
    PyDict, concat, contains, eq, get, hashable, is_int, iterate, length, slice_chars,
};
use crate::desk::pyval::subscript;
use crate::desk::reuse::MAX_WEEK_BLOCKS;
use crate::error::{EngineError, EngineResult};
use crate::stored::{attribute_error, py_str, truthy, type_name};
use crate::time::is_week_start;

pub const EXPORT_FORMAT: &str = "flexweek-week";
pub const DAY_FORMAT: &str = "flexweek-day";
pub const EXPORT_VERSION: i64 = 2;

/// The block as `exportable_block` hands it to the model: a link to homework the file does not
/// carry is dropped first.
pub fn export_input(block: &Value, assignments: &Value) -> EngineResult<Value> {
    let mut copy = block.clone();
    let linked = get(&copy, "assignment_id")?.cloned();
    if let Some(id) = linked
        && truthy(Some(&id))
        && !contains(assignments, &id)?
        && let Some(object) = copy.as_object_mut()
    {
        object.shift_remove("assignment_id");
    }
    Ok(copy)
}

/// The ids of the homework `referenced_assignments` gives a body to: each once, in the order the
/// blocks name them, and only those the account has. A later id may fail after earlier ones were
/// taken; the ids so far come back with that failure, since Python had made their bodies by then.
pub fn referenced_ids(
    blocks: &Value,
    assignments: &Value,
) -> EngineResult<(Vec<Value>, Option<EngineError>)> {
    let mut ids: Vec<Value> = Vec::new();
    for block in iterate(blocks)? {
        if let Some(id) = get(&block, "assignment_id")?
            && truthy(Some(id))
        {
            ids.push(id.clone());
        }
    }
    let mut unique: Vec<Value> = Vec::new();
    for id in ids {
        if let Err(error) = hashable(&id, "set element") {
            return Ok((unique, Some(error)));
        }
        if unique.iter().any(|seen| eq(seen, &id)) {
            continue;
        }
        match contains(assignments, &id) {
            Ok(true) => unique.push(id),
            Ok(false) => {}
            Err(error) => return Ok((unique, Some(error))),
        }
    }
    Ok((unique, None))
}

/// What `assignment_body` hands the model: only the keys the model has.
pub fn assignment_input(item: &Value, fields: &[String]) -> EngineResult<Value> {
    let Value::Object(item) = item else {
        return Err(attribute_error(item, "items"));
    };
    Ok(Value::Object(
        item.iter()
            .filter(|(key, _)| fields.contains(key))
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect(),
    ))
}

/// A block of the day export after the model: its days are the day, and only that day stays missed.
pub fn day_copy(copy: &Value, day: &Value) -> EngineResult<Value> {
    let mut copy = copy.clone();
    let Value::Object(fields) = &mut copy else {
        return Err(attribute_error(&copy, "get"));
    };
    fields.insert("days".into(), json!([day]));
    if let Some(missed) = fields.get("missed_days").cloned()
        && truthy(Some(&missed))
    {
        let mut kept = Vec::new();
        for item in iterate(&missed)? {
            if eq(&item, day) {
                kept.push(item);
            }
        }
        fields.insert("missed_days".into(), Value::Array(kept));
    }
    Ok(copy)
}

pub fn export_week(week_start: &Value, blocks: &Value, assignments: &Value) -> Value {
    json!({
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "week_start": week_start,
        "blocks": blocks,
        "assignments": assignments,
    })
}

pub fn export_day(
    week_start: &Value,
    date: &Value,
    day: &Value,
    blocks: &Value,
    assignments: &Value,
) -> Value {
    json!({
        "format": DAY_FORMAT,
        "version": EXPORT_VERSION,
        "week_start": week_start,
        "date": date,
        "day": day,
        "blocks": blocks,
        "assignments": assignments,
    })
}

fn refused(message: impl Into<String>) -> Value {
    json!({"error": message.into()})
}

/// What a file says before its blocks are checked: an error, or its format, version, week, day and
/// whether it carries a homework list. `readable` is whether the text parsed; `data` what it parsed to.
pub fn import_head(empty: bool, readable: bool, data: Option<&Value>) -> EngineResult<Value> {
    if empty {
        return Ok(refused("Empty file."));
    }
    let Some(data) = data.filter(|_| readable) else {
        return Ok(refused("Not valid JSON. Plain-text import is export-only."));
    };
    if !matches!(data, Value::Object(_)) || crate::stored::nonfinite(data).is_some() {
        return Ok(refused("Invalid FlexWeek export."));
    }
    let format = get(data, "format")?.unwrap_or(&Value::Null);
    hashable(format, "set element")?;
    let known = format
        .as_str()
        .filter(|name| *name == EXPORT_FORMAT || *name == DAY_FORMAT);
    let Some(format) = known else {
        return Ok(refused("Unrecognized export format."));
    };
    let version = get(data, "version")?.unwrap_or(&Value::Null);
    let number = match version {
        Value::Bool(flag) => Some(i128::from(*flag)),
        Value::Number(found) if is_int(version) => {
            Some(found.to_string().parse::<i128>().unwrap_or(
                if found.to_string().starts_with('-') {
                    i128::MIN
                } else {
                    i128::MAX
                },
            ))
        }
        _ => None,
    };
    let Some(number) = number.filter(|found| *found >= 1) else {
        return Ok(refused("Export has no version."));
    };
    if number > i128::from(EXPORT_VERSION) {
        return Ok(refused(format!(
            "Export came from a newer FlexWeek (version {}).",
            py_str(version)
        )));
    }
    if !matches!(get(data, "blocks")?, Some(Value::Array(_))) {
        return Ok(refused("Export is missing blocks."));
    }
    let carries = number >= 2;
    if carries && !matches!(get(data, "assignments")?, Some(Value::Array(_))) {
        return Ok(refused("Export is missing its homework list."));
    }
    let week_start = get(data, "week_start")?.cloned().unwrap_or(Value::Null);
    if truthy(Some(&week_start)) {
        match &week_start {
            Value::String(text) => {
                if !is_week_start(text) {
                    return Ok(refused("Export week_start must be a Monday."));
                }
            }
            other => {
                return Err(EngineError {
                    kind: crate::error::ErrorKind::Type,
                    message: format!(
                        "expected string or bytes-like object, got '{}'",
                        type_name(other)
                    ),
                });
            }
        }
    }
    Ok(json!({
        "format": format,
        "version": number.min(i128::from(i64::MAX)) as i64,
        "week_start": week_start,
        "day": get(data, "day")?.cloned().unwrap_or(Value::Null),
        "homework_from_file": carries,
    }))
}

/// `next(item for item in ids if ids.count(item) > 1)`.
fn first_repeated(ids: &[Value]) -> Option<&Value> {
    ids.iter()
        .find(|item| ids.iter().filter(|other| eq(other, item)).count() > 1)
}

/// The rest of the file's checks, on blocks and homework the models have accepted.
pub fn import_tail(head: &Value, blocks: &[Value], assignments: &[Value]) -> EngineResult<Value> {
    let format = subscript(head, "format")?.clone();
    let day = subscript(head, "day")?.clone();
    let version = subscript(head, "version")?.as_i64().unwrap_or(0);
    let week_start = subscript(head, "week_start")?.clone();
    let day_error =
        || refused("Day export must contain only its day in 0..6. Nothing was imported.");
    if format == json!(DAY_FORMAT) {
        let in_range = is_int(&day) && {
            let found = crate::stored::py_int(&day).unwrap_or(-1);
            (0..=6).contains(&found)
        };
        if !in_range {
            return Ok(day_error());
        }
        for block in blocks {
            if !eq(subscript(block, "days")?, &json!([day.clone()])) {
                return Ok(day_error());
            }
        }
    }
    let mut ids: Vec<Value> = Vec::new();
    for block in blocks {
        ids.push(subscript(block, "id")?.clone());
    }
    if ids.len() as i64 > MAX_WEEK_BLOCKS {
        return Ok(refused(format!(
            "Export has more than {MAX_WEEK_BLOCKS} blocks. Nothing was imported."
        )));
    }
    let seen: Vec<&Value> = ids.iter().collect();
    if let Some(repeated) = first_repeated(&ids) {
        return Ok(refused(format!(
            "Export repeats the id {}.",
            py_str(repeated)
        )));
    }
    for block in blocks {
        if let Some(parent) = get(block, "pomodoro_parent_id")? {
            hashable(parent, "set element")?;
            if seen.iter().any(|held| eq(held, parent)) {
                return Ok(refused(
                    "Export includes a task together with the focus chunks split from it. Nothing was imported.",
                ));
            }
        }
    }
    let mut homework_ids: Vec<Value> = Vec::new();
    for item in assignments {
        homework_ids.push(subscript(item, "id")?.clone());
    }
    if version >= 2 {
        if homework_ids.len() as i64 > MAX_WEEK_BLOCKS {
            return Ok(refused(format!(
                "Export has more than {MAX_WEEK_BLOCKS} homework items. Nothing was imported."
            )));
        }
        if let Some(repeated) = first_repeated(&homework_ids) {
            return Ok(refused(format!(
                "Export repeats the homework id {}. Nothing was imported.",
                py_str(repeated)
            )));
        }
        for (index, block) in blocks.iter().enumerate() {
            if let Some(linked) = get(block, "assignment_id")?
                && truthy(Some(linked))
                && !homework_ids.iter().any(|held| eq(held, linked))
            {
                return Ok(refused(format!(
                    "Block {} points at homework the file does not include. Nothing was imported.",
                    index + 1
                )));
            }
        }
    }
    let shown_day = if is_int(&day) { day } else { Value::Null };
    Ok(json!({
        "format": format,
        "week_start": if truthy(Some(&week_start)) { week_start } else { Value::Null },
        "day": shown_day,
        "blocks": blocks,
        "assignments": assignments,
        "error": Value::Null,
    }))
}

pub fn occurrence_import_id(day: &Value, block_id: &Value) -> EngineResult<String> {
    let prefix = format!("occ-{}-", py_str(day));
    let legacy = concat(&prefix, block_id)?;
    if legacy.chars().count() <= 80 {
        return Ok(legacy);
    }
    let text = block_id.as_str().unwrap_or_default();
    let mut hash_val: u32 = 2166136261;
    for ch in text.chars() {
        hash_val ^= u32::from(ch);
        hash_val = hash_val.wrapping_mul(16777619);
    }
    let suffix = format!("-{hash_val:08x}");
    let available = 80 - (prefix.chars().count() + suffix.chars().count()) as i64;
    Ok(format!(
        "{prefix}{}{suffix}",
        slice_chars(text, None, Some(available))
    ))
}

pub fn migrated_assignment_id(week_start: &Value, source_id: &Value) -> String {
    crate::plan::migrated_assignment_id(&py_str(week_start), &py_str(source_id))
}

fn dict_get<'a>(value: &'a Value, key: &Value) -> EngineResult<Option<&'a Value>> {
    hashable(key, "dict key")?;
    Ok(match (value, key) {
        (Value::Object(map), Value::String(name)) => map.get(name),
        (Value::Object(_), _) => None,
        (other, _) => return Err(attribute_error(other, "get")),
    })
}

pub fn plan_imported_homework(
    homework: &Value,
    blocks: &Value,
    week_start: &Value,
    assignments: &Value,
) -> EngineResult<Value> {
    let mut id_for = PyDict::new();
    let mut create = Vec::new();
    for item in iterate(homework)? {
        // `assignments.get(item["id"])` finds `get` before it reads the id.
        dict_get(assignments, &Value::Null)?;
        let item_id = subscript(&item, "id")?.clone();
        let own = dict_get(assignments, &item_id)?;
        if let Some(own) = own
            && truthy(Some(own))
            && eq(
                get(own, "title")?.unwrap_or(&Value::Null),
                get(&item, "title")?.unwrap_or(&Value::Null),
            )
            && eq(
                get(own, "due")?.unwrap_or(&Value::Null),
                get(&item, "due")?.unwrap_or(&Value::Null),
            )
        {
            id_for.set(item_id.clone(), item_id)?;
            continue;
        }
        let new_id = json!(migrated_assignment_id(week_start, &item_id));
        if !contains(assignments, &new_id)? {
            let mut created = item.clone();
            let Value::Object(fields) = &mut created else {
                return Err(attribute_error(&item, "get"));
            };
            fields.insert("id".into(), new_id.clone());
            create.push(created);
        }
        id_for.set(item_id, new_id)?;
    }
    let mut remapped = Vec::new();
    for block in iterate(blocks)? {
        let mut copy = block.clone();
        let source = get(&copy, "assignment_id")?.cloned().unwrap_or(Value::Null);
        if let Some(found) = id_for.get(&source)?.cloned()
            && let Value::Object(fields) = &mut copy
        {
            fields.insert("assignment_id".into(), found);
        }
        remapped.push(copy);
    }
    Ok(json!({"blocks": remapped, "create": create}))
}

fn list_or_empty(value: Option<&Value>) -> Value {
    match value {
        Some(found) if truthy(Some(found)) => found.clone(),
        _ => json!([]),
    }
}

pub fn merge_imported_blocks(
    existing: &Value,
    incoming: &Value,
    mode: &Value,
    day: &Value,
) -> EngineResult<Vec<Value>> {
    if eq(mode, &json!("replace")) {
        return iterate(incoming);
    }
    let mut by_id = PyDict::new();
    for block in iterate(existing)? {
        by_id.set(subscript(&block, "id")?.clone(), block.clone())?;
    }
    for block in iterate(incoming)? {
        if !truthy(Some(&block)) {
            continue;
        }
        let block_id = get(&block, "id")?.cloned().unwrap_or(Value::Null);
        if !truthy(Some(&block_id)) {
            continue;
        }
        let current = by_id.get(&block_id)?.cloned();
        let split_id = if day.is_null() {
            json!("")
        } else {
            json!(occurrence_import_id(day, &block_id)?)
        };
        let prior_split = by_id.get(&split_id)?.cloned();
        let imports_one_day =
            is_int(day) && eq(&list_or_empty(get(&block, "days")?), &json!([day.clone()]));
        let current_ok = current.as_ref().filter(|found| truthy(Some(found)));
        if let Some(current) = current_ok
            && imports_one_day
            && eq(
                get(current, "kind")?.unwrap_or(&Value::Null),
                &json!("flexible"),
            )
            && length(&list_or_empty(get(current, "days")?))? > 1
        {
            return Err(EngineError::value(
                concat("Day import cannot merge multi-day task ", &block_id)?
                    + ". Import the full week instead.",
            ));
        }
        let kinds_locked = |current: &Value| -> EngineResult<bool> {
            if !eq(
                get(&block, "kind")?.unwrap_or(&Value::Null),
                &json!("locked"),
            ) {
                return Ok(false);
            }
            Ok(eq(
                get(current, "kind")?.unwrap_or(&Value::Null),
                &json!("locked"),
            ))
        };
        if let Some(current) = current_ok
            && kinds_locked(current)?
            && imports_one_day
            && contains(&list_or_empty(get(current, "days")?), day)?
            && is_series_checked(current)?
        {
            if let Some(prior) = &prior_split
                && truthy(Some(prior))
            {
                return Err(EngineError::value(
                    concat("Import would overwrite existing block ", &split_id)? + ".",
                ));
            }
            let mut kept_days = Vec::new();
            for item in iterate(subscript(current, "days")?)? {
                if !eq(&item, day) {
                    kept_days.push(item);
                }
            }
            let mut split = block.clone();
            let Value::Object(fields) = &mut split else {
                return Err(attribute_error(&block, "get"));
            };
            fields.insert("id".into(), split_id.clone());
            fields.insert("days".into(), json!([day]));
            let mut missed = Vec::new();
            for item in iterate(&list_or_empty(fields.get("missed_days")))? {
                if eq(&item, day) {
                    missed.push(item);
                }
            }
            fields.insert("missed_days".into(), Value::Array(missed));
            if !kept_days.is_empty() {
                let mut kept = current.clone();
                let Value::Object(kept_fields) = &mut kept else {
                    return Err(attribute_error(current, "get"));
                };
                let mut still = Vec::new();
                for item in iterate(&list_or_empty(kept_fields.get("missed_days")))? {
                    if contains(&Value::Array(kept_days.clone()), &item)? {
                        still.push(item);
                    }
                }
                kept_fields.insert("days".into(), Value::Array(kept_days));
                kept_fields.insert("missed_days".into(), Value::Array(still));
                by_id.set(subscript(current, "id")?.clone(), kept)?;
            } else {
                by_id.pop(subscript(current, "id")?)?;
            }
            by_id.set(split_id.clone(), split)?;
            continue;
        }
        if let Some(current) = current_ok
            && kinds_locked(current)?
            && imports_one_day
            && !contains(&list_or_empty(get(current, "days")?), day)?
            && let Some(prior) = prior_split.as_ref().filter(|found| truthy(Some(found)))
            && eq(&list_or_empty(get(prior, "days")?), &json!([day.clone()]))
        {
            let mut split = block.clone();
            let Value::Object(fields) = &mut split else {
                return Err(attribute_error(&block, "get"));
            };
            fields.insert("id".into(), split_id.clone());
            by_id.set(split_id.clone(), split)?;
            continue;
        }
        by_id.set(block_id, block.clone())?;
    }
    Ok(by_id.into_values())
}
