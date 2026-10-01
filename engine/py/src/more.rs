//! Bindings for the slices after time. Dicts cross as JSON text.

use ::flexweek_engine::desk::custom_look;
use ::flexweek_engine::desk::reuse;
use ::flexweek_engine::plan;
use ::flexweek_engine::snapshot;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyModule;
use serde_json::Value;

fn parse(text: &str) -> PyResult<Value> {
    serde_json::from_str(text).map_err(|error| PyValueError::new_err(error.to_string()))
}

fn dump(value: &Value) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "null".to_string())
}

fn maps(text: &str) -> PyResult<Vec<serde_json::Map<String, Value>>> {
    let value = parse(text)?;
    Ok(value
        .as_array()
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|item| item.as_object().cloned())
        .collect())
}

#[pyfunction]
fn sentence(code: &str) -> PyResult<String> {
    plan::sentence(code).map_err(crate::raise)
}

#[pyfunction]
fn slack_sentence(slack_min: i64, status: &str) -> String {
    plan::slack_sentence(slack_min, status)
}

#[pyfunction]
fn canonical(text: &str) -> PyResult<String> {
    Ok(snapshot::canonical(&parse(text)?))
}

#[pyfunction]
fn state_token(text: &str) -> PyResult<String> {
    Ok(snapshot::state_token(&parse(text)?))
}

#[pyfunction]
fn diff_snapshots(current: &str, stored: &str) -> PyResult<String> {
    Ok(dump(&snapshot::diff_snapshots(
        &parse(current)?,
        &parse(stored)?,
    )))
}

#[pyfunction]
fn diff_transfer(current: &str, incoming: &str) -> PyResult<String> {
    Ok(dump(&snapshot::diff_transfer(
        &parse(current)?,
        &parse(incoming)?,
    )))
}

#[pyfunction]
fn transfer_apply_bytes(text: &str) -> PyResult<usize> {
    Ok(snapshot::transfer_apply_bytes(&parse(text)?))
}

#[pyfunction]
fn transfer_fits(text: &str) -> PyResult<bool> {
    Ok(snapshot::transfer_fits(&parse(text)?))
}

#[pyfunction]
fn format_recovery_code(raw_hex: &str) -> String {
    snapshot::format_recovery_code(raw_hex)
}

#[pyfunction]
fn recovery_code_well_formed(code: &str) -> bool {
    snapshot::recovery_code_well_formed(code)
}

#[pyfunction]
fn hash_recovery_code(value: &str) -> String {
    snapshot::hash_recovery_code(value)
}

#[pyfunction]
fn normalize_recovery_code(value: &str) -> String {
    snapshot::normalize_recovery_code(value)
}

#[pyfunction]
fn free_name(saved: &str, name: &str) -> PyResult<String> {
    custom_look::free_name(&maps(saved)?, name).map_err(crate::raise)
}

#[pyfunction]
fn rename_look(saved: &str, old: &str, new_name: &str) -> PyResult<String> {
    let kept = custom_look::rename_look(&maps(saved)?, old, new_name).map_err(crate::raise)?;
    Ok(dump(&Value::Array(
        kept.into_iter().map(Value::Object).collect(),
    )))
}

#[pyfunction]
fn duplicate_look(saved: &str, name: &str) -> PyResult<(String, String)> {
    let (kept, copy) = custom_look::duplicate_look(&maps(saved)?, name).map_err(crate::raise)?;
    Ok((
        dump(&Value::Array(kept.into_iter().map(Value::Object).collect())),
        copy,
    ))
}

#[pyfunction]
fn delete_look(saved: &str, name: &str) -> PyResult<String> {
    let kept = custom_look::delete_look(&maps(saved)?, name).map_err(crate::raise)?;
    Ok(dump(&Value::Array(
        kept.into_iter().map(Value::Object).collect(),
    )))
}

#[pyfunction]
fn solve_request(
    blocks: &str,
    assignments: &str,
    week_start: &str,
    everything: bool,
    only: Option<Vec<String>>,
    not_before_day: Option<i64>,
    not_before_minute: Option<i64>,
) -> PyResult<(String, Vec<String>)> {
    let blocks = parse(blocks)?;
    let assignments = parse(assignments)?;
    let blocks = blocks.as_array().cloned().unwrap_or_default();
    let assignments = assignments.as_object().cloned().unwrap_or_default();
    let not_before = match (not_before_day, not_before_minute) {
        (Some(day), Some(minute)) => Some((day, minute)),
        _ => None,
    };
    let (payload, targets) = reuse::solve_request(
        &blocks,
        &assignments,
        week_start,
        everything,
        only.as_deref(),
        not_before,
    );
    Ok((dump(&Value::Array(payload)), targets))
}

#[pyfunction]
fn settle_placements(
    blocks: &str,
    assignments: &str,
    week_start: &str,
    keep: Vec<String>,
) -> PyResult<(String, String)> {
    let blocks = parse(blocks)?.as_array().cloned().unwrap_or_default();
    let assignments = parse(assignments)?.as_object().cloned().unwrap_or_default();
    let (out, lost) = reuse::settle_placements(&blocks, &assignments, week_start, &keep);
    Ok((dump(&Value::Array(out)), dump(&Value::Array(lost))))
}

#[pyfunction]
fn snap_minutes(value: i64, minimum: i64, maximum: i64) -> i64 {
    plan::snap_minutes(value, minimum, maximum)
}

#[pyfunction]
fn split_plan(
    duration_min: i64,
    work_min: i64,
    break_min: i64,
    long_break_min: i64,
    cadence: i64,
) -> PyResult<String> {
    crate::guard(|| {
        Ok(dump(
            &plan::split_plan(duration_min, work_min, break_min, long_break_min, cadence)
                .map_err(crate::raise)?,
        ))
    })
}

#[pyfunction]
fn preview_split(
    duration_min: Option<i64>,
    timer_work_min: i64,
    timer_break_min: i64,
    timer_long_break_min: i64,
    timer_long_break_every: i64,
) -> PyResult<String> {
    Ok(dump(
        &plan::preview_split(
            duration_min,
            timer_work_min,
            timer_break_min,
            timer_long_break_min,
            timer_long_break_every,
        )
        .map_err(crate::raise)?,
    ))
}

#[pyfunction]
fn timer_presets() -> String {
    dump(&Value::Array(plan::timer_presets().to_vec()))
}

#[pyfunction]
fn migrated_assignment_id(week_start: &str, source_id: &str) -> String {
    plan::migrated_assignment_id(week_start, source_id)
}

#[pyfunction]
fn due_from_latest(week_start: &str, latest: Option<&str>, days: Vec<i64>) -> PyResult<String> {
    plan::due_from_latest(week_start, latest, &days).map_err(crate::raise)
}

#[pyfunction]
fn completed_at_for_block(week_start: &str, block: &str) -> PyResult<String> {
    let block = parse(block)?;
    crate::guard(move || plan::completed_at_for_block(week_start, &block).map_err(crate::raise))
}

#[pyfunction]
fn due_placement_bound(week_start: &str, due: &str) -> PyResult<Option<(i64, i64)>> {
    crate::guard(|| plan::due_placement_bound(week_start, due).map_err(crate::raise))
}

#[pyfunction]
fn due_slack_point(week_start: &str, due: &str) -> PyResult<(i64, i64)> {
    crate::guard(|| plan::due_slack_point(week_start, due).map_err(crate::raise))
}

#[pyfunction]
fn unplanned_minutes(estimate_min: i64, focus_minutes: i64, planned: i64) -> i64 {
    plan::unplanned_minutes(estimate_min, focus_minutes, planned)
}

#[pyfunction]
fn prepare_solve(blocks: &str, week_start: &str, assignments: &str) -> PyResult<String> {
    let blocks = parse(blocks)?.as_array().cloned().unwrap_or_default();
    let assignments = parse(assignments)?.as_object().cloned().unwrap_or_default();
    let assignments: std::collections::BTreeMap<String, Value> = assignments.into_iter().collect();
    let (keep, deadlines, slack) =
        plan::prepare_solve(&blocks, week_start, &assignments).map_err(crate::raise)?;
    let mut deadline_map = serde_json::Map::new();
    for (key, value) in deadlines {
        deadline_map.insert(
            key,
            match value {
                Some((day, minute)) => serde_json::json!([day, minute]),
                None => Value::Null,
            },
        );
    }
    let mut slack_map = serde_json::Map::new();
    for (key, (day, minute)) in slack {
        slack_map.insert(key, serde_json::json!([day, minute]));
    }
    Ok(dump(&serde_json::json!({
        "keep": keep,
        "deadlines": deadline_map,
        "slack": slack_map,
    })))
}

#[pyfunction]
fn legacy_session(week_start: &str, block: &str) -> PyResult<String> {
    let (block, body) = plan::legacy_session(week_start, &parse(block)?).map_err(crate::raise)?;
    Ok(dump(&serde_json::json!([block, body])))
}

#[pyfunction]
fn rewrite_session(block: &str, assignment: &str) -> PyResult<String> {
    Ok(dump(&plan::rewrite_session(
        &parse(block)?,
        &parse(assignment)?,
    )))
}

#[pyfunction]
fn planned_minutes_by_id(weeks: &str, from_week: &str) -> PyResult<String> {
    let weeks: Vec<(String, Vec<Value>)> = parse(weeks)?
        .as_array()
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|item| {
            let pair = item.as_array()?;
            let start = pair.first()?.as_str()?.to_string();
            let blocks = pair.get(1)?.as_array()?.clone();
            Some((start, blocks))
        })
        .collect();
    let planned = plan::planned_minutes_by_id(&weeks, from_week);
    Ok(dump(&Value::Object(
        planned
            .into_iter()
            .map(|(key, value)| (key, Value::from(value)))
            .collect(),
    )))
}

#[pyfunction]
fn migrate_blocks(week_start: &str, blocks: &str) -> PyResult<String> {
    let blocks = parse(blocks)?.as_array().cloned().unwrap_or_default();
    let (blocks, assignments) = plan::migrate_blocks(week_start, &blocks).map_err(crate::raise)?;
    Ok(dump(&serde_json::json!([blocks, assignments])))
}

#[pyfunction]
fn build_day(
    date_str: &str,
    week_start: &str,
    blocks: &str,
    assignment_rows: &str,
    weeks: &str,
) -> PyResult<String> {
    let blocks = parse(blocks)?.as_array().cloned().unwrap_or_default();
    let rows: Vec<(Value, i64)> = parse(assignment_rows)?
        .as_array()
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|item| {
            let pair = item.as_array()?;
            Some((pair.first()?.clone(), pair.get(1)?.as_i64()?))
        })
        .collect();
    let weeks: Vec<(String, Vec<Value>)> = parse(weeks)?
        .as_array()
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|item| {
            let pair = item.as_array()?;
            Some((
                pair.first()?.as_str()?.to_string(),
                pair.get(1)?.as_array()?.clone(),
            ))
        })
        .collect();
    plan::build_day(date_str, week_start, &blocks, &rows, &weeks)
        .map(|value| dump(&value))
        .map_err(crate::raise)
}

#[pyfunction]
fn build_month(month: &str, assignment_rows: &str, weeks: &str) -> PyResult<String> {
    let rows: Vec<(Value, i64)> = parse(assignment_rows)?
        .as_array()
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|item| {
            let pair = item.as_array()?;
            Some((pair.first()?.clone(), pair.get(1)?.as_i64()?))
        })
        .collect();
    let weeks: Vec<(String, Vec<Value>)> = parse(weeks)?
        .as_array()
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|item| {
            let pair = item.as_array()?;
            Some((
                pair.first()?.as_str()?.to_string(),
                pair.get(1)?.as_array()?.clone(),
            ))
        })
        .collect();
    plan::build_month(month, &rows, &weeks)
        .map(|value| dump(&value))
        .map_err(crate::raise)
}

#[pyfunction]
fn is_work_session(block: &str) -> PyResult<bool> {
    Ok(plan::is_work_session(&parse(block)?))
}

pub fn add(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(sentence, module)?)?;
    module.add_function(wrap_pyfunction!(slack_sentence, module)?)?;
    module.add_function(wrap_pyfunction!(canonical, module)?)?;
    module.add_function(wrap_pyfunction!(state_token, module)?)?;
    module.add_function(wrap_pyfunction!(diff_snapshots, module)?)?;
    module.add_function(wrap_pyfunction!(diff_transfer, module)?)?;
    module.add_function(wrap_pyfunction!(transfer_apply_bytes, module)?)?;
    module.add_function(wrap_pyfunction!(transfer_fits, module)?)?;
    module.add_function(wrap_pyfunction!(format_recovery_code, module)?)?;
    module.add_function(wrap_pyfunction!(recovery_code_well_formed, module)?)?;
    module.add_function(wrap_pyfunction!(hash_recovery_code, module)?)?;
    module.add_function(wrap_pyfunction!(normalize_recovery_code, module)?)?;
    module.add_function(wrap_pyfunction!(free_name, module)?)?;
    module.add_function(wrap_pyfunction!(rename_look, module)?)?;
    module.add_function(wrap_pyfunction!(duplicate_look, module)?)?;
    module.add_function(wrap_pyfunction!(delete_look, module)?)?;
    module.add_function(wrap_pyfunction!(solve_request, module)?)?;
    module.add_function(wrap_pyfunction!(settle_placements, module)?)?;
    module.add_function(wrap_pyfunction!(snap_minutes, module)?)?;
    module.add_function(wrap_pyfunction!(split_plan, module)?)?;
    module.add_function(wrap_pyfunction!(preview_split, module)?)?;
    module.add_function(wrap_pyfunction!(timer_presets, module)?)?;
    module.add_function(wrap_pyfunction!(migrated_assignment_id, module)?)?;
    module.add_function(wrap_pyfunction!(due_from_latest, module)?)?;
    module.add_function(wrap_pyfunction!(completed_at_for_block, module)?)?;
    module.add_function(wrap_pyfunction!(due_placement_bound, module)?)?;
    module.add_function(wrap_pyfunction!(due_slack_point, module)?)?;
    module.add_function(wrap_pyfunction!(unplanned_minutes, module)?)?;
    module.add_function(wrap_pyfunction!(prepare_solve, module)?)?;
    module.add_function(wrap_pyfunction!(legacy_session, module)?)?;
    module.add_function(wrap_pyfunction!(rewrite_session, module)?)?;
    module.add_function(wrap_pyfunction!(planned_minutes_by_id, module)?)?;
    module.add_function(wrap_pyfunction!(migrate_blocks, module)?)?;
    module.add_function(wrap_pyfunction!(build_day, module)?)?;
    module.add_function(wrap_pyfunction!(build_month, module)?)?;
    module.add_function(wrap_pyfunction!(is_work_session, module)?)?;
    Ok(())
}
