"""What every main view owes the student, whichever design and whichever options: by itself it can add
homework, run the plan, reach the day screen, show everything that has no time yet, open any block on
screen, and reach every day of the week. The mock-up measured this; the native client tests it.
"""

from __future__ import annotations

import importlib.util
import itertools
import os
from collections.abc import Iterator

import pytest

from desktop.tests.test_weekmodel import BLOCKS, HOMEWORK, TRACE, WEEK, block

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication, QPushButton

    from desktop.native.layouts.base import LayoutView, Scene
    from desktop.native.layouts.registry import LAYOUTS, tokens_for
    from desktop.native.layouts.views import VIEW_CLASSES
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import build_week, minute_of

    MAIN_VIEWS = [layout_id for layout_id in VIEW_CLASSES if LAYOUTS[layout_id].role == "plan"]
else:
    MAIN_VIEWS = []

WAITING = [
    *BLOCKS,
    block("second-wait", "flexible", [], None, 45, assignment_id="essay", title="Second wait"),
]


def every_choice(layout_id: str) -> list[dict[str, str]]:
    options = LAYOUTS[layout_id].options
    return [
        dict(zip([option.key for option in options], values, strict=True))
        for values in itertools.product(*[option.values for option in options])
    ]


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-main-views-test"])
    yield application


def shown(layout_id: str, options: dict[str, str], today: int | None = 3) -> LayoutView:
    palette = resolved_palette("light-frost", False, None, "default")
    week = build_week(WEEK, WAITING, HOMEWORK, TRACE)
    view = VIEW_CLASSES[layout_id]()
    view.resize(1366, 700)
    tokens = tokens_for(layout_id, options["colour"], palette)
    view.show_week(Scene(week, today, minute_of("13:40"), options, tokens))
    return view


def names(view: LayoutView) -> set[str]:
    return {item.objectName() for item in view.findChildren(QPushButton)}


def blocks_offered(view: LayoutView) -> set[str]:
    return {item.property("block_id") for item in view.findChildren(QPushButton)} - {None}


@pytest.mark.parametrize("layout_id", MAIN_VIEWS)
def test_a_main_view_can_plan_by_itself_whatever_its_options(qapp: QApplication, layout_id: str) -> None:
    for options in every_choice(layout_id):
        view = shown(layout_id, options)
        found = names(view)
        for need in ("Add",):
            assert any(name.endswith(need) or need + "Small" in name for name in found), (options, need)
        assert {"poster-1", "second-wait"} <= blocks_offered(view), options


@pytest.mark.parametrize("layout_id", MAIN_VIEWS)
def test_a_main_view_reaches_every_day_of_the_week(qapp: QApplication, layout_id: str) -> None:
    for options in every_choice(layout_id):
        view = shown(layout_id, options)
        everything = {"school", "dinner", "essay-1", "chem-1", "math-1"}
        days = {item.property("day_target") for item in view.findChildren(QPushButton)} - {None}
        assert everything <= blocks_offered(view) or days == set(range(7)), options


@pytest.mark.parametrize("layout_id", MAIN_VIEWS)
def test_a_main_views_buttons_ask_for_the_right_thing(qapp: QApplication, layout_id: str) -> None:
    view = shown(layout_id, every_choice(layout_id)[0])
    asked: list[str] = []
    view.add_requested.connect(lambda _category: asked.append("add"))
    view.plan_requested.connect(lambda: asked.append("plan"))
    view.my_day_requested.connect(lambda: asked.append("my day"))
    view.block_activated.connect(asked.append)
    next(item for item in view.findChildren(QPushButton) if item.objectName().endswith("Add")).click()
    next(item for item in view.findChildren(QPushButton) if item.property("block_id") == "poster-1").click()
    assert asked == ["add", "poster-1"]


@pytest.mark.parametrize("layout_id", MAIN_VIEWS)
def test_a_main_view_survives_an_empty_week_and_another_week(qapp: QApplication, layout_id: str) -> None:
    palette = resolved_palette("light-frost", False, None, "default")
    options = every_choice(layout_id)[0]
    tokens = tokens_for(layout_id, options["colour"], palette)
    for today in (3, None):
        view = VIEW_CLASSES[layout_id]()
        view.show_week(Scene(build_week(WEEK, [], {}, None), today, minute_of("13:40"), options, tokens))
        found = names(view)
        assert any(name.endswith("Add") or "AddSmall" in name for name in found), found


@pytest.mark.parametrize("layout_id", ["clay", "mission"])
def test_a_designs_blocks_take_the_family_and_their_words_read_on_them(qapp, layout_id: str) -> None:
    """Clay lightened each mark and Mission darkened it, so in Match my look homework's darker mark
    came out neon red under dark words, and Mission's blocks were ink under ink. They take the one
    family now, pale on light cards and sunk into dark ones, in the look and in their own colours."""
    from desktop.native.calendar import CATEGORIES
    from desktop.native.hours.canvas import Drawn
    from desktop.native.hours.geometry import Span
    from desktop.native.layouts.clay import ClayPainter
    from desktop.native.layouts.mission import MissionPainter
    from desktop.native.layouts.registry import MATCH
    from desktop.native.look import contrast

    painter_for = {"clay": ClayPainter, "mission": MissionPainter}[layout_id]
    colourways = [MATCH, *(value for value, _, _ in LAYOUTS[layout_id].colourways)]
    unreadable = []
    for (pack, dark), colour in itertools.product((("light-frost", False), ("dark-frost", True)), colourways):
        painter = painter_for(tokens_for(layout_id, colour, resolved_palette(pack, dark, None)))
        for category in CATEGORIES:
            drawn = Drawn(category, "Block", category, category == "assignments", Span(0, 600, 660), 0, 1)
            fill, ink, _outline, _edge = painter.fills(drawn)
            if contrast(ink.name(), fill.name()) < 4.5:
                unreadable.append((pack, colour, category, round(contrast(ink.name(), fill.name()), 2)))
    assert unreadable == []
