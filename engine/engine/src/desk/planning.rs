//! Planning helpers from `desktop/native/reuse.py`, on the values as the Python code held them, so a
//! wrong kind of value raises what Python raised.

use chrono::Datelike;
use serde_json::{Value, json};

use crate::desk::calendar::DAY_FULL;
use crate::desk::grid::unpack_pair;
use crate::desk::pydate::from_iso;
use crate::desk::pyops::{
    Cmp, PyDict, compare, contains, eq, first_of, get, hashable, head, hhmm_of, in_set, int_of,
    is_int, iso_day_of, iterate, length, or_default, order, py_dict, tuple_index,
};
use crate::desk::pyval::{list_of, subscript, type_error};
use crate::error::{EngineError, EngineResult};
use crate::snapshot::dumps_sorted;
use crate::stored::{attribute_error, py_int, py_str, text, truthy};
use crate::time::{DAY_END_MIN, DAY_START_MIN, SLOT_MIN, hhmm_to_minutes, minutes_to_hhmm};

fn null() -> &'static Value {
    static NULL: Value = Value::Null;
    &NULL
}

fn minutes_of(start: &Value) -> EngineResult<i64> {
    hhmm_to_minutes(text(start, "split")?)
}

fn list_field(block: &Value, key: &str) -> EngineResult<Value> {
    Ok(or_default(get(block, key)?, json!([])))
}

pub fn is_homework_session(block: &Value) -> EngineResult<bool> {
    Ok(truthy(get(block, "assignment_id")?))
}

pub fn session_days(week_start: &str, due: &Value) -> EngineResult<Vec<i64>> {
    let monday = from_iso(week_start)?;
    let due_day = iso_day_of(&head(due, 10)?)?;
    let last = crate::stored::add_days(monday, 6)?;
    if due_day < monday {
        return Ok(vec![0]);
    }
    if due_day > last {
        return Ok(vec![0, 1, 2, 3, 4]);
    }
    Ok((0..=i64::from(due_day.weekday().num_days_from_monday())).collect())
}

pub fn is_planned(block: &Value) -> EngineResult<bool> {
    if !eq(get(block, "kind")?.unwrap_or(null()), &json!("flexible")) {
        return Ok(false);
    }
    if !truthy(get(block, "start")?) {
        return Ok(false);
    }
    if truthy(get(block, "completed")?) {
        return Ok(false);
    }
    Ok(length(&list_field(block, "days")?)? == 1)
}

/// `assignments.get(key)` for a key of any kind.
fn table_get<'a>(table: &'a Value, key: &Value) -> EngineResult<Option<&'a Value>> {
    let Value::Object(map) = table else {
        return Err(attribute_error(table, "get"));
    };
    hashable(key, "dict key")?;
    Ok(key.as_str().and_then(|name| map.get(name)))
}

pub fn planning_days(
    block: &Value,
    assignments: &Value,
    week_start: &str,
) -> EngineResult<Vec<Value>> {
    // `assignments.get(...)` finds `get` before it reads the block.
    table_get(assignments, &Value::Null)?;
    let link = or_default(get(block, "assignment_id")?, json!(""));
    let assignment = table_get(assignments, &link)?;
    if let Some(found) = assignment
        && truthy(Some(found))
        && truthy(get(found, "due")?)
    {
        let due = subscript(found, "due")?;
        return Ok(session_days(week_start, due)?
            .into_iter()
            .map(Value::from)
            .collect());
    }
    list_of(&or_default(get(block, "days")?, json!([0])))
}

fn place_map(trace: &Value, key: &str) -> EngineResult<Vec<Value>> {
    let source = or_default(Some(trace), json!({}));
    let listed = or_default(get(&source, key)?, json!([]));
    iterate(&listed)
}

pub fn apply_plan(
    blocks: &Value,
    trace: &Value,
    targets: Option<&Value>,
    assignments: Option<&Value>,
    week_start: Option<&str>,
) -> EngineResult<Vec<Value>> {
    let mut placed = PyDict::new();
    for item in place_map(trace, "placed")? {
        placed.set(subscript(&item, "id")?.clone(), item.clone())?;
    }
    let mut unplaced_ids: Vec<Value> = Vec::new();
    for item in place_map(trace, "unplaced")? {
        let id = subscript(&item, "id")?.clone();
        hashable(&id, "set element")?;
        unplaced_ids.push(id);
    }
    let mut out = Vec::new();
    for block in iterate(blocks)? {
        let mut copy = Value::Object(py_dict(&block)?);
        let unplanned = eq(get(&copy, "kind")?.unwrap_or(null()), &json!("flexible"))
            && !truthy(get(&copy, "completed")?);
        let skip = !unplanned
            || match targets {
                Some(set) => !in_set(&iterate(set)?, subscript(&copy, "id")?)?,
                None => false,
            };
        if skip {
            out.push(copy);
            continue;
        }
        let id = subscript(&copy, "id")?.clone();
        let winner = placed.get(&id)?.cloned();
        let fields = match &mut copy {
            Value::Object(fields) => fields,
            _ => return Err(type_error("block is not a dict")),
        };
        if let Some(winner) = winner.as_ref()
            && truthy(Some(winner))
            && truthy(get(winner, "start")?)
        {
            fields.insert("start".into(), subscript(winner, "start")?.clone());
            if truthy(get(winner, "days")?) {
                fields.insert(
                    "days".into(),
                    Value::Array(list_of(subscript(winner, "days")?)?),
                );
            }
        } else if in_set(&unplaced_ids, &id)? {
            fields.shift_remove("pinned");
            let had_start = fields.shift_remove("start");
            if had_start.as_ref().is_some_and(|value| truthy(Some(value)))
                && let (Some(assignments), Some(week_start)) = (assignments, week_start)
            {
                let days = planning_days(&copy, assignments, week_start)?;
                if let Value::Object(fields) = &mut copy {
                    fields.insert("days".into(), Value::Array(days));
                }
            }
        }
        out.push(copy);
    }
    Ok(out)
}

pub fn clear_stale_pins(blocks: &Value) -> EngineResult<Vec<Value>> {
    let mut out = Vec::new();
    for block in iterate(blocks)? {
        let stale = truthy(get(&block, "pinned")?)
            && !(truthy(get(&block, "start")?) && length(&list_field(&block, "days")?)? == 1);
        if stale {
            let Value::Object(fields) = &block else {
                return Err(attribute_error(&block, "items"));
            };
            out.push(Value::Object(
                fields
                    .iter()
                    .filter(|(key, _)| key.as_str() != "pinned")
                    .map(|(key, value)| (key.clone(), value.clone()))
                    .collect(),
            ));
        } else {
            out.push(block);
        }
    }
    Ok(out)
}

pub fn held_in_place(block: &Value) -> EngineResult<Value> {
    let id = subscript(block, "id")?.clone();
    let title = or_default(get(block, "title")?, json!("Homework"));
    let duration = subscript(block, "duration_min")?.clone();
    let days = Value::Array(list_of(subscript(block, "days")?)?);
    let start = subscript(block, "start")?.clone();
    Ok(json!({
        "id": id,
        "title": title,
        "kind": "locked",
        "duration_min": duration,
        "days": days,
        "start": start,
    }))
}

pub fn plan_start(
    week_start: &str,
    today_iso: &str,
    clock_minutes: i64,
    partial_minute: bool,
) -> EngineResult<Option<(i64, i64)>> {
    let day = (from_iso(today_iso)? - from_iso(week_start)?).num_days();
    if day < 0 {
        return Ok(None);
    }
    let minute = clock_minutes + i64::from(partial_minute);
    let minute = -((-minute).div_euclid(SLOT_MIN)) * SLOT_MIN;
    if minute >= DAY_END_MIN {
        return Ok(Some((day + 1, DAY_START_MIN)));
    }
    Ok(Some((day, minute)))
}

fn begun(block: &Value, not_before: Option<&Value>) -> EngineResult<bool> {
    let Some(not_before) = not_before.filter(|value| !value.is_null()) else {
        return Ok(false);
    };
    let here = json!([
        first_of(subscript(block, "days")?)?,
        minutes_of(subscript(block, "start")?)?
    ]);
    match not_before {
        Value::Array(_) => compare(Cmp::Lt, &here, not_before),
        other => Err(type_error(format!(
            "'<' not supported between instances of 'tuple' and '{}'",
            crate::stored::type_name(other)
        ))),
    }
}

fn from_not_before(session: &Value, not_before: &Value) -> EngineResult<Value> {
    let (day, minute) = unpack_pair(not_before)?;
    let mut days = Vec::new();
    for item in iterate(subscript(session, "days")?)? {
        if compare(Cmp::Ge, &item, &day)? {
            days.push(item);
        }
    }
    if days.is_empty() {
        days.push(day.clone());
    }
    let name = DAY_FULL[tuple_index(DAY_FULL.len(), &day)?];
    let earliest = format!("{name} {}", hhmm_of(&minute)?);
    let mut out = match session {
        Value::Object(fields) => fields.clone(),
        other => {
            return Err(type_error(format!(
                "'{}' object is not a mapping",
                crate::stored::type_name(other)
            )));
        }
    };
    out.insert("days".into(), Value::Array(days));
    out.insert("earliest".into(), json!(earliest));
    Ok(Value::Object(out))
}

pub fn solve_request(
    blocks: &Value,
    assignments: &Value,
    week_start: &str,
    everything: bool,
    only: Option<&Value>,
    not_before: Option<&Value>,
) -> EngineResult<(Vec<Value>, Vec<Value>)> {
    let mut payload = Vec::new();
    let mut targets: Vec<Value> = Vec::new();
    for block in iterate(blocks)? {
        if !eq(get(&block, "kind")?.unwrap_or(null()), &json!("flexible"))
            || truthy(get(&block, "completed")?)
        {
            payload.push(block);
            continue;
        }
        let planned = is_planned(&block)?;
        let kept = planned && (truthy(get(&block, "pinned")?) || begun(&block, not_before)?);
        let wanted = match only.filter(|value| !value.is_null()) {
            Some(only) => contains(only, subscript(&block, "id")?)?,
            None => (everything && !kept) || !planned,
        };
        if wanted {
            let mut session = match &block {
                Value::Object(fields) => fields.clone(),
                other => return Err(attribute_error(other, "get")),
            };
            if planned {
                session.shift_remove("start");
                session.insert(
                    "days".into(),
                    Value::Array(planning_days(&block, assignments, week_start)?),
                );
            }
            let session = Value::Object(session);
            payload.push(match not_before.filter(|value| !value.is_null()) {
                None => session,
                Some(limit) => from_not_before(&session, limit)?,
            });
            let id = subscript(&block, "id")?.clone();
            hashable(&id, "set element")?;
            if !targets.iter().any(|held| eq(held, &id)) {
                targets.push(id);
            }
        } else if planned {
            payload.push(held_in_place(&block)?);
        }
    }
    Ok((payload, targets))
}

pub fn due_point(due: &Value, week_start: &str) -> EngineResult<Option<(i64, i64)>> {
    if !truthy(Some(due)) {
        return Ok(None);
    }
    let text = match due {
        Value::String(found) => found.as_str(),
        other => {
            return Err(type_error(format!(
                "expected string or bytes-like object, got '{}'",
                crate::stored::type_name(other)
            )));
        }
    };
    let (due_day, minutes) = crate::model::parse_due(text)?;
    let offset = (due_day - from_iso(week_start)?).num_days();
    if offset > 6 {
        return Ok(None);
    }
    Ok(Some((offset, minutes)))
}

type Taken = Vec<Vec<(i64, i64, Value)>>;

fn taken_slot(day: &Value) -> EngineResult<usize> {
    hashable(day, "dict key")?;
    for slot in 0..7 {
        if eq(day, &json!(slot)) {
            return Ok(slot as usize);
        }
    }
    Err(match day {
        Value::String(name) => EngineError::key(name.as_str()),
        other => EngineError::key_repr(crate::stored::py_repr_of(other)),
    })
}

pub fn settle_placements(
    blocks: &Value,
    assignments: &Value,
    week_start: &str,
    keep: &Value,
    keep_is_set: bool,
) -> EngineResult<(Value, Vec<Value>)> {
    let all = iterate(blocks)?;
    let mut taken: Taken = vec![Vec::new(); 7];
    for block in &all {
        if !truthy(get(block, "start")?) {
            continue;
        }
        let start = minutes_of(subscript(block, "start")?)?;
        let span = int_of(&or_default(get(block, "duration_min")?, json!(0)))?;
        let end = start + span;
        if eq(get(block, "kind")?.unwrap_or(null()), &json!("locked")) {
            for day in iterate(&list_field(block, "days")?)? {
                if !contains(&list_field(block, "missed_days")?, &day)? {
                    taken[taken_slot(&day)?].push((
                        start,
                        end,
                        or_default(get(block, "title")?, json!("a fixed block")),
                    ));
                }
            }
        } else if truthy(get(block, "completed")?) {
            let days = list_field(block, "days")?;
            let only_day = if length(&days)? == 1 {
                first_of(&days)?
            } else {
                Value::Null
            };
            let day = get(block, "completed_day")?.cloned().unwrap_or(only_day);
            if !day.is_null() {
                taken[taken_slot(&day)?].push((
                    start,
                    end,
                    or_default(get(block, "title")?, json!("finished work")),
                ));
            }
        }
    }
    let mut keyed: Vec<(Value, Value)> = Vec::new();
    for block in &all {
        if !is_planned(block)? {
            continue;
        }
        let id = subscript(block, "id")?;
        let rank = !if keep_is_set {
            in_set(&iterate(keep)?, id)?
        } else {
            contains(keep, id)?
        };
        let key = json!([
            rank,
            first_of(subscript(block, "days")?)?,
            subscript(block, "start")?,
            id
        ]);
        keyed.push((key, block.clone()));
    }
    let mut failure = None;
    keyed.sort_by(|left, right| {
        order(&left.0, &right.0, Cmp::Lt).unwrap_or_else(|error| {
            failure.get_or_insert(error);
            std::cmp::Ordering::Equal
        })
    });
    if let Some(error) = failure {
        return Err(error);
    }
    let sessions: Vec<Value> = keyed.into_iter().map(|(_, block)| block).collect();
    let mut lost = PyDict::new();
    for block in &sessions {
        let day = first_of(subscript(block, "days")?)?;
        let start = minutes_of(subscript(block, "start")?)?;
        let end = start + int_of(&or_default(get(block, "duration_min")?, json!(0)))?;
        let found = table_get(
            assignments,
            &or_default(get(block, "assignment_id")?, json!("")),
        )?;
        let assignment = or_default(found, json!({}));
        let due = due_point(get(&assignment, "due")?.unwrap_or(null()), week_start)?;
        let pinned = truthy(get(block, "pinned")?);
        let slot = taken_slot(&day)?;
        let clash = if pinned {
            None
        } else {
            taken[slot]
                .iter()
                .find(|(low, high, _)| start < *high && *low < end)
                .map(|(_, _, title)| title.clone())
        };
        let why = if start < DAY_START_MIN || end > DAY_END_MIN {
            Some("that is outside the hours FlexWeek plans in".to_string())
        } else if due.is_some_and(|due| (int_of(&day).unwrap_or(0), end) > due) {
            Some("that is after it is due".to_string())
        } else {
            clash.map(|title| format!("{} is there now", py_str(&title)))
        };
        let Some(why) = why else {
            if !pinned {
                taken[slot].push((
                    start,
                    end,
                    or_default(get(block, "title")?, json!("homework")),
                ));
            }
            continue;
        };
        let title = or_default(get(block, "title")?, json!("Homework"));
        let shown = DAY_FULL[tuple_index(DAY_FULL.len(), &day)?];
        let stamp = crate::desk::weekmodel::hhmm_text(text(subscript(block, "start")?, "split")?);
        lost.set(
            subscript(block, "id")?.clone(),
            json!({
                "block_id": subscript(block, "id")?,
                "assignment_id": get(block, "assignment_id")?.cloned().unwrap_or(Value::Null),
                "title": title.clone(),
                "day": day,
                "start": subscript(block, "start")?,
                "message": format!("{} no longer fits {shown} at {stamp}: {why}.", py_str(&title)),
            }),
        )?;
    }
    if lost.is_empty() {
        return Ok((blocks.clone(), Vec::new()));
    }
    let mut out = Vec::new();
    for block in &all {
        if lost.contains(subscript(block, "id")?)? {
            let mut changed = match block {
                Value::Object(fields) => fields.clone(),
                other => return Err(attribute_error(other, "get")),
            };
            changed.shift_remove("start");
            changed.shift_remove("pinned");
            let changed_value = Value::Object(changed.clone());
            changed.insert(
                "days".into(),
                Value::Array(planning_days(&changed_value, assignments, week_start)?),
            );
            out.push(Value::Object(changed));
        } else {
            out.push(block.clone());
        }
    }
    let mut report = Vec::new();
    for block in &sessions {
        if let Some(entry) = lost.get(subscript(block, "id")?)? {
            report.push(entry.clone());
        }
    }
    Ok((Value::Array(out), report))
}

pub fn occurrence_days(block: &Value) -> EngineResult<Vec<Value>> {
    if truthy(Some(block))
        && eq(get(block, "kind")?.unwrap_or(null()), &json!("flexible"))
        && truthy(get(block, "completed")?)
    {
        let done = get(block, "completed_day")?.cloned().unwrap_or(Value::Null);
        if is_int(&done) {
            return Ok(vec![done]);
        }
        if let Some(days @ Value::Array(_)) = get(block, "days")?
            && length(days)? > 1
        {
            return Ok(Vec::new());
        }
    }
    let source = or_default(Some(block), json!({}));
    list_of(&or_default(get(&source, "days")?, json!([])))
}

pub fn session_minutes(blocks: &Value, assignment_id: &Value) -> EngineResult<i64> {
    let mut total = 0;
    for block in iterate(blocks)? {
        if eq(
            get(&block, "assignment_id")?.unwrap_or(null()),
            assignment_id,
        ) && !truthy(get(&block, "completed")?)
        {
            total += py_int(subscript(&block, "duration_min")?)?;
        }
    }
    Ok(total)
}

pub fn floor_slot(minutes: i64) -> i64 {
    (minutes.max(0) / SLOT_MIN) * SLOT_MIN
}

pub fn available_homework_minutes(
    assignment: &Value,
    blocks: &Value,
    committed: &Value,
) -> EngineResult<i64> {
    if !truthy(Some(assignment)) || truthy(get(assignment, "completed")?) {
        return Ok(0);
    }
    let id = subscript(assignment, "id")?;
    let here = session_minutes(blocks, id)?;
    let committed = session_minutes(&or_default(Some(committed), json!([])), id)?;
    match get(assignment, "unplanned_min")? {
        None | Some(Value::Null) => {
            let estimate = int_of(subscript(assignment, "estimate_min")?)?;
            let focus = int_of(&or_default(get(assignment, "focus_minutes")?, json!(0)))?;
            Ok(floor_slot((estimate - focus).max(0) - here))
        }
        Some(server) => Ok(floor_slot(py_int(server)? + committed - here)),
    }
}

pub fn block_occurs_on_day(
    block: &Value,
    day: &Value,
    placed: Option<&Value>,
) -> EngineResult<bool> {
    let flexible = is_homework_session(block)?
        || eq(get(block, "kind")?.unwrap_or(null()), &json!("flexible"));
    if flexible {
        let mut source = truthy(get(block, "start")?).then(|| block.clone());
        if source.is_none()
            && let Some(placed) = placed.filter(|list| truthy(Some(list)))
        {
            for item in iterate(placed)? {
                if eq(
                    get(&item, "id")?.unwrap_or(null()),
                    get(block, "id")?.unwrap_or(null()),
                ) && contains(&Value::Array(occurrence_days(&item)?), day)?
                {
                    source = Some(item);
                    break;
                }
            }
        }
        let Some(source) = source else {
            return Ok(false);
        };
        return Ok(truthy(Some(&source))
            && truthy(get(&source, "start")?)
            && contains(&Value::Array(occurrence_days(&source)?), day)?);
    }
    contains(&Value::Array(occurrence_days(block)?), day)
}

pub fn clipboard_fingerprint(items: &Value) -> EngineResult<String> {
    let mut payload = Vec::new();
    for item in iterate(items)? {
        payload.push(json!({
            "block": subscript(&item, "block")?,
            "source_day": subscript(&item, "source_day")?,
            "scope": subscript(&item, "scope")?,
        }));
    }
    Ok(dumps_sorted(&Value::Array(payload)))
}

pub fn capacity_problem(existing: i64, added: i64, label: &str) -> String {
    if i128::from(existing) + i128::from(added) > 100 {
        return format!(
            "{label} would exceed 100 blocks. Uncheck an item or remove a block first."
        );
    }
    String::new()
}

pub fn late_from_start(minute: i64) -> String {
    let snapped = minute.div_euclid(SLOT_MIN) * SLOT_MIN;
    minutes_to_hhmm(snapped.clamp(DAY_START_MIN, DAY_END_MIN - SLOT_MIN))
}

pub fn running_late_block(
    day: &Value,
    from_start: &str,
    minutes: i64,
    block_id: &Value,
) -> EngineResult<Value> {
    let start = hhmm_to_minutes(from_start)?;
    let duration = minutes.min(DAY_END_MIN - start);
    Ok(json!({
        "id": block_id,
        "kind": "locked",
        "title": "Running late",
        "duration_min": duration,
        "days": [day],
        "start": from_start,
        "priority": 1,
        "energy": "medium",
        "category": "downtime",
        "completed": false,
        "missed_days": [],
    }))
}

pub fn late_locked_line(block: &Value, moved: &Value) -> EngineResult<String> {
    let start = hhmm_to_minutes(&py_str(subscript(block, "start")?))?;
    let end = start + int_of(subscript(block, "duration_min")?)?;
    let extra = if truthy(Some(moved)) {
        format!("{} moved.", py_str(moved))
    } else {
        "Nothing had to move.".to_string()
    };
    Ok(format!(
        "Running late: {}–{} is now locked. {extra}",
        crate::desk::weekmodel::clock_text(start),
        crate::desk::weekmodel::clock_text(end)
    ))
}

pub fn copy_label(block: &Value, source_day: &Value, scope: &Value) -> EngineResult<Value> {
    let title = subscript(block, "title")?.clone();
    let series = eq(get(block, "kind")?.unwrap_or(null()), &json!("locked"))
        && length(&list_field(block, "days")?)? > 1;
    if eq(scope, &json!("series")) {
        return Ok(json!(format!("{} (all days)", py_str(&title))));
    }
    if series {
        let name = DAY_FULL[tuple_index(DAY_FULL.len(), source_day)?];
        return Ok(json!(format!("{} ({name} only)", py_str(&title))));
    }
    Ok(title)
}
