//! Rules the backend's helper functions in `app.py` used to decide in Python. Python keeps the
//! HTTP errors, the clock, the random draw and the pydantic checks; a check that has to run in
//! the middle of a rule arrives as a function the rule calls.

use flexweek_engine::plan;
use flexweek_engine::snapshot::canonical;
use flexweek_engine::stored;
use flexweek_engine::{EngineError, EngineResult, ErrorKind};
use serde_json::{Map, Value, json};

use crate::{StoreError, StoreResult, digest};

/// Either the rule failed, or the function it called did, and that failure goes back untouched.
pub enum Relay<E> {
    Store(StoreError),
    Caller(E),
}

impl<E> From<StoreError> for Relay<E> {
    fn from(error: StoreError) -> Self {
        Self::Store(error)
    }
}

impl<E> From<EngineError> for Relay<E> {
    fn from(error: EngineError) -> Self {
        Self::Store(StoreError::Engine(error))
    }
}

fn type_error(message: String) -> EngineError {
    EngineError {
        kind: ErrorKind::Type,
        message,
    }
}

fn parse_stored(text: &str) -> StoreResult<Value> {
    serde_json::from_str(text).map_err(|error| StoreError::Json {
        text: text.to_string(),
        error,
    })
}

/// SHA-256 of the canonical text of `value`: what the operation ledger compares payloads by.
pub fn payload_digest(value: &Value) -> String {
    digest(&canonical(value))
}

/// An assignment as the list shows it: the stored body, then the revision and the minutes
/// still unplanned. A key the body already has keeps its place.
pub fn assignment_view(body: &Value, revision: i64, planned: i64) -> EngineResult<Value> {
    let Value::Object(fields) = body else {
        return Err(type_error(format!(
            "'{}' object is not a mapping",
            stored::type_name(body)
        )));
    };
    let estimate = stored::py_int(stored::item(fields, "estimate_min")?)?;
    let focus = stored::py_int(stored::item(fields, "focus_minutes")?)?;
    let mut view = fields.clone();
    view.insert("revision".into(), json!(revision));
    view.insert("planned_min".into(), json!(planned));
    view.insert(
        "unplanned_min".into(),
        json!(plan::unplanned_minutes(estimate, focus, planned)),
    );
    Ok(Value::Object(view))
}

fn assignment_of<'a>(assignments: &'a Value, id: &str) -> EngineResult<&'a Value> {
    assignments
        .get(id)
        .ok_or_else(|| EngineError::key(id.to_string()))
}

/// Every block that names an assignment takes that assignment's title, priority and the rest.
pub fn rewrite_blocks(blocks: &Value, assignments: &Value) -> EngineResult<Vec<Value>> {
    let Value::Array(items) = blocks else {
        return Err(type_error(format!(
            "'{}' object is not iterable",
            stored::type_name(blocks)
        )));
    };
    let mut rewritten = Vec::with_capacity(items.len());
    for block in items {
        let named = block
            .get("assignment_id")
            .filter(|id| stored::truthy(Some(id)));
        match named {
            Some(id) => {
                let assignment = assignment_of(assignments, &stored::py_str(id))?;
                rewritten.push(plan::rewrite_session(block, assignment));
            }
            None => rewritten.push(block.clone()),
        }
    }
    Ok(rewritten)
}

fn membership(id: &Value, assignments: &Value) -> EngineResult<bool> {
    match id {
        Value::String(text) => Ok(assignments.get(text.as_str()).is_some()),
        Value::Array(_) | Value::Object(_) => Err(type_error(format!(
            "unhashable type: '{}'",
            stored::type_name(id)
        ))),
        _ => Ok(false),
    }
}

/// Stored blocks that name one of `assignments` take its fields. `normalize` is the pydantic
/// pass: it reads a block and hands back the block with every default filled in.
pub fn rewrite_stored_blocks<E>(
    blocks: &Value,
    assignments: &Value,
    mut normalize: impl FnMut(&Value) -> Result<Value, E>,
) -> Result<Vec<Value>, Relay<E>> {
    let items: Vec<Value> = match blocks {
        Value::Array(items) => items.clone(),
        other => stored::rows(other)?
            .into_iter()
            .map(Value::Object)
            .collect(),
    };
    let mut rewritten = Vec::with_capacity(items.len());
    for raw in items {
        let row = stored::dict(&raw)?;
        let named = row
            .get("assignment_id")
            .filter(|id| stored::truthy(Some(id)));
        let Some(id) = named else {
            rewritten.push(raw);
            continue;
        };
        if !membership(id, assignments)? {
            rewritten.push(raw);
            continue;
        }
        let block = normalize(&raw).map_err(Relay::Caller)?;
        let assignment = assignment_of(assignments, &stored::py_str(id))?;
        let swapped = plan::rewrite_session(&block, assignment);
        rewritten.push(normalize(&swapped).map_err(Relay::Caller)?);
    }
    Ok(rewritten)
}

fn loads(value: &Value) -> Result<Value, StoreError> {
    match value {
        Value::String(text) => parse_stored(text),
        other => Err(StoreError::Engine(type_error(format!(
            "the JSON object must be str, bytes or bytearray, not {}",
            stored::type_name(other)
        )))),
    }
}

/// `json.loads(value or "{}")`.
fn loads_or_empty(value: &Value) -> Result<Value, StoreError> {
    if stored::truthy(Some(value)) {
        loads(value)
    } else {
        Ok(json!({}))
    }
}

fn flag(value: &Value) -> Value {
    Value::Bool(stored::truthy(Some(value)))
}

fn whole(value: &Value) -> EngineResult<Value> {
    Ok(json!(stored::py_int(value)?))
}

/// What a preferences row hands the `Preferences` model: a missing comfort or availability
/// key becomes its default, a switch becomes a flag and a count a whole number.
pub fn preferences_fields(row: &Value) -> StoreResult<Value> {
    let row = stored::dict(row)?;
    let get = |key: &str| stored::item(row, key);
    let availability = loads_or_empty(get("availability_json")?)?;
    let comfort = loads_or_empty(get("comfort_json")?)?;
    let mut fields = Map::new();
    fields.insert("theme".into(), get("theme")?.clone());
    fields.insert("reminders_enabled".into(), flag(get("reminders_enabled")?));
    fields.insert(
        "reminder_lead_min".into(),
        whole(get("reminder_lead_min")?)?,
    );
    for name in ["reminder_sound", "reminder_dnd_override"] {
        fields.insert(name.into(), flag(get(name)?));
    }
    for name in [
        "timer_work_min",
        "timer_break_min",
        "timer_long_break_min",
        "timer_long_break_every",
    ] {
        fields.insert(name.into(), whole(get(name)?)?);
    }
    fields.insert(
        "auto_split_pomodoro".into(),
        flag(get("auto_split_pomodoro")?),
    );
    fields.insert(
        "default_spotify_url".into(),
        get("default_spotify_url")?.clone(),
    );
    fields.insert("alarms".into(), loads(get("alarms_json")?)?);
    let availability = stored::dict(&availability)?;
    for name in ["protected", "study_windows", "work_windows"] {
        let listed = availability
            .get(name)
            .filter(|value| stored::truthy(Some(value)))
            .cloned()
            .unwrap_or_else(|| json!([]));
        fields.insert(name.into(), listed);
    }
    fields.insert(
        "day_cutoff".into(),
        availability
            .get("day_cutoff")
            .cloned()
            .unwrap_or(Value::Null),
    );
    let comfort = stored::dict(&comfort)?;
    let kept = |name: &str, default: Value| comfort.get(name).cloned().unwrap_or(default);
    let switch = |name: &str, default: bool| comfort.get(name).map_or(Value::Bool(default), flag);
    fields.insert("alert_volume".into(), kept("alert_volume", json!(80)));
    fields.insert("end_chime".into(), switch("end_chime", false));
    fields.insert(
        "tray_notifications".into(),
        switch("tray_notifications", true),
    );
    fields.insert("start_at_login".into(), switch("start_at_login", false));
    fields.insert("preferred_view".into(), kept("preferred_view", Value::Null));
    fields.insert(
        "sidebar_collapsed".into(),
        switch("sidebar_collapsed", false),
    );
    fields.insert(
        "sidebar_width_px".into(),
        kept("sidebar_width_px", Value::Null),
    );
    fields.insert("theme_pack".into(), kept("theme_pack", json!("system")));
    fields.insert("accent".into(), kept("accent", json!("default")));
    fields.insert("accent_chips".into(), switch("accent_chips", false));
    fields.insert("motion".into(), kept("motion", Value::Null));
    fields.insert("alarm_tone".into(), kept("alarm_tone", json!("chime")));
    fields.insert(
        "planning_style".into(),
        kept("planning_style", json!("suggest")),
    );
    fields.insert("drag_step_min".into(), kept("drag_step_min", json!(5)));
    fields.insert("clock_24h".into(), switch("clock_24h", true));
    fields.insert("setup".into(), kept("setup", Value::Null));
    Ok(Value::Object(fields))
}

/// The windows the solver reads, from the stored availability text. No row at all is seven
/// empty days. `validate` runs each list through its pydantic model and returns the dumped list.
pub struct SolveAvailability {
    pub occupancy: Vec<u128>,
    pub study: Value,
    pub work: Value,
}

pub fn solve_availability<E>(
    stored_text: Option<&str>,
    mut validate: impl FnMut(&str, &Value) -> Result<Value, E>,
) -> Result<SolveAvailability, Relay<E>> {
    let Some(text) = stored_text else {
        return Ok(SolveAvailability {
            occupancy: vec![0; 7],
            study: json!([]),
            work: json!([]),
        });
    };
    let availability = if text.is_empty() {
        json!({})
    } else {
        parse_stored(text)?
    };
    let availability = stored::dict(&availability)?;
    let mut listed = |name: &str, kind: &str| -> Result<Value, Relay<E>> {
        let items = stored::py_list(availability.get(name))?;
        validate(kind, &Value::Array(items)).map_err(Relay::Caller)
    };
    let protected = listed("protected", "protected")?;
    let study = listed("study_windows", "study")?;
    let work = listed("work_windows", "work")?;
    let cutoff = match availability.get("day_cutoff") {
        None | Some(Value::Null) => None,
        Some(Value::String(text)) => Some(text.as_str()),
        Some(other) => {
            return Err(Relay::from(type_error(format!(
                "argument 'day_cutoff': '{}' object cannot be cast as 'str'",
                stored::type_name(other)
            ))));
        }
    };
    let protected = protected.as_array().cloned().unwrap_or_default();
    let occupancy = plan::occupancy_from_windows(&protected, cutoff)?;
    Ok(SolveAvailability {
        occupancy,
        study,
        work,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn text(value: &str) -> Value {
        serde_json::from_str(value).unwrap()
    }

    #[test]
    fn payload_digest_hashes_the_canonical_text() {
        // hashlib.sha256(b'{"a":[true,null],"b":1}').hexdigest()
        assert_eq!(
            payload_digest(&text(r#"{"b": 1, "a": [true, null]}"#)),
            "51705a2c9eb3e7e410a58f696a770c3ac3885a0cf43eb7fc88f5e47c11d4d30d"
        );
    }

    #[test]
    fn assignment_view_keeps_a_key_the_body_has_in_place() {
        // {**body, "revision": 3, "planned_min": 45, "unplanned_min": max(0, 90 - 30 - 45)}
        let body = text(r#"{"id": "a", "estimate_min": 90, "focus_minutes": 30, "revision": 9}"#);
        assert_eq!(
            assignment_view(&body, 3, 45).unwrap().to_string(),
            r#"{"id":"a","estimate_min":90,"focus_minutes":30,"revision":3,"planned_min":45,"unplanned_min":15}"#
        );
        let done = text(r#"{"estimate_min": 30, "focus_minutes": 60}"#);
        assert_eq!(
            assignment_view(&done, 1, 0).unwrap().to_string(),
            r#"{"estimate_min":30,"focus_minutes":60,"revision":1,"planned_min":0,"unplanned_min":0}"#
        );
    }

    #[test]
    fn assignment_view_raises_what_python_raised() {
        let missing = assignment_view(&text(r#"{"focus_minutes": 1}"#), 1, 0).unwrap_err();
        assert_eq!(
            (missing.kind, missing.message.as_str()),
            (ErrorKind::Key, "estimate_min")
        );
        let none = assignment_view(&text(r#"{"estimate_min": null, "focus_minutes": 1}"#), 1, 0)
            .unwrap_err();
        assert_eq!(none.kind, ErrorKind::Type);
        assert_eq!(
            none.message,
            "int() argument must be a string, a bytes-like object or a real number, not 'NoneType'"
        );
        let list = assignment_view(&text("[1]"), 1, 0).unwrap_err();
        assert_eq!(list.message, "'list' object is not a mapping");
    }

    const ASSIGNMENTS: &str = r#"{"a": {"title": "New", "priority": 1, "energy": "low", "course": null,
        "category": "c", "spotify_url": null}}"#;

    #[test]
    fn rewrite_blocks_changes_only_blocks_that_name_an_assignment() {
        let blocks = text(
            r#"[{"id": "s1", "assignment_id": "a", "title": "Old"},
                {"id": "s2", "assignment_id": null, "title": "Keep"},
                {"id": "s3", "assignment_id": "", "title": "Keep too"}]"#,
        );
        let out = rewrite_blocks(&blocks, &text(ASSIGNMENTS)).unwrap();
        assert_eq!(
            Value::Array(out).to_string(),
            r#"[{"id":"s1","assignment_id":"a","title":"New","priority":1,"energy":"low","course":null,"category":"c","spotify_url":null},{"id":"s2","assignment_id":null,"title":"Keep"},{"id":"s3","assignment_id":"","title":"Keep too"}]"#
        );
    }

    #[test]
    fn rewrite_blocks_names_the_assignment_it_cannot_find() {
        let blocks = text(r#"[{"id": "s1", "assignment_id": "zz"}]"#);
        let error = rewrite_blocks(&blocks, &text(ASSIGNMENTS)).unwrap_err();
        assert_eq!((error.kind, error.message.as_str()), (ErrorKind::Key, "zz"));
    }

    fn pad(block: &Value) -> Result<Value, String> {
        let mut block = block.clone();
        block
            .as_object_mut()
            .unwrap()
            .entry("pad")
            .or_insert(json!(0));
        Ok(block)
    }

    #[test]
    fn rewrite_stored_blocks_normalizes_a_rewritten_block_before_and_after() {
        let blocks = text(
            r#"[{"id": "s1", "assignment_id": "a", "title": "Old"},
                {"id": "s2", "assignment_id": "zz"},
                {"id": "s3"},
                {"id": "s4", "assignment_id": 7}]"#,
        );
        let mut calls = 0;
        let out = rewrite_stored_blocks(&blocks, &text(ASSIGNMENTS), |block| {
            calls += 1;
            pad(block)
        })
        .ok()
        .unwrap();
        assert_eq!(calls, 2);
        assert_eq!(
            Value::Array(out).to_string(),
            r#"[{"id":"s1","assignment_id":"a","title":"New","pad":0,"priority":1,"energy":"low","course":null,"category":"c","spotify_url":null},{"id":"s2","assignment_id":"zz"},{"id":"s3"},{"id":"s4","assignment_id":7}]"#
        );
    }

    #[test]
    fn rewrite_stored_blocks_gives_back_the_callers_failure_and_python_type_errors() {
        let blocks = text(r#"[{"id": "s1", "assignment_id": "a"}]"#);
        let failed = rewrite_stored_blocks(&blocks, &text(ASSIGNMENTS), |_| Err::<Value, _>("no"));
        assert!(matches!(failed, Err(Relay::Caller("no"))));
        let unhashable = text(r#"[{"id": "s1", "assignment_id": [1]}]"#);
        match rewrite_stored_blocks(&unhashable, &text(ASSIGNMENTS), pad) {
            Err(Relay::Store(StoreError::Engine(error))) => {
                assert_eq!(error.message, "unhashable type: 'list'");
            }
            _ => panic!("a list id must be an unhashable-type error"),
        }
        match rewrite_stored_blocks(&text(r#"["x"]"#), &text(ASSIGNMENTS), pad) {
            Err(Relay::Store(StoreError::Engine(error))) => {
                assert_eq!(error.message, "'str' object has no attribute 'get'");
            }
            _ => panic!("a block that is not a dict must fail on .get"),
        }
    }

    fn row(availability: &str, comfort: &str) -> Value {
        json!({
            "theme": "dark", "reminders_enabled": 1, "reminder_lead_min": 10,
            "reminder_sound": 0, "reminder_dnd_override": 0, "timer_work_min": 25,
            "timer_break_min": 5, "timer_long_break_min": 15, "timer_long_break_every": 4,
            "auto_split_pomodoro": 1, "default_spotify_url": null, "alarms_json": "[]",
            "availability_json": availability, "comfort_json": comfort,
        })
    }

    #[test]
    fn preferences_fields_fill_every_default_in_the_order_the_model_was_given() {
        let fields = preferences_fields(&row("", "{}")).unwrap();
        assert_eq!(
            fields.to_string(),
            concat!(
                r#"{"theme":"dark","reminders_enabled":true,"reminder_lead_min":10,"#,
                r#""reminder_sound":false,"reminder_dnd_override":false,"timer_work_min":25,"#,
                r#""timer_break_min":5,"timer_long_break_min":15,"timer_long_break_every":4,"#,
                r#""auto_split_pomodoro":true,"default_spotify_url":null,"alarms":[],"#,
                r#""protected":[],"study_windows":[],"work_windows":[],"day_cutoff":null,"#,
                r#""alert_volume":80,"end_chime":false,"tray_notifications":true,"#,
                r#""start_at_login":false,"preferred_view":null,"sidebar_collapsed":false,"#,
                r#""sidebar_width_px":null,"theme_pack":"system","accent":"default","#,
                r#""accent_chips":false,"motion":null,"alarm_tone":"chime","#,
                r#""planning_style":"suggest","drag_step_min":5,"clock_24h":true,"setup":null}"#
            )
        );
    }

    #[test]
    fn preferences_fields_keep_what_the_row_holds() {
        let fields = preferences_fields(&row(
            r#"{"protected": [{"a": 1}], "work_windows": [], "day_cutoff": "22:00"}"#,
            r#"{"alert_volume": null, "end_chime": 1, "tray_notifications": 0,
                "drag_step_min": 10, "setup": {"x": 1}}"#,
        ))
        .unwrap();
        assert_eq!(fields["protected"], json!([{"a": 1}]));
        assert_eq!(fields["work_windows"], json!([]));
        assert_eq!(fields["day_cutoff"], json!("22:00"));
        assert_eq!(fields["alert_volume"], Value::Null);
        assert_eq!(fields["end_chime"], json!(true));
        assert_eq!(fields["tray_notifications"], json!(false));
        assert_eq!(fields["drag_step_min"], json!(10));
        assert_eq!(fields["setup"], json!({"x": 1}));
    }

    #[test]
    fn preferences_fields_fail_as_the_python_did() {
        assert!(matches!(
            preferences_fields(&row("{oops", "{}")),
            Err(StoreError::Json { .. })
        ));
        let mut short = row("", "{}");
        short.as_object_mut().unwrap().shift_remove("theme");
        match preferences_fields(&short) {
            Err(StoreError::Engine(error)) => {
                assert_eq!(
                    (error.kind, error.message.as_str()),
                    (ErrorKind::Key, "theme")
                );
            }
            _ => panic!("a row without a theme is a KeyError"),
        }
        match preferences_fields(&row("[1]", "{}")) {
            Err(StoreError::Engine(error)) => {
                assert_eq!(error.message, "'list' object has no attribute 'get'");
            }
            _ => panic!("availability that is not a dict fails on .get"),
        }
    }

    fn keep_all(kind: &str, items: &Value) -> Result<Value, String> {
        Ok(json!({"kind": kind, "items": items}))
    }

    #[test]
    fn a_missing_availability_row_is_seven_empty_days() {
        let found = solve_availability(None, keep_all).ok().unwrap();
        assert_eq!(found.occupancy, vec![0u128; 7]);
        assert_eq!((found.study, found.work), (json!([]), json!([])));
    }

    #[test]
    fn availability_text_is_checked_by_kind_and_then_turned_into_occupancy() {
        // occupancy_from_windows([09:00 for 60 min on day 0], "22:00") in the original Python.
        let first = 78918677504442993555611320320_u128;
        let other = 78918677504442992524819169280_u128;
        let stored = r#"{"protected": [{"days": [0], "start": "09:00", "duration_min": 60, "kind": "meal"}],
            "study_windows": null, "work_windows": [{"w": 1}], "day_cutoff": "22:00"}"#;
        let mut kinds = Vec::new();
        let found = solve_availability(Some(stored), |kind, items| {
            kinds.push(kind.to_string());
            Ok::<_, String>(items.clone())
        })
        .ok()
        .unwrap();
        assert_eq!(kinds, ["protected", "study", "work"]);
        assert_eq!(
            found.occupancy,
            vec![first, other, other, other, other, other, other]
        );
        assert_eq!(found.study, json!([]));
        assert_eq!(found.work, json!([{"w": 1}]));
    }

    #[test]
    fn availability_that_is_an_empty_string_reads_as_no_windows() {
        let found = solve_availability(Some(""), keep_all).ok().unwrap();
        assert_eq!(found.occupancy, vec![0u128; 7]);
    }

    #[test]
    fn a_failing_check_stops_the_rule_before_the_occupancy() {
        let stored = r#"{"protected": [{"days": [0]}], "study_windows": [{"bad": 1}]}"#;
        let failed = solve_availability(Some(stored), |kind, items| {
            if kind == "study" {
                Err("invalid")
            } else {
                Ok(items.clone())
            }
        });
        assert!(matches!(failed, Err(Relay::Caller("invalid"))));
    }
}
