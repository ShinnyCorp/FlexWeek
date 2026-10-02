"""Part C of the desk comparisons: `custom_look` (what E6 moved into the engine) and the four look
rules `look.py` hands to it, each against the Python at 6e86802 in `desk_ref`.

The helpers are `test_engine_desk_parity`'s, used as attributes of that module so pytest does not collect
its tests a second time here.
"""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]
from hypothesis import assume, given
from hypothesis import strategies as st

import desk_ref.custom_look as ref_look
import desk_ref.look as ref_rules
import desktop.native.custom_look as live_look
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
