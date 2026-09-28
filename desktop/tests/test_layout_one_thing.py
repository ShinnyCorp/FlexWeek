"""One thing, the day screen, drawn as 0.17's Countdown. It is tested as a student meets it: what it
says and counts down at a given minute, what each button asks the window for, and that every option in
its Layout section changes what is on screen.
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
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton

    from desktop.native.layouts.base import Scene, rules
    from desktop.native.layouts.one_thing import RING_ROOMY, DayBar, OneThingView
    from desktop.native.layouts.registry import options_for, tokens_for
    from desktop.native.look import resolved_palette
    from desktop.native.ring import CountdownRing
    from desktop.native.weekmodel import build_week, minute_of
    from desktop.native.widgets import FittedLabel

THURSDAY = 3


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-one-thing-test"])
    yield application


def scene(clock: str, today: int | None = THURSDAY, accent: str = "default", **chosen: str) -> Scene:
    options = {**options_for(None, "one"), **chosen}
    palette = resolved_palette("light-frost", False, None, accent)
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    return Scene(week, today, minute_of(clock), options, tokens_for("one", options["colour"], palette))


def shown(
    qapp: QApplication,
    clock: str,
    today: int | None = THURSDAY,
    size: tuple[int, int] = (1200, 820),
    **chosen: str,
) -> OneThingView:
    view = OneThingView()
    view.resize(*size)
    view.show_week(scene(clock, today, **chosen))
    view.show()
    qapp.processEvents()
    return view


def says(view: OneThingView) -> tuple[str, str, str]:
    return tuple(view.findChild(QLabel, name).text() for name in ("oneLabel", "oneTitle", "oneLine"))


def counts(view: OneThingView) -> tuple[str, float]:
    """The ring's number and the share of its hour still to go."""
    ring = view.findChild(CountdownRing)
    return ring.number(), round(ring.left(), 3)


def then(view: OneThingView) -> list[str]:
    """What the Then list shows, a row each, as the student reads it across."""
    rows = [row for row in view.findChildren(QLabel, "oneRowTime") if row.isVisibleTo(view)]
    return [
        " ".join(
            [
                row.text(),
                row.parent().findChild(FittedLabel, "oneRowName").full_text(),
                row.parent().findChild(QLabel, "oneRowLength").text(),
            ]
        )
        for row in rows
    ]


def buttons(view: OneThingView) -> list[str]:
    return [button.objectName() for button in view.findChildren(QPushButton)]


def press(view: OneThingView, key: Qt.Key) -> None:
    view.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))


def test_during_school_it_counts_down_what_is_left_of_it(qapp: QApplication) -> None:
    view = shown(qapp, "13:40")
    assert says(view) == ("Now", "School", "08:00–14:30")
    assert counts(view) == ("50", round(50 / 60, 3))
    assert view.findChild(QLabel, "oneDate").text() == "Now 13:40"
    assert view.findChild(QLabel, "oneLeft").text() == "4 things left today"
    assert then(view) == ["18:00 Dinner 30 min", "18:45 Essay-1 1 h", "20:00 Chem-1 1 h 30 min"]


def test_the_ring_is_the_hour_ahead_like_a_kitchen_timer(qapp: QApplication) -> None:
    """Twenty minutes to go is a third of the ring from the top; three hours or more is the whole
    ring, and the number turns to hours."""
    assert counts(shown(qapp, "17:40")) == ("20", round(20 / 60, 3))
    assert counts(shown(qapp, "15:20")) == ("2:40", 1.0)
    assert counts(shown(qapp, "15:00")) == ("3", 1.0)
    assert shown(qapp, "15:00").findChild(CountdownRing).accessibleName() == "3 h until it starts"


def test_a_fixed_block_offers_no_homework_buttons(qapp: QApplication) -> None:
    assert buttons(shown(qapp, "13:40")) == ["oneLate", "oneBack"]


def test_during_homework_it_offers_finishing_and_focus(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    assert says(view) == ("Now", "Essay-1", "18:45–19:45")
    assert buttons(view) == ["oneFinished", "oneFocus", "oneLate", "oneBack"]


def test_between_blocks_it_says_what_is_next_and_when(qapp: QApplication) -> None:
    assert says(shown(qapp, "15:00")) == ("Up next", "Dinner", "18:00–18:30")


def test_when_the_day_is_over_it_says_what_tomorrow_starts_with(qapp: QApplication) -> None:
    view = shown(qapp, "22:30")
    assert says(view) == (
        "Nothing else scheduled today",
        "Nothing else scheduled today",
        "Tomorrow starts with School at 08:00",
    )
    # Said once: the heading would only repeat the title inside the ring.
    assert view.findChild(QLabel, "oneLabel").isVisibleTo(view) is False
    assert counts(view) == ("", 0.0)
    assert then(view) == []
    assert buttons(view) == ["oneBack"]


def test_in_another_week_it_does_not_pretend_to_know_today(qapp: QApplication) -> None:
    view = shown(qapp, "13:40", today=None)
    assert says(view)[:2] == ("Not this week", "Day screens show today")
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
        ("Up next", "Dinner"),
        ("Later today", "Essay-1"),
        ("Later today", "Chem-1"),
        ("Now", "School"),
        ("Up next", "Dinner"),
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
    assert says(view)[:2] == ("Up next", "Dinner")
    done = [{**block, "completed": True} if block["id"] == "essay-1" else block for block in BLOCKS]
    base = scene("13:41")
    view.show_week(
        Scene(build_week(WEEK, done, HOMEWORK, TRACE), THURSDAY, base.minute, base.options, base.tokens)
    )
    assert says(view)[:2] == ("Now", "School")


def test_option_lead_with_what_is_next_skips_what_is_on_now(qapp: QApplication) -> None:
    view = shown(qapp, "13:40", lead="next")
    assert says(view) == ("Up next", "Dinner", "18:00–18:30")
    assert counts(view) == ("4:20", 1.0)


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


def test_poster_counts_down_in_the_students_accent_not_0_16s_orange(qapp: QApplication) -> None:
    for accent in ("default", "sea"):
        worn = tokens_for("one", "black", resolved_palette("light-frost", False, None, accent))["accent"]
        view = shown(qapp, "19:00", colour="black", accent=accent)
        picture = view.findChild(CountdownRing).grab().toImage()
        inked = {
            picture.pixelColor(x, y).name() for x in range(picture.width()) for y in range(picture.height())
        }
        assert worn in inked, accent
        assert "#fb923c" not in inked, accent


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


def test_a_long_title_in_a_short_window_takes_two_lines_and_shortens_the_rest(qapp: QApplication) -> None:
    """Inside the ring there is room for two lines. The rest is shortened with an ellipsis rather than
    cut off or run into the number, and the whole name is in its tooltip and read out."""
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
    whole = "History essay outline and the annotated bibliography"
    assert title.text().count("\n") <= 1 and title.text().endswith("…")
    assert (title.toolTip(), title.accessibleName()) == (whole, whole)
    assert title.heightForWidth(title.width()) <= title.height()


def test_in_a_short_window_then_gives_way_before_the_ring_gets_small(qapp: QApplication) -> None:
    roomy = shown(qapp, "13:40")
    assert len(then(roomy)) == 3
    short = shown(qapp, "13:40", size=(1366, 560))
    assert then(short) == []
    assert short.findChild(CountdownRing).width() >= RING_ROOMY
