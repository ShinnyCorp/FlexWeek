//! Desktop logic bindings. Dicts cross as JSON text.

use ::flexweek_engine::desk::tokens::TextScale;
use ::flexweek_engine::desk::weekview::{self, Week};
use ::flexweek_engine::desk::{history, pomodoro, remind, tokens, update, weekmodel};
use std::cell::RefCell;

use ::flexweek_engine::{EngineError, EngineResult, ErrorKind};
use pyo3::exceptions::{PyKeyError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyAnyMethods, PyDict, PyFloat, PyFrozenSet, PyInt, PyList, PySet, PySetMethods};
use serde_json::{Map, Value};

use crate::{guard, raise};

/// The text has already been through Python's `json.loads`, which stops at about 1,000 levels of
/// nesting, so serde's own limit of 128 is lifted: a look or week file nested past it must read as
/// the original read it, not raise.
pub(crate) fn parse(text: &str) -> PyResult<Value> {
    let mut reader = serde_json::Deserializer::from_str(text);
    reader.disable_recursion_limit();
    serde::Deserialize::deserialize(&mut reader)
        .map_err(|error: serde_json::Error| PyValueError::new_err(error.to_string()))
}

pub(crate) fn dump(value: &Value) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "null".to_string())
}

pub(crate) fn objects(text: &str) -> PyResult<Vec<Value>> {
    Ok(parse(text)?.as_array().cloned().unwrap_or_default())
}

pub(crate) fn object_map(text: &str) -> PyResult<Map<String, Value>> {
    Ok(parse(text)?.as_object().cloned().unwrap_or_default())
}

fn scale_of(value: &Bound<'_, PyAny>) -> PyResult<TextScale> {
    if value.is_instance_of::<PyFloat>() || value.is_instance_of::<PyInt>() {
        return Ok(TextScale::Factor(value.extract()?));
    }
    let name: String = value.extract()?;
    Ok(TextScale::Named(name))
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
    changed_ids: &Bound<'_, PyAny>,
) -> PyResult<Option<String>> {
    let (before_blocks, after_blocks) = (parse(before_blocks)?, parse(after_blocks)?);
    let (before_assignments, after_assignments) =
        (parse(before_assignments)?, parse(after_assignments)?);
    let changed_ids = changed_ids
        .try_iter()?
        .map(|item| item?.extract::<String>())
        .collect::<PyResult<Vec<String>>>()?;
    guard(|| {
        let step = history::capture_step(
            label,
            week_start,
            &before_blocks,
            &after_blocks,
            &before_assignments,
            &after_assignments,
            &changed_ids,
        )
        .map_err(raise)?;
        Ok(step.map(|value| dump(&value)))
    })
}

/// `json.dumps(value)`, as the Python wrappers wrote it, so a value JSON cannot hold fails alike.
pub(crate) fn dumps_of(value: &Bound<'_, PyAny>) -> PyResult<String> {
    value
        .py()
        .import("json")?
        .call_method1("dumps", (value,))?
        .extract()
}

/// `json.loads(text)`: a value of the engine's, as the Python wrappers read it.
pub(crate) fn loads_of<'py>(py: Python<'py>, value: &Value) -> PyResult<Bound<'py, PyAny>> {
    py.import("json")?.call_method1("loads", (dump(value),))
}

/// What a set argument holds, written as the Python wrappers wrote it: a set or frozenset as the list
/// of its members, anything else as it is, and whether it was a set.
pub(crate) fn members_of(held: &Bound<'_, PyAny>) -> PyResult<(String, bool)> {
    if held.is_instance_of::<PySet>() || held.is_instance_of::<PyFrozenSet>() {
        let members = held.py().get_type::<PyList>().call1((held,))?;
        return Ok((dumps_of(&members)?, true));
    }
    Ok((dumps_of(held)?, false))
}

fn push_onto(stack: &Bound<'_, PyAny>, step: &Bound<'_, PyAny>) -> PyResult<()> {
    history::push_step(
        step,
        |step| stack.call_method1("append", (step,)).map(|_| ()),
        || stack.len(),
        || stack.del_item(0),
    )
}

/// Puts `step` on the newest end of `stack`, which is the caller's own list, and drops the oldest
/// step when that leaves it over the limit.
#[pyfunction]
fn history_push(stack: &Bound<'_, PyAny>, step: &Bound<'_, PyAny>) -> PyResult<()> {
    guard(|| push_onto(stack, step))
}

/// Folds `step` into the newest step of `stack`, or pushes it when there is none or that one is
/// stale. `stack` is changed in place.
#[pyfunction]
fn history_join(stack: &Bound<'_, PyAny>, step: &Bound<'_, PyAny>) -> PyResult<()> {
    guard(|| {
        if !stack.is_truthy()? {
            return push_onto(stack, step);
        }
        let newest = stack.get_item(-1)?;
        let (earlier, step_value) = (parse(&dumps_of(&newest)?)?, parse(&dumps_of(step)?)?);
        match history::join_into(&earlier, &step_value).map_err(raise)? {
            Some(joined) => stack.set_item(-1, loads_of(stack.py(), &joined)?),
            None => push_onto(stack, step),
        }
    })
}

/// Marks every step of `steps` that holds a week of `week_start` as stale, in place.
#[pyfunction]
fn history_mark_stale(steps: &Bound<'_, PyAny>, week_start: &Bound<'_, PyAny>) -> PyResult<()> {
    guard(|| {
        let items = steps.try_iter()?.map(|step| {
            let step = step?;
            let held = parse(&dumps_of(&step)?)?;
            let week = parse(&dumps_of(week_start)?)?;
            Ok((held, week, step))
        });
        history::mark_stale(items, |step| step.set_item("stale", true), raise)
    })
}

#[pyfunction]
fn week_set_clock_24h(on: bool) -> PyResult<()> {
    guard(|| {
        weekmodel::set_clock_24h(on);
        Ok(())
    })
}

#[pyfunction]
fn week_minute_of(hhmm: &str) -> PyResult<i128> {
    guard(|| weekmodel::minute_of(hhmm).map_err(raise))
}

#[pyfunction]
fn week_clock_text(minute: i64) -> PyResult<String> {
    guard(|| Ok(weekmodel::clock_text(minute)))
}

#[pyfunction]
fn week_hhmm_text(hhmm: &str) -> PyResult<String> {
    guard(|| weekmodel::hhmm_text(hhmm).map_err(raise))
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
fn week_due_label(due: &str) -> PyResult<String> {
    let due = parse(due)?;
    guard(|| weekmodel::due_label(&due).map_err(raise))
}

#[pyfunction]
fn week_moved_words(
    block: &str,
    from_day: i64,
    day: i64,
    start: i64,
    end: i64,
) -> PyResult<String> {
    let block = parse(block)?;
    guard(|| weekmodel::moved_words(&block, from_day, day, start, end).map_err(raise))
}

#[pyfunction]
fn week_added_words(block: &str) -> PyResult<String> {
    let block = parse(block)?;
    guard(|| weekmodel::added_words(&block).map_err(raise))
}

#[pyfunction]
fn week_dated_words(title: &str, iso: &str) -> PyResult<String> {
    let (title, iso) = (parse(title)?, parse(iso)?);
    guard(|| weekmodel::dated_words(&title, &iso).map_err(raise))
}

#[pyfunction]
fn week_build(week_start: &str, blocks: &str, assignments: &str, trace: &str) -> PyResult<String> {
    let (week_start, blocks) = (parse(week_start)?, parse(blocks)?);
    let (assignments, trace) = (parse(assignments)?, parse(trace)?);
    guard(|| {
        weekmodel::build_week(&week_start, &blocks, &assignments, &trace)
            .map(|week| dump(&week))
            .map_err(raise)
    })
}

#[pyfunction]
fn week_slack_words(slack: Option<&str>) -> PyResult<&'static str> {
    guard(|| Ok(weekview::slack_words(slack)))
}

#[pyfunction]
fn week_occurrence_minutes(start: i64, end: i64) -> PyResult<i64> {
    guard(|| Ok(weekview::minutes(start, end)))
}

#[pyfunction]
fn week_occurrence_live(work: bool, done: bool, missed: bool) -> PyResult<bool> {
    guard(|| Ok(weekview::live(work, done, missed)))
}

#[pyfunction]
fn week_date_of(week_start: &str, day: i64) -> PyResult<(i32, u32, u32)> {
    guard(|| weekview::date_of(week_start, day).map_err(raise))
}

/// A week read once, so the model's methods do not parse it on every call. It never changes, so a
/// copy is itself, and it pickles as the text it was made from.
#[pyclass(name = "WeekHandle", frozen, module = "flexweek_engine")]
#[derive(Clone)]
struct WeekHandle {
    week: Week,
    text: String,
}

#[pymethods]
impl WeekHandle {
    #[new]
    fn new(text: String) -> PyResult<Self> {
        let week = Week::read(&text).map_err(raise)?;
        Ok(Self { week, text })
    }

    fn on_day(&self, day: i64) -> Vec<usize> {
        self.week.on_day(day)
    }

    fn load_min(&self, day: i64) -> i64 {
        self.week.load_min(day)
    }

    fn open_work(&self) -> PyResult<Vec<usize>> {
        self.week.open_work().map_err(raise)
    }

    fn due_today_unplaced(&self, today: Option<i64>) -> PyResult<Vec<usize>> {
        self.week.due_today_unplaced(today).map_err(raise)
    }

    fn leftover_kind(&self, today: Option<i64>) -> PyResult<&'static str> {
        self.week.leftover_kind(today).map_err(raise)
    }

    fn leftover_words(&self, today: Option<i64>) -> PyResult<&'static str> {
        self.week.leftover_words(today).map_err(raise)
    }

    fn leftover_parts(&self, today: Option<i64>) -> PyResult<(String, String, String)> {
        self.week.leftover_parts(today).map_err(raise)
    }

    fn minutes_left_today(&self, today: Option<i64>, minute: i64) -> PyResult<i64> {
        self.week.minutes_left_today(today, minute).map_err(raise)
    }

    fn day_queue(&self, day: i64, minute: i64) -> (Option<usize>, Vec<usize>) {
        self.week.day_queue(day, minute)
    }

    fn __copy__(&self) -> Self {
        self.clone()
    }

    fn __deepcopy__(&self, _memo: &Bound<'_, PyAny>) -> Self {
        self.clone()
    }

    fn __reduce__<'py>(&self, py: Python<'py>) -> (Bound<'py, pyo3::types::PyType>, (String,)) {
        (py.get_type::<Self>(), (self.text.clone(),))
    }
}

#[pyfunction]
fn tokens_type_pt(role: &str, scale: &Bound<'_, PyAny>) -> PyResult<f64> {
    let scale = scale_of(scale)?;
    guard(|| tokens::type_pt(role, &scale).map_err(raise))
}

#[pyfunction]
fn tokens_text_knob(body_pt: f64) -> PyResult<Option<String>> {
    guard(|| Ok(tokens::text_knob(body_pt).map(str::to_string)))
}

#[pyfunction]
fn tokens_linear_rgb(colour: &str) -> PyResult<(f64, f64, f64)> {
    guard(|| tokens::linear_rgb(colour).map_err(raise))
}

#[pyfunction]
fn tokens_hex_from_linear(red: f64, green: f64, blue: f64) -> PyResult<String> {
    guard(|| tokens::hex_from_linear(red, green, blue).map_err(raise))
}

#[pyfunction]
fn tokens_oklab_from_linear(red: f64, green: f64, blue: f64) -> PyResult<(f64, f64, f64)> {
    guard(|| Ok(tokens::oklab_from_linear(red, green, blue)))
}

#[pyfunction]
fn tokens_linear_from_oklab(light: f64, a: f64, b: f64) -> PyResult<(f64, f64, f64)> {
    guard(|| tokens::linear_from_oklab(light, a, b).map_err(raise))
}

#[pyfunction]
fn tokens_oklab(colour: &str) -> PyResult<(f64, f64, f64)> {
    guard(|| tokens::oklab(colour).map_err(raise))
}

#[pyfunction]
fn tokens_oklch(light: f64, chroma: f64, hue: f64) -> PyResult<String> {
    guard(|| tokens::oklch(light, chroma, hue).map_err(raise))
}

#[pyfunction]
fn tokens_mix(top: &str, bottom: &str, alpha: f64) -> PyResult<String> {
    guard(|| tokens::mix(top, bottom, alpha).map_err(raise))
}

#[pyfunction]
fn tokens_luminance(colour: &str) -> PyResult<f64> {
    guard(|| tokens::luminance(colour).map_err(raise))
}

#[pyfunction]
fn tokens_contrast(first: &str, second: &str) -> PyResult<f64> {
    guard(|| tokens::contrast(first, second).map_err(raise))
}

#[pyfunction]
fn tokens_oklch_of(colour: &str) -> PyResult<(f64, f64, f64)> {
    guard(|| tokens::oklch_of(colour).map_err(raise))
}

#[pyfunction]
fn tokens_fit_lightness(colour: &str, grounds: &str, floor: f64) -> PyResult<String> {
    let grounds = parse(grounds)?;
    guard(|| {
        let grounds = grounds.as_array().cloned().unwrap_or_default();
        tokens::fit_lightness(colour, &grounds, floor).map_err(raise)
    })
}

#[pyfunction]
fn tokens_channels(colour: &str) -> PyResult<(i64, i64, i64)> {
    guard(|| tokens::channels(colour).map_err(raise))
}

#[pyfunction]
fn tokens_mix_oklab(top: &str, bottom: &str, amount: f64) -> PyResult<String> {
    guard(|| tokens::mix_oklab(top, bottom, amount).map_err(raise))
}

#[pyfunction]
fn tokens_family_colours(hue: f64, grey: bool, homework: bool, sleep: bool) -> PyResult<String> {
    guard(|| {
        let mut map = Map::new();
        for (family, pair) in tokens::family_colours(hue, grey, homework, sleep).map_err(raise)? {
            map.insert(family, serde_json::json!([pair.0, pair.1]));
        }
        Ok(dump(&Value::Object(map)))
    })
}

#[pyfunction]
fn pomo_timers(prefs: &str) -> PyResult<String> {
    let prefs = parse(prefs)?;
    guard(|| {
        let (work, rest, long, every) = pomodoro::timers(&prefs).map_err(raise)?;
        Ok(format!("[{work}, {rest}, {long}, {every}]"))
    })
}

#[pyfunction]
fn pomo_plan_for(duration_min: i64, prefs: &str) -> PyResult<String> {
    let prefs = parse(prefs)?;
    guard(|| {
        Ok(dump(
            &pomodoro::plan_for(duration_min, &prefs).map_err(raise)?,
        ))
    })
}

#[pyfunction]
fn pomo_child_title(title: &str, index: i64, total: i64) -> PyResult<String> {
    guard(|| Ok(pomodoro::child_title(title, index, total)))
}

pub(crate) fn fresh_id(py: Python<'_>) -> String {
    py.import("uuid")
        .and_then(|module| module.call_method0("uuid4"))
        .and_then(|value| value.str())
        .map(|text| text.to_string())
        .unwrap_or_else(|_| "id".to_string())
}

#[pyfunction]
fn pomo_split_children(py: Python<'_>, source: &str, placed: &str, plan: &str) -> PyResult<String> {
    let (source, placed, plan) = (parse(source)?, parse(placed)?, parse(plan)?);
    guard(|| {
        let children =
            pomodoro::split_children(&source, &placed, &plan, || fresh_id(py)).map_err(raise)?;
        Ok(dump(&Value::Array(children)))
    })
}

#[pyfunction]
fn pomo_splittable(block: &str, prefs: &str) -> PyResult<bool> {
    let (block, prefs) = (parse(block)?, parse(prefs)?);
    guard(|| pomodoro::splittable(&block, &prefs).map_err(raise))
}

#[pyfunction]
fn pomo_inflate_for_solve(blocks: &str, prefs: &str) -> PyResult<String> {
    let (blocks, prefs) = (parse(blocks)?, parse(prefs)?);
    guard(|| {
        Ok(dump(
            &pomodoro::inflate_for_solve(&blocks, &prefs).map_err(raise)?,
        ))
    })
}

#[pyfunction]
fn pomo_split_solved(
    py: Python<'_>,
    blocks: &str,
    trace: &str,
    prefs: &str,
) -> PyResult<(String, i64)> {
    let (blocks, trace, prefs) = (parse(blocks)?, parse(trace)?, parse(prefs)?);
    guard(|| {
        let (out, count) =
            pomodoro::split_solved(&blocks, &trace, &prefs, || fresh_id(py)).map_err(raise)?;
        Ok((dump(&out), count))
    })
}

#[pyfunction]
fn remind_lead_min(prefs: &str, default: i64) -> PyResult<i128> {
    let prefs = parse(prefs)?;
    guard(|| remind::reminder_lead_min(&prefs, default).map_err(raise))
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
    let alarm = parse(alarm)?;
    guard(|| remind::alarm_key(iso_date, &alarm).map_err(raise))
}

#[pyfunction]
fn remind_blocks(blocks: &str, trace: &str) -> PyResult<String> {
    let (blocks, trace) = (parse(blocks)?, parse(trace)?);
    guard(|| {
        let rows = remind::reminder_blocks(&blocks, &trace).map_err(raise)?;
        Ok(dump(&Value::Array(rows)))
    })
}

#[pyfunction]
fn remind_due(
    blocks: &str,
    trace: &str,
    today_iso: &str,
    now_min: i64,
    lead_min: i64,
    fired: &Bound<'_, PyAny>,
) -> PyResult<String> {
    let (blocks, trace) = (parse(blocks)?, parse(trace)?);
    let (fired, fired_is_set) = members_of(fired)?;
    let fired = parse(&fired)?;
    guard(|| {
        let rows = remind::due_reminders(
            &blocks,
            &trace,
            today_iso,
            now_min,
            lead_min,
            &fired,
            fired_is_set,
        )
        .map_err(raise)?;
        Ok(dump(&Value::Array(rows)))
    })
}

#[pyfunction]
fn remind_songs(
    blocks: &str,
    trace: &str,
    today_iso: &str,
    now_min: i64,
    played: &Bound<'_, PyAny>,
) -> PyResult<String> {
    let (blocks, trace) = (parse(blocks)?, parse(trace)?);
    let (played, played_is_set) = members_of(played)?;
    let played = parse(&played)?;
    guard(|| {
        let rows = remind::due_songs(&blocks, &trace, today_iso, now_min, &played, played_is_set)
            .map_err(raise)?;
        Ok(dump(&Value::Array(rows)))
    })
}

/// `moment_at(seconds)` and `moment_of(year, month, day)` are the caller's own local-clock
/// constructors (`datetime.fromtimestamp` and `datetime`); a Python error from them is raised as it
/// came.
#[pyfunction]
fn remind_clock_parts(
    now_ms: i64,
    moment_at: &Bound<'_, PyAny>,
    moment_of: &Bound<'_, PyAny>,
) -> PyResult<String> {
    let moment = moment_at.call1((remind::seconds_of(now_ms),))?;
    let field = |name: &str| moment.getattr(name);
    let (year, month, day) = (
        field("year")?.extract::<i32>()?,
        field("month")?.extract::<u32>()?,
        field("day")?.extract::<u32>()?,
    );
    let (hour, minute) = (
        field("hour")?.extract::<i64>()?,
        field("minute")?.extract::<i64>()?,
    );
    let midnight = moment_of.call1((year, month, day))?;
    let midnight_ms = remind::millis_of(midnight.call_method0("timestamp")?.extract::<f64>()?);
    guard(|| {
        let parts = remind::clock_parts(now_ms, (year, month, day, hour, minute), midnight_ms)
            .map_err(raise)?;
        Ok(dump(&Value::Object(parts)))
    })
}

#[pyfunction]
fn remind_todays_starts(blocks: &str, trace: &str, today_iso: &str) -> PyResult<String> {
    let (blocks, trace) = (parse(blocks)?, parse(trace)?);
    guard(|| {
        let rows = remind::todays_starts(&blocks, &trace, today_iso).map_err(raise)?;
        Ok(dump(&Value::Array(
            rows.into_iter()
                .map(|(block, day, start, key)| serde_json::json!([block, day, start, key]))
                .collect(),
        )))
    })
}

/// `moment_of_day(today_iso)` is the caller's own date reader (`datetime.fromisoformat`); the local
/// time of an alarm is read from it when one is needed, and a Python error from it is raised as it
/// came. `fired` gets the keys the engine marks when it is a set, whether or not the call goes on to
/// fail.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn remind_due_alarms(
    alarms: &str,
    today_iso: &str,
    weekday: i64,
    now_ms: i64,
    last_check_ms: Option<i64>,
    fired: &Bound<'_, PyAny>,
    snoozed: &str,
    moment_of_day: &Bound<'_, PyAny>,
) -> PyResult<(String, String, i64)> {
    let fired_set = fired.cast::<PySet>().ok();
    let is_set = fired_set.is_some();
    let held_type = fired.get_type().name()?.to_string();
    let (members, _) = members_of(fired)?;
    let (alarms, fired, snoozed) = (parse(alarms)?, parse(&members)?, parse(snoozed)?);
    let mut added: Vec<String> = Vec::new();
    let failure: RefCell<Option<PyErr>> = RefCell::new(None);
    let mut convert = |hour: i64, minute: i64| -> EngineResult<i64> {
        let read = || -> PyResult<i64> {
            let kwargs = PyDict::new(moment_of_day.py());
            kwargs.set_item("hour", hour)?;
            kwargs.set_item("minute", minute)?;
            kwargs.set_item("second", 0)?;
            kwargs.set_item("microsecond", 0)?;
            let day = moment_of_day.call1((today_iso,))?;
            let due_at = day.call_method("replace", (), Some(&kwargs))?;
            let seconds = due_at.call_method0("timestamp")?.extract::<f64>()?;
            Ok(remind::millis_of(seconds))
        };
        read().map_err(|error| {
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
            &fired,
            fired_set.is_some(),
            &mut added,
            &snoozed,
            &mut convert,
        ))
    })?;
    if let Some(set) = fired_set {
        for key in &added {
            set.add(key)?;
        }
    }
    if let Some(error) = failure.into_inner() {
        return Err(error);
    }
    let (queued, remaining, last) = outcome.map_err(|mut error| {
        // The core saw a list; a frozenset or tuple names its own type in Python's message.
        if !is_set
            && error.kind == ErrorKind::Attribute
            && error.message.ends_with("attribute 'add'")
        {
            error.message = format!("'{held_type}' object has no attribute 'add'");
        }
        raise(error)
    })?;
    let remaining: Map<String, Value> = remaining
        .into_iter()
        .filter_map(|(id, due)| id.as_str().map(|name| (name.to_string(), due)))
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
fn update_parse_version(value: &str) -> PyResult<Option<Vec<i64>>> {
    guard(|| Ok(update::parse_version(value)))
}

#[pyfunction]
fn update_is_newer(candidate: &str, current: &str) -> PyResult<bool> {
    guard(|| Ok(update::is_newer(candidate, current)))
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
fn update_asset_name(kind: &str) -> PyResult<String> {
    guard(|| {
        update::asset_name(kind)
            .map(str::to_string)
            .ok_or_else(|| PyKeyError::new_err((kind.to_string(),)))
    })
}

/// `release` is whatever the network handed back; only a dict is a release, anything else is
/// none.
#[pyfunction]
fn update_available(
    release: &Bound<'_, PyAny>,
    kind: &str,
    current: &str,
) -> PyResult<Option<String>> {
    if !release.is_instance_of::<PyDict>() {
        return Ok(None);
    }
    let release = parse(&dumps_of(release)?)?;
    guard(|| {
        let found = update::available(&release, kind, current).map_err(raise)?;
        Ok(found.map(|item| {
            dump(&serde_json::json!({
                "version": item.version,
                "asset": item.asset,
                "url": item.url,
                "checksum_url": item.checksum_url,
                "notes": item.notes,
            }))
        }))
    })
}

/// `payload` is read only when there is a digest to compare it with, as `hashlib` was.
#[pyfunction]
fn update_verified(payload: &Bound<'_, PyAny>, digest: Option<&str>) -> PyResult<bool> {
    let wanted = digest.filter(|text| !text.is_empty() && text.chars().count() == 64);
    if wanted.is_none() {
        return Ok(false);
    }
    if payload.is_instance_of::<pyo3::types::PyString>() {
        return Err(PyTypeError::new_err(
            "Strings must be encoded before hashing",
        ));
    }
    let Ok(bytes) = payload.extract::<Vec<u8>>() else {
        return Err(PyTypeError::new_err(
            "object supporting the buffer API required",
        ));
    };
    guard(|| Ok(update::verified(&bytes, digest)))
}

pyo3::create_exception!(
    flexweek_engine,
    LookNameProblem,
    PyValueError,
    "A name a saved look cannot have, or one no saved look has."
);

pub fn add(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<WeekHandle>()?;
    module.add("LookNameProblem", module.py().get_type::<LookNameProblem>())?;
    crate::export!(
        module,
        history_same_value,
        history_capture_step,
        history_push,
        history_join,
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
        week_slack_words,
        week_occurrence_minutes,
        week_occurrence_live,
        week_date_of,
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
        update_parse_version,
        update_is_newer,
        update_install_kind,
        update_asset_name,
        update_available,
        update_verified,
        week_handle_of,
        week_set_clock,
    );
    Ok(())
}

/// `value` as text, refused as PyO3 refuses an argument of the wrong kind, for what the Python
/// wrapper once passed as an argument and the binding now reads off an object.
pub(crate) fn text_arg(value: &Bound<'_, PyAny>, name: &str) -> PyResult<String> {
    value.extract::<String>().map_err(|error| {
        if error.is_instance_of::<PyTypeError>(value.py()) {
            PyTypeError::new_err(format!("argument '{name}': {error}"))
        } else {
            error
        }
    })
}

/// `text_arg`, with none allowed.
pub(crate) fn opt_text_arg(value: &Bound<'_, PyAny>, name: &str) -> PyResult<Option<String>> {
    if value.is_none() {
        return Ok(None);
    }
    text_arg(value, name).map(Some)
}

/// `getattr(object, name, None)`.
pub(crate) fn attr_or_none<'py>(
    object: &Bound<'py, PyAny>,
    name: &str,
) -> PyResult<Bound<'py, PyAny>> {
    match object.getattr(name) {
        Err(error) if error.is_instance_of::<pyo3::exceptions::PyAttributeError>(object.py()) => {
            Ok(object.py().None().into_bound(object.py()))
        }
        found => found,
    }
}

/// The week a `WeekModel` holds, read once and kept on the model when its tuples cannot change, so
/// the methods of a week on screen do not read it again. A model whose occurrences or waiting are
/// lists is read each time, since they can.
#[pyfunction]
fn week_handle_of(model: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    guard(|| {
        let py = model.py();
        let kept = model.getattr("__dict__")?;
        let held = kept.call_method1("get", ("_engine_week",))?;
        if !held.is_none() {
            return Ok(held.unbind());
        }
        let vars = py.import("builtins")?.getattr("vars")?;
        let week_start = model.getattr("week_start")?;
        let occurrences = model.getattr("occurrences")?;
        let occupied = PyList::empty(py);
        for item in occurrences.try_iter()? {
            occupied.append(vars.call1((item?,))?)?;
        }
        let waiting = model.getattr("waiting")?;
        let queued = PyList::empty(py);
        for item in waiting.try_iter()? {
            queued.append(vars.call1((item?,))?)?;
        }
        let body = PyDict::new(py);
        body.set_item("week_start", week_start)?;
        body.set_item("occurrences", occupied)?;
        body.set_item("waiting", queued)?;
        let handle = Py::new(py, WeekHandle::new(dumps_of(&body)?)?)?;
        if occurrences.is_instance_of::<pyo3::types::PyTuple>()
            && waiting.is_instance_of::<pyo3::types::PyTuple>()
        {
            kept.set_item("_engine_week", &handle)?;
        }
        Ok(handle.into_any())
    })
}

/// Records what the window last passed for the 24-hour clock in `state` (the caller's own record,
/// compared as the object it was, not its truth), tells the engine, and says whether it changed.
#[pyfunction]
fn week_set_clock(on: &Bound<'_, PyAny>, state: &Bound<'_, PyAny>) -> PyResult<bool> {
    guard(|| {
        let changed = state.get_item("24h")?.ne(on)?;
        state.set_item("24h", on)?;
        weekmodel::set_clock_24h(on.is_truthy()?);
        Ok(changed)
    })
}
