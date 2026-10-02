//! What the methods of `WeekModel` and `Occurrence` in `desktop/native/weekmodel.py` work out.
//!
//! The Python classes stay dataclasses; each method sends the week as the JSON `Week::read` takes
//! and gets back positions in its own tuples, so the objects it returns are the ones the model holds.

use chrono::Datelike;
use serde_json::Value;

use crate::desk::pydate::from_iso;
use crate::desk::pyval::type_error;
use crate::desk::weekmodel::{LEFTOVER, SLACK_WORDS, due_label};
use crate::error::{EngineError, EngineResult};
use crate::stored::{dict, truthy};

/// `SLACK_WORDS.get(slack or "", "")`.
pub fn slack_words(slack: Option<&str>) -> &'static str {
    SLACK_WORDS
        .iter()
        .find(|(key, _)| Some(*key) == slack)
        .map_or("", |(_, words)| words)
}

/// `Occurrence.minutes`.
pub fn minutes(start: i64, end: i64) -> i64 {
    end - start
}

/// `Occurrence.live`: homework is live until it is done or missed; fixed blocks always are.
pub fn live(work: bool, done: bool, missed: bool) -> bool {
    !(work && (done || missed))
}

/// `date.fromisoformat(week_start) + timedelta(days=day)`.
pub fn date_of(week_start: &str, day: i64) -> EngineResult<(i32, u32, u32)> {
    let moved = crate::stored::add_days(from_iso(week_start)?, day)?;
    Ok((moved.year(), moved.month(), moved.day()))
}

#[derive(Clone)]
struct Occ {
    day: i64,
    start: i64,
    end: i64,
    work: bool,
    live: bool,
    slack: Option<String>,
}

#[derive(Clone)]
struct Wait {
    title: String,
    minutes: i64,
    due: Option<String>,
}

#[derive(Clone)]
pub struct Week {
    week_start: String,
    occurrences: Vec<Occ>,
    waiting: Vec<Wait>,
}

fn whole(row: &serde_json::Map<String, Value>, key: &str) -> EngineResult<i64> {
    row.get(key)
        .and_then(Value::as_i64)
        .ok_or_else(|| type_error(format!("{key} must be a whole number")))
}

fn word(row: &serde_json::Map<String, Value>, key: &str) -> EngineResult<Option<String>> {
    match row.get(key) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(text)) => Ok(Some(text.clone())),
        Some(_) => Err(type_error(format!("{key} must be text"))),
    }
}

impl Week {
    pub fn read(text: &str) -> EngineResult<Week> {
        let raw: Value =
            serde_json::from_str(text).map_err(|error| EngineError::value(error.to_string()))?;
        let fields = dict(&raw)?;
        let list = |key: &str| {
            fields
                .get(key)
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default()
        };
        let mut occurrences = Vec::new();
        for item in list("occurrences") {
            let row = dict(&item)?;
            let work = truthy(row.get("work"));
            occurrences.push(Occ {
                day: whole(row, "day")?,
                start: whole(row, "start")?,
                end: whole(row, "end")?,
                work,
                live: live(work, truthy(row.get("done")), truthy(row.get("missed"))),
                slack: word(row, "slack")?,
            });
        }
        let mut waiting = Vec::new();
        for item in list("waiting") {
            let row = dict(&item)?;
            waiting.push(Wait {
                title: word(row, "title")?.unwrap_or_default(),
                minutes: whole(row, "minutes")?,
                due: word(row, "due")?,
            });
        }
        Ok(Week {
            week_start: fields
                .get("week_start")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            occurrences,
            waiting,
        })
    }

    pub fn on_day(&self, day: i64) -> Vec<usize> {
        (0..self.occurrences.len())
            .filter(|at| self.occurrences[*at].day == day)
            .collect()
    }

    pub fn load_min(&self, day: i64) -> i64 {
        self.on_day(day)
            .into_iter()
            .map(|at| &self.occurrences[at])
            .filter(|item| item.work)
            .map(|item| minutes(item.start, item.end))
            .sum()
    }

    /// Homework still to do, the most squeezed first; equal ones stay in the order they came.
    pub fn open_work(&self) -> EngineResult<Vec<usize>> {
        let mut keyed: Vec<((i64, i64, i64), usize)> = Vec::new();
        for (at, item) in self.occurrences.iter().enumerate() {
            if !(item.work && item.live) {
                continue;
            }
            let squeeze = match item.slack.as_deref() {
                Some("danger") => 0,
                Some("tight") => 1,
                None => 2,
                Some("ok") => 3,
                Some(other) => return Err(EngineError::key(other)),
            };
            keyed.push(((squeeze, item.day, item.start), at));
        }
        keyed.sort_by_key(|(key, _)| *key);
        Ok(keyed.into_iter().map(|(_, at)| at).collect())
    }

    pub fn due_today_unplaced(&self, today: Option<i64>) -> EngineResult<Vec<usize>> {
        let Some(today) = today else {
            return Ok(Vec::new());
        };
        let (year, month, day) = date_of(&self.week_start, today)?;
        let iso = format!("{year:04}-{month:02}-{day:02}");
        Ok((0..self.waiting.len())
            .filter(|at| {
                self.waiting[*at]
                    .due
                    .as_deref()
                    .unwrap_or("")
                    .starts_with(&iso)
            })
            .collect())
    }

    pub fn leftover_kind(&self, today: Option<i64>) -> EngineResult<&'static str> {
        if today.is_some() && !self.due_today_unplaced(today)?.is_empty() {
            return Ok("needs_time");
        }
        let homework: Vec<&Occ> = self.occurrences.iter().filter(|item| item.work).collect();
        if homework.is_empty() && self.waiting.is_empty() {
            return Ok(if self.occurrences.is_empty() {
                "no_homework"
            } else {
                "calendar_only"
            });
        }
        if !homework.iter().any(|item| item.live) && self.waiting.is_empty() {
            return Ok("all_finished");
        }
        Ok("calendar_only")
    }

    pub fn leftover_words(&self, today: Option<i64>) -> EngineResult<&'static str> {
        let kind = self.leftover_kind(today)?;
        Ok(LEFTOVER
            .iter()
            .find(|(key, _)| *key == kind)
            .map_or("", |(_, words)| words))
    }

    /// Kicker, title, line. When homework needs a time, the title is its name.
    pub fn leftover_parts(&self, today: Option<i64>) -> EngineResult<(String, String, String)> {
        let kind = self.leftover_kind(today)?;
        let heading = self.leftover_words(today)?.to_string();
        if kind == "needs_time" {
            let first = &self.waiting[self.due_today_unplaced(today)?[0]];
            let due = due_label(first.due.as_deref(), &self.week_start);
            let line = if due.is_empty() {
                "Due today".to_string()
            } else {
                format!("Due {due}")
            };
            return Ok((heading, first.title.clone(), line));
        }
        Ok((heading.clone(), heading, String::new()))
    }

    pub fn minutes_left_today(&self, today: Option<i64>, minute: i64) -> EngineResult<i64> {
        let Some(today) = today else {
            return Ok(0);
        };
        let mut total = 0;
        for at in self.on_day(today) {
            let item = &self.occurrences[at];
            if item.work && item.live && item.end > minute {
                total += item.end - item.start.max(minute);
            }
        }
        for at in self.due_today_unplaced(Some(today))? {
            total += self.waiting[at].minutes;
        }
        Ok(total)
    }

    /// The thing on now, then the rest of the day in order. Homework wins over the fixed block
    /// around it.
    pub fn day_queue(&self, day: i64, minute: i64) -> (Option<usize>, Vec<usize>) {
        let live: Vec<usize> = self
            .on_day(day)
            .into_iter()
            .filter(|at| self.occurrences[*at].live)
            .collect();
        let mut running: Vec<usize> = live
            .iter()
            .copied()
            .filter(|at| {
                let item = &self.occurrences[*at];
                item.start <= minute && minute < item.end
            })
            .collect();
        running.sort_by_key(|at| (!self.occurrences[*at].work, self.occurrences[*at].start));
        let current = running.first().copied();
        let mut queue: Vec<usize> = current.into_iter().collect();
        queue.extend(
            live.into_iter()
                .filter(|at| self.occurrences[*at].start > minute),
        );
        (current, queue)
    }
}
