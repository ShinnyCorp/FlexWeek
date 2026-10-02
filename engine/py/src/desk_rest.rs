//! Bindings for the rest of the Qt-free desktop modules.

use std::collections::HashSet;

use std::cell::RefCell;

use ::flexweek_engine::desk::{calendar, clipboard, custom_look, files, focus, reuse, update};
use ::flexweek_engine::{EngineError, EngineResult};
use pyo3::prelude::*;
use serde_json::{Map, Value};

use crate::desk::{dump, maps_of, object_map, objects, parse};
use crate::guard;

fn opt_value(text: Option<&str>) -> PyResult<Option<Value>> {
    match text {
        Some(text) => Ok(Some(parse(text)?)),
        None => Ok(None),
    }
}

fn opt_map(text: Option<&str>) -> PyResult<Option<Map<String, Value>>> {
    match text {
        Some(text) => Ok(Some(object_map(text)?)),
        None => Ok(None),
    }
}

fn id_set(text: Option<&str>) -> PyResult<Option<HashSet<String>>> {
    let Some(text) = text else {
        return Ok(None);
    };
    Ok(Some(
        objects(text)?
            .into_iter()
            .filter_map(|item| item.as_str().map(str::to_string))
            .collect(),
    ))
}

fn array(items: Vec<Value>) -> String {
    dump(&Value::Array(items))
}

fn maps(items: Vec<Map<String, Value>>) -> String {
    array(items.into_iter().map(Value::Object).collect())
}

#[pyfunction]
fn calendar_category_title(category: Option<&str>) -> PyResult<String> {
    guard(|| Ok(calendar::category_title(category).to_string()))
}

#[pyfunction]
fn calendar_is_series(block: &str) -> PyResult<bool> {
    let block = parse(block)?;
    guard(|| Ok(calendar::is_series(&block)))
}

#[pyfunction]
fn calendar_monday_of(iso_day: &str) -> PyResult<String> {
    guard(|| Ok(calendar::monday_of(iso_day)))
}

#[pyfunction]
fn calendar_date_for_day(week_start: &str, day: i64) -> PyResult<String> {
    guard(|| Ok(calendar::date_for_day(week_start, day)))
}

#[pyfunction]
fn calendar_sunday_due(week_start: &str) -> PyResult<String> {
    guard(|| Ok(calendar::sunday_due(week_start)))
}

#[pyfunction]
fn calendar_local_stamp(stamp: &str) -> PyResult<String> {
    guard(|| Ok(calendar::local_stamp(Some(stamp))))
}

#[pyfunction]
fn calendar_occupied(blocks: &str, day: i64) -> PyResult<Vec<(i64, i64)>> {
    let blocks = objects(blocks)?;
    guard(|| Ok(calendar::occupied_intervals(&blocks, day)))
}

#[pyfunction]
fn calendar_click_range(begin: i64, occupied: Vec<(i64, i64)>) -> PyResult<Option<(i64, i64)>> {
    guard(|| Ok(calendar::create_click_range(begin, &occupied)))
}

#[pyfunction]
fn calendar_apply_times(
    block: &str,
    start_min: i64,
    end_min: i64,
    day: Option<i64>,
) -> PyResult<Option<String>> {
    let block = parse(block)?;
    guard(|| {
        Ok(calendar::apply_block_times(&block, start_min, end_min, day).map(|value| dump(&value)))
    })
}

#[pyfunction]
fn calendar_split(
    blocks: &str,
    block_id: &str,
    day: i64,
    new_id: &str,
) -> PyResult<(String, Option<String>)> {
    let blocks = objects(blocks)?;
    guard(|| {
        let (out, made) = calendar::split_occurrence(&blocks, block_id, day, new_id);
        Ok((array(out), made))
    })
}

#[pyfunction]
fn calendar_delete(blocks: &str, block_id: &str, day: Option<i64>) -> PyResult<String> {
    let blocks = objects(blocks)?;
    guard(|| Ok(array(calendar::delete_occurrence(&blocks, block_id, day))))
}

#[pyfunction]
fn calendar_apply_edit(
    blocks: &str,
    block: &str,
    scope: &str,
    day: Option<i64>,
    new_id: &str,
) -> PyResult<String> {
    let blocks = objects(blocks)?;
    let block = parse(block)?;
    guard(|| {
        Ok(array(calendar::apply_block_edit(
            &blocks, &block, scope, day, new_id,
        )))
    })
}

#[pyfunction]
fn calendar_relocate(
    source: &str,
    block_id: &str,
    from_day: i64,
    to_day: i64,
    dest: Option<&str>,
    new_id: &str,
) -> PyResult<Option<(String, Option<String>, String)>> {
    let source = objects(source)?;
    let dest = dest.map(objects).transpose()?;
    guard(|| {
        Ok(
            calendar::relocate_block(&source, block_id, from_day, to_day, dest.as_deref(), new_id)
                .map(|(source_out, dest_out, made)| (array(source_out), dest_out.map(array), made)),
        )
    })
}

#[pyfunction]
fn calendar_first_day(week_start: &str, today_iso: &str) -> PyResult<i64> {
    guard(|| Ok(calendar::first_plannable_day(week_start, today_iso)))
}

#[pyfunction]
fn calendar_due_day(due: Option<&str>, week_start: &str) -> PyResult<Option<i64>> {
    guard(|| Ok(calendar::due_day_in_week(due, week_start)))
}

#[pyfunction]
fn calendar_days_through(due_day: Option<i64>, first_day: i64) -> PyResult<Vec<i64>> {
    guard(|| Ok(calendar::days_through(due_day, first_day)))
}

#[pyfunction]
fn calendar_month_for_view(iso_day: &str) -> PyResult<String> {
    guard(|| Ok(calendar::month_for_view(iso_day)))
}

#[pyfunction]
fn calendar_shifted_month(month: &str, amount: i64) -> PyResult<Option<String>> {
    guard(|| Ok(calendar::shifted_month(month, amount)))
}

#[pyfunction]
fn calendar_month_anchor(selected_month: &str, today: &str) -> PyResult<String> {
    guard(|| Ok(calendar::month_anchor_date(selected_month, today)))
}

#[pyfunction]
fn calendar_due_soon(iso_day: &str, assignments: &str) -> PyResult<String> {
    let assignments = object_map(assignments)?;
    guard(|| Ok(array(calendar::due_soon_for(iso_day, &assignments))))
}

#[pyfunction]
fn calendar_placement(block: &str, day: i64, trace: Option<&str>) -> PyResult<String> {
    let block = parse(block)?;
    let trace = opt_value(trace)?;
    guard(|| {
        Ok(match calendar::placement_on(&block, day, trace.as_ref()) {
            calendar::PlacementOn::NotToday => "not_today".to_string(),
            calendar::PlacementOn::None => "none".to_string(),
            calendar::PlacementOn::Time(start) => format!("time:{start}"),
        })
    })
}

#[pyfunction]
fn calendar_agenda(
    week_start: &str,
    iso_day: &str,
    blocks: &str,
    assignments: &str,
    trace: Option<&str>,
    day_data: Option<&str>,
) -> PyResult<String> {
    let blocks = objects(blocks)?;
    let assignments = object_map(assignments)?;
    let trace = opt_value(trace)?;
    let day_data = opt_value(day_data)?;
    guard(|| {
        Ok(dump(&calendar::agenda_for(
            week_start,
            iso_day,
            &blocks,
            &assignments,
            trace.as_ref(),
            day_data.as_ref(),
        )))
    })
}

#[pyfunction]
fn calendar_next_action(
    sessions: &str,
    due_soon: &str,
    assignments: &str,
    day_data: Option<&str>,
) -> PyResult<String> {
    let sessions = objects(sessions)?;
    let due_soon = objects(due_soon)?;
    let assignments = object_map(assignments)?;
    let day_data = opt_value(day_data)?;
    guard(|| {
        Ok(dump(&calendar::next_action_for(
            &sessions,
            &due_soon,
            &assignments,
            day_data.as_ref(),
        )))
    })
}

#[pyfunction]
fn calendar_setup_block(block: &str) -> PyResult<bool> {
    let block = parse(block)?;
    guard(|| Ok(calendar::is_setup_block(&block)))
}

#[pyfunction]
fn calendar_span_problem(
    day: i64,
    start_min: i64,
    end_min: i64,
    due_day: Option<i64>,
    due_minute: Option<i64>,
) -> PyResult<Option<String>> {
    let due = match (due_day, due_minute) {
        (Some(day), Some(minute)) => Some((day, minute)),
        _ => None,
    };
    guard(|| Ok(calendar::span_problem(&[], "", day, start_min, end_min, due).map(str::to_string)))
}

#[pyfunction]
fn calendar_span_clash(
    blocks: &str,
    block_id: &str,
    day: i64,
    start_min: i64,
    end_min: i64,
) -> PyResult<Option<String>> {
    let blocks = objects(blocks)?;
    guard(|| {
        Ok(calendar::span_clash(
            &blocks, block_id, day, start_min, end_min,
        ))
    })
}

#[pyfunction]
fn calendar_category_icon(category: Option<&str>) -> PyResult<Option<String>> {
    guard(|| Ok(calendar::category_icon(category).map(str::to_string)))
}

#[pyfunction]
fn focus_phase_ms(phase: &str, prefs: Option<&str>) -> PyResult<i64> {
    let prefs = opt_map(prefs)?;
    guard(|| Ok(focus::phase_duration_ms(phase, prefs.as_ref())))
}

#[pyfunction]
fn focus_countdown(milliseconds: i64) -> PyResult<String> {
    guard(|| Ok(focus::format_countdown(milliseconds)))
}

#[pyfunction]
fn focus_remaining(state: &str, now_ms: i64) -> PyResult<i64> {
    let state = object_map(state)?;
    guard(|| Ok(focus::remaining_ms(&state, now_ms)))
}

#[pyfunction]
fn focus_now(state: Option<&str>) -> PyResult<String> {
    let state = opt_map(state)?;
    guard(|| Ok(focus::focus_now(state.as_ref()).to_string()))
}

#[pyfunction]
fn focus_more_time(estimate_min: i64) -> PyResult<Vec<i64>> {
    guard(|| Ok(focus::more_time_choices(estimate_min)))
}

#[pyfunction]
fn focus_persist(state: Option<&str>) -> PyResult<Option<String>> {
    let state = opt_map(state)?;
    guard(|| Ok(focus::persist_payload(state.as_ref()).map(|value| dump(&value))))
}

#[pyfunction]
fn focus_restore(
    saved: Option<&str>,
    assignments: &str,
    blocks: &str,
    now_ms: i64,
) -> PyResult<Option<String>> {
    let saved = opt_value(saved)?;
    let assignments = object_map(assignments)?;
    let blocks = objects(blocks)?;
    guard(|| {
        Ok(
            focus::restore_state(saved.as_ref(), &assignments, &blocks, now_ms)
                .map(|state| dump(&Value::Object(state))),
        )
    })
}

#[pyfunction]
fn focus_begin(target: &str, prefs: Option<&str>, now_ms: i64) -> PyResult<String> {
    let target = object_map(target)?;
    let prefs = opt_map(prefs)?;
    guard(|| {
        Ok(dump(&Value::Object(focus::begin_state(
            target,
            prefs.as_ref(),
            now_ms,
        ))))
    })
}

#[pyfunction]
fn focus_pause(state: &str, now_ms: i64) -> PyResult<String> {
    let state = object_map(state)?;
    guard(|| Ok(dump(&Value::Object(focus::pause_state(&state, now_ms)))))
}

#[pyfunction]
fn focus_set_phase(state: &str, phase: &str, prefs: Option<&str>, now_ms: i64) -> PyResult<String> {
    let state = object_map(state)?;
    let prefs = opt_map(prefs)?;
    guard(|| {
        Ok(dump(&Value::Object(focus::set_phase(
            &state,
            phase,
            prefs.as_ref(),
            now_ms,
        ))))
    })
}

#[pyfunction]
fn focus_break_phase(cycles: i64, prefs: Option<&str>) -> PyResult<String> {
    let prefs = opt_map(prefs)?;
    guard(|| Ok(focus::break_phase(cycles, prefs.as_ref()).to_string()))
}

#[pyfunction]
fn focus_credit(
    state: &str,
    assignment: Option<&str>,
    block: Option<&str>,
    work_min: i64,
) -> PyResult<Option<String>> {
    let state = object_map(state)?;
    let assignment = opt_value(assignment)?;
    let block = opt_value(block)?;
    guard(|| {
        Ok(
            focus::credit_target(&state, assignment.as_ref(), block.as_ref(), work_min)
                .map(|value| dump(&value)),
        )
    })
}

#[pyfunction]
fn focus_candidates(blocks: &str, assignments: &str, trace: Option<&str>) -> PyResult<String> {
    let blocks = objects(blocks)?;
    let assignments = object_map(assignments)?;
    let trace = opt_value(trace)?;
    guard(|| {
        Ok(array(focus::focus_candidates(
            &blocks,
            &assignments,
            trace.as_ref(),
        )))
    })
}

#[pyfunction]
fn focus_now_next(blocks: &str, day: i64, minute: i64) -> PyResult<String> {
    let blocks = objects(blocks)?;
    guard(|| {
        Ok(dump(&Value::Object(focus::now_and_next(
            &blocks, day, minute,
        ))))
    })
}

#[pyfunction]
fn focus_now_next_line(result: &str, minute: i64) -> PyResult<String> {
    let result = object_map(result)?;
    guard(|| Ok(focus::now_next_line(&result, minute)))
}

#[pyfunction]
fn reuse_restore_label(text: &str) -> PyResult<String> {
    guard(|| Ok(reuse::restore_point_label(text)))
}

#[pyfunction]
fn reuse_week_label(week_start: &str) -> PyResult<String> {
    guard(|| Ok(reuse::week_label(week_start)))
}

#[pyfunction]
fn reuse_floor_slot(minutes: i64) -> PyResult<i64> {
    guard(|| Ok(reuse::floor_slot(minutes)))
}

#[pyfunction]
fn reuse_homework(block: &str) -> PyResult<bool> {
    let block = parse(block)?;
    guard(|| Ok(reuse::is_homework_session(&block)))
}

#[pyfunction]
fn reuse_session_days(week_start: &str, due: &str) -> PyResult<Vec<i64>> {
    guard(|| Ok(reuse::session_days(week_start, due)))
}

#[pyfunction]
fn reuse_planned(block: &str) -> PyResult<bool> {
    let block = parse(block)?;
    guard(|| Ok(reuse::is_planned(&block)))
}

#[pyfunction]
fn reuse_planning_days(block: &str, assignments: &str, week_start: &str) -> PyResult<Vec<i64>> {
    let block = parse(block)?;
    let assignments = object_map(assignments)?;
    guard(|| Ok(reuse::planning_days(&block, &assignments, week_start)))
}

#[pyfunction]
fn reuse_apply_plan(
    blocks: &str,
    trace: Option<&str>,
    targets: Option<&str>,
    assignments: Option<&str>,
    week_start: Option<&str>,
) -> PyResult<String> {
    let blocks = objects(blocks)?;
    let trace = opt_value(trace)?;
    let targets = id_set(targets)?;
    let assignments = opt_map(assignments)?;
    guard(|| {
        Ok(array(reuse::apply_plan(
            &blocks,
            trace.as_ref(),
            targets.as_ref(),
            assignments.as_ref(),
            week_start,
        )))
    })
}

#[pyfunction]
fn reuse_clear_pins(blocks: &str) -> PyResult<String> {
    let blocks = objects(blocks)?;
    guard(|| Ok(array(reuse::clear_stale_pins(&blocks))))
}

#[pyfunction]
fn reuse_held(block: &str) -> PyResult<String> {
    let block = parse(block)?;
    guard(|| Ok(dump(&reuse::held_in_place(&block))))
}

#[pyfunction]
fn reuse_plan_start(
    week_start: &str,
    now_iso: &str,
    now_minute: i64,
    now_has_subminute: bool,
) -> PyResult<Option<(i64, i64)>> {
    guard(|| {
        Ok(reuse::plan_start(
            week_start,
            now_iso,
            now_minute,
            now_has_subminute,
        ))
    })
}

#[pyfunction]
fn reuse_occurrence_days(block: &str) -> PyResult<Vec<i64>> {
    let block = parse(block)?;
    guard(|| Ok(reuse::occurrence_days(&block)))
}

#[pyfunction]
fn reuse_session_minutes(blocks: &str, assignment_id: &str) -> PyResult<i64> {
    let blocks = objects(blocks)?;
    guard(|| reuse::session_minutes(&blocks, &Value::from(assignment_id)).map_err(crate::raise))
}

#[pyfunction]
fn reuse_available_minutes(
    assignment: Option<&str>,
    blocks: &str,
    committed: Option<&str>,
) -> PyResult<i64> {
    let assignment = opt_value(assignment)?;
    let blocks = objects(blocks)?;
    let committed = committed.map(objects).transpose()?;
    guard(|| {
        reuse::available_homework_minutes(assignment.as_ref(), &blocks, committed.as_deref())
            .map_err(crate::raise)
    })
}

#[pyfunction]
fn reuse_capacity(existing_count: i64, added_count: i64, label: &str) -> PyResult<String> {
    guard(|| Ok(reuse::capacity_problem(existing_count, added_count, label)))
}

#[pyfunction]
fn reuse_overlap(start_a: i64, end_a: i64, start_b: i64, end_b: i64) -> PyResult<bool> {
    guard(|| Ok(reuse::intervals_overlap(start_a, end_a, start_b, end_b)))
}

#[pyfunction]
fn reuse_late_from(minute: i64) -> PyResult<String> {
    guard(|| Ok(reuse::late_from_start(minute)))
}

#[pyfunction]
fn reuse_late_block(day: i64, from_start: &str, minutes: i64, block_id: &str) -> PyResult<String> {
    guard(|| {
        Ok(dump(&reuse::running_late_block(
            day, from_start, minutes, block_id,
        )))
    })
}

#[pyfunction]
fn reuse_late_refusal(
    week_start: &str,
    today_iso: &str,
    dirty: bool,
    conflict: bool,
    block_count: i64,
) -> PyResult<Option<String>> {
    guard(|| {
        Ok(
            reuse::running_late_refusal(week_start, today_iso, dirty, conflict, block_count)
                .map(str::to_string),
        )
    })
}

#[pyfunction]
fn reuse_late_line(block: &str, moved: i64) -> PyResult<String> {
    let block = parse(block)?;
    guard(|| Ok(reuse::late_locked_line(&block, moved)))
}

#[pyfunction]
fn reuse_late_id(operation_id: &str) -> PyResult<String> {
    guard(|| Ok(reuse::late_id(operation_id)))
}

#[pyfunction]
fn reuse_copy_label(block: &str, source_day: i64, scope: &str) -> PyResult<String> {
    let block = parse(block)?;
    guard(|| Ok(reuse::copy_label(&block, source_day, scope)))
}

#[pyfunction]
fn reuse_due_point(due: Option<&str>, week_start: &str) -> PyResult<Option<(i64, i64)>> {
    guard(|| {
        Ok(reuse::due_point(
            due.filter(|text| !text.is_empty()),
            week_start,
        ))
    })
}

#[pyfunction]
fn reuse_copied_fixed(source: &str, days: &str, block_id: &str) -> PyResult<String> {
    let source = parse(source)?;
    let days = objects(days)?;
    let days: Vec<i64> = days.into_iter().filter_map(|item| item.as_i64()).collect();
    guard(|| {
        let block = reuse::copied_fixed_block(&source, &days, block_id).map_err(crate::raise)?;
        Ok(dump(&block))
    })
}

#[pyfunction]
fn reuse_copied_homework(
    assignment: &str,
    day: i64,
    duration: i64,
    block_id: &str,
) -> PyResult<String> {
    let assignment = parse(assignment)?;
    guard(|| {
        let block = reuse::copied_homework_block(&assignment, day, duration, block_id)
            .map_err(crate::raise)?;
        Ok(dump(&block))
    })
}

#[pyfunction]
fn reuse_clipboard_item(
    block: &str,
    source_day: i64,
    scope: &str,
    group_id: &str,
) -> PyResult<String> {
    let block = parse(block)?;
    guard(|| {
        Ok(dump(&reuse::clipboard_item(
            &block, source_day, scope, group_id,
        )))
    })
}

#[pyfunction]
fn reuse_fingerprint(items: &str) -> PyResult<String> {
    let items = objects(items)?;
    guard(|| Ok(reuse::clipboard_fingerprint(&items)))
}

#[pyfunction]
fn reuse_occurs(block: &str, day: i64, placed: Option<&str>) -> PyResult<bool> {
    let block = parse(block)?;
    let placed = placed.map(objects).transpose()?;
    guard(|| Ok(reuse::block_occurs_on_day(&block, day, placed.as_deref())))
}

#[pyfunction]
fn reuse_row_conflict(
    row: &str,
    rows: &str,
    existing: &str,
    skip: Option<i64>,
) -> PyResult<Option<String>> {
    let row = parse(row)?;
    let rows = objects(rows)?;
    let existing = objects(existing)?;
    let skip = skip.and_then(|index| usize::try_from(index).ok());
    guard(|| {
        let conflict =
            clipboard::row_conflict(&row, &rows, &existing, skip).map_err(crate::raise)?;
        Ok(conflict.map(|title| match title {
            Value::String(text) => text,
            other => other.to_string(),
        }))
    })
}

#[pyfunction]
fn reuse_preview_message(
    row: &str,
    rows: &str,
    existing: &str,
    skip: Option<i64>,
) -> PyResult<String> {
    let row = parse(row)?;
    let rows = objects(rows)?;
    let existing = objects(existing)?;
    let skip = skip.and_then(|index| usize::try_from(index).ok());
    guard(|| {
        clipboard::preview_conflict_message(&row, &rows, &existing, skip).map_err(crate::raise)
    })
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn reuse_proposals(
    items: &str,
    kind: &str,
    week_start: &str,
    target_day: i64,
    target_start: Option<&str>,
    assignments: &str,
    available: &str,
) -> PyResult<String> {
    let items = objects(items)?;
    let assignments = object_map(assignments)?;
    let available = object_map(available)?;
    guard(|| {
        let rows = clipboard::proposals_from_clipboard(
            &items,
            kind,
            week_start,
            target_day,
            target_start,
            &assignments,
            &available,
        )
        .map_err(crate::raise)?;
        Ok(dump(&Value::Array(rows)))
    })
}

#[pyfunction]
fn reuse_merge_rows(rows: &str, operation_id: &str) -> PyResult<String> {
    let rows = objects(rows)?;
    guard(|| {
        let merged = clipboard::merge_preview_rows(&rows, operation_id).map_err(crate::raise)?;
        Ok(dump(&Value::Array(merged)))
    })
}

#[pyfunction]
fn reuse_routine_sources(blocks: &str) -> PyResult<String> {
    let blocks = objects(blocks)?;
    guard(|| {
        let kept = clipboard::routine_source_blocks(&blocks).map_err(crate::raise)?;
        Ok(dump(&Value::Array(kept)))
    })
}

#[pyfunction]
fn reuse_routine_template(block: &str, template_id: &str) -> PyResult<String> {
    let block = parse(block)?;
    guard(|| {
        let body = clipboard::routine_template(&block, template_id).map_err(crate::raise)?;
        Ok(dump(&body))
    })
}

#[pyfunction]
fn reuse_routine_rows(routine: &str, week_start: &str, allowed_days: &str) -> PyResult<String> {
    let routine = parse(routine)?;
    let allowed = objects(allowed_days)?;
    guard(|| {
        let rows = clipboard::routine_rows(&routine, week_start, &allowed).map_err(crate::raise)?;
        Ok(dump(&Value::Array(rows)))
    })
}

#[pyfunction]
fn reuse_unfinished(
    assignments: &str,
    saved_weeks: &str,
    week_start: &str,
    blocks: &str,
    committed: &str,
) -> PyResult<String> {
    let assignments = object_map(assignments)?;
    let saved = objects(saved_weeks)?;
    let blocks = objects(blocks)?;
    let committed = objects(committed)?;
    guard(|| {
        let items =
            clipboard::unfinished_items(&assignments, &saved, week_start, &blocks, &committed)
                .map_err(crate::raise)?;
        Ok(dump(&Value::Array(items)))
    })
}

/// `today()` is the caller's local date as an ISO string; a Python error from it is raised as it
/// came.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn reuse_planner_title(
    week_start: &str,
    session_day: Option<&str>,
    session_month: Option<&str>,
    view: &str,
    short: bool,
    selected_day: Option<&str>,
    today: &Bound<'_, PyAny>,
) -> PyResult<String> {
    let failure: RefCell<Option<PyErr>> = RefCell::new(None);
    let mut local_date = || -> EngineResult<String> {
        today
            .call0()
            .and_then(|value| value.extract::<String>())
            .map_err(|error| {
                *failure.borrow_mut() = Some(error);
                EngineError::value("local date")
            })
    };
    let outcome = guard(|| {
        Ok(reuse::planner_title(
            week_start,
            session_day,
            session_month,
            view,
            short,
            selected_day,
            &mut local_date,
        ))
    })?;
    match failure.into_inner() {
        Some(error) => Err(error),
        None => outcome.map_err(crate::raise),
    }
}

#[pyfunction]
fn files_export_input(block: &str, assignments: Vec<String>) -> PyResult<String> {
    let block = parse(block)?;
    guard(|| {
        let copy = files::export_input(&block, &assignments).map_err(crate::raise)?;
        Ok(dump(&copy))
    })
}

/// The ids, and the error that stopped the list, as an exception for Python to raise once it has
/// made the bodies of the ids before it.
#[pyfunction]
fn files_referenced_ids(
    py: Python<'_>,
    blocks: &str,
    assignments: Vec<String>,
) -> PyResult<(Vec<String>, Option<Py<PyAny>>)> {
    let blocks = objects(blocks)?;
    guard(|| {
        let (ids, failure) = files::referenced_ids(&blocks, &assignments).map_err(crate::raise)?;
        Ok((
            ids,
            failure.map(|error| crate::raise(error).into_value(py).into_any()),
        ))
    })
}

#[pyfunction]
fn files_assignment_input(item: &str, fields: Vec<String>) -> PyResult<String> {
    let item = parse(item)?;
    guard(|| {
        let body = files::assignment_input(&item, &fields).map_err(crate::raise)?;
        Ok(dump(&body))
    })
}

#[pyfunction]
fn files_export_week(week_start: &str, blocks: &str, assignments: &str) -> PyResult<String> {
    let blocks = objects(blocks)?;
    let assignments = object_map(assignments)?;
    guard(|| {
        Ok(dump(&files::export_week_payload(
            week_start,
            &blocks,
            &assignments,
        )))
    })
}

#[pyfunction]
fn files_export_day(
    week_start: &str,
    day: i64,
    blocks: &str,
    assignments: &str,
) -> PyResult<String> {
    let blocks = objects(blocks)?;
    let assignments = object_map(assignments)?;
    guard(|| {
        Ok(dump(&files::export_day_payload(
            week_start,
            day,
            &blocks,
            &assignments,
        )))
    })
}

#[pyfunction]
fn files_parse_import(raw: &str) -> PyResult<String> {
    guard(|| Ok(dump(&files::parse_import_payload(raw))))
}

#[pyfunction]
fn files_occurrence_id(day: i64, block_id: &str) -> PyResult<String> {
    guard(|| Ok(files::occurrence_import_id(day, block_id)))
}

#[pyfunction]
fn files_plan_homework(
    homework: &str,
    blocks: &str,
    week_start: &str,
    assignments: &str,
) -> PyResult<String> {
    let homework = objects(homework)?;
    let blocks = objects(blocks)?;
    let assignments = object_map(assignments)?;
    guard(|| {
        Ok(dump(&files::plan_imported_homework(
            &homework,
            &blocks,
            week_start,
            &assignments,
        )))
    })
}

#[pyfunction]
fn files_merge(existing: &str, incoming: &str, mode: &str, day: Option<i64>) -> PyResult<String> {
    let existing = objects(existing)?;
    let incoming = objects(incoming)?;
    guard(|| {
        files::merge_imported_blocks(&existing, &incoming, mode, day)
            .map(array)
            .map_err(crate::raise)
    })
}

#[pyfunction]
fn update_release_from_page(location: &str) -> PyResult<Option<String>> {
    guard(|| Ok(update::release_from_page(location).map(|value| dump(&value))))
}

#[pyfunction]
fn update_expected_digest(checksum_text: &str, asset: &str) -> PyResult<Option<String>> {
    guard(|| Ok(update::expected_digest(checksum_text, asset)))
}

#[pyfunction]
fn update_sanitize(raw: &str) -> PyResult<String> {
    let raw = parse(raw)?;
    guard(|| Ok(dump(&Value::Object(update::sanitize_updates(&raw)))))
}

#[pyfunction]
fn update_due(settings: &str, now_ms: i64) -> PyResult<bool> {
    let settings = object_map(settings)?;
    guard(|| Ok(update::due_for_check(&settings, now_ms)))
}

#[pyfunction]
fn look_saved(raw: &str) -> PyResult<String> {
    let raw = parse(raw)?;
    guard(|| {
        custom_look::sanitize_saved(&raw)
            .map(maps)
            .map_err(crate::raise)
    })
}

#[pyfunction]
fn look_save(saved: &str, custom: &str, name: &str) -> PyResult<String> {
    let saved = maps_of(saved)?;
    let custom = object_map(custom)?;
    guard(|| {
        custom_look::save_look(&saved, &custom, name)
            .map(maps)
            .map_err(crate::raise)
    })
}

#[pyfunction]
fn look_reset(custom: &str) -> PyResult<String> {
    let custom = object_map(custom)?;
    guard(|| Ok(dump(&Value::Object(custom_look::reset_look(&custom)))))
}

#[pyfunction]
fn look_export(custom: &str) -> PyResult<String> {
    let custom = parse(custom)?;
    guard(|| Ok(custom_look::export_look(&custom)))
}

#[pyfunction]
fn look_import(size: usize, raw: Option<&str>) -> PyResult<(Option<String>, Vec<String>)> {
    let raw = raw.map(parse).transpose()?;
    guard(|| {
        let imported = custom_look::import_look(size, raw.as_ref());
        Ok((
            imported.look.map(|look| dump(&Value::Object(look))),
            imported.problems,
        ))
    })
}

#[pyfunction]
fn look_base_of(pack: &str, look: &str) -> PyResult<String> {
    let (pack, look) = (parse(pack)?, parse(look)?);
    guard(|| Ok(dump(&custom_look::base_of(&pack, &look))))
}

#[pyfunction]
fn look_start(pack: &str, look: &str, accent: &str) -> PyResult<String> {
    let (pack, look, accent) = (parse(pack)?, parse(look)?, parse(accent)?);
    guard(|| {
        Ok(dump(&Value::Object(custom_look::start_custom(
            &pack, &look, &accent,
        ))))
    })
}

#[pyfunction]
fn look_wear(look: &str, custom: &str) -> PyResult<String> {
    let (look, custom) = (parse(look)?, parse(custom)?);
    guard(|| Ok(dump(&Value::Object(custom_look::wear(&look, &custom)))))
}

#[pyfunction]
fn look_name(name: Option<&str>) -> PyResult<String> {
    guard(|| custom_look::name_valid(name).map_err(crate::raise))
}

#[pyfunction]
fn look_find(saved: &str, name: &str) -> PyResult<i64> {
    let saved = objects(saved)?;
    guard(|| {
        let at = custom_look::find_index_of(&saved, name).map_err(crate::raise)?;
        Ok(at.map_or(-1, |index| index as i64))
    })
}

#[pyfunction]
fn look_tables() -> PyResult<String> {
    guard(|| Ok(dump(&custom_look::tables())))
}

#[pyfunction]
fn look_readability(custom: &str, palette: &str, blocks: &str) -> PyResult<String> {
    let custom = object_map(custom)?;
    let palette_map = object_map(palette)?;
    let text_of = |key: &str| {
        palette_map
            .get(key)
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string()
    };
    let palette = custom_look::ReadabilityPalette {
        window: text_of("window"),
        panel: text_of("panel"),
        grid: text_of("grid"),
        text: text_of("text"),
        muted: text_of("muted"),
        accent: text_of("accent"),
        accent_ink: text_of("accent_ink"),
    };
    let filled = objects(blocks)?
        .into_iter()
        .filter_map(|item| {
            let obj = item.as_object()?;
            Some(custom_look::BlockInk {
                key: obj.get("key")?.as_str()?.to_string(),
                label: obj.get("label")?.as_str()?.to_string(),
                fill: obj.get("fill")?.as_str()?.to_string(),
                ink: obj.get("ink")?.as_str()?.to_string(),
            })
        })
        .collect::<Vec<_>>();
    guard(|| {
        let found = custom_look::readability(&custom, &palette, &filled);
        Ok(array(
            found
                .into_iter()
                .map(|problem| {
                    serde_json::json!({
                        "words": problem.words,
                        "ink": problem.ink,
                        "ground": problem.ground,
                        "ratio": problem.ratio,
                        "field": problem.field,
                        "fixed": problem.fixed,
                    })
                })
                .collect(),
        ))
    })
}

#[pyfunction]
fn look_apply_fix(custom: &str, problem: &str) -> PyResult<String> {
    let custom = object_map(custom)?;
    let problem = object_map(problem)?;
    let field = problem
        .get("field")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default();
    let problem = custom_look::ReadabilityProblem {
        words: problem
            .get("words")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        ink: problem
            .get("ink")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        ground: problem
            .get("ground")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        ratio: problem.get("ratio").and_then(Value::as_f64).unwrap_or(0.0),
        field,
        fixed: problem
            .get("fixed")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
    };
    guard(|| {
        Ok(dump(&Value::Object(custom_look::apply_fix(
            &custom, &problem,
        ))))
    })
}

pub fn add(module: &Bound<'_, PyModule>) -> PyResult<()> {
    crate::export!(
        module,
        calendar_category_title,
        calendar_is_series,
        calendar_monday_of,
        calendar_date_for_day,
        calendar_sunday_due,
        calendar_local_stamp,
        calendar_occupied,
        calendar_click_range,
        calendar_apply_times,
        calendar_split,
        calendar_delete,
        calendar_apply_edit,
        calendar_relocate,
        calendar_first_day,
        calendar_due_day,
        calendar_days_through,
        calendar_month_for_view,
        calendar_shifted_month,
        calendar_month_anchor,
        calendar_due_soon,
        calendar_placement,
        calendar_agenda,
        calendar_next_action,
        calendar_setup_block,
        calendar_span_problem,
        calendar_span_clash,
        calendar_category_icon,
        focus_phase_ms,
        focus_countdown,
        focus_remaining,
        focus_now,
        focus_more_time,
        focus_persist,
        focus_restore,
        focus_begin,
        focus_pause,
        focus_set_phase,
        focus_break_phase,
        focus_credit,
        focus_candidates,
        focus_now_next,
        focus_now_next_line,
        reuse_restore_label,
        reuse_week_label,
        reuse_floor_slot,
        reuse_homework,
        reuse_session_days,
        reuse_planned,
        reuse_planning_days,
        reuse_apply_plan,
        reuse_clear_pins,
        reuse_held,
        reuse_plan_start,
        reuse_occurrence_days,
        reuse_session_minutes,
        reuse_available_minutes,
        reuse_capacity,
        reuse_overlap,
        reuse_late_from,
        reuse_late_block,
        reuse_late_refusal,
        reuse_late_line,
        reuse_late_id,
        reuse_copy_label,
        reuse_due_point,
        reuse_copied_fixed,
        reuse_copied_homework,
        reuse_clipboard_item,
        reuse_fingerprint,
        reuse_occurs,
        reuse_row_conflict,
        reuse_preview_message,
        reuse_proposals,
        reuse_merge_rows,
        reuse_routine_sources,
        reuse_routine_template,
        reuse_routine_rows,
        reuse_unfinished,
        reuse_planner_title,
        files_export_input,
        files_referenced_ids,
        files_assignment_input,
        files_export_week,
        files_export_day,
        files_parse_import,
        files_occurrence_id,
        files_plan_homework,
        files_merge,
        update_release_from_page,
        update_expected_digest,
        update_sanitize,
        update_due,
        look_saved,
        look_save,
        look_reset,
        look_export,
        look_import,
        look_base_of,
        look_start,
        look_wear,
        look_name,
        look_find,
        look_tables,
        look_readability,
        look_apply_fix,
    );
    Ok(())
}
