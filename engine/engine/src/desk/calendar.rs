//! Week-grid edits and calendar helpers from `desktop/native/calendar.py`.

use chrono::{Datelike, Duration, NaiveDate};

fn iso_date(day: NaiveDate) -> String {
    format!("{:04}-{:02}-{:02}", day.year(), day.month(), day.day())
}
use serde_json::{Map, Value, json};

use crate::error::{EngineError, EngineResult};
use crate::time::{self, DAY_END_MIN, DAY_START_MIN, hhmm_to_minutes, minutes_to_hhmm};

pub const LOCKED_CATEGORIES: [&str; 6] = ["class", "exercise", "extra", "meals", "sleep", "free"];
pub const FLEX_CATEGORIES: [&str; 2] = ["assignments", "study"];
pub const WEEKDAYS: [i64; 5] = [0, 1, 2, 3, 4];
pub const DAYS: [&str; 7] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
pub const DAY_FULL: [&str; 7] = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
];
pub const FIRST_MONTH: &str = "2000-01";
pub const LAST_MONTH: &str = "2099-12";
pub const SERIES_DRAG_MESSAGE: &str = "{title} repeats on {count} days, so dragging it is ambiguous. Edit the occurrence or the series.";
pub const SETUP_SCHOOL_ID: &str = "school";
pub const SETUP_ACTIVITY_PREFIX: &str = "activity-";

pub fn category_title(category: Option<&str>) -> &'static str {
    CATEGORIES
        .iter()
        .find(|(key, _)| Some(*key) == category)
        .map(|(_, info)| info.label)
        .unwrap_or("Fixed time")
}

pub fn is_series(block: &Value) -> bool {
    block.get("kind").and_then(Value::as_str) == Some("locked")
        && block
            .get("days")
            .and_then(Value::as_array)
            .map(|d| d.len() > 1)
            .unwrap_or(false)
}

fn parse_iso_day(value: &str) -> Option<NaiveDate> {
    NaiveDate::parse_from_str(value, "%Y-%m-%d").ok()
}

pub fn monday_of(iso_day: &str) -> String {
    let day = parse_iso_day(iso_day).expect("iso day");
    let monday = day - Duration::days(i64::from(day.weekday().num_days_from_monday()));
    iso_date(monday)
}

pub fn date_for_day(week_start: &str, day: i64) -> String {
    let start = parse_iso_day(week_start).expect("week start");
    iso_date(start + Duration::days(day))
}

pub fn sunday_due(week_start: &str) -> String {
    format!("{}T23:59", date_for_day(week_start, 6))
}

pub fn local_stamp(now_iso_minute: Option<&str>) -> String {
    if let Some(stamp) = now_iso_minute {
        return stamp.to_string();
    }
    String::new()
}

pub fn occupied_intervals(blocks: &[Value], day: i64) -> Vec<(i64, i64)> {
    let mut intervals = Vec::new();
    for block in blocks {
        if block.get("start").is_none() {
            continue;
        }
        let days = block.get("days").and_then(Value::as_array);
        if !days.is_some_and(|d| d.iter().any(|v| v.as_i64() == Some(day))) {
            continue;
        }
        if block
            .get("missed_days")
            .and_then(Value::as_array)
            .is_some_and(|m| m.iter().any(|v| v.as_i64() == Some(day)))
        {
            continue;
        }
        let begin =
            hhmm_to_minutes(block.get("start").and_then(Value::as_str).unwrap_or("")).unwrap_or(0);
        let duration = block
            .get("duration_min")
            .and_then(Value::as_i64)
            .unwrap_or(0);
        intervals.push((begin, begin + duration));
    }
    intervals.sort_unstable();
    intervals
}

pub fn create_click_range(begin: i64, occupied: &[(i64, i64)]) -> Option<(i64, i64)> {
    let mut stop = (begin + 60).min(DAY_END_MIN);
    for (slot_start, _slot_end) in occupied {
        if begin <= *slot_start && *slot_start < stop {
            stop = *slot_start;
            break;
        }
    }
    if stop <= begin {
        return None;
    }
    Some((begin, stop))
}

pub fn apply_block_times(
    block: &Value,
    start_min: i64,
    end_min: i64,
    day: Option<i64>,
) -> Option<Value> {
    if block.get("start").is_none() || is_series(block) {
        return None;
    }
    let duration = end_min - start_min;
    if duration <= 0 || start_min < DAY_START_MIN || end_min > DAY_END_MIN {
        return None;
    }
    let mut updated = deep_copy(block);
    let obj = updated.as_object_mut()?;
    obj.insert("start".into(), json!(minutes_to_hhmm(start_min)));
    obj.insert("duration_min".into(), json!(duration));
    if let Some(day) = day {
        let days = block.get("days").and_then(Value::as_array);
        if days.map(|d| d.as_slice()) != Some(&[json!(day)]) {
            obj.insert("days".into(), json!([day]));
            if obj.contains_key("completed_day") {
                obj.insert("completed_day".into(), json!(day));
            }
        }
    }
    Some(updated)
}

pub fn split_occurrence(
    blocks: &[Value],
    block_id: &str,
    day: i64,
    new_id: &str,
) -> (Vec<Value>, Option<String>) {
    let current = blocks
        .iter()
        .find(|b| b.get("id").and_then(Value::as_str) == Some(block_id));
    let Some(current) = current else {
        return (blocks.iter().map(deep_copy).collect(), None);
    };
    let days = current.get("days").and_then(Value::as_array);
    if !days.is_some_and(|d| d.iter().any(|v| v.as_i64() == Some(day)))
        || days.is_some_and(|d| d.len() == 1)
    {
        return (blocks.iter().map(deep_copy).collect(), None);
    }
    let new_days: Vec<i64> = days
        .unwrap()
        .iter()
        .filter_map(Value::as_i64)
        .filter(|d| *d != day)
        .collect();
    let missed: Vec<i64> = current
        .get("missed_days")
        .and_then(Value::as_array)
        .map(|m| {
            m.iter()
                .filter_map(Value::as_i64)
                .filter(|d| new_days.contains(d))
                .collect()
        })
        .unwrap_or_default();
    let mut remaining = deep_copy(current);
    if let Some(obj) = remaining.as_object_mut() {
        obj.insert("days".into(), json!(new_days));
        obj.insert("missed_days".into(), json!(missed));
    }
    let mut occurrence = deep_copy(current);
    if let Some(obj) = occurrence.as_object_mut() {
        obj.insert("id".into(), json!(new_id));
        obj.insert("days".into(), json!([day]));
        let missed = current
            .get("missed_days")
            .and_then(Value::as_array)
            .is_some_and(|m| m.iter().any(|v| v.as_i64() == Some(day)));
        obj.insert(
            "missed_days".into(),
            json!(if missed { vec![day] } else { Vec::<i64>::new() }),
        );
    }
    let mut replaced: Vec<Value> = blocks
        .iter()
        .map(|item| {
            if item.get("id").and_then(Value::as_str) == Some(block_id) {
                deep_copy(&remaining)
            } else {
                deep_copy(item)
            }
        })
        .collect();
    replaced.push(occurrence);
    (replaced, Some(new_id.to_string()))
}

pub fn delete_occurrence(blocks: &[Value], block_id: &str, day: Option<i64>) -> Vec<Value> {
    let mut result = Vec::new();
    for item in blocks {
        if item.get("id").and_then(Value::as_str) != Some(block_id) {
            result.push(deep_copy(item));
            continue;
        }
        let days = item.get("days").and_then(Value::as_array);
        if day.is_none()
            || days.map(|d| d.len()).unwrap_or(0) <= 1
            || !days.is_some_and(|d| d.iter().any(|v| v.as_i64() == day))
        {
            continue;
        }
        let kept_days: Vec<i64> = days
            .unwrap()
            .iter()
            .filter_map(Value::as_i64)
            .filter(|d| Some(*d) != day)
            .collect();
        let missed: Vec<i64> = item
            .get("missed_days")
            .and_then(Value::as_array)
            .map(|m| {
                m.iter()
                    .filter_map(Value::as_i64)
                    .filter(|d| kept_days.contains(d))
                    .collect()
            })
            .unwrap_or_default();
        let mut kept = deep_copy(item);
        if let Some(obj) = kept.as_object_mut() {
            obj.insert("days".into(), json!(kept_days));
            obj.insert("missed_days".into(), json!(missed));
        }
        if kept
            .get("days")
            .and_then(Value::as_array)
            .is_some_and(|d| !d.is_empty())
        {
            result.push(kept);
        }
    }
    result
}

pub fn apply_block_edit(
    blocks: &[Value],
    block: &Value,
    scope: &str,
    day: Option<i64>,
    new_occurrence_id: &str,
) -> Vec<Value> {
    let block_id = block.get("id").and_then(Value::as_str).unwrap_or("");
    let current = blocks
        .iter()
        .find(|item| item.get("id").and_then(Value::as_str) == Some(block_id));
    if let (Some(current), Some(day)) = (current, day)
        && scope == "occurrence"
        && is_series(current)
    {
        let (split, new_id) = split_occurrence(blocks, block_id, day, new_occurrence_id);
        let target_days = vec![day];
        let missed: Vec<i64> = block
            .get("missed_days")
            .and_then(Value::as_array)
            .map(|m| {
                m.iter()
                    .filter_map(Value::as_i64)
                    .filter(|d| target_days.contains(d))
                    .collect()
            })
            .unwrap_or_default();
        let mut updated = deep_copy(block);
        if let Some(obj) = updated.as_object_mut() {
            obj.insert("id".into(), json!(new_id.as_deref().unwrap_or(block_id)));
            obj.insert("days".into(), json!(target_days));
            obj.insert("missed_days".into(), json!(missed));
        }
        let uid = updated.get("id").and_then(Value::as_str).unwrap_or("");
        return split
            .into_iter()
            .map(|item| {
                if item.get("id").and_then(Value::as_str) == Some(uid) {
                    updated.clone()
                } else {
                    item
                }
            })
            .collect();
    }
    let mut replaced = false;
    let mut result = Vec::new();
    for item in blocks {
        if item.get("id").and_then(Value::as_str) == Some(block_id) {
            result.push(deep_copy(block));
            replaced = true;
        } else {
            result.push(deep_copy(item));
        }
    }
    if !replaced {
        result.push(deep_copy(block));
    }
    result
}

pub fn relocate_block(
    source: &[Value],
    block_id: &str,
    from_day: i64,
    to_day: i64,
    dest: Option<&[Value]>,
    new_id: &str,
) -> Option<(Vec<Value>, Option<Vec<Value>>, String)> {
    let block = source
        .iter()
        .find(|item| item.get("id").and_then(Value::as_str) == Some(block_id))?;
    if !block
        .get("days")
        .and_then(Value::as_array)
        .is_some_and(|d| d.iter().any(|v| v.as_i64() == Some(from_day)))
        || block.get("start").is_none()
    {
        return None;
    }

    fn for_date(item: &Value, from_day: i64, to_day: i64) -> Value {
        let mut out = deep_copy(item);
        if let Some(obj) = out.as_object_mut() {
            obj.insert("days".into(), json!([to_day]));
            if obj.get("assignment_id").is_some()
                && obj.get("kind").and_then(Value::as_str) == Some("flexible")
                && obj.get("completed").and_then(Value::as_bool) != Some(true)
            {
                obj.insert("pinned".into(), json!(true));
            }
            if obj.get("completed_day").and_then(Value::as_i64) == Some(from_day) {
                obj.insert("completed_day".into(), json!(to_day));
            }
            let days = obj.get("days").and_then(Value::as_array).cloned();
            let missed: Vec<i64> = obj
                .get("missed_days")
                .and_then(Value::as_array)
                .map(|m| {
                    m.iter()
                        .filter_map(Value::as_i64)
                        .filter(|d| {
                            days.as_ref()
                                .is_some_and(|ds| ds.iter().any(|v| v.as_i64() == Some(*d)))
                        })
                        .collect()
                })
                .unwrap_or_default();
            obj.insert("missed_days".into(), json!(missed));
        }
        out
    }

    if dest.is_none() {
        if is_series(block) {
            let before: std::collections::HashSet<String> = source
                .iter()
                .filter_map(|item| item.get("id").and_then(Value::as_str).map(str::to_string))
                .collect();
            let edited = apply_block_edit(source, block, "occurrence", Some(from_day), new_id);
            let made = edited
                .iter()
                .find(|item| {
                    item.get("id")
                        .and_then(Value::as_str)
                        .is_some_and(|id| !before.contains(id))
                })
                .and_then(|item| item.get("id").and_then(Value::as_str))
                .unwrap_or(block_id)
                .to_string();
            let out = edited
                .into_iter()
                .map(|item| {
                    if item.get("id").and_then(Value::as_str) == Some(&made) {
                        for_date(&item, from_day, to_day)
                    } else {
                        deep_copy(&item)
                    }
                })
                .collect();
            return Some((out, None, made));
        }
        let out = apply_block_edit(
            source,
            &for_date(block, from_day, to_day),
            "series",
            None,
            new_id,
        );
        return Some((out, None, block_id.to_string()));
    }

    if is_series(block) {
        let (split, made_id) = split_occurrence(source, block_id, from_day, new_id);
        let made = made_id.unwrap_or_else(|| block_id.to_string());
        let occurrence = split
            .iter()
            .find(|item| item.get("id").and_then(Value::as_str) == Some(&made))
            .cloned()?;
        let source_out: Vec<Value> = split
            .into_iter()
            .filter(|item| item.get("id").and_then(Value::as_str) != Some(&made))
            .map(|item| deep_copy(&item))
            .collect();
        let mut dest_vec: Vec<Value> = dest.unwrap().iter().map(deep_copy).collect();
        dest_vec.push(for_date(&occurrence, from_day, to_day));
        return Some((source_out, Some(dest_vec), made));
    }
    let source_out: Vec<Value> = source
        .iter()
        .filter(|item| item.get("id").and_then(Value::as_str) != Some(block_id))
        .map(deep_copy)
        .collect();
    let mut dest_vec: Vec<Value> = dest.unwrap().iter().map(deep_copy).collect();
    dest_vec.push(for_date(block, from_day, to_day));
    Some((source_out, Some(dest_vec), block_id.to_string()))
}

pub fn first_plannable_day(week_start: &str, today_iso: &str) -> i64 {
    let today = parse_iso_day(today_iso).expect("today iso");
    let monday = parse_iso_day(week_start).expect("week");
    let sunday = monday + Duration::days(6);
    if monday <= today && today <= sunday {
        return i64::from(today.weekday().num_days_from_monday());
    }
    0
}

pub fn due_day_in_week(due: Option<&str>, week_start: &str) -> Option<i64> {
    let due = due?;
    let due_day = parse_iso_day(&due[..10])?;
    let monday = parse_iso_day(week_start)?;
    Some((due_day - monday).num_days())
}

pub fn days_through(due_day: Option<i64>, first_day: i64) -> Vec<i64> {
    let last = due_day.map(|d| d.min(6)).unwrap_or(6);
    if last < 0 {
        return Vec::new();
    }
    if last < first_day {
        return vec![last];
    }
    (0..7)
        .filter(|day| first_day <= *day && *day <= last)
        .collect()
}

pub fn month_for_view(iso_day: &str) -> String {
    let month = &iso_day[..7.min(iso_day.len())];
    if month < FIRST_MONTH {
        return FIRST_MONTH.to_string();
    }
    if month > LAST_MONTH {
        return LAST_MONTH.to_string();
    }
    month.to_string()
}

pub fn shifted_month(month: &str, amount: i64) -> Option<String> {
    let parts: Vec<&str> = month.split('-').collect();
    if parts.len() != 2 {
        return None;
    }
    let year: i64 = parts[0].parse().ok()?;
    let month_number: i64 = parts[1].parse().ok()?;
    let index = year * 12 + (month_number - 1) + amount;
    let (nxt_year, nxt_month) = (index.div_euclid(12), index.rem_euclid(12));
    let label = format!("{nxt_year:04}-{:02}", nxt_month + 1);
    if label.as_str() < FIRST_MONTH || label.as_str() > LAST_MONTH {
        return None;
    }
    Some(label)
}

pub fn month_anchor_date(selected_month: &str, today: &str) -> String {
    if today.len() >= 7 && &today[..7] == selected_month {
        return today.to_string();
    }
    format!("{selected_month}-01")
}

pub fn due_soon_for(iso_day: &str, assignments: &Map<String, Value>) -> Vec<Value> {
    let day = parse_iso_day(iso_day).expect("iso day");
    let tomorrow = iso_date(day + Duration::days(1));
    let mut items: Vec<Value> = assignments
        .values()
        .filter(|item| {
            item.get("completed").and_then(Value::as_bool) != Some(true)
                && item
                    .get("due")
                    .and_then(Value::as_str)
                    .unwrap_or("9999")
                    .get(..10)
                    .unwrap_or("9999")
                    <= tomorrow.as_str()
        })
        .cloned()
        .collect();
    items.sort_by(|a, b| {
        due_sort_key(
            a.get("due").and_then(Value::as_str),
            a.get("id").and_then(Value::as_str).unwrap_or(""),
        )
        .cmp(&due_sort_key(
            b.get("due").and_then(Value::as_str),
            b.get("id").and_then(Value::as_str).unwrap_or(""),
        ))
    });
    items
}

pub fn is_work_session(block: &Value) -> bool {
    block.get("kind").and_then(Value::as_str) == Some("flexible")
        || (block.get("kind").and_then(Value::as_str) == Some("locked")
            && block.get("pomodoro_role").and_then(Value::as_str) == Some("work")
            && block.get("assignment_id").is_some())
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PlacementOn {
    NotToday,
    None,
    Time(String),
}

pub fn placement_on(block: &Value, day: i64, trace: Option<&Value>) -> PlacementOn {
    let placed = trace
        .and_then(|t| t.get("placed"))
        .and_then(Value::as_array)
        .and_then(|items| {
            items.iter().find(|item| {
                item.get("id").and_then(Value::as_str) == block.get("id").and_then(Value::as_str)
            })
        });
    if let Some(placed) = placed
        && placed.get("start").is_some()
    {
        if placed
            .get("days")
            .and_then(Value::as_array)
            .is_some_and(|d| d.iter().any(|v| v.as_i64() == Some(day)))
        {
            return PlacementOn::Time(
                placed
                    .get("start")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
            );
        }
        return PlacementOn::NotToday;
    }
    if block.get("start").is_some() {
        if block
            .get("days")
            .and_then(Value::as_array)
            .is_some_and(|d| d.iter().any(|v| v.as_i64() == Some(day)))
        {
            return PlacementOn::Time(
                block
                    .get("start")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
            );
        }
        return PlacementOn::NotToday;
    }
    PlacementOn::None
}

pub fn agenda_for(
    week_start: &str,
    iso_day: &str,
    blocks: &[Value],
    assignments: &Map<String, Value>,
    trace: Option<&Value>,
    day_data: Option<&Value>,
) -> Value {
    let week = parse_iso_day(week_start).expect("week");
    let day = parse_iso_day(iso_day).expect("day");
    let day_index = (day - week).num_days();
    let mut sessions = Vec::new();
    let mut fixed = Vec::new();
    if (0..=6).contains(&day_index) {
        for block in blocks {
            if !block
                .get("days")
                .and_then(Value::as_array)
                .is_some_and(|d| d.iter().any(|v| v.as_i64() == Some(day_index)))
            {
                continue;
            }
            if block
                .get("missed_days")
                .and_then(Value::as_array)
                .is_some_and(|m| m.iter().any(|v| v.as_i64() == Some(day_index)))
            {
                continue;
            }
            let start = placement_on(block, day_index, trace);
            if start == PlacementOn::NotToday {
                continue;
            }
            let start_val = match start {
                PlacementOn::Time(s) => Value::String(s),
                PlacementOn::None => Value::Null,
                PlacementOn::NotToday => continue,
            };
            let row = json!({"block": block, "start": start_val});
            if is_work_session(block) {
                sessions.push(row);
            } else if block.get("kind").and_then(Value::as_str) == Some("locked") {
                fixed.push(row);
            }
        }
    }
    fn in_clock_order(row: &Value) -> (String, String) {
        let start = row.get("start");
        let key = match start {
            Some(Value::String(s)) if !s.is_empty() => s.clone(),
            _ => "99:99".to_string(),
        };
        let id = row
            .get("block")
            .and_then(|b| b.get("id"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        (key, id)
    }
    sessions.sort_by_key(in_clock_order);
    fixed.sort_by_key(in_clock_order);
    let due_soon = due_soon_for(iso_day, assignments);
    json!({
        "day_index": day_index,
        "due_soon": due_soon,
        "sessions": sessions,
        "fixed": fixed,
        "next_action": next_action_for(&sessions, &due_soon, assignments, day_data),
    })
}

pub fn next_action_for(
    sessions: &[Value],
    due_soon: &[Value],
    assignments: &Map<String, Value>,
    day_data: Option<&Value>,
) -> Value {
    for row in sessions {
        let block = row.get("block").unwrap();
        let assignment_id = block
            .get("assignment_id")
            .and_then(Value::as_str)
            .unwrap_or("");
        let assignment = assignments.get(assignment_id);
        if row.get("start").is_some()
            && block.get("completed").and_then(Value::as_bool) != Some(true)
            && assignment
                .and_then(|a| a.get("completed"))
                .and_then(Value::as_bool)
                != Some(true)
        {
            return json!({"kind": "start", "id": block.get("id")});
        }
    }
    let mut unplanned = Map::new();
    if let Some(list) = day_data
        .and_then(|d| d.get("due_soon"))
        .and_then(Value::as_array)
    {
        for item in list {
            if let Some(id) = item.get("id").and_then(Value::as_str) {
                unplanned.insert(
                    id.to_string(),
                    json!(
                        item.get("unplanned_min")
                            .and_then(Value::as_i64)
                            .unwrap_or(0)
                    ),
                );
            }
        }
    }
    for item in due_soon {
        let id = item.get("id").and_then(Value::as_str).unwrap_or("");
        if unplanned.get(id).and_then(Value::as_i64).unwrap_or(0) > 0 {
            return json!({"kind": "plan", "id": item.get("id")});
        }
    }
    json!({"kind": "add"})
}

pub fn is_setup_block(block: &Value) -> bool {
    let block_id = block.get("id").and_then(Value::as_str).unwrap_or("");
    block_id == SETUP_SCHOOL_ID
        || block_id == "sport"
        || block_id.starts_with(SETUP_ACTIVITY_PREFIX)
}

pub fn span_problem(
    _blocks: &[Value],
    _block_id: &str,
    day: i64,
    start_min: i64,
    end_min: i64,
    due: Option<(i64, i64)>,
) -> Option<&'static str> {
    if start_min < DAY_START_MIN || end_min > DAY_END_MIN {
        return Some("That is outside the hours FlexWeek plans in, so it stayed where it was.");
    }
    if let Some(due) = due
        && (day, end_min) > due
    {
        return Some("That ends after it is due, so it stayed where it was.");
    }
    None
}

pub fn span_clash(
    blocks: &[Value],
    block_id: &str,
    day: i64,
    start_min: i64,
    end_min: i64,
) -> Option<String> {
    for other in blocks {
        if other.get("id").and_then(Value::as_str) == Some(block_id) || other.get("start").is_none()
        {
            continue;
        }
        if !other
            .get("days")
            .and_then(Value::as_array)
            .is_some_and(|d| d.iter().any(|v| v.as_i64() == Some(day)))
            || other
                .get("missed_days")
                .and_then(Value::as_array)
                .is_some_and(|m| m.iter().any(|v| v.as_i64() == Some(day)))
        {
            continue;
        }
        if other.get("completed").and_then(Value::as_bool) == Some(true) {
            let completed_day = other.get("completed_day").and_then(Value::as_i64);
            if completed_day.is_some_and(|d| d != day) {
                continue;
            }
        }
        let begin =
            hhmm_to_minutes(other.get("start").and_then(Value::as_str).unwrap_or("")).unwrap_or(0);
        let other_end = begin
            + other
                .get("duration_min")
                .and_then(Value::as_i64)
                .unwrap_or(0);
        if start_min < other_end && begin < end_min {
            return Some(
                other
                    .get("title")
                    .and_then(Value::as_str)
                    .unwrap_or("another block")
                    .to_string(),
            );
        }
    }
    None
}

pub fn category_icon(category: Option<&str>) -> Option<&'static str> {
    if category == Some("homework") {
        return Some("book-open");
    }
    CATEGORIES
        .iter()
        .find(|(key, _)| Some(*key) == category)
        .and_then(|(_, info)| info.icon)
}

// --- due parsing (from backend.models, used by weekmodel and reuse) ---

pub const END_OF_DAY_MIN: i64 = 24 * 60;
pub const END_OF_DAY_CLOCK: &str = "23:59";

pub fn parse_due(value: &str) -> EngineResult<(NaiveDate, i64)> {
    if value.len() == 10 && value.as_bytes().get(4) == Some(&b'-') {
        let day = parse_iso_day(value).ok_or_else(|| {
            EngineError::value("must be YYYY-MM-DD or YYYY-MM-DDTHH:MM with no seconds or timezone")
        })?;
        return Ok((day, END_OF_DAY_MIN));
    }
    if value.len() >= 16 && value.as_bytes().get(10) == Some(&b'T') {
        let day = parse_iso_day(&value[..10]).ok_or_else(|| {
            EngineError::value("must be YYYY-MM-DD or YYYY-MM-DDTHH:MM with no seconds or timezone")
        })?;
        let clock = &value[11..16];
        if clock == END_OF_DAY_CLOCK {
            return Ok((day, END_OF_DAY_MIN));
        }
        let minutes = time::hhmm_to_minutes(clock)?;
        return Ok((day, minutes));
    }
    Err(EngineError::value(
        "must be YYYY-MM-DD or YYYY-MM-DDTHH:MM with no seconds or timezone",
    ))
}

pub fn due_is_timed(value: &str) -> bool {
    value.len() >= 16
        && value.as_bytes().get(10) == Some(&b'T')
        && &value[11..16] != END_OF_DAY_CLOCK
}

pub fn due_sort_key(due: Option<&str>, item_id: &str) -> (NaiveDate, i64, String) {
    if let Some(due) = due
        && let Ok((day, minute)) = parse_due(due)
    {
        return (day, minute, item_id.to_string());
    }
    (
        NaiveDate::from_ymd_opt(9999, 12, 31).expect("max date"),
        END_OF_DAY_MIN,
        item_id.to_string(),
    )
}

pub struct CategoryInfo {
    pub icon: Option<&'static str>,
    pub label: &'static str,
    pub hue: i64,
    pub color: &'static str,
    pub mark: &'static str,
    pub kind: &'static str,
}

pub static CATEGORIES: [(&str, CategoryInfo); 8] = [
    (
        "class",
        CategoryInfo {
            icon: Some("house"),
            label: "School",
            hue: 250,
            color: "#cfe8ff",
            mark: "#398ad6",
            kind: "locked",
        },
    ),
    (
        "assignments",
        CategoryInfo {
            icon: Some("book-open"),
            label: "Homework",
            hue: 25,
            color: "#ffdad6",
            mark: "#831a1d",
            kind: "flexible",
        },
    ),
    (
        "study",
        CategoryInfo {
            icon: Some("pencil"),
            label: "Study",
            hue: 320,
            color: "#f2dbf8",
            mark: "#ab68ba",
            kind: "flexible",
        },
    ),
    (
        "exercise",
        CategoryInfo {
            icon: Some("target"),
            label: "Sports",
            hue: 150,
            color: "#d0eed5",
            mark: "#399d57",
            kind: "locked",
        },
    ),
    (
        "extra",
        CategoryInfo {
            icon: Some("sparkles"),
            label: "Activity",
            hue: 200,
            color: "#c3eef0",
            mark: "#009ea7",
            kind: "locked",
        },
    ),
    (
        "meals",
        CategoryInfo {
            icon: Some("clock"),
            label: "Meals",
            hue: 70,
            color: "#f9e0c5",
            mark: "#bb7400",
            kind: "locked",
        },
    ),
    (
        "sleep",
        CategoryInfo {
            icon: Some("moon"),
            label: "Sleep",
            hue: 280,
            color: "#c4c8e8",
            mark: "#5656b0",
            kind: "locked",
        },
    ),
    (
        "free",
        CategoryInfo {
            icon: None,
            label: "Free",
            hue: 250,
            color: "#e0e5eb",
            mark: "#82878c",
            kind: "locked",
        },
    ),
];

pub fn deep_copy(value: &Value) -> Value {
    serde_json::from_str(&value.to_string()).unwrap_or(Value::Null)
}
