"""Day dial, the clock-face day screen. The face is painted, so the tests hold it to two promises: a
click on an arc reaches that block, and every arc has a row beside it that a keyboard can reach.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

from desktop.tests.test_weekmodel import BLOCKS, HOMEWORK, TRACE, WEEK, block

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton

    from desktop.native.layouts.base import Scene
    from desktop.native.layouts.dial import DayDialView, DialFace
    from desktop.native.layouts.registry import options_for, tokens_for
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import build_week, minute_of

THURSDAY = 3


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-dial-test"])
    yield application


def shown(
    qapp: QApplication,
    clock: str,
    blocks: list[dict] | None = None,
    today: int | None = THURSDAY,
    **chosen: str,
) -> DayDialView:
    options = {**options_for(None, "dial"), **chosen}
    palette = resolved_palette("light-frost", False, None, "default")
    week = build_week(WEEK, blocks or BLOCKS, HOMEWORK, TRACE)
    view = DayDialView()
    view.resize(1300, 720)
    view.show_week(
        Scene(week, today, minute_of(clock), options, tokens_for("dial", options["colour"], palette))
    )
    view.show()
    qapp.processEvents()
    return view


def text(view: DayDialView, name: str) -> str:
    return view.findChild(QLabel, name).text()


def rows(view: DayDialView) -> list[tuple[str, str]]:
    found = [item for item in view.findChildren(QPushButton) if item.property("kind") == "row"]
    return [(item.text().split("    ")[1], item.property("state")) for item in found]


def reachable(face: DialFace) -> set[str]:
    hits = set()
    for x in range(0, face.width(), 5):
        for y in range(0, face.height(), 5):
            found = face.block_at(QPointF(x, y))
            if found is not None:
                hits.add(found.block_id)
    return hits


def test_during_homework_the_card_says_so_and_what_comes_after(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    assert text(view, "dialKicker") == "NOW · UNTIL 19:45 · 45 MIN LEFT"
    assert text(view, "dialTitle") == "Essay-1"
    assert text(view, "dialThen") == "THEN CHEM-1 AT 20:00"
    assert [
        item.objectName() for item in view.findChildren(QPushButton) if item.property("kind") != "row"
    ] == [
        "dialFinished",
        "dialFocus",
        "dialLate",
        "dialBack",
    ]


def test_the_list_reads_the_day_out_marking_what_is_over_and_what_is_on(qapp: QApplication) -> None:
    assert rows(shown(qapp, "19:00")) == [
        ("School", "past"),
        ("Dinner", "past"),
        ("Essay-1", "now"),
        ("Chem-1", ""),
    ]


def test_every_arc_has_a_row_a_keyboard_can_reach(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    opened: list[str] = []
    view.block_activated.connect(opened.append)
    for item in [entry for entry in view.findChildren(QPushButton) if entry.property("kind") == "row"]:
        assert item.focusPolicy() != Qt.FocusPolicy.NoFocus
        item.click()
    assert opened == ["school", "dinner", "essay-1", "chem-1"]
    assert reachable(view.findChild(DialFace, "dialFace")) == set(opened)


def test_a_click_on_an_arc_opens_that_block_and_the_middle_opens_nothing(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    face = view.findChild(DialFace, "dialFace")
    opened: list[str] = []
    view.block_activated.connect(opened.append)
    QTest.mouseClick(face, Qt.MouseButton.LeftButton, pos=QPoint(face.width() // 2, face.height() // 2))
    assert opened == []
    spot = next(
        QPoint(x, y)
        for x in range(0, face.width(), 4)
        for y in range(0, face.height(), 4)
        if (found := face.block_at(QPointF(x, y))) is not None and found.block_id == "chem-1"
    )
    QTest.mouseClick(face, Qt.MouseButton.LeftButton, pos=spot)
    assert opened == ["chem-1"]


def test_homework_inside_a_fixed_block_can_still_be_clicked(qapp: QApplication) -> None:
    inside = [*BLOCKS, block("study-hall", "flexible", [3], "10:00", 45, assignment_id="essay")]
    face = shown(qapp, "19:00", inside).findChild(DialFace, "dialFace")
    assert {"school", "study-hall"} <= reachable(face)


def test_a_small_dial_opens_that_day_and_today_is_one_press_back(qapp: QApplication) -> None:
    view = shown(qapp, "19:00")
    QTest.mouseClick(view.findChild(DialFace, "dialMini0"), Qt.MouseButton.LeftButton)
    assert text(view, "dialKicker") == "MONDAY, SEPTEMBER 14"
    assert text(view, "dialTitle") == "45 min planned · 45 min done"
    assert rows(view) == [("School", "past"), ("Math-1", "past"), ("Dinner", "past")]
    view.findChild(QPushButton, "dialToday").click()
    assert text(view, "dialKicker") == "NOW · UNTIL 19:45 · 45 MIN LEFT"


def test_in_another_week_it_shows_the_week_but_claims_no_now(qapp: QApplication) -> None:
    view = shown(qapp, "19:00", today=None)
    assert text(view, "dialKicker") == "MONDAY, SEPTEMBER 14"
    assert view.findChild(QPushButton, "dialToday") is None
    assert view.findChild(QPushButton, "dialFinished") is None
    assert view.findChild(QPushButton, "dialBack") is not None


def test_work_with_no_time_is_mentioned_with_the_way_to_fix_it(qapp: QApplication) -> None:
    assert text(shown(qapp, "19:00"), "dialWaiting") == (
        "1 task not placed yet. Go back to planning to give it a time."
    )


def test_option_all_24_hours_reaches_what_the_school_day_span_cannot(qapp: QApplication) -> None:
    early = [*BLOCKS, block("paper-round", "locked", [3], "05:00", 45)]
    assert "paper-round" not in reachable(shown(qapp, "19:00", early).findChild(DialFace, "dialFace"))
    assert "paper-round" in reachable(
        shown(qapp, "19:00", early, hours="full").findChild(DialFace, "dialFace")
    )


def test_option_list_hidden_and_week_hidden_remove_them(qapp: QApplication) -> None:
    assert rows(shown(qapp, "19:00", list="hide")) == []
    assert len(shown(qapp, "19:00").findChildren(DialFace)) == 8
    assert len(shown(qapp, "19:00", week="hide").findChildren(DialFace)) == 1


def test_option_colours_repaint_the_screen(qapp: QApplication) -> None:
    def corner(view: DayDialView) -> str:
        return view.grab().toImage().pixelColor(3, 3).name()

    assert corner(shown(qapp, "19:00", colour="midnight")) == "#0a0d1a"
    assert corner(shown(qapp, "19:00", colour="daylight")) == "#f4f6fb"
    assert (
        corner(shown(qapp, "19:00", colour="match"))
        == resolved_palette("light-frost", False, None, "default")["window"]
    )


def test_the_face_is_described_for_a_screen_reader(qapp: QApplication) -> None:
    face = shown(qapp, "19:00").findChild(DialFace, "dialFace")
    assert face.accessibleName() == "Thursday: School 08:00, Dinner 18:00, Essay-1 18:45, Chem-1 20:00"


def test_the_week_strip_survives_large_text(qapp: QApplication) -> None:
    """The strip is how another day is reached. At High contrast's larger text it used to be
    sliced in half by the scroller, with the day names off screen entirely."""
    from PySide6.QtWidgets import QLabel, QWidget

    options = options_for(None, "dial")
    palette = resolved_palette("light-frost", False, None, "default")
    view = DayDialView()
    view.resize(1366, 700)
    view.show()
    qapp.processEvents()
    view.show_week(
        Scene(
            build_week(WEEK, BLOCKS, HOMEWORK, TRACE),
            3,
            minute_of("13:40"),
            options,
            tokens_for("dial", options["colour"], palette),
            1.25,
        )
    )
    qapp.processEvents()
    strip = view.findChild(QWidget, "dialStrip")
    assert strip is not None and strip.isVisible()
    bottom = strip.mapTo(view, strip.rect().bottomLeft()).y()
    assert bottom <= view.height(), f"the strip runs {bottom - view.height()}px past the view"
    names = [label for label in strip.findChildren(QLabel) if label.objectName() == "dialMiniName"]
    assert len(names) == 7
    for label in names:
        edge = label.mapTo(view, label.rect().bottomLeft()).y()
        assert edge <= view.height(), f"{label.text()} is cut off"


def test_hiding_the_week_strip_still_works(qapp: QApplication) -> None:
    from PySide6.QtWidgets import QWidget

    assert shown(qapp, "19:00", week="hide").findChild(QWidget, "dialStrip").isVisible() is False
    assert shown(qapp, "19:00").findChild(QWidget, "dialStrip").isVisible() is True
