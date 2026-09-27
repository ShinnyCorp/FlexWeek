"""Motion never delays a click: the new page is live at once, and only a picture of the old one fades."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QPropertyAnimation, QRect, QRectF
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFrame, QLabel, QStackedWidget, QVBoxLayout, QWidget

    from desktop.native.hours.canvas import BlockPainter, HoursCanvas
    from desktop.native.hours.geometry import LinearTrack
    from desktop.native.hours.hand import Hand, Verdict
    from desktop.native.look import resolved_palette
    from desktop.native.motion import (
        DURATION_MS,
        FADE_NAME,
        app_level,
        appear,
        apply_ui_effects,
        glide,
        motion_level,
        slide_page,
        switch_page,
    )
    from desktop.native.weekmodel import Occurrence
    from desktop.native.widgets import Dialog


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-motion-test"])


def pictures(host: QWidget) -> list[QLabel]:
    return [label for label in host.findChildren(QLabel, FADE_NAME) if label.isVisible()]


def two_pages(qapp: QApplication) -> tuple[QStackedWidget, QWidget, QWidget]:
    stack = QStackedWidget()
    first, second = QLabel("Week"), QLabel("Month")
    stack.addWidget(first)
    stack.addWidget(second)
    stack.resize(400, 300)
    stack.show()
    qapp.processEvents()
    return stack, first, second


@pytest.mark.parametrize(
    ("preference", "look", "level"),
    [("off", "extra", "off"), (None, "extra", "extra"), (None, None, "normal"), ("fast", "normal", "normal")],
)
def test_the_students_setting_wins_over_the_looks_own(preference: object, look: object, level: str) -> None:
    assert motion_level(preference, look) == level


def test_a_switch_is_immediate_and_its_fade_clears_itself(qapp: QApplication) -> None:
    stack, _first, second = two_pages(qapp)
    switch_page(stack, second, "normal")
    assert stack.currentWidget() is second, "the new page is live before any animation"
    assert len(pictures(stack)) == 1
    QTest.qWait(DURATION_MS["normal"] + 150)
    assert pictures(stack) == []
    stack.close()


def test_a_switch_crossfades_the_new_page_in_under_the_old_one(qapp: QApplication) -> None:
    stack, _first, second = two_pages(qapp)
    switch_page(stack, second, "normal")
    QTest.qWait(40)
    effect = second.graphicsEffect()
    assert effect is not None and 0 < effect.opacity() < 1, "the new page is on its way in"
    assert len(pictures(stack)) == 1, "while the old one is on its way out"
    QTest.qWait(DURATION_MS["normal"] + 150)
    assert second.graphicsEffect() is None, "an effect left in place slows every later repaint"
    stack.close()


def test_off_means_no_animation(qapp: QApplication) -> None:
    stack, _first, second = two_pages(qapp)
    switch_page(stack, second, "off")
    assert stack.currentWidget() is second
    assert pictures(stack) == []
    stack.close()


def test_quick_switches_never_stack_pictures(qapp: QApplication) -> None:
    """A picture taken over a fading one would show the page before last."""
    stack, first, second = two_pages(qapp)
    switch_page(stack, second, "extra")
    switch_page(stack, first, "extra")
    qapp.processEvents()
    assert len(pictures(stack)) == 1
    QTest.qWait(DURATION_MS["extra"] + 150)
    assert pictures(stack) == []
    stack.close()


def test_a_notice_rises_into_place_and_leaves_no_effect_behind(qapp: QApplication) -> None:
    host = QWidget()
    host.resize(400, 300)
    notice = QLabel("Saved.", host)
    notice.move(40, 60)
    host.show()
    qapp.processEvents()
    appear(notice, "normal", rise=True)
    assert notice.graphicsEffect() is not None
    QTest.qWait(DURATION_MS["normal"] + 150)
    assert (notice.x(), notice.y()) == (40, 60)
    assert notice.graphicsEffect() is None, "an effect left in place slows every later repaint"
    host.close()


def test_a_page_slides_in_from_the_side_it_is_heading_and_lands_in_place(qapp: QApplication) -> None:
    stack, _first, second = two_pages(qapp)
    slide_page(stack, second, "normal", 1)
    assert stack.currentWidget() is second, "the new page is live before any animation"
    QTest.qWait(40)
    assert second.x() > 0, "going forward, the new page comes in from the right"
    assert len(pictures(stack)) == 1
    QTest.qWait(DURATION_MS["normal"] + 150)
    assert second.pos().isNull()
    assert second.graphicsEffect() is None
    assert pictures(stack) == []
    stack.close()


def test_an_animation_cut_short_by_another_leaves_the_widget_where_it_belongs(qapp: QApplication) -> None:
    """Stopping an animation does not say it finished, so its tidying has to happen anyway. A notice
    shown twice in a row rose from wherever the first rise had got to, and stayed that far down."""
    host = QWidget()
    host.resize(400, 300)
    notice = QLabel("Saved.", host)
    notice.move(40, 60)
    host.show()
    qapp.processEvents()
    appear(notice, "extra", rise=True)
    QTest.qWait(40)
    appear(notice, "extra", rise=True)
    QTest.qWait(DURATION_MS["extra"] + 150)
    assert (notice.x(), notice.y()) == (40, 60)
    assert notice.graphicsEffect() is None
    host.close()


def test_a_glide_ends_on_its_target(qapp: QApplication) -> None:
    host = QWidget()
    host.resize(200, 300)
    marker = QFrame(host)
    marker.setGeometry(QRect(10, 10, 3, 20))
    host.show()
    qapp.processEvents()
    glide(marker, QRect(10, 120, 3, 24), "normal")
    QTest.qWait(40)
    assert 10 < marker.y() < 120, "it moves there rather than jumping"
    glide(marker, QRect(10, 200, 3, 24), "normal")
    QTest.qWait(DURATION_MS["normal"] + 200)
    assert marker.geometry() == QRect(10, 200, 3, 24)
    glide(marker, QRect(10, 40, 3, 24), "off")
    assert marker.geometry() == QRect(10, 40, 3, 24), "with animations off it is simply there"
    host.close()


def test_a_notice_that_arrives_while_the_last_one_rises_lands_where_it_belongs(qapp: QApplication) -> None:
    """The hours a notice floats over can move while one rises, as large text grows the bar. A rise
    still running from the last notice carried the new one back to where the last was meant to go."""
    from desktop.native.widgets import TOAST_FOOT, Toast

    host = QWidget()
    host.resize(600, 400)
    hours = QWidget(host)
    hours.setGeometry(0, 60, 600, 300)
    toast = Toast(host, hours)
    toast.motion = "extra"
    host.show()
    qapp.processEvents()
    toast.show_message("Moved History essay to Fri 18:00.")
    QTest.qWait(30)
    hours.setGeometry(0, 72, 600, 280)
    toast.show_message("Running late: 16:30-17:00 is now locked.")
    QTest.qWait(DURATION_MS["extra"] + 150)
    assert toast.y() + toast.height() == 72 + 280 - TOAST_FOOT
    host.close()


def occurrence(block_id: str, day: int, start: int, end: int) -> Occurrence:
    title = block_id.title()
    return Occurrence(block_id, title, "class", day, start, end, False, False, False, None, None, None)


class Hours:
    """A week of hours on screen, with the hand that the window would own."""

    def __init__(self, qapp: QApplication) -> None:
        self.window = QWidget()
        self.window.resize(420, 500)
        self.hand = Hand(lambda block_id, from_day, span: Verdict(True, ""), self.window)
        self.canvas = HoursCanvas(
            self.hand,
            BlockPainter(resolved_palette("system", False, None)),
            lambda area: [
                LinearTrack(day, QRectF(area.left() + day * 60, area.top(), 60, area.height()), first=480)
                for day in range(7)
            ],
        )
        QVBoxLayout(self.window).addWidget(self.canvas)
        self.canvas.set_week([occurrence("essay", 1, 9 * 60, 10 * 60)])
        self.window.show()
        qapp.processEvents()

    def picture(self) -> QImage:
        return self.canvas.grab().toImage()

    def settled_picture(self, week: list[Occurrence]) -> QImage:
        """The week as it looks with nothing moving: drawn on a fresh canvas of the same size."""
        other = Hours.__new__(Hours)
        other.window = QWidget()
        other.window.resize(self.window.size())
        other.hand = Hand(lambda block_id, from_day, span: Verdict(True, ""), other.window)
        other.canvas = HoursCanvas(other.hand, self.canvas.painter, self.canvas._lay_out)
        QVBoxLayout(other.window).addWidget(other.canvas)
        other.window.show()
        QApplication.processEvents()
        other.canvas.set_week(week)
        picture = other.picture()
        other.window.close()
        return picture


LATER = [occurrence("essay", 3, 15 * 60, 16 * 60), occurrence("club", 5, 12 * 60, 13 * 60)]


def test_after_a_plan_blocks_slide_to_their_places_and_new_ones_fade_in(qapp: QApplication) -> None:
    hours = Hours(qapp)
    final = hours.settled_picture(LATER)
    hours.canvas.set_week(LATER)
    QTest.qWait(40)
    assert hours.picture() != final, "partway there, not already there"
    QTest.qWait(DURATION_MS[app_level()] + 150)
    assert hours.picture() == final
    hours.window.close()


def test_a_block_let_go_by_hand_is_already_where_it_belongs(qapp: QApplication) -> None:
    hours = Hours(qapp)
    moved = [occurrence("essay", 3, 15 * 60, 16 * 60)]
    final = hours.settled_picture(moved)
    hours.hand.dropped = "essay"
    hours.canvas.set_week(moved)
    assert hours.picture() == final, "it does not jump back to slide from where it was picked up"
    hours.window.close()


def test_animations_off_means_no_animation_anywhere(qapp: QApplication) -> None:
    apply_ui_effects("off")
    try:
        hours = Hours(qapp)
        final = hours.settled_picture(LATER)
        hours.canvas.set_week(LATER)
        assert hours.picture() == final, "blocks are simply where they are"
        hours.window.close()
        stack, _first, second = two_pages(qapp)
        switch_page(stack, second, app_level())
        assert pictures(stack) == [] and second.graphicsEffect() is None
        stack.close()
        dialog = Dialog()
        dialog.show()
        qapp.processEvents()
        assert dialog.windowOpacity() == 1.0
        assert dialog.findChildren(QPropertyAnimation) == []
        dialog.close()
    finally:
        apply_ui_effects("normal")


def test_a_dialog_eases_in_once(qapp: QApplication) -> None:
    dialog = Dialog()
    dialog.resize(300, 200)
    dialog.show()
    QTest.qWait(40)
    assert 0 < dialog.windowOpacity() < 1
    QTest.qWait(DURATION_MS[app_level()] + 150)
    assert dialog.windowOpacity() == 1.0
    dialog.hide()
    dialog.show()
    assert dialog.windowOpacity() == 1.0, "shown again, it is simply there"
    dialog.close()
