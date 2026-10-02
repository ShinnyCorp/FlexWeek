//! Availability, solver, and store-hash bindings. Dicts cross as JSON text.

use std::path::Path;

use ::flexweek_engine::plan;
use ::flexweek_engine::snapshot;
use ::flexweek_engine::solver::{self, DeadlineOverrides, StudyWindow, TimeBlock, WorkWindow};
use flexweek_store as store;
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
    guard(|| {
        plan::add_occupancy(&mut occ, day, start_min, end_min).map_err(crate::raise)?;
        Ok(occ)
    })
}

#[pyfunction]
fn occupancy_from_windows(protected: &str, day_cutoff: Option<&str>) -> PyResult<Vec<u128>> {
    guard(|| {
        let protected = parse(protected)?.as_array().cloned().unwrap_or_default();
        plan::occupancy_from_windows(&protected, day_cutoff).map_err(crate::raise)
    })
}

#[pyfunction]
fn lateness_occupancy(day: i64, from_start: &str, minutes: i64) -> PyResult<Vec<u128>> {
    guard(|| plan::lateness_occupancy(day, from_start, minutes).map_err(crate::raise))
}

#[pyfunction]
fn study_rank(
    windows: &str,
    course: Option<&str>,
    day: i64,
    start_min: i64,
    duration_min: i64,
) -> PyResult<i64> {
    guard(|| {
        let windows = parse(windows)?.as_array().cloned().unwrap_or_default();
        Ok(plan::study_rank(
            &windows,
            course,
            day,
            start_min,
            duration_min,
        ))
    })
}

#[pyfunction]
fn resolve_work_windows(windows: Option<&str>) -> PyResult<(String, bool)> {
    guard(|| {
        let parsed = windows.map(parse).transpose()?;
        let list = parsed.as_ref().and_then(Value::as_array);
        let (resolved, defaulted) = plan::resolve_work_windows(list.map(Vec::as_slice));
        Ok((dump(&Value::Array(resolved)), defaulted))
    })
}

#[pyfunction]
fn session_inside_work_windows(
    windows: &str,
    course: Option<&str>,
    day: i64,
    start_min: i64,
    duration_min: i64,
) -> PyResult<bool> {
    guard(|| {
        let windows = parse(windows)?.as_array().cloned().unwrap_or_default();
        plan::session_inside_work_windows(&windows, course, day, start_min, duration_min)
            .map_err(crate::raise)
    })
}

#[pyfunction]
fn merge_occupancy(base: Vec<u128>, extra: Vec<u128>) -> PyResult<Vec<u128>> {
    guard(|| plan::merge_occupancy(&base, &extra).map_err(crate::raise))
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
    guard(|| {
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
    })
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
    guard(|| {
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
    })
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
    guard(|| {
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
    })
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
    guard(|| {
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
    })
}

#[pyfunction]
fn digest(value: &str) -> PyResult<String> {
    guard(|| Ok(store::digest(value)))
}

#[pyfunction]
fn password_hash(py: Python<'_>, password: &str, salt: &str) -> PyResult<String> {
    let password = password.to_string();
    let salt = salt.to_string();
    guard(|| {
        py.detach(|| store::password_hash(&password, &salt))
            .map_err(|error| store_py(py, error))
    })
}

#[pyfunction]
fn password_matches(py: Python<'_>, password: &str, encoded: &str) -> PyResult<bool> {
    let password = password.to_string();
    let encoded = encoded.to_string();
    guard(|| {
        py.detach(|| store::password_matches(&password, &encoded))
            .map_err(|error| store_py(py, error))
    })
}

#[pyfunction]
fn transfer_apply_envelope(snapshot: &str) -> PyResult<String> {
    guard(|| Ok(dump(&snapshot::transfer_apply_envelope(&parse(snapshot)?))))
}

#[pyfunction]
fn store_initialize(py: Python<'_>, path: &str, current_week_start: &str) -> PyResult<()> {
    let path = path.to_string();
    let current_week_start = current_week_start.to_string();
    guard(|| {
        py.detach(|| store::initialize(Path::new(&path), &current_week_start))
            .map_err(|error| store_py(py, error))
    })
}

#[pyfunction]
fn store_throttle(
    py: Python<'_>,
    path: &str,
    address: &str,
    username: &str,
    now_unix: i64,
) -> PyResult<bool> {
    let path = path.to_string();
    let address = address.to_string();
    let username = username.to_string();
    guard(|| {
        py.detach(|| store::throttle(Path::new(&path), &address, &username, now_unix))
            .map_err(|error| store_py(py, error))
    })
}

pub(crate) fn store_py(py: Python<'_>, error: flexweek_store::StoreError) -> PyErr {
    match error {
        flexweek_store::StoreError::Sqlite(sqlite) => crate::db::sqlite_py(py, &sqlite),
        flexweek_store::StoreError::Engine(engine) => crate::raise(engine),
        flexweek_store::StoreError::Json { text, error } => {
            json_error(py, &text).unwrap_or_else(|| value_error(error.to_string()))
        }
        other => value_error(other.to_string()),
    }
}

/// The error Python's `json.loads` raises on `text`, type and message both. None when Python
/// reads text the engine's parser does not, such as `NaN`.
fn json_error(py: Python<'_>, text: &str) -> Option<PyErr> {
    let loads = py.import("json").and_then(|json| json.getattr("loads"));
    match loads {
        Ok(loads) => loads.call1((text,)).err(),
        Err(error) => Some(error),
    }
}

pub fn add(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("MAX_BODY", snapshot::MAX_BODY)?;
    crate::export!(
        module,
        add_occupancy,
        occupancy_from_windows,
        lateness_occupancy,
        study_rank,
        resolve_work_windows,
        session_inside_work_windows,
        merge_occupancy,
        spread_sessions,
        solve,
        reschedule_after_miss,
        reschedule_running_late,
        digest,
        password_hash,
        password_matches,
        transfer_apply_envelope,
        store_initialize,
        store_throttle,
    );
    Ok(())
}
