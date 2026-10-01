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
    from PySide6.QtCore import QAbstractAnimation, QPoint, QPointF, QRectF, Qt
    from PySide6.QtGui import QCursor, QFont, QFontMetricsF, QImage, QPainter
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

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
    qapp: QApplication, *, tab: str = "week", day: int = 3, blocks: list[dict] | None = None, **chosen: str
) -> ClayDeckView:
    options = {**options_for(None, "clay"), **chosen}
    palette = resolved_palette("light-frost", False, None, "default")
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


def test_neighbours_show_the_stretch_the_day_in_front_shows_on_the_drags_step(qapp: QApplication) -> None:
    view = shown(qapp)
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
    scroll.verticalScrollBar().setValue(top - 120)
    qapp.processEvents()
    moved = view.hours_surfaces()[1].tracks[0]
    assert moved.first == pytest.approx(first - 120 / track.per_minute(), abs=step)


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
    20:00-21:30. Until 22:00: 50 minutes of School, and all the rest, are still ahead."""
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
        ("Planned", "3 h 50 min"),
        ("Free until 22:00", "4 h 30 min"),
        ("Next at 18:00", "in 4 h 20 min"),
    ]
    assert summary.geometry().left() > visible_scrolls(view)[0].geometry().right()


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
