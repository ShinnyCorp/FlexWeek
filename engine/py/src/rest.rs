//! Availability, solver, and store-hash bindings. Dicts cross as JSON text.

use std::path::Path;

use ::flexweek_engine::plan;
use ::flexweek_engine::snapshot;
use ::flexweek_engine::solver::{self, DeadlineOverrides, StudyWindow, TimeBlock, WorkWindow};
use flexweek_store as store;
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

fn value_error(message: String) -> PyErr {
    PyValueError::new_err(message)
}

fn blocks_of(text: &str) -> PyResult<Vec<TimeBlock>> {
    parse(text)?
        .as_array()
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(|item| solver::block_from_value(item).map_err(|error| value_error(error.message)))
        .collect()
}

fn work_windows_of(text: Option<&str>) -> PyResult<Option<Vec<WorkWindow>>> {
    let Some(text) = text else {
        return Ok(None);
    };
    Ok(Some(
        parse(text)?
            .as_array()
            .cloned()
            .unwrap_or_default()
            .iter()
            .map(solver::work_window_from_value)
            .collect(),
    ))
}

fn study_windows_of(text: Option<&str>) -> PyResult<Option<Vec<StudyWindow>>> {
    let Some(text) = text else {
        return Ok(None);
    };
    Ok(Some(
        parse(text)?
            .as_array()
            .cloned()
            .unwrap_or_default()
            .iter()
            .map(solver::study_window_from_value)
            .collect(),
    ))
}

fn overrides_of(deadlines: Option<&str>, slack: Option<&str>) -> PyResult<DeadlineOverrides> {
    let deadlines = deadlines.map(parse).transpose()?;
    let slack = slack.map(parse).transpose()?;
    Ok(solver::overrides_from(deadlines.as_ref(), slack.as_ref()))
}

fn search<T>(
    py: Python<'_>,
    clock: &Py<PyAny>,
    body: impl FnOnce(&dyn Fn() -> f64) -> Result<T, String>,
) -> PyResult<T> {
    // The search keeps the GIL. Reading the clock on every check used to drop it and take it
    // again, so one busy Python thread made the solve wait on each reading.
    let failure: std::cell::RefCell<Option<PyErr>> = std::cell::RefCell::new(None);
    let result = body(&|| {
        if failure.borrow().is_some() {
            return f64::MAX;
        }
        match clock.bind(py).call0().and_then(|value| value.extract()) {
            Ok(elapsed) => elapsed,
            Err(err) => {
                *failure.borrow_mut() = Some(err);
                f64::MAX
            }
        }
    });
    if let Some(err) = failure.into_inner() {
        return Err(err);
    }
    result.map_err(value_error)
}

#[pyfunction]
fn add_occupancy(
    mut occ: Vec<u128>,
    day: i64,
    start_min: i64,
    end_min: i64,
) -> PyResult<Vec<u128>> {
    plan::add_occupancy(&mut occ, day, start_min, end_min).map_err(crate::raise)?;
    Ok(occ)
}

#[pyfunction]
fn occupancy_from_windows(protected: &str, day_cutoff: Option<&str>) -> PyResult<Vec<u128>> {
    let protected = parse(protected)?.as_array().cloned().unwrap_or_default();
    plan::occupancy_from_windows(&protected, day_cutoff).map_err(crate::raise)
}

#[pyfunction]
fn lateness_occupancy(day: i64, from_start: &str, minutes: i64) -> PyResult<Vec<u128>> {
    plan::lateness_occupancy(day, from_start, minutes).map_err(crate::raise)
}

#[pyfunction]
fn study_rank(
    windows: &str,
    course: Option<&str>,
    day: i64,
    start_min: i64,
    duration_min: i64,
) -> PyResult<i64> {
    let windows = parse(windows)?.as_array().cloned().unwrap_or_default();
    Ok(plan::study_rank(
        &windows,
        course,
        day,
        start_min,
        duration_min,
    ))
}

#[pyfunction]
fn resolve_work_windows(windows: Option<&str>) -> PyResult<(String, bool)> {
    let parsed = windows.map(parse).transpose()?;
    let list = parsed.as_ref().and_then(Value::as_array);
    let (resolved, defaulted) = plan::resolve_work_windows(list.map(Vec::as_slice));
    Ok((dump(&Value::Array(resolved)), defaulted))
}

#[pyfunction]
fn session_inside_work_windows(
    windows: &str,
    course: Option<&str>,
    day: i64,
    start_min: i64,
    duration_min: i64,
) -> PyResult<bool> {
    let windows = parse(windows)?.as_array().cloned().unwrap_or_default();
    plan::session_inside_work_windows(&windows, course, day, start_min, duration_min)
        .map_err(crate::raise)
}

#[pyfunction]
fn merge_occupancy(base: Vec<u128>, extra: Vec<u128>) -> PyResult<Vec<u128>> {
    plan::merge_occupancy(&base, &extra).map_err(crate::raise)
}

#[pyfunction]
fn spread_sessions(
    estimate_min: i64,
    focus_minutes: i64,
    planned_min: i64,
    due: &str,
    session_min: i64,
    from_date: &str,
) -> PyResult<(String, i64)> {
    let (sessions, remaining) = plan::spread_sessions(
        estimate_min,
        focus_minutes,
        planned_min,
        due,
        session_min,
        from_date,
    )
    .map_err(|error| value_error(error.message))?;
    Ok((dump(&Value::Array(sessions)), remaining))
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn solve(
    py: Python<'_>,
    blocks: &str,
    deadlines: Option<&str>,
    slack_deadlines: Option<&str>,
    extra_occ: Option<Vec<u128>>,
    study_windows: Option<&str>,
    work_windows: Option<&str>,
    clock: Py<PyAny>,
) -> PyResult<String> {
    let blocks = blocks_of(blocks)?;
    let study = study_windows_of(study_windows)?;
    let work = work_windows_of(work_windows)?;
    let overrides = overrides_of(deadlines, slack_deadlines)?;
    let trace = search(py, &clock, |elapsed| {
        solver::solve(
            &blocks,
            extra_occ.as_deref(),
            study.as_deref(),
            work.as_deref(),
            Some(&overrides),
            solver::SOLVE_BUDGET_MS,
            elapsed,
        )
        .map_err(|error| error.message)
    })?;
    Ok(dump(&solver::trace_to_value(&trace)))
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn reschedule_after_miss(
    py: Python<'_>,
    blocks: &str,
    missed_block_id: &str,
    missed_day: i64,
    previous_placed: &str,
    deadlines: Option<&str>,
    slack_deadlines: Option<&str>,
    extra_occ: Option<Vec<u128>>,
    study_windows: Option<&str>,
    work_windows: Option<&str>,
    clock: Py<PyAny>,
) -> PyResult<String> {
    let blocks = blocks_of(blocks)?;
    let previous = blocks_of(previous_placed)?;
    let study = study_windows_of(study_windows)?;
    let work = work_windows_of(work_windows)?;
    let overrides = overrides_of(deadlines, slack_deadlines)?;
    let missed = missed_block_id.to_string();
    let trace = search(py, &clock, |elapsed| {
        solver::reschedule_after_miss(
            &blocks,
            &missed,
            missed_day,
            &previous,
            extra_occ.as_deref(),
            study.as_deref(),
            work.as_deref(),
            Some(&overrides),
            solver::SOLVE_BUDGET_MS,
            elapsed,
        )
        .map_err(|error| error.message)
    })?;
    Ok(dump(&solver::trace_to_value(&trace)))
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn reschedule_running_late(
    py: Python<'_>,
    blocks: &str,
    day: i64,
    minutes: i64,
    from_start: &str,
    previous_placed: &str,
    deadlines: Option<&str>,
    slack_deadlines: Option<&str>,
    extra_occ: Option<Vec<u128>>,
    study_windows: Option<&str>,
    work_windows: Option<&str>,
    clock: Py<PyAny>,
) -> PyResult<String> {
    let blocks = blocks_of(blocks)?;
    let previous = blocks_of(previous_placed)?;
    let study = study_windows_of(study_windows)?;
    let work = work_windows_of(work_windows)?;
    let overrides = overrides_of(deadlines, slack_deadlines)?;
    let from_start = from_start.to_string();
    let trace = search(py, &clock, |elapsed| {
        solver::reschedule_running_late(
            &blocks,
            day,
            minutes,
            &from_start,
            &previous,
            extra_occ.as_deref(),
            study.as_deref(),
            work.as_deref(),
            Some(&overrides),
            solver::SOLVE_BUDGET_MS,
            elapsed,
        )
        .map_err(|error| error.message)
    })?;
    Ok(dump(&solver::trace_to_value(&trace)))
}

#[pyfunction]
fn digest(value: &str) -> String {
    store::digest(value)
}

#[pyfunction]
fn password_hash(password: &str, salt: &str) -> PyResult<String> {
    store::password_hash(password, salt).map_err(|error| value_error(error.to_string()))
}

#[pyfunction]
fn password_matches(password: &str, encoded: &str) -> PyResult<bool> {
    store::password_matches(password, encoded).map_err(|error| value_error(error.to_string()))
}

#[pyfunction]
fn make_token(raw: &[u8]) -> PyResult<String> {
    let bytes: [u8; 32] = raw
        .try_into()
        .map_err(|_| value_error("a sign-in token is 32 bytes".into()))?;
    Ok(store::make_token(&bytes))
}

#[pyfunction]
fn transfer_apply_envelope(snapshot: &str) -> PyResult<String> {
    Ok(dump(&snapshot::transfer_apply_envelope(&parse(snapshot)?)))
}

#[pyfunction]
fn store_initialize(path: &str, current_week_start: &str) -> PyResult<()> {
    store::initialize(Path::new(path), current_week_start)
        .map_err(|error| value_error(error.to_string()))
}

#[pyfunction]
fn store_throttle(path: &str, address: &str, username: &str, now_unix: i64) -> PyResult<bool> {
    store::throttle(Path::new(path), address, username, now_unix)
        .map_err(|error| value_error(error.to_string()))
}

pub fn add(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("MAX_BODY", snapshot::MAX_BODY)?;
    module.add_function(wrap_pyfunction!(add_occupancy, module)?)?;
    module.add_function(wrap_pyfunction!(occupancy_from_windows, module)?)?;
    module.add_function(wrap_pyfunction!(lateness_occupancy, module)?)?;
    module.add_function(wrap_pyfunction!(study_rank, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_work_windows, module)?)?;
    module.add_function(wrap_pyfunction!(session_inside_work_windows, module)?)?;
    module.add_function(wrap_pyfunction!(merge_occupancy, module)?)?;
    module.add_function(wrap_pyfunction!(spread_sessions, module)?)?;
    module.add_function(wrap_pyfunction!(solve, module)?)?;
    module.add_function(wrap_pyfunction!(reschedule_after_miss, module)?)?;
    module.add_function(wrap_pyfunction!(reschedule_running_late, module)?)?;
    module.add_function(wrap_pyfunction!(digest, module)?)?;
    module.add_function(wrap_pyfunction!(password_hash, module)?)?;
    module.add_function(wrap_pyfunction!(password_matches, module)?)?;
    module.add_function(wrap_pyfunction!(make_token, module)?)?;
    module.add_function(wrap_pyfunction!(transfer_apply_envelope, module)?)?;
    module.add_function(wrap_pyfunction!(store_initialize, module)?)?;
    module.add_function(wrap_pyfunction!(store_throttle, module)?)?;
    Ok(())
}
