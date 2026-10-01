//! Python module `flexweek_engine`. The core stays free of Python.

use ::flexweek_engine::time;
use ::flexweek_engine::{EngineError, ErrorKind};
use pyo3::exceptions::{
    PyIndexError, PyKeyError, PyLookupError, PyOverflowError, PyRuntimeError, PyValueError,
    PyZeroDivisionError,
};
use pyo3::prelude::*;
use pyo3::types::{PyDate, PyDict, PyModule};

mod more;
mod rest;

pub(crate) fn raise(err: EngineError) -> PyErr {
    match err.kind {
        ErrorKind::Value => PyValueError::new_err(err.message),
        ErrorKind::Lookup => PyLookupError::new_err(err.message),
        ErrorKind::Key => PyKeyError::new_err(err.message),
        ErrorKind::Index => PyIndexError::new_err(err.message),
        ErrorKind::Overflow => PyOverflowError::new_err(err.message),
        ErrorKind::ZeroDivision => PyZeroDivisionError::new_err(err.message),
    }
}

pub(crate) fn guard<T>(func: impl FnOnce() -> PyResult<T> + std::panic::UnwindSafe) -> PyResult<T> {
    match std::panic::catch_unwind(func) {
        Ok(result) => result,
        Err(payload) => Err(PyRuntimeError::new_err(panic_message(&payload))),
    }
}

fn panic_message(payload: &Box<dyn std::any::Any + Send>) -> String {
    if let Some(message) = payload.downcast_ref::<&str>() {
        return (*message).to_string();
    }
    if let Some(message) = payload.downcast_ref::<String>() {
        return message.clone();
    }
    "rust panic".to_string()
}

fn as_date(py: Python<'_>, iso: &str) -> PyResult<Py<PyDate>> {
    let mut parts = iso.split('-');
    let year: i32 = parts.next().unwrap_or("0").parse().unwrap_or(0);
    let month: u8 = parts.next().unwrap_or("0").parse().unwrap_or(0);
    let day: u8 = parts.next().unwrap_or("0").parse().unwrap_or(0);
    Ok(PyDate::new(py, year, month, day)?.unbind())
}

fn iso_of(value: &Bound<'_, PyAny>) -> PyResult<String> {
    if let Ok(text) = value.extract::<String>() {
        return Ok(text);
    }
    value.call_method0("isoformat")?.extract()
}

#[pyfunction]
fn casefold(text: &str) -> String {
    ::flexweek_engine::casefold::casefold(text)
}

#[pyfunction]
fn hhmm_to_minutes(hhmm: &str) -> PyResult<i64> {
    guard(|| time::hhmm_to_minutes(hhmm).map_err(raise))
}

#[pyfunction]
fn clock_to_minutes(hhmm: &str) -> PyResult<i64> {
    guard(|| time::clock_to_minutes(hhmm).map_err(raise))
}

#[pyfunction]
fn minutes_to_hhmm(minutes: i64) -> String {
    time::minutes_to_hhmm(minutes)
}

#[pyfunction]
fn start_fits_day(start_min: i64) -> bool {
    time::start_fits_day(start_min)
}

#[pyfunction]
fn span_fits_day(start_min: i64, duration_min: i64) -> bool {
    time::span_fits_day(start_min, duration_min)
}

#[pyfunction]
fn on_slot(minutes: i64) -> bool {
    time::on_slot(minutes)
}

#[pyfunction]
fn minutes_to_slot(minutes: i64) -> PyResult<i64> {
    time::minutes_to_slot(minutes).map_err(raise)
}

#[pyfunction]
fn hhmm_to_slot(hhmm: &str) -> PyResult<i64> {
    time::hhmm_to_slot(hhmm).map_err(raise)
}

#[pyfunction]
fn slot_to_hhmm(slot: i64) -> PyResult<String> {
    time::slot_to_hhmm(slot).map_err(raise)
}

#[pyfunction]
fn duration_to_slots(duration_min: i64) -> PyResult<i64> {
    time::duration_to_slots(duration_min).map_err(raise)
}

#[pyfunction]
fn overlaps(a_start: i64, a_end: i64, b_start: i64, b_end: i64) -> bool {
    time::overlaps(a_start, a_end, b_start, b_end)
}

#[pyfunction]
fn block_interval_on_day(block: &Bound<'_, PyAny>, day: i64) -> PyResult<Option<(i64, i64)>> {
    let days: Vec<i64> = block.getattr("days")?.extract()?;
    let start: Option<String> = block.getattr("start")?.extract()?;
    let duration_min: i64 = block.getattr("duration_min")?.extract()?;
    time::block_interval_on_day(&days, start.as_deref(), duration_min, day).map_err(raise)
}

#[pyfunction]
fn parse_deadline(latest: Option<&str>, days: Vec<i64>) -> PyResult<Option<(i64, i64)>> {
    time::parse_deadline(latest, &days).map_err(raise)
}

#[pyfunction]
fn occupancy_mask(start_slot: i64, n_slots: i64) -> PyResult<u128> {
    time::occupancy_mask(start_slot, n_slots).map_err(raise)
}

#[pyfunction]
fn occupancy_between(start_min: i64, end_min: i64) -> PyResult<u128> {
    time::occupancy_between(start_min, end_min).map_err(raise)
}

#[pyfunction]
fn monday_of(date_str: &str) -> PyResult<String> {
    time::monday_of(date_str).map_err(raise)
}

#[pyfunction]
fn current_week_start(py: Python<'_>) -> PyResult<String> {
    let today: String = py
        .import("datetime")?
        .getattr("date")?
        .call_method0("today")?
        .call_method0("isoformat")?
        .extract()?;
    time::monday_of(&today).map_err(raise)
}

#[pyfunction]
fn is_week_start(value: &str) -> bool {
    time::is_week_start(value)
}

#[pyfunction]
fn is_calendar_date(value: &str) -> bool {
    time::is_calendar_date(value)
}

#[pyfunction]
fn parse_month(py: Python<'_>, value: &str) -> PyResult<(Py<PyDate>, Py<PyDate>)> {
    let (start, end) = time::parse_month(value).map_err(raise)?;
    Ok((as_date(py, &start)?, as_date(py, &end)?))
}

#[pyfunction]
fn is_month_label(value: &str) -> bool {
    time::is_month_label(value)
}

#[pyfunction]
fn month_grid(
    py: Python<'_>,
    start: &Bound<'_, PyAny>,
    end: &Bound<'_, PyAny>,
) -> PyResult<(Py<PyDate>, Py<PyDate>)> {
    let (grid_start, grid_end) = time::month_grid(&iso_of(start)?, &iso_of(end)?).map_err(raise)?;
    Ok((as_date(py, &grid_start)?, as_date(py, &grid_end)?))
}

#[pymodule]
fn flexweek_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("SLOT_MIN", time::SLOT_MIN)?;
    m.add("DAY_START_MIN", time::DAY_START_MIN)?;
    m.add("DAY_END_MIN", time::DAY_END_MIN)?;
    m.add("SLOTS_PER_DAY", time::SLOTS_PER_DAY)?;
    let py = m.py();
    let names = PyDict::new(py);
    for (name, index) in time::day_name_to_index() {
        names.set_item(name, index)?;
    }
    m.add("DAY_NAME_TO_INDEX", names)?;
    m.add_function(wrap_pyfunction!(casefold, m)?)?;
    m.add_function(wrap_pyfunction!(hhmm_to_minutes, m)?)?;
    m.add_function(wrap_pyfunction!(clock_to_minutes, m)?)?;
    m.add_function(wrap_pyfunction!(minutes_to_hhmm, m)?)?;
    m.add_function(wrap_pyfunction!(start_fits_day, m)?)?;
    m.add_function(wrap_pyfunction!(span_fits_day, m)?)?;
    m.add_function(wrap_pyfunction!(on_slot, m)?)?;
    m.add_function(wrap_pyfunction!(minutes_to_slot, m)?)?;
    m.add_function(wrap_pyfunction!(hhmm_to_slot, m)?)?;
    m.add_function(wrap_pyfunction!(slot_to_hhmm, m)?)?;
    m.add_function(wrap_pyfunction!(duration_to_slots, m)?)?;
    m.add_function(wrap_pyfunction!(overlaps, m)?)?;
    m.add_function(wrap_pyfunction!(block_interval_on_day, m)?)?;
    m.add_function(wrap_pyfunction!(parse_deadline, m)?)?;
    m.add_function(wrap_pyfunction!(occupancy_mask, m)?)?;
    m.add_function(wrap_pyfunction!(occupancy_between, m)?)?;
    m.add_function(wrap_pyfunction!(monday_of, m)?)?;
    m.add_function(wrap_pyfunction!(current_week_start, m)?)?;
    m.add_function(wrap_pyfunction!(is_week_start, m)?)?;
    m.add_function(wrap_pyfunction!(is_calendar_date, m)?)?;
    m.add_function(wrap_pyfunction!(parse_month, m)?)?;
    m.add_function(wrap_pyfunction!(is_month_label, m)?)?;
    m.add_function(wrap_pyfunction!(month_grid, m)?)?;
    more::add(m)?;
    rest::add(m)?;
    Ok(())
}
