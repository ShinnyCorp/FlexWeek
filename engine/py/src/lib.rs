//! Python module `flexweek_engine`. The core stays free of Python.

use std::sync::{Mutex, OnceLock};

use ::flexweek_engine::time;
use ::flexweek_engine::{EngineError, ErrorKind};
use pyo3::exceptions::{
    PyIndexError, PyKeyError, PyLookupError, PyOverflowError, PyRuntimeError, PyValueError,
    PyZeroDivisionError,
};
use pyo3::prelude::*;
use pyo3::types::{PyDate, PyDict, PyModule};

mod db;
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

pub(crate) fn guard<T>(func: impl FnOnce() -> PyResult<T>) -> PyResult<T> {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(func)) {
        Ok(result) => result,
        Err(payload) => Err(PyRuntimeError::new_err(panic_message(&payload))),
    }
}

fn export_names() -> &'static Mutex<Vec<&'static str>> {
    static NAMES: OnceLock<Mutex<Vec<&'static str>>> = OnceLock::new();
    NAMES.get_or_init(|| Mutex::new(Vec::new()))
}

pub(crate) fn register_export(name: &'static str) {
    export_names().lock().expect("export registry").push(name);
}

macro_rules! export {
    ($module:expr, $($fn:ident),+ $(,)?) => {{
        $(
            crate::register_export(stringify!($fn));
            $module.add_function(pyo3::wrap_pyfunction!($fn, $module)?)?;
        )+
    }};
}
pub(crate) use export;

#[pyfunction]
fn guarded_names() -> PyResult<Vec<String>> {
    guard(|| {
        Ok(export_names()
            .lock()
            .expect("export registry")
            .iter()
            .copied()
            .map(str::to_string)
            .collect())
    })
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
fn casefold(text: &str) -> PyResult<String> {
    guard(|| Ok(::flexweek_engine::casefold::casefold(text)))
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
fn minutes_to_hhmm(minutes: i64) -> PyResult<String> {
    guard(|| Ok(time::minutes_to_hhmm(minutes)))
}

#[pyfunction]
fn start_fits_day(start_min: i64) -> PyResult<bool> {
    guard(|| Ok(time::start_fits_day(start_min)))
}

#[pyfunction]
fn span_fits_day(start_min: i64, duration_min: i64) -> PyResult<bool> {
    guard(|| Ok(time::span_fits_day(start_min, duration_min)))
}

#[pyfunction]
fn on_slot(minutes: i64) -> PyResult<bool> {
    guard(|| Ok(time::on_slot(minutes)))
}

#[pyfunction]
fn minutes_to_slot(minutes: i64) -> PyResult<i64> {
    guard(|| time::minutes_to_slot(minutes).map_err(raise))
}

#[pyfunction]
fn hhmm_to_slot(hhmm: &str) -> PyResult<i64> {
    guard(|| time::hhmm_to_slot(hhmm).map_err(raise))
}

#[pyfunction]
fn slot_to_hhmm(slot: i64) -> PyResult<String> {
    guard(|| time::slot_to_hhmm(slot).map_err(raise))
}

#[pyfunction]
fn duration_to_slots(duration_min: i64) -> PyResult<i64> {
    guard(|| time::duration_to_slots(duration_min).map_err(raise))
}

#[pyfunction]
fn overlaps(a_start: i64, a_end: i64, b_start: i64, b_end: i64) -> PyResult<bool> {
    guard(|| Ok(time::overlaps(a_start, a_end, b_start, b_end)))
}

#[pyfunction]
fn block_interval_on_day(block: &Bound<'_, PyAny>, day: i64) -> PyResult<Option<(i64, i64)>> {
    guard(|| {
        let days: Vec<i64> = block.getattr("days")?.extract()?;
        let start: Option<String> = block.getattr("start")?.extract()?;
        let duration_min: i64 = block.getattr("duration_min")?.extract()?;
        time::block_interval_on_day(&days, start.as_deref(), duration_min, day).map_err(raise)
    })
}

#[pyfunction]
fn parse_deadline(latest: Option<&str>, days: Vec<i64>) -> PyResult<Option<(i64, i64)>> {
    guard(|| time::parse_deadline(latest, &days).map_err(raise))
}

#[pyfunction]
fn occupancy_mask(start_slot: i64, n_slots: i64) -> PyResult<u128> {
    guard(|| time::occupancy_mask(start_slot, n_slots).map_err(raise))
}

#[pyfunction]
fn occupancy_between(start_min: i64, end_min: i64) -> PyResult<u128> {
    guard(|| time::occupancy_between(start_min, end_min).map_err(raise))
}

#[pyfunction]
fn monday_of(date_str: &str) -> PyResult<String> {
    guard(|| time::monday_of(date_str).map_err(raise))
}

#[pyfunction]
fn current_week_start(py: Python<'_>) -> PyResult<String> {
    guard(|| {
        let today: String = py
            .import("datetime")?
            .getattr("date")?
            .call_method0("today")?
            .call_method0("isoformat")?
            .extract()?;
        time::monday_of(&today).map_err(raise)
    })
}

#[pyfunction]
fn is_week_start(value: &str) -> PyResult<bool> {
    guard(|| Ok(time::is_week_start(value)))
}

#[pyfunction]
fn is_calendar_date(value: &str) -> PyResult<bool> {
    guard(|| Ok(time::is_calendar_date(value)))
}

#[pyfunction]
fn parse_month(py: Python<'_>, value: &str) -> PyResult<(Py<PyDate>, Py<PyDate>)> {
    guard(|| {
        let (start, end) = time::parse_month(value).map_err(raise)?;
        Ok((as_date(py, &start)?, as_date(py, &end)?))
    })
}

#[pyfunction]
fn is_month_label(value: &str) -> PyResult<bool> {
    guard(|| Ok(time::is_month_label(value)))
}

#[pyfunction]
fn month_grid(
    py: Python<'_>,
    start: &Bound<'_, PyAny>,
    end: &Bound<'_, PyAny>,
) -> PyResult<(Py<PyDate>, Py<PyDate>)> {
    guard(|| {
        let (grid_start, grid_end) =
            time::month_grid(&iso_of(start)?, &iso_of(end)?).map_err(raise)?;
        Ok((as_date(py, &grid_start)?, as_date(py, &grid_end)?))
    })
}

#[cfg(feature = "audit")]
fn int_one(text: &str) -> (String, String) {
    match time::py_int(text) {
        Ok(value) => ("ok".to_string(), value.to_string()),
        Err(err) => {
            let kind = match err.kind {
                ErrorKind::Overflow => "OverflowError",
                ErrorKind::Value => "ValueError",
                ErrorKind::Key => "KeyError",
                ErrorKind::Index => "IndexError",
                ErrorKind::Lookup => "LookupError",
                ErrorKind::ZeroDivision => "ZeroDivisionError",
            };
            (kind.to_string(), err.message)
        }
    }
}

#[cfg(feature = "audit")]
#[pyfunction]
fn panic_probe() -> PyResult<()> {
    guard(|| -> PyResult<()> { panic!("probe") })
}

#[cfg(feature = "audit")]
#[pyfunction]
fn int_text(text: &str) -> PyResult<(String, String)> {
    guard(|| Ok(int_one(text)))
}

#[cfg(feature = "audit")]
#[pyfunction]
fn int_chars(text: &str) -> PyResult<Vec<(String, String)>> {
    guard(|| Ok(text.chars().map(|ch| int_one(&ch.to_string())).collect()))
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
    crate::export!(
        m,
        casefold,
        hhmm_to_minutes,
        clock_to_minutes,
        minutes_to_hhmm,
        start_fits_day,
        span_fits_day,
        on_slot,
        minutes_to_slot,
        hhmm_to_slot,
        slot_to_hhmm,
        duration_to_slots,
        overlaps,
        block_interval_on_day,
        parse_deadline,
        occupancy_mask,
        occupancy_between,
        monday_of,
        current_week_start,
        is_week_start,
        is_calendar_date,
        parse_month,
        is_month_label,
        month_grid,
        guarded_names,
    );
    #[cfg(feature = "audit")]
    crate::export!(m, panic_probe, int_text, int_chars);
    more::add(m)?;
    rest::add(m)?;
    db::add(m)?;
    Ok(())
}
