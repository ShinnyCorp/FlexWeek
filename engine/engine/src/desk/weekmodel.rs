//! Week reading model from `desktop/native/weekmodel.py`.

use chrono::{Datelike, Duration, NaiveDate};
use serde_json::{Value, json};

use std::sync::atomic::{AtomicBool, Ordering};

use crate::desk::calendar::{
    self, DAYS, deep_copy, due_is_timed, due_sort_key, is_series, is_work_session,
};

static CLOCK_24H: AtomicBool = AtomicBool::new(true);

pub const SLACK_WORDS: [(&str, &str); 3] = [
    ("danger", "Cutting it close"),
    ("tight", "Tight"),
    ("ok", "Plenty of time"),
];
const SLACK_ORDER: [(&str, i64); 4] = [("danger", 0), ("tight", 1), ("", 2), ("ok", 3)];
pub const NOT_PLANNED: &str = "Not planned yet.";
pub const HOMEWORK: &str = "assignments";
pub const END_OF_DAY: i64 = 24 * 60;
const MONTHS: [&str; 12] = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];
pub const LEFTOVER: [(&str, &str); 4] = [
    ("needs_time", "Not placed yet"),
    ("no_homework", "No homework added"),
    ("all_finished", "All homework finished"),
    ("calendar_only", "Nothing else scheduled today"),
];

pub fn set_clock_24h(on: bool) -> bool {
    let changed = CLOCK_24H.load(Ordering::Relaxed) != on;
    CLOCK_24H.store(on, Ordering::Relaxed);
    changed
}

fn clock_24h() -> bool {
    CLOCK_24H.load(Ordering::Relaxed)
}

fn no_start(block: &Value) -> bool {
    match block.get("start") {
        None | Some(Value::Null) => true,
        Some(Value::String(text)) => text.is_empty(),
        _ => false,
    }
}

pub fn minute_of(hhmm: &str) -> i64 {
    let parts: Vec<&str> = hhmm.split(':').collect();
    let hours: i64 = parts.first().unwrap_or(&"0").parse().unwrap_or(0);
    let minutes: i64 = parts.get(1).unwrap_or(&"0").parse().unwrap_or(0);
    hours * 60 + minutes
}

pub fn clock_text(minute: i64) -> String {
    let hours = minute.div_euclid(60);
    let minutes = minute.rem_euclid(60);
    if clock_24h() {
        return format!("{hours:02}:{minutes:02}");
    }
    let shown_hour = hours % 12;
    let shown = if shown_hour == 0 { 12 } else { shown_hour };
    let half = if hours % 24 < 12 { "AM" } else { "PM" };
    format!("{shown}:{minutes:02} {half}")
}

pub fn hhmm_text(hhmm: &str) -> String {
    clock_text(minute_of(hhmm))
}

pub fn time_format() -> &'static str {
    if clock_24h() { "HH:mm" } else { "h:mm AP" }
}

pub fn clock_label(minute: i64) -> String {
    clock_text(minute)
}

fn twelve(minute: i64) -> (String, &'static str) {
    let hours = minute.div_euclid(60);
    let minutes = minute.rem_euclid(60);
    let shown_hour = hours % 12;
    let h = if shown_hour == 0 { 12 } else { shown_hour };
    let shown = if minutes == 0 {
        format!("{h}")
    } else {
        format!("{h}:{minutes:02}")
    };
    let half = if hours % 24 < 12 { "AM" } else { "PM" };
    (shown, half)
}

pub fn short_clock(minute: i64) -> String {
    if clock_24h() {
        return clock_text(minute);
    }
    let (shown, half) = twelve(minute);
    format!("{shown} {half}")
}

pub fn range_label(start: i64, end: i64) -> String {
    if clock_24h() {
        return format!("{}–{}", clock_text(start), clock_text(end));
    }
    let (first, first_half) = twelve(start);
    let (last, last_half) = twelve(end);
    if first_half == last_half {
        format!("{first}–{last} {last_half}")
    } else {
        format!("{first} {first_half}–{last} {last_half}")
    }
}

pub fn length_label(minutes: i64) -> String {
    let minutes = minutes.max(0);
    let hours = minutes / 60;
    let rest = minutes % 60;
    if hours == 0 {
        return format!("{rest} min");
    }
    if rest == 0 {
        return format!("{hours} h");
    }
    format!("{hours} h {rest} min")
}

pub fn planned_line(planned_min: i64, done_min: i64) -> String {
    if planned_min <= 0 {
        return "Nothing planned yet".to_string();
    }
    let done = if done_min <= 0 {
        "0 done".to_string()
    } else {
        format!("{} done", length_label(done_min))
    };
    format!("{} planned · {done}", length_label(planned_min))
}

pub fn due_label(due: Option<&str>, _week_start: &str) -> String {
    let Some(due) = due else {
        return String::new();
    };
    let day = NaiveDate::parse_from_str(&due[..10], "%Y-%m-%d").expect("due day");
    let mut words = format!(
        "{} {} {}",
        DAYS[day.weekday().num_days_from_monday() as usize],
        day.day(),
        MONTHS[(day.month() as usize).saturating_sub(1)]
    );
    if due_is_timed(due) {
        words.push_str(&format!(", {}", hhmm_text(&due[11..16])));
    }
    words
}

pub fn moved_words(block: &Value, from_day: i64, day: i64, start: i64, end: i64) -> String {
    let title = block
        .get("title")
        .and_then(Value::as_str)
        .unwrap_or("the block");
    if no_start(block) {
        return format!(
            "Placed {title} on {} {}.",
            DAYS[day as usize],
            clock_label(start)
        );
    }
    let mut title = title.to_string();
    if is_series(block) {
        title = format!("{}'s {title}", calendar::DAY_FULL[from_day as usize]);
    }
    let was = minute_of(
        block
            .get("start")
            .and_then(Value::as_str)
            .unwrap_or("00:00"),
    );
    let was_end = was
        + block
            .get("duration_min")
            .and_then(Value::as_i64)
            .unwrap_or(0);
    if day == from_day && start == was && end != was_end {
        return format!("{title} now ends at {}.", clock_label(end));
    }
    if day == from_day && end == was_end && start != was {
        return format!("{title} now starts at {}.", clock_label(start));
    }
    format!(
        "Moved {title} to {} {}.",
        DAYS[day as usize],
        clock_label(start)
    )
}

pub fn added_words(block: &Value) -> String {
    let title = block
        .get("title")
        .and_then(Value::as_str)
        .unwrap_or("a block");
    let days = block.get("days").and_then(Value::as_array);
    if !no_start(block) && days.map(|d| d.len()) == Some(1) {
        let day = days.unwrap()[0].as_i64().unwrap_or(0) as usize;
        return format!(
            "Added {title} on {} {}.",
            DAYS[day],
            hhmm_text(
                block
                    .get("start")
                    .and_then(Value::as_str)
                    .unwrap_or("00:00")
            )
        );
    }
    format!("Added {title}.")
}

pub fn dated_words(title: &str, iso: &str) -> String {
    format!("Moved {title} to {}.", due_label(Some(iso), ""))
}

#[derive(Clone, Debug, PartialEq)]
pub struct Occurrence {
    pub block_id: String,
    pub title: String,
    pub category: String,
    pub day: i64,
    pub start: i64,
    pub end: i64,
    pub work: bool,
    pub done: bool,
    pub missed: bool,
    pub assignment_id: Option<String>,
    pub due: Option<String>,
    pub slack: Option<String>,
    pub pinned: bool,
}

impl Occurrence {
    pub fn minutes(&self) -> i64 {
        self.end - self.start
    }

    pub fn live(&self) -> bool {
        !(self.work && (self.done || self.missed))
    }

    pub fn slack_words(&self) -> &'static str {
        SLACK_WORDS
            .iter()
            .find(|(key, _)| Some(*key) == self.slack.as_deref())
            .map(|(_, words)| *words)
            .unwrap_or("")
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Waiting {
    pub block_id: String,
    pub title: String,
    pub category: String,
    pub minutes: i64,
    pub assignment_id: Option<String>,
    pub due: Option<String>,
    pub reason: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct DayQueue {
    pub current: Option<Occurrence>,
    pub queue: Vec<Occurrence>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct WeekModel {
    pub week_start: String,
    pub occurrences: Vec<Occurrence>,
    pub waiting: Vec<Waiting>,
    pub focus_min: i64,
}

impl WeekModel {
    pub fn date_of(&self, day: i64) -> NaiveDate {
        NaiveDate::parse_from_str(&self.week_start, "%Y-%m-%d").expect("week") + Duration::days(day)
    }

    pub fn on_day(&self, day: i64) -> Vec<Occurrence> {
        self.occurrences
            .iter()
            .filter(|item| item.day == day)
            .cloned()
            .collect()
    }

    pub fn load_min(&self, day: i64) -> i64 {
        self.on_day(day)
            .iter()
            .filter(|item| item.work)
            .map(|item| item.minutes())
            .sum()
    }

    pub fn open_work(&self) -> Vec<Occurrence> {
        let mut items: Vec<Occurrence> = self
            .occurrences
            .iter()
            .filter(|item| item.work && item.live())
            .cloned()
            .collect();
        items.sort_by(|a, b| {
            let order = |slack: &Option<String>| {
                SLACK_ORDER
                    .iter()
                    .find(|(key, _)| slack.as_deref() == Some(*key))
                    .map(|(_, v)| *v)
                    .unwrap_or(2)
            };
            (order(&a.slack), a.day, a.start, &a.block_id).cmp(&(
                order(&b.slack),
                b.day,
                b.start,
                &b.block_id,
            ))
        });
        items
    }

    pub fn due_today_unplaced(&self, today: Option<i64>) -> Vec<Waiting> {
        let Some(today) = today else {
            return Vec::new();
        };
        let day_date = self.date_of(today);
        let iso = format!(
            "{:04}-{:02}-{:02}",
            day_date.year(),
            day_date.month(),
            day_date.day()
        );
        self.waiting
            .iter()
            .filter(|item| item.due.as_deref().is_some_and(|d| d.starts_with(&iso)))
            .cloned()
            .collect()
    }

    pub fn leftover_kind(&self, today: Option<i64>) -> &'static str {
        if today.is_some() && !self.due_today_unplaced(today).is_empty() {
            return "needs_time";
        }
        let homework: Vec<_> = self.occurrences.iter().filter(|item| item.work).collect();
        if homework.is_empty() && self.waiting.is_empty() {
            return if self.occurrences.is_empty() {
                "no_homework"
            } else {
                "calendar_only"
            };
        }
        if !homework.iter().any(|item| item.live()) && self.waiting.is_empty() {
            return "all_finished";
        }
        "calendar_only"
    }

    pub fn leftover_words(&self, today: Option<i64>) -> &'static str {
        LEFTOVER
            .iter()
            .find(|(k, _)| *k == self.leftover_kind(today))
            .map(|(_, w)| *w)
            .unwrap_or("")
    }

    pub fn leftover_parts(&self, today: Option<i64>) -> (String, String, String) {
        let kind = self.leftover_kind(today);
        let heading = self.leftover_words(today).to_string();
        if kind == "needs_time" {
            let first = &self.due_today_unplaced(today)[0];
            let due = due_label(first.due.as_deref(), &self.week_start);
            let line = if due.is_empty() {
                "Due today".to_string()
            } else {
                format!("Due {due}")
            };
            return (heading.clone(), first.title.clone(), line);
        }
        (heading.clone(), heading, String::new())
    }

    pub fn minutes_left_today(&self, today: Option<i64>, minute: i64) -> i64 {
        let Some(today) = today else {
            return 0;
        };
        let mut total = 0i64;
        for item in self.on_day(today) {
            if item.work && item.live() && item.end > minute {
                total += item.end - item.start.max(minute);
            }
        }
        total += self
            .due_today_unplaced(Some(today))
            .iter()
            .map(|item| item.minutes)
            .sum::<i64>();
        total
    }

    pub fn day_queue(&self, day: i64, minute: i64) -> DayQueue {
        let live: Vec<_> = self
            .on_day(day)
            .into_iter()
            .filter(|item| item.live())
            .collect();
        let mut running: Vec<_> = live
            .iter()
            .filter(|item| item.start <= minute && minute < item.end)
            .cloned()
            .collect();
        running.sort_by(|a, b| (!a.work).cmp(&!b.work).then(a.start.cmp(&b.start)));
        let current = running.first().cloned();
        let later: Vec<_> = live
            .into_iter()
            .filter(|item| item.start > minute)
            .collect();
        let mut queue = Vec::new();
        if let Some(ref c) = current {
            queue.push(c.clone());
        }
        queue.extend(later);
        DayQueue { current, queue }
    }
}

pub fn build_week(
    week_start: &str,
    blocks: &[Value],
    assignments: Option<&serde_json::Map<String, Value>>,
    trace: Option<&Value>,
) -> WeekModel {
    let homework = assignments.cloned().unwrap_or_default();
    let placed: std::collections::HashMap<String, Value> = trace
        .and_then(|t| t.get("placed"))
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| Some((item.get("id")?.as_str()?.to_string(), item.clone())))
                .collect()
        })
        .unwrap_or_default();
    let notes: std::collections::HashMap<String, Value> = trace
        .and_then(|t| t.get("explanations"))
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| {
                    Some((item.get("block_id")?.as_str()?.to_string(), item.clone()))
                })
                .collect()
        })
        .unwrap_or_default();
    let mut occurrences = Vec::new();
    let mut waiting = Vec::new();
    for original in blocks {
        let block = if original.get("completed").and_then(Value::as_bool) == Some(true) {
            deep_copy(original)
        } else {
            original
                .get("id")
                .and_then(Value::as_str)
                .and_then(|id| placed.get(id))
                .cloned()
                .unwrap_or_else(|| deep_copy(original))
        };
        let assignment = original
            .get("assignment_id")
            .and_then(Value::as_str)
            .and_then(|id| homework.get(id));
        let work = is_work_session(original);
        let done = block.get("completed").and_then(Value::as_bool) == Some(true)
            || assignment
                .and_then(|a| a.get("completed"))
                .and_then(Value::as_bool)
                == Some(true);
        let note = original
            .get("id")
            .and_then(Value::as_str)
            .and_then(|id| notes.get(id));
        if no_start(&block) {
            if work && !done {
                waiting.push(Waiting {
                    block_id: original
                        .get("id")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string(),
                    title: original
                        .get("title")
                        .and_then(Value::as_str)
                        .unwrap_or("Untitled")
                        .to_string(),
                    category: original
                        .get("category")
                        .and_then(Value::as_str)
                        .unwrap_or(HOMEWORK)
                        .to_string(),
                    minutes: original
                        .get("duration_min")
                        .and_then(Value::as_i64)
                        .unwrap_or(0),
                    assignment_id: original
                        .get("assignment_id")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    due: assignment
                        .and_then(|a| a.get("due"))
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    reason: note
                        .and_then(|n| n.get("message"))
                        .and_then(Value::as_str)
                        .unwrap_or(NOT_PLANNED)
                        .to_string(),
                });
            }
            continue;
        }
        let mut days: Vec<i64> = block
            .get("days")
            .and_then(Value::as_array)
            .map(|d| d.iter().filter_map(Value::as_i64).collect())
            .unwrap_or_default();
        if block.get("completed").and_then(Value::as_bool) == Some(true)
            && let Some(day) = block.get("completed_day").and_then(Value::as_i64)
        {
            days = vec![day];
        }
        let start = minute_of(
            block
                .get("start")
                .and_then(Value::as_str)
                .unwrap_or("00:00"),
        );
        let end = (start
            + block
                .get("duration_min")
                .and_then(Value::as_i64)
                .unwrap_or(0))
        .min(END_OF_DAY);
        for day in days {
            occurrences.push(Occurrence {
                block_id: original
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                title: block
                    .get("title")
                    .and_then(Value::as_str)
                    .unwrap_or("Untitled")
                    .to_string(),
                category: block
                    .get("category")
                    .and_then(Value::as_str)
                    .map(str::to_string)
                    .unwrap_or_else(|| {
                        if work {
                            HOMEWORK.to_string()
                        } else {
                            String::new()
                        }
                    }),
                day,
                start,
                end,
                work,
                done,
                missed: original
                    .get("missed_days")
                    .and_then(Value::as_array)
                    .is_some_and(|m| m.iter().any(|v| v.as_i64() == Some(day))),
                assignment_id: original
                    .get("assignment_id")
                    .and_then(Value::as_str)
                    .map(str::to_string),
                due: assignment
                    .and_then(|a| a.get("due"))
                    .and_then(Value::as_str)
                    .map(str::to_string),
                slack: note
                    .and_then(|n| n.get("slack_status"))
                    .and_then(Value::as_str)
                    .map(str::to_string),
                pinned: block
                    .get("pinned")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
            });
        }
    }
    occurrences.sort_by(|a, b| (a.day, a.start, &a.block_id).cmp(&(b.day, b.start, &b.block_id)));
    waiting.sort_by(|a, b| {
        due_sort_key(a.due.as_deref(), &a.title)
            .cmp(&due_sort_key(b.due.as_deref(), &b.title))
            .then(a.block_id.cmp(&b.block_id))
    });
    let worked: std::collections::HashSet<String> = blocks
        .iter()
        .filter_map(|b| {
            b.get("assignment_id")
                .and_then(Value::as_str)
                .map(str::to_string)
        })
        .collect();
    let mut focus = 0i64;
    for key in &worked {
        focus += homework
            .get(key)
            .and_then(|a| a.get("focus_minutes"))
            .and_then(Value::as_i64)
            .unwrap_or(0);
    }
    focus += blocks
        .iter()
        .filter(|b| !crate::stored::truthy(b.get("assignment_id")))
        .map(|b| b.get("focus_minutes").and_then(Value::as_i64).unwrap_or(0))
        .sum::<i64>();
    WeekModel {
        week_start: week_start.to_string(),
        occurrences,
        waiting,
        focus_min: focus,
    }
}

pub fn build_week_json(
    week_start: &str,
    blocks: &[Value],
    assignments: Option<&serde_json::Map<String, Value>>,
    trace: Option<&Value>,
) -> Value {
    let week = build_week(week_start, blocks, assignments, trace);
    json!({
        "week_start": week.week_start,
        "focus_min": week.focus_min,
        "occurrences": week.occurrences.iter().map(|item| json!({
            "block_id": item.block_id,
            "title": item.title,
            "category": item.category,
            "day": item.day,
            "start": item.start,
            "end": item.end,
            "work": item.work,
            "done": item.done,
            "missed": item.missed,
            "assignment_id": item.assignment_id,
            "due": item.due,
            "slack": item.slack,
            "pinned": item.pinned,
        })).collect::<Vec<_>>(),
        "waiting": week.waiting.iter().map(|item| json!({
            "block_id": item.block_id,
            "title": item.title,
            "category": item.category,
            "minutes": item.minutes,
            "assignment_id": item.assignment_id,
            "due": item.due,
            "reason": item.reason,
        })).collect::<Vec<_>>(),
    })
}
