"""Motion never delays a click: the new page is live at once, only a picture of the old one fades, and
what comes in is painted on its way while the widget already sits where it belongs."""

from __future__ import annotations

import importlib.util
import os
import time
from collections.abc import Callable, Iterator

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QAbstractAnimation, QEvent, QPoint, QRect, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPalette, QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QGraphicsDropShadowEffect,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )

    from desktop.native.hours.canvas import BlockPainter, HoursCanvas
    from desktop.native.hours.geometry import LinearTrack
    from desktop.native.hours.hand import Hand, Verdict
    from desktop.native.look import MOTION_LEVELS, resolved_palette
    from desktop.native.motion import (
        EASE_MS,
        FADE_NAME,
        LEVELS,
        OVER_MS,
        PAGE_IN_AFTER_MS,
        PAGE_IN_MS,
        PAGE_OUT_MS,
        RISE_PX,
        SEGMENT_MS,
        SLIDE_NAME,
        SLIDE_PX,
        Clock,
        Dim,
        app_level,
        appear,
        apply_ui_effects,
        distance,
        duration,
        glide,
        hold_picture,
        motion_level,
        moves,
        slide_down,
        slide_over,
        switch_page,
    )
    from desktop.native.weekmodel import Occurrence
    from desktop.native.widgets import Dialog, PlanReview, Segment, SegmentTrack
    from desktop.tests.motion_support import ManualTime, manual_time  # noqa: F401


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-motion-test"])


def pictures(host: QWidget) -> list[QLabel]:
    return [label for label in host.findChildren(QLabel, FADE_NAME) if label.isVisible()]


def slides(host: QWidget) -> list[QLabel]:
    return [label for label in host.findChildren(QLabel, SLIDE_NAME) if label.isVisible()]


# Long enough for a page to fade through at the slowest level, with room for a busy machine.
THROUGH_MS = duration(max(PAGE_OUT_MS, PAGE_IN_AFTER_MS + PAGE_IN_MS), "extra") + 150


def two_pages(qapp: QApplication) -> tuple[QStackedWidget, QWidget, QWidget]:
    stack = QStackedWidget()
    first, second = QLabel("Week"), QLabel("Month")
    stack.addWidget(first)
    stack.addWidget(second)
    stack.resize(400, 300)
    stack.show()
    qapp.processEvents()
    return stack, first, second


def within(seconds: float, done: Callable[[], bool]) -> bool:
    """Whether `done` comes true within `seconds`, looked at every few milliseconds. One look after a
    fixed wait failed on a busy test worker that had not yet run the fade's last frame."""
    deadline = time.monotonic() + seconds
    while not done():
        if time.monotonic() > deadline:
            return False
        QTest.qWait(5)
    return True


@pytest.mark.parametrize(
    ("preference", "look", "level"),
    [
        ("off", "extra", "off"),
        (None, "extra", "extra"),
        (None, None, "normal"),
        ("fast", "normal", "normal"),
        (None, "reduce", "reduce"),
        ("reduce", "normal", "reduce"),
    ],
)
def test_the_students_setting_wins_over_the_looks_own(preference: object, look: object, level: str) -> None:
    assert motion_level(preference, look) == level


def test_the_four_levels_are_the_ones_preferences_and_custom_looks_store() -> None:
    assert tuple(LEVELS) == MOTION_LEVELS == ("normal", "extra", "reduce", "off")


def test_normal_runs_the_plans_numbers_and_the_other_levels_scale_them() -> None:
    """Decisions 30 to 33 of 0.17, and the page change as 0.17.2 has it: 120 ms out, 160 in starting
    30 ms after, a 24-pixel slide (at 12 none was seen), an 8-pixel rise, Settings in 200 ms and the
    segment in 160. Reduce keeps every fade at Normal's length and moves nothing; More is longer and
    further; Off is at once."""
    timings = (PAGE_OUT_MS, PAGE_IN_MS, PAGE_IN_AFTER_MS, OVER_MS, SEGMENT_MS)
    normal = [duration(ms, "normal") for ms in timings]
    assert normal == [120, 160, 30, 200, 160]
    assert (distance(SLIDE_PX, "normal"), distance(RISE_PX, "normal")) == (24, 8)
    for ms in normal:
        assert duration(ms, "reduce") == ms
        assert duration(ms, "extra") > ms
        assert duration(ms, "off") == 0
    for px in (SLIDE_PX, RISE_PX):
        assert distance(px, "reduce") == distance(px, "off") == 0
        assert distance(px, "extra") > distance(px, "normal")
    assert [moves(level) for level in MOTION_LEVELS] == [True, True, False, False]


def test_more_is_clearly_longer_than_normal_with_the_standard_ease_at_about_450_ms() -> None:
    """0.18.5 #96: Normal and More used to look much alike (a Normal switch about 0.3 s, More about
    0.23 s in Jonathan's check). The roadmap asks for about 0.45 s for More's standard ease against
    Normal's 0.18 s, and every other length scales with it, so no part of More is only a little
    longer than Normal's."""
    assert duration(EASE_MS, "normal") == 180
    assert duration(EASE_MS, "extra") == 450
    for ms in (PAGE_OUT_MS, PAGE_IN_MS, PAGE_IN_AFTER_MS, OVER_MS, SEGMENT_MS, EASE_MS):
        assert duration(ms, "extra") >= 2 * duration(ms, "normal"), ms
    # Reduce keeps Normal's lengths, so More is clearly longer than it too; Off is at once.
    assert duration(EASE_MS, "reduce") == 180 and duration(EASE_MS, "off") == 0
    assert distance(SLIDE_PX, "extra") > distance(SLIDE_PX, "normal")


def test_a_switch_is_immediate_and_its_fade_clears_itself(qapp: QApplication) -> None:
    stack, _first, second = two_pages(qapp)
    switch_page(stack, second, "normal")
    assert stack.currentWidget() is second, "the new page is live before any animation"
    assert len(pictures(stack)) == 1
    QTest.qWait(THROUGH_MS)
    assert pictures(stack) == []
    stack.close()


@pytest.mark.parametrize("level", ["normal", "extra", "reduce"])
def test_a_switch_never_shows_an_empty_page(qapp: QApplication, level: str) -> None:
    """Grok Bot's 0.17.0 audit (A1): when the new page waited for the old one to go (decision 28), the
    window dipped through 3 or 4 almost blank frames. Now the new page comes in while the old one is
    still going: together they are never less than three quarters there, and the old one is half gone
    before the new one is half there, so the two are only seen together faintly."""
    stack, _first, second = two_pages(qapp)
    switch_page(stack, second, level)
    frames: list[tuple[float, float]] = []

    def frame() -> bool:
        """Note how opaque the old page and the new one are painted; true once the fade is over."""
        old, new = pictures(stack), second.graphicsEffect()
        going = max((picture.graphicsEffect().opacity for picture in old), default=0.0)
        frames.append((going, new.opacity if new else 1.0))
        return not old and new is None

    assert within(2, frame), "an effect left in place slows every later repaint"
    assert frames[0] == (1.0, 0.0), "it starts from the old page"
    assert min(old + new for old, new in frames) >= 0.7, "never an empty page"
    assert any(0 < old < 1 and 0 < new < 1 for old, new in frames), "the new one comes in as the old goes"
    assert all(old <= 0.5 for old, new in frames if new >= 0.5), "the old is half gone by the time"
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
    QTest.qWait(THROUGH_MS)
    assert pictures(stack) == []
    assert (first.graphicsEffect(), second.graphicsEffect()) == (None, None)
    stack.close()


def test_a_clock_reads_the_time_source_and_a_paused_one_stands_still(
    qapp: QApplication, manual_time: ManualTime  # noqa: F811
) -> None:
    host = QWidget()
    seen: list[float] = []
    clock = Clock(host)
    clock.start(100, seen.append)
    manual_time.advance(30)
    assert clock.currentTime() == 30 and seen[-1] == 30.0
    clock.pause()
    manual_time.advance(500)
    assert clock.currentTime() == 30 and seen[-1] == 30.0, "time that passes while paused is not counted"
    clock.resume()
    manual_time.advance(20)
    assert clock.currentTime() == 50 and seen[-1] == 50.0
    manual_time.advance(1_000)
    assert seen[-1] == 100.0, "a late frame still ends on the end"
    assert clock.state() == QAbstractAnimation.State.Stopped
    host.close()


def test_a_notice_rises_into_place_and_leaves_no_effect_behind(
    qapp: QApplication, manual_time: ManualTime  # noqa: F811
) -> None:
    host = QWidget()
    host.resize(400, 300)
    notice = QLabel("Saved.", host)
    notice.move(40, 60)
    host.show()
    qapp.processEvents()
    appear(notice, "normal", rise=True)
    effect = notice.graphicsEffect()
    assert effect is not None and effect.offset == QPoint(0, 8), "it starts 8 pixels low"
    assert (notice.x(), notice.y()) == (40, 60), "painted low: the notice itself is already in place"
    manual_time.advance(duration(EASE_MS, "normal") // 2)
    # Half the 180 ms on the out-cubic ease: 1 - (1 - 1/2)^3 = 7/8 of the way, so 1/8 of the 8 pixels left.
    assert effect.opacity == pytest.approx(0.875) and effect.offset == QPoint(0, 1)
    manual_time.advance(duration(EASE_MS, "normal") // 2)
    assert (notice.x(), notice.y()) == (40, 60)
    assert notice.graphicsEffect() is None, "an effect left in place slows every later repaint"
    host.close()


def test_a_page_slides_in_from_the_side_it_is_heading_and_lands_in_place(
    qapp: QApplication, manual_time: ManualTime  # noqa: F811
) -> None:
    stack, _first, second = two_pages(qapp)
    switch_page(stack, second, "normal", 1)
    assert stack.currentWidget() is second, "the new page is live before any animation"
    assert second.graphicsEffect().offset == QPoint(24, 0), "going forward, it comes in from the right"
    assert second.pos().isNull(), "painted to the side: the page itself is where clicks find it"
    manual_time.advance(40)
    (old,) = pictures(stack)
    # The old page fades evenly over 120 ms and drifts 24 pixels left: a third of the way at 40 ms.
    assert old.graphicsEffect().offset == QPoint(-8, 0), "the old page drifts away to the left"
    assert old.graphicsEffect().opacity == pytest.approx(2 / 3)
    # The new one starts 30 ms behind and takes 160, out-cubic: 10/160 in, 1 - (15/16)^3 of the way.
    assert second.graphicsEffect().opacity == pytest.approx(1 - (15 / 16) ** 3)
    assert second.graphicsEffect().offset == QPoint(20, 0)
    manual_time.advance(THROUGH_MS)
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert second.pos().isNull()
    assert second.graphicsEffect() is None
    assert pictures(stack) == []
    stack.close()


def test_under_reduce_a_page_fades_through_and_moves_nothing(
    qapp: QApplication, manual_time: ManualTime  # noqa: F811
) -> None:
    stack, _first, second = two_pages(qapp)
    switch_page(stack, second, "reduce", 1)
    effect = second.graphicsEffect()
    assert effect.offset == QPoint() and effect.opacity == 0, "no slide, and still a fade"
    manual_time.advance(40)
    (old,) = pictures(stack)
    assert old.graphicsEffect().offset == QPoint(), "no drift"
    assert old.graphicsEffect().opacity == pytest.approx(2 / 3), "a third of 120 ms gone"
    manual_time.advance(THROUGH_MS)
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert pictures(stack) == [] and second.graphicsEffect() is None
    stack.close()


def test_settings_slides_in_from_the_right_over_the_page_dimmed(qapp: QApplication) -> None:
    """Decision 30 of 0.17: Settings slides in over the week dimmed 20 %, rather than fading over it."""
    stack, first, second = two_pages(qapp)
    slide_over(stack, second, "normal")
    assert stack.currentWidget() is second and second.graphicsEffect() is None
    (coming,) = slides(stack)
    assert coming.pos() == QPoint(stack.width(), 0), "its picture starts off the right edge"
    (week,) = pictures(stack)
    kids = stack.children()
    assert kids.index(week) < kids.index(coming), "the page it covers stays under it"
    assert len(week.findChildren(Dim)) == 1
    QTest.qWait(duration(OVER_MS, "normal") // 2)
    assert 0 < coming.x() < stack.width()
    assert 0 < week.findChildren(Dim)[0].share < 1, "the page under it is dimming"
    QTest.qWait(duration(OVER_MS, "extra") + 150)
    assert pictures(stack) == [] and slides(stack) == [] and second.graphicsEffect() is None
    slide_over(stack, first, "normal", back=True)
    assert stack.currentWidget() is first and first.graphicsEffect() is None, "the page under it is live"
    (leaving,) = pictures(stack)
    assert leaving.graphicsEffect().offset == QPoint(), "it slides away from where it was"
    assert len(stack.findChildren(Dim, options=Qt.FindChildOption.FindDirectChildrenOnly)) == 1
    QTest.qWait(duration(OVER_MS, "extra") + 150)
    assert pictures(stack) == [] and stack.findChildren(Dim) == []
    stack.close()


def test_the_page_sliding_in_is_painted_once_not_on_every_frame(qapp: QApplication) -> None:
    """J12: Settings stuttered in. The page was drawn through an effect, which paints the whole page
    again for each frame. A picture of it slides instead, so the page paints for the picture and when
    it lands, however many frames the slide has."""

    class Counted(QLabel):
        paints = 0

        def paintEvent(self, event: object) -> None:  # noqa: N802
            Counted.paints += 1
            super().paintEvent(event)  # type: ignore[arg-type]

    stack = QStackedWidget()
    first, second = QLabel("Week"), Counted("Settings")
    stack.addWidget(first)
    stack.addWidget(second)
    stack.resize(400, 300)
    stack.show()
    qapp.processEvents()
    Counted.paints = 0
    slide_over(stack, second, "normal")
    frames = 0
    deadline = time.monotonic() + (duration(OVER_MS, "normal") + 150) / 1000
    while time.monotonic() < deadline:
        qapp.processEvents()
        frames += 1
        QTest.qWait(8)
    assert frames >= 8, "the slide ran for several frames"
    assert Counted.paints <= 3, f"the page painted {Counted.paints} times over {frames} frames"
    assert stack.currentWidget() is second and second.graphicsEffect() is None
    stack.close()


def test_the_design_pictures_wait_until_settings_has_slid_in(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """J12: each design's picture takes over 100 ms to draw, and they were drawn one after another
    from the moment Settings was built, so the first slide in got three frames. The first is held
    until a slide at the slowest level has landed."""
    from desktop.native.layouts import dialog
    from desktop.native.layouts.dialog import DesignPicker

    drawn: list[float] = []
    started = time.monotonic()

    class Counting:
        def get(self, *_args: object) -> QPixmap:
            drawn.append(time.monotonic() - started)
            return QPixmap(4, 4)

    monkeypatch.setattr(dialog, "Previews", Counting)
    picker = DesignPicker("plan", "designs", "Design", "slate")
    assert picker.cards
    picker.show()
    slide = duration(OVER_MS, "extra") / 1000
    while time.monotonic() - started < slide:
        qapp.processEvents()
        QTest.qWait(5)
    assert drawn == [], "nothing is drawn while the page could still be sliding in"
    assert within(3, lambda: len(drawn) == len(picker.cards)), "then every picture is drawn"
    assert drawn[0] >= slide
    picker.close()
    picker.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_under_reduce_settings_fades_through_rather_than_over_the_page(qapp: QApplication) -> None:
    stack, _first, second = two_pages(qapp)
    slide_over(stack, second, "reduce")
    effect = second.graphicsEffect()
    assert effect.offset == QPoint() and effect.opacity == 0
    assert stack.findChildren(Dim) == []
    assert within(2, lambda: second.graphicsEffect() is None and pictures(stack) == [])
    stack.close()


def test_an_animation_cut_short_by_another_leaves_the_widget_where_it_belongs(
    qapp: QApplication, manual_time: ManualTime  # noqa: F811
) -> None:
    """Stopping an animation does not say it finished, so its tidying has to happen anyway. A notice
    shown twice in a row rose from wherever the first rise had got to, and stayed that far down."""
    host = QWidget()
    host.resize(400, 300)
    notice = QLabel("Saved.", host)
    notice.move(40, 60)
    host.show()
    qapp.processEvents()
    appear(notice, "extra", rise=True)
    manual_time.advance(40)
    appear(notice, "extra", rise=True)
    manual_time.advance(duration(EASE_MS, "extra"))
    assert (notice.x(), notice.y()) == (40, 60)
    assert notice.graphicsEffect() is None
    host.close()


def opening_review(qapp: QApplication, level: str) -> tuple[QWidget, PlanReview, QWidget]:
    from desktop.tests.test_plan_review import TITLES, TRACE, WEEK

    host = QWidget()
    column = QVBoxLayout(host)
    review = PlanReview(host)
    below = QLabel("The page below", host)
    column.addWidget(review)
    column.addWidget(below)
    column.addStretch(1)
    host.resize(500, 400)
    host.show()
    qapp.processEvents()
    review.set_trace(TRACE, TITLES, WEEK, (2, 1))
    slide_down(review, level)
    return host, review, below


def test_the_plan_review_slides_down_over_the_planner_without_pushing_it(qapp: QApplication) -> None:
    """#98: the bar grew in the column, so Got it was a grey strip for a frame and the week jumped."""
    host = QWidget()
    host.resize(500, 400)
    planner = QLabel("Week hours", host)
    planner.setGeometry(0, 120, 500, 280)
    review = PlanReview(host)
    review.set_trace(
        {"unplaced": [], "moves": [], "explanations": []},
        {},
        "2026-01-05",
        (2, 0),
    )
    review.setGeometry(0, 40, 500, review.sizeHint().height())
    host.show()
    qapp.processEvents()
    before = planner.y()
    slide_down(review, "normal")
    qapp.processEvents()
    assert planner.y() == before, "the planner stays put while the bar moves over it"
    assert review.height() == review.sizeHint().height(), "the bar is drawn at full height from the start"
    QTest.qWait(duration(EASE_MS, "normal") + 100)
    assert planner.y() == before
    host.close()


def test_the_plan_review_opened_again_before_it_finished_still_ends_free(qapp: QApplication) -> None:
    host, review, _below = opening_review(qapp, "normal")
    review._motion_running[0].setCurrentTime(40)
    slide_down(review, "normal")
    review._motion_running[0].setCurrentTime(duration(EASE_MS, "normal"))
    assert review.maximumHeight() == 16777215
    host.close()


@pytest.mark.parametrize("level", ["reduce", "off"])
def test_where_nothing_travels_the_plan_review_is_full_height_at_once(qapp: QApplication, level: str) -> None:
    host, review, _below = opening_review(qapp, level)
    assert review.maximumHeight() == 16777215
    qapp.processEvents()
    assert review.height() == review.sizeHint().height()
    host.close()


def test_a_glide_ends_on_its_target(qapp: QApplication, manual_time: ManualTime) -> None:  # noqa: F811
    host = QWidget()
    host.resize(200, 300)
    marker = QFrame(host)
    marker.setGeometry(QRect(10, 10, 3, 20))
    host.show()
    qapp.processEvents()
    glide(marker, QRect(10, 120, 3, 24), "normal")
    manual_time.advance(40)
    # 40 of the 240 ms on the out-cubic ease is 1 - (5/6)^3 = 0.4213 of the way: 10 + 110 * 0.4213.
    assert marker.geometry() == QRect(10, 56, 3, 22), "it moves there rather than jumping"
    glide(marker, QRect(10, 200, 3, 24), "normal")
    manual_time.advance(duration(EASE_MS + 60, "normal"))
    assert marker.geometry() == QRect(10, 200, 3, 24)
    glide(marker, QRect(10, 40, 3, 24), "off")
    assert marker.geometry() == QRect(10, 40, 3, 24), "with animations off it is simply there"
    glide(marker, QRect(10, 90, 3, 24), "reduce")
    assert marker.geometry() == QRect(10, 90, 3, 24), "under Reduce it does not travel either"
    host.close()


def test_a_notice_that_arrives_while_the_last_one_rises_lands_where_it_belongs(
    qapp: QApplication, manual_time: ManualTime  # noqa: F811
) -> None:
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
    manual_time.advance(30)
    hours.setGeometry(0, 72, 600, 280)
    toast.show_message("Running late: 16:30-17:00 is now locked.")
    manual_time.advance(duration(EASE_MS, "extra"))
    # The card, inside the room the toast keeps round it for its shadow.
    assert toast.y() + toast.card.geometry().bottom() + 1 == 72 + 280 - TOAST_FOOT
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


def test_after_a_plan_blocks_slide_to_their_places_and_new_ones_fade_in(
    qapp: QApplication, manual_time: ManualTime  # noqa: F811
) -> None:
    hours = Hours(qapp)
    final = hours.settled_picture(LATER)
    hours.canvas.set_week(LATER)
    manual_time.advance(40)
    # 40 of the 180 ms on the out-cubic ease: 1 - (1 - 2/9)^3.
    assert hours.canvas._progress == pytest.approx(1 - (7 / 9) ** 3)
    assert hours.picture() != final, "partway there, not already there"
    manual_time.advance(duration(EASE_MS) - 40)
    assert hours.picture() == final
    hours.window.close()


def first_frame_and_last(qapp: QApplication, level: str) -> tuple[QImage, QImage, QPoint]:
    """The hours the moment a plan moved the essay from Tuesday 9:00, as they end up, and where the
    essay was."""
    apply_ui_effects(level)
    hours = Hours(qapp)
    was = hours.canvas.tracks[1].rect_for(9 * 60, 10 * 60).center().toPoint()
    final = hours.settled_picture(LATER)
    hours.canvas.set_week(LATER)
    first = hours.picture()
    hours.window.close()
    return first, final, was


def test_under_reduce_a_moved_block_fades_in_where_it_went_rather_than_sliding(qapp: QApplication) -> None:
    """The review's motion-sensitive student: fades yes, sliding blocks no."""
    try:
        first, final, was = first_frame_and_last(qapp, "normal")
        assert first.pixelColor(was) != final.pixelColor(was), "Normal starts it where it was"
        first, final, was = first_frame_and_last(qapp, "reduce")
        assert first.pixelColor(was) == final.pixelColor(was), "Reduce never draws it there"
        assert first != final, "but it still fades in"
    finally:
        apply_ui_effects("normal")


def test_laying_the_hours_out_again_where_nothing_moved_keeps_the_slide(
    qapp: QApplication, manual_time: ManualTime  # noqa: F811
) -> None:
    """Decision 34 of 0.17: after Plan the hours scroll to what it placed, and the slide was cut
    short by that scroll's layout, so nothing was seen to move."""
    hours = Hours(qapp)
    final = hours.settled_picture(LATER)
    hours.canvas.set_week(LATER)
    hours.canvas.relayout()
    manual_time.advance(40)
    assert hours.picture() != final, "still on its way"
    manual_time.advance(duration(EASE_MS) - 40)
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
        QVBoxLayout(dialog).addWidget(QLabel("Nothing moves"))
        dialog.show()
        qapp.processEvents()
        assert dialog.windowOpacity() == 1.0
        assert [child for child in dialog.findChildren(QWidget) if child.graphicsEffect()] == []
        dialog.close()
    finally:
        apply_ui_effects("normal")


def test_a_dialog_fades_and_rises_through_its_content_once(
    qapp: QApplication, manual_time: ManualTime  # noqa: F811
) -> None:
    """Decision 31 of 0.17: a window's own opacity is ignored on Wayland, so dialogs appeared in one
    frame there. What the dialog holds fades and rises instead; the window is never faded."""
    apply_ui_effects("normal")
    dialog = Dialog()
    words = QLabel("Are you sure?")
    # Named, as most of a dialog's parts are: a search for unnamed children found none of them.
    words.setObjectName("question")
    QVBoxLayout(dialog).addWidget(words)
    dialog.resize(300, 200)
    dialog.show()
    effect = words.graphicsEffect()
    assert effect is not None and effect.offset == QPoint(0, RISE_PX)
    manual_time.advance(40)
    assert effect.opacity == pytest.approx(1 - (7 / 9) ** 3)
    assert dialog.windowOpacity() == 1.0
    manual_time.advance(duration(EASE_MS) - 40)
    assert words.graphicsEffect() is None
    dialog.hide()
    dialog.show()
    assert words.graphicsEffect() is None, "shown again, it is simply there"
    dialog.close()


def test_a_sheet_fades_its_card_and_shadow_as_one_and_keeps_the_shadow(qapp: QApplication) -> None:
    apply_ui_effects("normal")
    window = QWidget()
    window.resize(900, 700)
    window.show()
    qapp.processEvents()
    sheet = Dialog(window, sheet=True)
    sheet.card_body("Add homework").addWidget(QLabel("Homework"))
    sheet.show()
    qapp.processEvents()
    shadow = sheet.card.graphicsEffect()
    assert isinstance(shadow, QGraphicsDropShadowEffect)
    face = sheet.card.parentWidget()
    assert face is not sheet and face.graphicsEffect() is not None, "the card and its shadow fade together"
    shade = window.findChild(QWidget, "sheetShade")
    assert shade.graphicsEffect() is not None, "the dimming comes in with it"
    QTest.qWait(duration(EASE_MS) + 150)
    assert face.graphicsEffect() is None and shade.graphicsEffect() is None
    assert sheet.card.graphicsEffect() is shadow, "the fade leaves the card's shadow alone"
    sheet.close()
    window.close()


def segments(qapp: QApplication) -> tuple[SegmentTrack, list[Segment]]:
    track = SegmentTrack()
    track.setLayout(QHBoxLayout())
    track.layout().setContentsMargins(0, 0, 0, 0)
    colours = track.palette()
    colours.setColor(QPalette.ColorRole.AlternateBase, QColor("#ffffff"))
    colours.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
    colours.setColor(QPalette.ColorRole.Highlight, QColor("#ff0000"))
    track.setPalette(colours)
    made = []
    for words in ("Day", "Week", "Month"):
        button = Segment(words)
        button.setCheckable(True)
        button.setStyleSheet("background: transparent; border: none; color: #ffffff;")
        track.add(button)
        made.append(button)
    made[0].setChecked(True)
    track.show()
    qapp.processEvents()
    track.grab()
    return track, made


def pill_on(track: SegmentTrack, button: Segment) -> bool:
    """Whether the chosen pill, red here, is drawn under the top middle of `button`, above its words."""
    spot = track.grab().toImage().pixelColor(button.geometry().center().x(), button.geometry().top() + 2)
    return spot.red() > 200 and spot.green() < 80


def test_the_segmented_selection_slides_to_the_segment_chosen(qapp: QApplication) -> None:
    """Decision 32 of 0.17: the view control's selection jumped."""
    apply_ui_effects("normal")
    track, (day, week, month) = segments(qapp)
    assert pill_on(track, day)
    month.setChecked(True)
    day.setChecked(False)
    assert pill_on(track, day) and not pill_on(track, month), "it leaves from where it was"
    # Held a fifth of the way through, where an eased slide is about halfway, rather than timed.
    track._slide.pause()
    track._slide.setCurrentTime(duration(SEGMENT_MS) // 5)
    assert pill_on(track, week), "and passes over the segment between, as no fade would"
    track._slide.resume()
    QTest.qWait(duration(SEGMENT_MS) + 150)
    assert pill_on(track, month) and not pill_on(track, day)
    apply_ui_effects("off")
    day.setChecked(True)
    month.setChecked(False)
    assert pill_on(track, day) and not pill_on(track, month), "with animations off it is simply there"
    apply_ui_effects("normal")
    track.close()


class _Counted(QWidget):
    """A child whose paints can be counted. A page drawn through an effect paints these every frame."""

    def __init__(self) -> None:
        super().__init__()
        self.paints = 0
        self.setMinimumHeight(24)

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        self.paints += 1


def _frames(qapp: QApplication, seconds: float) -> int:
    frames = 0
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        frames += 1
        QTest.qWait(8)
    return frames


def test_a_page_change_does_not_repaint_the_live_page_every_frame(qapp: QApplication) -> None:
    """The page coming in is live at once. Its widgets are painted into one picture for the fade,
    not again on every frame."""
    apply_ui_effects("normal")
    stack = QStackedWidget()
    first = QLabel("Week")
    second = QWidget()
    column = QVBoxLayout(second)
    children = [_Counted() for _ in range(6)]
    for child in children:
        column.addWidget(child)
    stack.addWidget(first)
    stack.addWidget(second)
    stack.resize(400, 300)
    stack.show()
    qapp.processEvents()
    for child in children:
        child.paints = 0
    switch_page(stack, second, "normal")
    frames = _frames(qapp, (duration(PAGE_IN_AFTER_MS + PAGE_IN_MS, "normal") + 80) / 1000)
    assert frames >= 8, "the page change ran for several frames"
    for child in children:
        assert child.paints <= 3, f"a live widget painted {child.paints} times over {frames} frames"
    stack.close()


def test_a_sheet_does_not_repaint_the_page_under_it_every_frame(qapp: QApplication) -> None:
    """The shade covers the window. The page under it stays as it was for the fade, instead of
    being painted again because the shade moved."""
    apply_ui_effects("normal")
    window = QWidget()
    column = QVBoxLayout(window)
    children = [_Counted() for _ in range(6)]
    for child in children:
        column.addWidget(child)
    window.resize(900, 700)
    window.show()
    qapp.processEvents()
    for child in children:
        child.paints = 0
    sheet = Dialog(window, sheet=True)
    sheet.card_body("Add homework").addWidget(QLabel("Homework"))
    sheet.show()
    qapp.processEvents()
    assert all(not child.updatesEnabled() for child in children), "the page under the sheet holds still"
    frames = _frames(qapp, (duration(EASE_MS, "normal") + 80) / 1000)
    assert frames >= 8, "the sheet ran for several frames"
    for child in children:
        assert child.paints <= 4, f"the page painted {child.paints} times over {frames} frames"
    assert within(2, lambda: all(child.updatesEnabled() for child in children))
    sheet.close()
    window.close()


def test_a_page_change_ends_where_motion_off_leaves_it(qapp: QApplication) -> None:
    """The fade is only on the way. Where it ends is the page motion Off shows at once."""

    def landed(level: str) -> QImage:
        apply_ui_effects(level)
        stack, _first, second = two_pages(qapp)
        switch_page(stack, second, level)
        assert within(2, lambda: second.graphicsEffect() is None and pictures(stack) == [])
        assert second.pos() == QPoint(0, 0)
        image = stack.grab().toImage()
        stack.close()
        return image

    try:
        assert landed("normal") == landed("off")
    finally:
        apply_ui_effects("normal")


def test_the_clock_follows_the_screen_and_falls_back_to_60(qapp: QApplication) -> None:
    """Frames follow the screen. An unknown rate is 60, whose interval is 17 ms, never 0."""
    from desktop.native import motion as motion_module

    assert motion_module.frame_interval_ms(180) == round(1000 / 180) == 6
    assert motion_module.frame_interval_ms(360) == 3
    assert motion_module.frame_interval_ms(60) == 17
    assert motion_module.frame_interval_ms(0) == 17
    assert motion_module.frame_interval_ms(-5) == 17
    assert motion_module.frame_interval_ms(59.94) == round(1000 / 59.94)
    apply_ui_effects("normal")
    host = QWidget()
    notice = QLabel("Saved.", host)
    notice.move(10, 10)
    host.resize(200, 80)
    host.show()
    qapp.processEvents()
    appear(notice, "normal")
    clock = notice._motion_running[0]
    rate = notice.screen().refreshRate() if notice.screen() is not None else 0
    assert clock.interval() == motion_module.frame_interval_ms(rate or 0)
    assert clock.interval() >= 1
    host.close()


def test_a_design_picture_waits_while_something_moves(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A picture takes about a tenth of a second, so drawn in the middle of a fade it held that fade
    still for as long (Retro's week to day, 2026-10-08). It waits until nothing moves."""
    from desktop.native import motion as moving
    from desktop.native.layouts import dialog
    from desktop.native.layouts.dialog import DesignPicker

    drawn: list[int] = []

    class Counting:
        def get(self, *_args: object) -> QPixmap:
            drawn.append(1)
            return QPixmap(4, 4)

    monkeypatch.setattr(dialog, "Previews", Counting)
    picker = DesignPicker("plan", "designs", "Design", "slate")
    owner = QWidget()
    owner.resize(40, 40)
    owner.show()
    moving.appear(owner, "normal")
    assert moving.busy()
    picker._draw_next()
    assert drawn == [], "nothing is drawn while the fade runs"
    deadline = time.monotonic() + 3
    while not drawn and time.monotonic() < deadline:
        qapp.processEvents()
    assert not moving.busy()
    assert drawn == [1], "once the fade has ended the picture is drawn"
    for widget in (picker, owner):
        widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_design_pictures_are_drawn_one_a_turn_and_can_be_drawn_ahead(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each design picture takes about a tenth of a second. Chained on a zero timer they become one
    long turn. Ahead of time, while Settings is not on screen, they can all be drawn now."""
    from desktop.native.layouts import dialog
    from desktop.native.layouts.dialog import DesignPicker

    drawn: list[int] = []

    class Counting:
        def get(self, *_args: object) -> QPixmap:
            drawn.append(1)
            return QPixmap(4, 4)

    monkeypatch.setattr(dialog, "Previews", Counting)
    picker = DesignPicker("plan", "designs", "Design", "slate")
    picker._draw_next()
    assert len(drawn) == 1
    qapp.processEvents()
    assert len(drawn) == 1, "the next picture waits until the next turn"
    picker.warm()
    assert len(drawn) == len(picker.cards)
    picker.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_a_page_is_pictured_at_the_size_it_will_have_on_screen(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stacked page grabbed at its old size is drawn once small, then resized and drawn again
    while it fades. The picture is taken after it has the stack's size."""
    from desktop.native import motion as moving

    apply_ui_effects("normal")
    stack = QStackedWidget()
    first = QLabel("Week")
    second = QWidget()
    QVBoxLayout(second).addWidget(QLabel("Day"))
    stack.addWidget(first)
    stack.addWidget(second)
    stack.resize(640, 400)
    stack.show()
    qapp.processEvents()
    stack.setCurrentWidget(second)
    qapp.processEvents()
    # Stale size, as a newly shown view can still have until its layout runs.
    second.resize(80, 40)
    sizes: list[tuple[int, int]] = []
    real = moving._kept

    def spy(widget: QWidget) -> QPixmap | None:
        sizes.append((widget.width(), widget.height()))
        return real(widget)

    monkeypatch.setattr(moving, "_kept", spy)
    appear(second, "normal")
    assert sizes, "the incoming page was pictured"
    assert sizes[0] == (stack.width(), stack.height()), sizes
    stack.close()


def test_typing_during_a_sheet_fade_shows_at_once(qapp: QApplication) -> None:
    """While a sheet fades, the title field already has focus. Letters typed then must show, not
    wait under a still picture until the fade ends."""
    apply_ui_effects("normal")
    window = QWidget()
    window.resize(900, 700)
    window.show()
    qapp.processEvents()
    sheet = Dialog(window, sheet=True)
    field = QLineEdit()
    sheet.card_body("Add homework").addWidget(field)
    sheet.show()
    qapp.processEvents()
    face = sheet._face
    assert face is not None
    effect = face.graphicsEffect()
    assert effect is not None and getattr(effect, "_picture", None) is not None
    field.setFocus()
    QTest.keyClicks(field, "Math")
    assert field.text() == "Math"
    assert getattr(effect, "_picture", "missing") is None, "the still picture gave way so the letters show"
    sheet.close()
    window.close()


@pytest.mark.parametrize("design", ["timeline", "mission", "bento", "retro", "clay", "one", "dial"])
def test_a_design_preview_renders_once_at_its_final_width(qapp, monkeypatch, design):
    from desktop.native import previews
    from desktop.native.layouts.views import VIEW_CLASSES

    apply_ui_effects("off")
    calls = []
    cls = VIEW_CLASSES[design]
    render = cls.render

    def counted(self, scene, changed):
        calls.append(self.width())
        return render(self, scene, changed)

    monkeypatch.setattr(cls, "render", counted)
    previews.render(design, None, "slate", None, 206)
    assert calls == [1280], "a preview must not rebuild after a stale narrow first render"


def test_visible_design_pictures_wait_for_motion_but_not_forever(qapp, monkeypatch):
    from desktop.native import motion
    from desktop.native.layouts import dialog

    picker = dialog.DesignPicker("plan", "designs", "Design", "slate")
    picker.show()
    calls = []
    monkeypatch.setattr(picker, "_draw_one", lambda: calls.append(1) or False)
    monkeypatch.setattr(dialog.QTimer, "singleShot", lambda *_: None)
    owner = QWidget()
    owner.show()
    clock = motion.Clock(owner)
    clock.start(10000, lambda _: None)
    picker._draw_next()
    assert calls == [], "visible previews must wait while a fade runs"
    clock.stop()
    picker._draw_next()
    assert calls == [1], "drawing resumes as soon as motion stops"
    calls.clear()
    clock.start(10000, lambda _: None)
    for _ in range(10):
        picker._draw_next()
        assert calls == [], "ten waits are allowed before drawing through a stuck clock"
    picker._draw_next()
    assert calls == [1]
    clock.stop()
    picker.close()
    owner.close()


def test_paused_stopped_and_hidden_clocks_are_not_busy(qapp):
    from desktop.native import motion

    owner = QWidget()
    owner.show()
    clock = motion.Clock(owner)
    clock.start(10000, lambda _: None)
    assert motion.busy()
    clock.pause()
    assert not motion.busy(), "a paused clock is not moving"
    held = clock.currentTime()
    QTest.qWait(20)
    assert clock.currentTime() == held
    clock.resume()
    assert motion.busy()
    owner.hide()
    assert not motion.busy()
    owner.show()
    assert motion.busy()
    clock.stop()
    assert not motion.busy()
    owner.close()


def test_a_click_in_a_fade_drops_its_picture_but_another_windows_key_does_not(qapp):
    apply_ui_effects("normal")
    owner = QWidget()
    field = QLineEdit(owner)
    owner.resize(200, 80)
    owner.show()
    other = QLineEdit()
    other.show()
    qapp.processEvents()
    appear(owner, "normal")
    effect = owner.graphicsEffect()
    assert effect._picture is not None
    QTest.keyClicks(other, "Elsewhere")
    assert other.text() == "Elsewhere"
    assert effect._picture is not None, "input in another window must not end this picture"
    QTest.mouseClick(field, Qt.MouseButton.LeftButton)
    assert effect._picture is None, "a click inside the fade shows its live contents"
    owner.close()
    other.close()


def test_a_fade_picture_shows_the_week_as_it_looks_after_a_block_is_added(qapp: QApplication) -> None:
    """A reused grab must not keep a picture from before the week changed."""
    apply_ui_effects("normal")
    week = QWidget()
    week.setAutoFillBackground(True)
    palette = week.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#111111"))
    week.setPalette(palette)
    week.resize(200, 120)
    week.show()
    qapp.processEvents()
    stale = hold_picture(week, "normal")
    assert stale is not None
    stale.hide()
    stale.deleteLater()
    qapp.processEvents()
    block = QWidget(week)
    block.setGeometry(24, 24, 48, 48)
    block.setAutoFillBackground(True)
    ink = block.palette()
    ink.setColor(QPalette.ColorRole.Window, QColor("#ff00aa"))
    block.setPalette(ink)
    block.show()
    qapp.processEvents()
    picture = hold_picture(week, "normal")
    assert picture is not None
    sample = picture.pixmap().toImage().pixelColor(48, 48)
    assert sample.name() == "#ff00aa", "the fade shows the block, not the empty week"
    week.close()
