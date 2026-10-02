"""Part B of the E6 desktop comparison: focus, pomodoro and files against `desk_ref`.

Same rules as `test_engine_desk_parity.py`, whose helpers it uses: each live function and its reference
get their own deep copy of the arguments and must give the same result (by `repr`), the same raised
error (type and message) and the same arguments afterwards. These cases cover what the wrappers used
to decide in Python around the engine and the engine now decides: which blocks a day export takes,
which error comes first when several things are wrong, and what the model is handed from an import.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

import desk_ref.files as ref_files
import desk_ref.focus as ref_focus
import desktop.native.files as live_files
import desktop.native.focus as live_focus
import desktop.tests.test_engine_desk_parity as base

CHECK = base.CHECK
WIDE = base.WIDE
same = base.same
maybe = base.maybe

WEEK_START = "2026-09-21"
HOMEWORK = {"essay": base.FILE_HOMEWORK}
# What a block can be in a list the wrapper is handed: whole, one the model refuses, one that is not
# a block at all. A refused block after a good one, and a broken one after a refused one, are the
# orders in which two things are wrong at once.
BLOCKS = st.one_of(
    st.just(base.FILE_BLOCK),
    st.just(base.FILE_SESSION),
    st.just({**base.FILE_BLOCK, "id": ""}),
    st.just({**base.FILE_SESSION, "days": [1, 1, 9]}),
    st.just({**base.FILE_BLOCK, "missed_days": [0, 2]}),
    st.just({**base.FILE_SESSION, "assignment_id": "gone"}),
    maybe(None, 5, "x", [], {}),
)
ASSIGNMENTS = st.one_of(
    st.dictionaries(maybe("essay", "lab", "gone"), maybe(base.FILE_HOMEWORK, {}, 5, None), max_size=2),
    maybe(None, [], "x", ["essay"], {"essay": {**base.FILE_HOMEWORK, "title": ""}}),
)
DAYS = st.one_of(base.DAY, maybe(None, "x", 9, -1, 1.5, True, [1]))
WEEKS = maybe(WEEK_START, "x", None, 5, "2026-09-22T00:00", "", "2026-W39-1")


@WIDE
@given(st.lists(BLOCKS, max_size=4), ASSIGNMENTS, WEEKS)
def test_week_exports_when_more_than_one_thing_is_wrong(blocks, assignments, week_start):
    same(live_files.export_week_payload, ref_files.export_week_payload, week_start, blocks, assignments)


@WIDE
@given(st.lists(BLOCKS, max_size=4), ASSIGNMENTS, WEEKS, DAYS)
def test_day_exports_when_more_than_one_thing_is_wrong(blocks, assignments, week_start, day):
    same(live_files.export_day_payload, ref_files.export_day_payload, week_start, day, blocks, assignments)


@pytest.mark.parametrize("day", range(7))
def test_a_day_export_takes_the_blocks_that_fall_on_that_day(day):
    blocks = [
        base.FILE_BLOCK,
        base.FILE_SESSION,
        {**base.FILE_BLOCK, "id": "b3", "days": [day, 6], "missed_days": [day, 6]},
    ]
    same(live_files.export_day_payload, ref_files.export_day_payload, WEEK_START, day, blocks, HOMEWORK)
    same(live_files.export_week_payload, ref_files.export_week_payload, WEEK_START, blocks, HOMEWORK)


def test_a_failure_in_the_blocks_after_a_refusal_by_the_model_gives_the_models_error():
    refused = {**base.FILE_BLOCK, "id": ""}
    for blocks in ([refused, 5], [refused, None], [5, refused], [base.FILE_BLOCK, 5, refused]):
        same(live_files.export_week_payload, ref_files.export_week_payload, WEEK_START, blocks, HOMEWORK)
        same(live_files.export_day_payload, ref_files.export_day_payload, WEEK_START, 0, blocks, HOMEWORK)


@pytest.mark.parametrize("fault", base.HOMEWORK_FAULTS, ids=repr)
def test_a_day_export_with_a_bad_week_and_homework_the_model_refuses(fault):
    assignments = {"essay": {**base.FILE_HOMEWORK, **fault}}
    for week_start in (WEEK_START, "x", None):
        same(
            live_files.export_day_payload,
            ref_files.export_day_payload,
            week_start,
            1,
            [base.FILE_SESSION],
            assignments,
        )


def import_text(payload):
    return json.dumps(payload)


@pytest.mark.parametrize(
    "text",
    [
        '{"format": "flexweek-week", "version": 2, "blocks": [{"id": "a", "title": "T", "kind": "locked",'
        ' "duration_min": NaN, "days": [0]}], "assignments": []}',
        '{"format": "flexweek-week", "version": 2, "blocks": [], "assignments": [{"id": "h", "title": "T",'
        ' "due": "2026-09-24", "estimate_min": Infinity}]}',
        '{"format": "flexweek-week", "version": 2, "blocks": [{"id": "a", "title": "\\ud800", "kind":'
        ' "locked", "duration_min": 15, "days": [0], "start": "09:00"}], "assignments": []}',
        '{"format": "flexweek-week", "version": 2, "blocks": [], "assignments": [{"id": "h\\udfff",'
        ' "title": "T", "due": "2026-09-24", "estimate_min": 30}]}',
        '{"format": "flexweek-week", "version": 2, "blocks": [{"id": "", "title": "T", "kind": "locked",'
        ' "duration_min": 15, "days": [0]}], "assignments": [{"id": "", "title": "T"}]}',
    ],
    ids=["nan-block", "inf-homework", "surrogate-block", "surrogate-homework", "block-before-homework"],
)
def test_what_python_reads_that_the_engine_cannot_is_handed_to_the_models_as_read(text):
    base.import_matches(text)


@WIDE
@given(
    st.lists(
        st.one_of(
            st.just(base.FILE_BLOCK),
            st.just(base.FILE_SESSION),
            st.just({**base.FILE_BLOCK, "id": "z", "title": ""}),
            maybe(None, 5, "x", [], {}),
        ),
        max_size=3,
    ),
    st.lists(
        st.one_of(st.just(base.FILE_HOMEWORK), st.just({**base.FILE_HOMEWORK, "id": ""}), maybe(None, 5, {})),
        max_size=3,
    ),
    maybe(1, 2, 3),
    maybe("flexweek-week", "flexweek-day"),
)
def test_imports_where_blocks_and_homework_are_both_odd(blocks, homework, version, kind):
    payload = {
        "format": kind,
        "version": version,
        "week_start": WEEK_START,
        "day": 1,
        "blocks": blocks,
        "assignments": homework,
    }
    base.import_matches(import_text(payload))


@CHECK
@given(st.integers(min_value=-(10**6), max_value=10**6))
def test_more_time_choices_on_generated_estimates(estimate):
    same(live_focus.more_time_choices, ref_focus.more_time_choices, estimate)


@CHECK
@given(maybe(0, 1, 15, 30, 240, 241, 10**9, -1, True, False))
def test_more_time_choices_on_the_edges(estimate):
    same(live_focus.more_time_choices, ref_focus.more_time_choices, estimate)
