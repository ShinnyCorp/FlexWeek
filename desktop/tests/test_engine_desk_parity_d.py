"""Part D of the desk comparisons: the minor review repairs against frozen Python."""

from __future__ import annotations

import json

import flexweek_engine
import pytest

import desk_ref.calendar as ref_calendar
import desk_ref.custom_look as ref_custom
import desk_ref.focus as ref_focus
import desk_ref.history as ref_history
import desk_ref.look as ref_look
import desk_ref.tokens as ref_tokens
import desk_ref.update as ref_update
import desk_ref.weekmodel as ref_week
import desktop.native.calendar as live_calendar
import desktop.native.custom_look as live_custom
import desktop.native.focus as live_focus
import desktop.native.history as live_history
import desktop.native.look as live_look
import desktop.native.tokens as live_tokens
import desktop.native.update as live_update
import desktop.native.weekmodel as live_week
import desktop.tests.test_engine_desk_parity as base


@pytest.mark.parametrize("assignments", [{}, {"a1": None}])
def test_restore_state_treats_a_null_assignment_as_missing(assignments):
    saved = {"phase": "work", "weekStart": "2026-09-28", "cycles": 0,
             "endsAt": 10000, "assignmentId": "a1"}
    assert ref_focus.restore_state(saved, assignments=assignments, blocks=[], now_ms=5000) is None
    base.same(live_focus.restore_state, ref_focus.restore_state, saved,
              assignments=assignments, blocks=[], now_ms=5000)


def test_deleting_a_whole_block_does_not_read_its_days():
    blocks = [{"id": "x", "title": "t"}, {"id": "y"}]
    assert ref_calendar.delete_occurrence(blocks, "x", None) == [{"id": "y"}]
    base.same(live_calendar.delete_occurrence, ref_calendar.delete_occurrence, blocks, "x", None)


@pytest.mark.parametrize("hue", [-0.0, -360.0, 0.0, 360.0])
def test_category_hue_serializes_zero_without_a_sign(hue):
    raw = {"base": "light", "categories": {"class": {"hue": hue}}}
    expected = ref_look.sanitize_custom(raw)
    assert expected[0]["categories"]["class"]["hue"] == 0.0
    assert json.dumps(live_look.sanitize_custom(raw)) == json.dumps(expected)


@pytest.mark.parametrize("grounds, expected", [(('#ffffff',), '#000000'), ((), '#777777')])
def test_nan_contrast_floor_keeps_pythons_comparison(grounds, expected):
    floor = float("nan")
    assert ref_tokens.fit_lightness("#777777", grounds, floor) == expected
    base.same(live_tokens.fit_lightness, ref_tokens.fit_lightness, "#777777", grounds, floor)


def test_week_methods_accept_whole_float_fields():
    def observed(module):
        row = module.Occurrence("b", "Math", "assignments", 1.0, 540.0, 600.0,
                                True, False, False, "a1", None, None)
        waiting = module.Waiting("w", "English", "assignments", 30.0, "a2", "2026-09-29", "")
        model = module.WeekModel("2026-09-28", (row,), (waiting,))
        assert model.on_day(1)[0] is row
        assert model.load_min(1) == 60
        assert model.minutes_left_today(1, 540) == 90

    base.same(lambda: observed(live_week), lambda: observed(ref_week))


@pytest.mark.parametrize("method", ["on_day", "load_min", "open_work"])
def test_unhashable_week_models_use_the_engine_without_caching(method):
    blocks = [{"id": "b1", "title": "HW", "kind": "flexible", "assignment_id": "a1",
               "start": "16:00", "duration_min": 60, "days": [0]}]
    assignments = {"a1": {"due": ["2026-10-05"]}}

    def observed(module):
        model = module.build_week("2026-09-28", blocks, assignments, None)
        if method == "load_min":
            return model.load_min(0)
        rows = model.on_day(0) if method == "on_day" else model.open_work()
        assert rows[0] is model.occurrences[0]
        return [row.block_id for row in rows]

    assert observed(ref_week) == (60 if method == "load_min" else ["b1"])
    base.same(lambda: observed(live_week), lambda: observed(ref_week))


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e",
                                      "\x85", "\u2028", "\u2029"])
@pytest.mark.parametrize("digest", ["a" * 64, "É" * 64])
def test_checksum_files_use_python_line_breaks_and_character_lengths(separator, digest):
    text = f"junk{separator}{digest}  *app"
    assert ref_update.expected_digest(text, "app") == digest.lower()
    base.same(live_update.expected_digest, ref_update.expected_digest, text, "app")


def test_checksum_fields_accept_python_separator_whitespace():
    text = "a" * 64 + "\x1f*app"
    assert ref_update.expected_digest(text, "app") == "a" * 64
    base.same(live_update.expected_digest, ref_update.expected_digest, text, "app")


@pytest.mark.parametrize("length", [49, 50, 51])
def test_history_push_preserves_identity_and_removes_only_one_oldest_step(length):
    def observed(module):
        stack = [{"label": str(at)} for at in range(length)]
        held = tuple(stack)
        step = {"label": "new", "not_json": object()}
        module.push_step(stack, step)
        first = 0 if length < 50 else 1
        assert all(row is held[at] for at, row in enumerate(stack[:-1], first))
        assert stack[-1] is step
        assert len(stack) == length + (length < 50)
        return [row["label"] for row in stack]

    base.same(lambda: observed(live_history), lambda: observed(ref_history))


@pytest.mark.parametrize("malformed", [False, True])
def test_history_stale_marking_preserves_identity_and_partial_updates(malformed):
    def observed(module):
        steps = [{"weeks": [{"week_start": "w"}], "stale": False},
                 {"weeks": [{}] if malformed else [{"week_start": "other"}], "stale": False},
                 {"weeks": [{"week_start": "w"}], "stale": False}]
        held = tuple(steps)
        outcome = base.produced(module.mark_stale, (steps, "w"), {})
        assert all(row is held[at] for at, row in enumerate(steps))
        assert steps[0]["stale"] is True
        assert steps[1]["stale"] is False
        assert steps[2]["stale"] is (not malformed)
        return outcome, steps

    base.same(lambda: observed(live_history), lambda: observed(ref_history))


def test_empty_history_does_not_encode_an_unused_week():
    def observed(module):
        return module.mark_stale(iter(()), object())

    base.same(lambda: observed(live_history), lambda: observed(ref_history))


@pytest.mark.parametrize("raw", [None, True, {}, (), set(), object(), [],
                                 [{"base": "light", "name": "Study"}],
                                 '[{"base":"light","name":"Study"}]'])
def test_raw_look_saved_binding_and_adapter_match_the_original(raw):
    base.same(lambda: json.loads(flexweek_engine.look_saved(raw)),
              lambda: ref_custom.sanitize_saved(raw))
    base.same(lambda: live_custom.sanitize_saved(raw), lambda: ref_custom.sanitize_saved(raw))


@pytest.mark.parametrize("name", [None, True, 8, [], b"Study", object()])
@pytest.mark.parametrize("operation", ["name", "save", "free", "rename"])
def test_raw_look_name_bindings_use_the_engine_name_error(name, operation):
    calls = {
        "name": (flexweek_engine.look_name, (name,)),
        "save": (flexweek_engine.look_save, ("[]", '{"base":"light"}', name)),
        "free": (flexweek_engine.free_name, ("[]", name)),
        "rename": (flexweek_engine.rename_look,
                   ('[{"base":"light","name":"Kept"}]', "Kept", name)),
    }
    function, args = calls[operation]
    assert base.produced(function, args, {}) == ("raise", "LookNameProblem", "A look needs a name.")


@pytest.mark.parametrize("name", ["  Study  ", "", None, True, 8, [], b"Study", object()])
@pytest.mark.parametrize("operation", ["name", "save", "free", "rename"])
def test_raw_look_name_adapters_preserve_results_and_errors(name, operation):
    def observed(module):
        calls = {
            "name": (module._name, (name,)),
            "save": (module.save_look, ([], {"base": "light"}, name)),
            "free": (module.free_name, ([], name)),
            "rename": (module.rename_look, ([{"base": "light", "name": "Kept"}], "Kept", name)),
        }
        function, args = calls[operation]
        return base.produced(function, args, {})

    base.same(lambda: observed(live_custom), lambda: observed(ref_custom))
