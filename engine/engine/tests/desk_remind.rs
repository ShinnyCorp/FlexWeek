//! Rust twin of `desktop/tests/test_remind.py`: reminder lead windows and alarm snooze.

mod common;

use common::desk::{utc_ms, with};
use flexweek_engine::EngineResult;
use flexweek_engine::desk::remind::{
    self, ALARM_SNOOZE_MS, clock_parts, millis_of, seconds_of, snooze_until, start_alert_due,
};
use serde_json::{Value, json};
use std::collections::HashSet;

// The calls below encode their arguments as the Python wrappers in desktop/native/remind.py do
// (a set as a list, an absent trace as null) and hand the engine's answer back; the one thing the
// binding does besides is adding the keys the engine reports to the caller's set, so this does too.

fn sorted(set: &HashSet<String>) -> Value {
    let mut names: Vec<&String> = set.iter().collect();
    names.sort();
    json!(names)
}

fn due_reminders(
    blocks: &[Value],
    trace: Option<&Value>,
    today_iso: &str,
    now_min: i64,
    lead_min: i64,
    fired: &HashSet<String>,
) -> Vec<Value> {
    due_reminders_with(
        blocks, trace, today_iso, now_min, lead_min, fired, "", false,
    )
}

#[allow(clippy::too_many_arguments)]
fn due_reminders_with(
    blocks: &[Value],
    trace: Option<&Value>,
    today_iso: &str,
    now_min: i64,
    lead_min: i64,
    fired: &HashSet<String>,
    default_link: &str,
    sound_is_spotify: bool,
) -> Vec<Value> {
    remind::due_reminders(
        &json!(blocks),
        trace.unwrap_or(&Value::Null),
        today_iso,
        now_min,
        lead_min,
        &sorted(fired),
        true,
        &json!(default_link),
        sound_is_spotify,
    )
    .expect("due")
}

fn due_songs(
    blocks: &[Value],
    trace: Option<&Value>,
    today_iso: &str,
    now_min: i64,
    played: &HashSet<String>,
) -> Vec<Value> {
    due_songs_with(blocks, trace, today_iso, now_min, 0, played, "", false)
}

#[allow(clippy::too_many_arguments)]
fn due_songs_with(
    blocks: &[Value],
    trace: Option<&Value>,
    today_iso: &str,
    now_min: i64,
    lead_min: i64,
    played: &HashSet<String>,
    default_link: &str,
    sound_is_spotify: bool,
) -> Vec<Value> {
    remind::due_songs(
        &json!(blocks),
        trace.unwrap_or(&Value::Null),
        today_iso,
        now_min,
        lead_min,
        &sorted(played),
        true,
        &json!(default_link),
        sound_is_spotify,
    )
    .expect("songs")
}

type Alarms = (Vec<Value>, Vec<(Value, Value)>, i64);

#[allow(clippy::too_many_arguments)]
fn due_alarms(
    alarms: &[Value],
    today_iso: &str,
    weekday: i64,
    now_ms: i64,
    last_check_ms: Option<i64>,
    fired: &mut HashSet<String>,
    snoozed: &[(String, i64)],
    due_ms_of: &mut dyn FnMut(i64, i64) -> EngineResult<i64>,
) -> Alarms {
    let waiting: serde_json::Map<String, Value> = snoozed
        .iter()
        .map(|(id, due)| (id.clone(), json!(due)))
        .collect();
    let mut added = Vec::new();
    let found = remind::due_alarms(
        &json!(alarms),
        today_iso,
        weekday,
        now_ms,
        last_check_ms,
        &sorted(fired),
        true,
        &mut added,
        &Value::Object(waiting),
        due_ms_of,
    );
    fired.extend(added);
    found.expect("alarms")
}

#[test]
fn test_start_alert_due_from_the_lead_to_the_start() {
    // 16:00 start, 5 minute lead: due from 15:55 through the 16:00 minute, never after.
    assert!(start_alert_due(16 * 60, 15 * 60 + 55, 5));
    assert!(!start_alert_due(16 * 60, 15 * 60 + 54, 5));
    assert!(start_alert_due(16 * 60, 15 * 60 + 58, 5));
    assert!(start_alert_due(16 * 60, 16 * 60, 5));
    assert!(!start_alert_due(16 * 60, 16 * 60 + 1, 5));
    assert!(start_alert_due(16 * 60, 16 * 60, 0));
    assert!(!start_alert_due(16 * 60, 15 * 60 + 55, 0));
}

#[test]
fn test_due_reminders_fire_once_per_block_start() {
    let blocks = [json!({
        "id": "soccer",
        "title": "Soccer",
        "kind": "locked",
        "start": "16:00",
        "days": [0],
        "completed": false,
        "missed_days": [],
    })];
    let mut fired: HashSet<String> = HashSet::new();
    let first = due_reminders(&blocks, None, "2026-09-14", 15 * 60 + 55, 5, &fired);
    assert_eq!(first.len(), 1);
    assert_eq!(first[0]["title"], "Soccer starts soon");
    fired.insert(first[0]["key"].as_str().expect("key").to_string());
    let again = due_reminders(&blocks, None, "2026-09-14", 15 * 60 + 56, 5, &fired);
    assert_eq!(again, Vec::<Value>::new());
    let at_start = due_reminders(&blocks, None, "2026-09-14", 16 * 60, 0, &HashSet::new());
    assert_eq!(at_start.len(), 1);
}

#[test]
fn test_completed_and_missed_blocks_do_not_remind() {
    let blocks = [
        json!({
            "id": "done",
            "title": "Done",
            "kind": "locked",
            "start": "16:00",
            "days": [0],
            "completed": true,
            "missed_days": [],
        }),
        json!({
            "id": "missed",
            "title": "Missed",
            "kind": "locked",
            "start": "16:00",
            "days": [0],
            "completed": false,
            "missed_days": [0],
        }),
    ];
    assert_eq!(
        due_reminders(
            &blocks,
            None,
            "2026-09-14",
            15 * 60 + 55,
            5,
            &HashSet::new()
        ),
        Vec::<Value>::new()
    );
}

#[test]
fn test_alarm_fires_once_then_snoozes_five_minutes() {
    let now_ms = utc_ms(2026, 9, 14, 7, 0);
    let midnight_ms = utc_ms(2026, 9, 14, 0, 0);
    let clock = clock_parts(now_ms, (2026, 9, 14, 7, 0), midnight_ms).expect("clock parts");
    let today = clock["iso"].as_str().expect("iso").to_string();
    let weekday = clock["day"].as_i64().expect("day");
    assert_eq!(clock["midnight_ms"], json!(midnight_ms));
    let alarm =
        json!({"id": "wake", "name": "Wake", "time": "07:00", "days": [0], "enabled": true});
    let due_ms_of = |hour: i64, minute: i64| {
        Ok(millis_of(
            seconds_of(midnight_ms) + (hour * 60 + minute) as f64 * 60.0,
        ))
    };
    let mut fired: HashSet<String> = HashSet::new();
    let (queued, _snoozed, last) = due_alarms(
        std::slice::from_ref(&alarm),
        &today,
        weekday,
        now_ms,
        Some(now_ms - 60_000),
        &mut fired,
        &[],
        &mut { due_ms_of },
    );
    let queued_ids: Vec<&Value> = queued.iter().map(|item| &item["id"]).collect();
    assert_eq!(queued_ids, ["wake"]);
    let until = snooze_until(now_ms);
    assert_eq!(until - now_ms, ALARM_SNOOZE_MS);
    let (later, remaining, _last) = due_alarms(
        std::slice::from_ref(&alarm),
        &today,
        weekday,
        until,
        Some(last),
        &mut fired,
        &[("wake".to_string(), until)],
        &mut { due_ms_of },
    );
    let later_ids: Vec<&Value> = later.iter().map(|item| &item["id"]).collect();
    assert_eq!(later_ids, ["wake"]);
    assert_eq!(remaining, Vec::<(Value, Value)>::new());
}

#[test]
fn test_alarm_fires_at_seven_on_a_daylight_saving_day() {
    // The Python test sets TZ to America/New_York and lets the wrapper read the local clock. The
    // engine never reads a zone: it takes the day's 07:00 from the caller. So the three days are
    // laid out as that zone gives them, in whole hours from local midnight to local 07:00:
    // 6 on the spring-forward day, 8 on the fall-back day, 7 on an ordinary one.
    let alarm =
        json!({"id": "wake", "name": "Wake", "time": "07:00", "days": [6], "enabled": true});
    let queued_at = |year: i32, month: u32, day: u32, hours_since_midnight: i64| -> Vec<String> {
        let midnight_ms = utc_ms(year, month, day, 0, 0);
        let now_ms = millis_of(seconds_of(midnight_ms) + hours_since_midnight as f64 * 3_600.0);
        let today = format!("{year:04}-{month:02}-{day:02}");
        let clock =
            clock_parts(now_ms, (year, month, day, 7, 0), midnight_ms).expect("clock parts");
        // The engine never reads a zone. Local 07:00 on that date is `hours_since_midnight`
        // after local midnight, which is 6 on the spring-forward day, 8 on the fall-back day,
        // 7 on an ordinary one.
        let mut due_ms_of = |hour: i64, minute: i64| {
            Ok(millis_of(
                seconds_of(midnight_ms)
                    + (hour + hours_since_midnight - 7) as f64 * 3_600.0
                    + minute as f64 * 60.0,
            ))
        };
        let (queued, _, _) = due_alarms(
            std::slice::from_ref(&alarm),
            &today,
            clock["day"].as_i64().expect("day"),
            now_ms,
            Some(now_ms - 60_000),
            &mut HashSet::new(),
            &[],
            &mut due_ms_of,
        );
        queued
            .iter()
            .map(|item| item["id"].as_str().expect("id").to_string())
            .collect()
    };
    assert_eq!(queued_at(2026, 3, 8, 6), ["wake"]);
    assert_eq!(queued_at(2026, 11, 1, 8), ["wake"]);
    assert_eq!(queued_at(2026, 9, 13, 7), ["wake"]);
}

const THURSDAY: &str = "2026-09-17";

fn practice() -> Value {
    json!({
        "id": "practice",
        "title": "Guitar practice",
        "kind": "locked",
        "start": "18:45",
        "days": [3],
        "completed": false,
        "missed_days": [],
    })
}

/// Each minute checked in turn, as the poll does, keeping what has fired.
fn reminded(minutes: std::ops::Range<i64>, lead: i64, block: &Value) -> Vec<(i64, String)> {
    let mut fired: HashSet<String> = HashSet::new();
    let mut seen = Vec::new();
    for minute in minutes {
        let due = due_reminders(
            std::slice::from_ref(block),
            None,
            THURSDAY,
            minute,
            lead,
            &fired,
        );
        for item in due {
            fired.insert(item["key"].as_str().expect("key").to_string());
            seen.push((minute, item["title"].as_str().expect("title").to_string()));
        }
    }
    seen
}

#[test]
fn test_a_block_first_seen_inside_its_lead_reminds_at_the_first_check() {
    // Saved at 18:38 for 18:45 with a 10-minute lead: the lead began at 18:35.
    assert_eq!(
        reminded(18 * 60 + 38..19 * 60, 10, &practice()),
        [(18 * 60 + 38, "Guitar practice starts soon".to_string())]
    );
}

#[test]
fn test_a_block_first_seen_in_its_start_minute_says_it_starts_now() {
    assert_eq!(
        reminded(18 * 60 + 45..19 * 60, 10, &practice()),
        [(18 * 60 + 45, "Guitar practice starts now".to_string())]
    );
}

#[test]
fn test_a_block_that_has_started_does_not_remind() {
    assert_eq!(reminded(18 * 60 + 46..19 * 60, 10, &practice()), []);
}

#[test]
fn test_a_block_with_a_song_is_announced_by_the_song_at_its_start() {
    let block = with(
        practice(),
        json!({"spotify_url": "https://open.spotify.com/track/abc"}),
    );
    assert_eq!(reminded(18 * 60 + 45..19 * 60, 0, &block), []);
    let mut played: HashSet<String> = HashSet::new();
    let mut songs: Vec<(i64, String, String)> = Vec::new();
    for minute in 18 * 60 + 40..19 * 60 {
        let due = due_songs(
            std::slice::from_ref(&block),
            None,
            THURSDAY,
            minute,
            &played,
        );
        for song in due {
            played.insert(song["id"].as_str().expect("id").to_string());
            songs.push((
                minute,
                song["name"].as_str().expect("name").to_string(),
                song["spotify_url"].as_str().expect("url").to_string(),
            ));
        }
    }
    assert_eq!(
        songs,
        [(
            18 * 60 + 45,
            "Guitar practice".to_string(),
            "https://open.spotify.com/track/abc".to_string()
        )]
    );
    let start = 18 * 60 + 45;
    assert_eq!(
        due_songs(&[practice()], None, THURSDAY, start, &HashSet::new()),
        Vec::<Value>::new()
    );
}

const DEFAULT_SONG: &str = "https://open.spotify.com/playlist/settings";
const OWN_SONG: &str = "https://open.spotify.com/track/own";

/// The links of the songs due at each minute checked in turn, with what has played kept.
fn sung(
    minutes: std::ops::Range<i64>,
    lead: i64,
    block: &Value,
    default_link: &str,
    sound_is_spotify: bool,
) -> Vec<(i64, String)> {
    let mut played: HashSet<String> = HashSet::new();
    let mut seen = Vec::new();
    for minute in minutes {
        let due = due_songs_with(
            std::slice::from_ref(block),
            None,
            THURSDAY,
            minute,
            lead,
            &played,
            default_link,
            sound_is_spotify,
        );
        for song in due {
            played.insert(song["id"].as_str().expect("id").to_string());
            seen.push((
                minute,
                song["spotify_url"].as_str().expect("url").to_string(),
            ));
        }
    }
    seen
}

#[test]
fn test_a_block_without_a_link_plays_the_settings_link_when_the_sound_is_spotify() {
    assert_eq!(
        sung(18 * 60 + 40..19 * 60, 5, &practice(), DEFAULT_SONG, true),
        [(18 * 60 + 45, DEFAULT_SONG.to_string())]
    );
}

#[test]
fn test_a_block_with_its_own_link_plays_that_link_not_the_settings_one() {
    let block = with(practice(), json!({"spotify_url": OWN_SONG}));
    assert_eq!(
        sung(18 * 60 + 40..19 * 60, 5, &block, DEFAULT_SONG, true),
        [(18 * 60 + 45, OWN_SONG.to_string())]
    );
    // The block's own link plays whatever the chosen sound is, as before.
    assert_eq!(
        sung(18 * 60 + 40..19 * 60, 5, &block, DEFAULT_SONG, false),
        [(18 * 60 + 45, OWN_SONG.to_string())]
    );
}

#[test]
fn test_a_block_without_a_link_plays_nothing_when_the_sound_is_not_spotify() {
    assert_eq!(
        sung(18 * 60 + 40..19 * 60, 5, &practice(), DEFAULT_SONG, false),
        []
    );
}

#[test]
fn test_a_block_without_a_link_plays_nothing_when_the_settings_link_is_empty() {
    assert_eq!(sung(18 * 60 + 40..19 * 60, 5, &practice(), "", true), []);
}

#[test]
fn test_a_song_caught_late_still_plays_within_the_reminder_lead() {
    // 18:45 start, 10-minute lead, first look at 18:53: eight minutes late, inside the lead.
    assert_eq!(
        sung(18 * 60 + 53..19 * 60, 10, &practice(), DEFAULT_SONG, true),
        [(18 * 60 + 53, DEFAULT_SONG.to_string())]
    );
    // One minute past the lead is too late.
    assert_eq!(
        sung(18 * 60 + 56..19 * 60, 10, &practice(), DEFAULT_SONG, true),
        []
    );
}

#[test]
fn test_a_short_lead_never_narrows_the_song_window_below_two_minutes() {
    // The window was two minutes before it followed the lead; a lead of 0 or 1 must not shrink it.
    for lead in [0, 1] {
        assert_eq!(
            sung(18 * 60 + 47..19 * 60, lead, &practice(), DEFAULT_SONG, true),
            [(18 * 60 + 47, DEFAULT_SONG.to_string())],
            "lead {lead}"
        );
        assert_eq!(
            sung(18 * 60 + 48..19 * 60, lead, &practice(), DEFAULT_SONG, true),
            [],
            "lead {lead}"
        );
    }
}

#[test]
fn test_a_start_played_by_the_settings_song_is_not_also_announced_by_a_notice() {
    let start = 18 * 60 + 45;
    let none = HashSet::new();
    let notice = |sound_is_spotify: bool, minute: i64| {
        due_reminders_with(
            &[practice()],
            None,
            THURSDAY,
            minute,
            5,
            &none,
            DEFAULT_SONG,
            sound_is_spotify,
        )
    };
    // Ahead of the start the notice says so, whatever the sound: reminders stay Chime.
    let soon = notice(true, start - 5);
    assert_eq!(soon.len(), 1);
    assert_eq!(soon[0]["title"], "Guitar practice starts soon");
    // At the start the song announces it, so the notice stays quiet.
    assert_eq!(notice(true, start), Vec::<Value>::new());
    // With the sound on a tone there is no song, so the notice does announce it.
    let now = notice(false, start);
    assert_eq!(now.len(), 1);
    assert_eq!(now[0]["title"], "Guitar practice starts now");
}

#[test]
fn test_the_reminder_lead_default_is_five_minutes() {
    assert_eq!(remind::REMINDER_LEAD_DEFAULT_MIN, 5);
    assert_eq!(
        remind::reminder_lead_min(&json!({}), remind::REMINDER_LEAD_DEFAULT_MIN).expect("lead"),
        5
    );
}
