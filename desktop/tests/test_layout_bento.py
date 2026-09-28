"""Bento (0.17): the week or today as the hero tile, the tiles around it, and their retained hours."""

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
    import shiboken6
    from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF
    from PySide6.QtGui import QEnterEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

    from desktop.native.hours import canvas as canvas_module
    from desktop.native.hours.canvas import Drawn, HoursCanvas
    from desktop.native.hours.chips import TrayChip
    from desktop.native.hours.geometry import Span
    from desktop.native.hours.hand import Hand, Verdict
    from desktop.native.layouts.base import Scene
    from desktop.native.layouts.bento import (
        DAY_SCALE,
        LIFT_MS,
        RISE,
        BentoPainter,
        BentoView,
        DayTile,
        LoadBars,
        free_slots,
        time_left,
    )
    from desktop.native.layouts.registry import LAYOUTS, MATCH, options_for, tokens_for
    from desktop.native.look import AA_TEXT, contrast, resolved_palette
    from desktop.native.motion import apply_ui_effects
    from desktop.native.weekmodel import build_week, minute_of


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-bento-test"])
    yield application


def scene(surface: str = "week", *, clock: str = "13:40", blocks: list[dict] | None = None,
          homework: dict | None = None, iso_day: str = "2026-09-17", today: int | None = 3,
          scale: float = 1.0, **chosen: str) -> Scene:
    options = {**options_for(None, "bento"), **chosen}
    palette = resolved_palette("light-frost", False, None, "default")
    week = build_week(
        WEEK, BLOCKS if blocks is None else blocks,
        HOMEWORK if homework is None else homework, TRACE,
    )
    return Scene(
        week, today, minute_of(clock), options,
        tokens_for("bento", options["colour"], palette), scale=scale, surface=surface,
        month={"month": "2026-09", "days": []} if surface == "month" else None,
        iso_day=iso_day,
    )


def shown(qapp: QApplication, surface: str = "week", *, size: tuple[int, int] = (1150, 768),
          **given: object) -> BentoView:
    view = BentoView()
    view.resize(*size)
    view.show_week(scene(surface, **given))
    view.show()
    qapp.processEvents()
    return view


def text(view: BentoView, name: str) -> str:
    found = view.findChild(QLabel, name)
    assert found is not None, name
    return found.text()


def texts(view: BentoView, name: str) -> list[str]:
    return [item.text() for item in view.findChildren(QLabel, name) if item.isVisible()]


def hours(view: BentoView, name: str = "bentoDayHours") -> HoursCanvas:
    found = view.findChild(HoursCanvas, name)
    assert found is not None and found.isVisible(), name
    return found


def test_the_hero_is_a_choice_of_week_or_today_and_the_week_comes_first() -> None:
    hero = next(option for option in LAYOUTS["bento"].options if option.key == "hero")
    assert (hero.label, hero.level) == ("Hero", "style")
    assert [(choice.value, choice.label) for choice in hero.choices] == [("week", "Week"), ("today", "Today")]
    assert options_for(None, "bento")["hero"] == "week"


def test_a_bento_saved_before_the_hero_still_opens_as_it_was(qapp: QApplication) -> None:
    """0.16 saved Supporting tiles too; that option went, and what else was saved is kept."""
    saved = {"main": "bento", "options": {"bento": {"colour": "sunset", "corners": "square",
                                                    "tiles": "essentials"}}}
    assert options_for(saved, "bento") == {"colour": "sunset", "hero": "week", "corners": "square"}
    view = BentoView()
    view.resize(1150, 768)
    palette = resolved_palette("light-frost", False, None, "default")
    options = options_for(saved, "bento")
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    view.show_week(Scene(week, 3, minute_of("13:40"), options, tokens_for("bento", "sunset", palette)))
    view.show()
    qapp.processEvents()
    assert hours(view, "bentoWeekHours").isVisible()
    assert view.findChild(TrayChip, "bentoWaiting0").isVisible()


def test_day_hero_is_one_live_full_day_track_with_window_hand(qapp: QApplication) -> None:
    host = QWidget()
    hand = Hand(lambda *_: Verdict(True, ""), host)
    view = BentoView(hand=hand)
    view.resize(1150, 768)
    view.show_week(scene("day"))
    view.show()
    qapp.processEvents()
    canvas = hours(view)
    assert view.hand is hand
    assert [(track.day, track.first, track.last) for track in canvas.tracks] == [(3, 0, 1440)]
    assert canvas.hand is hand
    assert text(view, "bentoHeroTitle") == "Today"


def test_week_hero_has_seven_live_columns_and_openable_day_names(qapp: QApplication) -> None:
    view = shown(qapp)
    canvas = hours(view, "bentoWeekHours")
    assert [(track.day, track.first, track.last) for track in canvas.tracks] == [
        (day, 0, 1440) for day in range(7)
    ]
    assert text(view, "bentoHeroTitle") == "This week"
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    pick = view.findChild(QPushButton, "bentoDayName0")
    assert pick is not None
    assert canvas.day_name(0) == pick.mapToGlobal(pick.rect().center())
    pick.click()
    assert opened == ["2026-09-14"]


def test_neither_hero_draws_an_add_of_its_own(qapp: QApplication) -> None:
    """The top bar has Add in every design (decision 11 of 0.17)."""
    for hero in ("week", "today"):
        for surface in ("week", "day"):
            view = shown(qapp, surface, hero=hero)
            assert not [
                item.objectName() for item in view.findChildren(QPushButton) if "Add" in item.objectName()
            ], (hero, surface)


def test_waiting_homework_is_a_hand_chip_and_due_soon_says_where_each_is(qapp: QApplication) -> None:
    view = shown(qapp)
    chip = view.findChild(TrayChip, "bentoWaiting0")
    assert chip is not None
    assert chip.hand is view.hand
    assert text(view, "bentoWaitingLabel") == "Not placed yet"
    # Soonest due first: Chem due tonight, the essay tomorrow, the poster on Sunday and not placed.
    assert texts(view, "bentoDueMeta") == ["1 h 30 · Thu 20:00", "1 h · Thu 18:45", "2 h · Not placed"]
    rows = [view.findChild(QPushButton, f"bentoDue{index}") for index in range(3)]
    assert [row.property("block_id") for row in rows] == ["chem-1", "essay-1", "poster-1"]
    assert text(view, "bentoDuePlaced") == "2 of 3 placed"
    opened: list[str] = []
    view.block_activated.connect(opened.append)
    rows[2].click()
    assert opened == ["poster-1"]
    day = shown(qapp, "day")
    assert day.findChild(QPushButton, "bentoDue0") is not None
    assert text(day, "bentoWaitingHint") == "Drag one onto your day."


def test_due_soon_counts_down_to_the_first_homework_due(qapp: QApplication) -> None:
    due = shown(qapp).findChild(QWidget, "bentoDue")
    # Chem lab report is due at the end of today, Thursday, and it is 13:40.
    figure = (due.findChild(QLabel, "bentoFigure").text(), due.findChild(QLabel, "bentoDueUntil").text())
    assert figure == ("10 h 20 min", "until the end of today")
    from datetime import date

    thursday = date(2026, 9, 17)
    assert time_left("2026-09-20T20:00", thursday, 820) == ("3 days", "until Sunday 20", False)
    assert time_left("2026-09-18T21:00", thursday, 820) == ("1 day", "until Friday 18", False)
    assert time_left("2026-09-17T12:00", thursday, 820) == ("Past due", "was due at 12:00", True)
    assert time_left("2026-09-16T21:00", thursday, 820) == ("Past due", "was due Wednesday 16", True)


def test_next_says_what_is_on_now_and_the_two_that_follow(qapp: QApplication) -> None:
    view = shown(qapp)
    assert text(view, "bentoNextLabel") == "Now"
    assert text(view, "bentoNextTitle") == "School"
    assert text(view, "bentoNextIn") == "50 min left"
    assert text(view, "bentoNextWhen") == "08:00 · 6 h 30 min"
    then = view.findChild(QLabel, "bentoNextThen").text()
    assert "Dinner at 18:00" in then and "Essay-1 at 18:45" in then and "Chem" not in then
    later = shown(qapp, clock="15:40")
    assert (text(later, "bentoNextLabel"), text(later, "bentoNextTitle")) == ("Next", "Dinner")
    assert text(later, "bentoNextIn") == "in 2 h 20 min"


def test_next_is_left_out_on_a_week_that_is_not_this_one(qapp: QApplication) -> None:
    view = shown(qapp, today=None)
    assert view.findChild(QWidget, "bentoNext") is None
    # With no now, Due soon has nothing to count down from, and still lists what is due.
    assert view.findChild(QLabel, "bentoDueUntil") is None
    assert view.findChild(QPushButton, "bentoDue0").property("block_id") == "chem-1"
    assert text(view, "bentoWaitingLabel") == "Not placed yet"


def test_the_load_tile_charts_the_weeks_homework_by_day(qapp: QApplication) -> None:
    view = shown(qapp)
    labels = [item.text() for item in view.findChild(QWidget, "bentoLoad").findChildren(QLabel)]
    # Monday's finished Math worksheet and Thursday's essay and Chem report, placed; the poster to go.
    assert {"3 h 15 min", "placed, 2 h to go"} <= set(labels)
    assert view.findChild(LoadBars, "bentoLoadBars").minutes == [45, 0, 0, 150, 0, 0, 0]


def test_the_legend_names_only_the_categories_the_week_has(qapp: QApplication) -> None:
    view = shown(qapp)
    assert view.findChild(QWidget, "bentoLegend").accessibleName() == "Colours: School, Homework, Meals"


def test_day_puts_the_days_summary_and_its_free_time_beside_its_hours(qapp: QApplication) -> None:
    view = shown(qapp, "day", clock="15:40")
    # School 6 h 30 min, Dinner 30 min, the essay 1 h and the Chem report 1 h 30 min.
    assert text(view, "bentoSumPlanned") == "9 h 30 min planned"
    # In the legend's order, the category's order in the app.
    assert texts(view, "bentoSumRowName") == ["School", "Homework", "Meals"]
    assert text(view, "bentoFreeLabel") == "Free from now"
    assert texts(view, "bentoFreeRowName") == ["15:40–18:00", "21:30–22:00"]
    friday = shown(qapp, "day", iso_day="2026-09-18")
    assert text(friday, "bentoHeroTitle") == "Friday 18"
    assert text(friday, "bentoFreeLabel") == "Free time"
    assert friday.findChild(QWidget, "bentoNext") is not None, "the tiles stay on Day"


def test_free_time_runs_from_the_first_block_to_ten_and_from_now_on_today() -> None:
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    thursday = week.on_day(3)
    # School to 14:30, Dinner 18:00, the essay 18:45 to 19:45, Chem 20:00 to 21:30: the quarter hours
    # between them are too short to list.
    assert free_slots(thursday, None) == [(870, 1080), (1290, 1320)]
    assert free_slots(thursday, minute_of("15:40")) == [(940, 1080), (1290, 1320)]
    assert free_slots((), None) == [(480, 1320)]


def test_a_half_hour_block_says_its_name_at_the_level_the_hours_open_at(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dinner is half an hour. In the body size the week's 44 pixels an hour left it no line."""
    written: list[str] = []
    real = canvas_module._paint_layout

    def spy(painter, lay, *rest) -> None:
        written.extend(line.text for line in lay)
        real(painter, lay, *rest)

    monkeypatch.setattr(canvas_module, "_paint_layout", spy)
    for surface, name in (("week", "bentoWeekHours"), ("day", "bentoDayHours")):
        written.clear()
        hours(shown(qapp, surface), name).grab()
        assert any(line.startswith("Dinner") for line in written), (surface, written)


def test_the_today_hero_swaps_in_the_day_a_tile_is_clicked_on(qapp: QApplication) -> None:
    view = shown(qapp, hero="today")
    assert [track.day for track in hours(view).tracks] == [3]
    tiles = {tile.property("day_target") for tile in view.findChildren(DayTile)}
    assert tiles == {0, 1, 2, 4, 5, 6}
    heading = view.findChild(QPushButton, "bentoHeroDay")
    assert heading.property("day_target") == 3
    assert hours(view).day_name(3) == heading.mapToGlobal(heading.rect().center())
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    view.findChild(DayTile, "bentoDay4").click()
    qapp.processEvents()
    assert [track.day for track in hours(view).tracks] == [4]
    assert {tile.property("day_target") for tile in view.findChildren(DayTile) if tile.isVisible()} == {
        0, 1, 2, 3, 5, 6,
    }
    assert opened == []
    # A new minute keeps Friday in the hero.
    view.show_week(scene(hero="today", clock="13:41"))
    qapp.processEvents()
    assert [track.day for track in hours(view).tracks] == [4]


def test_a_day_tile_on_day_opens_that_day(qapp: QApplication) -> None:
    view = shown(qapp, "day", hero="today")
    assert [track.day for track in hours(view).tracks] == [3]
    assert view.findChild(QLabel, "bentoSumPlanned") is not None
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    view.findChild(DayTile, "bentoDay4").click()
    assert opened == ["2026-09-18"]


def test_a_day_tile_says_its_first_item_its_load_its_homework_and_what_is_due(qapp: QApplication) -> None:
    view = shown(qapp, hero="today")

    def said(day: int) -> str:
        return view.findChild(DayTile, f"bentoDay{day}").accessibleDescription()

    # Monday: School, the finished Math worksheet and Dinner. Friday: the essay is due. Sunday: the
    # poster is due and only Dinner is planned.
    assert said(0) == "Monday 14, first School at 08:00, 7 h 45 min planned, 1 homework"
    assert said(4) == "Friday 18, first School at 08:00, 7 h planned, 1 due"
    assert said(6) == "Sunday 20, first Dinner at 18:00, 30 min planned, 1 due"


def test_a_pointed_at_day_lifts_and_does_not_rise_with_animations_off(qapp: QApplication) -> None:
    def pointed(view: BentoView) -> DayTile:
        tile = view.findChild(DayTile, "bentoDay4")
        at = QPointF(8, 8)
        QApplication.sendEvent(tile, QEnterEvent(at, at, QPointF(tile.mapToGlobal(QPoint(8, 8)))))
        return tile

    try:
        apply_ui_effects("normal")
        view = shown(qapp, hero="today")
        rest = view.findChild(DayTile, "bentoDay4").card()
        tile = pointed(view)
        QTest.qWait(LIFT_MS + 150)
        assert tile.lift == 1.0
        assert tile.card().top() == rest.top() - RISE
        apply_ui_effects("off")
        view = shown(qapp, hero="today")
        tile = pointed(view)
        assert tile.lift == 1.0, "lifted at once"
        assert tile.card() == rest, "and in place"
    finally:
        apply_ui_effects("normal")


def test_every_bento_colourway_paints_the_hero_in_words_that_read() -> None:
    palette = resolved_palette("light-frost", False, None, "default")
    for value, _, _ in LAYOUTS["bento"].colourways:
        tokens = tokens_for("bento", value, palette)
        for ink in ("hero_ink", "hero_muted"):
            assert contrast(tokens[ink], tokens["hero"]) >= AA_TEXT, (value, ink)
    assert "hero" not in tokens_for("bento", MATCH, palette)


def test_indigo_paints_the_hero_alone_and_match_my_look_keeps_it_a_card(qapp: QApplication) -> None:
    for colour in ("indigo", MATCH):
        view = shown(qapp, colour=colour)
        hero = view.findChild(QWidget, "bentoHero")
        tokens = view.scene.tokens
        picture = view.grab().toImage()
        inside = picture.pixelColor(hero.mapTo(view, QPoint(hero.width() // 2, 4))).name()
        assert inside == (tokens["hero"] if colour == "indigo" else tokens["surface"]), colour
        load = view.findChild(QWidget, "bentoLoad")
        assert picture.pixelColor(load.mapTo(view, QPoint(load.width() // 2, 4))).name() == tokens["surface"]


def test_day_and_week_keep_their_scroll_and_zoom_through_redraw(qapp: QApplication) -> None:
    view = shown(qapp)
    week = view._scrolls["week"]
    week.zoom_by(1)
    week_px = week.px
    week.verticalScrollBar().setValue(260)
    view.show_week(scene("week", clock="13:41"))
    qapp.processEvents()
    assert view._scrolls["week"] is week
    assert week.px == week_px
    assert week.verticalScrollBar().value() > 0
    view.show_week(scene("day"))
    qapp.processEvents()
    day = view._scrolls["day"]
    day.zoom_by(1)
    view.show_week(scene("week", clock="13:42"))
    qapp.processEvents()
    assert view._scrolls["week"] is week
    assert view._scrolls["day"] is day
    assert week.px == week_px
    view.show_week(scene("day", clock="13:43"))
    qapp.processEvents()
    assert view._scrolls["day"] is day
    assert day.px == DAY_SCALE.step(DAY_SCALE.default, 1)
    view.show_week(scene("month"))
    qapp.processEvents()
    assert view.hours_surfaces() == []
    assert view.month_surfaces()
    assert shiboken6.isValid(week)
    assert shiboken6.isValid(day)
    view.close()
    view.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(week)
    assert not shiboken6.isValid(day)


def test_the_tiles_stay_beside_the_hero_in_a_small_window(qapp: QApplication) -> None:
    view = shown(qapp, "day")
    hero = view.findChild(QLabel, "bentoHeroTitle")
    waiting = view.findChild(TrayChip, "bentoWaiting0")
    assert waiting.isVisible()
    assert waiting.mapToGlobal(waiting.rect().center()).x() > hero.mapToGlobal(hero.rect().center()).x()


def test_a_narrow_window_or_large_text_puts_the_tiles_under_the_hero(qapp: QApplication) -> None:
    for size, scale in (((800, 700), 1.0), ((1150, 768), 1.2)):
        view = shown(qapp, size=size, scale=scale)
        hero = view.findChild(QWidget, "bentoHero")
        due = view.findChild(QWidget, "bentoDue")
        assert due.geometry().top() > hero.geometry().bottom(), (size, scale)
        assert view.findChild(QWidget, "bentoScroll").horizontalScrollBar().maximum() == 0, (size, scale)


def test_an_uncategorized_block_remains_readable_in_midnight(qapp: QApplication) -> None:
    palette = resolved_palette("light-frost", False, None, "default")
    tokens = tokens_for("bento", "midnight", palette)
    block = Drawn("plain", "Untyped event", "", False, Span(3, 21 * 60, 22 * 60), 0, 1)
    fill, ink, _outline, _edge = BentoPainter(tokens).fills(block)
    assert fill.name() == tokens["surface"]
    assert ink.name() == tokens["text"]


def test_month_uses_the_shared_grid(qapp: QApplication) -> None:
    view = shown(qapp, "month")
    assert view.hours_surfaces() == []
    assert view.month_surfaces()
