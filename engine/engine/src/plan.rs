//! `backend/assignments.py`, `availability.py`, `comfort.py`, `day.py`, `month.py`, `explain.py`.

use std::collections::BTreeMap;
use std::sync::LazyLock;

use chrono::{Datelike, Duration, NaiveDate};
use serde_json::{Map, Value, json};

use crate::error::{EngineError, EngineResult};
use crate::model::{LAST_DAY_ISO, due_sort_key, parse_due};
use crate::stored::{self, Dict};
use crate::time::{
    DAY_END_MIN, SLOT_MIN, SLOTS_PER_DAY, block_interval_on_day, clock_to_minutes, date_from_iso,
    deadline_with, hhmm_to_minutes, minutes_to_hhmm, monday_of, month_grid, occupancy_between,
    parse_month, shift_days,
};

fn iso_date(day: NaiveDate) -> String {
    format!("{:04}-{:02}-{:02}", day.year(), day.month(), day.day())
}

// --- explain.py ---

pub const REASON_COPY: &[(&str, &str)] = &[
    (
        "LOCKED_OVERLAP",
        "Your fixed plans and finished work leave no gap long enough for it before it is due.",
    ),
    (
        "DEADLINE_MISS",
        "There is not enough time left before it is due, even with nothing else planned.",
    ),
    (
        "NO_SLOT_LEFT",
        "Your plans and other homework already fill every gap long enough for it.",
    ),
    (
        "PRIORITY_PREEMPT",
        "Work with a higher priority used the free time before it is due.",
    ),
    (
        "ENERGY_MISMATCH",
        "Planned outside its preferred time of day.",
    ),
    (
        "SLEEP_GUARD",
        "It does not fit in the day on the days left for it.",
    ),
    (
        "WORK_WINDOW_MISS",
        "That does not fit in the times you set aside for work.",
    ),
    (
        "RESHUFFLE_AFTER_MISS",
        "Moved because you missed a day, so the rest of the week still fits.",
    ),
];

pub fn sentence(code: &str) -> EngineResult<String> {
    REASON_COPY
        .iter()
        .find(|(key, _)| *key == code)
        .map(|(_, copy)| copy.to_string())
        .ok_or_else(|| EngineError::lookup(format!("unknown reason code: {code}")))
}

fn amount(minutes: i64) -> String {
    let (hours, rest) = (minutes.div_euclid(60), minutes.rem_euclid(60));
    if hours == 0 {
        return format!("{rest} min");
    }
    if rest == 0 {
        format!("{hours} h")
    } else {
        format!("{hours} h {rest} min")
    }
}

pub fn slack_sentence(slack_min: i64, status: &str) -> String {
    if slack_min == 0 {
        return "Finishes right when it is due.".to_string();
    }
    let only = if status == "danger" { "only " } else { "" };
    format!("Finishes {only}{} before it is due.", amount(slack_min))
}

// --- comfort.py ---

static TIMER_PRESETS: LazyLock<Vec<Value>> = LazyLock::new(|| {
    vec![
        json!({
            "id": "short",
            "label": "Short",
            "timer_work_min": 15,
            "timer_break_min": 15,
            "timer_long_break_min": 30,
            "timer_long_break_every": 4,
        }),
        json!({
            "id": "standard",
            "label": "Standard",
            "timer_work_min": 30,
            "timer_break_min": 15,
            "timer_long_break_min": 30,
            "timer_long_break_every": 4,
        }),
        json!({
            "id": "long",
            "label": "Long",
            "timer_work_min": 45,
            "timer_break_min": 15,
            "timer_long_break_min": 30,
            "timer_long_break_every": 4,
        }),
    ]
});

pub fn timer_presets() -> &'static [Value] {
    TIMER_PRESETS.as_slice()
}

pub fn reminder_limits() -> BTreeMap<&'static str, &'static str> {
    BTreeMap::from([
        (
            "web_open",
            "Reminders fire in this browser only while FlexWeek is open in a tab.",
        ),
        (
            "desktop_background",
            "The desktop app can still alert from the tray after the window is closed.",
        ),
        (
            "spotify",
            "A Spotify link is best-effort. FlexWeek plays a built-in sound if the track does not play.",
        ),
        (
            "duplicate",
            "The same block start fires at most one reminder until it is handled or the day changes.",
        ),
    ])
}

const FIELD_LABEL: &[(&str, &str)] = &[
    ("timer_work_min", "Work length"),
    ("timer_break_min", "Break length"),
    ("timer_long_break_min", "Long break"),
];

pub fn snap_minutes(value: i64, minimum: i64, maximum: i64) -> i64 {
    let mut snapped = ((value as f64 / SLOT_MIN as f64).round() * SLOT_MIN as f64) as i64;
    if snapped < minimum {
        snapped = minimum + ((SLOT_MIN - minimum.rem_euclid(SLOT_MIN)) % SLOT_MIN);
    }
    if snapped > maximum {
        snapped = maximum - maximum.rem_euclid(SLOT_MIN);
    }
    if snapped < SLOT_MIN {
        snapped = SLOT_MIN;
    }
    snapped
}

pub fn split_plan(
    duration_min: i64,
    work_min: i64,
    break_min: i64,
    long_break_min: i64,
    cadence: i64,
) -> EngineResult<Value> {
    let mut remaining = duration_min;
    let mut work_index = 0i64;
    let mut segments: Vec<Value> = Vec::new();
    while remaining > 0 {
        work_index += 1;
        let length = work_min.min(remaining);
        segments.push(json!({
            "role": "work",
            "duration_min": length,
            "index": work_index,
        }));
        remaining -= length;
        if remaining > 0 {
            if cadence == 0 {
                return Err(EngineError::zero_division("division by zero"));
            }
            let long = work_index.rem_euclid(cadence) == 0;
            segments.push(json!({
                "role": "break",
                "duration_min": if long { long_break_min } else { break_min },
                "index": work_index,
            }));
        }
    }
    let total_min: i64 = segments
        .iter()
        .map(|s| s["duration_min"].as_i64().unwrap_or(0))
        .sum();
    Ok(json!({
        "segments": segments,
        "total_min": total_min,
    }))
}

pub fn preview_split(
    duration_min: Option<i64>,
    timer_work_min: i64,
    timer_break_min: i64,
    timer_long_break_min: i64,
    timer_long_break_every: i64,
) -> EngineResult<Value> {
    let snapped = json!({
        "timer_work_min": snap_minutes(timer_work_min, 1, 180),
        "timer_break_min": snap_minutes(timer_break_min, 1, 60),
        "timer_long_break_min": snap_minutes(timer_long_break_min, 1, 120),
        "timer_long_break_every": timer_long_break_every,
    });
    let original = [
        ("timer_work_min", timer_work_min),
        ("timer_break_min", timer_break_min),
        ("timer_long_break_min", timer_long_break_min),
    ];
    let mut parts: Vec<String> = Vec::new();
    for (key, orig) in original {
        let snapped_val = snapped[key].as_i64().unwrap_or(0);
        if orig != snapped_val {
            let label = FIELD_LABEL
                .iter()
                .find(|(k, _)| *k == key)
                .map(|(_, l)| *l)
                .unwrap_or(key);
            parts.push(format!(
                "{label} {orig} minutes becomes {snapped_val} on the 15-minute grid."
            ));
        }
    }
    let mut plan = json!({"segments": [], "total_min": 0});
    if let Some(duration_min) = duration_min {
        plan = split_plan(
            duration_min,
            snapped["timer_work_min"].as_i64().unwrap_or(15),
            snapped["timer_break_min"].as_i64().unwrap_or(15),
            snapped["timer_long_break_min"].as_i64().unwrap_or(30),
            timer_long_break_every,
        )?;
    }
    let mut out = Map::new();
    for (k, v) in snapped.as_object().unwrap() {
        out.insert(k.clone(), v.clone());
    }
    out.insert("rounded".into(), json!(!parts.is_empty()));
    out.insert(
        "message".into(),
        Value::String(if parts.is_empty() {
            String::new()
        } else {
            parts.join(" ")
        }),
    );
    if let Some(obj) = plan.as_object() {
        for (k, v) in obj {
            out.insert(k.clone(), v.clone());
        }
    }
    Ok(Value::Object(out))
}

// --- assignments.py (sha256 + helpers) ---

fn sha256(data: &[u8]) -> [u8; 32] {
    // Minimal SHA-256 (FIPS 180-4) for migrated_assignment_id only.
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];
    fn rotr(x: u32, n: u32) -> u32 {
        x.rotate_right(n)
    }
    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
        0x5be0cd19,
    ];
    let bit_len = (data.len() as u64) * 8;
    let mut msg = data.to_vec();
    msg.push(0x80);
    while msg.len() % 64 != 56 {
        msg.push(0);
    }
    msg.extend_from_slice(&bit_len.to_be_bytes());
    for chunk in msg.chunks(64) {
        let mut w = [0u32; 64];
        for (i, word) in chunk.chunks(4).enumerate().take(16) {
            w[i] = u32::from_be_bytes(word.try_into().unwrap());
        }
        for i in 16..64 {
            let s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
            let s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16]
                .wrapping_add(s0)
                .wrapping_add(w[i - 7])
                .wrapping_add(s1);
        }
        let (mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut hh) =
            (h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7]);
        for i in 0..64 {
            let s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
            let ch = (e & f) ^ ((!e) & g);
            let t1 = hh
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(K[i])
                .wrapping_add(w[i]);
            let s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let t2 = s0.wrapping_add(maj);
            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(t1);
            d = c;
            c = b;
            b = a;
            a = t1.wrapping_add(t2);
        }
        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
        h[5] = h[5].wrapping_add(f);
        h[6] = h[6].wrapping_add(g);
        h[7] = h[7].wrapping_add(hh);
    }
    let mut out = [0u8; 32];
    for (i, word) in h.iter().enumerate() {
        out[i * 4..(i + 1) * 4].copy_from_slice(&word.to_be_bytes());
    }
    out
}

pub fn migrated_assignment_id(week_start: &str, source_id: &str) -> String {
    let digest = sha256(format!("{week_start}:{source_id}").as_bytes());
    let hex: String = digest.iter().map(|b| format!("{b:02x}")).collect();
    format!("a-{}", &hex[..32])
}

fn parse_iso_date(s: &str) -> EngineResult<NaiveDate> {
    date_from_iso(s)
}

fn py_index(len: usize, index: i64) -> EngineResult<usize> {
    let n = i64::try_from(len).unwrap_or(i64::MAX);
    let resolved = if index < 0 {
        n.checked_add(index)
    } else {
        Some(index)
    };
    match resolved {
        Some(at) if at >= 0 && at < n => Ok(at as usize),
        _ => Err(EngineError::index("list index out of range")),
    }
}

fn py_int(token: &str) -> EngineResult<i64> {
    crate::time::py_int(token)
}

fn unpacked_minutes(text: &str) -> EngineResult<i64> {
    // `map(int, text.split(":"))` converts each piece before the unpack counts them.
    let mut numbers = Vec::new();
    for part in text.split(':') {
        numbers.push(py_int(part)?);
    }
    if numbers.len() < 2 {
        return Err(EngineError::value(format!(
            "not enough values to unpack (expected 2, got {})",
            numbers.len()
        )));
    }
    if numbers.len() > 2 {
        return Err(EngineError::value("too many values to unpack (expected 2)"));
    }
    Ok(numbers[0] * 60 + numbers[1])
}

pub fn due_from_latest(
    week_start: &str,
    latest: Option<&str>,
    days: &[i64],
) -> EngineResult<String> {
    let days: Vec<Value> = days.iter().map(|day| Value::from(*day)).collect();
    due_of(week_start, latest.map(Value::from).as_ref(), &days)
}

/// `due_from_latest` on what a stored row holds: `latest` may be any value, `days` any list.
fn due_of(week_start: &str, latest: Option<&Value>, days: &[Value]) -> EngineResult<String> {
    let monday = parse_iso_date(week_start)?;
    let latest = match latest {
        None | Some(Value::Null) => None,
        Some(value) => Some(stored::text(value, "strip")?),
    };
    let last_day = || {
        if days.is_empty() {
            Ok(Value::from(0))
        } else {
            stored::py_max(days)
        }
    };
    let Some((day, minutes)) = deadline_with(latest, last_day)? else {
        let sunday = shift_days(monday, 6)?;
        return Ok(format!("{}T23:59", iso_date(sunday)));
    };
    let day = stored::add_days_of(monday, &day)?;
    Ok(format!("{}T{}", iso_date(day), minutes_to_hhmm(minutes)))
}

pub fn completed_at_for_block(week_start: &str, block: &Value) -> EngineResult<String> {
    let monday = parse_iso_date(week_start)?;
    let block = stored::dict(block)?;
    let start = block.get("start");
    let days = stored::py_list(block.get("days"))?;
    let mut day = block.get("completed_day").filter(|day| !day.is_null());
    if let Some(start) = start.filter(|start| stored::truthy(Some(start))) {
        if day.is_none() && days.len() == 1 {
            day = Some(&days[0]).filter(|day| !day.is_null());
        }
        if let Some(day) = day {
            let start = hhmm_to_minutes(stored::text(start, "split")?)?;
            let duration = stored::py_int(stored::item(block, "duration_min")?)?;
            let mut end = start
                .checked_add(duration)
                .ok_or_else(|| EngineError::overflow("Python int too large to convert to C int"))?;
            let mut day_date = stored::add_days(monday, stored::py_int(day)?)?;
            if end >= 24 * 60 {
                day_date = stored::add_days(day_date, end.div_euclid(24 * 60))?;
                end = end.rem_euclid(24 * 60);
            }
            let last = NaiveDate::parse_from_str(LAST_DAY_ISO, "%Y-%m-%d").unwrap();
            if day_date > last {
                return Ok(format!("{LAST_DAY_ISO}T23:59"));
            }
            return Ok(format!("{}T{}", iso_date(day_date), minutes_to_hhmm(end)));
        }
    }
    let sunday = shift_days(monday, 6)?;
    Ok(format!("{}T23:59", iso_date(sunday)))
}

fn assignment_body(
    assignment_id: &str,
    block: &Dict,
    due: &str,
    estimate_min: i64,
    focus_minutes: i64,
    focus_sessions: i64,
    completed: bool,
    completed_at: Option<&str>,
) -> Value {
    let title = block
        .get("title")
        .filter(|title| stored::truthy(Some(title)))
        .cloned()
        .unwrap_or_else(|| json!(assignment_id));
    json!({
        "id": assignment_id,
        "title": title,
        "course": block.get("course"),
        "category": block.get("category"),
        "priority": block.get("priority").unwrap_or(&json!(3)),
        "energy": block.get("energy").unwrap_or(&json!("medium")),
        "spotify_url": block.get("spotify_url"),
        "due": due,
        "estimate_min": estimate_min,
        "focus_minutes": focus_minutes,
        "focus_sessions": focus_sessions,
        "completed": completed,
        "completed_at": completed_at,
    })
}

fn as_session(block: &mut Dict, assignment_id: &str) {
    block.insert("assignment_id".into(), json!(assignment_id));
    block.shift_remove("latest");
    block.shift_remove("focus_minutes");
    block.shift_remove("focus_sessions");
}

pub fn due_placement_bound(week_start: &str, due: &str) -> EngineResult<Option<(i64, i64)>> {
    let monday = parse_iso_date(week_start)?;
    let (due_day, minutes) = parse_due(due)?;
    let sunday = shift_days(monday, 6)?;
    if due_day > sunday {
        return Ok(None);
    }
    if due_day < monday {
        return Ok(Some((0, 0)));
    }
    Ok(Some(((due_day - monday).num_days(), minutes)))
}

pub fn due_slack_point(week_start: &str, due: &str) -> EngineResult<(i64, i64)> {
    let monday = parse_iso_date(week_start)?;
    let (due_day, minutes) = parse_due(due)?;
    Ok(((due_day - monday).num_days(), minutes))
}

pub fn unplanned_minutes(estimate_min: i64, focus_minutes: i64, planned: i64) -> i64 {
    let remaining = (estimate_min - focus_minutes).max(0);
    (remaining - planned).max(0)
}

pub fn planned_minutes_by_id(
    weeks: &[(String, Vec<Value>)],
    from_week: &str,
) -> BTreeMap<String, i64> {
    let mut totals: BTreeMap<String, i64> = BTreeMap::new();
    for (week_start, blocks) in weeks {
        if week_start.as_str() < from_week {
            continue;
        }
        for block in blocks {
            let Some(aid) = block.get("assignment_id").and_then(Value::as_str) else {
                continue;
            };
            if block
                .get("completed")
                .and_then(Value::as_bool)
                .unwrap_or(false)
            {
                continue;
            }
            let dur = block["duration_min"].as_i64().unwrap_or(0);
            *totals.entry(aid.to_string()).or_insert(0) += dur;
        }
    }
    totals
}

pub fn prepare_solve(
    blocks: &[Value],
    week_start: &str,
    assignments: &BTreeMap<String, Value>,
) -> EngineResult<(
    Vec<Value>,
    BTreeMap<String, Option<(i64, i64)>>,
    BTreeMap<String, (i64, i64)>,
)> {
    let mut keep: Vec<Value> = Vec::new();
    let mut deadlines: BTreeMap<String, Option<(i64, i64)>> = BTreeMap::new();
    let mut slack: BTreeMap<String, (i64, i64)> = BTreeMap::new();
    for block in blocks {
        let aid = block.get("assignment_id").and_then(Value::as_str);
        let Some(aid) = aid else {
            keep.push(block.clone());
            continue;
        };
        let body = assignments
            .get(aid)
            .ok_or_else(|| EngineError::key(aid.to_string()))?;
        if body
            .get("completed")
            .and_then(Value::as_bool)
            .unwrap_or(false)
            && !block
                .get("completed")
                .and_then(Value::as_bool)
                .unwrap_or(false)
        {
            continue;
        }
        let mut updated = block.clone();
        if let Some(obj) = updated.as_object_mut() {
            obj.insert(
                "course".into(),
                body.get("course").cloned().unwrap_or(Value::Null),
            );
        }
        keep.push(updated);
        let block_id = block["id"].as_str().unwrap_or("");
        deadlines.insert(
            block_id.to_string(),
            due_placement_bound(week_start, body["due"].as_str().unwrap_or(""))?,
        );
        slack.insert(
            block_id.to_string(),
            due_slack_point(week_start, body["due"].as_str().unwrap_or(""))?,
        );
    }
    Ok((keep, deadlines, slack))
}

pub fn legacy_session(week_start: &str, block: &Value) -> EngineResult<(Value, Value)> {
    let raw = block.clone();
    let block_id = block["id"].as_str().unwrap_or("");
    let aid = migrated_assignment_id(week_start, block_id);
    let days: Vec<i64> = block
        .get("days")
        .and_then(Value::as_array)
        .map(|a| a.iter().filter_map(|v| v.as_i64()).collect())
        .unwrap_or_default();
    let due = due_from_latest(
        week_start,
        block.get("latest").and_then(Value::as_str),
        &days,
    )?;
    let completed = block
        .get("completed")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let completed_at = if completed {
        Some(completed_at_for_block(week_start, &raw)?)
    } else {
        None
    };
    let body = assignment_body(
        &aid,
        stored::dict(&raw)?,
        &due,
        block["duration_min"].as_i64().unwrap_or(0),
        block
            .get("focus_minutes")
            .and_then(Value::as_i64)
            .unwrap_or(0),
        block
            .get("focus_sessions")
            .and_then(Value::as_i64)
            .unwrap_or(0),
        completed,
        completed_at.as_deref(),
    );
    let mut session = block.clone();
    if let Some(obj) = session.as_object_mut() {
        obj.insert("assignment_id".into(), json!(aid));
        obj.insert("latest".into(), Value::Null);
        obj.insert("focus_minutes".into(), json!(0));
        obj.insert("focus_sessions".into(), json!(0));
    }
    Ok((session, body))
}

pub fn rewrite_session(block: &Value, assignment: &Value) -> Value {
    let mut out = block.clone();
    if let Some(obj) = out.as_object_mut() {
        for key in [
            "title",
            "priority",
            "energy",
            "course",
            "category",
            "spotify_url",
        ] {
            if let Some(v) = assignment.get(key) {
                obj.insert(key.into(), v.clone());
            }
        }
    }
    out
}

pub fn migrate_blocks(week_start: &str, blocks: &Value) -> EngineResult<(Value, Vec<Value>)> {
    let mut updated = stored::rows(blocks)?;
    let mut created: Vec<Value> = Vec::new();
    let mut grouped: Vec<(String, Vec<usize>)> = Vec::new();
    for (index, block) in updated.iter().enumerate() {
        let parent = block.get("pomodoro_parent_id");
        if block.get("kind").and_then(Value::as_str) == Some("locked") && stored::truthy(parent) {
            let parent = stored::py_str(parent.unwrap_or(&Value::Null));
            match grouped.iter_mut().find(|(name, _)| *name == parent) {
                Some((_, indices)) => indices.push(index),
                None => grouped.push((parent, vec![index])),
            }
        }
    }
    let mut claimed: std::collections::BTreeSet<usize> = std::collections::BTreeSet::new();
    let monday = parse_iso_date(week_start)?;
    let sunday_due = format!("{}T23:59", iso_date(shift_days(monday, 6)?));
    for (parent, indices) in grouped {
        let work_indices: Vec<usize> = indices
            .into_iter()
            .filter(|i| updated[*i].get("pomodoro_role").and_then(Value::as_str) == Some("work"))
            .collect();
        if work_indices.is_empty()
            || work_indices
                .iter()
                .any(|i| stored::truthy(updated[*i].get("assignment_id")))
        {
            continue;
        }
        let work: Vec<&Dict> = work_indices.iter().map(|i| &updated[*i]).collect();
        let aid = migrated_assignment_id(week_start, &parent);
        let completed = work.iter().all(|b| stored::truthy(b.get("completed")));
        let completed_at = if completed {
            let mut ends = Vec::new();
            for block in work.iter().filter(|b| stored::truthy(b.get("start"))) {
                ends.push(completed_at_for_block(
                    week_start,
                    &Value::Object((*block).clone()),
                )?);
            }
            Some(ends.into_iter().max().unwrap_or_else(|| sunday_due.clone()))
        } else {
            None
        };
        let mut estimate_min = 0i64;
        for block in &work {
            estimate_min = sum(
                estimate_min,
                stored::py_int(stored::item(block, "duration_min")?)?,
            )?;
        }
        let mut focus_minutes = 0i64;
        for block in &work {
            focus_minutes = sum(
                focus_minutes,
                stored::int_or_zero(block.get("focus_minutes"))?,
            )?;
        }
        let mut focus_sessions = 0i64;
        for block in &work {
            focus_sessions = sum(
                focus_sessions,
                stored::int_or_zero(block.get("focus_sessions"))?,
            )?;
        }
        created.push(assignment_body(
            &aid,
            work[0],
            &sunday_due,
            estimate_min,
            focus_minutes,
            focus_sessions,
            completed,
            completed_at.as_deref(),
        ));
        for index in work_indices {
            as_session(&mut updated[index], &aid);
            claimed.insert(index);
        }
    }
    for (index, block) in updated.iter_mut().enumerate() {
        if claimed.contains(&index)
            || stored::truthy(block.get("assignment_id"))
            || block.get("kind").and_then(Value::as_str) != Some("flexible")
        {
            continue;
        }
        let aid = migrated_assignment_id(week_start, &stored::py_str(stored::item(block, "id")?));
        let completed = stored::truthy(block.get("completed"));
        let latest = block.get("latest");
        let days = stored::py_list(block.get("days"))?;
        let due = due_of(week_start, latest, &days)?;
        let estimate_min = stored::py_int(stored::item(block, "duration_min")?)?;
        let focus_minutes = stored::int_or_zero(block.get("focus_minutes"))?;
        let focus_sessions = stored::int_or_zero(block.get("focus_sessions"))?;
        let completed_at = if completed {
            Some(completed_at_for_block(
                week_start,
                &Value::Object(block.clone()),
            )?)
        } else {
            None
        };
        created.push(assignment_body(
            &aid,
            block,
            &due,
            estimate_min,
            focus_minutes,
            focus_sessions,
            completed,
            completed_at.as_deref(),
        ));
        as_session(block, &aid);
    }
    let updated = match blocks {
        Value::Array(_) => Value::Array(updated.into_iter().map(Value::Object).collect()),
        // An empty str or dict iterates as nothing and comes back as it was.
        other => other.clone(),
    };
    Ok((updated, created))
}

/// Python's `sum` of ints, which has no ceiling; past 64 bits this raises instead.
fn sum(total: i64, more: i64) -> EngineResult<i64> {
    total
        .checked_add(more)
        .ok_or_else(|| EngineError::overflow("Python int too large to convert to C int"))
}

// --- availability.py ---

pub const LATE_COPY: &str = "Moved after you ran late so the rest of the day still fits.";
pub const CLUSTER_COPY: &str = "Several tasks are short on time. Shorten a session, pick another day, or free some protected hours. Work that cannot fit stays unplaced.";

pub fn default_work_windows() -> Vec<Value> {
    vec![json!({
        "days": [0, 1, 2, 3, 4, 5, 6],
        "start": "00:00",
        "end": "24:00",
    })]
}

pub fn legacy_work_windows() -> Vec<Value> {
    vec![json!({
        "days": [0, 1, 2, 3, 4, 5, 6],
        "start": "06:00",
        "end": "23:00",
    })]
}

pub fn add_occupancy(occ: &mut [u128], day: i64, start_min: i64, end_min: i64) -> EngineResult<()> {
    let day = py_index(occ.len(), day)?;
    occ[day] |= occupancy_between(start_min, end_min)?;
    Ok(())
}

pub fn occupancy_from_windows(
    protected: &[Value],
    day_cutoff: Option<&str>,
) -> EngineResult<Vec<u128>> {
    let mut occ = vec![0u128; 7];
    for window in protected {
        let start = unpacked_minutes(window["start"].as_str().unwrap_or("00:00"))?;
        let duration = window["duration_min"].as_i64().unwrap_or(0);
        if let Some(days) = window.get("days").and_then(Value::as_array) {
            for day in days {
                if let Some(d) = day.as_i64() {
                    add_occupancy(&mut occ, d, start, start + duration)?;
                }
            }
        }
    }
    if let Some(day_cutoff) = day_cutoff.filter(|text| !text.is_empty()) {
        let cutoff = unpacked_minutes(day_cutoff)?;
        for day in 0..7 {
            add_occupancy(&mut occ, day, cutoff, DAY_END_MIN)?;
        }
    }
    Ok(occ)
}

pub fn lateness_occupancy(day: i64, from_start: &str, minutes: i64) -> EngineResult<Vec<u128>> {
    let mut occ = vec![0u128; 7];
    let start = unpacked_minutes(from_start)?;
    add_occupancy(&mut occ, day, start, start + minutes)?;
    Ok(occ)
}

fn casefold_trim(s: Option<&str>) -> Option<String> {
    s.filter(|t| !crate::time::py_strip(t).is_empty())
        .map(|t| crate::casefold::casefold(crate::time::py_strip(t)))
}

pub fn study_rank(
    windows: &[Value],
    course: Option<&str>,
    day: i64,
    start_min: i64,
    duration_min: i64,
) -> i64 {
    let wanted = casefold_trim(course);
    let mut best = 2i64;
    for window in windows {
        let days: Vec<i64> = window
            .get("days")
            .and_then(Value::as_array)
            .map(|a| a.iter().filter_map(|v| v.as_i64()).collect())
            .unwrap_or_default();
        if !days.contains(&day) {
            continue;
        }
        let start_str = window["start"].as_str().unwrap_or("00:00");
        let parts: Vec<&str> = start_str.split(':').collect();
        let begin =
            parts[0].parse::<i64>().unwrap_or(0) * 60 + parts[1].parse::<i64>().unwrap_or(0);
        let win_dur = window["duration_min"].as_i64().unwrap_or(0);
        if !(begin <= start_min && start_min + duration_min <= begin + win_dur) {
            continue;
        }
        if window.get("subject").is_none_or(Value::is_null) {
            best = best.min(1);
        } else if let Some(wanted) = &wanted
            && window
                .get("subject")
                .and_then(Value::as_str)
                .map(|s| crate::casefold::casefold(crate::time::py_strip(s)))
                == Some(wanted.clone())
        {
            return 0;
        }
    }
    best
}

pub fn resolve_work_windows(windows: Option<&[Value]>) -> (Vec<Value>, bool) {
    if let Some(windows) = windows
        && !windows.is_empty()
    {
        return (windows.to_vec(), false);
    }
    (default_work_windows(), true)
}

fn merged_work_spans(
    windows: &[Value],
    course: Option<&str>,
    day: i64,
) -> EngineResult<Vec<(i64, i64)>> {
    let wanted = casefold_trim(course);
    let mut spans: Vec<(i64, i64)> = Vec::new();
    for window in windows {
        let days: Vec<i64> = window
            .get("days")
            .and_then(Value::as_array)
            .map(|a| a.iter().filter_map(|v| v.as_i64()).collect())
            .unwrap_or_default();
        if !days.contains(&day) {
            continue;
        }
        if let Some(subject) = window.get("subject").and_then(Value::as_str)
            && (wanted.is_none()
                || crate::casefold::casefold(crate::time::py_strip(subject))
                    != wanted.as_deref().unwrap_or(""))
        {
            continue;
        }
        let begin = clock_to_minutes(window["start"].as_str().unwrap_or("00:00"))?;
        let finish = clock_to_minutes(window["end"].as_str().unwrap_or("24:00"))?;
        if begin < finish {
            spans.push((begin, finish));
        }
    }
    if spans.is_empty() {
        return Ok(vec![]);
    }
    spans.sort_unstable();
    let mut merged = vec![spans[0]];
    for (begin, finish) in spans.into_iter().skip(1) {
        let (_last_begin, last_finish) = merged.last_mut().unwrap();
        if begin <= *last_finish {
            *last_finish = (*last_finish).max(finish);
        } else {
            merged.push((begin, finish));
        }
    }
    Ok(merged)
}

pub fn session_inside_work_windows(
    windows: &[Value],
    course: Option<&str>,
    day: i64,
    start_min: i64,
    duration_min: i64,
) -> EngineResult<bool> {
    let end_min = start_min + duration_min;
    Ok(merged_work_spans(windows, course, day)?
        .iter()
        .any(|(begin, finish)| *begin <= start_min && end_min <= *finish))
}

pub fn merge_occupancy(base: &[u128], extra: &[u128]) -> EngineResult<Vec<u128>> {
    if base.len() != extra.len() {
        let message = if extra.len() > base.len() {
            "zip() argument 2 is longer than argument 1"
        } else {
            "zip() argument 2 is shorter than argument 1"
        };
        return Err(EngineError::value(message));
    }
    Ok(base
        .iter()
        .zip(extra.iter())
        .map(|(left, right)| left | right)
        .collect())
}

pub fn spread_sessions(
    estimate_min: i64,
    focus_minutes: i64,
    planned_min: i64,
    due: &str,
    session_min: i64,
    from_date: &str,
) -> EngineResult<(Vec<Value>, i64)> {
    let remaining = unplanned_minutes(estimate_min, focus_minutes, planned_min);
    let remainder = remaining.rem_euclid(SLOT_MIN);
    let grid_total = remaining - remainder;
    let (due_day, _) = parse_due(due)?;
    let start = parse_iso_date(from_date)?;
    if remaining == 0 || start > due_day {
        return Ok((vec![], remaining));
    }
    let mut dates: Vec<NaiveDate> = Vec::new();
    let mut cursor = start;
    while cursor <= due_day {
        dates.push(cursor);
        cursor += Duration::days(1);
    }
    let mut sizes: Vec<i64> = Vec::new();
    let mut left = grid_total;
    while left >= session_min {
        sizes.push(session_min);
        left -= session_min;
    }
    if left > 0 {
        sizes.push(left);
    }
    let mut sessions: Vec<Value> = Vec::new();
    for (index, duration) in sizes.iter().enumerate() {
        let day = dates[index % dates.len()];
        let weekday = day.weekday().num_days_from_monday() as i64;
        sessions.push(json!({
            "week_start": monday_of(&iso_date(day))?,
            "date": iso_date(day),
            "days": [weekday],
            "duration_min": duration,
        }));
    }
    Ok((sessions, remainder))
}

// --- day.py ---

pub fn is_work_session(block: &Value) -> bool {
    if block.get("assignment_id").and_then(Value::as_str).is_none() {
        return false;
    }
    if block.get("kind").and_then(Value::as_str) == Some("flexible") {
        return true;
    }
    block.get("kind").and_then(Value::as_str) == Some("locked")
        && block.get("pomodoro_role").and_then(Value::as_str) == Some("work")
}

fn day_on_day(block: &Value, day_index: i64) -> bool {
    let days: Vec<i64> = block
        .get("days")
        .and_then(Value::as_array)
        .map(|a| a.iter().filter_map(|v| v.as_i64()).collect())
        .unwrap_or_default();
    if block.get("kind").and_then(Value::as_str) == Some("flexible")
        && block
            .get("completed")
            .and_then(Value::as_bool)
            .unwrap_or(false)
    {
        let pinned = block.get("completed_day").and_then(Value::as_i64);
        return match pinned {
            None => days.len() == 1 && days.first().copied() == Some(day_index),
            Some(p) => p == day_index,
        };
    }
    days.contains(&day_index)
}

fn dump_block(block: &Value) -> Value {
    block.clone()
}

fn due_soon(
    assignment_rows: &[(Value, i64)],
    agenda: NaiveDate,
    week_start: &str,
    weeks: &[(String, Vec<Value>)],
) -> EngineResult<Vec<Value>> {
    let planned = planned_minutes_by_id(weeks, week_start);
    let tomorrow = agenda + Duration::days(1);
    let mut items: Vec<Value> = Vec::new();
    for (body, revision) in assignment_rows {
        if body
            .get("completed")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            continue;
        }
        let (due_day, _) = parse_due(body["due"].as_str().unwrap_or(""))?;
        if due_day > tomorrow {
            continue;
        }
        let id = body["id"].as_str().unwrap_or("");
        let planned_min = planned.get(id).copied().unwrap_or(0);
        let mut item = body.clone();
        if let Some(obj) = item.as_object_mut() {
            obj.insert("revision".into(), json!(revision));
            obj.insert("planned_min".into(), json!(planned_min));
            obj.insert(
                "unplanned_min".into(),
                json!(unplanned_minutes(
                    body["estimate_min"].as_i64().unwrap_or(0),
                    body.get("focus_minutes")
                        .and_then(Value::as_i64)
                        .unwrap_or(0),
                    planned_min,
                )),
            );
        }
        items.push(item);
    }
    items.sort_by(|a, b| {
        let ka = due_sort_key(
            a.get("due").and_then(Value::as_str),
            a["id"].as_str().unwrap_or(""),
        )
        .unwrap();
        let kb = due_sort_key(
            b.get("due").and_then(Value::as_str),
            b["id"].as_str().unwrap_or(""),
        )
        .unwrap();
        ka.cmp(&kb)
    });
    Ok(items)
}

fn available_min(blocks: &[Value], day_index: i64) -> EngineResult<i64> {
    let mut mask = 0u128;
    for raw in blocks {
        if !day_on_day(raw, day_index) || raw.get("start").and_then(Value::as_str).is_none() {
            continue;
        }
        let days: Vec<i64> = raw
            .get("days")
            .and_then(Value::as_array)
            .map(|a| a.iter().filter_map(|v| v.as_i64()).collect())
            .unwrap_or_default();
        let interval = block_interval_on_day(
            &days,
            raw.get("start").and_then(Value::as_str),
            raw["duration_min"].as_i64().unwrap_or(0),
            day_index,
        )?;
        if let Some((start, end)) = interval {
            mask |= occupancy_between(start, end)?;
        }
    }
    Ok((SLOTS_PER_DAY - mask.count_ones() as i64) * SLOT_MIN)
}

fn planned(block: &Value) -> bool {
    block.get("start").and_then(Value::as_str).is_some()
        || block
            .get("completed")
            .and_then(Value::as_bool)
            .unwrap_or(false)
}

fn by_category(sessions: &[Value], locked: &[Value]) -> Vec<Value> {
    let mut groups: BTreeMap<Option<String>, (i64, i64)> = BTreeMap::new();
    for block in sessions.iter().chain(locked.iter()) {
        let category = block
            .get("category")
            .and_then(Value::as_str)
            .map(|s| s.to_string());
        let entry = groups.entry(category).or_insert((0, 0));
        let duration = block["duration_min"].as_i64().unwrap_or(0);
        if planned(block) {
            entry.0 += duration;
        }
        if is_work_session(block)
            && block
                .get("completed")
                .and_then(Value::as_bool)
                .unwrap_or(false)
        {
            entry.1 += duration;
        }
    }
    let mut ordered: Vec<(Option<String>, (i64, i64))> = groups.into_iter().collect();
    ordered.sort_by(|a, b| {
        b.1.0.cmp(&a.1.0).then_with(|| {
            a.0.as_deref()
                .unwrap_or("")
                .cmp(b.0.as_deref().unwrap_or(""))
        })
    });
    ordered
        .into_iter()
        .filter(|(_, (scheduled, focus))| *scheduled != 0 || *focus != 0)
        .map(|(category, (scheduled_min, focus_min))| {
            json!({
                "category": category,
                "scheduled_min": scheduled_min,
                "focus_min": focus_min,
            })
        })
        .collect()
}

fn next_action(sessions: &[Value], due_soon: &[Value]) -> Value {
    let mut starters: Vec<&Value> = sessions
        .iter()
        .filter(|b| {
            b.get("start").and_then(Value::as_str).is_some()
                && !b.get("completed").and_then(Value::as_bool).unwrap_or(false)
        })
        .collect();
    starters.sort_by(|a, b| {
        a["start"]
            .as_str()
            .unwrap_or("")
            .cmp(b["start"].as_str().unwrap_or(""))
            .then_with(|| {
                a["id"]
                    .as_str()
                    .unwrap_or("")
                    .cmp(b["id"].as_str().unwrap_or(""))
            })
    });
    if let Some(block) = starters.first() {
        return json!({"kind": "start", "block_id": block["id"]});
    }
    for item in due_soon {
        if item["unplanned_min"].as_i64().unwrap_or(0) > 0 {
            return json!({"kind": "plan", "assignment_id": item["id"]});
        }
    }
    json!({"kind": "add"})
}

pub fn build_day(
    date_str: &str,
    week_start: &str,
    blocks: &[Value],
    assignment_rows: &[(Value, i64)],
    weeks: &[(String, Vec<Value>)],
) -> EngineResult<Value> {
    let agenda = parse_iso_date(date_str)?;
    let monday = parse_iso_date(week_start)?;
    let day_index = (agenda - monday).num_days();
    let sessions: Vec<Value> = blocks
        .iter()
        .filter(|b| is_work_session(b) && day_on_day(b, day_index))
        .map(dump_block)
        .collect();
    let locked: Vec<Value> = blocks
        .iter()
        .filter(|b| {
            b.get("kind").and_then(Value::as_str) == Some("locked")
                && !is_work_session(b)
                && day_on_day(b, day_index)
        })
        .map(dump_block)
        .collect();
    let due_soon = due_soon(assignment_rows, agenda, week_start, weeks)?;
    let scheduled: i64 = sessions
        .iter()
        .chain(locked.iter())
        .filter(|b| planned(b))
        .map(|b| b["duration_min"].as_i64().unwrap_or(0))
        .sum();
    let focus: i64 = sessions
        .iter()
        .filter(|b| b.get("completed").and_then(Value::as_bool).unwrap_or(false))
        .map(|b| b["duration_min"].as_i64().unwrap_or(0))
        .sum();
    Ok(json!({
        "date": date_str,
        "week_start": week_start,
        "due_soon": due_soon,
        "sessions": sessions,
        "locked": locked,
        "next_action": next_action(&sessions, &due_soon),
        "workload": {
            "scheduled_min": scheduled,
            "focus_min": focus,
            "available_min": available_min(blocks, day_index)?,
            "by_category": by_category(&sessions, &locked),
        },
    }))
}

// --- month.py ---

fn dates_between(start: NaiveDate, end: NaiveDate) -> Vec<NaiveDate> {
    let mut days = Vec::new();
    let mut day = start;
    while day <= end {
        days.push(day);
        day += Duration::days(1);
    }
    days
}

fn month_on_day(block: &Value, day_index: i64) -> bool {
    block
        .get("days")
        .and_then(Value::as_array)
        .map(|a| a.iter().any(|v| v.as_i64() == Some(day_index)))
        .unwrap_or(false)
}

fn placed_on_day(block: &Value, day_index: i64) -> bool {
    block.get("start").and_then(Value::as_str).is_some() && month_on_day(block, day_index)
}

fn date_block(block: &Value) -> Value {
    let days: Vec<i64> = block
        .get("days")
        .and_then(Value::as_array)
        .map(|a| a.iter().filter_map(|v| v.as_i64()).collect())
        .unwrap_or_default();
    json!({
        "id": block["id"],
        "title": block["title"],
        "start": block.get("start"),
        "duration_min": block["duration_min"].as_i64().unwrap_or(0),
        "category": block.get("category"),
        "kind": block["kind"],
        "assignment_id": block.get("assignment_id"),
        "repeats": days.len() > 1,
        "pinned": block.get("pinned").and_then(Value::as_bool).unwrap_or(false),
        "completed": block.get("completed").and_then(Value::as_bool).unwrap_or(false),
    })
}

fn is_planned_session(block: &Value) -> bool {
    block.get("start").and_then(Value::as_str).is_some()
        && block
            .get("days")
            .and_then(Value::as_array)
            .map(|a| a.len() == 1)
            .unwrap_or(false)
}

fn session_pinned_on_day(block: &Value, day_index: i64) -> bool {
    let days: Vec<i64> = block
        .get("days")
        .and_then(Value::as_array)
        .map(|a| a.iter().filter_map(|v| v.as_i64()).collect())
        .unwrap_or_default();
    if !block
        .get("completed")
        .and_then(Value::as_bool)
        .unwrap_or(false)
    {
        return is_planned_session(block) && days.first().copied() == Some(day_index);
    }
    match block.get("completed_day").and_then(Value::as_i64) {
        None => days.len() == 1 && days.first().copied() == Some(day_index),
        Some(pinned) => pinned == day_index,
    }
}

fn is_undated_session(block: &Value) -> bool {
    block.get("kind").and_then(Value::as_str) == Some("flexible")
        && is_work_session(block)
        && !block
            .get("completed")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        && !is_planned_session(block)
}

fn assignment_details(body: &Value) -> (bool, bool, i64, i64) {
    let checklist = body
        .get("checklist")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let has_notes = body
        .get("notes")
        .and_then(Value::as_str)
        .map(|s| !s.trim().is_empty())
        .unwrap_or(false);
    let has_links = body
        .get("links")
        .and_then(Value::as_array)
        .is_some_and(|a| !a.is_empty());
    let done = checklist
        .iter()
        .filter(|item| item.get("done").and_then(Value::as_bool).unwrap_or(false))
        .count() as i64;
    (has_notes, has_links, checklist.len() as i64, done)
}

fn deadline_item(
    body: &Value,
    revision: i64,
    due_day: NaiveDate,
    planned: &BTreeMap<String, i64>,
) -> Value {
    let id = body["id"].as_str().unwrap_or("");
    json!({
        "id": id,
        "title": body["title"],
        "due": body["due"],
        "date": iso_date(due_day),
        "completed": body.get("completed").and_then(Value::as_bool).unwrap_or(false),
        "estimate_min": body["estimate_min"].as_i64().unwrap_or(0),
        "unplanned_min": unplanned_minutes(
            body["estimate_min"].as_i64().unwrap_or(0),
            body.get("focus_minutes").and_then(Value::as_i64).unwrap_or(0),
            planned.get(id).copied().unwrap_or(0),
        ),
        "revision": revision,
    })
}

pub fn build_month(
    month: &str,
    assignment_rows: &[(Value, i64)],
    weeks: &[(String, Vec<Value>)],
) -> EngineResult<Value> {
    let (start_s, end_s) = parse_month(month)?;
    let start = parse_iso_date(&start_s)?;
    let end = parse_iso_date(&end_s)?;
    let (grid_start_s, grid_end_s) = month_grid(&start_s, &end_s)?;
    let grid_start = parse_iso_date(&grid_start_s)?;
    let grid_end = parse_iso_date(&grid_end_s)?;
    let grid_days = dates_between(grid_start, grid_end);
    let mut weeks_by_start: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    for (ws, blocks) in weeks {
        weeks_by_start.insert(ws.clone(), blocks.clone());
    }
    let from_week = monday_of(&iso_date(start))?;
    let planned = planned_minutes_by_id(weeks, &from_week);

    let mut due_by_date: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    for day in &grid_days {
        due_by_date.insert(iso_date(*day), Vec::new());
    }
    let mut overdue: Vec<Value> = Vec::new();
    let mut assignment_due: BTreeMap<String, NaiveDate> = BTreeMap::new();
    for (body, revision) in assignment_rows {
        let (due_day, _) = parse_due(body["due"].as_str().unwrap_or(""))?;
        let id = body["id"].as_str().unwrap_or("").to_string();
        assignment_due.insert(id.clone(), due_day);
        let item = deadline_item(body, *revision, due_day, &planned);
        let key = iso_date(due_day);
        if due_by_date.contains_key(&key) {
            due_by_date.get_mut(&key).unwrap().push(item);
        } else if due_day < grid_start
            && !body
                .get("completed")
                .and_then(Value::as_bool)
                .unwrap_or(false)
        {
            overdue.push(item);
        }
    }
    for items in due_by_date.values_mut() {
        items.sort_by(|a, b| {
            let ka = due_sort_key(
                a.get("due").and_then(Value::as_str),
                a["id"].as_str().unwrap_or(""),
            )
            .unwrap();
            let kb = due_sort_key(
                b.get("due").and_then(Value::as_str),
                b["id"].as_str().unwrap_or(""),
            )
            .unwrap();
            ka.cmp(&kb)
        });
    }
    overdue.sort_by(|a, b| {
        let ka = due_sort_key(
            a.get("due").and_then(Value::as_str),
            a["id"].as_str().unwrap_or(""),
        )
        .unwrap();
        let kb = due_sort_key(
            b.get("due").and_then(Value::as_str),
            b["id"].as_str().unwrap_or(""),
        )
        .unwrap();
        ka.cmp(&kb)
    });

    let mut session_dates: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut days_out: Vec<Value> = Vec::new();
    for day in &grid_days {
        let label = iso_date(*day);
        let week_start = monday_of(&label)?;
        let day_index = day.weekday().num_days_from_monday() as i64;
        let blocks = weeks_by_start.get(&week_start).cloned().unwrap_or_default();
        let sessions: Vec<&Value> = blocks
            .iter()
            .filter(|block| {
                is_work_session(block)
                    && if block.get("kind").and_then(Value::as_str) == Some("locked") {
                        placed_on_day(block, day_index)
                    } else {
                        session_pinned_on_day(block, day_index)
                    }
            })
            .collect();
        let locked: Vec<&Value> = blocks
            .iter()
            .filter(|block| {
                block.get("kind").and_then(Value::as_str) == Some("locked")
                    && !is_work_session(block)
                    && placed_on_day(block, day_index)
            })
            .collect();
        for block in &sessions {
            if let Some(aid) = block.get("assignment_id").and_then(Value::as_str) {
                let seen = session_dates.entry(aid.to_string()).or_default();
                if !seen.contains(&label) {
                    seen.push(label.clone());
                }
            }
        }
        let due_items = due_by_date.get(&label).cloned().unwrap_or_default();
        let on_date: Vec<&Value> = sessions
            .iter()
            .copied()
            .chain(locked.iter().copied())
            .collect();
        let mut chips: Vec<Value> = on_date.iter().map(|b| date_block(b)).collect();
        chips.sort_by(|a, b| {
            a["start"]
                .as_str()
                .unwrap_or("")
                .cmp(b["start"].as_str().unwrap_or(""))
                .then_with(|| {
                    a["title"]
                        .as_str()
                        .unwrap_or("")
                        .cmp(b["title"].as_str().unwrap_or(""))
                })
        });
        days_out.push(json!({
            "date": label,
            "week_start": week_start,
            "in_month": start <= *day && *day <= end,
            "due_ids": due_items.iter().map(|i| i["id"].clone()).collect::<Vec<_>>(),
            "session_count": sessions.len(),
            "locked_count": locked.len(),
            "scheduled_min": on_date.iter().map(|b| b["duration_min"].as_i64().unwrap_or(0)).sum::<i64>(),
            "focus_min": sessions.iter().filter(|b| b.get("completed").and_then(Value::as_bool).unwrap_or(false)).map(|b| b["duration_min"].as_i64().unwrap_or(0)).sum::<i64>(),
            "blocks": chips,
        }));
    }

    let week_starts: std::collections::BTreeSet<String> = grid_days
        .iter()
        .map(|day| monday_of(&iso_date(*day)).unwrap())
        .collect();
    let undated: Vec<Value> = week_starts
        .iter()
        .flat_map(|week_start| {
            weeks_by_start
                .get(week_start)
                .cloned()
                .unwrap_or_default()
                .into_iter()
                .filter(|block| {
                    if !is_undated_session(block) {
                        return false;
                    }
                    let monday = parse_iso_date(week_start).unwrap();
                    block
                        .get("days")
                        .and_then(Value::as_array)
                        .map(|days| {
                            days.iter().any(|index| {
                                let d = monday + Duration::days(index.as_i64().unwrap_or(0));
                                grid_start <= d && d <= grid_end
                            })
                        })
                        .unwrap_or(false)
                })
        })
        .collect();

    let deadlines: Vec<Value> = grid_days
        .iter()
        .flat_map(|day| {
            due_by_date
                .get(&iso_date(*day))
                .cloned()
                .unwrap_or_default()
        })
        .collect();
    let mut visible_ids: std::collections::BTreeSet<String> = deadlines
        .iter()
        .chain(overdue.iter())
        .filter_map(|item| item["id"].as_str().map(str::to_string))
        .collect();
    visible_ids.extend(session_dates.keys().cloned());
    let by_id: BTreeMap<String, (Value, i64)> = assignment_rows
        .iter()
        .map(|(body, rev)| {
            (
                body["id"].as_str().unwrap_or("").to_string(),
                (body.clone(), *rev),
            )
        })
        .collect();
    let mut projects: Vec<Value> = Vec::new();
    for assignment_id in visible_ids {
        let Some((body, revision)) = by_id.get(&assignment_id) else {
            continue;
        };
        if body
            .get("completed")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            continue;
        }
        let (has_notes, has_links, checklist_total, checklist_done) = assignment_details(body);
        let dates = session_dates
            .get(&assignment_id)
            .cloned()
            .unwrap_or_default();
        if !(has_notes || has_links || checklist_total > 0 || dates.len() >= 2) {
            continue;
        }
        let due_day = assignment_due[&assignment_id];
        let mut item = deadline_item(body, *revision, due_day, &planned);
        if let Some(obj) = item.as_object_mut() {
            obj.insert("session_dates".into(), json!(dates));
            obj.insert("has_notes".into(), json!(has_notes));
            obj.insert("has_links".into(), json!(has_links));
            obj.insert("checklist_total".into(), json!(checklist_total));
            obj.insert("checklist_done".into(), json!(checklist_done));
        }
        projects.push(item);
    }
    projects.sort_by(|a, b| {
        let ka = due_sort_key(
            a.get("due").and_then(Value::as_str),
            a["id"].as_str().unwrap_or(""),
        )
        .unwrap();
        let kb = due_sort_key(
            b.get("due").and_then(Value::as_str),
            b["id"].as_str().unwrap_or(""),
        )
        .unwrap();
        ka.cmp(&kb)
    });

    Ok(json!({
        "month": month,
        "start": start_s,
        "end": end_s,
        "grid_start": grid_start_s,
        "grid_end": grid_end_s,
        "days": days_out,
        "deadlines": deadlines,
        "projects": projects,
        "overdue": overdue,
        "unscheduled": {
            "session_count": undated.len(),
            "minutes": undated.iter().map(|b| b["duration_min"].as_i64().unwrap_or(0)).sum::<i64>(),
        },
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn migrated_id_matches_python_sha256() {
        assert_eq!(
            migrated_assignment_id("2024-01-01", "block-1"),
            "a-f1780bbad147d7eced00e3db463e743f"
        );
    }

    #[test]
    fn unplanned_minutes_matches_python() {
        assert_eq!(unplanned_minutes(60, 10, 20), 30);
    }

    #[test]
    fn snap_minutes_matches_python() {
        assert_eq!(snap_minutes(17, 1, 180), 15);
        assert_eq!(snap_minutes(7, 1, 180), 15);
        assert_eq!(snap_minutes(185, 1, 180), 180);
    }

    #[test]
    fn split_plan_60_matches_python() {
        let plan = split_plan(60, 25, 5, 15, 4).unwrap();
        assert_eq!(plan["total_min"].as_i64(), Some(70));
        assert_eq!(plan["segments"].as_array().map(|a| a.len()), Some(5));
    }

    #[test]
    fn explain_copy_matches_python() {
        assert_eq!(slack_sentence(0, "ok"), "Finishes right when it is due.");
        assert_eq!(
            slack_sentence(29, "danger"),
            "Finishes only 29 min before it is due."
        );
        assert_eq!(
            slack_sentence(45, "ok"),
            "Finishes 45 min before it is due."
        );
        assert_eq!(
            sentence("NO_SLOT_LEFT").unwrap(),
            "Your plans and other homework already fill every gap long enough for it."
        );
    }

    #[test]
    fn due_placement_bound_matches_python() {
        assert_eq!(
            due_placement_bound("2024-01-01", "2024-01-03T12:00").unwrap(),
            Some((2, 720))
        );
        assert_eq!(
            due_placement_bound("2024-01-01", "2024-01-10T12:00").unwrap(),
            None
        );
        assert_eq!(
            due_placement_bound("2024-01-08", "2024-01-03T12:00").unwrap(),
            Some((0, 0))
        );
    }
}
