"""Each desk module against the Python reference in `desk_ref` (the modules at 6e86802).

Results are compared by `repr`, so dict key order, list against tuple and int against float count as
differences, as they do for a caller. The first tests cover functions the other desktop tests never
call; the rest pin each difference the shadow run found once it was fixed.
"""

from __future__ import annotations

import contextlib
import copy
import json
import os
import time
import types
from datetime import datetime

from hypothesis import given, settings
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
