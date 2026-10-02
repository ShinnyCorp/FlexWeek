//! Restore snapshots, transfer size, and recovery-code text.
//! Random bytes for a new code are passed in. This module does not draw them.

use sha2::{Digest, Sha256};

use serde_json::{Map, Value};

pub const MAX_BODY: usize = 256 * 1024;
pub const TRANSFER_TOO_LARGE: &str = "This account is larger than the 256 KiB transfer limit.";
const APPLY_TOKEN_PAD: &str = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff";
const APPLY_OPERATION_PAD: &str =
    "oooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooo";

fn py_string(text: &str) -> String {
    let mut out = String::from("\"");
    for unit in text.encode_utf16() {
        let ch = char::from_u32(u32::from(unit));
        match ch {
            Some('"') => out.push_str("\\\""),
            Some('\\') => out.push_str("\\\\"),
            Some('\u{0008}') => out.push_str("\\b"),
            Some('\u{000c}') => out.push_str("\\f"),
            Some('\n') => out.push_str("\\n"),
            Some('\r') => out.push_str("\\r"),
            Some('\t') => out.push_str("\\t"),
            Some(c) if (c as u32) < 0x20 || (c as u32) >= 0x7f => {
                out.push_str(&format!("\\u{unit:04x}"));
            }
            Some(c) => out.push(c),
            None => out.push_str(&format!("\\u{unit:04x}")),
        }
    }
    out.push('"');
    out
}

fn py_number(number: &serde_json::Number) -> String {
    let raw = number.to_string();
    if raw.contains(['.', 'e', 'E']) {
        let value: f64 = raw.parse().unwrap_or(f64::NAN);
        return match value {
            v if v.is_nan() => "NaN".into(),
            v if v.is_infinite() && v > 0.0 => "Infinity".into(),
            v if v.is_infinite() => "-Infinity".into(),
            v => py_json_float(v),
        };
    }
    // `json.loads("-0")` is the int 0.
    if raw == "-0" { "0".into() } else { raw }
}

/// Python `repr` of a float.
pub(crate) fn py_float_repr(value: f64) -> String {
    match value {
        v if v.is_nan() => "nan".into(),
        v if v.is_infinite() && v > 0.0 => "inf".into(),
        v if v.is_infinite() => "-inf".into(),
        v => py_json_float(v),
    }
}

/// Python `json.dumps` prints a float with `repr`, and adds `.0` so it stays a float.
fn py_json_float(value: f64) -> String {
    if value == 0.0 {
        return if value.is_sign_negative() {
            "-0.0".into()
        } else {
            "0.0".into()
        };
    }
    let negative = value.is_sign_negative();
    let abs = value.abs();
    let raw = format!("{abs}");
    let scientific = abs < 1e-4 || abs >= 1e16;
    let digits = if scientific {
        if raw.contains('e') || raw.contains('E') {
            normalize_exp(&raw)
        } else {
            fixed_to_scientific(&raw)
        }
    } else if raw.contains('e') || raw.contains('E') {
        fixed_from_scientific(&raw)
    } else if raw.contains('.') {
        raw
    } else {
        format!("{raw}.0")
    };
    if negative {
        format!("-{digits}")
    } else {
        digits
    }
}

fn normalize_exp(raw: &str) -> String {
    let Some((body, exp)) = raw.split_once(['e', 'E']) else {
        return raw.to_string();
    };
    let Ok(exp) = exp.parse::<i32>() else {
        return raw.to_string();
    };
    format!("{body}e{exp:+03}")
}

fn fixed_to_scientific(text: &str) -> String {
    let digits_only: String = text.chars().filter(|ch| ch.is_ascii_digit()).collect();
    let first = digits_only.find(|ch: char| ch != '0').unwrap_or(0);
    let point = text.find('.').unwrap_or(text.len());
    let int_digits = text[..point]
        .chars()
        .filter(|ch| ch.is_ascii_digit())
        .count();
    let exp = int_digits as i32 - first as i32 - 1;
    let mut sig = digits_only[first..].trim_end_matches('0').to_string();
    if sig.is_empty() {
        sig = "0".into();
    }
    if sig.len() > 1 {
        sig.insert(1, '.');
    }
    format!("{sig}e{exp:+03}")
}

fn fixed_from_scientific(raw: &str) -> String {
    let (body, exp) = raw.split_once(['e', 'E']).unwrap_or((raw, "0"));
    let exp: i32 = exp.parse().unwrap_or(0);
    let negative_body = body.starts_with('-');
    let body = body.trim_start_matches('-');
    let mut digits: String = body.chars().filter(|ch| *ch != '.').collect();
    let point = body.find('.').unwrap_or(body.len());
    let point = point as i32 + exp;
    if point <= 0 {
        let zeros = "0".repeat((-point) as usize);
        digits = format!("0.{zeros}{digits}");
    } else if point as usize >= digits.len() {
        digits.push_str(&"0".repeat(point as usize - digits.len()));
        digits.push_str(".0");
    } else {
        digits.insert(point as usize, '.');
    }
    if negative_body {
        format!("-{digits}")
    } else {
        digits
    }
}

fn json_text(value: &Value, comma: &str, colon: &str) -> String {
    match value {
        Value::Null => "null".to_string(),
        Value::Bool(true) => "true".to_string(),
        Value::Bool(false) => "false".to_string(),
        Value::Number(number) => py_number(number),
        Value::String(text) => py_string(text),
        Value::Array(items) => {
            let parts: Vec<String> = items
                .iter()
                .map(|item| json_text(item, comma, colon))
                .collect();
            format!("[{}]", parts.join(comma))
        }
        Value::Object(map) => {
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            let parts: Vec<String> = keys
                .into_iter()
                .map(|key| {
                    format!(
                        "{}{colon}{}",
                        py_string(key),
                        json_text(&map[key], comma, colon)
                    )
                })
                .collect();
            format!("{{{}}}", parts.join(comma))
        }
    }
}

fn canonical_value(value: &Value) -> String {
    json_text(value, ",", ":")
}

pub fn canonical(value: &Value) -> String {
    canonical_value(value)
}

/// `json.dumps(value, sort_keys=True)` with Python's default `", "` and `": "` separators.
pub fn dumps_sorted(value: &Value) -> String {
    json_text(value, ", ", ": ")
}

/// `json.dumps(value, indent=indent)`: keys in the order they were written, every non-ASCII
/// character escaped, an empty list or dict as `[]` or `{}`.
pub fn dumps_indent(value: &Value, indent: usize) -> String {
    fn walk(value: &Value, indent: usize, level: usize, out: &mut String) {
        let pad = |depth: usize| " ".repeat(indent * depth);
        match value {
            Value::Array(items) if !items.is_empty() => {
                out.push('[');
                for (index, item) in items.iter().enumerate() {
                    out.push_str(if index == 0 { "\n" } else { ",\n" });
                    out.push_str(&pad(level + 1));
                    walk(item, indent, level + 1, out);
                }
                out.push('\n');
                out.push_str(&pad(level));
                out.push(']');
            }
            Value::Object(map) if !map.is_empty() => {
                out.push('{');
                for (index, (key, item)) in map.iter().enumerate() {
                    out.push_str(if index == 0 { "\n" } else { ",\n" });
                    out.push_str(&pad(level + 1));
                    out.push_str(&py_string(key));
                    out.push_str(": ");
                    walk(item, indent, level + 1, out);
                }
                out.push('\n');
                out.push_str(&pad(level));
                out.push('}');
            }
            other => out.push_str(&json_text(other, ", ", ": ")),
        }
    }
    let mut out = String::new();
    walk(value, indent, 0, &mut out);
    out
}

pub fn state_token(snapshot: &Value) -> String {
    let digest = Sha256::digest(canonical(snapshot).as_bytes());
    hex::encode(digest)
}

fn title_of(row: &Value) -> String {
    let mut body = row.get("body").cloned().unwrap_or(Value::Null);
    if let Value::String(text) = &body {
        body = serde_json::from_str(text).unwrap_or(Value::Null);
    }
    body.get("title")
        .map(|item| match item {
            Value::String(text) => text.clone(),
            other => canonical_value(other).trim_matches('"').to_string(),
        })
        .unwrap_or_default()
}

fn reference(row: &Value) -> Value {
    serde_json::json!({
        "id": row.get("id").cloned().unwrap_or(Value::Null),
        "title": title_of(row),
    })
}

pub fn diff_snapshots(current: &Value, stored: &Value) -> Value {
    let weeks = |root: &Value| -> Map<String, Value> {
        let mut out = Map::new();
        for row in root
            .get("weeks")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            if let Some(start) = row.get("week_start").and_then(Value::as_str) {
                out.insert(
                    start.to_string(),
                    row.get("blocks").cloned().unwrap_or(Value::Null),
                );
            }
        }
        out
    };
    let assignments = |root: &Value| -> Map<String, Value> {
        let mut out = Map::new();
        for row in root
            .get("assignments")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            if let Some(id) = row.get("id").and_then(Value::as_str) {
                out.insert(id.to_string(), row.clone());
            }
        }
        out
    };
    let current_weeks = weeks(current);
    let stored_weeks = weeks(stored);
    let current_assignments = assignments(current);
    let stored_assignments = assignments(stored);
    let mut weeks_added: Vec<&String> = stored_weeks
        .keys()
        .filter(|key| !current_weeks.contains_key(key.as_str()))
        .collect();
    weeks_added.sort();
    let mut weeks_removed: Vec<&String> = current_weeks
        .keys()
        .filter(|key| !stored_weeks.contains_key(key.as_str()))
        .collect();
    weeks_removed.sort();
    let mut weeks_changed: Vec<&String> = stored_weeks
        .keys()
        .filter(|key| {
            current_weeks.get(key.as_str()).is_some_and(|blocks| {
                canonical(blocks) != canonical(stored_weeks.get(key.as_str()).unwrap())
            })
        })
        .collect();
    weeks_changed.sort();
    let mut added_ids: Vec<&String> = stored_assignments
        .keys()
        .filter(|key| !current_assignments.contains_key(key.as_str()))
        .collect();
    added_ids.sort();
    let mut removed_ids: Vec<&String> = current_assignments
        .keys()
        .filter(|key| !stored_assignments.contains_key(key.as_str()))
        .collect();
    removed_ids.sort();
    let mut changed_ids: Vec<&String> = stored_assignments
        .keys()
        .filter(|key| {
            let Some(current_row) = current_assignments.get(key.as_str()) else {
                return false;
            };
            let stored_row = stored_assignments.get(key.as_str()).unwrap();
            canonical(stored_row.get("body").unwrap_or(&Value::Null))
                != canonical(current_row.get("body").unwrap_or(&Value::Null))
        })
        .collect();
    changed_ids.sort();
    serde_json::json!({
        "weeks": {
            "added": weeks_added,
            "changed": weeks_changed,
            "removed": weeks_removed,
        },
        "assignments": {
            "added": added_ids.iter().map(|id| reference(&stored_assignments[*id])).collect::<Vec<_>>(),
            "changed": changed_ids.iter().map(|id| reference(&stored_assignments[*id])).collect::<Vec<_>>(),
            "removed": removed_ids.iter().map(|id| reference(&current_assignments[*id])).collect::<Vec<_>>(),
        }
    })
}

fn routine_core(row: &Value) -> Value {
    serde_json::json!({
        "id": row.get("id").cloned().unwrap_or(Value::Null),
        "name": row.get("name").cloned().unwrap_or(Value::Null),
        "blocks": row.get("blocks").cloned().unwrap_or(Value::Null),
        "revision": row.get("revision").cloned().unwrap_or(Value::Null),
    })
}

pub fn diff_transfer(current: &Value, incoming: &Value) -> Value {
    let mut changes = diff_snapshots(current, incoming);
    let routines = |root: &Value, key: &str| -> Map<String, Value> {
        let mut out = Map::new();
        for row in root
            .get(key)
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            if let Some(id) = row.get("id").and_then(Value::as_str) {
                out.insert(id.to_string(), row.clone());
            }
        }
        out
    };
    let current_routines = routines(current, "routines");
    let incoming_routines = routines(incoming, "routines");
    let mut added: Vec<&String> = incoming_routines
        .keys()
        .filter(|key| !current_routines.contains_key(key.as_str()))
        .collect();
    added.sort();
    let mut removed: Vec<&String> = current_routines
        .keys()
        .filter(|key| !incoming_routines.contains_key(key.as_str()))
        .collect();
    removed.sort();
    let mut changed: Vec<&String> = incoming_routines
        .keys()
        .filter(|key| {
            current_routines.get(key.as_str()).is_some_and(|row| {
                canonical(&routine_core(row))
                    != canonical(&routine_core(incoming_routines.get(key.as_str()).unwrap()))
            })
        })
        .collect();
    changed.sort();
    let name = |rows: &Map<String, Value>, id: &str| {
        rows.get(id)
            .and_then(|row| row.get("name"))
            .cloned()
            .unwrap_or(Value::Null)
    };
    if let Some(object) = changes.as_object_mut() {
        object.insert(
            "routines".into(),
            serde_json::json!({
                "added": added.iter().map(|id| serde_json::json!({"id": id, "name": name(&incoming_routines, id)})).collect::<Vec<_>>(),
                "changed": changed.iter().map(|id| serde_json::json!({"id": id, "name": name(&incoming_routines, id)})).collect::<Vec<_>>(),
                "removed": removed.iter().map(|id| serde_json::json!({"id": id, "name": name(&current_routines, id)})).collect::<Vec<_>>(),
            }),
        );
        let prefs_changed = canonical(current.get("preferences").unwrap_or(&Value::Null))
            != canonical(incoming.get("preferences").unwrap_or(&Value::Null));
        object.insert("preferences_changed".into(), Value::Bool(prefs_changed));
    }
    changes
}

pub fn transfer_apply_envelope(snapshot: &Value) -> Value {
    serde_json::json!({
        "snapshot": snapshot,
        "state_token": APPLY_TOKEN_PAD,
        "operation_id": APPLY_OPERATION_PAD,
    })
}

pub fn transfer_apply_bytes(snapshot: &Value) -> usize {
    // Python json.dumps keeps the dict's key order and does not sort it.
    fn dump(value: &Value) -> String {
        match value {
            Value::Null => "null".to_string(),
            Value::Bool(true) => "true".to_string(),
            Value::Bool(false) => "false".to_string(),
            Value::Number(number) => py_number(number),
            Value::String(text) => py_string(text),
            Value::Array(items) => {
                let parts: Vec<String> = items.iter().map(dump).collect();
                format!("[{}]", parts.join(","))
            }
            Value::Object(map) => {
                let parts: Vec<String> = map
                    .iter()
                    .map(|(key, item)| format!("{}:{}", py_string(key), dump(item)))
                    .collect();
                format!("{{{}}}", parts.join(","))
            }
        }
    }
    dump(&transfer_apply_envelope(snapshot)).len()
}

pub fn transfer_fits(snapshot: &Value) -> bool {
    transfer_apply_bytes(snapshot) <= MAX_BODY
}

pub fn format_recovery_code(raw_hex: &str) -> String {
    let chars: Vec<char> = raw_hex.chars().collect();
    let take = |start: usize, end: usize| -> String {
        chars
            .get(start..end.min(chars.len()).max(start))
            .unwrap_or(&[])
            .iter()
            .collect()
    };
    format!(
        "{}-{}-{}-{}",
        take(0, 4),
        take(4, 8),
        take(8, 12),
        take(12, chars.len())
    )
}

pub fn recovery_code_well_formed(code: &str) -> bool {
    let mut parts = code.split('-');
    let ok = |part: Option<&str>| {
        part.is_some_and(|text| text.len() == 4 && text.bytes().all(|b| b.is_ascii_hexdigit()))
    };
    ok(parts.next())
        && ok(parts.next())
        && ok(parts.next())
        && ok(parts.next())
        && parts.next().is_none()
        && code.bytes().all(|b| b.is_ascii_hexdigit() || b == b'-')
        && code.chars().all(|ch| !ch.is_ascii_uppercase())
}

pub fn normalize_recovery_code(value: &str) -> String {
    value
        .chars()
        .filter(|ch| ch.is_ascii_hexdigit())
        .flat_map(|ch| ch.to_lowercase())
        .collect()
}

pub fn hash_recovery_code(value: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(b"flexweek-recovery:");
    hasher.update(normalize_recovery_code(value).as_bytes());
    hex::encode(hasher.finalize())
}

/// One `secrets.token_bytes` draw. `None` when the code is a repeat or not four hex groups.
pub fn accept_recovery_draw(
    raw: &[u8],
    seen: &mut std::collections::BTreeSet<String>,
) -> Option<String> {
    let code = format_recovery_code(&hex::encode(raw));
    let digest = hash_recovery_code(&code);
    if seen.contains(&digest) || !recovery_code_well_formed(&code) {
        return None;
    }
    seen.insert(digest);
    Some(code)
}

pub fn recovery_codes_from_draws(count: usize, draws: &[&[u8]]) -> Vec<String> {
    let mut seen = std::collections::BTreeSet::new();
    let mut codes = Vec::new();
    for raw in draws {
        if codes.len() >= count {
            break;
        }
        if let Some(code) = accept_recovery_draw(raw, &mut seen) {
            codes.push(code);
        }
    }
    codes
}

pub fn recovery_code_matches(presented: &str, stored_hash: &str) -> crate::EngineResult<bool> {
    let digest = hash_recovery_code(presented);
    if !digest.is_ascii() || !stored_hash.is_ascii() {
        return Err(crate::EngineError {
            kind: crate::ErrorKind::Type,
            message: "comparing strings with non-ASCII characters is not supported".into(),
        });
    }
    Ok(eq_ascii(digest.as_bytes(), stored_hash.as_bytes()))
}

fn eq_ascii(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    let mut diff = 0u8;
    for (left, right) in left.iter().zip(right.iter()) {
        diff |= left ^ right;
    }
    diff == 0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn floats_match_python_json() {
        let cases = [
            ("1e-05", "1e-05"),
            ("0.0001", "0.0001"),
            ("1.0", "1.0"),
            ("1e+16", "1e+16"),
            ("1.192092896e-07", "1.192092896e-07"),
            ("1.7366396438412993e-304", "1.7366396438412993e-304"),
            ("3.8073887657203757e-295", "3.8073887657203757e-295"),
            ("0", "0"),
            ("1", "1"),
            ("10.0", "10.0"),
            ("-0.0", "-0.0"),
        ];
        for (input, want) in cases {
            let value: Value = serde_json::from_str(input).unwrap();
            assert_eq!(canonical_value(&value), want, "{input} -> {value}");
        }
    }

    #[test]
    fn draws_skip_a_duplicate_and_a_short_code() {
        let draws: &[&[u8]] = &[
            &[0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77],
            &[0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77],
            &[0xab],
            &[0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff, 0x00, 0x11],
        ];
        assert_eq!(
            recovery_codes_from_draws(2, draws),
            vec![
                "0011-2233-4455-6677".to_string(),
                "aabb-ccdd-eeff-0011".to_string(),
            ]
        );
        assert!(recovery_codes_from_draws(0, draws).is_empty());
    }

    #[test]
    fn compare_matches_hmac_on_ascii_and_rejects_non_ascii() {
        let digest = "2115f4faa2798a135efc96595d802aa15ef8a2e8099efa8483b6ee97296c45e2";
        assert_eq!(hash_recovery_code("0011-2233-4455-6677"), digest);
        assert!(recovery_code_matches("0011-2233-4455-6677", digest).unwrap());
        assert!(!recovery_code_matches("0011-2233-4455-6677", "abcd").unwrap());
        assert!(!recovery_code_matches("0011-2233-4455-6677", &"\u{7f}".repeat(64)).unwrap());
        let err = recovery_code_matches("0011-2233-4455-6677", "é").unwrap_err();
        assert_eq!(err.kind, crate::ErrorKind::Type);
        assert_eq!(
            err.message,
            "comparing strings with non-ASCII characters is not supported"
        );
        let err = recovery_code_matches("0011-2233-4455-6677", "\u{80}").unwrap_err();
        assert_eq!(err.kind, crate::ErrorKind::Type);
        assert_eq!(
            err.message,
            "comparing strings with non-ASCII characters is not supported"
        );
    }
}
