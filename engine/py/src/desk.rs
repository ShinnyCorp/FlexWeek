//! Desktop logic bindings. Dicts cross as JSON text.

use std::collections::HashSet;

use ::flexweek_engine::desk::tokens::TextScale;
use ::flexweek_engine::desk::{history, pomodoro, remind, tokens, update, weekmodel};
use std::cell::RefCell;

use ::flexweek_engine::{EngineError, EngineResult};
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyAnyMethods, PyFloat, PyInt, PySet, PySetMethods};
use serde_json::{Map, Value};

use crate::{guard, raise};

pub(crate) fn parse(text: &str) -> PyResult<Value> {
    serde_json::from_str(text).map_err(|error| PyValueError::new_err(error.to_string()))
}

pub(crate) fn dump(value: &Value) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "null".to_string())
}

pub(crate) fn objects(text: &str) -> PyResult<Vec<Value>> {
    Ok(parse(text)?.as_array().cloned().unwrap_or_default())
}

pub(crate) fn maps_of(text: &str) -> PyResult<Vec<Map<String, Value>>> {
    Ok(objects(text)?
        .into_iter()
        .filter_map(|item| match item {
            Value::Object(map) => Some(map),
            _ => None,
        })
        .collect())
}

pub(crate) fn object_map(text: &str) -> PyResult<Map<String, Value>> {
    Ok(parse(text)?.as_object().cloned().unwrap_or_default())
}

fn scale_factor(value: &Bound<'_, PyAny>) -> PyResult<f64> {
    if value.is_instance_of::<PyFloat>() || value.is_instance_of::<PyInt>() {
        return value.extract();
    }
    let name: String = value.extract()?;
    Ok(tokens::TEXT_SCALE
        .iter()
        .find(|(key, _)| *key == name)
        .map(|(_, factor)| *factor)
        .unwrap_or(1.0))
}

#[pyfunction]
fn history_same_value(left: &str, right: &str) -> PyResult<bool> {
    guard(|| Ok(history::same_value(&parse(left)?, &parse(right)?)))
}

#[pyfunction]
fn history_capture_step(
    label: &str,
    week_start: &str,
    before_blocks: &str,
    after_blocks: &str,
    before_assignments: &str,
    after_assignments: &str,
    changed_ids: Vec<String>,
) -> PyResult<Option<String>> {
    guard(|| {
        let ids: HashSet<String> = changed_ids.into_iter().collect();
        Ok(history::capture_step(
            label,
            week_start,
            &objects(before_blocks)?,
            &objects(after_blocks)?,
            &object_map(before_assignments)?,
            &object_map(after_assignments)?,
            &ids,
        )
        .map(|step| dump(&Value::Object(step))))
    })
}

#[pyfunction]
fn history_push_step(stack: &str, step: &str) -> PyResult<String> {
    guard(|| {
        let mut items = maps_of(stack)?;
        let step = object_map(step)?;
        history::push_step(&mut items, step);
        Ok(dump(&Value::Array(
            items.into_iter().map(Value::Object).collect(),
        )))
    })
}

#[pyfunction]
fn history_join_step(stack: &str, step: &str) -> PyResult<String> {
    guard(|| {
        let mut items = maps_of(stack)?;
        history::join_step(&mut items, object_map(step)?);
        Ok(dump(&Value::Array(
            items.into_iter().map(Value::Object).collect(),
        )))
    })
}

#[pyfunction]
fn history_mark_stale(steps: &str, week_start: &str) -> PyResult<String> {
    guard(|| {
        let mut items = maps_of(steps)?;
        history::mark_stale(&mut items, week_start);
        Ok(dump(&Value::Array(
            items.into_iter().map(Value::Object).collect(),
        )))
    })
}

#[pyfunction]
fn week_set_clock_24h(on: bool) -> PyResult<bool> {
    guard(|| Ok(weekmodel::set_clock_24h(on)))
}

#[pyfunction]
fn week_minute_of(hhmm: &str) -> PyResult<i64> {
    guard(|| Ok(weekmodel::minute_of(hhmm)))
}

#[pyfunction]
fn week_clock_text(minute: i64) -> PyResult<String> {
    guard(|| Ok(weekmodel::clock_text(minute)))
}

#[pyfunction]
fn week_hhmm_text(hhmm: &str) -> PyResult<String> {
    guard(|| Ok(weekmodel::hhmm_text(hhmm)))
}

#[pyfunction]
fn week_time_format() -> PyResult<String> {
    guard(|| Ok(weekmodel::time_format().to_string()))
}

#[pyfunction]
fn week_clock_label(minute: i64) -> PyResult<String> {
    guard(|| Ok(weekmodel::clock_label(minute)))
}

#[pyfunction]
fn week_short_clock(minute: i64) -> PyResult<String> {
    guard(|| Ok(weekmodel::short_clock(minute)))
}

#[pyfunction]
fn week_range_label(start: i64, end: i64) -> PyResult<String> {
    guard(|| Ok(weekmodel::range_label(start, end)))
}

#[pyfunction]
fn week_length_label(minutes: i64) -> PyResult<String> {
    guard(|| Ok(weekmodel::length_label(minutes)))
}

#[pyfunction]
fn week_planned_line(planned_min: i64, done_min: i64) -> PyResult<String> {
    guard(|| Ok(weekmodel::planned_line(planned_min, done_min)))
}

#[pyfunction]
fn week_due_label(due: Option<&str>, week_start: &str) -> PyResult<String> {
    guard(|| Ok(weekmodel::due_label(due, week_start)))
}

#[pyfunction]
fn week_moved_words(
    block: &str,
    from_day: i64,
    day: i64,
    start: i64,
    end: i64,
) -> PyResult<String> {
    guard(|| {
        Ok(weekmodel::moved_words(
            &parse(block)?,
            from_day,
            day,
            start,
            end,
        ))
    })
}

#[pyfunction]
fn week_added_words(block: &str) -> PyResult<String> {
    guard(|| Ok(weekmodel::added_words(&parse(block)?)))
}

#[pyfunction]
fn week_dated_words(title: &str, iso: &str) -> PyResult<String> {
    guard(|| Ok(weekmodel::dated_words(title, iso)))
}

#[pyfunction]
fn week_build(
    week_start: &str,
    blocks: &str,
    assignments: &str,
    trace: Option<&str>,
) -> PyResult<String> {
    guard(|| {
        let blocks = objects(blocks)?;
        let assignments = object_map(assignments)?;
        let trace = trace.map(parse).transpose()?;
        Ok(dump(&weekmodel::build_week_json(
            week_start,
            &blocks,
            Some(&assignments),
            trace.as_ref(),
        )))
    })
}

#[pyfunction]
fn tokens_type_pt(role: &str, scale: &Bound<'_, PyAny>) -> PyResult<f64> {
    let factor = scale_factor(scale)?;
    guard(|| Ok(tokens::type_pt(role, TextScale::Factor(factor))))
}

#[pyfunction]
fn tokens_text_knob(body_pt: f64) -> PyResult<Option<String>> {
    guard(|| Ok(tokens::text_knob(body_pt).map(str::to_string)))
}

#[pyfunction]
fn tokens_linear_rgb(colour: &str) -> PyResult<(f64, f64, f64)> {
    guard(|| Ok(tokens::linear_rgb(colour)))
}

#[pyfunction]
fn tokens_hex_from_linear(red: f64, green: f64, blue: f64) -> PyResult<String> {
    guard(|| Ok(tokens::hex_from_linear(red, green, blue)))
}

#[pyfunction]
fn tokens_oklab_from_linear(red: f64, green: f64, blue: f64) -> PyResult<(f64, f64, f64)> {
    guard(|| Ok(tokens::oklab_from_linear(red, green, blue)))
}

#[pyfunction]
fn tokens_linear_from_oklab(light: f64, a: f64, b: f64) -> PyResult<(f64, f64, f64)> {
    guard(|| Ok(tokens::linear_from_oklab(light, a, b)))
}

#[pyfunction]
fn tokens_oklab(colour: &str) -> PyResult<(f64, f64, f64)> {
    guard(|| Ok(tokens::oklab(colour)))
}

#[pyfunction]
fn tokens_oklch(light: f64, chroma: f64, hue: f64) -> PyResult<String> {
    guard(|| Ok(tokens::oklch(light, chroma, hue)))
}

#[pyfunction]
fn tokens_mix(top: &str, bottom: &str, alpha: f64) -> PyResult<String> {
    guard(|| Ok(tokens::mix(top, bottom, alpha)))
}

#[pyfunction]
fn tokens_luminance(colour: &str) -> PyResult<f64> {
    guard(|| Ok(tokens::luminance(colour)))
}

#[pyfunction]
fn tokens_contrast(first: &str, second: &str) -> PyResult<f64> {
    guard(|| Ok(tokens::contrast(first, second)))
}

#[pyfunction]
fn tokens_oklch_of(colour: &str) -> PyResult<(f64, f64, f64)> {
    guard(|| Ok(tokens::oklch_of(colour)))
}

#[pyfunction]
fn tokens_fit_lightness(colour: &str, grounds: Vec<String>, floor: f64) -> PyResult<String> {
    let refs: Vec<&str> = grounds.iter().map(String::as_str).collect();
    guard(|| Ok(tokens::fit_lightness(colour, &refs, floor)))
}

#[pyfunction]
fn tokens_channels(colour: &str) -> PyResult<(i64, i64, i64)> {
    guard(|| tokens::channels(colour).map_err(raise))
}

#[pyfunction]
fn tokens_mix_oklab(top: &str, bottom: &str, amount: f64) -> PyResult<String> {
    guard(|| Ok(tokens::mix_oklab(top, bottom, amount)))
}

#[pyfunction]
fn tokens_family_colours(hue: f64, grey: bool, homework: bool, sleep: bool) -> PyResult<String> {
    guard(|| {
        let mut map = Map::new();
        for (family, pair) in tokens::family_colours(hue, grey, homework, sleep) {
            map.insert(family, serde_json::json!([pair.0, pair.1]));
        }
        Ok(dump(&Value::Object(map)))
    })
}

fn pomo_prefs(text: Option<&str>) -> PyResult<Option<Map<String, Value>>> {
    Ok(match text {
        Some(text) => Some(object_map(text)?),
        None => None,
    })
}

#[pyfunction]
fn pomo_timers(prefs: Option<&str>) -> PyResult<(i64, i64, i64, i64)> {
    let prefs = pomo_prefs(prefs)?;
    guard(|| Ok(pomodoro::timers(prefs.as_ref())))
}

#[pyfunction]
fn pomo_plan_for(duration_min: i64, prefs: Option<&str>) -> PyResult<String> {
    let prefs = pomo_prefs(prefs)?;
    guard(|| Ok(dump(&pomodoro::plan_for(duration_min, prefs.as_ref()))))
}

#[pyfunction]
fn pomo_child_title(title: &str, index: i64, total: i64) -> PyResult<String> {
    guard(|| Ok(pomodoro::child_title(title, index, total)))
}

fn fresh_id(py: Python<'_>) -> String {
    py.import("uuid")
        .and_then(|module| module.call_method0("uuid4"))
        .and_then(|value| value.str())
        .map(|text| text.to_string())
        .unwrap_or_else(|_| "id".to_string())
}

#[pyfunction]
fn pomo_split_children(py: Python<'_>, source: &str, placed: &str, plan: &str) -> PyResult<String> {
    let source = parse(source)?;
    let placed = parse(placed)?;
    let plan = parse(plan)?;
    guard(|| {
        Ok(dump(&Value::Array(pomodoro::split_children(
            &source,
            &placed,
            &plan,
            || fresh_id(py),
        ))))
    })
}

#[pyfunction]
fn pomo_splittable(block: &str, prefs: Option<&str>) -> PyResult<bool> {
    let prefs = pomo_prefs(prefs)?;
    guard(|| Ok(pomodoro::splittable(&parse(block)?, prefs.as_ref())))
}

#[pyfunction]
fn pomo_inflate_for_solve(blocks: &str, prefs: Option<&str>) -> PyResult<String> {
    let prefs = pomo_prefs(prefs)?;
    guard(|| {
        Ok(dump(&Value::Array(pomodoro::inflate_for_solve(
            &objects(blocks)?,
            prefs.as_ref(),
        ))))
    })
}

#[pyfunction]
fn pomo_split_solved(
    py: Python<'_>,
    blocks: &str,
    trace: Option<&str>,
    prefs: Option<&str>,
) -> PyResult<(String, i64)> {
    let prefs = pomo_prefs(prefs)?;
    let trace = trace.map(parse).transpose()?;
    let blocks = objects(blocks)?;
    guard(|| {
        let (blocks, count) =
            pomodoro::split_solved(&blocks, trace.as_ref(), prefs.as_ref(), || fresh_id(py));
        Ok((dump(&Value::Array(blocks)), count))
    })
}

fn fresh_ids(text: &str) -> PyResult<HashSet<String>> {
    Ok(parse(text)?
        .as_array()
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|item| item.as_str().map(str::to_string))
        .collect())
}

#[pyfunction]
fn remind_lead_min(prefs: Option<&str>, default: i64) -> PyResult<i64> {
    let prefs = pomo_prefs(prefs)?;
    guard(|| remind::reminder_lead_min(prefs.as_ref(), default).map_err(raise))
}

#[pyfunction]
fn remind_start_alert_due(start_min: i64, now_min: i64, lead: i64) -> PyResult<bool> {
    guard(|| Ok(remind::start_alert_due(start_min, now_min, lead)))
}

#[pyfunction]
fn remind_song_due(start_min: i64, now_min: i64) -> PyResult<bool> {
    guard(|| Ok(remind::song_due(start_min, now_min)))
}

#[pyfunction]
fn remind_key(week_start: &str, block_id: &str, day: i64, start: &str) -> PyResult<String> {
    guard(|| Ok(remind::reminder_key(week_start, block_id, day, start)))
}

#[pyfunction]
fn remind_alarm_key(iso_date: &str, alarm: &str) -> PyResult<String> {
    guard(|| Ok(remind::alarm_key(iso_date, &object_map(alarm)?)))
}

#[pyfunction]
fn remind_blocks(blocks: &str, trace: Option<&str>) -> PyResult<String> {
    let trace = trace.map(parse).transpose()?;
    guard(|| {
        let rows = remind::reminder_blocks(&objects(blocks)?, trace.as_ref()).map_err(raise)?;
        Ok(dump(&Value::Array(rows)))
    })
}

#[pyfunction]
fn remind_due(
    blocks: &str,
    trace: Option<&str>,
    today_iso: &str,
    now_min: i64,
    lead_min: i64,
    fired: &str,
) -> PyResult<String> {
    let trace = trace.map(parse).transpose()?;
    let fired = fresh_ids(fired)?;
    guard(|| {
        let rows = remind::due_reminders(
            &objects(blocks)?,
            trace.as_ref(),
            today_iso,
            now_min,
            lead_min,
            &fired,
        )
        .map_err(raise)?;
        Ok(dump(&Value::Array(rows)))
    })
}

#[pyfunction]
fn remind_songs(
    blocks: &str,
    trace: Option<&str>,
    today_iso: &str,
    now_min: i64,
    played: &str,
) -> PyResult<String> {
    let trace = trace.map(parse).transpose()?;
    let played = fresh_ids(played)?;
    guard(|| {
        let rows = remind::due_songs(
            &objects(blocks)?,
            trace.as_ref(),
            today_iso,
            now_min,
            &played,
        )
        .map_err(raise)?;
        Ok(dump(&Value::Array(rows)))
    })
}

#[pyfunction]
fn remind_clock_parts(
    now_ms: i64,
    year: i32,
    month: u32,
    day: u32,
    hour: i64,
    minute: i64,
    midnight_ms: i64,
) -> PyResult<String> {
    guard(|| {
        let parts = remind::clock_parts(now_ms, (year, month, day, hour, minute), midnight_ms)
            .map_err(raise)?;
        Ok(dump(&Value::Object(parts)))
    })
}

#[pyfunction]
fn remind_todays_starts(blocks: &str, trace: Option<&str>, today_iso: &str) -> PyResult<String> {
    let trace = trace.map(parse).transpose()?;
    guard(|| {
        let rows =
            remind::todays_starts(&objects(blocks)?, trace.as_ref(), today_iso).map_err(raise)?;
        Ok(dump(&Value::Array(
            rows.into_iter()
                .map(|(block, day, start, key)| serde_json::json!([block, day, start, key]))
                .collect(),
        )))
    })
}

/// `due_ms_of(hour, minute)` is the caller's own local-clock conversion; a Python error from it
/// is raised as it came.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn remind_due_alarms(
    alarms: &str,
    today_iso: &str,
    weekday: i64,
    now_ms: i64,
    last_check_ms: Option<i64>,
    fired: &Bound<'_, PySet>,
    snoozed: &str,
    due_ms_of: &Bound<'_, PyAny>,
) -> PyResult<(String, String, i64)> {
    let alarms = objects(alarms)?;
    let waiting: Vec<(String, i64)> = object_map(snoozed)?
        .into_iter()
        .map(|(id, due)| {
            due.as_i64()
                .map(|ms| (id, ms))
                .ok_or_else(|| PyTypeError::new_err("snoozed times must be whole milliseconds"))
        })
        .collect::<PyResult<_>>()?;
    let mut seen: HashSet<String> = fired
        .iter()
        .filter_map(|key| key.extract::<String>().ok())
        .collect();
    let before = seen.clone();
    let failure: RefCell<Option<PyErr>> = RefCell::new(None);
    let mut convert = |hour: i64, minute: i64| -> EngineResult<i64> {
        due_ms_of
            .call1((hour, minute))
            .and_then(|value| value.extract::<i64>())
            .map_err(|error| {
                *failure.borrow_mut() = Some(error);
                EngineError::value("local time")
            })
    };
    let outcome = guard(|| {
        Ok(remind::due_alarms(
            &alarms,
            today_iso,
            weekday,
            now_ms,
            last_check_ms,
            &mut seen,
            &waiting,
            &mut convert,
        ))
    })?;
    for key in seen.difference(&before) {
        fired.add(key)?;
    }
    if let Some(error) = failure.into_inner() {
        return Err(error);
    }
    let (queued, remaining, last) = outcome.map_err(raise)?;
    let remaining: Map<String, Value> = remaining
        .into_iter()
        .map(|(id, due)| (id, Value::from(due)))
        .collect();
    Ok((
        dump(&Value::Array(queued)),
        dump(&Value::Object(remaining)),
        last,
    ))
}

#[pyfunction]
fn remind_snooze_until(now_ms: i64) -> PyResult<i64> {
    guard(|| Ok(remind::snooze_until(now_ms)))
}

#[pyfunction]
fn update_install_kind(
    platform: &str,
    appimage: &str,
    appdir: &str,
    executable: &str,
) -> PyResult<String> {
    guard(|| {
        Ok(update::install_kind(
            Some(platform),
            Some(appimage),
            Some(appdir),
            Some(executable),
        )
        .to_string())
    })
}

#[pyfunction]
fn update_asset_name(kind: &str) -> PyResult<Option<String>> {
    guard(|| Ok(update::asset_name(kind).map(str::to_string)))
}

#[pyfunction]
fn update_available(release: &str, kind: &str, current: &str) -> PyResult<Option<String>> {
    guard(|| {
        Ok(
            update::available(&parse(release)?, kind, current).map(|item| {
                dump(&serde_json::json!({
                    "version": item.version,
                    "asset": item.asset,
                    "url": item.url,
                    "checksum_url": item.checksum_url,
                    "notes": item.notes,
                }))
            }),
        )
    })
}

#[pyfunction]
fn update_verified(payload: &[u8], digest: Option<&str>) -> PyResult<bool> {
    guard(|| Ok(update::verified(payload, digest)))
}

pub fn add(module: &Bound<'_, PyModule>) -> PyResult<()> {
    crate::export!(
        module,
        history_same_value,
        history_capture_step,
        history_push_step,
        history_join_step,
        history_mark_stale,
        week_set_clock_24h,
        week_minute_of,
        week_clock_text,
        week_hhmm_text,
        week_time_format,
        week_clock_label,
        week_short_clock,
        week_range_label,
        week_length_label,
        week_planned_line,
        week_due_label,
        week_moved_words,
        week_added_words,
        week_dated_words,
        week_build,
        tokens_type_pt,
        tokens_text_knob,
        tokens_linear_rgb,
        tokens_hex_from_linear,
        tokens_oklab_from_linear,
        tokens_linear_from_oklab,
        tokens_oklab,
        tokens_oklch,
        tokens_mix,
        tokens_luminance,
        tokens_contrast,
        tokens_oklch_of,
        tokens_fit_lightness,
        tokens_channels,
        tokens_mix_oklab,
        tokens_family_colours,
        pomo_timers,
        pomo_plan_for,
        pomo_child_title,
        pomo_split_children,
        pomo_splittable,
        pomo_inflate_for_solve,
        pomo_split_solved,
        remind_lead_min,
        remind_start_alert_due,
        remind_song_due,
        remind_key,
        remind_alarm_key,
        remind_clock_parts,
        remind_todays_starts,
        remind_due_alarms,
        remind_blocks,
        remind_due,
        remind_songs,
        remind_snooze_until,
        update_install_kind,
        update_asset_name,
        update_available,
        update_verified,
    );
    Ok(())
}
