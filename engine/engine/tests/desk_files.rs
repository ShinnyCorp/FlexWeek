//! Rust twin of `desktop/tests/test_files.py`: week and day file parse/merge.

mod common;

use common::desk::{object, with};
use flexweek_engine::desk::files::{
    EXPORT_VERSION, export_day_payload, export_week_payload, merge_imported_blocks,
    parse_import_payload, plan_imported_homework,
};
use serde_json::{Value, json};

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
        "due": "2026-09-18T21:00",
        "estimate_min": 60,
        "priority": 3,
        "energy": "medium",
        "completed": false,
    })
}

fn error_of(raw: &str) -> String {
    parse_import_payload(raw)["error"]
        .as_str()
        .expect("an error message")
        .to_string()
}

#[test]
fn test_week_export_carries_referenced_homework_and_drops_unknown_links() {
    let session = json!({
        "id": "sess",
        "title": "Essay",
        "kind": "flexible",
        "duration_min": 60,
        "days": [0, 1, 2, 3, 4],
        "assignment_id": "essay",
    });
    let orphan = with(soccer(), json!({"assignment_id": "missing"}));
    let assignments = object(json!({"essay": essay()}));
    let payload = export_week_payload("2026-09-14", &[session, orphan], &assignments);
    assert_eq!(payload["format"], "flexweek-week");
    assert_eq!(payload["version"], EXPORT_VERSION);
    assert_eq!(payload["assignments"][0]["id"], "essay");
    assert!(payload["blocks"][1].get("assignment_id").is_none());
}

#[test]
fn test_parse_rejects_newer_versions_and_plain_text() {
    assert_eq!(error_of(""), "Empty file.");
    assert!(error_of("not json").contains("JSON"));
    let newer = json!({"format": "flexweek-week", "version": 99, "blocks": []}).to_string();
    assert!(error_of(&newer).contains("newer FlexWeek"));
}

#[test]
fn test_day_import_splits_a_locked_series_instead_of_replacing_other_days() {
    let existing = [soccer()];
    let incoming = [with(soccer(), json!({"days": [0], "start": "17:00"}))];
    let merged = merge_imported_blocks(&existing, &incoming, "merge", Some(0)).expect("merged");
    let by_id = |id: &str| {
        merged
            .iter()
            .rev()
            .find(|block| block["id"] == id)
            .unwrap_or_else(|| panic!("no block {id} in {merged:?}"))
    };
    assert_eq!(by_id("soccer")["days"], json!([2]));
    assert_eq!(by_id("soccer")["start"], "16:00");
    let split = by_id("occ-0-soccer");
    assert_eq!(split["days"], json!([0]));
    assert_eq!(split["start"], "17:00");
}

#[test]
fn test_plan_imported_homework_reuses_matching_ids_and_migrates_the_rest() {
    let own = essay();
    let other = with(essay(), json!({"id": "other", "title": "Lab"}));
    let assignments = object(json!({"essay": own.clone()}));
    let plan = plan_imported_homework(
        &[own, other],
        &[
            json!({"id": "a", "assignment_id": "essay"}),
            json!({"id": "b", "assignment_id": "other"}),
        ],
        "2026-09-14",
        &assignments,
    );
    assert_eq!(plan["blocks"][0]["assignment_id"], "essay");
    assert!(
        plan["blocks"][1]["assignment_id"]
            .as_str()
            .expect("a migrated id")
            .starts_with("a-")
    );
    assert_eq!(plan["create"][0]["id"], plan["blocks"][1]["assignment_id"]);
}

#[test]
fn test_replace_mode_drops_existing_blocks() {
    let merged = merge_imported_blocks(
        &[soccer()],
        &[with(soccer(), json!({"id": "band"}))],
        "replace",
        None,
    )
    .expect("merged");
    let ids: Vec<&Value> = merged.iter().map(|block| &block["id"]).collect();
    assert_eq!(ids, ["band"]);
}

#[test]
fn test_parse_rejects_oversize_dangling_and_pomodoro_pairs() {
    let too_many: Vec<Value> = (0..101)
        .map(|index| with(soccer(), json!({"id": format!("b{index}")})))
        .collect();
    let packed = json!({
        "format": "flexweek-week",
        "version": 2,
        "week_start": "2026-09-14",
        "blocks": too_many,
        "assignments": [],
    })
    .to_string();
    assert!(error_of(&packed).contains("more than 100 blocks"));
    let session = json!({
        "id": "sess",
        "title": "Essay",
        "kind": "flexible",
        "duration_min": 60,
        "days": [0],
        "assignment_id": "essay",
    });
    let dangling = json!({
        "format": "flexweek-week",
        "version": 2,
        "week_start": "2026-09-14",
        "blocks": [session],
        "assignments": [],
    })
    .to_string();
    assert!(error_of(&dangling).contains("does not include"));
    let repeated = json!({
        "format": "flexweek-week",
        "version": 2,
        "week_start": "2026-09-14",
        "blocks": [],
        "assignments": [essay(), essay()],
    })
    .to_string();
    assert!(error_of(&repeated).contains("homework id"));
    let chunk = with(
        soccer(),
        json!({"id": "chunk", "pomodoro_parent_id": "soccer", "pomodoro_role": "work"}),
    );
    let paired = json!({
        "format": "flexweek-week",
        "version": 2,
        "week_start": "2026-09-14",
        "blocks": [soccer(), chunk],
        "assignments": [],
    })
    .to_string();
    assert!(error_of(&paired).contains("focus chunks"));
}

#[test]
fn test_day_export_completed_flexible_pins_to_completed_day() {
    let session = json!({
        "id": "sess",
        "title": "Essay",
        "kind": "flexible",
        "duration_min": 60,
        "days": [1, 3],
        "start": "16:00",
        "completed": true,
        "completed_day": 3,
        "assignment_id": "essay",
    });
    let assignments = object(json!({"essay": essay()}));
    let tuesday = export_day_payload(
        "2026-09-14",
        1,
        std::slice::from_ref(&session),
        &assignments,
    );
    let thursday = export_day_payload(
        "2026-09-14",
        3,
        std::slice::from_ref(&session),
        &assignments,
    );
    assert_eq!(tuesday["blocks"], json!([]));
    let ids: Vec<&Value> = thursday["blocks"]
        .as_array()
        .expect("blocks")
        .iter()
        .map(|block| &block["id"])
        .collect();
    assert_eq!(ids, ["sess"]);
    assert_eq!(thursday["blocks"][0]["days"], json!([3]));
}

#[test]
fn test_day_export_keeps_only_that_weekday() {
    let payload = export_day_payload("2026-09-14", 0, &[soccer()], &object(json!({})));
    assert_eq!(payload["format"], "flexweek-day");
    assert_eq!(payload["day"], 0);
    assert_eq!(payload["blocks"][0]["days"], json!([0]));
    let parsed = parse_import_payload(&payload.to_string());
    assert!(parsed.get("error").is_none_or(Value::is_null));
    assert_eq!(parsed["day"], 0);
}
