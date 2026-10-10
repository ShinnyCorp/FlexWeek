//! Import and export of week and day files from `desktop/native/files.py`.
//!
//! The pydantic models stay in Python (`TimeBlock`, `AssignmentContent`); the Python wrappers run
//! them at the points the original did. What is here is everything around them.

use serde_json::{Value, json};

use crate::desk::calendar::is_series_checked;
use crate::desk::planning::occurrence_days;
use crate::desk::pyops::{
    PyDict, concat, contains, eq, get, hashable, is_int, iso_day_of, iterate, length, slice_chars,
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
    // The same homework is the same title and due date; anything else under that id is other work.
    let same = |held: Option<&Value>, item: &Value| -> EngineResult<bool> {
        let Some(held) = held.filter(|held| truthy(Some(held))) else {
            return Ok(false);
        };
        Ok(eq(
            get(held, "title")?.unwrap_or(&Value::Null),
            get(item, "title")?.unwrap_or(&Value::Null),
        ) && eq(
            get(held, "due")?.unwrap_or(&Value::Null),
            get(item, "due")?.unwrap_or(&Value::Null),
        ))
    };
    let mut id_for = PyDict::new();
    let mut create: Vec<Value> = Vec::new();
    for item in iterate(homework)? {
        // `assignments.get(item["id"])` finds `get` before it reads the id.
        dict_get(assignments, &Value::Null)?;
        let item_id = subscript(&item, "id")?.clone();
        if same(dict_get(assignments, &item_id)?, &item)? {
            id_for.set(item_id.clone(), item_id)?;
            continue;
        }
        // The id this import derives may already hold homework an earlier import made from a
        // different version of this item: reuse it only for the same homework, otherwise try the
        // next derived id, so changed homework never takes over the old one's sessions and an
        // import of the same file again still finds the homework it made the first time.
        let mut attempt = 1;
        let new_id = loop {
            let source = if attempt == 1 {
                item_id.clone()
            } else {
                json!(format!("{}#{attempt}", py_str(&item_id)))
            };
            let candidate = json!(migrated_assignment_id(week_start, &source));
            let made_now = create.iter().any(|made| eq(&made["id"], &candidate));
            if !made_now && !contains(assignments, &candidate)? {
                let mut created = item.clone();
                let Value::Object(fields) = &mut created else {
                    return Err(attribute_error(&item, "get"));
                };
                fields.insert("id".into(), candidate.clone());
                create.push(created);
                break candidate;
            }
            if !made_now && same(dict_get(assignments, &candidate)?, &item)? {
                break candidate;
            }
            attempt += 1;
        };
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

/// What `exportable_block` hands the model for each block a week or day export takes, up to the first
/// block that fails (`day` is `None` for a week). A failure comes back with the inputs before it:
/// Python had run the model on those by then, so it raises the failure only after them.
pub fn block_inputs(
    blocks: &Value,
    assignments: &Value,
    day: Option<&Value>,
) -> (Vec<Value>, Option<EngineError>) {
    let mut inputs: Vec<Value> = Vec::new();
    let all = match iterate(blocks) {
        Ok(all) => all,
        Err(error) => return (inputs, Some(error)),
    };
    for block in all {
        if let Some(day) = day {
            match occurrence_days(&block).and_then(|days| contains(&Value::Array(days), day)) {
                Ok(true) => {}
                Ok(false) => continue,
                Err(error) => return (inputs, Some(error)),
            }
        }
        match export_input(&block, assignments) {
            Ok(input) => inputs.push(input),
            Err(error) => return (inputs, Some(error)),
        }
    }
    (inputs, None)
}

/// An export once the model has checked its blocks: the payload with an empty homework list, the ids
/// of the homework to add, and the failure that stopped them, as `referenced_ids` has it.
pub struct ExportRest {
    pub payload: Value,
    pub ids: Vec<Value>,
    pub failure: Option<EngineError>,
}

fn stopped(error: EngineError) -> ExportRest {
    ExportRest {
        payload: Value::Null,
        ids: Vec::new(),
        failure: Some(error),
    }
}

/// The week export (`day` is `None`) or the day export of `blocks`, which the model has accepted. A
/// day export shows only its day on each block and carries the date, which fails before the homework
/// ids are read, as it did when the payload was built key by key.
pub fn export_rest(
    week_start: &Value,
    day: Option<&Value>,
    blocks: &Value,
    assignments: &Value,
) -> ExportRest {
    let no_homework = json!([]);
    let (payload, shown) = match day {
        None => (
            export_week(week_start, blocks, &no_homework),
            blocks.clone(),
        ),
        Some(day) => {
            let mut day_blocks = Vec::new();
            let all = match iterate(blocks) {
                Ok(all) => all,
                Err(error) => return stopped(error),
            };
            for block in all {
                match day_copy(&block, day) {
                    Ok(copy) => day_blocks.push(copy),
                    Err(error) => return stopped(error),
                }
            }
            let date = iso_day_of(week_start)
                .and_then(|start| crate::stored::add_days_of(start, day))
                .map(crate::desk::pydate::iso_text);
            let date = match date {
                Ok(date) => date,
                Err(error) => return stopped(error),
            };
            let shown = Value::Array(day_blocks);
            (
                export_day(week_start, &json!(date), day, &shown, &no_homework),
                shown,
            )
        }
    };
    match referenced_ids(&shown, assignments) {
        Ok((ids, failure)) => ExportRest {
            payload,
            ids,
            failure,
        },
        Err(error) => stopped(error),
    }
}

/// The export with the homework bodies the model made.
pub fn export_finish(payload: &Value, bodies: &Value) -> Value {
    let mut finished = payload.clone();
    if let Some(fields) = finished.as_object_mut() {
        fields.insert("assignments".into(), bodies.clone());
    }
    finished
}

/// `import_head` and, when the file passes it, the blocks and homework the model is to check: the
/// head alone, with no blocks, when the file is refused.
pub fn import_start(
    empty: bool,
    readable: bool,
    data: Option<&Value>,
) -> EngineResult<(Value, Vec<Value>, Vec<Value>)> {
    let head = import_head(empty, readable, data)?;
    let (Some(data), false) = (data, truthy(head.get("error"))) else {
        return Ok((head, Vec::new(), Vec::new()));
    };
    let blocks = iterate(subscript(data, "blocks")?)?;
    let homework = match head.get("homework_from_file") {
        Some(Value::Bool(true)) => iterate(subscript(data, "assignments")?)?,
        _ => Vec::new(),
    };
    Ok((head, blocks, homework))
}

/// What the import comes to once the model has had the blocks and homework: the head's refusal, the
/// model's own complaint (`failure`, its text), or the rest of the file's checks.
pub fn import_finish(
    head: &Value,
    blocks: &[Value],
    assignments: &[Value],
    failure: Option<&str>,
) -> EngineResult<Value> {
    if truthy(head.get("error")) {
        return Ok(head.clone());
    }
    if let Some(message) = failure {
        return Ok(refused(format!("{message} Nothing was imported.")));
    }
    import_tail(head, blocks, assignments)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn week_block(id: &str, days: Value) -> Value {
        json!({"id": id, "kind": "locked", "days": days, "start": "16:00", "duration_min": 60})
    }

    #[test]
    fn a_day_takes_only_the_blocks_that_fall_on_it() {
        let blocks = json!([week_block("a", json!([0, 2])), week_block("b", json!([1]))]);
        let (inputs, failure) = block_inputs(&blocks, &json!({}), Some(&json!(2)));
        assert!(failure.is_none());
        assert_eq!(inputs.len(), 1);
        assert_eq!(inputs[0]["id"], "a");
    }

    #[test]
    fn a_format_that_is_not_text_is_refused_not_raised() {
        for format in [json!([]), json!({}), json!(5), Value::Null] {
            let data = json!({"format": format, "version": 2, "blocks": [], "assignments": []});
            let head = import_head(false, true, Some(&data)).expect("a refusal, not an error");
            assert_eq!(head["error"], "Unrecognized export format.");
        }
    }

    #[test]
    fn a_week_takes_every_block_and_drops_a_link_the_account_lacks() {
        let mut linked = week_block("a", json!([0]));
        linked["assignment_id"] = json!("gone");
        let blocks = json!([linked, week_block("b", json!([1]))]);
        let (inputs, failure) = block_inputs(&blocks, &json!({}), None);
        assert!(failure.is_none());
        assert_eq!(inputs.len(), 2);
        assert!(inputs[0].get("assignment_id").is_none());
    }

    #[test]
    fn a_block_that_fails_comes_back_with_the_inputs_before_it() {
        let blocks = json!([week_block("a", json!([0])), 5]);
        let (inputs, failure) = block_inputs(&blocks, &json!({}), None);
        assert_eq!(inputs.len(), 1);
        assert_eq!(
            failure.unwrap().message,
            "'int' object has no attribute 'get'"
        );
    }

    #[test]
    fn a_day_export_shows_only_its_day_with_the_date() {
        let mut block = week_block("a", json!([0, 2]));
        block["missed_days"] = json!([0, 2]);
        let rest = export_rest(
            &json!("2026-09-21"),
            Some(&json!(2)),
            &json!([block]),
            &json!({}),
        );
        assert!(rest.failure.is_none());
        assert_eq!(rest.payload["format"], "flexweek-day");
        assert_eq!(rest.payload["date"], "2026-09-23");
        assert_eq!(rest.payload["blocks"][0]["days"], json!([2]));
        assert_eq!(rest.payload["blocks"][0]["missed_days"], json!([2]));
        assert_eq!(rest.payload["assignments"], json!([]));
    }

    #[test]
    fn a_day_export_with_a_bad_week_fails_before_it_names_homework() {
        let mut block = week_block("a", json!([2]));
        block["assignment_id"] = json!("essay");
        let rest = export_rest(
            &json!("x"),
            Some(&json!(2)),
            &json!([block]),
            &json!({"essay": {}}),
        );
        assert!(rest.ids.is_empty());
        assert_eq!(
            rest.failure.unwrap().message,
            "Invalid isoformat string: 'x'"
        );
    }

    #[test]
    fn a_week_export_names_each_homework_once_and_finishes_with_the_bodies() {
        let mut first = week_block("a", json!([0]));
        first["assignment_id"] = json!("essay");
        let mut second = week_block("b", json!([1]));
        second["assignment_id"] = json!("essay");
        let rest = export_rest(
            &json!("2026-09-21"),
            None,
            &json!([first, second]),
            &json!({"essay": {}}),
        );
        assert_eq!(rest.ids, vec![json!("essay")]);
        assert_eq!(rest.payload["format"], "flexweek-week");
        let finished = export_finish(&rest.payload, &json!([{"id": "essay"}]));
        assert_eq!(finished["assignments"], json!([{"id": "essay"}]));
        let keys: Vec<&String> = finished.as_object().unwrap().keys().collect();
        assert_eq!(
            keys,
            ["format", "version", "week_start", "blocks", "assignments"]
        );
    }

    #[test]
    fn a_refused_file_has_no_blocks_to_check() {
        let (head, blocks, homework) = import_start(true, false, None).unwrap();
        assert_eq!(head["error"], "Empty file.");
        assert!(blocks.is_empty() && homework.is_empty());
        assert_eq!(
            import_finish(&head, &[], &[], None).unwrap()["error"],
            "Empty file."
        );
    }

    #[test]
    fn a_version_one_file_has_no_homework_even_if_it_lists_some() {
        let data = json!({
            "format": "flexweek-week", "version": 1, "blocks": [{"id": "a"}],
            "assignments": [{"id": "h"}],
        });
        let (head, blocks, homework) = import_start(false, true, Some(&data)).unwrap();
        assert_eq!(head["homework_from_file"], false);
        assert_eq!(blocks.len(), 1);
        assert!(homework.is_empty());
    }

    #[test]
    fn a_version_two_file_hands_over_its_homework() {
        let data = json!({
            "format": "flexweek-week", "version": 2, "blocks": [],
            "assignments": [{"id": "h"}],
        });
        let (_, blocks, homework) = import_start(false, true, Some(&data)).unwrap();
        assert!(blocks.is_empty());
        assert_eq!(homework, vec![json!({"id": "h"})]);
    }

    #[test]
    fn the_models_complaint_ends_the_import_with_nothing_imported() {
        let head = json!({
            "format": "flexweek-week", "version": 2, "week_start": null, "day": null,
            "homework_from_file": true,
        });
        let result = import_finish(&head, &[], &[], Some("bad block")).unwrap();
        assert_eq!(result, json!({"error": "bad block Nothing was imported."}));
    }

    #[test]
    fn a_file_the_model_accepts_goes_on_to_the_rest_of_the_checks() {
        let head = json!({
            "format": "flexweek-week", "version": 2, "week_start": "2026-09-21", "day": null,
            "homework_from_file": true,
        });
        let blocks = [
            json!({"id": "a", "days": [0]}),
            json!({"id": "a", "days": [1]}),
        ];
        let result = import_finish(&head, &blocks, &[], None).unwrap();
        assert_eq!(result["error"], "Export repeats the id a.");
    }
}
