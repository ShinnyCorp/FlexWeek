"""The remaining design animations follow the screen without changing their paths or ends."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QRectF
from PySide6.QtWidgets import QApplication

from desktop.native import motion
from desktop.tests.test_motion import Hours

LEVELS = ["normal", "extra", "reduce", "off"]


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication(["flexweek-motion-clocks"])



def clock_at(clock, length, share=0.5):
    assert isinstance(clock, motion.Clock), "this animation must use the screen-rate clock"
    assert clock.interval() == 3, "360 Hz screens require a 3 ms clock"
    assert clock.duration() == length
    clock.pause()
    clock.setCurrentTime(length * share)


@pytest.fixture(autouse=True)
def screen_clock(monkeypatch):
    monkeypatch.setattr(motion, "screen_rate", lambda _: 360)
    yield
    motion.apply_ui_effects("off")


@pytest.mark.parametrize("level", LEVELS)
def test_hours_settle_keeps_easing_and_its_final_rectangle(qapp, level):
    motion.apply_ui_effects("off")
    hours = Hours(qapp)
    canvas = hours.canvas
    key = ("homework", 2)
    before, target = QRectF(0, 0, 40, 30), QRectF(80, 0, 40, 30)
    canvas._last_rects = {key: target}
    motion.apply_ui_effects(level)
    canvas._settle_from({key: before})
    if level == "off":
        assert canvas._shown_rect(key, target) == target
        assert not canvas._slides and not canvas._fresh
    else:
        clock_at(canvas._settling, motion.duration(180, level))
        assert canvas._progress == pytest.approx(0.875)
        assert canvas._shown_rect(key, target).x() == (70 if level != "reduce" else 80)
        canvas._settling.setCurrentTime(canvas._settling.duration())
        assert canvas._shown_rect(key, target) == target
        assert not canvas._slides and not canvas._fresh
    hours.window.close()


@pytest.mark.parametrize("level", LEVELS)
def test_zoom_glide_keeps_its_scroll_path_and_end(qapp, level):
    from desktop.tests.test_hours_zoom import a_lane_week, settle

    scroll = a_lane_week(qapp)
    scroll.resize(400, 420)
    settle(qapp)
    bar = scroll.horizontalScrollBar()
    scroll.scroll_to(9 * 60, above=0)
    settle(qapp)
    start = bar.value()
    scroll.scroll_to(17 * 60, above=60)
    end = bar.value()
    assert end > start
    bar.setValue(start)
    scroll.reveal(17 * 60, 60, level)
    if level in ("reduce", "off"):
        assert bar.value() == end
    else:
        clocks = [clock for clock in scroll.findChildren(motion.Clock) if clock.parent() is scroll]
        assert len(clocks) == 1, "one reveal has one screen-rate clock"
        clock = clocks[0]
        clock_at(clock, motion.duration(240, level))
        assert bar.value() == round(start + (end - start) * 0.875)
        clock.setCurrentTime(clock.duration())
        assert bar.value() == end
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert [clock for clock in scroll.findChildren(motion.Clock) if clock.parent() is scroll] == []
    scroll.close()


@pytest.mark.parametrize("level", LEVELS)
def test_bento_lift_keeps_its_cubic_path_and_end(qapp, level):
    from desktop.native.layouts.bento import DayTile
    from desktop.tests.test_layout_bento import shown

    motion.apply_ui_effects(level)
    view = shown(qapp, hero="today")
    tile = view.findChild(DayTile)
    tile._lifting.stop()
    tile.lift = 0.0
    tile._aim(True)
    if level in ("reduce", "off"):
        assert tile.lift == 1.0
    else:
        clock_at(tile._lifting, motion.duration(200, level))
        assert tile.lift == pytest.approx(0.875)
        tile._lifting.setCurrentTime(tile._lifting.duration())
        assert tile.lift == 1.0
        tile._aim(False)
        clock_at(tile._lifting, motion.duration(200, level))
        assert tile.lift == pytest.approx(0.125)
        tile._lifting.setCurrentTime(tile._lifting.duration())
        assert tile.lift == 0.0
    view.close()


@pytest.mark.parametrize("level", LEVELS)
def test_dial_hand_keeps_its_cubic_path_and_end(qapp, level):
    from desktop.native.layouts.dial import DialFace

    motion.apply_ui_effects(level)
    face = DialFace(2, False)
    face._now = 900
    face.ease_hand(780)
    if level in ("reduce", "off"):
        assert face._hand_at is None
    else:
        clock_at(face._easing, motion.duration(240, level))
        assert face._hand_at == pytest.approx(885)
        face._easing.setCurrentTime(face._easing.duration())
        assert face._hand_at is None
    face.close()


@pytest.mark.parametrize("level", LEVELS)
def test_retro_zoom_keeps_its_linear_path_and_end(qapp, level):
    from desktop.native.layouts.retro import Zoom
    from desktop.tests.test_layout_retro import shown

    motion.apply_ui_effects("off")
    view = shown(qapp)
    motion.apply_ui_effects(level)
    start = QRectF(10, 20, 30, 40)
    view._zoom("notes", start)
    flights = view.findChildren(Zoom)
    if level in ("reduce", "off"):
        assert flights == []
    else:
        assert len(flights) == 1
        flight = flights[0]
        clocks = flight.findChildren(motion.Clock)
        assert len(clocks) == 1, "the rectangle uses the screen-rate clock"
        clock_at(clocks[0], motion.duration(200, level))
        assert flight.share == pytest.approx(0.5), "Retro's rectangle was linear"
        clocks[0].setCurrentTime(clocks[0].duration())
        assert flight.share == 1.0
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert view.findChildren(Zoom) == []
    view.close()


@pytest.mark.parametrize("level", LEVELS)
def test_ring_keeps_its_cubic_arc_and_end(qapp, level):
    from desktop.native.ring import CountdownRing

    ring = CountdownRing()
    ring.run_down(1.0, 0.2, level)
    if level in ("reduce", "off"):
        assert ring.left() == 0.2
    else:
        clock_at(ring._ease, motion.duration(300, level))
        assert ring.left() == pytest.approx(0.3)
        ring._ease.setCurrentTime(ring._ease.duration())
        assert ring.left() == pytest.approx(0.2)
    ring.run_down(0.2, 0.8, level)
    assert ring.left() == 0.8, "a new countdown never eases backwards"
    ring.close()


def test_bento_off_is_instant_even_for_a_tile_built_with_motion(qapp):
    from desktop.native.layouts.bento import DayTile
    from desktop.tests.test_layout_bento import shown

    motion.apply_ui_effects("normal")
    view = shown(qapp, hero="today")
    tile = view.findChild(DayTile)
    tile._lifting.stop()
    tile.lift = 0.0
    motion.apply_ui_effects("off")
    tile._aim(True)
    assert tile.lift == 1.0
    view.close()


def test_dials_finished_clock_clears_its_hand_even_if_the_live_minute_changed(qapp):
    from desktop.native.layouts.dial import DialFace

    motion.apply_ui_effects("normal")
    face = DialFace(2, False)
    face._now = 900
    face.ease_hand(780)
    face._now = None
    face._easing.setCurrentTime(240)
    assert face._hand_at is None
    face.close()
