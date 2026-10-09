"""Hours that zoom and scroll: the level a surface shows, the minute that stays put while it changes,
and the short block that must still move when it is pressed.

These send Qt events, so they prove the rules; the rig (scripts/rig/drive.py) zooms and drags with a
real pointer on the real window.
"""

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
    from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
    from PySide6.QtGui import QColor, QImage, QMouseEvent, QRegion, QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QWidget

    from desktop.native.hours.classic import DAY_SCALE, WEEK_SCALE, ClassicDay, ClassicWeek
    from desktop.native.hours.geometry import Axis
    from desktop.native.hours.hand import Gesture, Hand, Verdict, span_words
    from desktop.native.hours.zoom import Scale, sanitize_zoom
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import build_week

MONDAY = "2026-09-21"
SCHOOL = {
    "id": "school",
    "title": "School",
    "kind": "locked",
    "days": [0],
    "start": "08:00",
    "duration_min": 390,
}
QUARTER = {"id": "quiz", "title": "Quiz", "kind": "locked", "days": [3], "start": "16:00", "duration_min": 15}


# The hosts of the hands these tests make. A hand is its host's Qt child and holds no reference of
# its own to it, so the host has to be kept for as long as the hand is used.
HOSTS: list = []


def a_hand(words: bool = False) -> Hand:
    """A hand that allows everything, saying a held block's times when `words` is set."""
    host = QWidget()
    HOSTS.append(host)
    return Hand(lambda block_id, from_day, span: Verdict(True, span_words(span) if words else ""), host)


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-zoom-test"])


def settle(qapp: QApplication) -> None:
    for _ in range(5):
        qapp.processEvents()


def a_week(qapp: QApplication, blocks: list[dict] | None = None, hand: Hand | None = None) -> ClassicWeek:
    # Inside the offscreen screen (800 by 800), where QApplication.widgetAt can find it.
    view = ClassicWeek(hand if hand is not None else a_hand())
    view.set_look(None, resolved_palette("system", False, None))
    view.set_week(build_week(MONDAY, blocks or [], {}, None), 3, 15 * 60 + 40)
    view.move(0, 0)
    view.resize(760, 520)
    view.show()
    settle(qapp)
    return view


def a_day(qapp: QApplication, blocks: list[dict], day: int) -> ClassicDay:
    view = ClassicDay(a_hand())
    view.set_look(None, resolved_palette("system", False, None))
    view.move(0, 0)
    view.resize(760, 560)
    view.set_day(build_week(MONDAY, blocks, {}, None), day, 3, 15 * 60 + 40)
    view.show()
    settle(qapp)
    return view


def minute_at(view: ClassicWeek | ClassicDay, y: float) -> float:
    """The minute at a height in the hours' viewport."""
    track = view.hours.tracks[0]
    inside = view.scroll.verticalScrollBar().value() + y
    return track.first + (inside - track.area.top()) / track.per_minute()


def wheel(widget: QWidget, at: QPointF, notches: float, ctrl: bool = True) -> None:
    modifiers = Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
    event = QWheelEvent(
        at,
        QPointF(widget.mapToGlobal(at.toPoint())),
        QPoint(),
        QPoint(0, round(120 * notches)),
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)


def test_a_remembered_level_is_read_back_as_one_the_surface_offers() -> None:
    scale = Scale("classic.week", (32, 48, 64), 48)
    assert scale.nearest(64) == 64
    assert scale.nearest(70) == 64, "a level no longer offered is the nearest that is"
    assert scale.nearest(40) == 32, "halfway between two levels is the smaller"
    assert scale.nearest("64") == 48 and scale.nearest(True) == 48 and scale.nearest(None) == 48
    assert scale.step(48, 5) == 64 and scale.step(48, -5) == 32
    assert sanitize_zoom(
        {"classic.week": 64, "classic.day": True, "Bad Key": 64, "bento.week": 9000, "x.y": 7}
    ) == {"classic.week": 64}
    assert sanitize_zoom(["classic.week", 64]) == {}


def test_a_scale_the_look_file_could_not_keep_is_refused_where_it_is_made() -> None:
    """The look file drops a key it does not recognise when it is read, so a scale named that way
    would zoom and then forget, with nothing said."""
    with pytest.raises(ValueError):
        Scale("mission.week2", (32, 48), 48)
    with pytest.raises(ValueError):
        Scale("one_thing.day", (32, 48), 48)
    assert Scale("mission.week", (32, 48), 48).key == "mission.week"


def test_ctrl_and_the_wheel_zoom_about_the_pointer(qapp: QApplication) -> None:
    view = a_week(qapp)
    port = view.scroll.viewport()
    y = port.height() * 0.7
    before = minute_at(view, y)
    wheel(view.hours, QPointF(300, view.scroll.verticalScrollBar().value() + y), 1)
    assert view.scroll.px == 64
    assert abs(minute_at(view, y) - before) <= 1, "the minute under the pointer stayed under it"
    wheel(view.hours, QPointF(300, view.scroll.verticalScrollBar().value() + y), 0.5)
    assert view.scroll.px == 64, "half a notch from a touchpad is not a step yet"
    wheel(view.hours, QPointF(300, view.scroll.verticalScrollBar().value() + y), 0.5)
    assert view.scroll.px == 96, "two half notches are one step"
    wheel(view.hours, QPointF(300, view.scroll.verticalScrollBar().value() + y), -2)
    assert view.scroll.px == 48
    top = view.scroll.verticalScrollBar().value()
    wheel(view.hours, QPointF(300, top + y), -1, ctrl=False)
    assert view.scroll.px == 48, "without Ctrl the wheel only scrolls"


def test_the_buttons_zoom_about_the_middle_and_stop_at_each_end(qapp: QApplication) -> None:
    """The keys are the window's, and test_zoom_keys presses them there; they zoom as these do."""
    view = a_week(qapp)
    middle = view.scroll.viewport().height() / 2
    before = minute_at(view, middle)
    QTest.mouseClick(view.scroll.buttons.into, Qt.MouseButton.LeftButton)
    assert view.scroll.px == 64
    assert abs(minute_at(view, middle) - before) <= 1
    for _ in range(6):
        QTest.mouseClick(view.scroll.buttons.into, Qt.MouseButton.LeftButton)
    assert view.scroll.px == WEEK_SCALE.levels[-1]
    assert not view.scroll.buttons.into.isEnabled() and view.scroll.buttons.out.isEnabled()
    view.scroll.zoom_by(0)
    assert view.scroll.px == WEEK_SCALE.default
    for _ in range(6):
        QTest.mouseClick(view.scroll.buttons.out, Qt.MouseButton.LeftButton)
    assert view.scroll.px == WEEK_SCALE.levels[0]
    assert not view.scroll.buttons.out.isEnabled()


def test_each_zoom_is_reported_once_so_the_window_can_remember_it(qapp: QApplication) -> None:
    view = a_week(qapp)
    said: list[tuple[str, int]] = []
    view.scroll.zoomed.connect(lambda key, px: said.append((key, px)))
    QTest.mouseClick(view.scroll.buttons.into, Qt.MouseButton.LeftButton)
    QTest.mouseClick(view.scroll.buttons.out, Qt.MouseButton.LeftButton)
    view.scroll.restore({"classic.week": 96})
    assert said == [("classic.week", 64), ("classic.week", 48)], "a restored level is not saved again"
    assert view.scroll.px == 96


def test_nothing_zooms_while_a_block_is_held(qapp: QApplication) -> None:
    view = a_week(qapp, [SCHOOL])
    view.scroll.scroll_to(9 * 60)
    press = view.hours.mapFromGlobal(view.hours.point_for(0, 10 * 60))
    QTest.mousePress(view.hours, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, press)
    assert view.hours.hand.busy
    view.scroll.zoom_by(1)
    assert view.scroll.px == WEEK_SCALE.default
    view.hours.hand.cancel()
    QTest.mouseRelease(view.hours, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, press)


def test_a_day_never_draws_fifteen_minutes_under_24_pixels(qapp: QApplication) -> None:
    view = a_day(qapp, [SCHOOL], 0)
    for px in DAY_SCALE.levels:
        view.scroll.restore({"classic.day": px})
        track = view.hours.tracks[0]
        assert track.per_minute() * 15 >= 24, f"15 minutes is {track.per_minute() * 15:.1f} px at {px}"


def press_kind(view: ClassicWeek | ClassicDay, block_id: str, day: int, share: float) -> Gesture:
    """What pressing a drawn block this far along it and moving a little picks up."""
    rect = view.hours.block_rect(block_id, day)
    assert rect is not None, f"{block_id} is not drawn"
    at = QPoint(rect.center().x(), rect.top() + round(rect.height() * share))
    local = QPointF(view.hours.mapFromGlobal(at))
    held = Qt.MouseButton.LeftButton
    for kind, buttons, point in (
        (QEvent.Type.MouseButtonPress, held, local),
        (QEvent.Type.MouseMove, held, local + QPointF(0, 12)),
        (QEvent.Type.MouseMove, held, local + QPointF(0, 24)),
    ):
        global_at = QPointF(view.hours.mapToGlobal(point.toPoint()))
        event = QMouseEvent(kind, point, global_at, held, buttons, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.hours, event)
    preview = view.hours.hand.preview
    view.hours.hand.cancel()
    assert preview is not None, f"pressing {share:.0%} into {block_id} picked nothing up"
    return preview.held.kind


def test_hours_that_grow_twice_while_opening_still_open_where_they_were_asked(qapp: QApplication) -> None:
    """A page still laying out can show the hours taller than they end up, twice over. The bar stops
    short of 10:00 each time it is pulled back by the growing hours; that is not the student
    scrolling, so once the hours are their own height they start at 10:00."""
    view = a_week(qapp)
    view.resize(760, 900)
    settle(qapp)
    view.scroll.scroll_to(10 * 60, above=0)
    settle(qapp)
    view.resize(760, 1100)
    settle(qapp)
    view.resize(760, 520)
    settle(qapp)
    at = minute_at(view, 0)
    assert 9 * 60 + 45 <= at <= 10 * 60 + 15, f"the hours start at {int(at) // 60:02d}:{int(at) % 60:02d}"


@pytest.mark.parametrize("px", WEEK_SCALE.levels)
def test_a_quarter_hour_on_the_week_moves_from_a_quarter_half_and_three_quarters_in(
    qapp: QApplication, px: int
) -> None:
    view = a_week(qapp, [QUARTER])
    view.scroll.restore({"classic.week": px})
    view.scroll.scroll_to(16 * 60)
    settle(qapp)
    for share in (0.25, 0.5, 0.75):
        assert press_kind(view, "quiz", 3, share) is Gesture.MOVE, f"{share:.0%} at {px} px an hour"


@pytest.mark.parametrize("px", DAY_SCALE.levels)
def test_a_quarter_hour_on_the_day_moves_from_a_quarter_half_and_three_quarters_in(
    qapp: QApplication, px: int
) -> None:
    view = a_day(qapp, [QUARTER], 3)
    view.scroll.restore({"classic.day": px})
    view.scroll.scroll_to(16 * 60)
    settle(qapp)
    for share in (0.25, 0.5, 0.75):
        assert press_kind(view, "quiz", 3, share) is Gesture.MOVE, f"{share:.0%} at {px} px an hour"


def test_an_hour_still_resizes_from_its_edges_at_every_level(qapp: QApplication) -> None:
    hour = {**QUARTER, "duration_min": 60}
    view = a_day(qapp, [hour], 3)
    for px in DAY_SCALE.levels:
        view.scroll.restore({"classic.day": px})
        view.scroll.scroll_to(16 * 60)
        settle(qapp)
        assert press_kind(view, "quiz", 3, 0.02) is Gesture.RESIZE_START, f"top edge at {px}"
        assert press_kind(view, "quiz", 3, 0.97) is Gesture.RESIZE_END, f"bottom edge at {px}"


def test_the_day_names_sit_over_their_columns_beside_a_scroll_bar(qapp: QApplication) -> None:
    view = a_week(qapp)
    assert view.scroll.verticalScrollBar().isVisible()
    for day in range(7):
        name = view.findChild(QWidget, f"weekDayName{day}")
        track = view.hours.track_for(day)
        assert name is not None and track is not None
        over = name.mapToGlobal(name.rect().center()).x()
        column = view.hours.mapToGlobal(track.area.center().toPoint()).x()
        assert abs(over - column) <= 1, f"{name.text()} is {over - column} px off its column"


def test_a_week_keeps_where_it_was_scrolled_when_it_is_shown_again(qapp: QApplication) -> None:
    view = a_week(qapp)
    bar = view.scroll.verticalScrollBar()
    view.set_week(build_week("2026-09-28", [], {}, None), None, None)
    opened_at = bar.value()
    bar.setValue(bar.maximum())
    view.hide()
    view.set_week(build_week("2026-09-28", [SCHOOL], {}, None), None, None)
    view.show()
    settle(qapp)
    assert opened_at != bar.maximum()
    assert bar.value() == bar.maximum(), "the same week jumped back to the morning"
    view.hide()
    other = build_week("2026-10-05", [], {}, None)
    view.set_week(other, 2, 12 * 60)
    view.set_week(other, 2, 12 * 60)
    view.show()
    settle(qapp)
    top, bottom = minute_at(view, 0), minute_at(view, view.scroll.viewport().height())
    assert abs((top + bottom) / 2 - 12 * 60) <= 2, "a hidden refresh lost the opening time"


def test_the_same_week_rendered_again_keeps_now_in_the_middle_while_the_page_settles(
    qapp: QApplication,
) -> None:
    """A save or a tick of the clock renders the week again. Opened with now in the middle, it keeps now
    there as the page settles, as a new look's taller header makes it, until the student scrolls."""
    view = a_week(qapp)
    view.set_week(build_week(MONDAY, [], {}, None), 3, 15 * 60 + 41)
    view.resize(760, 640)
    settle(qapp)
    top, bottom = minute_at(view, 0), minute_at(view, view.scroll.viewport().height())
    assert abs((top + bottom) / 2 - (15 * 60 + 40)) <= 2


def test_hours_cut_short_for_a_moment_go_back_to_where_they_were(qapp: QApplication) -> None:
    """A page laying itself out can give the hours a little less to scroll for a moment. The bar is
    cut back to that end, and once the room returns the hours are where the student left them."""
    view = a_week(qapp)
    bar = view.scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    end = bar.value()
    view.resize(760, 560)
    settle(qapp)
    assert bar.value() < end, "taller for a moment, the hours had less to scroll"
    view.resize(760, 520)
    settle(qapp)
    assert bar.value() == end


def test_y_for_is_safe_when_the_canvas_has_no_tracks(qapp: QApplication) -> None:
    """Clay's card slide can leave a kept centre while `_lay_out_now` clears the tracks; `_y_for` must
    not index an empty list (often seen as IndexError from `viewportEvent`)."""
    view = hours_placed_by_hand(qapp)
    scroll = view.scroll
    scroll.setGeometry(0, 0, 40, 520)
    settle(qapp)
    assert not scroll.canvas.tracks
    assert scroll._y_for(8 * 60) == 0.0

    scroll.setGeometry(0, 0, 760, 520)
    settle(qapp)
    scroll.scroll_to(10 * 60)
    bar = scroll.verticalScrollBar()
    scroll._placed = bar.value()
    scroll.setGeometry(0, 0, 40, 520)
    if scroll.canvas.tracks:
        scroll._keep_centre()
    QApplication.sendEvent(scroll.viewport(), QEvent(QEvent.Type.Resize))
    settle(qapp)


def test_a_time_asked_for_while_the_hours_have_no_room_is_shown_once_they_do(qapp: QApplication) -> None:
    """Clay deck's open card slides in from a narrow neighbour, and for a moment its hours have no width
    at all. A time asked for then waited for the hours to be shown again, which never came, and the
    day opened at the wrong hour.

    The hours are placed by hand, as Clay's row places its card's, not by the week's layout: the
    layout keeps them at least as wide as their gutter and a scroll bar, and whether that bar takes
    room depends on the app's style, which a window made by an earlier test leaves installed."""
    view = a_week(qapp)
    scroll = view.scroll
    view.layout().removeWidget(scroll)
    scroll.setGeometry(0, 0, 760, 520)
    scroll.scroll_to(8 * 60, above=0)
    settle(qapp)
    scroll.setGeometry(0, 0, 40, 520)
    settle(qapp)
    assert not view.hours.tracks, "no room for the hours"
    scroll.scroll_to(11 * 60, above=0)
    scroll.setGeometry(0, 0, 760, 520)
    settle(qapp)
    assert abs(minute_at(view, 0) - 11 * 60) <= 1


def hours_placed_by_hand(qapp: QApplication) -> ClassicWeek:
    """A week whose hours are placed by hand, as Clay's row places its card's, so they can be given no
    width at all (see the test above for why the week's own layout cannot)."""
    view = a_week(qapp)
    view.layout().removeWidget(view.scroll)
    view.scroll.setGeometry(0, 0, 760, 520)
    settle(qapp)
    return view


def test_a_week_left_while_its_hours_have_no_room_is_where_it_was_when_it_is_shown_again(
    qapp: QApplication,
) -> None:
    """Clay deck's card for another day slides in with no width for its hours, and the day being left
    is only then told apart from the new one. Where it was scrolled to is still remembered."""
    view = hours_placed_by_hand(qapp)
    scroll = view.scroll
    scroll.scroll_to(5 * 60, above=0)
    assert abs(minute_at(view, 0) - 5 * 60) <= 1
    scroll.setGeometry(0, 0, 40, 520)
    settle(qapp)
    assert not view.hours.tracks, "no room for the hours"
    view.set_week(build_week("2026-09-28", [], {}, None), None, None)
    scroll.setGeometry(0, 0, 760, 520)
    settle(qapp)
    assert abs(minute_at(view, 0) - (8 * 60 - 90)) <= 1, "an empty week opens an hour and a half above 08:00"
    view.set_week(build_week(MONDAY, [], {}, None), 3, 15 * 60 + 40)
    settle(qapp)
    assert abs(minute_at(view, 0) - 5 * 60) <= 1


def test_a_week_gone_back_to_while_its_hours_have_no_room_is_put_where_it_was_once_they_do(
    qapp: QApplication,
) -> None:
    view = hours_placed_by_hand(qapp)
    scroll = view.scroll
    scroll.scroll_to(5 * 60, above=0)
    view.set_week(build_week("2026-09-28", [], {}, None), None, None)
    settle(qapp)
    assert abs(minute_at(view, 0) - (8 * 60 - 90)) <= 1
    scroll.setGeometry(0, 0, 40, 520)
    settle(qapp)
    assert not view.hours.tracks, "no room for the hours"
    view.set_week(build_week(MONDAY, [], {}, None), 3, 15 * 60 + 40)
    scroll.setGeometry(0, 0, 760, 520)
    settle(qapp)
    assert abs(minute_at(view, 0) - 5 * 60) <= 1


def test_a_week_scrolled_while_its_hours_waited_for_room_is_left_where_it_was_scrolled_to(
    qapp: QApplication,
) -> None:
    """Hours cut short keep where they were until the room returns. Scrolled meanwhile, that is where
    the student left them, not the place they were waiting to go back to."""
    view = a_week(qapp)
    bar = view.scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    view.resize(760, 560)
    settle(qapp)
    bar.setValue(bar.value() - 40)
    left = minute_at(view, 0)
    view.set_week(build_week("2026-09-28", [], {}, None), None, None)
    settle(qapp)
    assert abs(minute_at(view, 0) - (8 * 60 - 90)) <= 1
    view.set_week(build_week(MONDAY, [], {}, None), 3, 15 * 60 + 40)
    settle(qapp)
    assert abs(minute_at(view, 0) - left) <= 1


def test_a_week_asked_for_and_never_shown_has_no_place_to_go_back_to(qapp: QApplication) -> None:
    """Day's hours are given every day the student picks while Week is on screen. A day they never saw
    opens as a first sight of it does, not wherever the hidden hours happened to lie."""
    view = a_week(qapp)
    view.hide()
    unseen = build_week("2026-09-28", [], {}, None)
    view.set_week(unseen, 2, 12 * 60)
    view.set_week(build_week("2026-10-05", [], {}, None), None, None)
    view.set_week(unseen, 2, 12 * 60)
    view.show()
    settle(qapp)
    top, bottom = minute_at(view, 0), minute_at(view, view.scroll.viewport().height())
    assert abs((top + bottom) / 2 - 12 * 60) <= 2


def test_a_week_opened_while_hidden_scrolls_to_now_when_it_is_shown(qapp: QApplication) -> None:
    view = a_week(qapp)
    view.hide()
    view.scroll.verticalScrollBar().setValue(0)
    view.set_week(build_week("2026-10-05", [], {}, None), 2, 12 * 60)
    view.show()
    settle(qapp)
    top, bottom = minute_at(view, 0), minute_at(view, view.scroll.viewport().height())
    assert abs((top + bottom) / 2 - 12 * 60) <= 2, "a new week opens with now in the middle"


def dark_in(image: QImage, strip: QRect, left: int) -> int:
    return sum(
        1
        for y in range(strip.top(), strip.bottom())
        for x in range(left, left + 60)
        if QColor(image.pixel(x, y)).lightness() < 90
    )


def test_a_small_repaint_does_not_write_a_long_blocks_name_again(qapp: QApplication) -> None:
    """The name of a block taller than the screen is kept in sight at the top of what shows. A repaint
    of a strip in its middle, as when a message over it goes away, must not write it there too."""
    view = a_day(qapp, [SCHOOL], 0)
    hours = view.hours
    track = hours.track_for(0)
    assert track is not None
    top, bottom = round(track.point_for(8 * 60).y()), round(track.point_for(14 * 60 + 30).y())
    view.scroll.verticalScrollBar().setValue(top - 20)
    strip = QRect(0, (top + bottom) // 2, hours.width(), 40)
    image = QImage(hours.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    hours.render(image, strip.topLeft(), QRegion(strip))
    assert dark_in(image, strip, round(track.area.left()) + 8) == 0


def a_lane_week(qapp: QApplication, hand: Hand | None = None):
    """Seven lanes whose time runs across, as Mission control's week lays them out, with their names
    kept in a strip on the left."""
    from PySide6.QtCore import QRectF
    from PySide6.QtWidgets import QLabel, QVBoxLayout

    from desktop.native.hours.canvas import BlockPainter, HoursCanvas
    from desktop.native.hours.geometry import Axis, LinearTrack
    from desktop.native.hours.zoom import HoursScroll

    def lanes(area: QRectF) -> list[LinearTrack]:
        tall = area.height() / 7
        return [
            LinearTrack(
                day, QRectF(area.left() + 8, area.top() + day * tall, area.width() - 16, tall), Axis.ACROSS
            )
            for day in range(7)
        ]

    hand = hand if hand is not None else a_hand()
    canvas = HoursCanvas(hand, BlockPainter(resolved_palette("system", False, None)), lanes, header=24)
    scroll = HoursScroll(
        canvas,
        Scale("lanes.week", (32, 48, 64, 96), 48),
        lambda px: 24 * px + 16,
        name="lanes",
        gutter=70,
        axis=Axis.ACROSS,
    )
    names = QWidget()
    column = QVBoxLayout(names)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(0)
    for day in range(7):
        label = QLabel(f"Day {day}")
        label.setObjectName(f"laneName{day}")
        column.addWidget(label, 1)
    scroll.set_header(names)
    scroll.move(0, 0)
    scroll.resize(760, 420)
    scroll.show()
    settle(qapp)
    return scroll


def minute_across(scroll, x: float) -> float:
    track = scroll.canvas.tracks[0]
    return track.first + (scroll.horizontalScrollBar().value() + x - track.area.left()) / track.per_minute()


def test_lanes_zoom_about_the_pointer_and_the_plain_wheel_moves_them_through_the_day(
    qapp: QApplication,
) -> None:
    scroll = a_lane_week(qapp)
    assert scroll.verticalScrollBar().maximum() == 0, "the lanes fit the height; only time scrolls"
    x = scroll.viewport().width() * 0.6
    before = minute_across(scroll, x)
    wheel(scroll.canvas, QPointF(scroll.horizontalScrollBar().value() + x, 100), 1)
    assert scroll.px == 64
    assert abs(minute_across(scroll, x) - before) <= 1, "the minute under the pointer stayed under it"
    at = scroll.horizontalScrollBar().value()
    # A real wheel passes from the canvas, which leaves it, to the viewport; a sent one stops where
    # it is sent, so it goes where a real one arrives.
    wheel(scroll.viewport(), QPointF(x, 100), -1, ctrl=False)
    assert scroll.px == 64
    assert scroll.horizontalScrollBar().value() > at, "the wheel moved the lanes on through the day"


def test_lane_names_stay_beside_their_lanes_while_the_hours_scroll(qapp: QApplication) -> None:
    scroll = a_lane_week(qapp)
    scroll.scroll_to(6 * 60, above=0)
    settle(qapp)
    for day in range(7):
        name = scroll.findChild(QWidget, f"laneName{day}")
        lane = scroll.canvas.track_for(day)
        beside = name.mapToGlobal(name.rect().center()).y()
        middle = scroll.canvas.mapToGlobal(lane.area.center().toPoint()).y()
        assert abs(beside - middle) <= 2, f"day {day}'s name is {beside - middle} px off its lane"
        assert name.mapToGlobal(name.rect().topLeft()).x() == scroll.mapToGlobal(scroll.rect().topLeft()).x()
    assert 5 * 60 + 45 <= minute_across(scroll, 0) <= 6 * 60 + 15, "06:00 is at the left"


def test_both_ends_of_a_lanes_day_can_be_reached(qapp: QApplication) -> None:
    scroll = a_lane_week(qapp)
    for level in scroll.scale.levels:
        scroll.restore({"lanes.week": level})
        scroll.canvas.reveal(3, 0, 60)
        settle(qapp)
        assert scroll.canvas.in_view(3, 0), f"00:00 at {level} px an hour"
        scroll.canvas.reveal(3, 23 * 60, 24 * 60)
        settle(qapp)
        assert scroll.canvas.in_view(3, 24 * 60), f"24:00 at {level} px an hour"


def test_a_long_blocks_name_stays_in_sight_on_lanes_scrolled_past_its_start(qapp: QApplication) -> None:
    """As on a column scrolled past a long block's top: School runs 08:00 to 14:30 and the lanes are
    scrolled to 12:00, so its name is written at the left of what shows, not at its start off screen."""
    scroll = a_lane_week(qapp)
    scroll.canvas.set_week(build_week(MONDAY, [SCHOOL], {}, None).occurrences)
    scroll.scroll_to(12 * 60, above=0)
    settle(qapp)
    port = scroll.viewport()
    box = scroll.canvas.block_rect("school", 0)
    assert box is not None
    block = QRect(port.mapFromGlobal(box.topLeft()), box.size())
    assert block.left() < 0 < block.right(), "School's start is scrolled away and its end shows"
    image = port.grab().toImage()
    inked = [
        x
        for x in range(0, 60)
        for y in range(block.top() + 4, block.bottom() - 4)
        if QColor(image.pixel(x, y)).lightness() < 90
    ]
    assert inked, "School's bar shows no name in what shows"
    assert min(inked) <= 8, f"School's name starts {min(inked)} px into what shows"


def a_side(host: QWidget) -> QWidget:
    """A panel beside the hours, with something to take the focus, as Mission's radar."""
    from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout

    side = QFrame(host)
    side.setFixedWidth(300)
    QVBoxLayout(side).addWidget(QPushButton("Science poster", side))
    return side


@pytest.mark.parametrize("new_side", [False, True])
def test_lanes_keep_their_time_when_a_design_parks_them_between_renders(
    qapp: QApplication, new_side: bool
) -> None:
    """Mission keeps its hours between renders and parks them on each one: hidden, out of its layout,
    back in, shown. The canvas still has the focus from the drag just finished, and hiding a scroll
    area that holds the focus moves it on and scrolls the hours to their middle. Mission also builds
    a new panel beside them on each render, which Qt shows only after the hours, so they are shown
    wider than they end up, too wide for 19:00 to be at the left. They must come back where they
    were, so the block just moved is still on screen."""
    from PySide6.QtWidgets import QHBoxLayout

    scroll = a_lane_week(qapp)
    host = QWidget()
    HOSTS.append(host)
    row = QHBoxLayout(host)
    row.addWidget(scroll, 1)
    side = a_side(host)
    row.addWidget(side)
    host.move(0, 0)
    host.resize(800, 480)
    host.show()
    settle(qapp)
    scroll.restore({"lanes.week": 96})
    scroll.scroll_to(19 * 60, above=0)
    host.activateWindow()
    assert QTest.qWaitForWindowActive(host)
    scroll.canvas.setFocus(Qt.FocusReason.MouseFocusReason)
    settle(qapp)
    assert QApplication.focusWidget() is scroll.canvas
    assert 18 * 60 + 45 <= minute_across(scroll, 0) <= 19 * 60 + 15, "19:00 is at the left"
    width = scroll.viewport().width()
    scroll.hide()
    row.removeWidget(scroll)
    if new_side:
        row.removeWidget(side)
        side.deleteLater()
        side = a_side(host)
    row.insertWidget(0, scroll, 1)
    if new_side:
        row.addWidget(side)
    scroll.show()
    settle(qapp)
    assert scroll.viewport().width() == width
    at = minute_across(scroll, 0)
    assert 18 * 60 + 45 <= at <= 19 * 60 + 15, (
        f"the lanes came back at {int(at) // 60:02d}:{int(at) % 60:02d}"
    )


ESSAY = {"id": "essay", "title": "Essay", "kind": "locked", "days": [3], "start": "19:00", "duration_min": 90}


def hold_still(canvas, day: int, minute: int) -> None:
    """Press the block at this day and minute and carry it a little across its time, so it is held
    where it is drawn."""
    press = QPointF(canvas.mapFromGlobal(canvas.point_for(day, minute)))
    across = QPointF(0, 1) if canvas.track_for(day).axis is Axis.ACROSS else QPointF(1, 0)
    held = Qt.MouseButton.LeftButton
    for kind, point in (
        (QEvent.Type.MouseButtonPress, press),
        (QEvent.Type.MouseMove, press + across * 6),
        (QEvent.Type.MouseMove, press + across * 12),
    ):
        global_at = QPointF(canvas.mapToGlobal(point.toPoint()))
        event = QMouseEvent(kind, point, global_at, held, held, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(canvas, event)
    assert canvas.hand.preview is not None, f"nothing was picked up on day {day} at minute {minute}"


def pill_box(canvas) -> QRect:
    """Where the held block's words are drawn on a pill beside it, in the canvas: everything in the
    accent colour outside the held block, whose own outline is that colour."""
    accent = QColor(resolved_palette("system", False, None)["accent"])
    held = next(
        track.transform.mapRect(rect).toAlignedRect().adjusted(-2, -2, 2, 2)
        for track in canvas.tracks
        for drawn, rect in canvas.drawn(track)
        if drawn.held
    )
    image = canvas.grab().toImage()
    box = QRect()
    for y in range(image.height()):
        for x in range(image.width()):
            colour = QColor(image.pixel(x, y))
            near = max(
                abs(colour.red() - accent.red()),
                abs(colour.green() - accent.green()),
                abs(colour.blue() - accent.blue()),
            )
            if near <= 6 and not held.contains(x, y):
                box = box.united(QRect(x, y, 1, 1))
    return box


def shown(canvas, scroll) -> QRect:
    """What shows of the canvas: the viewport, in the canvas's coordinates."""
    port = scroll.viewport()
    return QRect(canvas.mapFrom(port, QPoint(0, 0)), port.size())


def test_a_held_blocks_words_stay_in_what_shows_on_lanes(qapp: QApplication) -> None:
    """Lanes are a whole day wide. The essay, held near the right edge of what shows, has its times on
    a pill that fits there, not one running off past the edge of the viewport."""
    scroll = a_lane_week(qapp, a_hand(words=True))
    canvas = scroll.canvas
    canvas.set_week(build_week(MONDAY, [ESSAY], {}, None).occurrences)
    end = canvas.track_for(3).point_for(20 * 60 + 30).x()
    scroll.horizontalScrollBar().setValue(round(end + 30 - scroll.viewport().width()))
    settle(qapp)
    view = shown(canvas, scroll)
    assert 0 < view.right() - end <= 40, "the essay ends just inside the right edge of what shows"
    hold_still(canvas, 3, 19 * 60 + 45)
    pill = pill_box(canvas)
    canvas.hand.cancel()
    assert not pill.isEmpty(), "no words were drawn beside the held essay"
    assert view.contains(pill), (
        f"the pill spans x {pill.left()}–{pill.right()}; what shows is x {view.left()}–{view.right()}"
    )


def test_a_held_blocks_words_stay_in_what_shows_on_a_column_scrolled_past_its_start(
    qapp: QApplication,
) -> None:
    """School, held by its end with its start scrolled away above, has its times on a pill in what
    shows, not beside its start off the top of the viewport."""
    view = a_week(qapp, [SCHOOL], a_hand(words=True))
    view.scroll.scroll_to(12 * 60, above=0)
    settle(qapp)
    canvas = view.hours
    seen = shown(canvas, view.scroll)
    assert canvas.track_for(0).point_for(8 * 60).y() < seen.top(), "School's start is scrolled away"
    hold_still(canvas, 0, 14 * 60)
    pill = pill_box(canvas)
    canvas.hand.cancel()
    assert not pill.isEmpty(), "no words were drawn beside the held School"
    assert seen.contains(pill), (
        f"the pill spans y {pill.top()}–{pill.bottom()}; what shows is y {seen.top()}–{seen.bottom()}"
    )


def test_tab_moves_the_focus_on_and_leaves_the_hours_where_they_are(qapp: QApplication) -> None:
    """A scroll area shows the child that had the focus when the focus moves on, which for hours
    longer than what shows means jumping to their middle. Tab must only move the focus."""
    from PySide6.QtWidgets import QHBoxLayout

    scroll = a_lane_week(qapp)
    host = QWidget()
    HOSTS.append(host)
    row = QHBoxLayout(host)
    row.addWidget(scroll, 1)
    side = a_side(host)
    row.addWidget(side)
    host.move(0, 0)
    host.resize(800, 480)
    host.show()
    settle(qapp)
    scroll.restore({"lanes.week": 96})
    scroll.scroll_to(19 * 60, above=0)
    host.activateWindow()
    assert QTest.qWaitForWindowActive(host)
    scroll.canvas.setFocus(Qt.FocusReason.MouseFocusReason)
    settle(qapp)
    QTest.keyClick(scroll.canvas, Qt.Key.Key_Tab)
    settle(qapp)
    at = minute_across(scroll, 0)
    assert 18 * 60 + 45 <= at <= 19 * 60 + 15, (
        f"after Tab the lanes start at {int(at) // 60:02d}:{int(at) % 60:02d}"
    )
    assert QApplication.focusWidget() is not scroll.canvas, "Tab left the focus on the hours"


def test_resting_at_the_edge_of_the_page_around_the_lanes_scrolls_the_page(qapp: QApplication) -> None:
    """Lanes that scroll sideways on a page that scrolls down when the window is short, as 0.16's
    Timeline laid its week out. Resting at the page's bottom edge over the lanes scrolls the page,
    which the lanes cannot, so a block can be carried to a day below the fold; resting at the lanes'
    right edge still scrolls the lanes."""
    import time

    from PySide6.QtWidgets import QScrollArea, QVBoxLayout

    scroll = a_lane_week(qapp)
    scroll.canvas.set_week(
        build_week(MONDAY, [{**ESSAY, "days": [1], "start": "10:00"}], {}, None).occurrences
    )
    content = QWidget()
    column = QVBoxLayout(content)
    column.setContentsMargins(0, 0, 0, 0)
    column.addWidget(scroll)
    scroll.setFixedHeight(420)
    page = QScrollArea()
    HOSTS.append(page)
    page.setWidgetResizable(True)
    page.setWidget(content)
    page.move(0, 0)
    page.resize(760, 250)
    page.show()
    settle(qapp)
    scroll.scroll_to(10 * 60)
    settle(qapp)
    down, across = page.verticalScrollBar(), scroll.horizontalScrollBar()
    assert down.maximum() > 0 and down.value() == 0, "the page is too short for the lanes"
    assert 0 < across.value() < across.maximum(), "the lanes can scroll on through the day"

    canvas = scroll.canvas
    held = Qt.MouseButton.LeftButton

    def send(kind: QEvent.Type, at: QPoint) -> None:
        event = QMouseEvent(
            kind, QPointF(canvas.mapFromGlobal(at)), QPointF(at), held, held, Qt.KeyboardModifier.NoModifier
        )
        QApplication.sendEvent(canvas, event)

    def rest(at: QPoint, moved) -> None:
        send(QEvent.Type.MouseMove, at)
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and not moved():
            qapp.processEvents()

    start = canvas.point_for(1, 10 * 60 + 30)
    send(QEvent.Type.MouseButtonPress, start)
    send(QEvent.Type.MouseMove, start + QPoint(20, 0))
    assert canvas.hand.preview is not None, "the essay was not picked up"
    middle = scroll.viewport().width() // 2
    bottom = page.viewport().mapToGlobal(QPoint(0, page.viewport().height() - 10)).y()
    rest(QPoint(scroll.viewport().mapToGlobal(QPoint(middle, 0)).x(), bottom), lambda: down.value() > 0)
    assert down.value() > 0, "rested at the page's bottom edge over the lanes: the page scrolls down"

    port = page.viewport()
    right = scroll.viewport().mapToGlobal(QPoint(scroll.viewport().width() - 10, 0)).x()
    was = across.value()
    rest(QPoint(right, port.mapToGlobal(QPoint(0, port.height() // 2)).y()), lambda: across.value() > was)
    assert across.value() > was, "rested at the lanes' right edge: the lanes scroll on"
    send(QEvent.Type.MouseButtonRelease, start)
    canvas.hand.cancel()


def test_after_a_plan_the_hours_ease_to_homework_off_screen_and_stay_for_homework_on_it(
    qapp: QApplication,
) -> None:
    """Grok Bot's 0.17.0 audit (T7): after Plan the grid jumped, even to homework already in sight."""
    from PySide6.QtTest import QTest

    scroll = a_lane_week(qapp)
    # About seven hours show, so 17:00 is off screen from 09:00.
    scroll.resize(400, 420)
    settle(qapp)
    bar = scroll.horizontalScrollBar()
    scroll.scroll_to(9 * 60, above=0)
    settle(qapp)
    at_nine = bar.value()
    scroll.reveal(11 * 60, 60, "normal")
    QTest.qWait(400)
    assert bar.value() == at_nine, "11:00 already shows: nothing moves"
    scroll.reveal(17 * 60, 60, "normal")
    assert bar.value() == at_nine, "it starts from where it was"
    QTest.qWait(400)
    assert abs(minute_across(scroll, 0) - 16 * 60) <= 1, "and eases to an hour before 17:00"
    scroll.scroll_to(9 * 60, above=0)
    settle(qapp)
    scroll.reveal(17 * 60, 60, "reduce")
    assert abs(minute_across(scroll, 0) - 16 * 60) <= 1, "under Reduce it goes at once"
