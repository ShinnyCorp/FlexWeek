"""One thing, the day screen. It is tested as a student meets it: what it says at a given minute, what
each button asks the window for, and that every option in its Layout section changes what is on screen.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

from desktop.tests.test_weekmodel import BLOCKS, HOMEWORK, TRACE, WEEK

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QPushButton

    from desktop.native.layouts.base import Scene, rules
    from desktop.native.layouts.one_thing import DayBar, OneThingView
    from desktop.native.layouts.registry import options_for, tokens_for
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import build_week, minute_of

THURSDAY = 3


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-one-thing-test"])
    yield application


def scene(clock: str, today: int | None = THURSDAY, **chosen: str) -> Scene:
    options = {**options_for(None, "one"), **chosen}
    palette = resolved_palette("light-frost", False, None, "default")
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    return Scene(week, today, minute_of(clock), options, tokens_for("one", options["colour"], palette))


def shown(qapp: QApplication, clock: str, today: int | None = THURSDAY, **chosen: str) -> OneThingView:
    view = OneThingView()
    view.resize(1200, 700)
    view.show_week(scene(clock, today, **chosen))
    view.show()
    qapp.processEvents()
    return view


def says(view: OneThingView) -> tuple[str, str, str]:
    return tuple(view.findChild(QLabel, name).text() for name in ("oneLabel", "oneTitle", "oneLine"))


def buttons(view: OneThingView) -> list[str]:
    return [button.objectName() for button in view.findChildren(QPushButton)]


def press(view: OneThingView, key: Qt.Key) -> None:
    view.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))


def test_during_school_it_says_school_and_how_long_is_left(qapp: QApplication) -> None:
    view = shown(qapp, "13:40")
    assert says(view) == ("NOW", "SCHOOL", "UNTIL 14:30 · 50 MIN LEFT")
    assert view.findChild(QProgressBar, "oneProgress").value() == 340
    assert view.findChild(QLabel, "oneLeft").text() == "2 H 30 MIN LEFT TODAY"
    assert view.findChild(QLabel, "oneThen").text() == "THEN: DINNER 18:00, ESSAY-1 18:45"


def test_a_fixed_block_offers_no_homework_buttons(qapp: QApplication) -> None:
    assert buttons(shown(qapp, "13:40")) == ["oneLate", "oneBack"]


def test_during_homework_it_offers_finishing_and_focus(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    assert says(view) == ("NOW", "ESSAY-1", "UNTIL 19:45 · 45 MIN LEFT")
    assert buttons(view) == ["oneFinished", "oneFocus", "oneLate", "oneBack"]


def test_between_blocks_it_says_what_is_next_and_in_how_long(qapp: QApplication) -> None:
    view = shown(qapp, "15:00")
    assert says(view) == ("UP NEXT", "DINNER", "18:00 · IN 3 H")
    assert view.findChild(QProgressBar, "oneProgress") is None


def test_when_the_day_is_over_it_says_what_tomorrow_starts_with(qapp: QApplication) -> None:
    view = shown(qapp, "22:30")
    assert says(view) == (
        "NOTHING ELSE SCHEDULED TODAY",
        "NOTHING ELSE SCHEDULED TODAY",
        "TOMORROW STARTS WITH SCHOOL AT 08:00",
    )
    assert buttons(view) == ["oneBack"]


def test_in_another_week_it_does_not_pretend_to_know_today(qapp: QApplication) -> None:
    view = shown(qapp, "13:40", today=None)
    assert says(view)[:2] == ("NOT THIS WEEK", "DAY SCREENS SHOW TODAY")
    assert buttons(view) == ["oneBack"]


def test_each_button_asks_the_window_for_exactly_one_thing(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    asked: list[tuple] = []
    view.finished_requested.connect(lambda homework: asked.append(("finished", homework)))
    view.focus_requested.connect(lambda block, day: asked.append(("focus", block, day)))
    view.late_requested.connect(lambda: asked.append(("late",)))
    view.back_requested.connect(lambda: asked.append(("back",)))
    for name in ("oneFinished", "oneFocus", "oneLate", "oneBack"):
        view.findChild(QPushButton, name).click()
    assert asked == [("finished", "essay"), ("focus", "essay-1", THURSDAY), ("late",), ("back",)]


def test_space_walks_through_the_rest_of_the_day_and_comes_back_round(qapp: QApplication) -> None:
    view = shown(qapp, "13:40")
    seen = []
    for _ in range(5):
        press(view, Qt.Key.Key_Space)
        seen.append(says(view)[:2])
    assert seen == [
        ("UP NEXT", "DINNER"),
        ("LATER TODAY", "ESSAY-1"),
        ("LATER TODAY", "CHEM-1"),
        ("NOW", "SCHOOL"),
        ("UP NEXT", "DINNER"),
    ]


def test_enter_opens_the_thing_on_screen(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    opened: list[str] = []
    view.block_activated.connect(opened.append)
    press(view, Qt.Key.Key_Return)
    assert opened == ["essay-1"]


def test_a_new_minute_keeps_the_place_but_a_changed_week_starts_over(qapp: QApplication) -> None:
    view = shown(qapp, "13:40")
    press(view, Qt.Key.Key_Space)
    view.show_week(scene("13:41"))
    assert says(view)[:2] == ("UP NEXT", "DINNER")
    done = [{**block, "completed": True} if block["id"] == "essay-1" else block for block in BLOCKS]
    base = scene("13:41")
    view.show_week(
        Scene(build_week(WEEK, done, HOMEWORK, TRACE), THURSDAY, base.minute, base.options, base.tokens)
    )
    assert says(view)[:2] == ("NOW", "SCHOOL")


def test_option_lead_with_what_is_next_skips_what_is_on_now(qapp: QApplication) -> None:
    assert says(shown(qapp, "13:40", lead="next")) == ("UP NEXT", "DINNER", "18:00 · IN 4 H 20 MIN")


def test_option_buttons_hidden_leaves_only_the_way_back(qapp: QApplication) -> None:
    assert buttons(shown(qapp, "19:00", actions="hide")) == ["oneBack"]


def test_option_day_bar_hidden_removes_it(qapp: QApplication) -> None:
    assert shown(qapp, "19:00").findChild(DayBar) is not None
    assert shown(qapp, "19:00", daybar="hide").findChild(DayBar) is None


def test_option_colours_repaint_the_screen(qapp: QApplication) -> None:
    def corner(view: OneThingView) -> str:
        return view.grab().toImage().pixelColor(4, 4).name()

    assert corner(shown(qapp, "19:00", colour="black")) == "#000000"
    assert corner(shown(qapp, "19:00", colour="paper")) == "#f7f1e3"
    look = resolved_palette("light-frost", False, None, "default")
    assert corner(shown(qapp, "19:00", colour="match")) == look["window"]


def test_the_label_is_painted_in_the_accent_not_the_resets_colour(qapp: QApplication) -> None:
    view = shown(qapp, "19:00", colour="black")
    picture = view.findChild(QLabel, "oneLabel").grab().toImage()
    inked = {picture.pixelColor(x, y).name() for x in range(picture.width()) for y in range(picture.height())}
    assert "#fb923c" in inked
    assert "#ffffff" not in inked


def test_both_labels_of_a_shared_rule_get_its_colour(qapp: QApplication) -> None:
    view = shown(qapp, "13:40", colour="paper")
    for name in ("oneDate", "oneLeft"):
        picture = view.findChild(QLabel, name).grab().toImage()
        inked = {
            picture.pixelColor(x, y).name() for x in range(picture.width()) for y in range(picture.height())
        }
        assert "#57534e" in inked, name
        assert "#1c1917" not in inked, name


def test_every_selector_in_a_list_is_tied_to_the_view() -> None:
    assert rules("layoutOne", {"#a, #b": "color: red;"}) == "#layoutOne #a, #layoutOne #b { color: red; }"


def test_text_size_scales_the_screen(qapp: QApplication) -> None:
    base = scene("19:00")
    large = Scene(base.week, base.today, base.minute, base.options, base.tokens, 1.25)
    view = OneThingView()
    view.resize(1200, 700)
    view.show_week(base)
    normal_height = view.findChild(QPushButton, "oneBack").minimumSizeHint().height()
    view.show_week(large)
    view.show()
    qapp.processEvents()
    assert view.findChild(QPushButton, "oneBack").minimumSizeHint().height() > normal_height


def test_an_unchanged_scene_leaves_the_screen_alone(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    before = view.findChild(QPushButton, "oneBack")
    view.show_week(scene("19:00"))
    assert view.findChild(QPushButton, "oneBack") is before


def test_a_new_minute_does_not_take_the_keyboard_away(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    view.activateWindow()
    view.findChild(QPushButton, "oneLate").setFocus()
    qapp.processEvents()
    view.show_week(scene("19:01"))
    qapp.processEvents()
    assert QApplication.focusWidget() is view.findChild(QPushButton, "oneLate")


def test_a_long_title_in_a_short_window_is_never_cut_off(qapp: QApplication) -> None:
    long_title = [
        {**block, "title": "History essay outline and the annotated bibliography"}
        if block["id"] == "essay-1"
        else block
        for block in BLOCKS
    ]
    base = scene("19:00")
    view = OneThingView()
    view.resize(1366, 430)
    view.show_week(
        Scene(build_week(WEEK, long_title, HOMEWORK, TRACE), THURSDAY, base.minute, base.options, base.tokens)
    )
    view.show()
    qapp.processEvents()
    title = view.findChild(QLabel, "oneTitle")
    assert title.text() == "HISTORY ESSAY OUTLINE AND THE ANNOTATED BIBLIOGRAPHY"
    assert title.heightForWidth(title.width()) <= title.height()
