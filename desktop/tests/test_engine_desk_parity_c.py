"""Part C of the desk comparisons: `custom_look` (what E6 moved into the engine) and the four look
rules `look.py` hands to it, each against the Python at 6e86802 in `desk_ref`.

The helpers are `test_engine_desk_parity`'s, used as attributes of that module so pytest does not collect
its tests a second time here.
"""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]
import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

import desk_ref.custom_look as ref_look
import desk_ref.look as ref_rules
import desktop.native.custom_look as live_look
import desktop.native.look as live_rules
import desktop.tests.test_engine_desk_parity as base

NONFINITE = ["NaN", "Infinity", "-Infinity"]
LOOK_HEAD = '{"kind": "FlexWeek look", "version": 1, "base": "poster"'


@base.CHECK
@given(
    st.sampled_from(
        [
            "name",
            "accent",
            "colours",
            "categories",
            "corners",
            "text_scale",
            "edge_width",
            "show_times",
            "extra",
        ]
    ),
    st.sampled_from(NONFINITE),
    st.sampled_from(["{}", "[{}]", '{"a": {}}', '{"class": {"hue": {}}}', '{"text": {}, "page": {}}']),
)
def test_import_look_reads_a_non_finite_number_wherever_it_is_nested(key, number, shape):
    nested = shape.replace("{}", number)
    for body in (
        LOOK_HEAD + ', "' + key + '": ' + number + "}",
        LOOK_HEAD + ', "' + key + '": ' + nested + "}",
        LOOK_HEAD + ', "' + key + '": [' + number + ", " + nested + "]}",
    ):
        base.same(live_look.import_look, ref_look.import_look, body)
        base.same(live_look.import_look, ref_look.import_look, body.encode())


@base.CHECK
@given(st.sampled_from(NONFINITE), st.sampled_from(["version", "kind", "base"]))
def test_import_look_reads_a_non_finite_number_in_the_head(number, key):
    heads = {
        "version": '{"kind": "FlexWeek look", "version": NUM, "base": "light"}',
        "kind": '{"kind": NUM, "version": 1, "base": "light"}',
        "base": '{"kind": "FlexWeek look", "version": 1, "base": NUM}',
    }
    text = heads[key].replace("NUM", number)
    base.same(live_look.import_look, ref_look.import_look, text)


@base.CHECK
@given(st.sampled_from(NONFINITE), st.sampled_from(["[NUM]", '{"base": NUM}', '{"a": [NUM]}', "NUM"]))
def test_import_look_reads_a_non_finite_number_as_the_whole_file(number, shape):
    text = shape.replace("NUM", number)
    base.same(live_look.import_look, ref_look.import_look, text)


@base.CHECK
@given(base.raw_look(), st.booleans())
def test_readability_on_generated_looks(raw, system_dark):
    custom, _problems = ref_rules.sanitize_custom(raw)
    assume(custom is not None)
    base.same(live_look.readability, ref_look.readability, custom, system_dark)


@base.CHECK
@given(
    st.sampled_from(["edge", "filled", "outline"]),
    st.sampled_from(["light", "dark", "system", "high-contrast", "paper", "terminal", "poster", "pastel"]),
    base.maybe(None, "#3d6fc4", "#f4f4f4", "#101010"),
    st.booleans(),
)
def test_readability_for_each_way_blocks_are_drawn(blocks, look, accent, system_dark):
    custom = {"base": look, "name": "My look", "blocks": blocks}
    if accent is not None:
        custom["accent"] = accent
    base.same(live_look.readability, ref_look.readability, custom, system_dark)


def test_readability_checks_only_blocks_drawn_in_their_own_fill():
    palette = {name: "#ffffff" for name in ("window", "panel", "grid", "accent_ink")} | {
        name: "#000000" for name in ("text", "muted", "accent")
    }
    painted = [
        {"key": "class", "fill": "#ffffff", "drawn_fill": "#ffffff", "ink": "#ffffff"},
        {"key": "assignments", "fill": "#ffffff", "drawn_fill": "#000000", "ink": "#ffffff"},
        {"key": "nowhere", "fill": "#ffffff", "drawn_fill": "#ffffff", "ink": "#ffffff"},
    ]
    found = json.loads(
        flexweek_engine.look_readability(
            json.dumps({"base": "system"}), json.dumps(palette), json.dumps(painted)
        )
    )
    # Black on white reads, and so does every pair but white words on a white School block.
    assert [(item["words"], item["field"], item["ratio"]) for item in found] == [
        ("Text on School blocks", ["categories", "class"], 1.0)
    ]


JUNK = base.maybe(None, 5, "x", [], [1], {}, {"base": 5}, 1.5, True, float("nan"), float("inf"))
PACKS_AND_MORE = base.maybe(*base.PACKS_AND_JUNK, ["system"], {"a": 1}, True, 1.5, float("nan"), "Light")


@base.CHECK
@given(base.raw_look())
def test_sanitize_custom_on_generated_looks(raw):
    base.same(live_rules.sanitize_custom, ref_rules.sanitize_custom, raw)


@base.CHECK
@given(JUNK)
def test_sanitize_custom_on_something_that_is_not_a_look(raw):
    base.same(live_rules.sanitize_custom, ref_rules.sanitize_custom, raw)


@base.CHECK
@given(
    base.raw_look(),
    st.sampled_from(
        ["name", "accent", "colours", "categories", "corners", "text_scale", "edge_width", "motion"]
    ),
    st.sampled_from([float("nan"), float("inf"), float("-inf")]),
)
def test_sanitize_custom_on_a_non_finite_number(raw, key, number):
    base.same(live_rules.sanitize_custom, ref_rules.sanitize_custom, {**raw, key: number})
    base.same(live_rules.sanitize_custom, ref_rules.sanitize_custom, {**raw, key: [number]})
    base.same(live_rules.sanitize_custom, ref_rules.sanitize_custom, {**raw, key: {"hue": number}})
    base.same(live_rules.sanitize_custom, ref_rules.sanitize_custom, {**raw, "base": number})


@base.CHECK
@given(base.raw_look(), st.sampled_from(["\ud800", "a\udfffb", "\ud83d\ude00"]))
def test_sanitize_custom_on_a_lone_surrogate(raw, text):
    for body in ({**raw, "name": text}, {**raw, text: 1}, {**raw, "base": text}):
        base.same(live_rules.sanitize_custom, ref_rules.sanitize_custom, body)


@base.CHECK
@given(base.device_looks())
def test_sanitize_look_and_effective_look_on_generated_looks(look):
    base.same(live_rules.sanitize_look, ref_rules.sanitize_look, look)
    base.same(live_rules.effective_look, ref_rules.effective_look, look)


@base.CHECK
@given(JUNK)
def test_sanitize_look_and_effective_look_on_something_that_is_not_a_look(look):
    base.same(live_rules.sanitize_look, ref_rules.sanitize_look, look)
    base.same(live_rules.effective_look, ref_rules.effective_look, look)


@base.CHECK
@given(base.raw_look(), base.maybe("default", "paper", "poster", "terminal", None, 5))
def test_effective_look_of_a_custom_look_worn_on_a_device_look(custom, preset):
    look = {"preset": preset, "knobs": {"text": "small", "font": "mono"}, "custom": custom}
    base.same(live_rules.effective_look, ref_rules.effective_look, look)
    base.same(live_rules.sanitize_look, ref_rules.sanitize_look, look)


@pytest.mark.parametrize("corners", range(0, 17))
def test_effective_look_names_the_nearest_corners_on_every_base(corners):
    for name in live_rules.LOOK_BASES:
        for preset in ("default", "paper"):
            look = {"preset": preset, "custom": {"base": name, "corners": corners}}
            base.same(live_rules.effective_look, ref_rules.effective_look, look)


@pytest.mark.parametrize("hundredths", range(90, 131))
def test_effective_look_names_the_nearest_text_size_on_every_base(hundredths):
    for name in live_rules.LOOK_BASES:
        look = {"custom": {"base": name, "text_scale": hundredths / 100}}
        base.same(live_rules.effective_look, ref_rules.effective_look, look)


@pytest.mark.parametrize("body", [None, "sans", "serif", "mono"])
@pytest.mark.parametrize("heading", [None, "sans", "serif", "mono"])
def test_effective_look_reads_the_font_from_the_two_faces(body, heading):
    for name in live_rules.LOOK_BASES:
        for preset in ("default", "paper"):
            custom = {"base": name}
            if body is not None:
                custom["body_font"] = body
            if heading is not None:
                custom["heading_font"] = heading
            base.same(
                live_rules.effective_look, ref_rules.effective_look, {"preset": preset, "custom": custom}
            )


@base.CHECK
@given(PACKS_AND_MORE)
def test_known_pack(pack):
    base.same(live_rules.known_pack, ref_rules.known_pack, pack)


class SomeText(str):
    pass


def test_known_pack_on_a_subclass_of_text_and_on_a_lone_surrogate():
    for pack in (SomeText("slate"), SomeText("x"), "\ud800", b"slate", ("slate",)):
        base.same(live_rules.known_pack, ref_rules.known_pack, pack)


@base.CHECK
@given(base.device_looks())
def test_the_looks_that_read_the_four_rules_still_agree(look):
    # What look.py draws from its own parts, held to the frozen rules: a measure, a motion level and
    # a copy of the look all read `sanitize_look` and `effective_look` underneath.
    base.same(live_rules.look_measures, _frozen(live_rules.look_measures), look)
    base.same(live_rules.look_motion, _frozen(live_rules.look_motion), look)
    base.same(live_rules.copy_look, _frozen(live_rules.copy_look), look)


def _frozen(func):
    """`func` run with look.py's four rules swapped for the frozen ones, so the result is what it was
    before they called the engine."""

    def run(*args):
        names = ("sanitize_custom", "sanitize_look", "effective_look", "known_pack")
        held = {name: getattr(live_rules, name) for name in names}
        try:
            for name in names:
                setattr(live_rules, name, getattr(ref_rules, name))
            return func(*args)
        finally:
            for name, value in held.items():
                setattr(live_rules, name, value)

    return run
