//! Week-grid edits and Day/Month helpers from `desktop/native/calendar.py`, on the values as the
//! Python code held them, so a wrong kind of value raises what Python raised.

use chrono::Datelike;
use serde_json::{Map, Value, json};

use crate::desk::calendar::{FIRST_MONTH, LAST_MONTH, is_series_checked};
use crate::desk::pydate::{add_days_text, from_iso};
use crate::desk::pyops::{
    Cmp, PyDict, add, compare, contains, eq, get, hashable, head, iterate, length, or_default,
    order,
};
use crate::desk::pyval::{subscript, type_error};
use crate::error::{EngineError, EngineResult};
use crate::stored::{attribute_error, py_int, py_str, text, truthy, type_name};
use crate::time::{DAY_END_MIN, DAY_START_MIN, hhmm_to_minutes, minutes_to_hhmm};

type Fresh<'a> = &'a mut dyn FnMut() -> String;

fn null() -> &'static Value {
    static NULL: Value = Value::Null;
    &NULL
}

fn empty_list() -> Value {
    json!([])
}

fn minutes_of(start: &Value) -> EngineResult<i64> {
    hhmm_to_minutes(text(start, "split")?)
}

/// `block.get(key) or []`.
fn list_field(block: &Value, key: &str) -> EngineResult<Value> {
    Ok(or_default(get(block, key)?, empty_list()))
}

/// `a, b = value`: a pair, however it is held.
pub fn unpack_pair(value: &Value) -> EngineResult<(Value, Value)> {
    let items = match value {
        Value::Array(items) => items.clone(),
        Value::String(_) | Value::Object(_) => iterate(value)?,
        other => {
            return Err(type_error(format!(
                "cannot unpack non-iterable {} object",
                type_name(other)
            )));
        }
    };
    match items.len() {
        2 => Ok((items[0].clone(), items[1].clone())),
        count if count < 2 => Err(EngineError::value(format!(
            "not enough values to unpack (expected 2, got {count})"
        ))),
        count => Err(EngineError::value(if matches!(value, Value::Array(_)) {
            format!("too many values to unpack (expected 2, got {count})")
        } else {
            "too many values to unpack (expected 2)".to_string()
        })),
    }
}

/// `year, month = (int(part) for part in text.split("-"))`: the parts are read one at a time.
fn year_and_month(month: &str) -> EngineResult<(i64, i64)> {
    let mut read = Vec::new();
    for part in month.split('-') {
        let number = crate::time::py_int(part)?;
        if read.len() == 2 {
            return Err(EngineError::value("too many values to unpack (expected 2)"));
        }
        read.push(number);
    }
    match read.as_slice() {
        [year, month] => Ok((*year, *month)),
        other => Err(EngineError::value(format!(
            "not enough values to unpack (expected 2, got {})",
            other.len()
        ))),
    }
}

pub fn monday_of(iso_day: &str) -> EngineResult<String> {
    crate::desk::pydate::monday_text(iso_day)
}

/// `(date.fromisoformat(week_start) + timedelta(days=day)).isoformat()`, `day` as held.
pub fn date_for_day(week_start: &str, day: &Value) -> EngineResult<String> {
    let start = from_iso(week_start)?;
    Ok(crate::desk::pydate::iso_text(crate::stored::add_days_of(
        start, day,
    )?))
}

pub fn sunday_due(week_start: &str) -> EngineResult<String> {
    Ok(format!(
        "{}T23:59",
        date_for_day(week_start, &Value::from(6))?
    ))
}

fn pair(first: Value, second: Value) -> Value {
    Value::Array(vec![first, second])
}

pub fn occupied_intervals(blocks: &Value, day: &Value) -> EngineResult<Vec<Value>> {
    let mut intervals: Vec<Value> = Vec::new();
    for block in iterate(blocks)? {
        if !truthy(get(&block, "start")?) {
            continue;
        }
        if !contains(&list_field(&block, "days")?, day)? {
            continue;
        }
        if contains(&list_field(&block, "missed_days")?, day)? {
            continue;
        }
        let begin = Value::from(minutes_of(subscript(&block, "start")?)?);
        let end = add(&begin, subscript(&block, "duration_min")?)?;
        intervals.push(pair(begin, end));
    }
    intervals
        .sort_by(|left, right| order(left, right, Cmp::Lt).unwrap_or(std::cmp::Ordering::Equal));
    Ok(intervals)
}

pub fn create_click_range(begin: i64, occupied: &Value) -> EngineResult<Option<Value>> {
    let begin_value = Value::from(begin);
    let mut stop = Value::from((begin + 60).min(DAY_END_MIN));
    for slot in iterate(occupied)? {
        let (slot_start, _slot_end) = unpack_pair(&slot)?;
        if compare(Cmp::Le, &begin_value, &slot_start)? && compare(Cmp::Lt, &slot_start, &stop)? {
            stop = slot_start;
            break;
        }
    }
    if compare(Cmp::Le, &stop, &begin_value)? {
        return Ok(None);
    }
    Ok(Some(pair(begin_value, stop)))
}

pub fn apply_block_times(
    block: &Value,
    start_min: i64,
    end_min: i64,
    day: Option<i64>,
) -> EngineResult<Option<Value>> {
    if !truthy(get(block, "start")?) {
        return Ok(None);
    }
    if is_series_checked(block)? {
        return Ok(None);
    }
    let duration = end_min - start_min;
    if duration <= 0 || start_min < DAY_START_MIN || end_min > DAY_END_MIN {
        return Ok(None);
    }
    let mut updated = block.clone();
    let Value::Object(fields) = &mut updated else {
        return Err(attribute_error(block, "get"));
    };
    fields.insert("start".into(), json!(minutes_to_hhmm(start_min)));
    fields.insert("duration_min".into(), json!(duration));
    if let Some(day) = day {
        let held = iterate(&list_field(block, "days")?)?;
        if !eq(&Value::Array(held), &json!([day])) {
            fields.insert("days".into(), json!([day]));
            if get(&updated, "completed_day")?.is_some_and(|value| !value.is_null())
                && let Value::Object(fields) = &mut updated
            {
                fields.insert("completed_day".into(), json!(day));
            }
        }
    }
    Ok(Some(updated))
}

fn object_mut<'a>(
    value: &'a mut Value,
    original: &Value,
) -> EngineResult<&'a mut Map<String, Value>> {
    match value {
        Value::Object(fields) => Ok(fields),
        _ => Err(crate::desk::pyops::item_assignment(original)),
    }
}

/// `[item for item in values if keep(item)]`, over what `values` iterates.
fn filtered(
    values: &Value,
    mut keep: impl FnMut(&Value) -> EngineResult<bool>,
) -> EngineResult<Vec<Value>> {
    let mut kept = Vec::new();
    for item in iterate(values)? {
        if keep(&item)? {
            kept.push(item);
        }
    }
    Ok(kept)
}

fn id_is(item: &Value, wanted: &Value) -> EngineResult<bool> {
    Ok(eq(subscript(item, "id")?, wanted))
}

pub fn split_occurrence(
    blocks: &Value,
    block_id: &Value,
    day: &Value,
    fresh: Fresh<'_>,
) -> EngineResult<(Vec<Value>, Option<String>)> {
    let all = iterate(blocks)?;
    let mut current = None;
    for item in &all {
        if id_is(item, block_id)? {
            current = Some(item.clone());
            break;
        }
    }
    let current = current.ok_or_else(EngineError::stop)?;
    let held_days = subscript(&current, "days")?;
    if !contains(held_days, day)? || length(held_days)? == 1 {
        return Ok((all, None));
    }
    let mut remaining = current.clone();
    let days = filtered(held_days, |item| Ok(!eq(item, day)))?;
    let missed = {
        let list = list_field(&current, "missed_days")?;
        filtered(&list, |item| contains(&Value::Array(days.clone()), item))?
    };
    {
        let fields = object_mut(&mut remaining, &current)?;
        fields.insert("days".into(), Value::Array(days));
        fields.insert("missed_days".into(), Value::Array(missed));
    }
    let mut occurrence = current.clone();
    let new_id = fresh();
    let was_missed = contains(&list_field(&current, "missed_days")?, day)?;
    {
        let fields = object_mut(&mut occurrence, &current)?;
        fields.insert("id".into(), json!(new_id));
        fields.insert("days".into(), json!([day]));
        fields.insert(
            "missed_days".into(),
            if was_missed { json!([day]) } else { json!([]) },
        );
    }
    let mut replaced = Vec::new();
    for item in &all {
        replaced.push(if id_is(item, block_id)? {
            remaining.clone()
        } else {
            item.clone()
        });
    }
    replaced.push(occurrence);
    Ok((replaced, Some(new_id)))
}

pub fn delete_occurrence(
    blocks: &Value,
    block_id: &Value,
    day: &Value,
) -> EngineResult<Vec<Value>> {
    let mut result = Vec::new();
    for item in iterate(blocks)? {
        if !id_is(&item, block_id)? {
            result.push(item);
            continue;
        }
        if day.is_null() {
            continue;
        }
        let days = subscript(&item, "days")?;
        if length(days)? <= 1 || !contains(days, day)? {
            continue;
        }
        let mut kept = item.clone();
        let remaining = filtered(days, |value| Ok(!eq(value, day)))?;
        let missed = {
            let list = list_field(&kept, "missed_days")?;
            filtered(&list, |value| {
                contains(&Value::Array(remaining.clone()), value)
            })?
        };
        let nothing_left = remaining.is_empty();
        let fields = object_mut(&mut kept, &item)?;
        fields.insert("days".into(), Value::Array(remaining));
        fields.insert("missed_days".into(), Value::Array(missed));
        if !nothing_left {
            result.push(kept);
        }
    }
    Ok(result)
}

pub fn apply_block_edit(
    blocks: &Value,
    block: &Value,
    scope: &Value,
    day: &Value,
    fresh: Fresh<'_>,
) -> EngineResult<Vec<Value>> {
    let all = iterate(blocks)?;
    let mut current = None;
    for item in &all {
        if eq(subscript(item, "id")?, subscript(block, "id")?) {
            current = Some(item.clone());
            break;
        }
    }
    if eq(scope, &json!("occurrence"))
        && let Some(current) = &current
        && !day.is_null()
        && is_series_checked(current)?
    {
        let (split, new_id) = split_occurrence(blocks, subscript(block, "id")?, day, fresh)?;
        let mut updated = block.clone();
        let made = match new_id {
            Some(id) => json!(id),
            None => subscript(block, "id")?.clone(),
        };
        let missed = {
            let list = or_default(get(&updated, "missed_days")?, empty_list());
            filtered(&list, |item| contains(&json!([day]), item))?
        };
        {
            let fields = object_mut(&mut updated, block)?;
            fields.insert("id".into(), made.clone());
            fields.insert("days".into(), json!([day]));
            fields.insert("missed_days".into(), Value::Array(missed));
        }
        let mut out = Vec::new();
        for item in split {
            out.push(if id_is(&item, &made)? {
                updated.clone()
            } else {
                item
            });
        }
        return Ok(out);
    }
    let mut replaced = false;
    let mut result = Vec::new();
    for item in all {
        if eq(subscript(&item, "id")?, subscript(block, "id")?) {
            result.push(block.clone());
            replaced = true;
        } else {
            result.push(item);
        }
    }
    if !replaced {
        result.push(block.clone());
    }
    Ok(result)
}

pub fn relocate_block(
    source: &Value,
    block_id: &Value,
    from_day: &Value,
    to_day: &Value,
    dest: Option<&Value>,
    fresh: Fresh<'_>,
) -> EngineResult<Option<(Vec<Value>, Option<Vec<Value>>, Value)>> {
    let all = iterate(source)?;
    let mut found = None;
    for item in &all {
        if id_is(item, block_id)? {
            found = Some(item.clone());
            break;
        }
    }
    let Some(block) = found else {
        return Ok(None);
    };
    if !contains(&list_field(&block, "days")?, from_day)? || !truthy(get(&block, "start")?) {
        return Ok(None);
    }
    let for_date = |item: &Value| -> EngineResult<Value> {
        let mut out = item.clone();
        let linked = truthy(get(&out, "assignment_id")?)
            && eq(get(&out, "kind")?.unwrap_or(null()), &json!("flexible"))
            && !truthy(get(&out, "completed")?);
        let moved = eq(get(&out, "completed_day")?.unwrap_or(null()), from_day);
        let missed = {
            let list = list_field(&out, "missed_days")?;
            filtered(&list, |day| contains(&json!([to_day]), day))?
        };
        let fields = object_mut(&mut out, item)?;
        fields.insert("days".into(), json!([to_day]));
        if linked {
            fields.insert("pinned".into(), json!(true));
        }
        if moved {
            fields.insert("completed_day".into(), to_day.clone());
        }
        fields.insert("missed_days".into(), Value::Array(missed));
        Ok(out)
    };
    let source_array = Value::Array(all.clone());
    let Some(dest) = dest else {
        if is_series_checked(&block)? {
            let mut before: Vec<Value> = Vec::new();
            for item in &all {
                let id = subscript(item, "id")?;
                hashable(id, "set element")?;
                before.push(id.clone());
            }
            let edited =
                apply_block_edit(&source_array, &block, &json!("occurrence"), from_day, fresh)?;
            let mut made = block_id.clone();
            for item in &edited {
                let id = subscript(item, "id")?;
                hashable(id, "set element")?;
                if !before.iter().any(|seen| eq(seen, id)) {
                    made = id.clone();
                    break;
                }
            }
            let mut out = Vec::new();
            for item in &edited {
                out.push(if id_is(item, &made)? {
                    for_date(item)?
                } else {
                    item.clone()
                });
            }
            return Ok(Some((out, None, made)));
        }
        let edited = apply_block_edit(
            &source_array,
            &for_date(&block)?,
            &json!("series"),
            &Value::Null,
            fresh,
        )?;
        return Ok(Some((edited, None, block_id.clone())));
    };
    let dest_items = iterate(dest)?;
    if is_series_checked(&block)? {
        let (split, new_id) = split_occurrence(&source_array, block_id, from_day, fresh)?;
        let made = new_id.map_or_else(|| block_id.clone(), |id| json!(id));
        let mut occurrence = None;
        for item in &split {
            if id_is(item, &made)? {
                occurrence = Some(item.clone());
                break;
            }
        }
        let occurrence = occurrence.ok_or_else(EngineError::stop)?;
        let mut source_out = Vec::new();
        for item in &split {
            if !id_is(item, &made)? {
                source_out.push(item.clone());
            }
        }
        let mut dest_out = dest_items;
        dest_out.push(for_date(&occurrence)?);
        return Ok(Some((source_out, Some(dest_out), made)));
    }
    let mut source_out = Vec::new();
    for item in &all {
        if !id_is(item, block_id)? {
            source_out.push(item.clone());
        }
    }
    let mut dest_out = dest_items;
    dest_out.push(for_date(&block)?);
    Ok(Some((source_out, Some(dest_out), block_id.clone())))
}

pub fn first_plannable_day(week_start: &str, today_iso: &str) -> EngineResult<i64> {
    let today = from_iso(today_iso)?;
    let monday = from_iso(week_start)?;
    if monday <= today {
        let last = crate::stored::add_days(monday, 6)?;
        if today <= last {
            return Ok(i64::from(today.weekday().num_days_from_monday()));
        }
    }
    Ok(0)
}

pub fn due_day_in_week(due: &str, week_start: &str) -> EngineResult<i64> {
    let head: String = due.chars().take(10).collect();
    let due_day = from_iso(&head)?;
    let monday = from_iso(week_start)?;
    Ok((due_day - monday).num_days())
}

/// `due_day_in_week` for a deadline that may be missing: no deadline, no day. A deadline that is
/// not text is refused as the Python binding refused it.
pub fn due_day_of(due: &Value, week_start: &str) -> EngineResult<Option<i64>> {
    if !truthy(Some(due)) {
        return Ok(None);
    }
    let Some(text) = due.as_str() else {
        return Err(type_error(format!(
            "argument 'due': '{}' object cannot be converted to 'PyString'",
            type_name(due)
        )));
    };
    due_day_in_week(text, week_start).map(Some)
}

pub fn month_for_view(iso_day: &str) -> String {
    let month: String = iso_day.chars().take(7).collect();
    if month.as_str() < FIRST_MONTH {
        FIRST_MONTH.to_string()
    } else if month.as_str() > LAST_MONTH {
        LAST_MONTH.to_string()
    } else {
        month
    }
}

pub fn shifted_month(month: &str, amount: i64) -> EngineResult<Option<String>> {
    let (year, month_number) = year_and_month(month)?;
    let index = i128::from(year) * 12 + i128::from(month_number - 1) + i128::from(amount);
    let next_year = index.div_euclid(12);
    let next_month = index.rem_euclid(12);
    let label = format!("{next_year:04}-{:02}", next_month + 1);
    if label.as_str() < FIRST_MONTH || label.as_str() > LAST_MONTH {
        return Ok(None);
    }
    Ok(Some(label))
}

pub fn month_anchor_date(selected_month: &str, today: &str) -> String {
    let head: String = today.chars().take(7).collect();
    if head == selected_month {
        today.to_string()
    } else {
        format!("{selected_month}-01")
    }
}

pub fn due_soon_for(iso_day: &str, assignments: &Value) -> EngineResult<Vec<Value>> {
    let tomorrow = add_days_text(iso_day, 1)?;
    let Value::Object(table) = assignments else {
        return Err(attribute_error(assignments, "values"));
    };
    let mut keyed: Vec<(Value, (chrono::NaiveDate, i64, String))> = Vec::new();
    let mut items: Vec<Value> = Vec::new();
    for item in table.values() {
        if truthy(get(item, "completed")?) {
            continue;
        }
        let due = get(item, "due")?.cloned().unwrap_or_else(|| json!("9999"));
        if !compare(Cmp::Le, &head(&due, 10)?, &json!(tomorrow))? {
            continue;
        }
        items.push(item.clone());
    }
    for item in items {
        let due = or_default(get(&item, "due")?, Value::Null);
        let due_text = match &due {
            Value::Null => None,
            Value::String(found) if !found.is_empty() => Some(found.as_str()),
            Value::String(_) => None,
            other if !truthy(Some(other)) => None,
            other => {
                return Err(type_error(format!(
                    "expected string or bytes-like object, got '{}'",
                    type_name(other)
                )));
            }
        };
        let identity = py_str(&or_default(get(&item, "id")?, json!("")));
        let key = crate::model::due_sort_key(due_text, &identity)?;
        keyed.push((item, key));
    }
    keyed.sort_by(|left, right| left.1.cmp(&right.1));
    Ok(keyed.into_iter().map(|(item, _)| item).collect())
}

pub enum Placed {
    NotToday,
    At(Value),
}

pub fn placement_on(block: &Value, day: &Value, trace: Option<&Value>) -> EngineResult<Placed> {
    let trace = trace.cloned().unwrap_or(Value::Null);
    let found = or_default(Some(&trace), json!({}));
    let placements = match get(&found, "placed")? {
        Some(list) => list.clone(),
        None => empty_list(),
    };
    let mut placed = None;
    for item in iterate(&placements)? {
        if eq(subscript(&item, "id")?, subscript(block, "id")?) {
            placed = Some(item);
            break;
        }
    }
    if let Some(placed) = &placed
        && truthy(Some(placed))
        && truthy(get(placed, "start")?)
    {
        return if contains(subscript(placed, "days")?, day)? {
            Ok(Placed::At(subscript(placed, "start")?.clone()))
        } else {
            Ok(Placed::NotToday)
        };
    }
    if truthy(get(block, "start")?) {
        return if contains(&list_field(block, "days")?, day)? {
            Ok(Placed::At(subscript(block, "start")?.clone()))
        } else {
            Ok(Placed::NotToday)
        };
    }
    Ok(Placed::At(Value::Null))
}

/// `_is_work_session`.
pub(crate) fn work_session(block: &Value) -> EngineResult<bool> {
    let kind = get(block, "kind")?.unwrap_or(null());
    if eq(kind, &json!("flexible")) {
        return Ok(true);
    }
    Ok(eq(kind, &json!("locked"))
        && eq(
            get(block, "pomodoro_role")?.unwrap_or(null()),
            &json!("work"),
        )
        && truthy(get(block, "assignment_id")?))
}

fn clock_order(row: &Value) -> EngineResult<(String, String)> {
    let start = subscript(row, "start")?;
    let shown = match start {
        Value::String(found) if !found.is_empty() => found.clone(),
        _ => "99:99".to_string(),
    };
    Ok((shown, py_str(subscript(subscript(row, "block")?, "id")?)))
}

pub fn agenda_for(
    week_start: &str,
    iso_day: &str,
    blocks: &Value,
    assignments: &Value,
    trace: Option<&Value>,
    day_data: Option<&Value>,
) -> EngineResult<Value> {
    let day_index = (from_iso(iso_day)? - from_iso(week_start)?).num_days();
    let mut sessions: Vec<Value> = Vec::new();
    let mut fixed: Vec<Value> = Vec::new();
    if (0..=6).contains(&day_index) {
        let index = Value::from(day_index);
        for block in iterate(blocks)? {
            if !contains(&list_field(&block, "days")?, &index)? {
                continue;
            }
            if contains(&list_field(&block, "missed_days")?, &index)? {
                continue;
            }
            let start = match placement_on(&block, &index, trace)? {
                Placed::NotToday => continue,
                Placed::At(start) => start,
            };
            let row = json!({"block": block.clone(), "start": start});
            if work_session(&block)? {
                sessions.push(row);
            } else if eq(get(&block, "kind")?.unwrap_or(null()), &json!("locked")) {
                fixed.push(row);
            }
        }
    }
    for rows in [&mut sessions, &mut fixed] {
        let mut keyed = Vec::new();
        for row in rows.drain(..) {
            keyed.push((clock_order(&row)?, row));
        }
        keyed.sort_by(|left, right| left.0.cmp(&right.0));
        rows.extend(keyed.into_iter().map(|(_, row)| row));
    }
    let due_soon = due_soon_for(iso_day, assignments)?;
    let next = next_action_for(
        &Value::Array(sessions.clone()),
        &Value::Array(due_soon.clone()),
        assignments,
        day_data,
    )?;
    Ok(json!({
        "day_index": day_index,
        "due_soon": due_soon,
        "sessions": sessions,
        "fixed": fixed,
        "next_action": next,
    }))
}

/// `table.get(key)` where the key is any value.
fn table_get<'a>(table: &'a Value, key: &Value) -> EngineResult<Option<&'a Value>> {
    let Value::Object(map) = table else {
        return Err(attribute_error(table, "get"));
    };
    hashable(key, "dict key")?;
    Ok(key.as_str().and_then(|name| map.get(name)))
}

pub fn next_action_for(
    sessions: &Value,
    due_soon: &Value,
    assignments: &Value,
    day_data: Option<&Value>,
) -> EngineResult<Value> {
    for row in iterate(sessions)? {
        // `assignments.get(...)` finds `get` before it reads the row.
        table_get(assignments, &Value::Null)?;
        let block = subscript(&row, "block")?;
        let link = or_default(get(block, "assignment_id")?, json!(""));
        let assignment = table_get(assignments, &link)?;
        if truthy(Some(subscript(&row, "start")?))
            && !truthy(get(block, "completed")?)
            && !truthy(match assignment {
                Some(found) if truthy(Some(found)) => get(found, "completed")?,
                _ => None,
            })
        {
            return Ok(json!({"kind": "start", "id": subscript(block, "id")?}));
        }
    }
    let day_data = or_default(day_data, json!({}));
    let mut unplanned = PyDict::new();
    let soon = or_default(get(&day_data, "due_soon")?, empty_list());
    for item in iterate(&soon)? {
        let key = subscript(&item, "id")?.clone();
        let amount = or_default(get(&item, "unplanned_min")?, json!(0));
        unplanned.set(key, amount)?;
    }
    for item in iterate(due_soon)? {
        let found = unplanned
            .get(subscript(&item, "id")?)?
            .cloned()
            .unwrap_or_else(|| json!(0));
        if compare(Cmp::Gt, &found, &json!(0))? {
            return Ok(json!({"kind": "plan", "id": subscript(&item, "id")?}));
        }
    }
    Ok(json!({"kind": "add"}))
}

pub fn is_setup_block(block: &Value) -> EngineResult<bool> {
    let id = py_str(&or_default(get(block, "id")?, json!("")));
    Ok(id == crate::desk::calendar::SETUP_SCHOOL_ID
        || id == "sport"
        || id.starts_with(crate::desk::calendar::SETUP_ACTIVITY_PREFIX))
}

pub fn span_problem(
    day: i64,
    start_min: i64,
    end_min: i64,
    due: &Value,
    due_type: &str,
) -> EngineResult<Option<&'static str>> {
    if start_min < DAY_START_MIN || end_min > DAY_END_MIN {
        return Ok(Some(
            "That is outside the hours FlexWeek plans in, so it stayed where it was.",
        ));
    }
    if !due.is_null() {
        let here = json!([day, end_min]);
        let later = match due {
            Value::Array(_) if due_type == "tuple" => compare(Cmp::Gt, &here, due)?,
            _ => {
                return Err(type_error(format!(
                    "'>' not supported between instances of 'tuple' and '{due_type}'"
                )));
            }
        };
        if later {
            return Ok(Some(
                "That ends after it is due, so it stayed where it was.",
            ));
        }
    }
    Ok(None)
}

/// A start before now (local date and minute) cannot be chosen. `now_iso` is that local date.
/// A bad date is not a past time: the caller already has its own check for a date it cannot read.
pub fn past_problem(
    week_start: &str,
    day: i64,
    start_min: i64,
    now_iso: &str,
    now_min: i64,
) -> EngineResult<Option<&'static str>> {
    let Ok(monday) = from_iso(week_start) else {
        return Ok(None);
    };
    let Ok(now) = from_iso(now_iso) else {
        return Ok(None);
    };
    let Ok(target) = crate::stored::add_days(monday, day) else {
        return Ok(None);
    };
    if target < now || (target == now && start_min < now_min) {
        return Ok(Some("That's in the past."));
    }
    Ok(None)
}

pub fn span_clash(
    blocks: &Value,
    block_id: &Value,
    day: &Value,
    start_min: i64,
    end_min: i64,
) -> EngineResult<Option<String>> {
    for other in iterate(blocks)? {
        if id_is(&other, block_id)? || !truthy(get(&other, "start")?) {
            continue;
        }
        if !contains(&list_field(&other, "days")?, day)?
            || contains(&list_field(&other, "missed_days")?, day)?
        {
            continue;
        }
        if truthy(get(&other, "completed")?) {
            let done = get(&other, "completed_day")?.unwrap_or(null());
            if !done.is_null() && !eq(done, day) {
                continue;
            }
        }
        let begin = minutes_of(subscript(&other, "start")?)?;
        let length = py_int(subscript(&other, "duration_min")?)?;
        if start_min < begin + length && begin < end_min {
            return Ok(Some(py_str(&or_default(
                get(&other, "title")?,
                json!("another block"),
            ))));
        }
    }
    Ok(None)
}

pub fn category_icon(category: Option<&str>) -> Option<&'static str> {
    crate::desk::calendar::category_icon(category)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deleting_a_whole_block_does_not_read_its_days() {
        let result = delete_occurrence(
            &json!([{"id": "x", "title": "t"}, {"id": "y"}]),
            &json!("x"),
            &Value::Null,
        );
        assert!(
            result
                .as_ref()
                .is_ok_and(|rows| rows == &vec![json!({"id": "y"})]),
            "{result:?}"
        );
    }

    #[test]
    fn a_deadline_is_counted_in_days_from_the_week_start() {
        assert_eq!(
            due_day_of(&json!("2026-09-24"), "2026-09-21").unwrap(),
            Some(3)
        );
        assert_eq!(
            due_day_of(&json!("2026-09-24T21:00"), "2026-09-21").unwrap(),
            Some(3)
        );
        assert_eq!(
            due_day_of(&json!("2026-09-14"), "2026-09-21").unwrap(),
            Some(-7)
        );
    }

    #[test]
    fn no_deadline_is_no_day() {
        for none in [
            json!(null),
            json!(""),
            json!(0),
            json!(false),
            json!([]),
            json!({}),
        ] {
            assert_eq!(due_day_of(&none, "not a date").unwrap(), None);
        }
    }

    #[test]
    fn a_start_before_now_is_in_the_past_and_a_later_week_is_not() {
        let week = "2026-10-05";
        let thursday = "2026-10-08";
        let at = 15 * 60 + 10;
        assert_eq!(
            past_problem(week, 1, 16 * 60, thursday, at).unwrap(),
            Some("That's in the past."),
            "Tuesday of this week"
        );
        assert_eq!(
            past_problem(week, 3, 15 * 60, thursday, at).unwrap(),
            Some("That's in the past."),
            "earlier today"
        );
        assert_eq!(
            past_problem(week, 3, at, thursday, at).unwrap(),
            None,
            "this minute is not past"
        );
        assert_eq!(
            past_problem(week, 3, 15 * 60 + 15, thursday, at).unwrap(),
            None,
            "later today"
        );
        assert_eq!(
            past_problem("2026-09-28", 4, 18 * 60, thursday, at).unwrap(),
            Some("That's in the past."),
            "last week"
        );
        assert_eq!(
            past_problem("2026-10-12", 0, 8 * 60, thursday, at).unwrap(),
            None,
            "next week"
        );
        assert_eq!(
            past_problem("not a date", 0, 0, thursday, at).unwrap(),
            None
        );
    }

    #[test]
    fn a_deadline_that_is_not_text_is_refused() {
        let error = due_day_of(&json!(7), "2026-09-21").unwrap_err();
        assert_eq!(
            error.message,
            "argument 'due': 'int' object cannot be converted to 'PyString'"
        );
        assert!(due_day_of(&json!("x"), "2026-09-21").is_err());
    }
}
