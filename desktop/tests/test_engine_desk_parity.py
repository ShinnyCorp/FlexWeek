"""Each desk module against the Python reference in `desk_ref` (the modules at 6e86802).

Results are compared by `repr`, so dict key order, list against tuple and int against float count as
differences, as they do for a caller. The first tests cover functions the other desktop tests never
call; the rest pin each difference the shadow run found once it was fixed.
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import importlib
import inspect
import json
import os
import re
import time
import types
import uuid
from datetime import date, datetime

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import desk_ref.calendar as ref_calendar
import desk_ref.custom_look as ref_look
import desk_ref.files as ref_files
import desk_ref.focus as ref_focus
import desk_ref.history as ref_history
import desk_ref.pomodoro as ref_pomodoro
import desk_ref.remind as ref_remind
import desk_ref.reuse as ref_reuse
import desk_ref.tokens as ref_tokens
import desk_ref.update as ref_update
import desk_ref.weekmodel as ref_weekmodel
import desktop.native.calendar as live_calendar
import desktop.native.custom_look as live_look
import desktop.native.files as live_files
import desktop.native.focus as live_focus
import desktop.native.history as live_history
import desktop.native.pomodoro as live_pomodoro
import desktop.native.remind as live_remind
import desktop.native.reuse as live_reuse
import desktop.native.tokens as live_tokens
import desktop.native.update as live_update
import desktop.native.weekmodel as live_weekmodel

CHECK = settings(max_examples=30, deadline=None)
WIDE = settings(max_examples=300, deadline=None)
WEEK = "2026-09-21"
TAG = "https://github.com/j0nsh1n/FlexWeek/releases/tag/"
HEX = st.from_regex(r"#[0-9a-f]{6}", fullmatch=True)
DAY = st.integers(min_value=0, max_value=6)
MINUTE = st.integers(min_value=0, max_value=24 * 60)


def match(live, ref, *args, **kwargs):
    assert repr(live(*args, **kwargs)) == repr(ref(*args, **kwargs))


def block(**extra):
    body = {
        "id": "soccer",
        "title": "Soccer",
        "kind": "locked",
        "duration_min": 60,
        "days": [0, 2],
        "start": "16:00",
        "category": "exercise",
    }
    body.update(extra)
    return body


def homework(**extra):
    body = {
        "id": "essay",
        "title": "Essay",
        "due": "2026-09-24T21:00",
        "estimate_min": 60,
    }
    body.update(extra)
    return body


def placed(module, item, day, trace):
    value = module.placement_on(item, day, trace)
    if value is module.NOT_TODAY:
        return "NOT_TODAY"
    return value


@CHECK
@given(DAY, st.lists(st.just(block()), max_size=3))
def test_occupied_intervals(day, blocks):
    match(live_calendar.occupied_intervals, ref_calendar.occupied_intervals, blocks, day)


@CHECK
@given(st.integers(min_value=-14, max_value=14))
def test_shifted_month(amount):
    match(live_calendar.shifted_month, ref_calendar.shifted_month, "2026-09", amount)


@CHECK
@given(st.sampled_from(["2026-09-21", "2026-10-01"]))
def test_month_anchor_date(today):
    match(live_calendar.month_anchor_date, ref_calendar.month_anchor_date, "2026-09", today)


@CHECK
@given(DAY)
def test_placement_on(day):
    item = block()
    assert repr(placed(live_calendar, item, day, None)) == repr(placed(ref_calendar, item, day, None))


@CHECK
@given(st.booleans())
def test_next_action_for(done):
    item = block(assignment_id="essay", completed=done, kind="flexible", days=[0])
    sessions = [{"block": item, "start": "16:00"}]
    due = [homework()]
    assignments = {"essay": homework(completed=done)}
    match(
        live_calendar.next_action_for,
        ref_calendar.next_action_for,
        sessions,
        due,
        assignments,
        None,
    )


@CHECK
@given(st.just(homework()))
def test_assignment_body(item):
    match(live_files.assignment_body, ref_files.assignment_body, item)


@CHECK
@given(st.just(block()))
def test_exportable_block(item):
    match(live_files.exportable_block, ref_files.exportable_block, item, {})


@CHECK
@given(st.just(block(assignment_id="essay")))
def test_referenced_assignments(item):
    match(
        live_files.referenced_assignments,
        ref_files.referenced_assignments,
        [item],
        {"essay": homework()},
    )


@CHECK
@given(DAY, st.text(min_size=1, max_size=40, alphabet="abc"))
def test_occurrence_import_id(day, block_id):
    match(live_files.occurrence_import_id, ref_files.occurrence_import_id, day, block_id)


@CHECK
@given(st.integers(), st.text())
def test_same_value(number, text):
    match(live_history.same_value, ref_history.same_value, {"n": number, "t": text}, {"t": text, "n": number})


@CHECK
@given(st.integers(min_value=1, max_value=90))
def test_timers(work):
    match(live_pomodoro.timers, ref_pomodoro.timers, {"timer_work_min": work})


@CHECK
@given(MINUTE, MINUTE)
def test_song_due(start, now):
    match(live_remind.song_due, ref_remind.song_due, start, now)


@CHECK
@given(DAY, st.text(min_size=1, max_size=8, alphabet="abc"))
def test_reminder_key(day, block_id):
    match(live_remind.reminder_key, ref_remind.reminder_key, WEEK, block_id, day, "16:00")


@CHECK
@given(st.text(min_size=0, max_size=8, alphabet="abc"))
def test_alarm_key(alarm_id):
    match(live_remind.alarm_key, ref_remind.alarm_key, "2026-09-24", {"id": alarm_id, "time": "07:30"})


@CHECK
@given(st.booleans())
def test_reminder_blocks(with_trace):
    blocks = [block(), block(id="essay", kind="flexible", assignment_id="essay", days=[1])]
    trace = {"placed": [block(id="essay", kind="flexible", days=[1])]} if with_trace else None
    match(live_remind.reminder_blocks, ref_remind.reminder_blocks, blocks, trace)


@CHECK
@given(st.just("2026-09-21"))
def test_todays_starts(today):
    blocks = [block(days=[0])]
    assert repr(list(live_remind.todays_starts(blocks, None, today))) == repr(
        list(ref_remind.todays_starts(blocks, None, today))
    )


@CHECK
@given(st.integers(min_value=-20, max_value=24 * 60))
def test_floor_slot(minutes):
    match(live_reuse.floor_slot, ref_reuse.floor_slot, minutes)


@CHECK
@given(st.booleans())
def test_is_homework_session(linked):
    item = block(assignment_id="essay") if linked else block()
    match(live_reuse.is_homework_session, ref_reuse.is_homework_session, item)


@CHECK
@given(st.booleans())
def test_planning_days(linked):
    item = block(assignment_id="essay") if linked else block()
    assignments = {"essay": homework()} if linked else {}
    match(live_reuse.planning_days, ref_reuse.planning_days, item, assignments, WEEK)


@CHECK
@given(st.just(block(kind="flexible", assignment_id="essay", days=[1], start="10:00")))
def test_held_in_place(item):
    match(live_reuse.held_in_place, ref_reuse.held_in_place, item)


@CHECK
@given(st.just("essay"))
def test_session_minutes(assignment_id):
    blocks = [block(assignment_id=assignment_id, duration_min=60), block(duration_min=30)]
    match(live_reuse.session_minutes, ref_reuse.session_minutes, blocks, assignment_id)


@CHECK
@given(st.integers(min_value=0, max_value=100), st.integers(min_value=0, max_value=100))
def test_intervals_overlap(start, end):
    match(live_reuse.intervals_overlap, ref_reuse.intervals_overlap, start, start + end, 40, 70)


@CHECK
@given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
def test_hex_from_linear(channel):
    match(live_tokens.hex_from_linear, ref_tokens.hex_from_linear, channel, channel, channel)


@CHECK
@given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
def test_linear_from_oklab(light):
    match(live_tokens.linear_from_oklab, ref_tokens.linear_from_oklab, light, 0.0, 0.0)


@CHECK
@given(st.sampled_from(["windows", "appimage", "tarball"]))
def test_asset_name(kind):
    match(live_update.asset_name, ref_update.asset_name, kind)


def test_release_from_page_rejects_hostile_tags():
    hostile = [
        TAG + "v9.9.9/../../evil",
        TAG + "v1.2.3?download=1",
        TAG + "v1.2.3/extra",
    ]
    for location in hostile:
        assert live_update.release_from_page(location) is None
        assert ref_update.release_from_page(location) is None
    match(live_update.release_from_page, ref_update.release_from_page, TAG + "v1.2.3")


def test_merge_keeps_the_other_days_of_a_series():
    existing = [block()]
    incoming = [block(days=[0], start="17:00")]
    match(live_files.merge_imported_blocks, ref_files.merge_imported_blocks, existing, incoming, "merge", 0)


def test_export_payloads_keep_defaults():
    blocks = [block(id="sess", title="Essay", kind="flexible", days=[0, 1, 2, 3, 4], assignment_id="essay")]
    assignments = {"essay": homework()}
    match(live_files.export_week_payload, ref_files.export_week_payload, WEEK, blocks, assignments)
    match(live_files.export_day_payload, ref_files.export_day_payload, WEEK, 0, [block()], {})


def test_parse_repeats_the_whole_homework_sentence():
    raw = json.dumps(
        {
            "format": "flexweek-week",
            "version": 2,
            "week_start": "2026-09-14",
            "blocks": [],
            "assignments": [homework(), homework()],
        }
    )
    parsed = live_files.parse_import_payload(raw)
    assert repr(parsed) == repr(ref_files.parse_import_payload(raw))
    assert parsed["error"] == "Export repeats the homework id essay. Nothing was imported."


def test_plan_start_rounds_a_half_minute_up_to_the_quarter_hour():
    now = datetime(2026, 9, 24, 10, 0, 30)
    assert live_reuse.plan_start(WEEK, now) == ref_reuse.plan_start(WEEK, now) == (3, 615)


def test_now_next_line_keeps_the_wait_when_nothing_is_current():
    result = {
        "current": None,
        "next": {"title": "Soccer practice", "start": "16:00", "duration_min": 60},
    }
    text = live_focus.now_next_line(result, 14 * 60)
    assert text == ref_focus.now_next_line(result, 14 * 60)
    assert "(in " in text


def test_copy_label_says_only():
    match(live_reuse.copy_label, ref_reuse.copy_label, block(), 4, "once")


def test_child_title_counts_characters():
    title = "x" * 80
    match(live_pomodoro.child_title, ref_pomodoro.child_title, title, 2, 9)


def test_type_pt_rounds_half_to_even():
    assert live_tokens.type_pt("body", 1.25) == ref_tokens.type_pt("body", 1.25) == 16.0


@CHECK
@given(HEX)
def test_oklab_matches_bit_for_bit(colour):
    match(live_tokens.oklab, ref_tokens.oklab, colour)
    match(live_tokens.oklch_of, ref_tokens.oklch_of, colour)


@CHECK
@given(
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_oklab_from_linear_matches_bit_for_bit(red, green, blue):
    match(live_tokens.oklab_from_linear, ref_tokens.oklab_from_linear, red, green, blue)


def test_clipboard_fingerprint_uses_pythons_separators():
    items = [
        {
            "block": block(),
            "source_day": 4,
            "scope": "once",
            "group_id": "g",
        }
    ]
    live = live_reuse.clipboard_fingerprint(items)
    assert live == ref_reuse.clipboard_fingerprint(items)
    assert ": " in live


@CHECK
@given(HEX, st.booleans())
def test_readability_follows_the_colour_maths(accent, system_dark):
    custom = {"accent": accent}

    def rows(module):
        return [
            (item.words, item.ink, item.ground, item.ratio, item.field, item.fixed)
            for item in module.readability(custom, system_dark)
        ]

    assert repr(rows(live_look)) == repr(rows(ref_look))


def test_readability_offers_black_where_the_original_does():
    custom = {"base": "system", "name": "My look", "colours": {"page": "#1e2430"}}
    fixes = [item.fixed for item in live_look.readability(custom, False)]
    assert repr(fixes) == repr([item.fixed for item in ref_look.readability(custom, False)])
    assert fixes[0] == "#000000"


def test_every_coarse_colour_matches_bit_for_bit():
    steps = [f"{value:02x}" for value in range(0, 256, 17)]
    colours = [f"#{red}{green}{blue}" for red in steps for green in steps for blue in steps]
    assert repr([live_tokens.oklab(colour) for colour in colours]) == repr(
        [ref_tokens.oklab(colour) for colour in colours]
    )
    assert repr([live_tokens.oklch_of(colour) for colour in colours]) == repr(
        [ref_tokens.oklch_of(colour) for colour in colours]
    )


def session(**extra):
    """A planned homework session whose middle keys a function drops, as the app's blocks have."""
    body = {
        "id": "sess",
        "title": "Essay",
        "kind": "flexible",
        "duration_min": 60,
        "days": [1],
        "start": "16:00",
        "pinned": True,
        "completed_day": None,
        "priority": 3,
        "course": "History",
        "spotify_url": None,
        "assignment_id": "essay",
    }
    body.update(extra)
    return body


def test_apply_plan_keeps_the_key_order():
    trace = {"placed": [], "unplaced": [{"id": "sess"}]}
    match(
        live_reuse.apply_plan,
        ref_reuse.apply_plan,
        [session()],
        trace,
        assignments={"essay": homework()},
        week_start=WEEK,
    )


def test_solve_request_keeps_the_key_order():
    match(
        live_reuse.solve_request,
        ref_reuse.solve_request,
        [session(pinned=None)],
        {"essay": homework()},
        WEEK,
        everything=True,
    )


def test_settle_placements_keeps_the_key_order():
    late = session(start="23:30", pinned=None)
    match(live_reuse.settle_placements, ref_reuse.settle_placements, [late], {"essay": homework()}, WEEK)


def test_copied_fixed_block_keeps_the_key_order():
    match(live_reuse.copied_fixed_block, ref_reuse.copied_fixed_block, session(), [2], "copy")


def test_routine_rows_keep_the_key_order():
    routine = {
        "blocks": [
            {
                "template_id": "run",
                "title": "Run",
                "days": [0, 2],
                "start": "07:00",
                "duration_min": 30,
                "category": "exercise",
            }
        ]
    }
    match(live_reuse.routine_rows, ref_reuse.routine_rows, routine, WEEK, [0, 1, 2])


POMODORO = {"auto_split_pomodoro": True}


def numbered(blocks):
    """Each block's id replaced by its position, in place, since a split gives every chunk a new random
    id on each side."""
    return [{**item, "id": index} for index, item in enumerate(blocks)]


def split(source):
    """The chunks and breaks of `source` placed on Tuesday at 16:00, from both sides."""
    plan = ref_pomodoro.plan_for(source["duration_min"], POMODORO)
    placed_at = {"days": [1], "start": "16:00"}
    live = numbered(live_pomodoro.split_children(source, placed_at, plan))
    ref = numbered(ref_pomodoro.split_children(source, placed_at, plan))
    assert len(ref) > 2, "the source must really split, with a break, or the test checks nothing"
    return live, ref


def test_split_children_keep_the_key_order():
    live, ref = split(session(duration_min=120, pomodoro_role=None))
    assert repr(live) == repr(ref)


def test_split_solved_keeps_the_key_order():
    source = session(duration_min=120, start=None, pinned=None, days=[1, 2], pomodoro_role=None)
    trace = {"placed": [{"id": "sess", "days": [1], "start": "16:00"}]}
    live, live_count = live_pomodoro.split_solved([source], trace, POMODORO)
    ref, ref_count = ref_pomodoro.split_solved([source], trace, POMODORO)
    assert live_count == ref_count == 1
    assert repr(numbered(live)) == repr(numbered(ref))


def test_a_null_link_is_not_homework():
    for value in (None, ""):
        item = block(assignment_id=value)
        match(live_reuse.is_homework_session, ref_reuse.is_homework_session, item)
    assert live_reuse.is_homework_session(block(assignment_id=None)) is False


def test_a_null_pomodoro_role_still_splits():
    item = session(duration_min=120, pomodoro_role=None)
    assert live_pomodoro.splittable(item, POMODORO) is ref_pomodoro.splittable(item, POMODORO) is True


def test_split_children_of_unlinked_work_keep_its_focus():
    live, ref = split(session(duration_min=120, assignment_id=None, focus_sessions=2, focus_minutes=50))
    assert repr(live) == repr(ref)
    assert live[0]["focus_minutes"] == 50


def test_week_focus_counts_blocks_with_a_null_link():
    blocks = [block(days=[0], assignment_id=None, focus_minutes=25)]
    live = live_weekmodel.build_week(WEEK, blocks, {}, None)
    ref = ref_weekmodel.build_week(WEEK, blocks, {}, None)
    assert repr(live) == repr(ref)
    assert live.focus_min == 25


def test_unplanned_minutes_of_null_mean_not_known():
    assignment = homework(id="essay", unplanned_min=None, focus_minutes=15)
    match(live_reuse.available_homework_minutes, ref_reuse.available_homework_minutes, assignment, [])
    assert live_reuse.available_homework_minutes(assignment, []) == 45


def test_merge_skips_empty_and_idless_blocks():
    incoming = [{}, block(id="")]
    match(
        live_files.merge_imported_blocks, ref_files.merge_imported_blocks, [block()], incoming, "merge", None
    )


def test_relocating_a_null_linked_block_does_not_pin_it():
    item = block(kind="flexible", assignment_id=None, days=[1], start="16:00")
    match(live_calendar.relocate_block, ref_calendar.relocate_block, [item], "soccer", 1, 2)


def outcome(function, *args):
    try:
        return "ok", repr(function(*args))
    except Exception as error:  # noqa: BLE001
        return "raise", type(error).__name__, str(error)


def test_look_names_are_checked_alike():
    for name in ("  My   look ", "", "   ", 7, "x" * 200, "Default", "default"):
        assert outcome(live_look._name, name) == outcome(ref_look._name, name)


def test_finding_a_saved_look_ignores_case():
    saved = [{"name": "Night"}, {"name": "Day"}]
    for name in ("night", "DAY", "Dusk"):
        match(live_look._find, ref_look._find, saved, name)


def test_agenda_counts_only_linked_work_chunks():
    chunks = [
        block(id=f"chunk{index}", pomodoro_role="work", assignment_id=link, days=[0], start=start)
        for index, (link, start) in enumerate((("essay", "16:00"), (None, "17:00"), ("", "18:00")))
    ]
    match(
        live_calendar.agenda_for,
        ref_calendar.agenda_for,
        WEEK,
        WEEK,
        chunks,
        {"essay": homework()},
        None,
        None,
    )


@CHECK
@given(HEX)
def test_channels(colour):
    match(live_tokens._channels, ref_tokens._channels, colour)


def test_every_channel_level_decodes_and_encodes_alike():
    for level in range(256):
        colour = f"#{level:02x}{level:02x}{level:02x}"
        match(live_tokens.linear_rgb, ref_tokens.linear_rgb, colour)
        value = level / 255
        match(live_tokens.hex_from_linear, ref_tokens.hex_from_linear, value, value / 2, value / 3)


@CHECK
@given(MINUTE, MINUTE)
def test_twelve_hour_labels(start, end):
    # Under the shadow run each live call also runs the reference, so the reference's own setting is
    # read, not inferred from what set_clock_24h returns.
    ref_was_24h = ref_weekmodel._clock["24h"]
    was_24h = live_weekmodel.set_clock_24h(False)
    ref_weekmodel.set_clock_24h(False)
    try:
        match(live_weekmodel.short_clock, ref_weekmodel.short_clock, start)
        match(live_weekmodel.range_label, ref_weekmodel.range_label, start, end)
    finally:
        live_weekmodel.set_clock_24h(was_24h)
        ref_weekmodel.set_clock_24h(ref_was_24h)


@CHECK
@given(DAY, st.integers(min_value=0, max_value=95).map(lambda slot: slot * 15))
def test_solve_request_from_now(day, minute):
    blocks = [
        session(pinned=None, days=[1], start="16:00"),
        session(id="later", pinned=None, days=[4], start="10:00"),
        session(id="open", pinned=None, start=None, days=[0, 1, 2, 3, 4]),
    ]
    match(
        live_reuse.solve_request,
        ref_reuse.solve_request,
        blocks,
        {"essay": homework()},
        WEEK,
        everything=True,
        not_before=(day, minute),
    )


# The functions that stayed in Python until the last step of E5. Each test hands the live function and
# the reference one their own deep copy of generated arguments, and requires the same result (by
# `repr`), the same raised error (type and message) and the same arguments afterwards.


def produced(func, args, kwargs, listed=False):
    try:
        value = func(*args, **kwargs)
        return ("ok", repr(list(value) if listed else value))
    except Exception as error:  # noqa: BLE001
        return ("raise", type(error).__name__, str(error))


def same(live, ref, *args, listed=False, **kwargs):
    live_call, ref_call = copy.deepcopy((args, kwargs)), copy.deepcopy((args, kwargs))
    assert produced(live, live_call[0], live_call[1], listed) == produced(
        ref, ref_call[0], ref_call[1], listed
    )
    assert repr(live_call) == repr(ref_call)


@contextlib.contextmanager
def local_zone(name):
    was = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if was is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = was
        time.tzset()


ZONES = st.sampled_from(["UTC", "America/New_York", "Europe/Berlin", "Australia/Lord_Howe", "Asia/Kolkata"])
TODAYS = st.sampled_from(["2026-09-21", "2026-09-22", "2026-09-24", "2026-09-27", "2026-10-04"])
BAD_TODAYS = st.sampled_from(
    [
        "x",
        "2026-13-01",
        "2026-02-30",
        "2026-04-31",
        "20260924",
        "2026-W39-4",
        "2026W394",
        "2026W39",
        "2026-W39",
        "2026W39-4",
        "2026-W394",
        "2026-W00-1",
        "2026-W54-1",
        "2026-W53-7",
        "2025-W53-1",
        "2026-W39-8",
        "",
        "2026-9-4",
        "0000-01-01",
        "2026-00-10",
        "2026-01-00",
        "9999-12-31",
        "２０２６-09-21",
        "2026-09-24T10:00",
        " 2026-09-24",
    ]
)


def maybe(*values):
    return st.sampled_from(values)


def remind_block(clean):
    """A block as the week holds them; with `clean` off, ids, starts and flags of the wrong kind too."""
    return st.fixed_dictionaries(
        {"id": maybe("a", "b", "c") if clean else maybe("a", "b", 7, None, "")},
        optional={
            "kind": maybe("locked", "flexible") if clean else maybe("locked", "flexible", None),
            "title": maybe("Study", "Ünï", "") if clean else maybe("Study", "", None, 5),
            "start": maybe("08:30", "16:00", "09:05", "7:05")
            if clean
            else maybe(None, "", "x", "25:00", 830, "9:5"),
            "days": st.lists(DAY, max_size=3),
            "completed": maybe(None, False, True),
            "completed_day": maybe(None, 0, 1, 2, 3),
            "missed_days": st.lists(DAY, max_size=2),
            "spotify_url": maybe(None, "", "https://open.spotify.com/track/x"),
        },
    )


REMIND_BLOCK = remind_block(True)
REMIND_TRACE = st.one_of(
    st.none(),
    st.just({}),
    st.fixed_dictionaries({"placed": st.lists(REMIND_BLOCK, max_size=3)}),
)


@CHECK
@given(st.integers(min_value=-2_000_000_000_000, max_value=4_100_000_000_000), ZONES)
def test_clock_parts_reads_the_local_clock(now_ms, zone):
    with local_zone(zone):
        same(live_remind.clock_parts, ref_remind.clock_parts, now_ms)


def test_clock_parts_in_a_zone_with_daylight_saving():
    # 2026-03-08 07:30 UTC is 03:30 in New York, the morning the clocks went forward.
    stamp = 1_772_955_000_000
    with local_zone("America/New_York"):
        assert live_remind.clock_parts(stamp) == {
            "iso": "2026-03-08",
            "day": 6,
            "minute": 3 * 60 + 30,
            "midnight_ms": 1_772_946_000_000,
            "now_ms": stamp,
        }
        same(live_remind.clock_parts, ref_remind.clock_parts, stamp)


@st.composite
def week_with_a_start_today(draw):
    """Blocks whose days mostly include today's weekday, so the missed-day and completed rules bite."""
    today = draw(TODAYS)
    weekday = datetime.fromisoformat(today).weekday()
    block_today = remind_block(True).map(lambda body: body)
    blocks = []
    for _ in range(draw(st.integers(1, 4))):
        body = draw(block_today)
        body["days"] = draw(
            st.sampled_from([[weekday], [weekday, (weekday + 1) % 7], [(weekday + 3) % 7], []])
        )
        body["missed_days"] = draw(st.sampled_from([[], [weekday], [(weekday + 1) % 7]]))
        blocks.append(body)
    trace = draw(
        st.one_of(st.none(), st.just({"placed": [dict(body, kind="flexible") for body in blocks[:2]]}))
    )
    return blocks, trace, today


@WIDE
@given(week_with_a_start_today())
def test_todays_starts_on_generated_weeks(week):
    same(live_remind.todays_starts, ref_remind.todays_starts, *week, listed=True)


@CHECK
@given(
    st.lists(remind_block(False), min_size=1, max_size=3),
    st.one_of(st.none(), st.fixed_dictionaries({"placed": st.lists(remind_block(False), max_size=2)})),
    st.one_of(TODAYS, BAD_TODAYS),
)
def test_todays_starts_on_malformed_weeks(blocks, trace, today):
    same(live_remind.todays_starts, ref_remind.todays_starts, blocks, trace, today, listed=True)


ALARM_TIMES = [
    "",
    "07:30",
    "7:30",
    "00:00",
    "23:59",
    "x",
    "25:00",
    "08:60",
    "5",
    "1:2:3",
    "1:2:x",
    "10:30",
    730,
    None,
]


def alarm_on(weekday):
    """An alarm that mostly rings on `weekday` and is mostly on, so the time rules are reached."""
    return st.fixed_dictionaries(
        {"time": st.one_of(maybe("07:30", "10:30", "23:59", "00:00"), maybe(*ALARM_TIMES))},
        optional={
            "id": maybe("a", "b", 3, "", None),
            "name": maybe("Wake", None),
            "enabled": maybe(True, True, True, False, None),
            "days": maybe([weekday], [weekday, (weekday + 2) % 7], [(weekday + 1) % 7], []),
        },
    )


@WIDE
@given(
    TODAYS,
    st.sets(st.sampled_from(["2026-09-24|a|07:30", "2026-09-24|b|10:30", "2026-09-24|3|23:59"]), max_size=2),
    ZONES,
    st.data(),
)
def test_due_alarms_on_generated_alarms(today, fired, zone, data):
    base = 1_790_000_000_000
    weekday = datetime.fromisoformat(today).weekday()
    alarms = data.draw(st.lists(alarm_on(weekday), max_size=4))
    with local_zone(zone):
        # Edges as well as the middle: a time found on the minute, a millisecond either side of it.
        edges = [base]
        for alarm in alarms:
            parts = str(alarm.get("time")).split(":")
            if (
                len(parts) == 2
                and all(part.isdigit() for part in parts)
                and int(parts[0]) < 24
                and int(parts[1]) < 60
            ):
                moment = datetime.fromisoformat(today).replace(hour=int(parts[0]), minute=int(parts[1]))
                edges += [int(moment.timestamp() * 1000) + step for step in (-1, 0, 1)]
        times = st.one_of(
            st.sampled_from(edges),
            st.integers(min_value=base - 3 * 24 * 3_600_000, max_value=base + 3 * 24 * 3_600_000),
        )
        now_ms = data.draw(times)
        last_check = data.draw(st.one_of(st.none(), times))
        snoozed = data.draw(st.dictionaries(st.sampled_from(["a", "b", "c"]), times, max_size=3))
        same(
            live_remind.due_alarms,
            ref_remind.due_alarms,
            alarms=alarms,
            today_iso=today,
            weekday=data.draw(st.one_of(st.just(weekday), DAY)),
            now_ms=now_ms,
            midnight_ms=base,
            last_check_ms=last_check,
            fired=fired,
            snoozed=snoozed,
        )


@CHECK
@given(BAD_TODAYS, st.lists(alarm_on(0), min_size=1, max_size=2))
def test_due_alarms_on_a_bad_date(today, alarms):
    same(
        live_remind.due_alarms,
        ref_remind.due_alarms,
        alarms=alarms,
        today_iso=today,
        weekday=0,
        now_ms=1_790_000_000_000,
        midnight_ms=0,
        last_check_ms=1_700_000_000_000,
        fired=set(),
        snoozed={},
    )


@CHECK
@given(
    st.one_of(
        st.none(),
        st.dictionaries(
            st.sampled_from(["reminder_lead_min", "other"]),
            st.one_of(st.none(), st.integers(-5, 90), st.sampled_from(["7", "x", 7.9, True, ""])),
            max_size=2,
        ),
    ),
    st.integers(0, 30),
)
def test_reminder_lead_min_on_generated_prefs(prefs, default):
    same(live_remind.reminder_lead_min, ref_remind.reminder_lead_min, prefs, default)


@CHECK
@given(
    st.dictionaries(
        st.sampled_from(["id", "time"]),
        st.one_of(
            st.none(), st.integers(-3, 3), st.sampled_from(["", "a", "07:30", "é"]), st.just(1.5), st.just(0)
        ),
    )
)
def test_alarm_key_prints_what_the_original_prints(alarm):
    same(live_remind.alarm_key, ref_remind.alarm_key, "2026-09-24", alarm)


@CHECK
@given(
    st.lists(remind_block(False), max_size=3),
    st.one_of(
        st.none(),
        st.just({}),
        st.fixed_dictionaries(
            {"placed": st.lists(remind_block(False), max_size=3)},
            optional={"other": maybe(1, None)},
        ),
    ),
)
def test_reminder_blocks_on_generated_weeks(blocks, trace):
    same(live_remind.reminder_blocks, ref_remind.reminder_blocks, blocks, trace)


@CHECK
@given(
    st.lists(REMIND_BLOCK, max_size=4),
    REMIND_TRACE,
    TODAYS,
    st.integers(7 * 60, 18 * 60),
    st.integers(0, 15),
    st.sets(st.sampled_from(["2026-09-21|a|0|08:30", "2026-09-21|b|0|16:00"]), max_size=2),
)
def test_due_reminders_and_songs_on_generated_weeks(blocks, trace, today, now_min, lead, fired):
    same(
        live_remind.due_reminders,
        ref_remind.due_reminders,
        blocks=blocks,
        trace=trace,
        today_iso=today,
        now_min=now_min,
        lead_min=lead,
        fired=fired,
    )
    same(
        live_remind.due_songs,
        ref_remind.due_songs,
        blocks=blocks,
        trace=trace,
        today_iso=today,
        now_min=now_min,
        played=fired,
    )


def test_an_alarm_is_due_after_the_last_look_up_to_and_including_now():
    # 07:30 on 2026-09-24 in UTC is 1_790_235_000_000 ms.
    due = 1_790_235_000_000
    alarm = {"id": "wake", "time": "07:30", "enabled": True, "days": [3]}

    def poll(now_ms, last_check_ms):
        return live_remind.due_alarms(
            alarms=[alarm],
            today_iso="2026-09-24",
            weekday=3,
            now_ms=now_ms,
            midnight_ms=0,
            last_check_ms=last_check_ms,
            fired=set(),
            snoozed={},
        )[0]

    with local_zone("UTC"):
        assert poll(due, due - 1) == [alarm]
        assert poll(due, due) == []
        assert poll(due - 1, due - 2) == []
        assert poll(due + 5, due - 1) == [alarm]


@st.composite
def fixed_block(draw, **extra):
    body = {
        "id": draw(maybe("b1", "b2", "b3")),
        "title": draw(maybe("Soccer", "Lunch", "Ünï", "")),
        "kind": "locked",
        "duration_min": draw(maybe(15, 30, 45, 60, 90, 120)),
        "days": draw(st.lists(DAY, min_size=1, max_size=3, unique=True)),
        "start": draw(maybe("08:00", "09:30", "16:00", "09:45", None)),
        "category": draw(maybe("class", "exercise", None)),
    }
    for name, values in {
        "course": ("Maths", None),
        "priority": (1, 3, None),
        "energy": ("low", "high", None),
        "spotify_url": ("https://open.spotify.com/track/x", None),
        "assignment_id": (None,),
        "pomodoro_role": (None, "work"),
        "template_id": (None, "t1"),
        "missed_days": ([], [0]),
        "completed": (False, True),
    }.items():
        if draw(st.booleans()):
            body[name] = draw(st.sampled_from(values))
    body.update(extra)
    return body


@st.composite
def homework_block(draw):
    return draw(fixed_block(kind="flexible", assignment_id=draw(maybe("essay", "lab", "ghost"))))


def assignment(**extra):
    body = {
        "id": "essay",
        "title": "Essay",
        "due": "2026-09-24T21:00",
        "estimate_min": 120,
        "priority": 2,
        "energy": "high",
        "course": "English",
        "category": "assignments",
        "spotify_url": None,
        "completed": False,
        "focus_minutes": 15,
        "unplanned_min": 60,
    }
    body.update(extra)
    return body


ASSIGNMENTS = st.fixed_dictionaries(
    {},
    optional={
        "essay": st.builds(assignment, priority=maybe(None, 0, 4), energy=maybe(None, "", "low")),
        "lab": st.builds(
            assignment,
            id=st.just("lab"),
            title=maybe("Lab", "Ünï"),
            due=maybe("2026-09-22", "2026-09-30T08:00", None, ""),
            unplanned_min=maybe(None, 0, 30, 45, 120),
            completed=maybe(False, True, None),
            estimate_min=maybe(30, 90),
        ),
    },
)
AVAILABLE = st.dictionaries(maybe("essay", "lab", "other"), st.integers(0, 120), max_size=3)
CLIP_ITEM = st.builds(
    lambda block, scope, group, source_day: {
        "block": block,
        "source_day": source_day,
        "scope": scope,
        "group_id": group,
    },
    st.one_of(fixed_block(), homework_block()),
    maybe("block", "series", "day"),
    maybe("g1", "g2", "g-3"),
    DAY,
)


@CHECK
@given(
    st.lists(CLIP_ITEM, max_size=4),
    maybe("block", "day", "week"),
    maybe("2026-09-21", "2026-09-28"),
    DAY,
    maybe("10:00", None, ""),
    ASSIGNMENTS,
    AVAILABLE,
)
def test_proposals_from_clipboard_on_generated_items(items, kind, week, day, start, assignments, available):
    same(
        live_reuse.proposals_from_clipboard,
        ref_reuse.proposals_from_clipboard,
        items,
        kind=kind,
        week_start=week,
        target_day=day,
        target_start=start,
        assignments=assignments,
        available=available,
    )


@CHECK
@given(
    st.lists(st.one_of(fixed_block().map(lambda body: {"block": body}), st.just({})), max_size=2),
    maybe("block", "series"),
)
def test_proposals_from_clipboard_on_malformed_items(items, scope):
    for item in items:
        item.update(source_day=0, scope=scope)
    same(
        live_reuse.proposals_from_clipboard,
        ref_reuse.proposals_from_clipboard,
        items,
        kind="block",
        week_start="2026-09-21",
        target_day=1,
        target_start=None,
        assignments={},
        available={},
    )


@st.composite
def preview_rows(draw, edited=True):
    """Rows as the paste preview holds them: made by the reference, then ticked and edited."""
    rows = ref_reuse.proposals_from_clipboard(
        draw(st.lists(CLIP_ITEM, min_size=1, max_size=4)),
        kind=draw(maybe("block", "day")),
        week_start="2026-09-21",
        target_day=draw(DAY),
        target_start=draw(maybe("10:00", None)),
        assignments=draw(ASSIGNMENTS),
        available=draw(AVAILABLE),
    )
    rows = copy.deepcopy(rows)
    for row in rows if edited else []:
        row["checked"] = draw(st.booleans())
        row["week_start"] = draw(maybe("2026-09-21", "2026-09-28"))
        if draw(st.booleans()):
            row["day"] = draw(DAY)
        if draw(st.booleans()):
            row["block"]["start"] = draw(maybe("08:30", "09:00", "16:00", None))
    return rows


@CHECK
@given(preview_rows(), maybe("op-1", "0123456789-abcdef-0123456789-xyz", ""))
def test_merge_preview_rows_on_generated_rows(rows, operation_id):
    same(live_reuse.merge_preview_rows, ref_reuse.merge_preview_rows, rows, operation_id)


@CHECK
@given(preview_rows(edited=False), maybe("op-1", "0123456789-abcdef-0123456789-xyz"))
def test_merge_preview_rows_on_untouched_rows(rows, operation_id):
    same(live_reuse.merge_preview_rows, ref_reuse.merge_preview_rows, rows, operation_id)


def test_a_series_pasted_on_days_out_of_order_merges_into_one_sorted_block():
    series = {
        "block": block(days=[4, 1, 4, 2], start="16:00"),
        "source_day": 1,
        "scope": "series",
        "group_id": "g",
    }
    rows = live_reuse.proposals_from_clipboard(
        [series],
        kind="block",
        week_start=WEEK,
        target_day=0,
        target_start=None,
        assignments={},
        available={},
    )
    merged = live_reuse.merge_preview_rows(rows, "ab-cd")
    assert [item["block"]["days"] for item in merged] == [[1, 2, 4]]
    assert [item["block"]["id"] for item in merged] == ["b-stage3-abcd-0"]


@CHECK
@given(preview_rows(), st.lists(fixed_block(), max_size=3))
def test_preview_conflict_message_on_generated_rows(rows, existing):
    for row in rows:
        same(live_reuse.preview_conflict_message, ref_reuse.preview_conflict_message, row, rows, existing)


@CHECK
@given(preview_rows())
def test_preview_conflict_message_of_a_row_among_its_copies(rows):
    for row in rows:
        same(live_reuse.row_conflict, ref_reuse.row_conflict, row, rows + [dict(row)], [])


@CHECK
@given(st.lists(st.one_of(fixed_block(), homework_block()), max_size=5))
def test_routine_source_blocks_on_generated_weeks(blocks):
    same(live_reuse.routine_source_blocks, ref_reuse.routine_source_blocks, blocks)


@CHECK
@given(fixed_block(), maybe("t1", "", "ünï"))
def test_routine_template_on_generated_blocks(body, template_id):
    same(live_reuse.routine_template, ref_reuse.routine_template, body, template_id)


@CHECK
@given(
    maybe(
        {}, {"title": "x"}, {"title": "x", "start": "08:00", "days": [0]}, {"title": "x", "duration_min": 5}
    ),
    maybe("t1"),
)
def test_routine_template_on_incomplete_blocks(body, template_id):
    same(live_reuse.routine_template, ref_reuse.routine_template, body, template_id)


@st.composite
def routines(draw):
    templates = [
        ref_reuse.routine_template(draw(fixed_block()), draw(maybe("t1", "t2")))
        for _ in range(draw(st.integers(0, 3)))
    ]
    return draw(maybe({"blocks": templates}, {}, {"blocks": None}, {"name": "x", "blocks": templates}))


@CHECK
@given(routines(), maybe("2026-09-21", "2026-09-28"), st.lists(DAY, max_size=7))
def test_routine_rows_on_generated_routines(routine, week, allowed):
    same(live_reuse.routine_rows, ref_reuse.routine_rows, routine, week, allowed)


@CHECK
@given(
    ASSIGNMENTS,
    st.lists(maybe("2026-09-14", "2026-09-21", "2026-09-28"), max_size=3),
    maybe("2026-09-21", "2026-09-07"),
    st.lists(homework_block(), max_size=4),
    st.lists(homework_block(), max_size=4),
)
def test_unfinished_items_on_generated_weeks(assignments, saved, week, blocks, committed):
    same(live_reuse.unfinished_items, ref_reuse.unfinished_items, assignments, saved, week, blocks, committed)


@CHECK
@given(
    maybe("2026-09-21", "2026-09-28", "2026-10-26", "2026-12-28", "2026-09-23", "x", "2026-13-01"),
    maybe(None, "", "2026-09-23", "2026-10-02", "bad", "2026-9-3"),
    maybe(None, "", "2026-10", "2026-11-15", "bad", "2026-0"),
    maybe("week", "day", "myday", "month", "other"),
    st.booleans(),
    maybe(None, "", "2026-09-30", "2026-12-31", "bad"),
    st.integers(min_value=1_700_000_000_000, max_value=1_800_000_000_000),
    ZONES,
)
def test_planner_title_on_generated_sessions(
    week, session_day, session_month, view, short, selected, now_ms, zone
):
    session = types.SimpleNamespace(
        week_start=week, selected_day=session_day, selected_month=session_month, now_ms=lambda: now_ms
    )
    with local_zone(zone):
        same(
            live_reuse.planner_title,
            ref_reuse.planner_title,
            session,
            view,
            short=short,
            selected_day=selected,
        )


def test_planner_title_of_my_day_reads_the_local_date():
    # 2026-09-30 23:30 UTC is already 1 October in Berlin, and still 30 September in New York.
    stamp = 1_790_811_000_000
    session = types.SimpleNamespace(week_start="2026-09-28", now_ms=lambda: stamp)
    with local_zone("Europe/Berlin"):
        assert live_reuse.planner_title(session, "myday") == "Thursday 1 October"
    with local_zone("America/New_York"):
        assert live_reuse.planner_title(session, "myday") == "Wednesday 30 September"


NAMES = [
    "Night",
    "night",
    "  Night   shift ",
    "My look",
    "",
    "   ",
    " ",
    "a b",
    "x" * 40,
    "x" * 41,
    "Ünï",
    "ÜNÏ",
    "straße",
    "STRASSE",
    "İstanbul",
    "ǅ",
    "light",
    "LIGHT",
    "Pack default",
    "high  contrast",
    "System",
    "nocturne",
    "é\U0001f600",
]
HEXES = [
    "#3d6fc4",
    "#3D6FC4",
    "#abcdef",
    "#12345",
    "#1234567",
    "3d6fc4",
    "#gggggg",
    "#12345\n",
    "red",
    "",
    None,
    5,
]


def raw_look():
    """A custom look as a look file might hold it: every setting right, wrong, or of the wrong kind."""
    return st.fixed_dictionaries(
        {
            "base": maybe(
                "light",
                "dark",
                "system",
                "high-contrast",
                "slate",
                "nocturne",
                "paper",
                "ink",
                "terminal",
                "poster",
                "pastel",
                "light",
                "x",
                "",
                None,
                5,
            )
        },
        optional={
            "name": st.one_of(maybe(*NAMES), maybe(None, 5, ["a"])),
            "accent": st.one_of(
                maybe("default", "sky", "gold", "sea", "sand", "other", None, 5), maybe(*HEXES)
            ),
            "colours": st.one_of(
                st.dictionaries(
                    maybe("page", "card", "text", "line", "muted", "extra"), maybe(*HEXES), max_size=5
                ),
                maybe(None, 5, "x", []),
            ),
            "categories": st.one_of(
                st.dictionaries(
                    maybe("class", "study", "sleep", "assignments", "zzz", "free"),
                    st.one_of(
                        st.fixed_dictionaries(
                            {},
                            optional={
                                "hue": maybe(250, -30, 720.5, 359.999, 0, True, "x", None, 1e300),
                                "colour": maybe(*HEXES),
                            },
                        ),
                        maybe(None, 5, "x", []),
                    ),
                    max_size=4,
                ),
                maybe(None, 5, [], "x"),
            ),
            "spacing": maybe("comfortable", "compact", "x", None, 5),
            "shadows": maybe("none", "soft", "bold", "hard", None),
            "body_font": maybe("sans", "serif", "mono", "x", None),
            "heading_font": maybe("sans", "serif", "mono", "x"),
            "blocks": maybe("edge", "filled", "outline", "outlined", 3),
            "hour_lines": maybe("none", "faint", "clear", "x"),
            "now_line": maybe("accent", "text", "x"),
            "motion": maybe("normal", "extra", "reduce", "off", "x"),
            "show_times": maybe(True, False, 1, "yes", None),
            "show_lengths": maybe(True, False, 0),
            "today_highlight": maybe(True, False, "x"),
            "corners": maybe(0, 16, 8, 7.5, 6.5, 16.5, -1, 0.5, True, "x", None, 8.0),
            "text_scale": maybe(
                0.9, 1.3, 1, 1.0, 1.255, 1.245, 0.125, 0.895, 1.2999, 1.305, True, "x", 1.125
            ),
            "edge_width": maybe(2, 6, 3.5, 2.5, 4.4999, 1, 7, False),
            "mystery": maybe(1, "x"),
            "kind": maybe("x"),
        },
    )


@CHECK
@given(raw_look())
def test_export_look_on_generated_looks(custom):
    same(live_look.export_look, ref_look.export_look, custom)


@CHECK
@given(maybe(None, 5, "x", [], [1]))
def test_export_look_of_something_that_is_not_a_look(custom):
    same(live_look.export_look, ref_look.export_look, custom)


def look_file(custom, kind="FlexWeek look", version=1):
    body = {"kind": kind, "version": version, **custom}
    return json.dumps(body)


@CHECK
@given(
    raw_look(),
    maybe("FlexWeek look", "other", None, 5),
    maybe(1, 2, 0, -1, 1.0, True, "1", None, 10**30),
    st.booleans(),
)
def test_import_look_on_generated_files(custom, kind, version, as_bytes):
    text = look_file(custom, kind, version)
    same(live_look.import_look, ref_look.import_look, text.encode() if as_bytes else text)


LOOK_HEAD = '{"kind": "FlexWeek look", "version": 1, "base": "light"'


@CHECK
@given(
    maybe(
        "",
        "not json",
        "[]",
        "null",
        '"x"',
        "{",
        "NaN",
        LOOK_HEAD + ', "text_scale": NaN}',
        LOOK_HEAD + ', "categories": {"class": {"hue": Infinity}}}',
        LOOK_HEAD + ', "categories": {"class": {"hue": -Infinity, "colour": "#abcdef"}}}',
        '{"kind": "FlexWeek look", "version": NaN, "base": "light"}',
        LOOK_HEAD + ', "colours": NaN, "name": NaN, "accent": Infinity}',
        LOOK_HEAD + ', "name": "caf\\u00e9"}',
        LOOK_HEAD + ', "base": "dark"}',
        LOOK_HEAD + "} trailing",
        "﻿{}",
        " \n{}",
        "x" * 70_000,
        LOOK_HEAD + ', "name": "' + "x" * 65_500 + '"}',
    )
)
def test_import_look_on_odd_text(text):
    same(live_look.import_look, ref_look.import_look, text)
    same(live_look.import_look, ref_look.import_look, text.encode("utf-8"))


def test_import_look_on_text_that_is_not_utf8():
    same(live_look.import_look, ref_look.import_look, b'{"kind": "\xff"}')
    same(live_look.import_look, ref_look.import_look, '{"a": 1}'.encode("utf-16"))


@CHECK
@given(st.one_of(st.lists(raw_look(), max_size=5), maybe(None, "x", {}, 5, [], {"a": 1})))
def test_sanitize_saved_on_generated_lists(raw):
    same(live_look.sanitize_saved, ref_look.sanitize_saved, raw)


@CHECK
@given(
    st.lists(
        st.builds(lambda body, name: {**body, "base": "light", "name": name}, raw_look(), maybe(*NAMES[:12])),
        min_size=1,
        max_size=6,
    )
)
def test_sanitize_saved_drops_a_look_named_twice(raw):
    same(live_look.sanitize_saved, ref_look.sanitize_saved, raw)


@CHECK
@given(st.one_of(maybe(*NAMES), maybe(None, 5, [], b"x")))
def test_look_names_on_generated_names(name):
    for func_pair in ((live_look._name, ref_look._name),):
        assert produced(func_pair[0], (name,), {}) == produced(func_pair[1], (name,), {})


@CHECK
@given(
    st.lists(
        st.one_of(
            st.fixed_dictionaries({"name": maybe(*NAMES)}), maybe({}, {"name": None}, {"name": 5}, 5, None)
        ),
        max_size=4,
    ),
    maybe(*NAMES),
)
def test_finding_a_saved_look_on_generated_lists(saved, name):
    same(live_look._find, ref_look._find, saved, name)


PACKS_AND_JUNK = ["system", "light-frost", "dark-frost", "nocturne", "slate", "other", "", None, 5]


@st.composite
def device_looks(draw):
    look = {}
    if draw(st.booleans()):
        look["preset"] = draw(
            maybe("default", "terminal", "poster", "ink", "high-contrast", "paper", "pastel", "x", None, 5)
        )
    if draw(st.booleans()):
        look["knobs"] = draw(
            st.one_of(
                st.fixed_dictionaries(
                    {},
                    optional={
                        "surface": maybe("flat", "layered", "frost", "x", 5),
                        "corners": maybe("soft", "sharp", "rounded", "round", "pill", None),
                        "depth": maybe("none", "soft", "bold", "flat", "hard"),
                        "font": maybe("sans", "serif", "mono", "x"),
                        "blocks": maybe("edge", "filled", "outline", "outlined"),
                        "density": maybe("comfortable", "compact"),
                        "text": maybe("small", "normal", "large", "huge"),
                    },
                ),
                maybe(None, 5, [], "x"),
            )
        )
    if draw(st.booleans()):
        look["custom"] = draw(st.one_of(raw_look(), maybe(None, 5, "x", [])))
    return draw(st.one_of(st.just(look), maybe(None, 5, "x", [])))


@CHECK
@given(maybe(*PACKS_AND_JUNK), device_looks())
def test_base_of_on_generated_looks(pack, look):
    same(live_look.base_of, ref_look.base_of, pack, look)


@CHECK
@given(maybe(*PACKS_AND_JUNK), device_looks(), maybe("default", "sky", "#ABCDEF", "#abc", "other", None, 5))
def test_start_custom_on_generated_looks(pack, look, accent):
    same(live_look.start_custom, ref_look.start_custom, pack, look, accent)
    same(live_look.start_custom, ref_look.start_custom, pack, look)


@CHECK
@given(device_looks(), st.one_of(raw_look(), maybe(None, 5, "x", [])))
def test_wear_on_generated_looks(look, custom):
    same(live_look.wear, ref_look.wear, look, custom)


@st.composite
def saved_looks(draw):
    names = draw(st.lists(maybe(*NAMES[:12], "Day", "dAy"), max_size=4))
    return [{"base": "light", "name": name} for name in names]


@CHECK
@given(saved_looks(), maybe(*NAMES), raw_look())
def test_saving_looks_on_generated_names(saved, name, custom):
    same(live_look.save_look, ref_look.save_look, saved, custom, name)
    same(live_look.free_name, ref_look.free_name, saved, name)
    same(live_look.rename_look, ref_look.rename_look, saved, "day", name)
    same(live_look.duplicate_look, ref_look.duplicate_look, saved, name)
    same(live_look.delete_look, ref_look.delete_look, saved, name)


def test_the_look_tables_in_the_engine_are_the_ones_in_look_py():
    import flexweek_engine

    import desktop.native.look as look
    from desktop.native.calendar import CATEGORIES

    held = json.loads(flexweek_engine.look_tables())
    wanted = {
        "LOOK_BASES": {key: list(value) for key, value in look.LOOK_BASES.items()},
        "BASE_LABELS": list(look.BASE_LABELS.values()),
        "PACK_LABELS": list(look.PACK_LABELS.values()),
        "PRESET_LABELS": list(look.LOOK_PRESET_LABELS.values()),
        "PACKS": list(look.PACKS),
        "ACCENTS": list(look.ACCENTS),
        "LOOK_KNOBS": {key: list(value) for key, value in look.LOOK_KNOBS.items()},
        "LOOK_DEFAULTS": look.LOOK_DEFAULTS,
        "LOOK_PRESETS": look.LOOK_PRESETS,
        "CUSTOM_CHOICES": {key: list(value) for key, value in look.CUSTOM_CHOICES.items()},
        "CUSTOM_SWITCHES": list(look.CUSTOM_SWITCHES),
        "CUSTOM_RANGES": {key: list(value) for key, value in look.CUSTOM_RANGES.items()},
        "CUSTOM_COLOURS": list(look.CUSTOM_COLOURS),
        "CATEGORIES": [[key, info["label"], info["kind"]] for key, info in CATEGORIES.items()],
    }
    assert held == wanted


def test_base_of_each_pack_and_preset():
    for pack in PACKS_AND_JUNK:
        for look in (None, {}, {"preset": "paper"}, {"preset": "default"}, {"custom": {"base": "slate"}}):
            same(live_look.base_of, ref_look.base_of, pack, look)


EXPORT_ASSIGNMENT = st.fixed_dictionaries(
    {"id": maybe("essay", "lab", "x"), "title": maybe("Essay", "Lab", "")},
    optional={
        "due": maybe("2026-09-24", "2026-09-24T21:00", "bad", None),
        "estimate_min": maybe(15, 60, 0, -5, "x"),
        "course": maybe("English", None),
        "category": maybe("assignments", "study", "x", None),
        "priority": maybe(1, 5, 9, None),
        "energy": maybe("low", "medium", "high", "x"),
        "notes": maybe("", "n", None),
        "links": maybe([], ["https://example.com"], None),
        "completed": maybe(True, False),
        "focus_minutes": maybe(0, 30),
        "unplanned_min": maybe(15, None),
        "stray": maybe(1, "x"),
    },
)
EXPORT_BLOCK = st.one_of(
    fixed_block(),
    homework_block(),
    st.fixed_dictionaries(
        {
            "id": maybe("b1", ""),
            "title": maybe("T", None),
            "kind": maybe("locked", "x"),
            "days": maybe([0], [], [7]),
        },
        optional={
            "duration_min": maybe(15, 7, 0),
            "start": maybe("08:00", "8:0", "25:00", None),
            "assignment_id": maybe("essay", "lab", "gone", "", None, 5, ["essay"]),
        },
    ),
)


@CHECK
@given(EXPORT_ASSIGNMENT)
def test_assignment_body_on_generated_homework(item):
    same(live_files.assignment_body, ref_files.assignment_body, item)


@CHECK
@given(maybe(None, 5, "x", []))
def test_assignment_body_of_something_that_is_not_a_row(item):
    same(live_files.assignment_body, ref_files.assignment_body, item)


@CHECK
@given(EXPORT_BLOCK, st.dictionaries(maybe("essay", "lab"), EXPORT_ASSIGNMENT, max_size=2))
def test_exportable_block_on_generated_blocks(item, assignments):
    same(live_files.exportable_block, ref_files.exportable_block, item, assignments)


@CHECK
@given(
    st.lists(EXPORT_BLOCK, max_size=5),
    st.dictionaries(maybe("essay", "lab", "x"), EXPORT_ASSIGNMENT, max_size=3),
)
def test_referenced_assignments_on_generated_weeks(blocks, assignments):
    same(live_files.referenced_assignments, ref_files.referenced_assignments, blocks, assignments)


@CHECK
@given(
    st.lists(
        maybe(
            {"assignment_id": "essay"},
            {"assignment_id": "lab"},
            {"assignment_id": "gone"},
            {},
            {"assignment_id": None},
            {"assignment_id": ""},
        ),
        max_size=6,
    )
)
def test_referenced_assignments_names_each_homework_once(blocks):
    assignments = {"essay": assignment(), "lab": assignment(id="lab", title="Lab")}
    same(live_files.referenced_assignments, ref_files.referenced_assignments, blocks, assignments)


CHANNEL_TEXT = st.one_of(
    st.from_regex(r"#[0-9a-fA-F]{6}", fullmatch=True),
    st.text(alphabet="#0123456789abcdefABCDEFxX_+-  ٣g", max_size=9),
    maybe(
        "",
        "#",
        "#12",
        "#1234",
        "#12345",
        "#ff",
        "#0x0x0x",
        "#_f_f_f",
        "#-1-1-1",
        "#+f+f+f",
        "# f f f ",
        "#٣٤٥",
    ),
)


@CHECK
@given(CHANNEL_TEXT)
def test_channels_read_each_pair_as_python_does(colour):
    same(live_tokens._channels, ref_tokens._channels, colour)


@WIDE
@given(st.text(alphabet="#0123456789abcdefABCDEFxX_+- \tg", max_size=8))
def test_channels_of_odd_text(colour):
    same(live_tokens._channels, ref_tokens._channels, colour)


@st.composite
def week_models(draw, rough=False):
    """The same week as the live classes and the reference ones hold it."""
    week_start = draw(
        maybe("2026-09-21", "2026-09-21", "2026-09-23", "2099-12-29") if rough else maybe("2026-09-21")
    )
    slacks = [None, "danger", "tight", "ok"] + (["weird"] if rough else [])
    occurrences = []
    for index in range(draw(st.integers(0, 6))):
        start = draw(st.integers(0, 1380))
        occurrences.append(
            {
                "block_id": f"b{index}",
                "title": draw(maybe("Study", "Class", "")),
                "category": draw(maybe("assignments", "class", "free")),
                "day": draw(DAY),
                "start": start,
                "end": start + draw(st.integers(0, 120)),
                "work": draw(st.booleans()),
                "done": draw(st.booleans()),
                "missed": draw(st.booleans()),
                "assignment_id": draw(maybe(None, "essay")),
                "due": draw(maybe(None, "2026-09-24")),
                "slack": draw(st.sampled_from(slacks)),
                "pinned": draw(st.booleans()),
            }
        )
    waiting = []
    for index in range(draw(st.integers(0, 3))):
        waiting.append(
            {
                "block_id": f"w{index}",
                "title": draw(maybe("Poster", "Essay", "Ünï")),
                "category": "assignments",
                "minutes": draw(st.integers(0, 180)),
                "assignment_id": draw(maybe(None, "poster")),
                "due": draw(
                    maybe(
                        None,
                        "",
                        "2026-09-21",
                        "2026-09-22T17:00",
                        "2026-09-23",
                        "2026-09-24T09:30",
                        "2026-09-27",
                    )
                ),
                "reason": draw(maybe("", "No room")),
            }
        )
    focus = draw(st.integers(0, 90))

    def build(module):
        return module.WeekModel(
            week_start,
            tuple(module.Occurrence(**row) for row in occurrences),
            tuple(module.Waiting(**row) for row in waiting),
            focus,
        )

    return build(live_weekmodel), build(ref_weekmodel)


def same_on(models, name, *args, listed=False):
    live, ref = models
    live_out = produced(getattr(live, name), args, {}, listed)
    ref_out = produced(getattr(ref, name), args, {}, listed)
    assert live_out == ref_out


TODAY = st.one_of(st.none(), DAY)


@CHECK
@given(week_models(), DAY, MINUTE, TODAY)
def test_week_model_methods_on_generated_weeks(models, day, minute, today):
    same_on(models, "on_day", day)
    same_on(models, "load_min", day)
    same_on(models, "open_work")
    same_on(models, "due_today_unplaced", today)
    same_on(models, "leftover_kind", today)
    same_on(models, "leftover_words", today)
    same_on(models, "leftover_parts", today)
    same_on(models, "minutes_left_today", today, minute)
    same_on(models, "day_queue", day, minute)
    same_on(models, "date_of", day)


@WIDE
@given(week_models(), DAY, st.integers(0, 24 * 60), TODAY)
def test_week_model_methods_on_wide_generated_weeks(models, day, minute, today):
    same_on(models, "day_queue", day, minute)
    same_on(models, "minutes_left_today", today, minute)
    same_on(models, "leftover_parts", today)
    same_on(models, "open_work")


@CHECK
@given(
    week_models(rough=True),
    st.integers(-9, 9),
    st.integers(-5, 1500),
    st.one_of(st.none(), st.integers(-9, 9)),
)
def test_week_model_methods_on_rough_weeks_and_days(models, day, minute, today):
    for name, args in (
        ("on_day", (day,)),
        ("load_min", (day,)),
        ("open_work", ()),
        ("due_today_unplaced", (today,)),
        ("leftover_kind", (today,)),
        ("leftover_parts", (today,)),
        ("minutes_left_today", (today, minute)),
        ("day_queue", (day, minute)),
        ("date_of", (day,)),
    ):
        same_on(models, name, *args)


@CHECK
@given(week_models(), DAY)
def test_week_model_hands_back_the_objects_it_holds(models, day):
    live, _ref = models
    assert all(
        item is held
        for item, held in zip(live.on_day(day), [i for i in live.occurrences if i.day == day], strict=True)
    )
    queue = live.day_queue(day, 600)
    assert all(any(item is held for held in live.occurrences) for item in queue.queue)
    assert all(any(item is held for held in live.occurrences) for item in live.open_work())
    assert all(any(item is held for held in live.waiting) for item in live.due_today_unplaced(day))


@CHECK
@given(week_models())
def test_occurrence_properties_on_generated_weeks(models):
    live, ref = models
    for live_item, ref_item in zip(live.occurrences, ref.occurrences, strict=True):
        assert (live_item.minutes, live_item.live, live_item.slack_words) == (
            ref_item.minutes,
            ref_item.live,
            ref_item.slack_words,
        )


def test_the_week_the_engine_holds_follows_a_changed_week():
    held = live_weekmodel.Occurrence("y", "Y", "assignments", 0, 60, 90, True, False, False, None, None, None)
    live = live_weekmodel.WeekModel("2026-09-21", (held,), (), 0)
    assert live.on_day(0) == (held,)
    assert dataclasses.replace(live, occurrences=()).on_day(0) == ()
    listed = live_weekmodel.WeekModel("2026-09-21", [], (), 0)
    first = listed.load_min(0)
    listed.occurrences.append(
        live_weekmodel.Occurrence("x", "X", "assignments", 0, 60, 120, True, False, False, None, None, None)
    )
    assert (first, listed.load_min(0)) == (0, 60)


def test_a_week_model_copies_and_pickles_with_the_engine_week_it_holds():
    import pickle

    held = live_weekmodel.Occurrence("y", "Y", "assignments", 0, 60, 90, True, False, False, None, None, None)
    model = live_weekmodel.WeekModel("2026-09-21", (held,), (), 0)
    model.on_day(0)
    for twin in (copy.copy(model), copy.deepcopy(model), pickle.loads(pickle.dumps(model))):
        assert twin == model
        assert twin.load_min(0) == 30 and twin.on_day(0) == (twin.occurrences[0],)


# Wrong input to every function. The shadow run and the tests above feed the desktop what it sends,
# which is valid; a student's file, a hand-edited look or a stale setting is not. For each top-level
# function of each reference module this makes arguments from realistic values, from odd ones (None,
# empty text, bad dates and times, negative and huge numbers) and from realistic values with one
# field spoiled, and requires the live function to give the same value or raise the same type with
# the same message. A Rust panic arrives as RuntimeError, which the originals never raise.

AUDIT = int(os.environ.get("AUDIT_EXAMPLES", "60"))
AUDITED = settings(
    max_examples=AUDIT,
    deadline=None,
    suppress_health_check=list(HealthCheck),
    database=None,
)
DESK_MODULES = ("calendar", "custom_look", "files", "focus", "history", "pomodoro", "remind", "reuse")
DESK_MODULES += ("tokens", "update", "weekmodel")
DESK_PAIRS = {
    name: (importlib.import_module(f"desktop.native.{name}"), importlib.import_module(f"desk_ref.{name}"))
    for name in DESK_MODULES
}
# Not a function of its arguments alone: the clock setting is global to the module, and the audit
# restores it around each call.
KEEPS_STATE = {"weekmodel.set_clock_24h"}


def audited_functions():
    """Every top-level function of the reference modules that the live module also has."""
    found = []
    for module_name, (live, ref) in DESK_PAIRS.items():
        for name, function in vars(ref).items():
            if inspect.isfunction(function) and function.__module__ == ref.__name__ and hasattr(live, name):
                found.append(f"{module_name}.{name}")
    return found


DATES = [
    "2026-09-21",
    "2026-09-24",
    "2026-09-27",
    "2026-10-04",
    "2000-01-03",
    "2099-12-27",
    "1999-12-27",
    "2099-12-31",
    "2026-W39-4",
    "20260921",
    "2026-9-21",
    "2026-13-01",
    "2026-02-30",
    "",
    " 2026-09-21",
    "2026-09-21T10:00",
    "2026-09-24T21:00",
    "2026-09-24T23:59",
    "2026-09-24T24:00",
    "0001-01-01",
    "9999-12-31",
    "2026-09",
    "2026-13",
    "x",
]
CLOCKS = [
    "08:00",
    "16:00",
    "09:45",
    "9:5",
    "24:00",
    "25:00",
    "08:60",
    "",
    "x",
    "8",
    "10:00:00",
    "-1:30",
    " 8:30",
]
WORDS = [
    "",
    "x",
    "essay",
    "b1",
    "series",
    "block",
    "day",
    "week",
    "work",
    "break",
    "long_break",
    "ended",
    "replace",
    "merge",
    "myday",
    "month",
    "windows",
    "appimage",
    "tarball",
    "é",
    "a" * 90,
    "\n",
    "  ",
]
WHOLE = [0, 1, 2, 3, 6, 7, -1, 15, 30, 45, 60, 90, 95, 96, 120, 1439, 1440, 1441, 10**9, 2**62, -(2**62)]
REALS = [0.0, 0.5, 1.0, 1.2, 0.85, -1.0, 360.0, 1e300, 1e-300]
# What a JSON file can hold in the place of a value: the kinds of things a spoiled field becomes.
ODD = [
    None,
    True,
    False,
    "",
    "x",
    0,
    -1,
    7,
    1.5,
    [],
    {},
    [None],
    {"a": None},
    [[]],
    [1, "a"],
    10**20,
    2**63,
    -(10**20),
]


def sample_block(**extra):
    body = {
        "id": "b1",
        "title": "Soccer",
        "kind": "locked",
        "duration_min": 60,
        "days": [0, 2],
        "start": "16:00",
        "category": "exercise",
    }
    body.update(extra)
    return body


BLOCK_POOL = [
    sample_block(),
    sample_block(
        id="b2", kind="flexible", days=[1], start="10:00", assignment_id="essay", category="assignments"
    ),
    sample_block(id="b3", kind="flexible", days=[0, 1, 2], start=None, assignment_id="essay"),
    sample_block(id="b4", kind="flexible", days=[3], start="09:00", completed=True, completed_day=3),
    sample_block(
        id="b5", days=[4], missed_days=[4], pinned=True, spotify_url="https://open.spotify.com/track/x"
    ),
    sample_block(id="b6", kind="flexible", days=[2], start="23:30", duration_min=90, pomodoro_role="work"),
    sample_block(
        id="b7", kind="flexible", days=[0], start="08:00", earliest="Monday 07:00", latest="Friday 20:00"
    ),
    sample_block(id="b8", start=None, days=[]),
    {},
    {"id": "b9"},
]
ASSIGNMENT_POOL = [
    {"id": "essay", "title": "Essay", "due": "2026-09-24T21:00", "estimate_min": 120, "unplanned_min": 60},
    {"id": "lab", "title": "Lab", "due": "2026-09-22", "estimate_min": 45, "completed": True},
    {"id": "poster", "title": "Poster", "due": None, "estimate_min": 90, "focus_minutes": 30, "priority": 2},
    {"id": "x"},
]
TRACE_POOL = [
    {"placed": [sample_block(id="b2", kind="flexible", start="11:00", days=[1])], "unplaced": [{"id": "b3"}]},
    {"placed": [], "explanations": [{"block_id": "b3", "message": "No room", "slack_status": "tight"}]},
    {"placed": [sample_block(id="b3", kind="flexible", start="09:00", days=[2])], "unplaced": []},
    {},
]
PREF_POOL = [
    {},
    {"timer_work_min": 25, "timer_break_min": 5, "timer_long_break_min": 20, "timer_long_break_every": 3},
    {"timer_work_min": 0},
    {"timer_long_break_every": 99},
    {"auto_split_pomodoro": True, "timer_work_min": 30},
    {"reminder_lead_min": 10},
    {"timer_work_min": "x"},
]
STATE_POOL = [
    {"id": "b1", "phase": "work", "cycles": 1, "running": True, "remainingMs": 600000, "endsAt": 5000},
    {
        "phase": "break",
        "cycles": 0,
        "running": False,
        "remainingMs": 5000,
        "endsAt": None,
        "assignmentId": "essay",
    },
    {"phase": "ended", "cycles": 2},
    {
        "assignmentId": "essay",
        "sessionId": "b2",
        "weekStart": "2026-09-21",
        "day": 1,
        "start": "10:00",
        "phase": "work",
        "cycles": 0,
        "endsAt": 1000,
        "remainingMs": None,
    },
]
ALARM_POOL = [
    {"id": "a", "name": "Wake", "time": "07:30", "enabled": True, "days": [0, 1, 2]},
    {"id": "b", "time": "25:00", "enabled": True, "days": [3]},
    {"id": 3, "time": "5", "enabled": 1, "days": [3]},
]
LOOK_POOL = [
    {"preset": "paper", "knobs": {"font": "mono"}},
    {"preset": "x", "knobs": 5},
    {},
    {"custom": {"base": "slate", "name": "N", "accent": "#aabbcc", "text_scale": 1.1}},
    {"custom": {"base": "x"}},
]
CUSTOM_POOL = [
    {"base": "light", "name": "Night"},
    {"base": "dark", "accent": "#12345a", "colours": {"page": "#101010"}},
    {"base": "slate", "categories": {"class": {"hue": 12}}, "motion": "off", "corners": 8},
    {"name": "x"},
    {"base": 5},
]
RELEASE_POOL = [
    {
        "tag_name": "v0.18.0",
        "assets": [
            {
                "name": "FlexWeek-x86_64.AppImage",
                "browser_download_url": "https://github.com/j0nsh1n/FlexWeek/releases/download/v0.18.0/FlexWeek-x86_64.AppImage",
            }
        ],
        "body": "",
    },
    {"tag_name": "x", "assets": []},
    {"tag_name": "v0.17.2"},
    {"assets": 5},
]
STEP_POOL = [
    {
        "label": "x",
        "weeks": [{"week_start": "2026-09-21", "before": [], "after": [{"id": "a"}]}],
        "assignments": [],
        "stale": False,
    },
    {"label": "", "weeks": [], "assignments": [], "stale": True},
    {},
]
SESSION_POOL = [
    types.SimpleNamespace(
        week_start="2026-09-21",
        selected_day="2026-09-23",
        selected_month="2026-10",
        now_ms=lambda: 1_790_000_000_000,
    ),
    types.SimpleNamespace(week_start="x", now_ms=lambda: 0),
    types.SimpleNamespace(),
]
MOMENTS = [
    datetime(2026, 9, 21, 10, 30),
    datetime(2026, 9, 24, 23, 59, 30),
    datetime(2026, 9, 20, 0, 0),
    datetime(2030, 1, 1),
]
ROW_POOL = [
    {
        "week_start": "2026-09-21",
        "day": 1,
        "fixed": True,
        "block": sample_block(days=[1]),
        "group_id": "g",
        "checked": True,
        "invalid": "",
        "original_duration": 60,
    },
    {
        "week_start": "2026-09-21",
        "day": 1,
        "fixed": False,
        "block": sample_block(kind="flexible", assignment_id="essay"),
        "group_id": "g",
        "checked": False,
        "invalid": "No time",
    },
]
ITEM_POOL = [
    {"block": sample_block(), "source_day": 0, "scope": "series", "group_id": "g"},
    {
        "block": sample_block(id="b2", kind="flexible", assignment_id="essay"),
        "source_day": 1,
        "scope": "block",
        "group_id": "h",
    },
]
ROUTINE_POOL = [
    {"blocks": [{"template_id": "t", "title": "Run", "days": [0, 2], "start": "07:00", "duration_min": 30}]},
    {},
]
PLAN_POOL = [
    {
        "error": None,
        "segments": [
            {"role": "work", "duration_min": 30, "index": 1},
            {"role": "break", "duration_min": 15, "index": 1},
        ],
        "total_min": 45,
    },
    {"error": "x", "segments": [], "total_min": 0},
    {},
]
PROBLEM_POOL = [
    types.SimpleNamespace(
        words="Text on cards",
        ink="#777777",
        ground="#ffffff",
        ratio=4.0,
        field=("colours", "text"),
        fixed="#555555",
    ),
    types.SimpleNamespace(words="x", ink="", ground="", ratio=0.0, field=("accent",), fixed="#abcdef"),
    types.SimpleNamespace(
        words="y", ink="", ground="", ratio=0.0, field=("categories", "class"), fixed="#abcdef"
    ),
]
RESULT_POOL = [
    {"current": None, "next": None},
    {"current": sample_block(), "next": sample_block(id="b2")},
    {"now": None},
    {},
]
PAIR_POOL = [(0, 15), (1, 600), (-1, 0), (5,), (), "x"]
INTERVALS = [[(0, 60)], [(600, 660), (700, 760)], [], [(60, 0)], [(1, 2, 3)]]


def pool_for(name, annotation):
    """Realistic values for a parameter, by what it is called and what it is said to be."""
    table = [
        (
            (
                "blocks",
                "before_blocks",
                "after_blocks",
                "existing",
                "incoming",
                "committed_blocks",
                "sessions",
                "source",
            ),
            [[], [BLOCK_POOL[0]], BLOCK_POOL[:3], BLOCK_POOL[:8], BLOCK_POOL],
        ),
        (("block", "placed_block", "session"), BLOCK_POOL),
        (("homework",), [[], ASSIGNMENT_POOL[:2], ASSIGNMENT_POOL]),
        (
            ("assignments", "before_assignments", "after_assignments", "available"),
            [
                {},
                {a["id"]: a for a in ASSIGNMENT_POOL},
                {"essay": ASSIGNMENT_POOL[0]},
                {"essay": 60, "lab": 0},
            ],
        ),
        (("assignment", "item", "target", "settings"), ASSIGNMENT_POOL + BLOCK_POOL[:2]),
        (("trace",), TRACE_POOL),
        (("prefs",), PREF_POOL),
        (("state",), STATE_POOL),
        (("alarm",), ALARM_POOL),
        (("alarms",), [ALARM_POOL, ALARM_POOL[:1], []]),
        (("look",), LOOK_POOL),
        (("custom",), CUSTOM_POOL),
        (("saved",), [[], [CUSTOM_POOL[0]], CUSTOM_POOL[:2]]),
        (("release",), RELEASE_POOL),
        (("step",), STEP_POOL),
        (("steps", "stack"), [[], STEP_POOL[:1], STEP_POOL]),
        (("row",), ROW_POOL),
        (("rows",), [[], ROW_POOL]),
        (("items",), [[], ITEM_POOL]),
        (("routine",), ROUTINE_POOL),
        (("plan",), PLAN_POOL),
        (("problem",), PROBLEM_POOL),
        (("result",), RESULT_POOL),
        (("placed",), [{"start": "09:00", "days": [1]}, {}]),
        (("day_data",), [None, {}, {"blocks": []}]),
        (("now",), MOMENTS + [None]),
        (("session",), SESSION_POOL),
        (("grounds",), [("#ffffff",), (), ("#000000", "#ffffff")]),
        (("occupied",), INTERVALS),
        (("not_before",), PAIR_POOL + [None]),
        (
            ("only", "targets", "keep", "fired", "played", "changed_ids"),
            [set(), {"b1"}, {"b2", "x"}],
        ),
        (("snoozed",), [{}, {"a": 1_790_000_000_000}]),
        (("saved_weeks",), [[], ["2026-09-14"], ["2026-09-28"]]),
        (("allowed_days",), [[], [0, 1, 2], [1]]),
        (("days", "changed", "extra"), [[0], [0, 2], [], [6, 7]]),
        (("payload",), [b"abc", b"", b"x" * 100]),
        (
            ("raw", "text", "location", "checksum_text"),
            ["", "{}", "[]", "x", json.dumps({"format": "flexweek-week", "version": 2, "blocks": []})],
        ),
    ]
    for names, values in table:
        if name in names:
            return list(values)
    kind = str(annotation)
    if name == "today" and "date" in kind and "str" not in kind:
        return [date(2026, 9, 23), date(2026, 9, 21), date(2026, 9, 27), None]
    if name == "due" and "tuple" in kind:
        return PAIR_POOL + [None]
    if name == "saved":
        return STATE_POOL + [None] if "dict | None" in kind else [[], [CUSTOM_POOL[0]], CUSTOM_POOL[:2]]
    if (
        name in {"week_start", "iso_day", "today_iso", "iso_date", "iso", "selected_month", "month", "due"}
        or "date" in name
    ):
        return DATES
    if name in {"start", "hhmm", "from_start", "target_start"}:
        return CLOCKS
    if "int" in kind and "list" not in kind and "dict" not in kind:
        return WHOLE
    if "float" in kind:
        return REALS + WHOLE[:6]
    if "bool" in kind:
        return [True, False]
    if "str" in kind:
        return WORDS + DATES[:3] + CLOCKS[:3]
    return [None, *WORDS[:4], *WHOLE[:4]]


def spoil(draw, value, depth=0):
    """`value` with one place changed to something of the wrong kind, or one key dropped."""
    if isinstance(value, dict) and value:
        key = draw(st.sampled_from(sorted(value, key=repr)))
        out = dict(value)
        if draw(st.integers(0, 3)) == 0:
            out.pop(key)
        elif depth < 2 and isinstance(value[key], dict | list) and draw(st.booleans()):
            out[key] = spoil(draw, value[key], depth + 1)
        else:
            out[key] = draw(st.sampled_from(ODD + WORDS[:6] + DATES[:4] + CLOCKS[:4] + WHOLE[:8]))
        return out
    if isinstance(value, list) and value:
        at = draw(st.integers(0, len(value) - 1))
        out = list(value)
        if depth < 2 and isinstance(value[at], dict | list) and draw(st.booleans()):
            out[at] = spoil(draw, value[at], depth + 1)
        else:
            out[at] = draw(st.sampled_from(ODD))
        return out
    return draw(st.sampled_from(ODD))


def odd_like(annotation):
    """Values of the kind the parameter is said to take that a caller should not send but might."""
    kind = str(annotation)
    if "object" in kind:
        return ODD + [(), b"x"]
    pieces = []
    if "str" in kind:
        pieces += WORDS + DATES + CLOCKS
    if "int" in kind and "list" not in kind and "dict" not in kind:
        pieces += WHOLE
    if "float" in kind:
        pieces += REALS
    if "bool" in kind:
        pieces += [True, False]
    if "dict" in kind:
        pieces += [{}, {"a": 1}, {"id": None}]
    if "list" in kind or "tuple" in kind:
        pieces += [[], [None], [1, "a"], [{}]]
    if "set" in kind:
        pieces += [set(), {""}]
    return pieces or [None]


@st.composite
def audit_arguments(draw, function):
    args, kwargs = [], {}
    for parameter in inspect.signature(function).parameters.values():
        if parameter.default is not inspect.Parameter.empty and draw(st.integers(0, 3)) == 0:
            continue
        pool = pool_for(parameter.name, parameter.annotation)
        choice = draw(st.integers(0, 9))
        value = draw(st.sampled_from(pool))
        if choice == 9:
            value = draw(st.sampled_from(odd_like(parameter.annotation)))
        elif choice == 8:
            kind = str(parameter.annotation)
            if any(word in kind for word in ("None", "dict", "list", "set", "object", "tuple")):
                value = None
        elif choice >= 6 and isinstance(value, dict | list):
            value = spoil(draw, value)
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            kwargs[parameter.name] = value
        else:
            args.append(value)
    return args, kwargs


def fixed_uuids(owner_modules):
    counter = iter(range(1, 10**9))

    def next_uuid():
        return uuid.UUID(int=next(counter))

    return next_uuid


def audited_call(function, args, kwargs, modules):
    previous = [(module, module.__dict__.get("uuid4")) for module in modules if "uuid4" in vars(module)]
    real = uuid.uuid4
    maker = fixed_uuids(modules)
    uuid.uuid4 = maker
    for module, _ in previous:
        module.uuid4 = maker
    try:
        try:
            value = function(*args, **kwargs)
            if inspect.isgenerator(value):
                value = list(value)
            return "ok", re.sub(r"<object object at 0x[0-9a-f]+>", "<sentinel>", repr(value))
        except Exception as error:  # noqa: BLE001
            return "raise", type(error).__name__, str(error)
    finally:
        uuid.uuid4 = real
        for module, original in previous:
            module.uuid4 = original


# Files a student brings in. Everything below goes through `parse_import_payload` and the two exports
# as text or as data, valid and not: one case for each rule of the two models and of the file's own
# checks, then valid files with places spoiled. Results, errors (type and message) and arguments
# afterwards must equal the original's.

FILE_BLOCK = {
    "id": "b1",
    "title": "Soccer",
    "kind": "locked",
    "duration_min": 60,
    "days": [0, 2],
    "start": "16:00",
    "category": "exercise",
}
FILE_SESSION = {
    "id": "s1",
    "title": "Essay",
    "kind": "flexible",
    "duration_min": 60,
    "days": [1],
    "start": "10:00",
    "category": "assignments",
    "assignment_id": "essay",
}
FILE_HOMEWORK = {"id": "essay", "title": "Essay", "due": "2026-09-24T21:00", "estimate_min": 60}
FILE_WEEK = {
    "format": "flexweek-week",
    "version": 2,
    "week_start": "2026-09-21",
    "blocks": [FILE_BLOCK, FILE_SESSION],
    "assignments": [FILE_HOMEWORK],
}
FILE_DAY = {
    "format": "flexweek-day",
    "version": 2,
    "week_start": "2026-09-21",
    "day": 2,
    "blocks": [{**FILE_BLOCK, "days": [2]}],
    "assignments": [],
}
LONG = "x" * 81
BLOCK_FAULTS = [
    {"id": ""},
    {"id": LONG},
    {"id": 5},
    {"id": None},
    {"title": ""},
    {"title": LONG},
    {"title": None},
    {"kind": "x"},
    {"kind": None},
    {"duration_min": 0},
    {"duration_min": -15},
    {"duration_min": 7141},
    {"duration_min": "60"},
    {"duration_min": 60.5},
    {"duration_min": True},
    {"days": []},
    {"days": "0"},
    {"days": [7]},
    {"days": [-1]},
    {"days": [0, 1, 2, 3, 4, 5, 6, 0]},
    {"days": [1.5]},
    {"days": [None]},
    {"priority": 0},
    {"priority": 6},
    {"energy": "x"},
    {"earliest": "x" * 41},
    {"latest": 5},
    {"start": "16:00:00"},
    {"start": 5},
    {"course": "c" * 41},
    {"category": "c" * 33},
    {"completed": "yes"},
    {"completed": 2},
    {"completed_day": 7},
    {"completed_day": -1},
    {"completed_day": 0},
    {"completed": True, "completed_day": 0},
    {"completed": True, "completed_day": 0, "kind": "flexible", "days": [0], "start": None},
    {"missed_days": [0, 0]},
    {"missed_days": [7]},
    {"missed_days": [1]},
    {"missed_days": [0, 1, 2, 3, 4, 5, 6, 0]},
    {"kind": "flexible", "missed_days": [0]},
    {"spotify_url": "x"},
    {"spotify_url": "http://evil.example/"},
    {"spotify_url": "https://open.spotify.com/track/" + "a" * 500},
    {"spotify_url": 5},
    {"focus_sessions": -1},
    {"focus_sessions": 10000},
    {"focus_minutes": 71401},
    {"focus_minutes": -1},
    {"pomodoro_parent_id": ""},
    {"pomodoro_parent_id": LONG},
    {"pomodoro_role": "x"},
    {"pomodoro_index": 0},
    {"pomodoro_index": 1000},
    {"pinned": True},
    {"pinned": "yes"},
    {"pinned": True, "kind": "flexible", "days": [0, 1], "start": "08:00"},
    {"pinned": True, "kind": "flexible", "start": None},
    {"assignment_id": ""},
    {"assignment_id": LONG},
    {"assignment_id": "essay"},
    {"assignment_id": "essay", "kind": "flexible", "latest": "Friday 20:00"},
    {"assignment_id": "essay", "kind": "flexible", "focus_minutes": 15},
    {"assignment_id": "essay", "kind": "locked", "pomodoro_role": "work"},
    {"assignment_id": "essay", "kind": "locked", "pomodoro_role": "break"},
    {"assignment_id": "essay", "kind": "flexible", "focus_sessions": 1},
    {"unknown": 1},
    {"id": None, "x": 1},
]
HOMEWORK_FAULTS = [
    {"id": ""},
    {"id": LONG},
    {"id": 5},
    {"title": ""},
    {"title": "   "},
    {"title": LONG},
    {"title": None},
    {"course": "c" * 41},
    {"category": "c" * 33},
    {"priority": 0},
    {"priority": 6},
    {"energy": "x"},
    {"spotify_url": "x"},
    {"due": "x"},
    {"due": "2026-09-24T25:00"},
    {"due": "2026-02-30"},
    {"due": "2026-09-24T21:00:00"},
    {"due": None},
    {"estimate_min": 0},
    {"estimate_min": 20},
    {"estimate_min": 1441},
    {"estimate_min": -15},
    {"estimate_min": "60"},
    {"estimate_min": 60.0},
    {"focus_minutes": -1},
    {"focus_minutes": 71401},
    {"focus_sessions": 10000},
    {"completed": True},
    {"completed": True, "completed_at": "2026-09-24T10:00"},
    {"completed_at": "2026-09-24T10:00"},
    {"completed": True, "completed_at": "x"},
    {"notes": "n" * 4001},
    {"notes": 5},
    {"links": "x"},
    {"links": [{"label": "L", "url": "https://example.com", "extra": 1}]},
    {"links": [{"label": " ", "url": "https://example.com"}]},
    {"links": [{"label": "L", "url": "ftp://x"}]},
    {"links": [{"label": "L", "url": "https://e.com"}] * 21},
    {"links": [5]},
    {"checklist": [{"id": "c", "text": "t"}, {"id": "c", "text": "u"}]},
    {"checklist": [{"id": "c", "text": " "}]},
    {"checklist": [{"id": "", "text": "t"}]},
    {"checklist": [{"id": str(n), "text": "t"} for n in range(41)]},
    {"checklist": "x"},
    {"unknown": 1},
    {"revision": 3},
]


def file_text(payload):
    return json.dumps(payload)


def import_matches(text):
    same(live_files.parse_import_payload, ref_files.parse_import_payload, text)


@pytest.mark.parametrize("fault", BLOCK_FAULTS, ids=repr)
def test_a_week_file_with_a_block_the_model_refuses(fault):
    for base in (FILE_BLOCK, FILE_SESSION):
        week = {**FILE_WEEK, "blocks": [{**base, **fault}]}
        import_matches(file_text(week))
        same(
            live_files.exportable_block,
            ref_files.exportable_block,
            {**base, **fault},
            {"essay": FILE_HOMEWORK},
        )
        same(
            live_files.export_week_payload,
            ref_files.export_week_payload,
            "2026-09-21",
            [{**base, **fault}],
            {"essay": FILE_HOMEWORK},
        )
        same(
            live_files.export_day_payload,
            ref_files.export_day_payload,
            "2026-09-21",
            1,
            [{**base, **fault, "days": [1]}],
            {"essay": FILE_HOMEWORK},
        )
    day = {**FILE_DAY, "blocks": [{**FILE_BLOCK, "days": [2], **fault}]}
    import_matches(file_text(day))


@pytest.mark.parametrize("fault", HOMEWORK_FAULTS, ids=repr)
def test_a_week_file_with_homework_the_model_refuses(fault):
    week = {**FILE_WEEK, "assignments": [{**FILE_HOMEWORK, **fault}]}
    import_matches(file_text(week))
    same(live_files.assignment_body, ref_files.assignment_body, {**FILE_HOMEWORK, **fault})
    same(
        live_files.referenced_assignments,
        ref_files.referenced_assignments,
        [FILE_SESSION],
        {"essay": {**FILE_HOMEWORK, **fault}},
    )
    same(
        live_files.export_week_payload,
        ref_files.export_week_payload,
        "2026-09-21",
        [FILE_SESSION],
        {"essay": {**FILE_HOMEWORK, **fault}},
    )


def with_blocks(payload, blocks):
    return {**payload, "blocks": blocks}


WEEK_HEAD = '{"format": "flexweek-week", "version": 2, '
FILE_RULES = [
    "",
    "   ",
    "\n",
    "x",
    "[]",
    "null",
    "5",
    '"x"',
    "{",
    "{}",
    "NaN",
    "[NaN]",
    file_text({**FILE_WEEK, "format": None}),
    file_text({**FILE_WEEK, "format": "other"}),
    file_text({**FILE_WEEK, "format": ["flexweek-week"]}),
    file_text({**FILE_WEEK, "format": {}}),
    file_text({k: v for k, v in FILE_WEEK.items() if k != "format"}),
    *[
        file_text({**FILE_WEEK, "version": v})
        for v in (None, 0, -1, True, False, 1, 3, 1.5, "2", [2], {}, 10**30, -(10**30), 2**63)
    ],
    file_text({k: v for k, v in FILE_WEEK.items() if k != "version"}),
    file_text({**FILE_WEEK, "blocks": None}),
    file_text({**FILE_WEEK, "blocks": {}}),
    file_text({**FILE_WEEK, "blocks": "x"}),
    file_text({k: v for k, v in FILE_WEEK.items() if k != "blocks"}),
    file_text({**FILE_WEEK, "blocks": [5]}),
    file_text({**FILE_WEEK, "blocks": [None]}),
    file_text({**FILE_WEEK, "blocks": [[]]}),
    file_text({**FILE_WEEK, "assignments": None}),
    file_text({**FILE_WEEK, "assignments": {}}),
    file_text({k: v for k, v in FILE_WEEK.items() if k != "assignments"}),
    file_text({**FILE_WEEK, "assignments": [5]}),
    file_text({**FILE_WEEK, "version": 1, "assignments": None}),
    file_text({**FILE_WEEK, "version": 1, "assignments": [5]}),
    *[
        file_text({**FILE_WEEK, "week_start": v})
        for v in (
            None,
            "",
            "2026-09-22",
            "2026-09-21T00:00",
            "x",
            5,
            0,
            [],
            {},
            True,
            1.5,
            "1999-12-27",
            "2100-01-04",
            "2026-W39-1",
            "20260921",
        )
    ],
    file_text({k: v for k, v in FILE_WEEK.items() if k != "week_start"}),
    *[file_text({**FILE_DAY, "day": v}) for v in (None, -1, 7, 0, 6, True, False, 1.0, "2", [2], 10**30)],
    file_text({k: v for k, v in FILE_DAY.items() if k != "day"}),
    file_text(with_blocks(FILE_DAY, [{**FILE_BLOCK, "days": [1]}])),
    file_text(with_blocks(FILE_DAY, [{**FILE_BLOCK, "days": [2, 3]}])),
    file_text(with_blocks(FILE_DAY, [])),
    file_text({**FILE_DAY, "day": True, "blocks": [{**FILE_BLOCK, "days": [1]}]}),
    file_text(with_blocks(FILE_WEEK, [{**FILE_BLOCK, "id": f"b{n}"} for n in range(100)])),
    file_text(with_blocks(FILE_WEEK, [{**FILE_BLOCK, "id": f"b{n}"} for n in range(101)])),
    file_text(with_blocks(FILE_WEEK, [FILE_BLOCK, FILE_BLOCK])),
    file_text(
        with_blocks(
            FILE_WEEK, [FILE_BLOCK, {**FILE_BLOCK, "id": "b2"}, FILE_BLOCK, {**FILE_BLOCK, "id": "b2"}]
        )
    ),
    file_text(
        with_blocks(
            FILE_WEEK,
            [
                {**FILE_BLOCK, "id": "a"},
                {**FILE_BLOCK, "id": "b"},
                {**FILE_BLOCK, "id": "b"},
                {**FILE_BLOCK, "id": "a"},
            ],
        )
    ),
    file_text(with_blocks(FILE_WEEK, [FILE_BLOCK, {**FILE_BLOCK, "id": "c", "pomodoro_parent_id": "b1"}])),
    file_text(with_blocks(FILE_WEEK, [{**FILE_BLOCK, "id": "c", "pomodoro_parent_id": "zzz"}])),
    file_text({**FILE_WEEK, "assignments": [{**FILE_HOMEWORK, "id": f"h{n}"} for n in range(100)]}),
    file_text({**FILE_WEEK, "assignments": [{**FILE_HOMEWORK, "id": f"h{n}"} for n in range(101)]}),
    file_text({**FILE_WEEK, "assignments": [FILE_HOMEWORK, FILE_HOMEWORK]}),
    file_text(
        {
            **FILE_WEEK,
            "assignments": [
                FILE_HOMEWORK,
                {**FILE_HOMEWORK, "id": "two"},
                FILE_HOMEWORK,
                {**FILE_HOMEWORK, "id": "two"},
            ],
        }
    ),
    file_text({**FILE_WEEK, "assignments": []}),
    file_text({**FILE_WEEK, "version": 1, "assignments": []}),
    file_text({**FILE_WEEK, "version": 1}),
    file_text({**FILE_WEEK, "blocks": [FILE_SESSION], "assignments": [{**FILE_HOMEWORK, "id": "other"}]}),
    file_text(FILE_WEEK),
    file_text(FILE_DAY),
    json.dumps(FILE_WEEK, indent=2),
    "﻿" + file_text(FILE_WEEK),
    "  " + file_text(FILE_WEEK) + "\n",
    file_text(FILE_WEEK)[:-3],
    file_text(FILE_WEEK) + " x",
    '{"format": "flexweek-week", "version": 2, "blocks": [], "assignments": [], "x": NaN}',
    '{"format": NaN, "version": 2, "blocks": [], "assignments": []}',
    '{"format": "flexweek-week", "version": NaN, "blocks": [], "assignments": []}',
    '{"format": "flexweek-week", "version": 2, "blocks": NaN, "assignments": []}',
    '{"format": "flexweek-week", "version": 2, "blocks": [], "assignments": [], "week_start": NaN}',
    '{"format": "flexweek-week", "version": 2, "blocks": [], "assignments": [], "week_start": Infinity}',
    '{"format": "flexweek-day", "version": 2, "blocks": [], "assignments": [], "day": NaN}',
    WEEK_HEAD
    + '"blocks": [{"id": "a", "title": "T", "kind": "locked", "duration_min": NaN, "days": [0]}],'
    + ' "assignments": []}',
    WEEK_HEAD
    + '"blocks": [{"id": "a\\ud800", "title": "T", "kind": "locked", "duration_min": 15, "days": [0]}],'
    + ' "assignments": []}',
    '{"format": "flexweek-week", "version": 2, "blocks": [], "assignments": [], "week_start": "\\ud800"}',
    '{"format": "flexweek-week", "version": 99999999999999999999999, "blocks": [], "assignments": []}',
]


@pytest.mark.parametrize("text", FILE_RULES, ids=lambda text: text[:50])
def test_each_rule_of_a_file_the_student_imports(text):
    import_matches(text)
    import_matches(text or None)
    same(live_files.parse_import_payload, ref_files.parse_import_payload, None)


@st.composite
def spoiled_files(draw):
    payload = copy.deepcopy(draw(maybe(FILE_WEEK, FILE_DAY)))
    for _ in range(draw(st.integers(1, 3))):
        payload = spoil(draw, payload)
    return payload


@WIDE
@given(spoiled_files())
def test_imports_of_files_with_places_spoiled(payload):
    if isinstance(payload, dict):
        import_matches(json.dumps(payload))
    import_matches(json.dumps(payload))


@WIDE
@given(
    st.lists(
        st.one_of(st.just(FILE_BLOCK), st.just(FILE_SESSION), st.just({}), maybe(None, 5, "x")), max_size=3
    ),
    maybe(1, 2, 3),
    maybe(0, 2, 7, None, True, "x"),
)
def test_imports_of_files_with_odd_blocks(blocks, version, day):
    payload = {
        "format": "flexweek-day",
        "version": version,
        "week_start": "2026-09-21",
        "day": day,
        "blocks": blocks,
        "assignments": [],
    }
    import_matches(json.dumps(payload))
    import_matches(json.dumps({**payload, "format": "flexweek-week"}))


@WIDE
@given(
    st.lists(st.one_of(st.just(FILE_BLOCK), st.just(FILE_SESSION), maybe(None, 5, "x", [], {})), max_size=3),
    st.one_of(
        st.dictionaries(maybe("essay", "lab", "gone"), st.just(FILE_HOMEWORK), max_size=2),
        maybe(None, [], "x", ["essay"]),
    ),
    st.one_of(DAY, maybe(None, "x", 9)),
)
def test_exports_of_odd_weeks(blocks, assignments, day):
    same(live_files.export_week_payload, ref_files.export_week_payload, "2026-09-21", blocks, assignments)
    same(live_files.export_day_payload, ref_files.export_day_payload, "2026-09-21", day, blocks, assignments)
