//! The standing week: the School and activities Setup made, which every week from Setup's week on
//! has without the student copying them. Each standing block keeps the id Setup gave it (`school`,
//! `sport`, `activity-N`), the same in every week and on every device, so a week that holds a block
//! with that id holds its own version of it for that week.

use std::collections::HashSet;

use serde_json::Value;

use crate::EngineResult;
use crate::desk::grid::is_setup_block;

fn id_of(block: &Value) -> Option<&str> {
    block.get("id").and_then(Value::as_str)
}

fn days_of(block: &Value) -> Vec<i64> {
    block
        .get("days")
        .and_then(Value::as_array)
        .map(|days| days.iter().filter_map(Value::as_i64).collect())
        .unwrap_or_default()
}

/// The block as it stands in every week: missed days belong to one week, never to the standing one.
pub fn standing_body(block: &Value) -> Value {
    let mut body = block.clone();
    if let Some(fields) = body.as_object_mut() {
        fields.shift_remove("missed_days");
    }
    body
}

/// A week as the student sees it: its own blocks, then each standing block it has no version of.
pub fn with_standing(stored: &[Value], standing: &[Value]) -> Vec<Value> {
    let held: HashSet<&str> = stored.iter().filter_map(id_of).collect();
    let mut week = stored.to_vec();
    week.extend(
        standing
            .iter()
            .filter(|block| id_of(block).is_some_and(|id| !held.contains(id)))
            .cloned(),
    );
    week
}

/// A saved week after the standing week changed to `standing`: each of its Setup blocks takes the new
/// days and times, keeping the missed days that are still among them (a block missed on every day,
/// which is how "just this week" removes one, stays missed on every day), and a Setup block that no
/// longer stands is removed. Everything else in the week is left as it was.
pub fn restand(stored: &[Value], standing: &[Value]) -> EngineResult<Vec<Value>> {
    let mut week = Vec::with_capacity(stored.len());
    for block in stored {
        if !is_setup_block(block)? {
            week.push(block.clone());
            continue;
        }
        let Some(new) = standing.iter().find(|item| id_of(item) == id_of(block)) else {
            continue;
        };
        let old_days = days_of(block);
        let missed: Vec<i64> = block
            .get("missed_days")
            .and_then(Value::as_array)
            .map(|days| days.iter().filter_map(Value::as_i64).collect())
            .unwrap_or_default();
        let new_days = days_of(new);
        let every_day_missed = !old_days.is_empty() && old_days.iter().all(|d| missed.contains(d));
        let kept: Vec<i64> = if every_day_missed {
            new_days
        } else {
            new_days
                .into_iter()
                .filter(|d| missed.contains(d))
                .collect()
        };
        let mut updated = standing_body(new);
        if !kept.is_empty()
            && let Some(fields) = updated.as_object_mut()
        {
            fields.insert("missed_days".into(), kept.into());
        }
        week.push(updated);
    }
    Ok(week)
}

/// An account from before the standing week: its Setup blocks are those of the newest saved week that
/// has any, standing from that week. None when no week has a Setup block.
pub fn derive_standing(
    weeks: &[(String, Vec<Value>)],
) -> EngineResult<Option<(String, Vec<Value>)>> {
    let mut newest: Option<(String, Vec<Value>)> = None;
    for (week_start, blocks) in weeks {
        if newest
            .as_ref()
            .is_some_and(|(start, _)| start >= week_start)
        {
            continue;
        }
        let mut setup = Vec::new();
        for block in blocks {
            if is_setup_block(block)? {
                setup.push(standing_body(block));
            }
        }
        if !setup.is_empty() {
            newest = Some((week_start.clone(), setup));
        }
    }
    Ok(newest)
}
