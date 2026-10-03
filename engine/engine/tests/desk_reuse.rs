//! Rust twin of `desktop/tests/test_reuse.py`: clipboard, collision and unfinished helpers.

mod common;

use common::desk::{object, with};
use flexweek_engine::desk::calendar::days_through;
use flexweek_engine::desk::clipboard;
use flexweek_engine::desk::grid::{due_day_of, first_plannable_day as first_day};
use flexweek_engine::desk::planning;
use flexweek_engine::desk::reuse::{
    MAX_WEEK_BLOCKS, copied_fixed_block, copied_homework_block, restore_point_label,
    running_late_refusal,
};
use flexweek_engine::time::SLOT_MIN;
use serde_json::{Map, Value, json};
use std::collections::{BTreeMap, BTreeSet, HashSet};

// The calls below encode their arguments as the Python wrappers in desktop/native/reuse.py do
// (sets as lists, an absent value as null) and unwrap the engine's result; nothing else.

fn occurrence_days(block: &Value) -> Vec<i64> {
    let days = planning::occurrence_days(block).expect("days");
    days.iter()
        .map(|day| day.as_i64().expect("a day"))
        .collect()
}

fn apply_plan(
    blocks: &[Value],
    trace: Option<&Value>,
    targets: Option<&HashSet<String>>,
    assignments: Option<&Map<String, Value>>,
    week_start: Option<&str>,
) -> Vec<Value> {
    let targets = targets.map(|set| {
        let mut sorted: Vec<&String> = set.iter().collect();
        sorted.sort();
        json!(sorted)
    });
    let assignments = assignments.map(|map| Value::Object(map.clone()));
    planning::apply_plan(
        &json!(blocks),
        trace.unwrap_or(&Value::Null),
        targets.as_ref(),
        assignments.as_ref(),
        week_start,
    )
    .expect("a plan")
}

fn clear_stale_pins(blocks: &[Value]) -> Vec<Value> {
    planning::clear_stale_pins(&json!(blocks)).expect("blocks")
}

fn available_homework_minutes(
    assignment: Option<&Value>,
    blocks: &[Value],
    committed: Option<&[Value]>,
) -> i64 {
    planning::available_homework_minutes(
        assignment.unwrap_or(&Value::Null),
        &json!(blocks),
        &committed.map_or(Value::Null, |list| json!(list)),
    )
    .expect("minutes")
}

fn capacity_problem(existing: i64, added: i64, label: &str) -> String {
    planning::capacity_problem(existing, added, label)
}

fn clipboard_fingerprint(items: &[Value]) -> String {
    planning::clipboard_fingerprint(&json!(items)).expect("a fingerprint")
}

fn late_locked_line(block: &Value, moved: i64) -> String {
    planning::late_locked_line(block, &json!(moved)).expect("a line")
}

fn running_late_block(day: i64, from_start: &str, minutes: i64, block_id: &str) -> Value {
    planning::running_late_block(&json!(day), from_start, minutes, &json!(block_id))
        .expect("a block")
}

fn settle_placements(
    blocks: &[Value],
    assignments: &Map<String, Value>,
    week_start: &str,
    keep: &[String],
) -> (Vec<Value>, Vec<Value>) {
    let mut sorted = keep.to_vec();
    sorted.sort();
    let (kept, lost) = planning::settle_placements(
        &json!(blocks),
        &Value::Object(assignments.clone()),
        week_start,
        &json!(sorted),
        true,
    )
    .expect("a week");
    (kept.as_array().expect("blocks").clone(), lost)
}

fn solve_request(
    blocks: &[Value],
    assignments: &Map<String, Value>,
    week_start: &str,
    everything: bool,
    only: Option<&[String]>,
    not_before: Option<(i64, i64)>,
) -> (Vec<Value>, Vec<String>) {
    let only = only.map(|ids| {
        let mut sorted = ids.to_vec();
        sorted.sort();
        json!(sorted)
    });
    let not_before = not_before.map(|(day, minute)| json!([day, minute]));
    let (payload, targets) = planning::solve_request(
        &json!(blocks),
        &Value::Object(assignments.clone()),
        week_start,
        everything,
        only.as_ref(),
        not_before.as_ref(),
        false,
    )
    .expect("a request");
    let targets = targets
        .iter()
        .map(|id| id.as_str().expect("an id").to_string())
        .collect();
    (payload, targets)
}

fn proposals_from_clipboard(
    items: &[Value],
    kind: &str,
    week_start: &str,
    target_day: i64,
    target_start: Option<&str>,
    assignments: &Map<String, Value>,
    available: &Map<String, Value>,
) -> Vec<Value> {
    clipboard::proposals_from_clipboard(
        &json!(items),
        kind,
        week_start,
        target_day,
        target_start,
        &Value::Object(assignments.clone()),
        &Value::Object(available.clone()),
    )
    .expect("rows")
}

fn merge_preview_rows(rows: &[Value], operation_id: &str) -> Vec<Value> {
    clipboard::merge_preview_rows(&json!(rows), operation_id).expect("groups")
}

fn routine_source_blocks(blocks: &[Value]) -> Vec<Value> {
    clipboard::routine_source_blocks(&json!(blocks)).expect("sources")
}

fn routine_template(block: &Value, template_id: &str) -> Value {
    clipboard::routine_template(block, template_id).expect("a template")
}

fn routine_rows(routine: &Value, week_start: &str, allowed_days: &[Value]) -> Vec<Value> {
    clipboard::routine_rows(routine, week_start, &json!(allowed_days)).expect("rows")
}

fn unfinished_items(
    assignments: &Map<String, Value>,
    saved_weeks: &[Value],
    week_start: &str,
    blocks: &[Value],
    committed: &[Value],
) -> Vec<Value> {
    clipboard::unfinished_items(
        &Value::Object(assignments.clone()),
        &json!(saved_weeks),
        week_start,
        &json!(blocks),
        &json!(committed),
    )
    .expect("items")
}

fn soccer() -> Value {
    json!({
        "id": "soccer",
        "title": "Soccer",
        "kind": "locked",
        "duration_min": 60,
        "days": [0, 2],
        "start": "16:00",
        "category": "exercise",
    })
}

fn essay() -> Value {
    json!({
        "id": "essay",
        "title": "Essay",
        "estimate_min": 90,
        "focus_minutes": 0,
        "unplanned_min": 90,
        "completed": false,
        "due": "2026-09-11T21:00",
    })
}

fn ids(list: &[&str]) -> BTreeSet<String> {
    list.iter().map(|id| (*id).to_string()).collect()
}

fn message_of(note: &Value) -> &str {
    note["message"].as_str().expect("message")
}

#[test]
fn test_completed_flexible_pins_to_completed_day_only() {
    let done = json!({
        "id": "sess",
        "kind": "flexible",
        "days": [1, 3],
        "completed": true,
        "completed_day": 3,
        "start": "16:00",
    });
    assert_eq!(occurrence_days(&done), [3]);
    let open_work = with(
        done.clone(),
        json!({"completed": false, "completed_day": null}),
    );
    assert_eq!(occurrence_days(&open_work), [1, 3]);
    let unpinned = with(done, json!({"completed_day": null}));
    assert_eq!(occurrence_days(&unpinned), Vec::<i64>::new());
}

#[test]
fn test_copied_fixed_block_drops_homework_and_timer_state() {
    let source = with(
        soccer(),
        json!({
            "assignment_id": "essay",
            "completed": true,
            "missed_days": [0],
            "focus_minutes": 15,
            "pomodoro_role": "work",
        }),
    );
    let copy = copied_fixed_block(&source, &[1], "copy-1").expect("a copy");
    assert_eq!(copy["id"], "copy-1");
    assert_eq!(copy["kind"], "locked");
    assert_eq!(copy["days"], json!([1]));
    assert_eq!(copy["completed"], json!(false));
    assert_eq!(copy["missed_days"], json!([]));
    assert_eq!(copy["focus_minutes"], 0);
    assert!(copy.get("assignment_id").is_none());
    assert!(copy.get("pomodoro_role").is_none());
}

#[test]
fn test_homework_paste_keeps_assignment_identity_and_shares_remaining_time() {
    let assignment = essay();
    let session = json!({
        "id": "sess",
        "assignment_id": "essay",
        "title": "Essay",
        "kind": "flexible",
        "duration_min": 60,
        "days": [1],
    });
    let items = [
        json!({"block": session, "source_day": 1, "scope": "occurrence", "group_id": "g1"}),
        json!({"block": session, "source_day": 1, "scope": "occurrence", "group_id": "g2"}),
    ];
    let rows = proposals_from_clipboard(
        &items,
        "day",
        "2026-09-07",
        3,
        None,
        &object(json!({"essay": assignment})),
        &object(json!({"essay": 90})),
    );
    assert_eq!(rows[0]["checked"], json!(true));
    assert_eq!(rows[0]["block"]["assignment_id"], "essay");
    assert_eq!(rows[0]["block"]["duration_min"], 60);
    assert_eq!(rows[0]["block"]["kind"], "flexible");
    let start = rows[0]["block"].get("start");
    assert!(
        start.is_none_or(|start| start.is_null() || start == ""),
        "{start:?}"
    );
    assert_eq!(rows[1]["checked"], json!(true));
    assert_eq!(rows[1]["block"]["duration_min"], 30);
}

#[test]
fn test_a_second_homework_paste_is_invalid_when_nothing_remains() {
    let assignment = essay();
    let session = json!({
        "id": "sess",
        "assignment_id": "essay",
        "title": "Essay",
        "kind": "flexible",
        "duration_min": 90,
        "days": [1],
    });
    let items = [
        json!({"block": session, "source_day": 1, "scope": "occurrence", "group_id": "g1"}),
        json!({"block": session, "source_day": 1, "scope": "occurrence", "group_id": "g2"}),
    ];
    let rows = proposals_from_clipboard(
        &items,
        "block",
        "2026-09-07",
        2,
        None,
        &object(json!({"essay": assignment})),
        &object(json!({"essay": 90})),
    );
    assert_eq!(rows[1]["checked"], json!(false));
    assert_eq!(
        rows[1]["invalid"],
        "No unplanned time remains for this homework."
    );
}

#[test]
fn test_paste_of_a_fixed_block_onto_the_same_slot_conflicts() {
    let source = soccer();
    let items =
        [json!({"block": source, "source_day": 0, "scope": "occurrence", "group_id": "g1"})];
    let mut rows = proposals_from_clipboard(
        &items,
        "block",
        "2026-09-07",
        0,
        Some("16:00"),
        &Map::new(),
        &Map::new(),
    );
    let existing = [source];
    // The binding finds this row's place by identity. JSON has not got that, so the engine is
    // told skip is 0, the only row.
    assert_eq!(
        clipboard::row_conflict(&rows[0], &json!(rows), &json!(existing), Some(0))
            .expect("a verdict"),
        Some(json!("Soccer"))
    );
    rows[0]["block"]["start"] = json!("18:00");
    assert_eq!(
        clipboard::row_conflict(&rows[0], &json!(rows), &json!(existing), Some(0))
            .expect("a verdict"),
        None
    );
}

#[test]
fn test_adjacent_blocks_do_not_conflict() {
    let existing = [soccer()];
    let row = json!({
        "week_start": "2026-09-07",
        "day": 0,
        "fixed": true,
        "checked": true,
        "block": {"title": "Piano", "start": "17:00", "duration_min": 30, "days": [0]},
    });
    assert_eq!(
        clipboard::row_conflict(&row, &json!([&row]), &json!(existing), Some(0))
            .expect("a verdict"),
        None
    );
}

#[test]
fn test_capacity_problem_uses_merged_block_count() {
    let rows = proposals_from_clipboard(
        &[json!({"block": soccer(), "source_day": 0, "scope": "series", "group_id": "g1"})],
        "block",
        "2026-09-07",
        1,
        None,
        &Map::new(),
        &Map::new(),
    );
    let groups = merge_preview_rows(&rows, "00000000-0000-4000-8000-000000000001");
    assert_eq!(groups.len(), 1);
    assert_eq!(groups[0]["block"]["days"], json!([0, 2]));
    assert!(
        groups[0]["block"]["id"]
            .as_str()
            .expect("id")
            .starts_with("b-stage3-")
    );
    assert!(!capacity_problem(100, 1, "This week").is_empty());
    assert!(capacity_problem(99, 1, "This week").is_empty());
    assert_eq!(MAX_WEEK_BLOCKS, 100);
}

#[test]
fn test_available_minutes_follow_dirty_sessions_on_the_open_week() {
    let mut assignment = essay();
    assert_eq!(
        available_homework_minutes(Some(&assignment), &[], Some(&[])),
        90
    );
    assignment["unplanned_min"] = json!(60);
    let committed = vec![copied_homework_block(&assignment, 1, 30, "here").expect("a block")];
    assert_eq!(
        available_homework_minutes(Some(&assignment), &committed, Some(&committed)),
        60
    );
    let mut draft = committed.clone();
    draft.push(copied_homework_block(&assignment, 2, 30, "extra").expect("a block"));
    assert_eq!(
        available_homework_minutes(Some(&assignment), &draft, Some(&committed)),
        30
    );
}

#[test]
fn test_unfinished_needs_an_earlier_saved_week_and_a_slot_of_remaining_time() {
    let mut assignment = essay();
    let earlier = [json!("2026-08-31")];
    let same = [json!("2026-09-07")];
    let listed = |assignment: &Value, saved: &[Value]| {
        unfinished_items(
            &object(json!({"essay": assignment})),
            saved,
            "2026-09-07",
            &[],
            &[],
        )
    };
    let items = listed(&assignment, &earlier);
    assert_eq!(items[0]["id"], "essay");
    assert_eq!(items[0]["remaining_min"], 90);
    assert_eq!(listed(&assignment, &same), Vec::<Value>::new());
    assignment["unplanned_min"] = json!(10);
    assert_eq!(listed(&assignment, &earlier), Vec::<Value>::new());
}

#[test]
fn test_unfinished_lists_a_morning_deadline_before_one_with_no_time() {
    let morning = with(essay(), json!({"id": "quiz", "due": "2026-09-11T09:00"}));
    let untimed = with(essay(), json!({"id": "paper", "due": "2026-09-11"}));
    let items = unfinished_items(
        &object(json!({"quiz": morning, "paper": untimed})),
        &[json!("2026-08-31")],
        "2026-09-07",
        &[],
        &[],
    );
    let order: Vec<&Value> = items.iter().map(|item| &item["id"]).collect();
    assert_eq!(order, ["quiz", "paper"]);
}

#[test]
fn test_days_through_due_matches_the_web_planner() {
    assert_eq!(
        due_day_of(&json!("2026-09-11T08:10"), "2026-09-07").expect("a day"),
        Some(4)
    );
    assert_eq!(days_through(Some(4), 2), vec![2, 3, 4]);
    assert_eq!(days_through(Some(1), 3), vec![1]);
    // The Python test reads the real clock and only asks for a weekday index; the engine takes today
    // as an argument, so one day inside the week and one outside stand in for it.
    for today in ["2026-09-09", "2026-01-01"] {
        assert!(
            (0..7).contains(&first_day("2026-09-07", today).expect("a day")),
            "{today}"
        );
    }
}

#[test]
fn test_routines_are_locked_times_without_homework_or_pomodoro() {
    let blocks = [
        soccer(),
        copied_homework_block(&essay(), 1, 60, "hw").expect("a block"),
        with(soccer(), json!({"id": "chunk", "pomodoro_role": "work"})),
    ];
    let sources = routine_source_blocks(&blocks);
    let source_ids: Vec<&Value> = sources.iter().map(|block| &block["id"]).collect();
    assert_eq!(source_ids, ["soccer"]);
    let template = routine_template(&soccer(), "t1");
    assert_eq!(template["template_id"], "t1");
    assert!(template.get("assignment_id").is_none());
    let routine = json!({"name": "Sports", "blocks": [template]});
    let allowed: Vec<Value> = (0..5).map(|day| json!(day)).collect();
    let rows = routine_rows(&routine, "2026-09-14", &allowed);
    let days: Vec<&Value> = rows.iter().map(|row| &row["day"]).collect();
    assert_eq!(days, [0, 2]);
    assert!(rows.iter().all(|row| row["fixed"] == json!(true)));
}

#[test]
fn test_running_late_occupies_from_a_snapped_start_until_the_day_end() {
    let block = running_late_block(0, "22:30", 60, "b-late-1");
    assert_eq!(block["title"], "Running late");
    assert_eq!(block["kind"], "locked");
    assert_eq!(block["start"], "22:30");
    assert_eq!(block["duration_min"], 60);
    assert_eq!(block["category"], "downtime");
    let today = "2026-09-14";
    assert_eq!(
        running_late_refusal("2026-09-14", today, false, false, 0),
        None
    );
    let elsewhere = running_late_refusal("2026-09-07", today, false, false, 0).unwrap_or("");
    assert!(
        elsewhere.to_lowercase().contains("this week"),
        "{elsewhere:?}"
    );
    assert_eq!(
        running_late_refusal("2026-09-14", today, true, false, 0),
        Some("Your last change is still saving. Try again in a moment.")
    );
    assert_eq!(
        running_late_refusal("2026-09-14", today, false, true, 0),
        Some("This week was changed somewhere else. Reload it first.")
    );
}

#[test]
fn test_late_locked_line_names_the_interval_and_what_moved() {
    let block = running_late_block(0, "19:00", 30, "b-late-1");
    assert_eq!(
        late_locked_line(&block, 2),
        "Running late: 19:00–19:30 is now locked. 2 moved."
    );
    assert_eq!(
        late_locked_line(&block, 0),
        "Running late: 19:00–19:30 is now locked. Nothing had to move."
    );
}

#[test]
fn test_restore_point_labels_fit_eighty_characters() {
    let label = restore_point_label(&format!("Before applying {} to 2026-09-14", "A".repeat(80)));
    assert_eq!(label.chars().count(), 80);
    assert!(label.ends_with('…'));
}

#[test]
fn test_clipboard_fingerprint_ignores_group_ids() {
    let left =
        [json!({"block": soccer(), "source_day": 0, "scope": "occurrence", "group_id": "a"})];
    let right =
        [json!({"block": soccer(), "source_day": 0, "scope": "occurrence", "group_id": "b"})];
    assert_eq!(clipboard_fingerprint(&left), clipboard_fingerprint(&right));
    assert_eq!(SLOT_MIN, 15);
}

#[test]
fn test_apply_plan_writes_solver_starts_onto_the_week() {
    let blocks = [
        json!({"id": "essay", "title": "Essay", "kind": "flexible", "days": [0, 1, 2], "duration_min": 60}),
        json!({
            "id": "school", "title": "School", "kind": "locked", "days": [0], "start": "08:00",
            "duration_min": 390,
        }),
    ];
    let trace = json!({
        "placed": [
            {
                "id": "essay", "title": "Essay", "kind": "flexible", "days": [1], "start": "16:00",
                "duration_min": 60,
            },
            {
                "id": "school", "title": "School", "kind": "locked", "days": [0], "start": "08:00",
                "duration_min": 390,
            },
        ],
        "unplaced": [],
    });
    let planned = apply_plan(&blocks, Some(&trace), None, None, None);
    let essay = planned
        .iter()
        .find(|item| item["id"] == "essay")
        .expect("the essay");
    assert_eq!(essay["start"], "16:00");
    assert_eq!(essay["days"], json!([1]));
}

#[test]
fn test_apply_plan_clears_a_start_the_solver_could_not_keep() {
    let blocks = [
        json!({"id": "essay", "kind": "flexible", "days": [0], "start": "16:00", "duration_min": 60}),
    ];
    let out = apply_plan(
        &blocks,
        Some(&json!({"placed": [], "unplaced": [{"id": "essay"}]})),
        None,
        None,
        None,
    );
    assert!(out[0].get("start").is_none());
}

// A planned week to change: school Monday to Friday until 15:15, Math and English after it on
// Monday, Reading on Saturday. The week of 2026-09-28 starts on a Monday.
const PLAN_WEEK: &str = "2026-09-28";

fn plan_homework() -> Map<String, Value> {
    object(json!({
        "math": {"id": "math", "title": "Math worksheet", "due": "2026-09-28T21:00"},
        "eng": {"id": "eng", "title": "English essay", "due": "2026-09-29T21:00"},
        "read": {"id": "read", "title": "Reading", "due": "2026-10-04T21:00"},
    }))
}

fn planned_week() -> Vec<Value> {
    let session = |block_id: &str, title: &str, minutes: i64, day: i64, start: &str| {
        json!({
            "id": format!("s-{block_id}"),
            "title": title,
            "kind": "flexible",
            "duration_min": minutes,
            "days": [day],
            "start": start,
            "assignment_id": block_id,
        })
    };
    let school = json!({
        "id": "school",
        "title": "School",
        "kind": "locked",
        "duration_min": 435,
        "days": [0, 1, 2, 3, 4],
        "start": "08:00",
    });
    vec![
        school,
        session("math", "Math worksheet", 30, 0, "15:15"),
        session("eng", "English essay", 90, 0, "15:45"),
        session("read", "Reading", 60, 5, "12:00"),
    ]
}

fn game(start: &str) -> Value {
    json!({"id": "game", "title": "Game", "kind": "locked", "duration_min": 120, "days": [5], "start": start})
}

type Times = BTreeMap<String, (Vec<i64>, Option<String>)>;

fn times(blocks: &[Value]) -> Times {
    blocks
        .iter()
        .map(|block| {
            let days = block["days"]
                .as_array()
                .expect("days")
                .iter()
                .map(|day| day.as_i64().expect("day"))
                .collect();
            let start = block
                .get("start")
                .and_then(Value::as_str)
                .map(str::to_string);
            (block["id"].as_str().expect("id").to_string(), (days, start))
        })
        .collect()
}

fn at(days: &[i64], start: Option<&str>) -> (Vec<i64>, Option<String>) {
    (days.to_vec(), start.map(str::to_string))
}

#[test]
fn test_a_saturday_event_elsewhere_moves_no_homework() {
    let mut week = planned_week();
    week.push(game("15:00"));
    let (settled, lost) = settle_placements(&week, &plan_homework(), PLAN_WEEK, &[]);
    assert_eq!(lost, Vec::<Value>::new());
    assert_eq!(times(&settled), times(&week));
}

#[test]
fn test_a_saturday_event_over_reading_takes_only_readings_time() {
    let mut week = planned_week();
    week.push(game("11:30"));
    let (settled, lost) = settle_placements(&week, &plan_homework(), PLAN_WEEK, &[]);
    let messages: Vec<&str> = lost.iter().map(message_of).collect();
    assert_eq!(
        messages,
        ["Reading no longer fits Saturday at 12:00: Game is there now."]
    );
    let after = times(&settled);
    // Every day up to Sunday's deadline is open to it again; Monday's homework has not moved.
    assert_eq!(after["s-read"], at(&[0, 1, 2, 3, 4, 5, 6], None));
    assert_eq!(after["s-math"], at(&[0], Some("15:15")));
    assert_eq!(after["s-eng"], at(&[0], Some("15:45")));
}

#[test]
fn test_a_deadline_moved_earlier_takes_the_time_away_and_says_why() {
    let mut homework = plan_homework();
    homework.insert(
        "eng".into(),
        with(homework["eng"].clone(), json!({"due": "2026-09-28T16:00"})),
    );
    let (settled, lost) = settle_placements(&planned_week(), &homework, PLAN_WEEK, &[]);
    let messages: Vec<&str> = lost.iter().map(message_of).collect();
    assert_eq!(
        messages,
        ["English essay no longer fits Monday at 15:45: that is after it is due."]
    );
    assert_eq!(times(&settled)["s-eng"], at(&[0], None));
    assert_eq!(times(&settled)["s-math"], at(&[0], Some("15:15")));
}

#[test]
fn test_homework_moved_onto_other_homework_pushes_the_other_one_out() {
    let mut week = planned_week();
    week[1] = with(week[1].clone(), json!({"start": "16:00"}));
    let (settled, lost) =
        settle_placements(&week, &plan_homework(), PLAN_WEEK, &["s-math".to_string()]);
    let messages: Vec<&str> = lost.iter().map(message_of).collect();
    assert_eq!(
        messages,
        ["English essay no longer fits Monday at 15:45: Math worksheet is there now."]
    );
    assert_eq!(times(&settled)["s-math"], at(&[0], Some("16:00")));
}

#[test]
fn test_a_missed_school_day_frees_time_rather_than_taking_any() {
    let mut week = planned_week();
    week[0] = with(week[0].clone(), json!({"missed_days": [0]}));
    week[1] = with(week[1].clone(), json!({"start": "09:00"}));
    let (_settled, lost) = settle_placements(&week, &plan_homework(), PLAN_WEEK, &[]);
    assert_eq!(lost, Vec::<Value>::new());
}

#[test]
fn test_planning_holds_planned_homework_in_place_and_places_the_rest() {
    let mut week = planned_week();
    week[3] = with(week[3].clone(), json!({"days": [5, 6]}));
    week[3]
        .as_object_mut()
        .expect("a block")
        .shift_remove("start");
    let (payload, targets) = solve_request(&week, &plan_homework(), PLAN_WEEK, false, None, None);
    assert_eq!(targets, ["s-read"]);
    let held: BTreeMap<&str, &Value> = payload
        .iter()
        .map(|block| (block["id"].as_str().expect("id"), block))
        .collect();
    assert_eq!(
        *held["s-math"],
        json!({
            "id": "s-math",
            "title": "Math worksheet",
            "kind": "locked",
            "duration_min": 30,
            "days": [0],
            "start": "15:15",
        })
    );
    assert_eq!(held["s-read"]["kind"], "flexible");
    assert_eq!(held["s-read"]["days"], json!([5, 6]));
}

#[test]
fn test_replanning_everything_reopens_every_day_up_to_each_deadline() {
    let (payload, targets) = solve_request(
        &planned_week(),
        &plan_homework(),
        PLAN_WEEK,
        true,
        None,
        None,
    );
    assert_eq!(
        targets.into_iter().collect::<BTreeSet<_>>(),
        ids(&["s-math", "s-eng", "s-read"])
    );
    let sent: BTreeMap<&str, &Value> = payload
        .iter()
        .map(|block| (block["id"].as_str().expect("id"), block))
        .collect();
    let english = sent["s-eng"];
    assert_eq!(english["kind"], "flexible");
    assert_eq!(english["days"], json!([0, 1]));
    assert!(english.get("start").is_none());
    assert_eq!(sent["s-math"]["days"], json!([0]));
}

#[test]
fn test_finding_a_new_time_places_only_the_named_work() {
    let mut week = planned_week();
    week.push(json!({"id": "s-new", "title": "Lab report", "kind": "flexible", "duration_min": 60, "days": [2]}));
    let only = ["s-eng".to_string()];
    let (payload, targets) =
        solve_request(&week, &plan_homework(), PLAN_WEEK, false, Some(&only), None);
    assert_eq!(targets, ["s-eng"]);
    let sent: BTreeMap<&str, &Value> = payload
        .iter()
        .map(|block| (block["id"].as_str().expect("id"), block))
        .collect();
    assert!(!sent.contains_key("s-new"));
    assert_eq!(sent["s-math"]["kind"], "locked");
}

#[test]
fn test_a_plan_for_part_of_the_week_changes_only_that_part() {
    let trace = json!({
        "placed": [{"id": "s-eng", "kind": "flexible", "days": [1], "start": "15:15"}],
        "unplaced": [{"id": "s-read"}],
    });
    let targets: HashSet<String> = ["s-eng", "s-read"]
        .iter()
        .map(|id| (*id).to_string())
        .collect();
    let out = apply_plan(
        &planned_week(),
        Some(&trace),
        Some(&targets),
        Some(&plan_homework()),
        Some(PLAN_WEEK),
    );
    let after = times(&out);
    assert_eq!(after["s-eng"], at(&[1], Some("15:15")));
    assert_eq!(after["s-read"], at(&[0, 1, 2, 3, 4, 5, 6], None));
    assert_eq!(after["s-math"], at(&[0], Some("15:15")));
}

#[test]
fn test_a_plan_never_rewrites_a_fixed_block() {
    // The solver lists a fixed block with its missed days left out. Copying that list back made
    // Monday a missed day of a block that no longer ran on Monday, and the week stopped saving.
    let school = with(planned_week()[0].clone(), json!({"missed_days": [0]}));
    let trace = json!({
        "placed": [with(school.clone(), json!({"days": [1, 2, 3, 4], "missed_days": []}))],
        "unplaced": [],
    });
    assert_eq!(
        apply_plan(
            std::slice::from_ref(&school),
            Some(&trace),
            None,
            None,
            None
        ),
        [school]
    );
}

fn pinned_week() -> (Vec<Value>, Map<String, Value>) {
    let mine = json!({
        "id": "mine",
        "title": "Essay",
        "kind": "flexible",
        "duration_min": 60,
        "days": [3],
        "start": "16:00",
        "assignment_id": "essay",
        "pinned": true,
    });
    let planned = with(
        mine.clone(),
        json!({"id": "other", "title": "Math", "start": "18:00", "assignment_id": "math", "pinned": false}),
    );
    let assignments = object(json!({
        "essay": {"id": "essay", "due": "2026-09-20T23:59"},
        "math": {"id": "math", "due": "2026-09-20T23:59"},
    }));
    (vec![mine, planned], assignments)
}

#[test]
fn test_replan_all_leaves_homework_placed_by_hand_where_it_is() {
    let (blocks, assignments) = pinned_week();
    let (payload, targets) = solve_request(&blocks, &assignments, "2026-09-14", true, None, None);
    assert_eq!(targets, ["other"]);
    let held = payload
        .iter()
        .find(|block| block["id"] == "mine")
        .expect("mine");
    assert_eq!(held["kind"], "locked");
    assert_eq!(held["start"], "16:00");
    assert_eq!(held["days"], json!([3]));
}

#[test]
fn test_homework_placed_by_hand_stays_beside_a_fixed_block_and_planned_homework_gives_way() {
    // Two at one time is allowed, as in Daily Scheduler, when the student chose it: the essay was put
    // at 16:00 by hand. Math was only put at 18:00 by the planner, so it makes way for Band.
    let (blocks, assignments) = pinned_week();
    let school = json!({
        "id": "school",
        "title": "School",
        "kind": "locked",
        "duration_min": 120,
        "days": [3],
        "start": "15:30",
    });
    let band = with(
        school.clone(),
        json!({"id": "band", "title": "Band", "duration_min": 60, "start": "18:00"}),
    );
    let mut week = blocks;
    week.extend([school, band]);
    let (settled, lost) = settle_placements(&week, &assignments, "2026-09-14", &[]);
    let mine = settled
        .iter()
        .find(|block| block["id"] == "mine")
        .expect("mine");
    assert_eq!(mine["start"], "16:00");
    assert_eq!(mine["pinned"], json!(true));
    let lost_ids: Vec<&Value> = lost.iter().map(|note| &note["block_id"]).collect();
    assert_eq!(lost_ids, ["other"]);
    assert!(message_of(&lost[0]).contains("Band is there now"));
}

#[test]
fn test_a_pin_goes_when_its_time_does() {
    // The server refuses a pin with no time, so a left-over pin would stop every save. Past its due
    // date a hand-placed session still loses its time, and its pin with it.
    let (blocks, mut assignments) = pinned_week();
    assignments.insert(
        "essay".into(),
        json!({"id": "essay", "due": "2026-09-16T23:59"}),
    );
    let (settled, lost) = settle_placements(&blocks, &assignments, "2026-09-14", &[]);
    let mine = settled
        .iter()
        .find(|block| block["id"] == "mine")
        .expect("mine");
    let lost_ids: Vec<&Value> = lost.iter().map(|note| &note["block_id"]).collect();
    assert_eq!(lost_ids, ["mine"]);
    assert!(
        mine.get("start").is_none() && mine.get("pinned").is_none(),
        "{mine}"
    );
    let unplaced = with(
        blocks[0].clone(),
        json!({"start": null, "days": [0, 1, 2, 3]}),
    );
    assert!(clear_stale_pins(&[unplaced])[0].get("pinned").is_none());
    assert_eq!(clear_stale_pins(&blocks[..1])[0]["pinned"], json!(true));
}

#[test]
fn test_settle_keeps_a_hand_placed_night_block() {
    let night = json!({
        "id": "s-essay",
        "title": "Essay",
        "kind": "flexible",
        "duration_min": 60,
        "days": [0],
        "start": "03:00",
        "pinned": true,
        "assignment_id": "essay",
    });
    let homework =
        object(json!({"essay": {"id": "essay", "title": "Essay", "due": "2026-09-15T23:59"}}));
    let (settled, lost) = settle_placements(&[night], &homework, "2026-09-14", &[]);
    assert_eq!(lost, Vec::<Value>::new());
    let kept = settled
        .iter()
        .find(|block| block["id"] == "s-essay")
        .expect("kept");
    assert_eq!(kept["start"], "03:00");
    assert_eq!(kept["pinned"], json!(true));
}

#[test]
fn test_planning_an_old_week_still_asks_the_solver_for_unplaced_homework() {
    let week = [
        json!({
            "id": "school",
            "title": "School",
            "kind": "locked",
            "duration_min": 390,
            "days": [0, 1, 2, 3, 4],
            "start": "08:00",
        }),
        json!({
            "id": "s-essay",
            "title": "Essay",
            "kind": "flexible",
            "duration_min": 60,
            "days": [0, 1],
            "assignment_id": "essay",
        }),
    ];
    let homework =
        object(json!({"essay": {"id": "essay", "title": "Essay", "due": "2026-09-16T23:59"}}));
    let (payload, targets) = solve_request(&week, &homework, "2026-09-14", false, None, None);
    assert_eq!(targets, ["s-essay"]);
    let held: BTreeMap<&str, &Value> = payload
        .iter()
        .map(|block| (block["id"].as_str().expect("id"), block))
        .collect();
    assert_eq!(held["school"]["start"], "08:00");
    assert_eq!(held["s-essay"]["kind"], "flexible");
    assert!(held["s-essay"].get("start").is_none());
}
