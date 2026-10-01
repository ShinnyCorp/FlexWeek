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
    from PySide6.QtCore import QPoint, QRect, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPalette
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QGraphicsDropShadowEffect,
        QHBoxLayout,
        QLabel,
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
        SLIDE_PX,
        Dim,
        app_level,
        appear,
        apply_ui_effects,
        distance,
        duration,
        glide,
        motion_level,
        moves,
        slide_over,
        switch_page,
    )
    from desktop.native.weekmodel import Occurrence
    from desktop.native.widgets import Dialog, PlanReview, Segment, SegmentTrack


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-motion-test"])


def pictures(host: QWidget) -> list[QLabel]:
    return [label for label in host.findChildren(QLabel, FADE_NAME) if label.isVisible()]


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


def test_a_notice_rises_into_place_and_leaves_no_effect_behind(qapp: QApplication) -> None:
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
    QTest.qWait(duration(EASE_MS, "normal") + 150)
    assert (notice.x(), notice.y()) == (40, 60)
    assert notice.graphicsEffect() is None, "an effect left in place slows every later repaint"
    host.close()


def test_a_page_slides_in_from_the_side_it_is_heading_and_lands_in_place(qapp: QApplication) -> None:
    stack, _first, second = two_pages(qapp)
    switch_page(stack, second, "normal", 1)
    assert stack.currentWidget() is second, "the new page is live before any animation"
    assert second.graphicsEffect().offset == QPoint(24, 0), "going forward, it comes in from the right"
    assert second.pos().isNull(), "painted to the side: the page itself is where clicks find it"
    QTest.qWait(40)
    (old,) = pictures(stack)
    assert old.graphicsEffect().offset.x() < 0, "the old page drifts away to the left"
    QTest.qWait(THROUGH_MS)
    assert second.pos().isNull()
    assert second.graphicsEffect() is None
    assert pictures(stack) == []
    stack.close()


def test_under_reduce_a_page_fades_through_and_moves_nothing(qapp: QApplication) -> None:
    stack, _first, second = two_pages(qapp)
    switch_page(stack, second, "reduce", 1)
    effect = second.graphicsEffect()
    assert effect.offset == QPoint() and effect.opacity == 0, "no slide, and still a fade"
    QTest.qWait(40)
    (old,) = pictures(stack)
    assert old.graphicsEffect().offset == QPoint(), "no drift"
    assert old.graphicsEffect().opacity < 1
    QTest.qWait(THROUGH_MS)
    assert pictures(stack) == [] and second.graphicsEffect() is None
    stack.close()


def test_settings_slides_in_from_the_right_over_the_page_dimmed(qapp: QApplication) -> None:
    """Decision 30 of 0.17: Settings slides in over the week dimmed 20 %, rather than fading over it."""
    stack, first, second = two_pages(qapp)
    slide_over(stack, second, "normal")
    assert stack.currentWidget() is second
    effect = second.graphicsEffect()
    assert effect.offset == QPoint(stack.width(), 0) and effect.opacity == 1, "it starts off the right edge"
    (week,) = pictures(stack)
    kids = stack.children()
    assert kids.index(week) < kids.index(second), "the page it covers stays under it"
    assert len(week.findChildren(Dim)) == 1
    QTest.qWait(duration(OVER_MS, "normal") // 2)
    assert 0 < effect.offset.x() < stack.width()
    assert 0 < week.findChildren(Dim)[0].share < 1, "the page under it is dimming"
    QTest.qWait(duration(OVER_MS, "extra") + 150)
    assert pictures(stack) == [] and second.graphicsEffect() is None
    slide_over(stack, first, "normal", back=True)
    assert stack.currentWidget() is first and first.graphicsEffect() is None, "the page under it is live"
    (leaving,) = pictures(stack)
    assert leaving.graphicsEffect().offset == QPoint(), "it slides away from where it was"
    assert len(stack.findChildren(Dim, options=Qt.FindChildOption.FindDirectChildrenOnly)) == 1
    QTest.qWait(duration(OVER_MS, "extra") + 150)
    assert pictures(stack) == [] and stack.findChildren(Dim) == []
    stack.close()


def test_under_reduce_settings_fades_through_rather_than_over_the_page(qapp: QApplication) -> None:
    stack, _first, second = two_pages(qapp)
    slide_over(stack, second, "reduce")
    effect = second.graphicsEffect()
    assert effect.offset == QPoint() and effect.opacity == 0
    assert stack.findChildren(Dim) == []
    assert within(2, lambda: second.graphicsEffect() is None and pictures(stack) == [])
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
    QTest.qWait(duration(EASE_MS, "extra") + 150)
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
    appear(review, level, grow=True)
    return host, review, below


def test_the_plan_review_opens_down_and_the_page_below_moves_with_it(qapp: QApplication) -> None:
    """The banner joined the column at full height in one frame, shoving the page below it, and only
    then faded in."""
    host, review, below = opening_review(qapp, "normal")
    clock = review._motion_running[0]
    clock.setCurrentTime(duration(EASE_MS, "normal") // 3)
    full = review.sizeHint().height()
    assert 0 <= review.maximumHeight() < full, "part way, its height is on its way up"
    assert review.height() < full
    effect = review.graphicsEffect()
    assert effect is not None and effect.opacity < 1, "it fades in while it grows"
    qapp.processEvents()
    partway = below.y()
    clock.setCurrentTime(duration(EASE_MS, "normal"))
    qapp.processEvents()
    assert review.maximumHeight() == 16777215, "no limit is left for a later resize or a second plan"
    assert review.height() == full
    assert review.graphicsEffect() is None
    assert below.y() > partway, "the page below moves down with it"
    host.close()


def test_the_plan_review_opened_again_before_it_finished_still_ends_free(qapp: QApplication) -> None:
    host, review, _below = opening_review(qapp, "normal")
    review._motion_running[0].setCurrentTime(40)
    appear(review, "normal", grow=True)
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
    QTest.qWait(duration(EASE_MS + 60, "normal") + 200)
    assert marker.geometry() == QRect(10, 200, 3, 24)
    glide(marker, QRect(10, 40, 3, 24), "off")
    assert marker.geometry() == QRect(10, 40, 3, 24), "with animations off it is simply there"
    glide(marker, QRect(10, 90, 3, 24), "reduce")
    assert marker.geometry() == QRect(10, 90, 3, 24), "under Reduce it does not travel either"
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
    QTest.qWait(duration(EASE_MS, "extra") + 150)
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


def test_after_a_plan_blocks_slide_to_their_places_and_new_ones_fade_in(qapp: QApplication) -> None:
    hours = Hours(qapp)
    final = hours.settled_picture(LATER)
    hours.canvas.set_week(LATER)
    QTest.qWait(40)
    assert hours.picture() != final, "partway there, not already there"
    QTest.qWait(duration(EASE_MS) + 150)
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


def test_laying_the_hours_out_again_where_nothing_moved_keeps_the_slide(qapp: QApplication) -> None:
    """Decision 34 of 0.17: after Plan the hours scroll to what it placed, and the slide was cut
    short by that scroll's layout, so nothing was seen to move."""
    hours = Hours(qapp)
    final = hours.settled_picture(LATER)
    hours.canvas.set_week(LATER)
    hours.canvas.relayout()
    QTest.qWait(40)
    assert hours.picture() != final, "still on its way"
    QTest.qWait(duration(EASE_MS) + 150)
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


def test_a_dialog_fades_and_rises_through_its_content_once(qapp: QApplication) -> None:
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
    QTest.qWait(40)
    assert 0 < effect.opacity < 1
    assert dialog.windowOpacity() == 1.0
    QTest.qWait(duration(EASE_MS) + 150)
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
