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
