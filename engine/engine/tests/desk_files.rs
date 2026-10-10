//! Rust twin of `desktop/tests/test_files.py`: week and day file parse/merge.

mod common;

use common::desk::{object, with};
use flexweek_engine::desk::files::{
    EXPORT_VERSION, assignment_input, block_inputs, export_finish, export_rest, import_finish,
    import_start, merge_imported_blocks, migrated_assignment_id, plan_imported_homework,
};
use serde_json::{Map, Value, json};

// The pydantic models (`TimeBlock`, `AssignmentContent`) stay in Python: the wrapper runs them
// between the engine's steps. Here that step is the identity, which is what it is for these
// inputs: none of them is one a model would refuse, or one whose defaults an assertion reads.
// `AssignmentContent.model_fields`, the keys the engine keeps of a homework item:
const HOMEWORK_FIELDS: [&str; 16] = [
    "id",
    "title",
    "course",
    "category",
    "priority",
    "energy",
    "spotify_url",
    "due",
    "estimate_min",
    "focus_minutes",
    "focus_sessions",
    "completed",
    "completed_at",
    "notes",
    "links",
    "checklist",
];

fn assignment_body(item: &Value) -> Value {
    let fields: Vec<String> = HOMEWORK_FIELDS
        .iter()
        .map(|name| (*name).to_string())
        .collect();
    assignment_input(item, &fields).expect("a body")
}

/// `export_week_payload` / `export_day_payload` in the wrapper: the blocks the engine hands the
/// model, the engine's payload and homework ids, then the homework bodies.
fn export(
    week_start: &str,
    day: Option<i64>,
    blocks: &[Value],
    assignments: &Map<String, Value>,
) -> Value {
    let table = Value::Object(assignments.clone());
    let day = day.map(|day| json!(day));
    let (inputs, failure) = block_inputs(&json!(blocks), &table, day.as_ref());
    assert!(failure.is_none(), "{failure:?}");
    let rest = export_rest(
        &json!(week_start),
        day.as_ref(),
        &Value::Array(inputs),
        &table,
    );
    assert!(rest.failure.is_none(), "{:?}", rest.failure);
    let bodies: Vec<Value> = rest
        .ids
        .iter()
        .map(|id| assignment_body(&assignments[id.as_str().expect("an id")]))
        .collect();
    export_finish(&rest.payload, &json!(bodies))
}

/// `parse_import_payload` in the wrapper: what the text reads as, then the engine's two steps.
fn parse_import_payload(raw: &str) -> Value {
    let text = raw.trim();
    let data: Option<Value> = if text.is_empty() {
        None
    } else {
        serde_json::from_str(text).ok()
    };
    let (head, blocks, homework) =
        import_start(text.is_empty(), data.is_some(), data.as_ref()).expect("a head");
    let bodies: Vec<Value> = homework.iter().map(assignment_body).collect();
    import_finish(&head, &blocks, &bodies, None).expect("a verdict")
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
    let payload = export("2026-09-14", None, &[session, orphan], &assignments);
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
    let merged = merge_imported_blocks(
        &json!(existing),
        &json!(incoming),
        &json!("merge"),
        &json!(0),
    )
    .expect("merged");
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
        &json!([own, other]),
        &json!([
            {"id": "a", "assignment_id": "essay"},
            {"id": "b", "assignment_id": "other"},
        ]),
        &json!("2026-09-14"),
        &Value::Object(assignments),
    )
    .expect("a plan");
    assert_eq!(plan["blocks"][0]["assignment_id"], "essay");
    assert!(
        plan["blocks"][1]["assignment_id"]
            .as_str()
            .expect("a migrated id")
            .starts_with("a-")
    );
    assert_eq!(plan["create"][0]["id"], plan["blocks"][1]["assignment_id"]);
}

// Audit finding 7: a destination without the source's own id already holds the id the first import
// derived. Changed homework under the same source id must not be attached to that old body.
#[test]
fn test_reimported_homework_reuses_a_derived_id_only_for_the_same_homework() {
    let week = json!("2026-09-14");
    let first_id = migrated_assignment_id(&week, &json!("essay"));
    let first = with(essay(), json!({"id": first_id, "title": "Essay draft"}));
    let mut held = object(json!({}));
    held.insert(first_id.clone(), first.clone());
    let sessions = json!([{"id": "s1", "assignment_id": "essay"}]);

    let changed = with(
        essay(),
        json!({"title": "Final essay", "due": "2026-09-19T21:00"}),
    );
    let plan = plan_imported_homework(
        &json!([changed.clone()]),
        &sessions,
        &week,
        &Value::Object(held.clone()),
    )
    .expect("a plan");
    let fresh = plan["blocks"][0]["assignment_id"].clone();
    assert_ne!(fresh, json!(first_id));
    assert_eq!(plan["create"].as_array().map(Vec::len), Some(1));
    assert_eq!(plan["create"][0]["id"], fresh);
    assert_eq!(plan["create"][0]["title"], "Final essay");
    assert_eq!(plan["create"][0]["due"], "2026-09-19T21:00");

    // The same changed file again finds the homework the second import made.
    held.insert(
        fresh.as_str().expect("an id").to_string(),
        plan["create"][0].clone(),
    );
    let again = plan_imported_homework(
        &json!([changed]),
        &sessions,
        &week,
        &Value::Object(held.clone()),
    )
    .expect("a plan");
    assert_eq!(again["blocks"][0]["assignment_id"], fresh);
    assert_eq!(again["create"], json!([]));

    // And the first file still lands on the first import's homework, with nothing new made.
    let original = plan_imported_homework(
        &json!([with(essay(), json!({"title": "Essay draft"}))]),
        &sessions,
        &week,
        &Value::Object(held),
    )
    .expect("a plan");
    assert_eq!(original["blocks"][0]["assignment_id"], json!(first_id));
    assert_eq!(original["create"], json!([]));
}

#[test]
fn test_replace_mode_drops_existing_blocks() {
    let merged = merge_imported_blocks(
        &json!([soccer()]),
        &json!([with(soccer(), json!({"id": "band"}))]),
        &json!("replace"),
        &Value::Null,
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
    let tuesday = export(
        "2026-09-14",
        Some(1),
        std::slice::from_ref(&session),
        &assignments,
    );
    let thursday = export(
        "2026-09-14",
        Some(3),
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
    let payload = export("2026-09-14", Some(0), &[soccer()], &object(json!({})));
    assert_eq!(payload["format"], "flexweek-day");
    assert_eq!(payload["day"], 0);
    assert_eq!(payload["blocks"][0]["days"], json!([0]));
    let parsed = parse_import_payload(&payload.to_string());
    assert!(parsed.get("error").is_none_or(Value::is_null));
    assert_eq!(parsed["day"], 0);
}
