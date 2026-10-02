//! Bindings for the slices after time. Dicts cross as JSON text.

use ::flexweek_engine::desk::custom_look;
use ::flexweek_engine::desk::planning;
use ::flexweek_engine::plan;
use ::flexweek_engine::snapshot;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::guard;
use pyo3::types::PyModule;
use serde_json::Value;

fn parse(text: &str) -> PyResult<Value> {
    serde_json::from_str(text).map_err(|error| PyValueError::new_err(error.to_string()))
}

fn dump(value: &Value) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "null".to_string())
}

#[pyfunction]
fn sentence(code: &str) -> PyResult<String> {
    guard(|| plan::sentence(code).map_err(crate::raise))
}

#[pyfunction]
fn slack_sentence(slack_min: i64, status: &str) -> PyResult<String> {
    guard(|| Ok(plan::slack_sentence(slack_min, status)))
}

#[pyfunction]
fn canonical(text: &str) -> PyResult<String> {
    guard(|| Ok(snapshot::canonical(&parse(text)?)))
}

#[pyfunction]
fn state_token(text: &str) -> PyResult<String> {
    guard(|| Ok(snapshot::state_token(&parse(text)?)))
}

#[pyfunction]
fn diff_snapshots(current: &str, stored: &str) -> PyResult<String> {
    guard(|| {
        Ok(dump(&snapshot::diff_snapshots(
            &parse(current)?,
            &parse(stored)?,
        )))
    })
}

#[pyfunction]
fn diff_transfer(current: &str, incoming: &str) -> PyResult<String> {
    guard(|| {
        Ok(dump(&snapshot::diff_transfer(
            &parse(current)?,
            &parse(incoming)?,
        )))
    })
}

#[pyfunction]
fn transfer_apply_bytes(text: &str) -> PyResult<usize> {
    guard(|| Ok(snapshot::transfer_apply_bytes(&parse(text)?)))
}

#[pyfunction]
fn transfer_fits(text: &str) -> PyResult<bool> {
    guard(|| Ok(snapshot::transfer_fits(&parse(text)?)))
}

#[pyfunction]
fn format_recovery_code(raw_hex: &str) -> PyResult<String> {
    guard(|| Ok(snapshot::format_recovery_code(raw_hex)))
}

#[pyfunction]
fn recovery_code_well_formed(code: &str) -> PyResult<bool> {
    guard(|| Ok(snapshot::recovery_code_well_formed(code)))
}

#[pyfunction]
fn hash_recovery_code(value: &str) -> PyResult<String> {
    guard(|| Ok(snapshot::hash_recovery_code(value)))
}

#[pyfunction]
fn normalize_recovery_code(value: &str) -> PyResult<String> {
    guard(|| Ok(snapshot::normalize_recovery_code(value)))
}

#[pyfunction]
fn free_name(saved: &str, name: &str) -> PyResult<String> {
    let saved = parse(saved)?;
    guard(|| custom_look::free_name(&saved, name).map_err(crate::raise))
}

#[pyfunction]
fn rename_look(saved: &str, old: &str, new_name: &str) -> PyResult<String> {
    let saved = parse(saved)?;
    guard(|| {
        let kept = custom_look::rename_look(&saved, old, new_name).map_err(crate::raise)?;
        Ok(dump(&Value::Array(kept)))
    })
}

#[pyfunction]
fn duplicate_look(saved: &str, name: &str) -> PyResult<(String, String)> {
    let saved = parse(saved)?;
    guard(|| {
        let (kept, copy) = custom_look::duplicate_look(&saved, name).map_err(crate::raise)?;
        Ok((dump(&Value::Array(kept)), copy))
    })
}

#[pyfunction]
fn delete_look(saved: &str, name: &str) -> PyResult<String> {
    let saved = parse(saved)?;
    guard(|| {
        let kept = custom_look::delete_look(&saved, name).map_err(crate::raise)?;
        Ok(dump(&Value::Array(kept)))
    })
}

#[pyfunction]
fn solve_request(
    blocks: &str,
    assignments: &str,
    week_start: &str,
    everything: bool,
    only: Option<&str>,
    not_before: Option<&str>,
    not_before_is_list: bool,
) -> PyResult<(String, String)> {
    let (blocks, assignments) = (parse(blocks)?, parse(assignments)?);
    let only = only.map(parse).transpose()?;
    let not_before = not_before.map(parse).transpose()?;
    guard(|| {
        let (payload, targets) = planning::solve_request(
            &blocks,
            &assignments,
            week_start,
            everything,
            only.as_ref(),
            not_before.as_ref(),
            not_before_is_list,
        )
        .map_err(crate::raise)?;
        Ok((dump(&Value::Array(payload)), dump(&Value::Array(targets))))
    })
}

#[pyfunction]
fn settle_placements(
    blocks: &str,
    assignments: &str,
    week_start: &str,
    keep: &str,
    keep_is_set: bool,
) -> PyResult<(String, String)> {
    let (blocks, assignments, keep) = (parse(blocks)?, parse(assignments)?, parse(keep)?);
    guard(|| {
        let (out, lost) =
            planning::settle_placements(&blocks, &assignments, week_start, &keep, keep_is_set)
                .map_err(crate::raise)?;
        Ok((dump(&out), dump(&Value::Array(lost))))
    })
}

#[pyfunction]
fn snap_minutes(value: i64, minimum: i64, maximum: i64) -> PyResult<i64> {
    guard(|| Ok(plan::snap_minutes(value, minimum, maximum)))
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
    guard(|| {
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
    })
}

#[pyfunction]
fn timer_presets() -> PyResult<String> {
    guard(|| Ok(dump(&Value::Array(plan::timer_presets().to_vec()))))
}

#[pyfunction]
fn migrated_assignment_id(week_start: &str, source_id: &str) -> PyResult<String> {
    guard(|| Ok(plan::migrated_assignment_id(week_start, source_id)))
}

#[pyfunction]
fn due_from_latest(week_start: &str, latest: Option<&str>, days: Vec<i64>) -> PyResult<String> {
    guard(|| plan::due_from_latest(week_start, latest, &days).map_err(crate::raise))
}

#[pyfunction]
fn completed_at_for_block(week_start: &str, block: &str) -> PyResult<String> {
    guard(|| {
        let block = parse(block)?;
        crate::guard(move || plan::completed_at_for_block(week_start, &block).map_err(crate::raise))
    })
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
fn unplanned_minutes(estimate_min: i64, focus_minutes: i64, planned: i64) -> PyResult<i64> {
    guard(|| {
        Ok(plan::unplanned_minutes(
            estimate_min,
            focus_minutes,
            planned,
        ))
    })
}

#[pyfunction]
fn prepare_solve(blocks: &str, week_start: &str, assignments: &str) -> PyResult<String> {
    guard(|| {
        let blocks = parse(blocks)?.as_array().cloned().unwrap_or_default();
        let assignments = parse(assignments)?.as_object().cloned().unwrap_or_default();
        let assignments: std::collections::BTreeMap<String, Value> =
            assignments.into_iter().collect();
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
    })
}

#[pyfunction]
fn legacy_session(week_start: &str, block: &str) -> PyResult<String> {
    guard(|| {
        let (block, body) =
            plan::legacy_session(week_start, &parse(block)?).map_err(crate::raise)?;
        Ok(dump(&serde_json::json!([block, body])))
    })
}

#[pyfunction]
fn rewrite_session(block: &str, assignment: &str) -> PyResult<String> {
    guard(|| {
        Ok(dump(&plan::rewrite_session(
            &parse(block)?,
            &parse(assignment)?,
        )))
    })
}

#[pyfunction]
fn planned_minutes_by_id(weeks: &str, from_week: &str) -> PyResult<String> {
    guard(|| {
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
    })
}

#[pyfunction]
fn migrate_blocks(week_start: &str, blocks: &str) -> PyResult<String> {
    guard(|| {
        let (blocks, assignments) =
            plan::migrate_blocks(week_start, &parse(blocks)?).map_err(crate::raise)?;
        Ok(dump(&serde_json::json!([blocks, assignments])))
    })
}

#[pyfunction]
fn build_day(
    date_str: &str,
    week_start: &str,
    blocks: &str,
    assignment_rows: &str,
    weeks: &str,
) -> PyResult<String> {
    guard(|| {
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
    })
}

#[pyfunction]
fn build_month(month: &str, assignment_rows: &str, weeks: &str) -> PyResult<String> {
    guard(|| {
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
    })
}

#[pyfunction]
fn is_work_session(block: &str) -> PyResult<bool> {
    guard(|| Ok(plan::is_work_session(&parse(block)?)))
}

pub fn add(module: &Bound<'_, PyModule>) -> PyResult<()> {
    crate::export!(
        module,
        sentence,
        slack_sentence,
        canonical,
        state_token,
        diff_snapshots,
        diff_transfer,
        transfer_apply_bytes,
        transfer_fits,
        format_recovery_code,
        recovery_code_well_formed,
        hash_recovery_code,
        normalize_recovery_code,
        free_name,
        rename_look,
        duplicate_look,
        delete_look,
        solve_request,
        settle_placements,
        snap_minutes,
        split_plan,
        preview_split,
        timer_presets,
        migrated_assignment_id,
        due_from_latest,
        completed_at_for_block,
        due_placement_bound,
        due_slack_point,
        unplanned_minutes,
        prepare_solve,
        legacy_session,
        rewrite_session,
        planned_minutes_by_id,
        migrate_blocks,
        build_day,
        build_month,
        is_work_session,
        snap_minutes_wide,
        generate_recovery_codes,
        recovery_code_matches,
    );
    Ok(())
}

fn is_overflow(py: Python<'_>, err: &PyErr) -> bool {
    err.is_instance(py, &py.get_type::<pyo3::exceptions::PyOverflowError>())
}

fn decimal_of_int(obj: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if !obj.is_instance_of::<pyo3::types::PyInt>() {
        return Ok(None);
    }
    match obj.extract::<i64>() {
        Ok(value) => Ok(Some(value.to_string())),
        Err(err) if is_overflow(obj.py(), &err) => Ok(Some(obj.str()?.extract()?)),
        Err(err) => Err(err),
    }
}

fn python_int(py: Python<'_>, decimal: &str) -> PyResult<Py<PyAny>> {
    Ok(py
        .import("builtins")?
        .getattr("int")?
        .call1((decimal,))?
        .unbind())
}

/// Integers f64 holds exactly keep `plan::snap_minutes`. Past 2^53, Python's formula.
#[pyfunction]
fn snap_minutes_wide(
    py: Python<'_>,
    value: &Bound<'_, PyAny>,
    minimum: &Bound<'_, PyAny>,
    maximum: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    guard(|| {
        let mut overflow = false;
        let mut fitted = [None, None, None];
        for (index, obj) in [value, minimum, maximum].into_iter().enumerate() {
            match obj.extract::<i64>() {
                Ok(number) => {
                    fitted[index] = Some(number);
                    // f64 cannot hold every integer past 2^53; `plan::snap_minutes` would drift.
                    if number.unsigned_abs() > (1u64 << 53) {
                        overflow = true;
                    }
                }
                Err(err) if is_overflow(py, &err) => overflow = true,
                Err(err) if !overflow => return Err(err),
                Err(_) => {}
            }
        }
        if !overflow {
            let snapped =
                plan::snap_minutes(fitted[0].unwrap(), fitted[1].unwrap(), fitted[2].unwrap());
            return Ok(snapped.into_pyobject(py)?.unbind().into_any());
        }
        let args = [value, minimum, maximum];
        let mut decimals = Vec::with_capacity(3);
        for obj in args {
            match decimal_of_int(obj)? {
                Some(text) => decimals.push(text),
                None => return snap_via_python(py, value, minimum, maximum),
            }
        }
        let snapped = ::flexweek_engine::wide_snap::snap_minutes_wide(
            &decimals[0],
            &decimals[1],
            &decimals[2],
        )
        .map_err(crate::raise)?;
        python_int(py, &snapped)
    })
}

fn snap_via_python(
    py: Python<'_>,
    value: &Bound<'_, PyAny>,
    minimum: &Bound<'_, PyAny>,
    maximum: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let decimal = decimal_of_int(value)?.ok_or_else(|| {
        pyo3::exceptions::PyTypeError::new_err(
            "unsupported operand type(s) for /: 'object' and 'int'",
        )
    })?;
    let number = python_int(py, &decimal)?;
    let quotient = number.bind(py).call_method1("__truediv__", (15,))?;
    let rounded = py
        .import("builtins")?
        .getattr("round")?
        .call1((quotient,))?;
    let product = rounded.call_method1("__mul__", (15,))?;
    let mut snapped = py.import("builtins")?.getattr("int")?.call1((product,))?;
    if snapped.lt(minimum)? {
        let rem = minimum.call_method1("__mod__", (15,))?;
        let fifteen = pyo3::types::PyInt::new(py, 15);
        let gap = fifteen.call_method1("__sub__", (rem,))?;
        let gap = gap.call_method1("__mod__", (15,))?;
        snapped = minimum.call_method1("__add__", (gap,))?;
    }
    if snapped.gt(maximum)? {
        let rem = maximum.call_method1("__mod__", (15,))?;
        snapped = maximum.call_method1("__sub__", (rem,))?;
    }
    let fifteen = pyo3::types::PyInt::new(py, 15);
    if snapped.lt(&fifteen)? {
        return Ok(fifteen.unbind().into_any());
    }
    Ok(snapped.unbind())
}

#[pyfunction]
fn generate_recovery_codes(
    count: &Bound<'_, PyAny>,
    draw: &Bound<'_, PyAny>,
) -> PyResult<Vec<String>> {
    guard(|| {
        let mut seen = std::collections::BTreeSet::new();
        let mut codes = Vec::new();
        loop {
            let more: bool = count.gt(codes.len())?;
            if !more {
                break;
            }
            let raw: Vec<u8> = draw.call0()?.extract()?;
            if let Some(code) = snapshot::accept_recovery_draw(&raw, &mut seen) {
                codes.push(code);
            }
        }
        Ok(codes)
    })
}

#[pyfunction]
fn recovery_code_matches(presented: &str, stored_hash: &str) -> PyResult<bool> {
    guard(|| snapshot::recovery_code_matches(presented, stored_hash).map_err(crate::raise))
}
