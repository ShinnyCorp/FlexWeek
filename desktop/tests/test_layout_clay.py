"""Clay deck is a row of cards, one day in front (0.17's Card carousel), all of them live hours on the
window's hand."""

from __future__ import annotations

import importlib.util
import os
import time
from collections.abc import Iterator

import pytest

from desktop.tests.test_weekmodel import BLOCKS, HOMEWORK, TRACE, WEEK, block

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QAbstractAnimation, QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt
    from PySide6.QtGui import QColor, QCursor, QFont, QFontMetricsF, QImage, QPainter
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget
    from shiboken6 import isValid

    from desktop.native import motion
    from desktop.native.hours import canvas as canvas_module
    from desktop.native.hours.canvas import Drawn, HoursCanvas
    from desktop.native.hours.geometry import Span
    from desktop.native.hours.zoom import HoursScroll
    from desktop.native.layouts.base import Scene
    from desktop.native.layouts.clay import Card, ClayChip, ClayDeckView, ClayPainter, Fade, slots
    from desktop.native.layouts.registry import options_for, tokens_for
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import build_week, clock_label, minute_of


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-clay-test"])
    yield application


@pytest.fixture(autouse=True)
def still() -> Iterator[None]:
    """The row where each move ends, unless a test asks for motion; the level is put back after."""
    was = motion.app_level()
    motion.apply_ui_effects("off")
    yield
    motion.apply_ui_effects(was)


def shown(
    qapp: QApplication,
    *,
    tab: str = "week",
    day: int = 3,
    blocks: list[dict] | None = None,
    pack: str = "light-frost",
    **chosen: str,
) -> ClayDeckView:
    options = {**options_for(None, "clay"), **chosen}
    palette = resolved_palette(pack, False, None, "default")
    week = build_week(WEEK, BLOCKS if blocks is None else blocks, HOMEWORK, TRACE)
    view = ClayDeckView()
    view.resize(1280, 764)
    view.show_week(Scene(
        week, 3, minute_of("13:40"), options,
        tokens_for("clay", options["colour"], palette),
        surface=tab, iso_day=week.date_of(day).isoformat(),
    ))
    view.show()
    qapp.processEvents()
    return view


def again(qapp: QApplication, view: ClayDeckView, **changed: object) -> None:
    previous = view.scene
    fields = {
        "week": previous.week, "today": previous.today, "minute": previous.minute,
        "options": previous.options, "tokens": previous.tokens, "surface": previous.surface,
        "iso_day": previous.iso_day, **changed,
    }
    view.show_week(Scene(**fields))
    qapp.processEvents()


def front(view: ClayDeckView) -> HoursCanvas:
    surfaces = view.hours_surfaces()
    assert isinstance(surfaces[0], HoursCanvas)
    return surfaces[0]


def visible_scrolls(view: ClayDeckView) -> list[HoursScroll]:
    return [scroll for scroll in view.findChildren(HoursScroll) if scroll.isVisible()]


def pairs(view: ClayDeckView) -> list[tuple[str, str]]:
    summary = view.findChild(QWidget, "claySummary")
    names = [item.text() for item in summary.findChildren(QLabel, "claySumName")]
    values = [item.text() for item in summary.findChildren(QLabel, "claySumLength")]
    return list(zip(names, values, strict=True))


def wheel(target: QWidget, notch: int) -> None:
    """One notch of the wheel over the middle of `target`, away from the student (1) or toward (-1),
    arriving at the window as a real one does. Qt passes a wheel that a widget ignores on to its
    parents only when it came from the system, so one sent to `target` alone never reached the row."""
    window = target.window()
    at = target.mapTo(window, target.rect().center())
    QTest.wheelEvent(window.windowHandle(), QPointF(at), QPoint(0, 120 * notch))


def rest(qapp: QApplication, seconds: float) -> None:
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        qapp.processEvents()
        time.sleep(0.01)


def drag(target: QWidget, start: QPoint, by: QPoint, *, let_go: bool = True) -> None:
    """Press at `start` on `target` and travel `by` in six moves, as a hand does, then let go unless
    asked not to. Aimed at points fixed in the window, as a real pointer's are, though the row moves
    the card under it; QTest sends each to `target`, the widget a real press would keep."""
    window = target.window()
    at = target.mapTo(window, start)
    QTest.mousePress(target, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    for step in range(1, 7):
        on = at + QPoint(round(by.x() * step / 6), round(by.y() * step / 6))
        QTest.mouseMove(target, target.mapFrom(window, on))
    if let_go:
        let_go_at(target, at + by)


def let_go_at(target: QWidget, at: QPoint) -> None:
    """Let go of `target` at a point in its window."""
    local = target.mapFrom(target.window(), at)
    QTest.mouseRelease(target, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, local)


def card_of(view: ClayDeckView, day: int) -> QWidget:
    return view.findChild(HoursCanvas, f"clayPeek{day}").parentWidget()


def at_slots(view: ClayDeckView, day: int) -> bool:
    """Whether every neighbour is where the row puts it with `day` in front: nothing left mid-drag."""
    row = view.row
    found = slots(row.width(), row.height(), day, row.scale, wide=row._open)
    return all(card_of(view, other).geometry() == found[other].toRect() for other in range(7) if other != day)


def test_the_day_in_front_is_the_one_hours_that_scroll_and_zoom_and_its_neighbours_are_live(
    qapp: QApplication,
) -> None:
    view = shown(qapp)
    assert [scroll.objectName() for scroll in visible_scrolls(view)] == ["clayWeekScroll"]
    hours = front(view)
    assert hours.parentWidget() is visible_scrolls(view)[0].viewport()
    assert [(track.day, track.first, track.last) for track in hours.tracks] == [(3, 0, 1440)]
    assert hours.block_rect("essay-1", 3) is not None
    days = [track.day for surface in view.hours_surfaces() for track in surface.tracks]
    assert days == [3, 0, 1, 2, 4, 5, 6]
    assert all(surface.hand is view.hand for surface in view.hours_surfaces())


def test_neighbours_show_the_stretch_the_day_in_front_opened_at_and_stay_still_while_it_scrolls(
    qapp: QApplication,
) -> None:
    """J10: scrolling the card in front scrolled its neighbours with it. They keep the stretch the day
    opened at, on the drag's step."""
    view = shown(qapp)
    # Painted once before the student scrolls, as on screen: a paint settling the page late once left
    # the neighbours taking the scrolled stretch after the scroll.
    view.grab()
    qapp.processEvents()
    scroll = visible_scrolls(view)[0]
    track = front(view).tracks[0]
    x = track.area.center().x()
    top = scroll.verticalScrollBar().value()
    first = track.minute_at(QPointF(x, top))
    last = track.minute_at(QPointF(x, top + scroll.viewport().height()))
    step = view.hand.step
    for surface in view.hours_surfaces()[1:]:
        (peek,) = surface.tracks
        assert peek.first % step == 0 and peek.last % step == 0
        assert peek.first <= first < peek.first + step
        assert peek.last - step < last <= peek.last
    held = [(surface.tracks[0].first, surface.tracks[0].last) for surface in view.hours_surfaces()[1:]]
    for value in (top - 120, 0, scroll.verticalScrollBar().maximum()):
        scroll.verticalScrollBar().setValue(value)
        qapp.processEvents()
        qapp.processEvents()
        assert front(view).tracks[0].minute_at(QPointF(x, scroll.verticalScrollBar().value())) != first
        now = [(surface.tracks[0].first, surface.tracks[0].last) for surface in view.hours_surfaces()[1:]]
        assert now == held


def test_neighbours_are_the_card_in_front_at_70_percent_with_the_room_between_kept() -> None:
    """The mock-up's row at 1280 pixels: the card in front 452 wide at 414, a neighbour 316 wide, 32
    between cards."""
    rects = slots(1280, 632, 3, 1.0, wide=False)
    assert (rects[3].left(), rects[3].width(), rects[3].height()) == (414, 452, 600)
    for day in (2, 4):
        assert rects[day].width() == pytest.approx(0.7 * 452)
        assert rects[day].height() == pytest.approx(0.7 * 600)
        assert rects[day].center().y() == pytest.approx(rects[3].center().y())
    assert rects[2].right() == pytest.approx(414 - 32)
    assert rects[4].left() == pytest.approx(414 + 452 + 32)
    assert rects[5].left() >= 1280, "the day after the neighbour waits past the edge rather than cut by it"
    assert rects[2].left() == pytest.approx(66, abs=1)
    assert slots(1280, 632, 3, 1.0, wide=True)[3].width() == 800


def test_a_narrower_row_narrows_the_card_in_front_so_both_neighbours_stay_whole() -> None:
    rects = slots(1150, 632, 3, 1.2, wide=False)
    assert rects[3].width() < 452 * 1.2
    assert rects[2].left() >= 0 and rects[4].right() <= 1150


@pytest.mark.parametrize("wide", [False, True])
@pytest.mark.parametrize(("width", "scale"), [(1280, 1.0), (1150, 1.2), (1024, 1.0), (900, 1.0), (1600, 1.0)])
def test_every_card_is_whole_in_the_row_or_wholly_past_its_ends(width: int, scale: float, wide: bool) -> None:
    """A card cut by the window's edge read as clipped, and on Day a neighbour's homework was a pink bar
    whose name lay past the edge. A card is seen whole or not at all."""
    for day_in_front in range(7):
        for day, rect in slots(width, 632, day_in_front, scale, wide=wide).items():
            inside = rect.left() >= -0.5 and rect.right() <= width + 0.5
            past = rect.right() <= 0.5 or rect.left() >= width - 0.5
            assert inside or past, (day_in_front, day, rect)


def test_open_on_day_the_neighbours_narrow_to_the_room_beside_it() -> None:
    """At 1280 the open card keeps the mock-up's 800 pixels, and a neighbour at 70 % would run past the
    window's edge: it takes the room beside the card instead, whole, at the height a neighbour has."""
    rects = slots(1280, 632, 3, 1.0, wide=True)
    assert rects[3].width() == 800
    for day in (2, 4):
        assert rects[day].left() >= 0 and rects[day].right() <= 1280
        assert rects[day].width() >= 140
        assert rects[day].height() == pytest.approx(0.7 * rects[3].height())
    assert rects[2].right() == pytest.approx(rects[3].left() - 32)
    assert rects[4].left() == pytest.approx(rects[3].right() + 32)


@pytest.mark.parametrize("tab", ["week", "day"])
def test_the_fade_at_the_rows_ends_stays_off_the_cards_in_view(qapp: QApplication, tab: str) -> None:
    """The row's ends fade into the page where the days further off slide in. Open on Day it ran 80
    pixels in, over the neighbour that now fits whole beside the open card."""
    view = shown(qapp, tab=tab)
    fade = view.row.findChild(Fade)
    row = view.row.rect()
    shown_cards = [card for card in view.findChildren(Card) if card.isVisible()]
    cards = [card.geometry() for card in shown_cards if row.contains(card.geometry())]
    assert len(cards) == 2
    for box in cards:
        assert fade.reach <= box.left() and fade.reach <= row.width() - (box.left() + box.width())


def test_a_side_card_labels_its_hours_left_of_its_blocks(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cards beside the one in front show the stretch it shows, but with no hour labels they read
    as a day squeezed on its own. Each labels its whole hours, as the card in front does, left of
    where its blocks are drawn."""
    monkeypatch.setattr(canvas_module, "QPainter", Wrote)
    view = shown(qapp)
    for name in ("clayPeek2", "clayPeek4"):
        side = view.findChild(HoursCanvas, name)
        (track,) = side.tracks
        Wrote.words, Wrote.boxes = [], []
        side.repaint()
        inside = range(-(-(track.first + 30) // 60) * 60, track.last - 30 + 1, 60)
        labels = [clock_label(minute) for minute in inside]
        assert len(labels) >= 8, labels
        beside = {words for words, box in Wrote.boxes if box.right() <= track.area.left()}
        assert set(labels) <= beside, (name, Wrote.words)


def test_homework_on_a_neighbour_of_the_open_day_says_its_name_on_screen(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Open on Day, Wednesday's card ran past the window's left edge, and its homework showed as a
    pink bar: the name was drawn, off screen. It is written where the student can read it."""
    monkeypatch.setattr(canvas_module, "QPainter", Wrote)
    extra = block("essay-2", "flexible", [2], "19:00", 60, assignment_id="essay")
    view = shown(qapp, tab="day", blocks=[*BLOCKS, extra])
    side = view.findChild(HoursCanvas, "clayPeek2")
    assert side.isVisible()
    Wrote.words, Wrote.boxes = [], []
    side.repaint()
    said = [box for words, box in Wrote.boxes if words.startswith("Essay")]
    assert said, Wrote.words
    for box in said:
        at = side.mapTo(view.row, box.topLeft().toPoint())
        assert view.row.rect().contains(at), at


def test_the_arrows_slide_the_row_a_day_and_stop_at_the_weeks_ends(qapp: QApplication) -> None:
    view = shown(qapp)
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    ahead = view.findChild(QPushButton, "clayAhead")
    back = view.findChild(QPushButton, "clayBack")
    ahead.click()
    assert view.row.front == 4
    assert [track.day for track in front(view).tracks] == [4]
    assert view.findChild(QPushButton, "clayWeekFront").day == 4
    for _ in range(4):
        back.click()
    assert view.row.front == 0
    assert not back.isEnabled() and ahead.isEnabled()
    for _ in range(6):
        ahead.click()
    assert view.row.front == 6
    assert back.isEnabled() and not ahead.isEnabled()
    assert opened == []


def test_the_front_names_its_day_and_how_much_it_holds(qapp: QApplication) -> None:
    view = shown(qapp)
    note = view.findChild(QPushButton, "clayWeekFront").findChild(QLabel, "clayNote")
    assert note.text() == "Today · 4 things"
    view.findChild(QPushButton, "clayAhead").click()
    assert note.text() == "2 things"
    view.findChild(QPushButton, "clayAhead").click()
    assert note.text() == "1 thing"


def test_the_wheel_slides_the_row_over_a_neighbour_and_scrolls_the_hours_over_the_front(
    qapp: QApplication,
) -> None:
    view = shown(qapp)
    friday = view.findChild(HoursCanvas, "clayPeek4")
    wheel(friday, -1)
    assert view.row.front == 4
    # At the top of the hours, where the wheel has nothing left to scroll and passes on to the row.
    visible_scrolls(view)[0].verticalScrollBar().setValue(0)
    wheel(front(view), 1)
    assert view.row.front == 4


def test_a_sliding_row_does_not_repaint_its_cards_every_frame(qapp: QApplication) -> None:
    """The row slides a picture of its cards. The cards themselves stay unpainted until it lands."""

    class Count(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.paints = 0

        def eventFilter(self, _watched: QObject, event: QEvent) -> bool:  # noqa: N802
            if event.type() == QEvent.Type.Paint:
                self.paints += 1
            return False

    view = shown(qapp)
    motion.apply_ui_effects("normal")
    cards = []
    for day in range(7):
        canvas = view.row.findChild(QWidget, f"clayPeek{day}")
        assert canvas is not None
        cards.append(canvas.parentWidget())
    counter = Count()
    for card in cards:
        card.installEventFilter(counter)
    view.findChild(QPushButton, "clayAhead").click()
    assert view.row._slide.state() == QAbstractAnimation.State.Running
    counter.paints = 0
    frames = 0
    deadline = time.monotonic() + 0.2
    while time.monotonic() < deadline and view.row._slide.state() == QAbstractAnimation.State.Running:
        qapp.processEvents()
        frames += 1
        QTest.qWait(8)
    assert frames >= 8, "the row slid for several frames"
    assert counter.paints <= 3, f"the cards painted {counter.paints} times over {frames} frames"
    rest(qapp, 0.3)
    assert view.row.front == 4
    thursday = view.row.findChild(QWidget, "clayPeek3").parentWidget()
    assert thursday.isVisible()


def test_the_row_slides_in_240_ms_and_jumps_with_motion_off(qapp: QApplication) -> None:
    view = shown(qapp)
    motion.apply_ui_effects("normal")
    friday = view.row.findChild(QWidget, "clayPeek4").parentWidget()
    before = friday.geometry()
    view.findChild(QPushButton, "clayAhead").click()
    qapp.processEvents()
    assert view.row._slide.state() == QAbstractAnimation.State.Running
    assert front(view).tracks[0].day == 4
    rest(qapp, 0.4)
    assert view.row._slide.state() == QAbstractAnimation.State.Stopped
    thursday = view.row.findChild(QWidget, "clayPeek3").parentWidget()
    assert thursday.isVisible() and thursday.geometry().right() < before.left()
    motion.apply_ui_effects("off")
    view.findChild(QPushButton, "clayAhead").click()
    assert view.row._slide.state() == QAbstractAnimation.State.Stopped
    assert view.row.front == 5


def test_under_reduce_the_row_changes_where_it_is_under_a_fading_picture(qapp: QApplication) -> None:
    """Decision 35 of 0.17: Clay's own motion keeps to the levels. Reduce fades and moves nothing;
    More slides longer than Normal."""
    view = shown(qapp)
    motion.apply_ui_effects("reduce")
    view.findChild(QPushButton, "clayAhead").click()
    assert view.row._slide.state() == QAbstractAnimation.State.Stopped, "nothing slides"
    assert view.row.front == 4 and front(view).tracks[0].day == 4, "Friday is in front at once"
    fading = [label for label in view.row.findChildren(QLabel, motion.FADE_NAME) if label.isVisible()]
    assert len(fading) == 1, "the row as it was fades away over it"
    rest(qapp, 0.4)
    assert [label for label in view.row.findChildren(QLabel, motion.FADE_NAME) if label.isVisible()] == []
    motion.apply_ui_effects("extra")
    view.findChild(QPushButton, "clayAhead").click()
    assert view.row._slide.duration() == motion.duration(240, "extra") > 240


def test_a_block_held_on_an_arrow_slides_the_row_to_the_next_day(qapp: QApplication) -> None:
    """How a block reaches a day that is not beside the one in front: rest it on an arrow."""
    view = shown(qapp)
    ahead = view.findChild(QPushButton, "clayAhead")
    QCursor.setPos(ahead.mapToGlobal(ahead.rect().center()))
    view.hand.active_changed.emit(True)
    rest(qapp, 0.8)
    assert view.row.front == 4
    view.hand.active_changed.emit(False)
    rest(qapp, 0.8)
    assert view.row.front == 4


def test_neighbours_sit_under_a_60_percent_veil_of_the_page_and_the_front_under_none(
    qapp: QApplication,
) -> None:
    """J10, board 5b: the neighbours peeked at full strength. A pixel of Friday's card, beside its hours
    where the clay is plain, is the page colour laid 60 % over the card colour; the card in front
    shows its own. On Slate, whose page and cards differ the most of the built-in looks."""
    view = shown(qapp, pack="slate")
    tokens = view.scene.tokens
    page, card = QColor(tokens["bg"]), QColor(tokens["surface"])
    picture = view.row.grab().toImage()

    def pixel(box: QRect) -> tuple[int, int, int]:
        colour = picture.pixelColor(box.left() + 3, box.top() + box.height() // 3)
        return colour.red(), colour.green(), colour.blue()

    veiled = [0.6 * page.redF() + 0.4 * card.redF(), 0.6 * page.greenF() + 0.4 * card.greenF(),
              0.6 * page.blueF() + 0.4 * card.blueF()]
    for day in (2, 4):
        got = pixel(card_of(view, day).geometry())
        assert all(abs(have - 255 * want) <= 1 for have, want in zip(got, veiled, strict=True)), (day, got)
    front_card = view.row._rects[3].toRect()
    assert pixel(front_card) == (card.red(), card.green(), card.blue())


def test_a_sideways_drag_on_a_neighbour_slides_the_row_to_that_day(qapp: QApplication) -> None:
    """J10: only the arrows and the wheel switched days. Dragged left from Friday, the row brings
    Friday to the front as the ahead arrow does, and nothing is picked up or made."""
    view = shown(qapp)
    made: list[object] = []
    view.hand.committed.connect(made.append)
    friday = view.findChild(HoursCanvas, "clayPeek4")
    drag(friday, friday.rect().center(), QPoint(-200, 0))
    assert view.row.front == 4
    assert [track.day for track in front(view).tracks] == [4]
    assert at_slots(view, 4)
    assert made == [] and not view.hand.busy


def test_a_sideways_drag_on_the_room_between_the_cards_slides_the_row(qapp: QApplication) -> None:
    view = shown(qapp)
    ahead = view.findChild(QPushButton, "clayAhead").geometry()
    gap = QPoint(ahead.center().x(), ahead.top() - 60)
    assert not view.row._rects[3].contains(QPointF(gap)) and not card_of(view, 4).geometry().contains(gap)
    drag(view.row, gap, QPoint(200, 0))
    assert view.row.front == 2
    assert at_slots(view, 2)


def test_a_drag_on_the_front_cards_hours_is_the_hands_and_never_moves_the_row(qapp: QApplication) -> None:
    view = shown(qapp)
    scroll = visible_scrolls(view)[0]
    hours = front(view)
    start = hours.mapFrom(scroll.viewport(), scroll.viewport().rect().center())
    before = (scroll.geometry(), card_of(view, 4).geometry())
    drag(hours, start, QPoint(-150, 0), let_go=False)
    try:
        assert view.hand.active, "the hand carries what the press picked up"
        assert (scroll.geometry(), card_of(view, 4).geometry()) == before
    finally:
        let_go_at(hours, hours.mapTo(view, start + QPoint(-150, 0)))
    assert view.row.front == 3
    assert at_slots(view, 3)


def test_a_drag_shorter_than_40_pixels_goes_back_to_the_day_it_left(qapp: QApplication) -> None:
    view = shown(qapp)
    friday = view.findChild(HoursCanvas, "clayPeek4")
    before = card_of(view, 4).geometry()
    start = friday.mapTo(view, friday.rect().center())
    drag(friday, friday.rect().center(), QPoint(-36, 0), let_go=False)
    try:
        assert card_of(view, 4).geometry() == before.translated(-36, 0), "the row follows the pointer"
    finally:
        let_go_at(friday, start + QPoint(-36, 0))
    assert view.row.front == 3
    assert card_of(view, 4).geometry() == before
    drag(friday, friday.rect().center(), QPoint(-44, 0))
    assert view.row.front == 4


def test_a_drag_settles_with_the_apps_motion_and_at_once_with_motion_off(qapp: QApplication) -> None:
    view = shown(qapp)
    friday = view.findChild(HoursCanvas, "clayPeek4")
    drag(friday, friday.rect().center(), QPoint(-200, 0))
    assert view.row._slide.state() == QAbstractAnimation.State.Stopped
    assert view.row.front == 4 and at_slots(view, 4)
    motion.apply_ui_effects("normal")
    saturday = view.findChild(HoursCanvas, "clayPeek5")
    drag(saturday, saturday.rect().center(), QPoint(-200, 0))
    assert view.row.front == 5
    assert view.row._slide.state() == QAbstractAnimation.State.Running
    rest(qapp, 0.4)
    assert view.row._slide.state() == QAbstractAnimation.State.Stopped and at_slots(view, 5)
    friday = view.findChild(HoursCanvas, "clayPeek4")
    drag(friday, friday.rect().center(), QPoint(20, 0))
    assert view.row.front == 5
    assert view.row._slide.state() == QAbstractAnimation.State.Running, "a short drag slides back"
    rest(qapp, 0.4)
    assert at_slots(view, 5)


def test_a_sideways_drag_on_day_asks_the_window_for_the_day_as_the_arrows_do(qapp: QApplication) -> None:
    view = shown(qapp, tab="day")
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    friday = view.findChild(HoursCanvas, "clayPeek4")
    assert friday.isVisible()
    drag(friday, friday.rect().center(), QPoint(-200, 0))
    assert opened == [view.scene.week.date_of(4).isoformat()]
    # The window has not shown Friday here, so the row went back to Thursday meanwhile.
    assert view.row.front == 3 and at_slots(view, 3)


def test_a_click_on_a_neighbour_still_opens_its_day_or_its_block(qapp: QApplication) -> None:
    """The row holds a press on a neighbour back until it knows it is no drag of the row; a click is
    then the click it was."""
    view = shown(qapp)
    days: list[str] = []
    blocks: list[str] = []
    view.day_activated.connect(days.append)
    view.hand.opened.connect(blocks.append)
    QTest.mouseClick(view.findChild(QPushButton, "clayDay4"), Qt.MouseButton.LeftButton)
    assert days == [view.scene.week.date_of(4).isoformat()]
    friday = view.findChild(HoursCanvas, "clayPeek4")
    school = friday.block_rect("school", 4)
    assert school is not None
    on_school = friday.mapFromGlobal(school.center())
    QTest.mouseClick(friday, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, on_school)
    assert blocks == ["school"]
    assert view.row.front == 3


def test_day_names_open_their_day_and_every_day_has_one(qapp: QApplication) -> None:
    view = shown(qapp)
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    names = {item.property("day_target") for item in view.findChildren(QPushButton)} - {None}
    assert names == set(range(7))
    QTest.mouseClick(view.findChild(QPushButton, "clayDay4"), Qt.MouseButton.LeftButton)
    QTest.mouseClick(view.findChild(QPushButton, "clayWeekFront"), Qt.MouseButton.LeftButton)
    week = view.scene.week
    assert opened == [week.date_of(4).isoformat(), week.date_of(3).isoformat()]


def test_a_name_past_the_rows_edge_is_brought_to_the_front_before_it_is_found(qapp: QApplication) -> None:
    view = shown(qapp)
    hours = front(view)
    friday = view.findChild(QPushButton, "clayDay4")
    assert friday.rect().contains(friday.mapFromGlobal(hours.day_name(4)))
    assert view.row.front == 3
    point = hours.day_name(6)
    assert view.row.front == 6
    head = view.findChild(QPushButton, "clayWeekFront")
    assert head.rect().contains(head.mapFromGlobal(point))
    assert view.row.rect().contains(view.row.mapFromGlobal(point))


def test_reveal_brings_a_day_to_the_front_and_its_time_into_view(qapp: QApplication) -> None:
    view = shown(qapp)
    view.hours_surfaces()[-1].reveal(5, 9 * 60, 10 * 60)
    qapp.processEvents()
    assert view.row.front == 5
    hours = front(view)
    assert hours.track_for(5, 9 * 60) is not None
    assert hours.in_view(5, 9 * 60) and hours.in_view(5, 10 * 60)


def test_with_the_days_either_side_hidden_only_the_front_is_hours(qapp: QApplication) -> None:
    view = shown(qapp, peek="hide")
    assert [track.day for surface in view.hours_surfaces() for track in surface.tracks] == [3]
    view.findChild(QPushButton, "clayAhead").click()
    assert [track.day for surface in view.hours_surfaces() for track in surface.tracks] == [4]


def test_day_opens_the_card_wider_with_its_hours_by_kind_and_what_is_left_today(qapp: QApplication) -> None:
    """Thursday at 13:40: School 08:00-14:30, Dinner 18:00-18:30, the essay 18:45-19:45 and chemistry
    20:00-21:30. Planned is placed homework still ahead (the essay and chemistry, 2 h 30 min), not School."""
    view = shown(qapp, tab="day")
    assert [scroll.objectName() for scroll in visible_scrolls(view)] == ["clayDayScroll"]
    assert [(track.day, track.first, track.last) for track in front(view).tracks] == [(3, 0, 1440)]
    summary = view.findChild(QWidget, "claySummary")
    assert summary.findChild(QLabel, "claySumTitle").text() == "Thursday, 08:00 to 22:00"
    assert pairs(view) == [
        ("School", "6 h 30 min"),
        ("Homework", "2 h 30 min"),
        ("Meals", "30 min"),
        ("Free", "4 h 30 min"),
        ("Planned", "2 h 30 min"),
        ("Free until 22:00", "4 h 30 min"),
        ("Next at 18:00", "in 4 h 20 min"),
    ]
    assert summary.geometry().left() > visible_scrolls(view)[0].geometry().right()


def test_planned_counts_only_what_is_left_of_homework_already_under_way() -> None:
    """At 13:40 the essay from 13:00 to 14:00 has 20 minutes left, and chemistry's 90 at 20:00 are all
    ahead: planned today is 1 h 50 min, not the essay's whole hour on top of chemistry."""
    from desktop.native.layouts.clay import left_today

    blocks = [dict(item, start="13:00") if item["id"] == "essay-1" else item for item in BLOCKS]
    planned, _free, _coming = left_today(build_week(WEEK, blocks, HOMEWORK, TRACE), 3, minute_of("13:40"))
    assert planned == 20 + 90


def test_another_day_has_no_left_today(qapp: QApplication) -> None:
    view = shown(qapp, tab="day", day=4)
    assert view.row.front == 4
    assert pairs(view) == [("School", "6 h 30 min"), ("Meals", "30 min"), ("Free", "7 h")]
    assert view.findChild(QLabel, "clayLeftTitle") is None


def test_days_arrows_ask_the_window_for_the_day_either_side_across_the_weeks_edge(
    qapp: QApplication,
) -> None:
    view = shown(qapp, tab="day", day=0)
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    view.findChild(QPushButton, "clayAhead").click()
    view.findChild(QPushButton, "clayBack").click()
    assert opened == ["2026-09-15", "2026-09-13"]
    assert view.row.front == 0


def test_a_block_carried_to_another_day_on_day_takes_the_window_there_when_it_is_let_go(
    qapp: QApplication,
) -> None:
    view = shown(qapp, tab="day")
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    ahead = view.findChild(QPushButton, "clayAhead")
    QCursor.setPos(ahead.mapToGlobal(ahead.rect().center()))
    view.hand.active_changed.emit(True)
    rest(qapp, 0.8)
    assert opened == []
    view.hand.active_changed.emit(False)
    assert opened == [view.scene.week.date_of(4).isoformat()]


def test_the_dish_holds_what_is_not_placed_yet_with_when_it_is_due(qapp: QApplication) -> None:
    view = shown(qapp)
    assert view.findChild(QLabel, "clayTrayLabel").text() == "Not placed yet"
    assert view.findChild(QLabel, "clayDue").text() == "Due Sun 20"
    assert view.findChild(QLabel, "clayHint").text() == "Drag a chip onto a day."
    chips = view.findChildren(ClayChip)
    assert [chip.block_id for chip in chips] == ["poster-1"]
    assert all(chip.hand is view.hand for chip in chips)


def test_scroll_and_zoom_survive_a_scene_refresh(qapp: QApplication) -> None:
    view = shown(qapp)
    scroll = view.findChild(HoursScroll, "clayWeekScroll")
    scroll.zoom_by(1)
    scroll.verticalScrollBar().setValue(240)
    before = (scroll.px, scroll.verticalScrollBar().value())
    again(qapp, view, minute=view.scene.minute + 15)
    assert view.findChild(HoursScroll, "clayWeekScroll") is scroll
    assert (scroll.px, scroll.verticalScrollBar().value()) == before
    assert front(view).now_min == view.scene.minute


def test_day_and_week_keep_separate_scrolls(qapp: QApplication) -> None:
    view = shown(qapp)
    week_scroll = view.findChild(HoursScroll, "clayWeekScroll")
    week_scene = view.scene
    again(qapp, view, surface="day")
    day_scroll = view.findChild(HoursScroll, "clayDayScroll")
    assert day_scroll is not week_scroll
    assert visible_scrolls(view) == [day_scroll]
    view.show_week(week_scene)
    qapp.processEvents()
    assert visible_scrolls(view) == [week_scroll]


if importlib.util.find_spec("PySide6") is not None:

    class Wrote(QPainter):
        """A painter that keeps every string drawn with it."""

        words: list[str] = []
        # Each string with the box it was drawn in, where it was drawn in one, in the painter's frame.
        boxes: list[tuple[str, QRectF]] = []

        def drawText(self, *args: object) -> None:  # noqa: N802
            words = next(arg for arg in reversed(args) if isinstance(arg, str))
            Wrote.words.append(words)
            if isinstance(args[0], QRectF):
                Wrote.boxes.append((words, self.transform().mapRect(args[0])))
            super().drawText(*args)


@pytest.mark.parametrize("points", [9, 13])
def test_a_short_block_on_a_side_card_keeps_its_name_where_a_shortened_one_fits(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, points: int
) -> None:
    """A half hour is 10 pixels tall on a card at 70 %, and its name is still written there, as the
    half hour Dinner is on the card in front. The name is shortened at a word with the ellipsis where
    the block is narrow, and where not even three letters of it fit, the colour alone is left."""
    monkeypatch.setattr(canvas_module, "QPainter", Wrote)
    usual = QFont(qapp.font())
    font = QFont(usual)
    font.setPointSize(points)
    qapp.setFont(font)
    try:
        view = shown(qapp)
        side = view.findChild(HoursCanvas, "clayPeek2")
        box = side.block_rect("dinner", 2)
        assert box is not None and box.height() < 12
        Wrote.words = []
        side.repaint()
        assert any(word.startswith("Dinner") for word in Wrote.words), "Dinner has lost its name"

        painter = side.painter
        drawn = Drawn("tea", "Tea and toast", "meals", False, Span(2, 18 * 60, 18 * 60 + 30), 0, 1)
        image = QImage(400, 40, QImage.Format.Format_ARGB32)
        page = QRectF(0, 0, 400, 40)

        def written(width: float) -> list[str]:
            Wrote.words = []
            paint = Wrote(image)
            painter.block(paint, QRectF(10, 10, width, 10), drawn, page)
            paint.end()
            return Wrote.words

        assert written(200)[0].startswith("Tea and toast")
        narrow = written(70)
        assert narrow and narrow[0].endswith("…") and narrow[0].startswith("Tea")
        assert written(24) == []
    finally:
        qapp.setFont(usual)


def test_the_icon_gives_way_on_a_card_where_it_would_cost_the_name(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A block with room for "Piano lesson" or for the icon and "Piano…" says its name, as the
    shared hours do. With room for both it has both."""
    from desktop.native import icons

    monkeypatch.setattr(canvas_module, "QPainter", Wrote)
    drew: list[str] = []
    real = icons.pixmap

    def pixmap(name: str, *rest: object):
        drew.append(name)
        return real(name, *rest)

    monkeypatch.setattr(icons, "pixmap", pixmap)
    view = shown(qapp)
    painter = view.findChild(HoursCanvas, "clayPeek2").painter
    drawn = Drawn("piano", "Piano lesson", "extra", False, Span(2, 17 * 60, 17 * 60 + 30), 0, 1)
    image = QImage(400, 40, QImage.Format.Format_ARGB32)
    page = QRectF(0, 0, 400, 40)

    def written(width: float) -> tuple[list[str], list[str]]:
        Wrote.words = []
        drew.clear()
        paint = Wrote(image)
        painter.block(paint, QRectF(10, 10, width, 10), drawn, page)
        paint.end()
        return Wrote.words, list(drew)

    name = QFontMetricsF(painter.fonts(qapp.font())[0]).horizontalAdvance("Piano lesson")
    # The name's own width and the 14 and 8 pixels a side card keeps clear at a block's ends.
    assert written(name + 23) == (["Piano lesson"], [])
    # Room for its time as well: the icon comes after the name and the time.
    words, pictures = written(name + 110)
    assert words[0] == "Piano lesson" and pictures == ["sparkles"]


def test_a_quarter_hour_on_a_side_card_is_named_beside_its_bar_clear_of_its_neighbours(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A quarter hour is under 7 pixels tall on a card at 70 %: too short for a line inside it. It is
    still named, by its name or else its start time, and two of them one after the other do not write
    over each other nor over a block tall enough for its own words."""
    monkeypatch.setattr(canvas_module, "QPainter", Wrote)
    quarters = [
        block("call", "locked", [2], "15:00", 15, title="Call", category="extra"),
        block("tidy", "locked", [2], "15:15", 15, title="Tidy", category="extra"),
        block("stretch", "locked", [2], "16:30", 15, title="Stretch", category="extra"),
    ]
    view = shown(qapp, blocks=[*BLOCKS, *quarters])
    side = view.findChild(HoursCanvas, "clayPeek2")

    def local(name: str) -> QRectF:
        found = side.block_rect(name, 2)
        assert found is not None
        return QRectF(QRect(side.mapFromGlobal(found.topLeft()), found.size()))

    bars = {name: local(name) for name in ("call", "tidy", "stretch")}
    assert all(bar.height() < 8 for bar in bars.values()), bars
    Wrote.words, Wrote.boxes = [], []
    side.repaint()
    named: dict[str, QRectF] = {}
    ways = (("call", "Call", "15:00"), ("tidy", "Tidy", "15:15"), ("stretch", "Stretch", "16:30"))
    for name, title, start in ways:
        # The hour labels in the gutter are also times: only words written over the block's own rows count.
        found = [
            box
            for words, box in Wrote.boxes
            if words in (title, start)
            and box.left() >= bars[name].left() - 1
            and abs(box.center().y() - bars[name].center().y()) < 14
        ]
        assert found, f"{title} is neither named nor given its start time: {Wrote.boxes}"
        named[name] = found[0]
    labels = list(named.values())
    for at, label in enumerate(labels):
        assert QRectF(side.rect()).contains(label), (at, label)
        for other in labels[at + 1:]:
            assert not label.intersects(other), "two labels write over each other"
    tall = [local("school"), local("dinner")]
    assert all(bar.height() >= 8 for bar in tall)
    for label in labels:
        assert not any(label.intersects(bar) for bar in tall), "a label is written over a tall block"


def test_a_half_hour_on_a_card_says_its_start_time_rather_than_its_icon(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The name, then the time, then the icon, as on the shared hours: room for "Dinner 18:30" or
    for the icon and "Dinner" says the time, and with room for all three the card has all three."""
    from desktop.native import icons

    monkeypatch.setattr(canvas_module, "QPainter", Wrote)
    drew: list[str] = []
    real = icons.pixmap

    def pixmap(name: str, *rest: object):
        drew.append(name)
        return real(name, *rest)

    monkeypatch.setattr(icons, "pixmap", pixmap)
    view = shown(qapp)
    painter = view.findChild(HoursCanvas, "clayPeek2").painter
    drawn = Drawn("dinner", "Dinner", "meals", False, Span(2, 18 * 60 + 30, 19 * 60), 0, 1)
    image = QImage(400, 40, QImage.Format.Format_ARGB32)
    page = QRectF(0, 0, 400, 40)

    def written(width: float) -> tuple[list[str], list[str]]:
        Wrote.words = []
        drew.clear()
        paint = Wrote(image)
        painter.block(paint, QRectF(10, 10, width, 10), drawn, page)
        paint.end()
        return Wrote.words, list(drew)

    title, small = painter.fonts(qapp.font())
    both = QFontMetricsF(title).horizontalAdvance("Dinner") + 6
    both += QFontMetricsF(small).horizontalAdvance("18:30")
    icon = round(QFontMetricsF(title).ascent()) + 4
    # The 14 and 8 pixels a side card keeps clear at a block's ends.
    assert written(both + 23) == (["Dinner", "18:30"], [])
    assert written(both + 23 + icon) == (["Dinner", "18:30"], ["clock"])


def test_a_block_that_shares_its_time_is_drawn_like_one_that_does_not(qapp: QApplication) -> None:
    """Two blocks side by side show they share their time by sitting side by side: the dot at the
    corner of each said nothing a student could read, and covered the end of the name."""
    options = options_for(None, "clay")
    tokens = tokens_for("clay", options["colour"], resolved_palette("light-frost", False, None, "default"))

    def painted(columns: int) -> QImage:
        drawn = Drawn("soccer", "Soccer practice", "extra", False, Span(1, 16 * 60, 17 * 60 + 30), 0, columns)
        image = QImage(200, 140, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        ClayPainter(tokens, full=True).body(painter, QRectF(20, 20, 60, 90), drawn)
        painter.end()
        return image

    assert painted(2) == painted(1), "a block that shares its time has a mark on it"


def test_the_row_is_seven_eighths_of_the_way_at_half_time(qapp, monkeypatch):
    view = shown(qapp)
    motion.apply_ui_effects("normal")
    view.findChild(QPushButton, "clayAhead").click()
    shares = []
    monkeypatch.setattr(view.row, "_slid", shares.append)
    view.row._slide.pause()
    view.row._slide.setCurrentTime(120)
    assert shares == [pytest.approx(0.875)]
    view.row._slide.stop()


def _slide_pictures(row) -> tuple[dict[int, object], dict[int, object]]:
    """Start and end pictures the row keeps while it slides, whatever shape it stores them in."""
    snaps = row._snaps
    assert snaps is not None
    if isinstance(snaps, tuple) and len(snaps) == 2:
        return snaps[0], snaps[1]
    starts, ends = {}, {}
    for day, pair in snaps.items():
        if isinstance(pair, tuple) and len(pair) == 2:
            starts[day], ends[day] = pair
        else:
            starts[day] = pair
    return starts, ends


def _frame_gap(qapp: QApplication, row) -> int:
    """The largest difference in any colour channel between the running slide's last frame and the
    row once it has landed. A sliver of antialiasing may differ at the arrows' and cards' edges;
    another hour, heading or card is a difference of 100 or more."""
    assert row._slide.state() == QAbstractAnimation.State.Running
    row._slide.pause()
    row._on_clock(float(row._slide.duration()))
    row.repaint()
    at_end = row.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    row._land()
    qapp.processEvents()
    row.repaint()
    landed = row.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    row._slide.stop()
    assert at_end.size() == landed.size()
    return max(abs(a - b) for a, b in zip(bytes(at_end.constBits()), bytes(landed.constBits()), strict=True))


def test_the_last_slide_frame_matches_the_landed_row(qapp: QApplication) -> None:
    """At t=1 the row is already the landed layout: start pictures are gone, end pictures sit at
    their finished size, so a grab matches one taken after the slide stops."""
    view = shown(qapp)
    motion.apply_ui_effects("normal")
    view.findChild(QPushButton, "clayAhead").click()
    assert _frame_gap(qapp, view.row) <= 16


def test_the_last_day_slide_frame_matches_the_landed_row(qapp: QApplication) -> None:
    """Day opens its hours and summary for the new day as the row starts to slide, so the end
    pictures hold the day as it lands, not the hours where the last day left them."""
    view = shown(qapp, tab="day")
    motion.apply_ui_effects("normal")
    scene = view.scene
    view.show_week(Scene(
        scene.week, scene.today, scene.minute, scene.options, scene.tokens,
        surface="day", iso_day=scene.week.date_of(4).isoformat(),
    ))
    assert _frame_gap(qapp, view.row) <= 16


def test_the_live_hours_stay_where_they_land_while_the_row_slides(qapp: QApplication) -> None:
    """The hours in front are not painted while the pictures move, so they must not be moved
    either: a widget moved with its updates off leaves stale pixels behind."""
    view = shown(qapp)
    motion.apply_ui_effects("normal")
    row = view.row
    view.findChild(QPushButton, "clayAhead").click()
    assert row._slide.state() == QAbstractAnimation.State.Running
    row._slide.pause()
    row._on_clock(row._slide.duration() / 2)
    assert row._snaps is not None
    mid = row.hours.geometry()
    row._land()
    assert mid == row.hours.geometry()
    row._slide.stop()


def test_day_hides_live_side_cards_while_the_row_slides(qapp: QApplication) -> None:
    """Day's render used to _put after the slide had started, which showed the live neighbours
    beside the moving pictures."""
    view = shown(qapp, tab="day")
    motion.apply_ui_effects("normal")
    row = view.row
    row._go(4, "slide")
    assert row._slide.state() == QAbstractAnimation.State.Running
    row.set_summary(view._summary(view.scene, 4))
    assert row._snaps is not None
    live = [card for card in row.findChildren(Card) if card.isVisible()]
    assert live == [], f"live side cards still showing: {[card.day for card in live]}"
    row._slide.stop()
    row._land()


def test_only_one_day_summary_shows_while_the_row_slides(qapp: QApplication) -> None:
    """The new day's summary must not sit live over the baked picture of the old one."""
    view = shown(qapp, tab="day")
    motion.apply_ui_effects("normal")
    row = view.row
    row._go(4, "slide")
    row.set_summary(view._summary(view.scene, 4))
    assert row._snaps is not None
    summaries = [widget for widget in view.findChildren(QWidget, "claySummary") if widget.isVisible()]
    assert summaries == [], "a live claySummary is stacking on the slide's pictures"
    row._slide.stop()
    row._land()


def test_a_summary_replaced_mid_slide_is_the_one_shown_when_it_lands(qapp: QApplication) -> None:
    """Day's summary can be replaced while the row slides. When it lands, the new one shows in the
    row, and the replaced one is never shown again, least of all as a window of its own."""
    view = shown(qapp, tab="day")
    motion.apply_ui_effects("normal")
    row = view.row
    row._go(4, "slide", summary=view._summary(view.scene, 4))
    assert row._snaps is not None
    old = row._summary
    fresh = view._summary(view.scene, 4)
    row.set_summary(fresh)
    row._slide.stop()
    row._land()
    assert row._summary is fresh
    assert fresh.parentWidget() is row and fresh.isVisible(), "the new summary shows once landed"
    assert old is None or not isValid(old) or not old.isVisible(), "the replaced summary stays hidden"


def test_a_card_entering_from_off_screen_has_a_picture(qapp: QApplication) -> None:
    """Saturday in front leaves Monday past the left edge; sliding to Sunday still keeps a picture
    of it, so it does not pop if it comes into view."""
    view = shown(qapp)
    view.row._go(5, "jump")
    monday = view.row._rects[0]
    assert monday.right() < 0, "Monday should start past the left edge"
    motion.apply_ui_effects("normal")
    view.row._go(6, "slide")
    assert view.row._slide.state() == QAbstractAnimation.State.Running
    starts, ends = _slide_pictures(view.row)
    assert 0 in starts or 0 in ends, "Monday has no start or end picture"
    view.row._slide.stop()
    view.row._land()


def _drawn_at(qapp: QApplication, view: ClayDeckView, share: float, monkeypatch) -> list[dict]:
    """Every picture the sliding row draws with the slide held at `share`: which day and end it is,
    its logical size, where it is drawn, its opacity and the clip it is drawn through."""
    row = view.row
    assert row._slide.state() != QAbstractAnimation.State.Stopped
    row._slide.pause()
    starts, ends = _slide_pictures(row)
    keys = {shot.picture.cacheKey(): (day, "start") for day, shot in starts.items()}
    keys.update({shot.picture.cacheKey(): (day, "end") for day, shot in ends.items()})
    seen: list[dict] = []
    original = type(row)._blit

    def record(self, painter, picture, target):
        ratio = picture.devicePixelRatio() or 1.0
        day, end = keys[picture.cacheKey()]
        seen.append({
            "day": day, "end": end, "opacity": painter.opacity(), "target": QRectF(target),
            "size": (picture.width() / ratio, picture.height() / ratio),
            "clip": painter.clipPath().boundingRect(), "card": QRectF(self._rects[day]),
        })
        original(self, painter, picture, target)

    monkeypatch.setattr(type(row), "_blit", record)
    row._slid(share)
    row.repaint()
    return seen


def _stop(row) -> None:
    row._slide.stop()
    row._land()


def _slide_week(qapp: QApplication):
    view = shown(qapp)
    motion.apply_ui_effects("normal")
    view.findChild(QPushButton, "clayAhead").click()
    return view


def _slide_day(qapp: QApplication):
    view = shown(qapp, tab="day")
    motion.apply_ui_effects("normal")
    scene = view.scene
    view.show_week(Scene(
        scene.week, scene.today, scene.minute, scene.options, scene.tokens,
        surface="day", iso_day=scene.week.date_of(4).isoformat(),
    ))
    return view


@pytest.mark.parametrize("start", [_slide_week, _slide_day], ids=["week", "day"])
def test_mid_slide_a_picture_is_scaled_alike_both_ways_and_clipped_to_its_card(
    qapp: QApplication, monkeypatch, start
) -> None:
    """A picture squeezed into another shape stretched its words. One factor on both sides, and the
    card's own rectangle as the clip, keep them as they were drawn."""
    view = start(qapp)
    scaled = 0
    for share in (0.05, 0.3, 0.5, 0.7):
        for item in _drawn_at(qapp, view, share, monkeypatch):
            wide, tall = item["size"]
            target = item["target"]
            assert abs(target.width() - target.height() * wide / tall) <= 1, (share, item)
            scaled += abs(target.height() - tall) > 2
            assert item["clip"].isEmpty() is False
            assert item["clip"].adjusted(-0.5, -0.5, 0.5, 0.5).contains(item["card"]), (share, item)
            assert item["card"].adjusted(-0.5, -0.5, 0.5, 0.5).contains(item["clip"]), (share, item)
        monkeypatch.undo()
    assert scaled > 0, "no picture was scaled, so the check saw nothing"
    _stop(view.row)


@pytest.mark.parametrize("start", [_slide_week, _slide_day], ids=["week", "day"])
def test_the_end_picture_takes_over_from_the_start_picture_between_15_and_55_percent(
    qapp: QApplication, monkeypatch, start
) -> None:
    """Before the window only the start picture shows, after it only the end, so two layouts overlap
    for a few frames and not the whole slide."""
    view = start(qapp)
    early = _drawn_at(qapp, view, 0.1, monkeypatch)
    monkeypatch.undo()
    late = _drawn_at(qapp, view, 0.6, monkeypatch)
    monkeypatch.undo()
    middle = _drawn_at(qapp, view, 0.35, monkeypatch)
    monkeypatch.undo()
    assert early and {item["end"] for item in early} == {"start"}
    assert {item["opacity"] for item in early} == {1.0}
    assert late and {item["end"] for item in late} == {"end"}
    assert {item["opacity"] for item in late} == {1.0}
    # Halfway through the window (a smoothstep at its middle) each has half.
    assert {item["end"] for item in middle} == {"start", "end"}
    assert {round(item["opacity"], 3) for item in middle} == {0.5}
    _stop(view.row)
