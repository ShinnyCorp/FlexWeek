"""What crosses to the engine as JSON, and back (0.18.5: the fast path for plain values).

NaN, infinity and lone surrogates cannot be JSON text the engine reads, so `plain` writes them in a
form `restore` turns back. Values with none of them skip the walk; these tests hold both paths to the
same answers.
"""

from __future__ import annotations

import json
import math

import pytest

from desktop.native import wire


def marked(word: str) -> str:
    """The one-key dict for a non-finite float, as it reads in JSON text."""
    return '{"\\u0000float": "' + word + '"}'


def test_a_plain_value_is_written_without_the_walk(monkeypatch: pytest.MonkeyPatch) -> None:
    """The requirement is the shortcut itself: nothing in a value without NaN, infinity or a lone
    surrogate needs to be changed, so nothing is visited."""

    def walked(_value: object) -> object:
        raise AssertionError("the walk ran for a plain value")

    monkeypatch.setattr(wire, "_clean", walked)
    value = {"title": "Maths", "days": [1, 3], "ratio": 0.5, "none": None, "nested": {"ok": True}, "é": "ü"}
    assert json.loads(wire.plain(value)) == value


def test_a_plain_value_is_written_as_json_dumps_wrote_it() -> None:
    value = {"b": [1, 2.5, "x"], "a": None, "t": (1, 2)}
    assert wire.plain(value) == '{"b": [1, 2.5, "x"], "a": null, "t": [1, 2]}'


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (float("nan"), marked("nan")),
        (float("inf"), marked("inf")),
        (float("-inf"), marked("-inf")),
        ([1.5, float("nan")], "[1.5, " + marked("nan") + "]"),
        ({"x": {"y": float("inf")}}, '{"x": {"y": ' + marked("inf") + "}}"),
    ],
)
def test_a_non_finite_float_is_written_as_the_one_key_dict(value: object, text: str) -> None:
    assert wire.plain(value) == text


@pytest.mark.parametrize("lone", ["\ud800", "\udbff", "\udc00", "\udfff"])
def test_a_lone_surrogate_is_written_as_a_private_use_character(lone: str) -> None:
    mapped = chr(0x10F800 + ord(lone) - 0xD800)
    assert json.loads(wire.plain({"t": f"a{lone}b"})) == {"t": f"a{mapped}b"}
    assert json.loads(wire.plain({f"k{lone}": 1})) == {f"k{mapped}": 1}


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        "\ud800",
        "x\udc00y",
        {"k\ud800": ["\udfff", float("nan")]},
        [{"a": float("-inf")}, "plain", 3, None, True],
        {"title": "Maths", "ratio": 0.5},
        "😀 and ü",
    ],
)
def test_a_value_comes_back_as_it_went_through_either_path(value: object) -> None:
    back = wire.restored(wire.plain(value))
    assert repr(back) == repr(value)


def test_an_answer_with_nothing_to_turn_back_is_not_walked(monkeypatch: pytest.MonkeyPatch) -> None:
    def walked(_value: object) -> object:
        raise AssertionError("the walk ran for a plain answer")

    monkeypatch.setattr(wire, "restore", walked)
    assert wire.restored('{"a": [1, 2.5, "x", null], "b": "ü 😀"}') == {"a": [1, 2.5, "x", None], "b": "ü 😀"}


@pytest.mark.parametrize(
    "text",
    [
        '{"x": {"\\u0000float": "nan"}}',
        '{"x": "a\U0010f800b"}',
        '{"x": "a\\udbfe\\udc00b"}',
    ],
)
def test_an_answer_with_something_to_turn_back_is_walked(text: str) -> None:
    assert repr(wire.restored(text)) == repr(wire.restore(json.loads(text)))


def test_an_answer_with_the_non_finite_marker_gives_the_float_back() -> None:
    back = wire.restored('{"v": {"\\u0000float": "nan"}, "w": {"\\u0000float": "-inf"}}')
    assert math.isnan(back["v"])
    assert back["w"] == float("-inf")


def test_an_answer_with_a_private_use_character_gives_the_surrogate_back() -> None:
    assert wire.restored('{"t": "a\U0010f800b"}') == {"t": "a\ud800b"}
