//! Rust twin of `desktop/tests/test_weekmodel.py`: the week model's placement rules as literal cases.
//!
//! The Python file's last test compares the model with what the week table draws; it drives a widget
//! and has no twin.

mod common;

use common::desk::{object, py_title, with};
use flexweek_engine::desk::weekmodel::{
    Occurrence, WeekModel, build_week, build_week_json, clock_label, due_label, length_label,
    planned_line,
};
use flexweek_engine::desk::weekview::{Week, slack_words};
use serde_json::{Map, Value, json};

const WEEK: &str = "2026-09-14";

fn homework() -> Map<String, Value> {
    object(json!({
        "chem": {"id": "chem", "title": "Chem lab report", "due": "2026-09-17T23:59", "completed": false},
        "essay": {"id": "essay", "title": "History essay", "due": "2026-09-18T21:00", "completed": false},
        "poster": {"id": "poster", "title": "Science fair poster", "due": "2026-09-20T20:00", "completed": false},
        "math": {"id": "math", "title": "Math worksheet", "due": "2026-09-15T08:00", "completed": true},
    }))
}

/// `block(block_id, kind, days, start, minutes, **extra)`: `title` and `category` in `extra` replace
/// the defaults, and the rest follow in order.
fn block(
    id: &str,
    kind: &str,
    days: Value,
    start: Option<&str>,
    minutes: i64,
    extra: Value,
) -> Value {
    let mut extra = object(extra);
    let title = extra
        .shift_remove("title")
        .unwrap_or_else(|| json!(py_title(id)));
    let default_category = if kind == "locked" {
        "class"
    } else {
        "assignments"
    };
    let category = extra
        .shift_remove("category")
        .unwrap_or_else(|| json!(default_category));
    let mut out = object(json!({
        "id": id,
        "title": title,
        "kind": kind,
        "category": category,
        "days": days,
        "start": start,
        "duration_min": minutes,
    }));
    out.extend(extra);
    Value::Object(out)
}

fn blocks() -> Vec<Value> {
    vec![
        block(
            "school",
            "locked",
            json!([0, 1, 2, 3, 4]),
            Some("08:00"),
            390,
            json!({}),
        ),
        block(
            "dinner",
            "locked",
            json!([0, 1, 2, 3, 4, 5, 6]),
            Some("18:00"),
            30,
            json!({"category": "meals"}),
        ),
        block(
            "chem-1",
            "flexible",
            json!([3]),
            None,
            90,
            json!({"assignment_id": "chem"}),
        ),
        block(
            "essay-1",
            "flexible",
            json!([3]),
            Some("18:45"),
            60,
            json!({"assignment_id": "essay"}),
        ),
        block(
            "poster-1",
            "flexible",
            json!([]),
            None,
            120,
            json!({"assignment_id": "poster"}),
        ),
        block(
            "math-1",
            "flexible",
            json!([0, 1]),
            Some("15:45"),
            45,
            json!({"assignment_id": "math", "completed": true, "completed_day": 0}),
        ),
    ]
}

fn trace() -> Value {
    json!({
        "placed": [block("chem-1", "flexible", json!([3]), Some("20:00"), 90, json!({"assignment_id": "chem"}))],
        "unplaced": [block("poster-1", "flexible", json!([]), None, 120, json!({"assignment_id": "poster"}))],
        "explanations": [
            {
                "block_id": "chem-1",
                "message": "Finishes only 2 h 29 min before it is due.",
                "slack_min": 149,
                "slack_status": "danger",
            },
            {
                "block_id": "essay-1",
                "message": "Finishes 25 h 15 min before it is due.",
                "slack_min": 1515,
                "slack_status": "tight",
            },
            {
                "block_id": "poster-1",
                "message": "There is not enough time left before it is due, even with nothing else planned.",
                "reason": "DEADLINE_MISS",
            },
        ],
    })
}

fn model(blocks: &[Value], homework: &Map<String, Value>, trace: Option<&Value>) -> WeekModel {
    build_week(WEEK, blocks, Some(homework), trace)
}

/// The week model together with the engine's queries over it, built from the same blocks the way
/// `build_week` hands the model to `WeekHandle`.
fn view(
    blocks: &[Value],
    homework: &Map<String, Value>,
    trace: Option<&Value>,
) -> (WeekModel, Week) {
    let text = build_week_json(WEEK, blocks, Some(homework), trace).to_string();
    (
        model(blocks, homework, trace),
        Week::read(&text).expect("a readable week"),
    )
}

fn on_day<'a>(week: &'a WeekModel, queries: &Week, day: i64) -> Vec<&'a Occurrence> {
    queries
        .on_day(day)
        .into_iter()
        .map(|at| &week.occurrences[at])
        .collect()
}

fn thursday() -> Vec<(String, String, String)> {
    let (week, queries) = view(&blocks(), &homework(), Some(&trace()));
    on_day(&week, &queries, 3)
        .iter()
        .map(|item| {
            (
                item.block_id.clone(),
                clock_label(item.start),
                clock_label(item.end),
            )
        })
        .collect()
}

fn triple(a: &str, b: &str, c: &str) -> (String, String, String) {
    (a.to_string(), b.to_string(), c.to_string())
}

#[test]
fn test_the_solver_placement_gives_unscheduled_work_its_time() {
    assert_eq!(
        thursday(),
        [
            triple("school", "08:00", "14:30"),
            triple("dinner", "18:00", "18:30"),
            triple("essay-1", "18:45", "19:45"),
            triple("chem-1", "20:00", "21:30"),
        ]
    );
}

#[test]
fn test_a_finished_session_stays_on_the_day_it_was_finished() {
    let week = model(&blocks(), &homework(), Some(&trace()));
    let math: Vec<(i64, bool)> = week
        .occurrences
        .iter()
        .filter(|item| item.block_id == "math-1")
        .map(|item| (item.day, item.done))
        .collect();
    assert_eq!(math, [(0, true)]);
}

#[test]
fn test_a_solver_placement_never_moves_finished_work() {
    let mut moved = trace();
    moved["placed"].as_array_mut().expect("placed").push(block(
        "math-1",
        "flexible",
        json!([4]),
        Some("10:00"),
        45,
        json!({}),
    ));
    let week = model(&blocks(), &homework(), Some(&moved));
    let math: Vec<(i64, String)> = week
        .occurrences
        .iter()
        .filter(|item| item.block_id == "math-1")
        .map(|item| (item.day, clock_label(item.start)))
        .collect();
    assert_eq!(math, [(0, "15:45".to_string())]);
}

#[test]
fn test_work_with_no_time_waits_with_the_solvers_reason() {
    let week = model(&blocks(), &homework(), Some(&trace()));
    let waiting: Vec<(&str, i64, &str)> = week
        .waiting
        .iter()
        .map(|item| (item.title.as_str(), item.minutes, item.reason.as_str()))
        .collect();
    assert_eq!(
        waiting,
        [(
            "Poster-1",
            120,
            "There is not enough time left before it is due, even with nothing else planned."
        )]
    );
}

#[test]
fn test_work_nobody_has_planned_yet_says_so() {
    let week = model(&blocks(), &homework(), None);
    let waiting: Vec<(&str, &str)> = week
        .waiting
        .iter()
        .map(|item| (item.block_id.as_str(), item.reason.as_str()))
        .collect();
    assert_eq!(
        waiting,
        [
            ("chem-1", "Not planned yet."),
            ("poster-1", "Not planned yet.")
        ]
    );
}

#[test]
fn test_waiting_work_that_shares_a_due_date_comes_in_title_order_whatever_the_ids() {
    let titles = ["Zoology", "Algebra", "Music", "Biology"];
    let mut shared = Map::new();
    for title in titles {
        shared.insert(
            title.to_string(),
            json!({"id": title, "title": title, "due": "2026-09-17T23:59", "completed": false}),
        );
    }
    for ids in [
        ["a", "b", "c", "d"],
        ["d", "c", "b", "a"],
        ["q", "z", "b", "m"],
    ] {
        let made: Vec<Value> = ids
            .iter()
            .zip(titles)
            .map(|(id, title)| {
                block(
                    id,
                    "flexible",
                    json!([]),
                    None,
                    30,
                    json!({"title": title, "assignment_id": title}),
                )
            })
            .collect();
        let mut reversed = made.clone();
        reversed.reverse();
        for order in [made, reversed] {
            let week = model(&order, &shared, None);
            let waiting: Vec<&str> = week
                .waiting
                .iter()
                .map(|item| item.title.as_str())
                .collect();
            assert_eq!(
                waiting,
                ["Algebra", "Biology", "Music", "Zoology"],
                "ids {ids:?}"
            );
        }
    }
}

#[test]
fn test_waiting_work_with_the_same_due_and_title_breaks_the_tie_by_id() {
    let essay = object(json!({
        "essay": {"id": "essay", "title": "Essay", "due": "2026-09-17T23:59", "completed": false},
    }));
    let made: Vec<Value> = ["s2", "s1"]
        .iter()
        .map(|id| {
            block(
                id,
                "flexible",
                json!([]),
                None,
                30,
                json!({"title": "Essay", "assignment_id": "essay"}),
            )
        })
        .collect();
    let ids: Vec<String> = model(&made, &essay, None)
        .waiting
        .into_iter()
        .map(|item| item.block_id)
        .collect();
    assert_eq!(ids, ["s1", "s2"]);
}

#[test]
fn test_risk_is_the_solvers_verdict_and_the_most_squeezed_comes_first() {
    let (week, queries) = view(&blocks(), &homework(), Some(&trace()));
    let open: Vec<(&str, Option<&str>, &str)> = queries
        .open_work()
        .expect("open work")
        .into_iter()
        .map(|at| &week.occurrences[at])
        .map(|item| {
            (
                item.block_id.as_str(),
                item.slack.as_deref(),
                slack_words(item.slack.as_deref()),
            )
        })
        .collect();
    assert_eq!(
        open,
        [
            ("chem-1", Some("danger"), "Cutting it close"),
            ("essay-1", Some("tight"), "Tight")
        ]
    );
}

#[test]
fn test_without_a_verdict_no_risk_is_claimed() {
    let (week, queries) = view(&blocks(), &homework(), None);
    let open: Vec<(&str, Option<&str>, &str)> = queries
        .open_work()
        .expect("open work")
        .into_iter()
        .map(|at| &week.occurrences[at])
        .map(|item| {
            (
                item.block_id.as_str(),
                item.slack.as_deref(),
                slack_words(item.slack.as_deref()),
            )
        })
        .collect();
    assert_eq!(open, [("essay-1", None, "")]);
}

#[test]
fn test_load_counts_homework_minutes_only() {
    let (_week, queries) = view(&blocks(), &homework(), Some(&trace()));
    let load: Vec<i64> = (0..7).map(|day| queries.load_min(day)).collect();
    assert_eq!(load, [45, 0, 0, 150, 0, 0, 0]);
}

#[test]
fn test_planned_line_uses_length_label() {
    assert_eq!(planned_line(60, 0), "1 h planned · 0 done");
    assert_eq!(planned_line(90, 45), "1 h 30 min planned · 45 min done");
    assert_eq!(planned_line(0, 0), "Nothing planned yet");
}

#[test]
fn test_the_day_queue_is_what_is_on_now_then_the_rest_in_order() {
    let (week, queries) = view(&blocks(), &homework(), Some(&trace()));
    let ids = |queue: &[usize]| -> Vec<String> {
        queue
            .iter()
            .map(|at| week.occurrences[*at].block_id.clone())
            .collect()
    };
    let (current, queue) = queries.day_queue(3, 13 * 60 + 40);
    assert_eq!(
        current.map(|at| week.occurrences[at].block_id.as_str()),
        Some("school")
    );
    assert_eq!(ids(&queue), ["school", "dinner", "essay-1", "chem-1"]);
    let (current, queue) = queries.day_queue(3, 19 * 60);
    assert_eq!(
        current.map(|at| week.occurrences[at].block_id.as_str()),
        Some("essay-1")
    );
    assert_eq!(ids(&queue), ["essay-1", "chem-1"]);
    let (current, queue) = queries.day_queue(3, 22 * 60);
    assert_eq!(current, None);
    assert_eq!(queue, Vec::<usize>::new());
}

#[test]
fn test_homework_wins_over_the_fixed_block_around_it() {
    let mut with_hall = blocks();
    with_hall.push(block(
        "study-hall",
        "flexible",
        json!([3]),
        Some("10:00"),
        30,
        json!({"assignment_id": "essay"}),
    ));
    let (week, queries) = view(&with_hall, &homework(), Some(&trace()));
    let (current, _queue) = queries.day_queue(3, 10 * 60 + 10);
    assert_eq!(
        current.map(|at| week.occurrences[at].block_id.as_str()),
        Some("study-hall")
    );
}

#[test]
fn test_finished_and_missed_homework_leave_the_queue() {
    let made = [
        block(
            "essay-1",
            "flexible",
            json!([3]),
            Some("18:45"),
            60,
            json!({"assignment_id": "essay", "missed_days": [3]}),
        ),
        block(
            "chem-1",
            "flexible",
            json!([3]),
            Some("20:00"),
            90,
            json!({"assignment_id": "chem", "completed": true}),
        ),
    ];
    let (week, queries) = view(&made, &homework(), None);
    let (_current, queue) = queries.day_queue(3, 18 * 60);
    assert_eq!(queue, Vec::<usize>::new());
    let flags: Vec<(&str, bool, bool)> = on_day(&week, &queries, 3)
        .iter()
        .map(|item| (item.block_id.as_str(), item.missed, item.done))
        .collect();
    assert_eq!(flags, [("essay-1", true, false), ("chem-1", false, true)]);
}

#[test]
fn test_focus_is_what_the_timer_credited_to_this_weeks_homework_and_blocks() {
    // The timer adds its minutes to the homework, or to a block with no homework. The week counts
    // the homework it has sessions of, each once however many sessions, and its other blocks;
    // homework with no session this week is another week's.
    let mut credited = homework();
    credited.insert(
        "chem".into(),
        with(credited["chem"].clone(), json!({"focus_minutes": 25})),
    );
    credited.insert(
        "essay".into(),
        with(credited["essay"].clone(), json!({"focus_minutes": 15})),
    );
    credited.insert(
        "later".into(),
        json!({"id": "later", "title": "Next week's reading", "due": "2026-09-25", "focus_minutes": 40}),
    );
    let mut made = blocks();
    made.push(block(
        "essay-2",
        "flexible",
        json!([4]),
        Some("17:00"),
        30,
        json!({"assignment_id": "essay"}),
    ));
    made.push(block(
        "piano",
        "locked",
        json!([2]),
        Some("17:00"),
        45,
        json!({"focus_minutes": 10}),
    ));
    assert_eq!(
        model(&made, &credited, Some(&trace())).focus_min,
        25 + 15 + 10
    );
    assert_eq!(model(&blocks(), &homework(), Some(&trace())).focus_min, 0);
}

#[test]
fn test_homework_the_account_marks_complete_is_done_even_if_the_block_is_not() {
    let made = [block(
        "math-2",
        "flexible",
        json!([2]),
        Some("16:00"),
        30,
        json!({"assignment_id": "math"}),
    )];
    let week = model(&made, &homework(), None);
    let done: Vec<(&str, bool)> = week
        .occurrences
        .iter()
        .map(|item| (item.block_id.as_str(), item.done))
        .collect();
    assert_eq!(done, [("math-2", true)]);
}

#[test]
fn test_a_homework_session_saved_without_a_category_is_still_homework() {
    let made = [
        with(
            block(
                "essay-1",
                "flexible",
                json!([3]),
                Some("18:45"),
                60,
                json!({"assignment_id": "essay"}),
            ),
            json!({"category": null}),
        ),
        with(
            block(
                "vocab-1",
                "flexible",
                json!([4]),
                Some("15:30"),
                30,
                json!({"assignment_id": "essay"}),
            ),
            json!({"category": "study"}),
        ),
        with(
            block(
                "waits",
                "flexible",
                json!([]),
                None,
                30,
                json!({"assignment_id": "essay"}),
            ),
            json!({"category": null}),
        ),
        with(
            block("club", "locked", json!([2]), Some("15:00"), 60, json!({})),
            json!({"category": null}),
        ),
    ];
    let week = model(&made, &homework(), None);
    let placed: Vec<(&str, &str)> = week
        .occurrences
        .iter()
        .map(|item| (item.block_id.as_str(), item.category.as_str()))
        .collect();
    assert_eq!(
        placed,
        [
            ("club", ""),
            ("essay-1", "assignments"),
            ("vocab-1", "study")
        ]
    );
    let waiting: Vec<(&str, &str)> = week
        .waiting
        .iter()
        .map(|item| (item.block_id.as_str(), item.category.as_str()))
        .collect();
    assert_eq!(waiting, [("waits", "assignments")]);
}

#[test]
fn test_a_block_cannot_run_past_midnight() {
    let week = model(
        &[block(
            "late",
            "locked",
            json!([0]),
            Some("23:30"),
            90,
            json!({}),
        )],
        &Map::new(),
        None,
    );
    let spans: Vec<(String, String)> = week
        .occurrences
        .iter()
        .map(|item| (clock_label(item.start), clock_label(item.end)))
        .collect();
    assert_eq!(spans, [("23:30".to_string(), "24:00".to_string())]);
}

#[test]
fn test_labels_read_the_way_a_student_says_them() {
    let lengths: Vec<String> = [30, 60, 90, 0].into_iter().map(length_label).collect();
    assert_eq!(lengths, ["30 min", "1 h", "1 h 30 min", "0 min"]);
    assert_eq!(due_label(Some("2026-09-17T23:59"), WEEK), "Thu 17 Sep");
    assert_eq!(due_label(Some("2026-09-27"), WEEK), "Sun 27 Sep");
    assert_eq!(
        due_label(Some("2026-09-27T09:00"), WEEK),
        "Sun 27 Sep, 09:00"
    );
    assert_eq!(
        due_label(Some("2026-09-28T08:00"), WEEK),
        "Mon 28 Sep, 08:00"
    );
    assert_eq!(due_label(Some("2026-09-20"), WEEK), "Sun 20 Sep");
    assert_eq!(due_label(None, WEEK), "");
}

#[test]
fn test_due_today_unplaced_is_homework_that_still_needs_a_time() {
    let made = [block(
        "math-u",
        "flexible",
        json!([3]),
        None,
        45,
        json!({"assignment_id": "math", "title": "Math worksheet"}),
    )];
    let open = object(json!({
        "math": {"id": "math", "title": "Math worksheet", "due": "2026-09-17T21:00", "completed": false},
    }));
    let (week, queries) = view(&made, &open, None);
    let due: Vec<&str> = queries
        .due_today_unplaced(Some(3))
        .expect("due")
        .into_iter()
        .map(|at| week.waiting[at].title.as_str())
        .collect();
    assert_eq!(due, ["Math worksheet"]);
    assert_eq!(
        queries.due_today_unplaced(Some(2)).expect("due"),
        Vec::<usize>::new()
    );
    assert_eq!(queries.leftover_kind(Some(3)).expect("kind"), "needs_time");
    assert_eq!(
        queries.leftover_words(Some(3)).expect("words"),
        "Not placed yet"
    );
    assert_eq!(
        queries.leftover_parts(Some(3)).expect("parts"),
        triple("Not placed yet", "Math worksheet", "Due Thu 17 Sep, 21:00")
    );
    assert_eq!(
        queries
            .minutes_left_today(Some(3), 16 * 60)
            .expect("minutes"),
        45
    );
}

#[test]
fn test_waiting_homework_is_ordered_by_when_it_must_end() {
    let made = [
        block(
            "all",
            "flexible",
            json!([]),
            None,
            30,
            json!({"assignment_id": "all", "title": "All day"}),
        ),
        block(
            "am",
            "flexible",
            json!([]),
            None,
            30,
            json!({"assignment_id": "am", "title": "Morning"}),
        ),
    ];
    let due = object(json!({
        "all": {"id": "all", "title": "All day", "due": "2026-09-17", "completed": false},
        "am": {"id": "am", "title": "Morning", "due": "2026-09-17T09:00", "completed": false},
    }));
    let week = model(&made, &due, None);
    let titles: Vec<&str> = week
        .waiting
        .iter()
        .map(|item| item.title.as_str())
        .collect();
    assert_eq!(titles, ["Morning", "All day"]);
}

#[test]
fn test_leftover_kind_splits_the_four_empty_days() {
    let (_, empty) = view(&[], &Map::new(), None);
    assert_eq!(empty.leftover_kind(Some(3)).expect("kind"), "no_homework");
    assert_eq!(
        empty.leftover_words(Some(3)).expect("words"),
        "No homework added"
    );
    let finished = [block(
        "math-1",
        "flexible",
        json!([3]),
        Some("15:00"),
        45,
        json!({"assignment_id": "math", "title": "Math worksheet", "completed": true, "completed_day": 3}),
    )];
    let math_done =
        object(json!({"math": with(homework()["math"].clone(), json!({"completed": true}))}));
    let (_, done) = view(&finished, &math_done, None);
    assert_eq!(done.leftover_kind(Some(3)).expect("kind"), "all_finished");
    assert_eq!(
        done.leftover_words(Some(3)).expect("words"),
        "All homework finished"
    );
    let (_, school) = view(
        &[block(
            "school",
            "locked",
            json!([3]),
            Some("08:00"),
            390,
            json!({}),
        )],
        &Map::new(),
        None,
    );
    assert_eq!(
        school.leftover_kind(Some(3)).expect("kind"),
        "calendar_only"
    );
    assert_eq!(
        school.leftover_words(Some(3)).expect("words"),
        "Nothing else scheduled today"
    );
}
