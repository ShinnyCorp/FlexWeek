//! Bindings for the rest of the Qt-free desktop modules.

use std::cell::RefCell;

use ::flexweek_engine::desk::{
    calendar, clipboard, custom_look, files, focus, grid, planning, reuse, update,
};
use ::flexweek_engine::{EngineError, EngineResult};
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;
use serde_json::{Map, Value, json};

use crate::desk::{dump, dumps_of, fresh_id, object_map, objects, parse};
use crate::guard;

fn opt_value(text: Option<&str>) -> PyResult<Option<Value>> {
    match text {
        Some(text) => Ok(Some(parse(text)?)),
        None => Ok(None),
    }
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
    guard(|| calendar::is_series_checked(&block).map_err(crate::raise))
}

#[pyfunction]
fn calendar_monday_of(iso_day: &str) -> PyResult<String> {
    guard(|| grid::monday_of(iso_day).map_err(crate::raise))
}

#[pyfunction]
fn calendar_date_for_day(week_start: &str, day: &str) -> PyResult<String> {
    let day = parse(day)?;
    guard(|| grid::date_for_day(week_start, &day).map_err(crate::raise))
}

#[pyfunction]
fn calendar_sunday_due(week_start: &str) -> PyResult<String> {
    guard(|| grid::sunday_due(week_start).map_err(crate::raise))
}

#[pyfunction]
fn calendar_local_stamp(stamp: &str) -> PyResult<String> {
    guard(|| Ok(calendar::local_stamp(Some(stamp))))
}

#[pyfunction]
fn calendar_occupied(blocks: &str, day: &str) -> PyResult<String> {
    let (blocks, day) = (parse(blocks)?, parse(day)?);
    guard(|| {
        let found = grid::occupied_intervals(&blocks, &day).map_err(crate::raise)?;
        Ok(dump(&Value::Array(found)))
    })
}

#[pyfunction]
fn calendar_click_range(begin: i64, occupied: &str) -> PyResult<Option<String>> {
    let occupied = parse(occupied)?;
    guard(|| {
        let found = grid::create_click_range(begin, &occupied).map_err(crate::raise)?;
        Ok(found.map(|span| dump(&span)))
    })
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
        let found =
            grid::apply_block_times(&block, start_min, end_min, day).map_err(crate::raise)?;
        Ok(found.map(|value| dump(&value)))
    })
}

#[pyfunction]
fn calendar_split(
    py: Python<'_>,
    blocks: &str,
    block_id: &str,
    day: &str,
) -> PyResult<(String, Option<String>)> {
    let (blocks, block_id, day) = (parse(blocks)?, parse(block_id)?, parse(day)?);
    guard(|| {
        let (out, made) = grid::split_occurrence(&blocks, &block_id, &day, &mut || fresh_id(py))
            .map_err(crate::raise)?;
        Ok((array(out), made))
    })
}

#[pyfunction]
fn calendar_delete(blocks: &str, block_id: &str, day: &str) -> PyResult<String> {
    let (blocks, block_id, day) = (parse(blocks)?, parse(block_id)?, parse(day)?);
    guard(|| {
        let kept = grid::delete_occurrence(&blocks, &block_id, &day).map_err(crate::raise)?;
        Ok(array(kept))
    })
}

#[pyfunction]
fn calendar_apply_edit(
    py: Python<'_>,
    blocks: &str,
    block: &str,
    scope: &str,
    day: &str,
) -> PyResult<String> {
    let (blocks, block) = (parse(blocks)?, parse(block)?);
    let (scope, day) = (parse(scope)?, parse(day)?);
    guard(|| {
        let edited = grid::apply_block_edit(&blocks, &block, &scope, &day, &mut || fresh_id(py))
            .map_err(crate::raise)?;
        Ok(array(edited))
    })
}

#[pyfunction]
fn calendar_relocate(
    py: Python<'_>,
    source: &str,
    block_id: &str,
    from_day: &str,
    to_day: &str,
    dest: Option<&str>,
) -> PyResult<Option<(String, Option<String>, String)>> {
    let (source, block_id) = (parse(source)?, parse(block_id)?);
    let (from_day, to_day) = (parse(from_day)?, parse(to_day)?);
    let dest = dest.map(parse).transpose()?;
    guard(|| {
        let moved = grid::relocate_block(
            &source,
            &block_id,
            &from_day,
            &to_day,
            dest.as_ref(),
            &mut || fresh_id(py),
        )
        .map_err(crate::raise)?;
        Ok(moved.map(|(source_out, dest_out, made)| {
            (array(source_out), dest_out.map(array), dump(&made))
        }))
    })
}

#[pyfunction]
fn calendar_first_day(week_start: &str, today_iso: &str) -> PyResult<i64> {
    guard(|| grid::first_plannable_day(week_start, today_iso).map_err(crate::raise))
}

#[pyfunction]
fn calendar_due_day(due: &str, week_start: &str) -> PyResult<Option<i64>> {
    let due = parse(due)?;
    guard(|| grid::due_day_of(&due, week_start).map_err(crate::raise))
}

#[pyfunction]
fn calendar_days_through(due_day: Option<i64>, first_day: i64) -> PyResult<Vec<i64>> {
    guard(|| Ok(calendar::days_through(due_day, first_day)))
}

#[pyfunction]
fn calendar_month_for_view(iso_day: &str) -> PyResult<String> {
    guard(|| Ok(grid::month_for_view(iso_day)))
}

#[pyfunction]
fn calendar_shifted_month(month: &str, amount: i64) -> PyResult<Option<String>> {
    guard(|| grid::shifted_month(month, amount).map_err(crate::raise))
}

#[pyfunction]
fn calendar_month_anchor(selected_month: &str, today: &str) -> PyResult<String> {
    guard(|| Ok(grid::month_anchor_date(selected_month, today)))
}

#[pyfunction]
fn calendar_due_soon(iso_day: &str, assignments: &str) -> PyResult<String> {
    let assignments = parse(assignments)?;
    guard(|| {
        let found = grid::due_soon_for(iso_day, &assignments).map_err(crate::raise)?;
        Ok(array(found))
    })
}

#[pyfunction]
fn calendar_placement(block: &str, day: &str, trace: Option<&str>) -> PyResult<String> {
    let (block, day) = (parse(block)?, parse(day)?);
    let trace = opt_value(trace)?;
    guard(|| {
        let placed = grid::placement_on(&block, &day, trace.as_ref()).map_err(crate::raise)?;
        Ok(match placed {
            grid::Placed::NotToday => json!({"not_today": true}),
            grid::Placed::At(start) => json!({"start": start}),
        }
        .to_string())
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
    let (blocks, assignments) = (parse(blocks)?, parse(assignments)?);
    let trace = opt_value(trace)?;
    let day_data = opt_value(day_data)?;
    guard(|| {
        let agenda = grid::agenda_for(
            week_start,
            iso_day,
            &blocks,
            &assignments,
            trace.as_ref(),
            day_data.as_ref(),
        )
        .map_err(crate::raise)?;
        Ok(dump(&agenda))
    })
}

#[pyfunction]
fn calendar_next_action(
    sessions: &str,
    due_soon: &str,
    assignments: &str,
    day_data: Option<&str>,
) -> PyResult<String> {
    let (sessions, due_soon) = (parse(sessions)?, parse(due_soon)?);
    let assignments = parse(assignments)?;
    let day_data = opt_value(day_data)?;
    guard(|| {
        let action = grid::next_action_for(&sessions, &due_soon, &assignments, day_data.as_ref())
            .map_err(crate::raise)?;
        Ok(dump(&action))
    })
}

#[pyfunction]
fn calendar_setup_block(block: &str) -> PyResult<bool> {
    let block = parse(block)?;
    guard(|| grid::is_setup_block(&block).map_err(crate::raise))
}

#[pyfunction]
fn calendar_span_problem(
    day: i64,
    start_min: i64,
    end_min: i64,
    due: &str,
    due_type: &str,
) -> PyResult<Option<String>> {
    let due = parse(due)?;
    guard(|| {
        let found =
            grid::span_problem(day, start_min, end_min, &due, due_type).map_err(crate::raise)?;
        Ok(found.map(str::to_string))
    })
}

#[pyfunction]
fn calendar_span_clash(
    blocks: &str,
    block_id: &str,
    day: &str,
    start_min: i64,
    end_min: i64,
) -> PyResult<Option<String>> {
    let (blocks, block_id, day) = (parse(blocks)?, parse(block_id)?, parse(day)?);
    guard(|| grid::span_clash(&blocks, &block_id, &day, start_min, end_min).map_err(crate::raise))
}

#[pyfunction]
fn calendar_category_icon(category: Option<&str>) -> PyResult<Option<String>> {
    guard(|| Ok(grid::category_icon(category).map(str::to_string)))
}

#[pyfunction]
fn focus_phase_ms(phase: &str, prefs: &str) -> PyResult<String> {
    let (phase, prefs) = (parse(phase)?, parse(prefs)?);
    guard(|| {
        let found = focus::phase_duration_ms(&phase, &prefs).map_err(crate::raise)?;
        Ok(found.to_string())
    })
}

#[pyfunction]
fn focus_countdown(milliseconds: i64) -> PyResult<String> {
    guard(|| Ok(focus::format_countdown(milliseconds)))
}

#[pyfunction]
fn focus_remaining(state: &str, now_ms: i64) -> PyResult<String> {
    let state = parse(state)?;
    guard(|| {
        Ok(focus::remaining_ms(&state, now_ms)
            .map_err(crate::raise)?
            .to_string())
    })
}

#[pyfunction]
fn focus_now(state: &str) -> PyResult<String> {
    let state = parse(state)?;
    guard(|| Ok(focus::focus_now(&state).map_err(crate::raise)?.to_string()))
}

#[pyfunction]
fn focus_more_time(estimate_min: i64) -> PyResult<Vec<i64>> {
    guard(|| Ok(focus::more_time_choices(estimate_min)))
}

#[pyfunction]
fn focus_persist(state: &str) -> PyResult<Option<String>> {
    let state = parse(state)?;
    guard(|| {
        let payload = focus::persist_payload(&state).map_err(crate::raise)?;
        Ok(payload.map(|value| dump(&value)))
    })
}

#[pyfunction]
fn focus_restore(
    saved: &str,
    assignments: &str,
    blocks: &str,
    now_ms: i64,
) -> PyResult<Option<String>> {
    let (saved, assignments, blocks) = (parse(saved)?, parse(assignments)?, parse(blocks)?);
    guard(|| {
        let state =
            focus::restore_state(&saved, &assignments, &blocks, now_ms).map_err(crate::raise)?;
        Ok(state.map(|value| dump(&value)))
    })
}

#[pyfunction]
fn focus_begin(target: &str, prefs: &str, now_ms: i64) -> PyResult<String> {
    let (target, prefs) = (parse(target)?, parse(prefs)?);
    guard(|| {
        Ok(dump(
            &focus::begin_state(&target, &prefs, now_ms).map_err(crate::raise)?,
        ))
    })
}

#[pyfunction]
fn focus_pause(state: &str, now_ms: i64) -> PyResult<String> {
    let state = parse(state)?;
    guard(|| {
        Ok(dump(
            &focus::pause_state(&state, now_ms).map_err(crate::raise)?,
        ))
    })
}

#[pyfunction]
fn focus_set_phase(state: &str, phase: &str, prefs: &str, now_ms: i64) -> PyResult<String> {
    let (state, phase, prefs) = (parse(state)?, parse(phase)?, parse(prefs)?);
    guard(|| {
        Ok(dump(
            &focus::set_phase(&state, &phase, &prefs, now_ms).map_err(crate::raise)?,
        ))
    })
}

#[pyfunction]
fn focus_break_phase(cycles: i64, prefs: &str) -> PyResult<String> {
    let prefs = parse(prefs)?;
    guard(|| {
        Ok(focus::break_phase(cycles, &prefs)
            .map_err(crate::raise)?
            .to_string())
    })
}

#[pyfunction]
fn focus_credit(
    state: &str,
    assignment: &str,
    block: &str,
    work_min: i64,
) -> PyResult<Option<String>> {
    let (state, assignment, block) = (parse(state)?, parse(assignment)?, parse(block)?);
    guard(|| {
        let credited =
            focus::credit_target(&state, &assignment, &block, work_min).map_err(crate::raise)?;
        Ok(credited.map(|value| dump(&value)))
    })
}

#[pyfunction]
fn focus_candidates(blocks: &str, assignments: &str, trace: &str) -> PyResult<String> {
    let (blocks, assignments, trace) = (parse(blocks)?, parse(assignments)?, parse(trace)?);
    guard(|| {
        let found = focus::focus_candidates(&blocks, &assignments, &trace).map_err(crate::raise)?;
        Ok(array(found))
    })
}

#[pyfunction]
fn focus_now_next(blocks: &str, day: &str, minute: i64) -> PyResult<String> {
    let (blocks, day) = (parse(blocks)?, parse(day)?);
    guard(|| {
        Ok(dump(
            &focus::now_and_next(&blocks, &day, minute).map_err(crate::raise)?,
        ))
    })
}

#[pyfunction]
fn focus_now_next_line(result: &str, minute: i64) -> PyResult<String> {
    let result = parse(result)?;
    guard(|| focus::now_next_line(&result, minute).map_err(crate::raise))
}

#[pyfunction]
fn reuse_restore_label(text: &str) -> PyResult<String> {
    guard(|| Ok(reuse::restore_point_label(text)))
}

#[pyfunction]
fn reuse_week_label(week_start: &str, today: &str) -> PyResult<String> {
    let today = ::flexweek_engine::desk::datetext::day_of(today).map_err(crate::raise)?;
    guard(|| reuse::week_label(week_start, today).map_err(crate::raise))
}

#[pyfunction]
fn reuse_floor_slot(minutes: i64) -> PyResult<i64> {
    guard(|| Ok(planning::floor_slot(minutes)))
}

#[pyfunction]
fn reuse_homework(block: &str) -> PyResult<bool> {
    let block = parse(block)?;
    guard(|| planning::is_homework_session(&block).map_err(crate::raise))
}

#[pyfunction]
fn reuse_session_days(week_start: &str, due: &str) -> PyResult<Vec<i64>> {
    let due = parse(due)?;
    guard(|| planning::session_days(week_start, &due).map_err(crate::raise))
}

#[pyfunction]
fn reuse_planned(block: &str) -> PyResult<bool> {
    let block = parse(block)?;
    guard(|| planning::is_planned(&block).map_err(crate::raise))
}

#[pyfunction]
fn reuse_planning_days(block: &str, assignments: &str, week_start: &str) -> PyResult<String> {
    let (block, assignments) = (parse(block)?, parse(assignments)?);
    guard(|| {
        let days =
            planning::planning_days(&block, &assignments, week_start).map_err(crate::raise)?;
        Ok(dump(&Value::Array(days)))
    })
}

#[pyfunction]
fn reuse_apply_plan(
    blocks: &str,
    trace: &str,
    targets: Option<&str>,
    assignments: Option<&str>,
    week_start: Option<&str>,
) -> PyResult<String> {
    let (blocks, trace) = (parse(blocks)?, parse(trace)?);
    let targets = targets.map(parse).transpose()?;
    let assignments = assignments.map(parse).transpose()?;
    guard(|| {
        let out = planning::apply_plan(
            &blocks,
            &trace,
            targets.as_ref(),
            assignments.as_ref(),
            week_start,
        )
        .map_err(crate::raise)?;
        Ok(array(out))
    })
}

#[pyfunction]
fn reuse_clear_pins(blocks: &str) -> PyResult<String> {
    let blocks = parse(blocks)?;
    guard(|| {
        Ok(array(
            planning::clear_stale_pins(&blocks).map_err(crate::raise)?,
        ))
    })
}

#[pyfunction]
fn reuse_held(block: &str) -> PyResult<String> {
    let block = parse(block)?;
    guard(|| {
        Ok(dump(
            &planning::held_in_place(&block).map_err(crate::raise)?,
        ))
    })
}

/// `now` is a datetime: its date, hour, minute and seconds are read here, as the Python wrapper
/// read them.
#[pyfunction]
fn reuse_plan_start(week_start: &str, now: &Bound<'_, PyAny>) -> PyResult<Option<(i64, i64)>> {
    let today_iso = now
        .call_method0("date")?
        .call_method0("isoformat")?
        .extract::<String>()?;
    let hour = now.getattr("hour")?.extract::<i64>()?;
    let minute = now.getattr("minute")?.extract::<i64>()?;
    let second = now.getattr("second")?.extract::<i64>()?;
    let microsecond = now.getattr("microsecond")?.extract::<i64>()?;
    guard(|| {
        planning::plan_start_at(week_start, &today_iso, hour, minute, second, microsecond)
            .map_err(crate::raise)
    })
}

#[pyfunction]
fn reuse_occurrence_days(block: &str) -> PyResult<String> {
    let block = parse(block)?;
    guard(|| {
        let days = planning::occurrence_days(&block).map_err(crate::raise)?;
        Ok(dump(&Value::Array(days)))
    })
}

#[pyfunction]
fn reuse_session_minutes(blocks: &str, assignment_id: &str) -> PyResult<i64> {
    let (blocks, assignment_id) = (parse(blocks)?, parse(assignment_id)?);
    guard(|| planning::session_minutes(&blocks, &assignment_id).map_err(crate::raise))
}

#[pyfunction]
fn reuse_available_minutes(assignment: &str, blocks: &str, committed: &str) -> PyResult<i64> {
    let (assignment, blocks, committed) = (parse(assignment)?, parse(blocks)?, parse(committed)?);
    guard(|| {
        planning::available_homework_minutes(&assignment, &blocks, &committed).map_err(crate::raise)
    })
}

#[pyfunction]
fn reuse_capacity(existing_count: i64, added_count: i64, label: &str) -> PyResult<String> {
    guard(|| {
        Ok(planning::capacity_problem(
            existing_count,
            added_count,
            label,
        ))
    })
}

#[pyfunction]
fn reuse_overlap(start_a: i64, end_a: i64, start_b: i64, end_b: i64) -> PyResult<bool> {
    guard(|| Ok(reuse::intervals_overlap(start_a, end_a, start_b, end_b)))
}

#[pyfunction]
fn reuse_late_from(minute: i64) -> PyResult<String> {
    guard(|| Ok(planning::late_from_start(minute)))
}

#[pyfunction]
fn reuse_late_block(day: &str, from_start: &str, minutes: i64, block_id: &str) -> PyResult<String> {
    let (day, block_id) = (parse(day)?, parse(block_id)?);
    guard(|| {
        let block = planning::running_late_block(&day, from_start, minutes, &block_id)
            .map_err(crate::raise)?;
        Ok(dump(&block))
    })
}

#[pyfunction]
fn reuse_late_refusal(
    week_start: &str,
    now: &Bound<'_, PyAny>,
    dirty: bool,
    conflict: bool,
    block_count: i64,
) -> PyResult<Option<String>> {
    let today_iso = now
        .call_method0("date")?
        .call_method0("isoformat")?
        .extract::<String>()?;
    guard(|| {
        Ok(
            reuse::running_late_refusal(week_start, &today_iso, dirty, conflict, block_count)
                .map(str::to_string),
        )
    })
}

#[pyfunction]
fn reuse_late_line(block: &str, moved: &str) -> PyResult<String> {
    let (block, moved) = (parse(block)?, parse(moved)?);
    guard(|| planning::late_locked_line(&block, &moved).map_err(crate::raise))
}

#[pyfunction]
fn reuse_late_id(operation_id: &str) -> PyResult<String> {
    guard(|| Ok(reuse::late_id(operation_id)))
}

#[pyfunction]
fn reuse_copy_label(block: &str, source_day: &str, scope: &str) -> PyResult<String> {
    let (block, source_day, scope) = (parse(block)?, parse(source_day)?, parse(scope)?);
    guard(|| {
        let label = planning::copy_label(&block, &source_day, &scope).map_err(crate::raise)?;
        Ok(dump(&label))
    })
}

#[pyfunction]
fn reuse_due_point(due: &str, week_start: &str) -> PyResult<Option<(i64, i64)>> {
    let due = parse(due)?;
    guard(|| planning::due_point(&due, week_start).map_err(crate::raise))
}

#[pyfunction]
fn reuse_copied_fixed(source: &str, days: &str, block_id: &str) -> PyResult<String> {
    let (source, days, block_id) = (parse(source)?, parse(days)?, parse(block_id)?);
    guard(|| {
        let block =
            reuse::copied_fixed_block_listing(&source, &days, &block_id).map_err(crate::raise)?;
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
    let (assignment, block_id) = (parse(assignment)?, parse(block_id)?);
    guard(|| {
        let block =
            reuse::copied_homework_block_of(&assignment, day, &Value::from(duration), &block_id)
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
    let items = parse(items)?;
    guard(|| planning::clipboard_fingerprint(&items).map_err(crate::raise))
}

#[pyfunction]
fn reuse_occurs(block: &str, day: &str, placed: Option<&str>) -> PyResult<bool> {
    let (block, day) = (parse(block)?, parse(day)?);
    let placed = placed.map(parse).transpose()?;
    guard(|| planning::block_occurs_on_day(&block, &day, placed.as_ref()).map_err(crate::raise))
}

/// Where `row` sits in `rows`: the engine reads JSON, which has no identity, so the caller's own
/// objects are searched here.
fn own_place(row: &Bound<'_, PyAny>, rows: &Bound<'_, PyAny>) -> Option<usize> {
    let items: Vec<Bound<'_, PyAny>> = if let Ok(list) = rows.cast::<pyo3::types::PyList>() {
        list.iter().collect()
    } else if let Ok(tuple) = rows.cast::<pyo3::types::PyTuple>() {
        tuple.iter().collect()
    } else {
        return None;
    };
    items.iter().position(|item| item.is(row))
}

#[pyfunction]
fn reuse_row_conflict(
    row: &Bound<'_, PyAny>,
    rows: &Bound<'_, PyAny>,
    existing: &Bound<'_, PyAny>,
) -> PyResult<Option<String>> {
    let skip = own_place(row, rows);
    let (row, rows, existing) = (
        parse(&dumps_of(row)?)?,
        parse(&dumps_of(rows)?)?,
        parse(&dumps_of(existing)?)?,
    );
    guard(|| {
        let conflict =
            clipboard::row_conflict(&row, &rows, &existing, skip).map_err(crate::raise)?;
        Ok(conflict.map(|title| dump(&title)))
    })
}

#[pyfunction]
fn reuse_preview_message(
    row: &Bound<'_, PyAny>,
    rows: &Bound<'_, PyAny>,
    existing: &Bound<'_, PyAny>,
) -> PyResult<String> {
    let skip = own_place(row, rows);
    let (row, rows, existing) = (
        parse(&dumps_of(row)?)?,
        parse(&dumps_of(rows)?)?,
        parse(&dumps_of(existing)?)?,
    );
    guard(|| {
        let message = clipboard::preview_conflict_message(&row, &rows, &existing, skip)
            .map_err(crate::raise)?;
        Ok(dump(&message))
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
    let (items, assignments, available) = (parse(items)?, parse(assignments)?, parse(available)?);
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
    let rows = parse(rows)?;
    guard(|| {
        let merged = clipboard::merge_preview_rows(&rows, operation_id).map_err(crate::raise)?;
        Ok(dump(&Value::Array(merged)))
    })
}

#[pyfunction]
fn reuse_routine_sources(blocks: &str) -> PyResult<String> {
    let blocks = parse(blocks)?;
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
    let (routine, allowed) = (parse(routine)?, parse(allowed_days)?);
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
    let (assignments, saved) = (parse(assignments)?, parse(saved_weeks)?);
    let (blocks, committed) = (parse(blocks)?, parse(committed)?);
    guard(|| {
        let items =
            clipboard::unfinished_items(&assignments, &saved, week_start, &blocks, &committed)
                .map_err(crate::raise)?;
        Ok(dump(&Value::Array(items)))
    })
}

/// `session` is the caller's own, read here for its week, day and month, and asked for `now_ms()`
/// only when My Day needs the local date; `moment_at` is `datetime.fromtimestamp`. A Python error
/// from either is raised as it came.
#[pyfunction]
fn reuse_planner_title(
    session: &Bound<'_, PyAny>,
    view: &str,
    short: bool,
    selected_day: Option<&str>,
    moment_at: &Bound<'_, PyAny>,
) -> PyResult<String> {
    let week_start = crate::desk::text_arg(&session.getattr("week_start")?, "week_start")?;
    let session_day = crate::desk::opt_text_arg(
        &crate::desk::attr_or_none(session, "selected_day")?,
        "session_day",
    )?;
    let session_month = crate::desk::opt_text_arg(
        &crate::desk::attr_or_none(session, "selected_month")?,
        "session_month",
    )?;
    let failure: RefCell<Option<PyErr>> = RefCell::new(None);
    let mut local_date = || -> EngineResult<String> {
        let read = || -> PyResult<String> {
            let millis = session.call_method0("now_ms")?.extract::<f64>()?;
            moment_at
                .call1((::flexweek_engine::desk::remind::seconds_of_millis(millis),))?
                .call_method0("date")?
                .call_method0("isoformat")?
                .extract::<String>()
        };
        read().map_err(|error| {
            *failure.borrow_mut() = Some(error);
            EngineError::value("local date")
        })
    };
    let outcome = guard(|| {
        Ok(reuse::planner_title(
            &week_start,
            session_day.as_deref(),
            session_month.as_deref(),
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

/// What to send the solver, and which sessions its answer may place. `only` and `not_before` are
/// read as the Python wrapper wrote them: `only` as the list of its members, `not_before` as it is,
/// with a note of whether it was a list.
#[pyfunction]
fn reuse_solve_request(
    blocks: &str,
    assignments: &str,
    week_start: &str,
    everything: &Bound<'_, PyAny>,
    only: &Bound<'_, PyAny>,
    not_before: &Bound<'_, PyAny>,
) -> PyResult<(String, String)> {
    let (blocks, assignments) = (parse(blocks)?, parse(assignments)?);
    let everything = everything.is_truthy()?;
    let only = if only.is_none() {
        None
    } else {
        let members = only.py().get_type::<pyo3::types::PyList>().call1((only,))?;
        Some(parse(&dumps_of(&members)?)?)
    };
    let held_a_list = not_before.is_instance_of::<pyo3::types::PyList>();
    let not_before = if not_before.is_none() {
        None
    } else {
        Some(parse(&dumps_of(not_before)?)?)
    };
    guard(|| {
        let (payload, targets) = planning::solve_request(
            &blocks,
            &assignments,
            week_start,
            everything,
            only.as_ref(),
            not_before.as_ref(),
            held_a_list,
        )
        .map_err(crate::raise)?;
        Ok((array(payload), array(targets)))
    })
}

/// Takes the time away from planned homework whose slot no longer works. `keep` is read as the
/// Python wrapper wrote it: a set or frozenset as the list of its members, anything else as it is.
#[pyfunction]
fn reuse_settle_placements(
    blocks: &str,
    assignments: &str,
    week_start: &str,
    keep: &Bound<'_, PyAny>,
) -> PyResult<(String, String)> {
    let (blocks, assignments) = (parse(blocks)?, parse(assignments)?);
    let (keep, keep_is_set) = crate::desk::members_of(keep)?;
    let keep = parse(&keep)?;
    guard(|| {
        let (kept, lost) =
            planning::settle_placements(&blocks, &assignments, week_start, &keep, keep_is_set)
                .map_err(crate::raise)?;
        Ok((dump(&kept), array(lost)))
    })
}

#[pyfunction]
fn files_export_input(block: &str, assignments: &str) -> PyResult<String> {
    let (block, assignments) = (parse(block)?, parse(assignments)?);
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
    assignments: &str,
) -> PyResult<(String, Option<Py<PyAny>>)> {
    let (blocks, assignments) = (parse(blocks)?, parse(assignments)?);
    guard(|| {
        let (ids, failure) = files::referenced_ids(&blocks, &assignments).map_err(crate::raise)?;
        Ok((
            dump(&Value::Array(ids)),
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
fn files_occurrence_id(day: &str, block_id: &str) -> PyResult<String> {
    let (day, block_id) = (parse(day)?, parse(block_id)?);
    guard(|| files::occurrence_import_id(&day, &block_id).map_err(crate::raise))
}

#[pyfunction]
fn files_plan_homework(
    homework: &str,
    blocks: &str,
    week_start: &str,
    assignments: &str,
) -> PyResult<String> {
    let (homework, blocks) = (parse(homework)?, parse(blocks)?);
    let (week_start, assignments) = (parse(week_start)?, parse(assignments)?);
    guard(|| {
        let plan = files::plan_imported_homework(&homework, &blocks, &week_start, &assignments)
            .map_err(crate::raise)?;
        Ok(dump(&plan))
    })
}

#[pyfunction]
fn files_merge(existing: &str, incoming: &str, mode: &str, day: &str) -> PyResult<String> {
    let (existing, incoming) = (parse(existing)?, parse(incoming)?);
    let (mode, day) = (parse(mode)?, parse(day)?);
    guard(|| {
        files::merge_imported_blocks(&existing, &incoming, &mode, &day)
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

/// A value `json.dumps` cannot write is read as none was given.
#[pyfunction]
fn update_sanitize(raw: &Bound<'_, PyAny>) -> PyResult<String> {
    let text = match dumps_of(raw) {
        Ok(text) => text,
        Err(error) if error.is_instance_of::<PyTypeError>(raw.py()) => "null".to_string(),
        Err(error) => return Err(error),
    };
    let raw = parse(&text)?;
    guard(|| Ok(dump(&Value::Object(update::sanitize_updates(&raw)))))
}

#[pyfunction]
fn update_due(settings: &str, now_ms: i64) -> PyResult<bool> {
    let settings = parse(settings)?;
    guard(|| update::due_for_check(&settings, now_ms).map_err(crate::raise))
}

#[pyfunction]
fn look_saved(raw: &Bound<'_, PyAny>) -> PyResult<String> {
    guard(|| {
        let raw = if raw.is_instance_of::<pyo3::types::PyList>() {
            parse(&dumps_of(raw)?)?
        } else {
            Value::Null
        };
        custom_look::sanitize_saved(&raw)
            .map(maps)
            .map_err(crate::raise)
    })
}

#[pyfunction]
fn look_save(saved: &str, custom: &str, name: &Bound<'_, PyAny>) -> PyResult<String> {
    let (saved, custom) = (parse(saved)?, parse(custom)?);
    guard(|| {
        let name = name.extract::<String>().unwrap_or_default();
        let kept = custom_look::save_look(&saved, &custom, &name).map_err(crate::raise)?;
        Ok(dump(&Value::Array(kept)))
    })
}

#[pyfunction]
fn look_reset(custom: &str) -> PyResult<String> {
    let custom = parse(custom)?;
    guard(|| {
        let kept = custom_look::reset_look(&custom).map_err(crate::raise)?;
        Ok(dump(&Value::Object(kept)))
    })
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
fn look_name(name: &Bound<'_, PyAny>) -> PyResult<String> {
    let name = name.extract::<String>().ok();
    guard(|| custom_look::name_valid(name.as_deref()).map_err(crate::raise))
}

#[pyfunction]
fn look_find(saved: &str, name: &str) -> PyResult<i64> {
    let saved = parse(saved)?;
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
    let custom = parse(custom)?;
    let custom = ::flexweek_engine::stored::dict(&custom)
        .map_err(crate::raise)?
        .clone();
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
    let painted = objects(blocks)?
        .into_iter()
        .filter_map(|item| {
            let obj = item.as_object()?;
            Some(custom_look::PaintedCategory {
                key: obj.get("key")?.as_str()?.to_string(),
                fill: obj.get("fill")?.as_str()?.to_string(),
                drawn_fill: obj.get("drawn_fill")?.as_str()?.to_string(),
                ink: obj.get("ink")?.as_str()?.to_string(),
            })
        })
        .collect::<Vec<_>>();
    let filled = custom_look::filled_blocks(&painted);
    guard(|| {
        let found = custom_look::readability(&custom, &palette, &filled).map_err(crate::raise)?;
        Ok(array(
            found
                .into_iter()
                .map(|problem| {
                    serde_json::json!({
                        "words": problem.words,
                        "plural": problem.plural,
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

/// `problem` is the caller's own object; its `field` and `fixed` are read when the Python code
/// read them, and an error from reading them is raised as it came.
#[pyfunction]
fn look_apply_fix(custom: &str, problem: &Bound<'_, PyAny>) -> PyResult<String> {
    let custom = parse(custom)?;
    let failure: RefCell<Option<PyErr>> = RefCell::new(None);
    let stash = |error: PyErr| {
        *failure.borrow_mut() = Some(error);
        EngineError::value("problem")
    };
    let mut field = || -> EngineResult<Value> {
        let value = problem.getattr("field").map_err(&stash)?;
        let items = value.try_iter().map_err(|_| {
            stash(PyTypeError::new_err(format!(
                "Value after * must be an iterable, not {}",
                value
                    .get_type()
                    .name()
                    .map(|name| name.to_string())
                    .unwrap_or_default()
            )))
        })?;
        let mut pieces = Vec::new();
        for item in items {
            let item = item.map_err(&stash)?;
            pieces.push(item.extract::<String>().map_or(Value::Null, Value::from));
        }
        Ok(Value::Array(pieces))
    };
    let mut fixed = || -> EngineResult<Value> {
        let value = problem.getattr("fixed").map_err(&stash)?;
        Ok(value.extract::<String>().map_or(Value::Null, Value::from))
    };
    let outcome = guard(|| Ok(custom_look::apply_fix(&custom, &mut field, &mut fixed)))?;
    if let Some(error) = failure.into_inner() {
        return Err(error);
    }
    outcome
        .map(|fixed| dump(&Value::Object(fixed)))
        .map_err(crate::raise)
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
        reuse_solve_request,
        reuse_settle_placements,
        files_export_input,
        files_referenced_ids,
        files_assignment_input,
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
        files_block_inputs,
        files_export_rest,
        files_export_finish,
        files_import_start,
        files_import_finish,
        look_sanitize_custom,
        look_sanitize_look,
        look_effective_look,
        look_known_pack,
    );
    Ok(())
}

/// The model inputs of a week export (`day` absent) or a day export, and the failure that stopped
/// them, as an exception for Python to raise once the model has run on the inputs before it.
#[pyfunction]
fn files_block_inputs(
    py: Python<'_>,
    blocks: &str,
    assignments: &str,
    day: Option<&str>,
) -> PyResult<(String, Option<Py<PyAny>>)> {
    let (blocks, assignments) = (parse(blocks)?, parse(assignments)?);
    let day = opt_value(day)?;
    guard(|| {
        let (inputs, failure) = files::block_inputs(&blocks, &assignments, day.as_ref());
        Ok((
            array(inputs),
            failure.map(|error| crate::raise(error).into_value(py).into_any()),
        ))
    })
}

#[pyfunction]
fn files_export_rest(
    py: Python<'_>,
    week_start: &str,
    day: Option<&str>,
    blocks: &str,
    assignments: &str,
) -> PyResult<(String, String, Option<Py<PyAny>>)> {
    let (week_start, blocks, assignments) =
        (parse(week_start)?, parse(blocks)?, parse(assignments)?);
    let day = opt_value(day)?;
    guard(|| {
        let rest = files::export_rest(&week_start, day.as_ref(), &blocks, &assignments);
        Ok((
            dump(&rest.payload),
            array(rest.ids),
            rest.failure
                .map(|error| crate::raise(error).into_value(py).into_any()),
        ))
    })
}

#[pyfunction]
fn files_export_finish(payload: &str, bodies: &str) -> PyResult<String> {
    let (payload, bodies) = (parse(payload)?, parse(bodies)?);
    guard(|| Ok(dump(&files::export_finish(&payload, &bodies))))
}

#[pyfunction]
fn files_import_start(
    empty: bool,
    readable: bool,
    data: Option<&str>,
) -> PyResult<(String, String, String)> {
    let data = opt_value(data)?;
    guard(|| {
        let (head, blocks, homework) =
            files::import_start(empty, readable, data.as_ref()).map_err(crate::raise)?;
        Ok((dump(&head), array(blocks), array(homework)))
    })
}

#[pyfunction]
fn files_import_finish(
    head: &str,
    blocks: &str,
    assignments: &str,
    failure: Option<&str>,
) -> PyResult<String> {
    let head = parse(head)?;
    let (blocks, assignments) = (objects(blocks)?, objects(assignments)?);
    guard(|| {
        let payload =
            files::import_finish(&head, &blocks, &assignments, failure).map_err(crate::raise)?;
        Ok(dump(&payload))
    })
}

/// `(custom, problems)` as one JSON pair: the cleaned look or null, and a sentence for each setting
/// dropped. The three look functions below read a NaN or Infinity as `import_look` does.
#[pyfunction]
fn look_sanitize_custom(raw: &str) -> PyResult<String> {
    let raw = custom_look::readable(&parse(raw)?);
    guard(|| {
        let (custom, problems) = custom_look::sanitize_custom(&raw);
        Ok(dump(&json!([custom.map(Value::Object), problems])))
    })
}

#[pyfunction]
fn look_sanitize_look(raw: &str) -> PyResult<String> {
    let raw = custom_look::readable(&parse(raw)?);
    guard(|| Ok(dump(&Value::Object(custom_look::sanitize_look(&raw)))))
}

#[pyfunction]
fn look_effective_look(choice: &str) -> PyResult<String> {
    let choice = custom_look::readable(&parse(choice)?);
    guard(|| Ok(dump(&Value::Object(custom_look::effective_look(&choice)))))
}

/// Takes the caller's own object: anything that is not text is no pack.
#[pyfunction]
fn look_known_pack(pack: &Bound<'_, PyAny>) -> PyResult<String> {
    let pack = pack.extract::<String>().map_or(Value::Null, Value::from);
    guard(|| {
        Ok(custom_look::known_pack(&pack)
            .as_str()
            .unwrap_or("system")
            .to_string())
    })
}
