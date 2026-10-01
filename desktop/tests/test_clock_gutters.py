"""Hour labels and the now pill fit the space painted for them in every design."""

from __future__ import annotations

import importlib.util
import re
import time
from datetime import datetime

import pytest

from desktop.tests.test_hours_open import DESIGNS

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QRect, QRectF
    from PySide6.QtGui import QFontMetricsF, QPainter
    from PySide6.QtWidgets import QApplication, QPushButton

    from desktop.native.hours import canvas as canvas_module
    from desktop.native.hours.zoom import HoursScroll
    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.look import sanitize_look
    from desktop.native.window import NativeWindow
    from desktop.tests.test_hours_open import hours, wait_until
    from desktop.tests.test_hours_open import qapp as qapp
    from desktop.tests.test_hours_open import window as window


def whole(painted: QRectF, scroll: HoursScroll) -> bool:
    """Whether a label's box lies inside the canvas, so no edge of it cuts the words."""
    return painted.left() >= -0.5 and painted.right() <= scroll.canvas.width() + 0.5


def overlapping(calls: list[tuple[str, QRectF, QRectF, float, float]]) -> list[tuple[str, str]]:
    """The pairs of labels whose words, not just their boxes, cover each other."""
    pairs = []
    for index, (text, _box, painted, width, height) in enumerate(calls):
        words = QRectF(painted.center().x() - width / 2, painted.center().y() - height / 2, width, height)
        for other, _box2, painted2, width2, height2 in calls[index + 1:]:
            words2 = QRectF(painted2.center().x() - width2 / 2, painted2.center().y() - height2 / 2,
                            width2, height2)
            if words.intersects(words2):
                pairs.append((text, other))
    return pairs


def settle(qapp: QApplication, window: NativeWindow) -> None:
    """Until the hours on screen have kept one size for a tenth of a second. Clay's Day card slides
    in from 35 px, where its hours have no room, and a grab before it arrives finds no labels."""
    last, since = None, time.monotonic()
    deadline = since + 8
    while time.monotonic() < deadline:
        qapp.processEvents()
        size = hours(window).size()
        if size != last:
            last, since = size, time.monotonic()
        elif time.monotonic() - since > 0.1:
            return
        time.sleep(0.01)
    raise AssertionError("the hours never stopped changing size")


@pytest.fixture
def written(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, QRectF, QRectF, float, float]]:
    """Every clock time the hours' painter writes: the words, the box they are written in, that box
    where it lands on the canvas, and the width and height the words need."""
    calls: list[tuple[str, QRectF, QRectF, float, float]] = []

    class Wrote(QPainter):
        def drawText(self, *args: object) -> None:  # noqa: N802
            text = next(arg for arg in reversed(args) if isinstance(arg, str))
            if re.fullmatch(r"\d{1,2}:\d{2}(?: [AP]M)?", text):
                box = next(arg for arg in args if isinstance(arg, (QRect, QRectF)))
                calls.append((text, QRectF(box), self.worldTransform().mapRect(QRectF(box)),
                              QFontMetricsF(self.font()).horizontalAdvance(text),
                              QFontMetricsF(self.font()).height()))
            super().drawText(*args)

    monkeypatch.setattr(canvas_module, "QPainter", Wrote)
    return calls


@pytest.mark.parametrize("design", DESIGNS)
@pytest.mark.parametrize("clock", ["12h", "24h"])
@pytest.mark.parametrize("text_size", ["normal", "large"])
@pytest.mark.parametrize("window_px", [810, 1280])
def test_the_hours_and_now_label_fit_their_painted_boxes(
    qapp: QApplication, window: NativeWindow, written: list[tuple[str, QRectF, QRectF, float, float]],
    design: str, clock: str, text_size: str, window_px: int,
) -> None:
    calls = written
    session = window.session
    session.preferences = {**session.preferences, "clock_24h": clock == "24h"}
    window._layout = sanitize_layout({"main": design, "day": "one"})
    window._look = sanitize_look({"knobs": {"text": text_size}})
    window._apply_appearance()
    window.resize(window_px, 800)
    window._on_week()
    for chosen in ("24h", "12h", clock):
        # What Settings does when the student picks a format.
        session.preferences = {**session.preferences, "clock_24h": chosen == "24h"}
        window._apply_appearance()
        window._sync_chrome()
        settle(qapp, window)
        scroll = hours(window)
        calls.clear()
        assert not scroll.canvas.grab().isNull()
        assert calls, f"{design} draws no clock labels after changing format"
        assert all(
            width <= box.width() + 0.5
            and (scroll.axis.value != "down" or whole(painted, scroll))
            for _text, box, painted, width, _height in calls
        ), (design, chosen, text_size, window_px, calls)
    for tab in ("viewWeek", "viewDay"):
        window.findChild(QPushButton, tab).click()
        wait_until(qapp, lambda: not session.busy)
        if tab == "viewDay":
            session.open_day(datetime.fromtimestamp(session.now_ms() / 1000).date().isoformat())
            wait_until(qapp, lambda: not session.busy)
        settle(qapp, window)
        scroll = hours(window)
        for level in scroll.scale.levels:
            scroll.restore({scroll.scale.key: level})
            for minute in (6 * 60, 12 * 60, 18 * 60):
                scroll.scroll_to(minute, None)
                for _ in range(4):
                    qapp.processEvents()
                calls.clear()
                assert not scroll.canvas.grab().isNull()
                assert calls, f"{design} {tab} draws no hours"
                for text, box, painted, width, height in calls:
                    assert width <= box.width() + 0.5, (design, tab, clock, text_size, level, text, box)
                    assert height <= box.height() + 0.5, (design, tab, clock, text_size, level, text, box)
                    if scroll.axis.value == "down":
                        assert whole(painted, scroll), (design, tab, clock, text_size, text, painted)
                crowded = overlapping(calls)
                assert not crowded, (design, tab, clock, text_size, level, minute, crowded)


@pytest.mark.parametrize("design", DESIGNS)
def test_a_new_text_size_gives_the_hours_the_room_their_labels_need(
    qapp: QApplication, window: NativeWindow, written: list[tuple[str, QRectF, QRectF, float, float]],
    design: str,
) -> None:
    session = window.session
    session.preferences = {**session.preferences, "clock_24h": False}
    window._layout = sanitize_layout({"main": design, "day": "one"})
    window.resize(810, 800)
    for text_size in ("normal", "large", "small", "large"):
        window._look = sanitize_look({"knobs": {"text": text_size}})
        window._apply_appearance()
        window._on_week()
        settle(qapp, window)
        scroll = hours(window)
        written.clear()
        assert not scroll.canvas.grab().isNull()
        assert written, f"{design} draws no clock labels at {text_size} text"
        for text, box, painted, width, _height in written:
            assert width <= box.width() + 0.5, (design, text_size, text, box)
            if scroll.axis.value == "down":
                assert whole(painted, scroll), (design, text_size, text, painted)


@pytest.mark.parametrize("design", DESIGNS)
@pytest.mark.parametrize("text_size", ["normal", "large"])
def test_the_now_pill_is_whole_beside_the_hours_as_the_minutes_pass_to_its_widest(
    qapp: QApplication, window: NativeWindow, written: list[tuple[str, QRectF, QRectF, float, float]],
    design: str, text_size: str,
) -> None:
    """The pill is written in 600, wider than an hour label, and 12:58 PM is as wide as it gets;
    the gutter is made at 9:05 AM, where it is narrower."""
    session = window.session
    session.preferences = {**session.preferences, "clock_24h": False}
    day = datetime.fromtimestamp(session.now_ms() / 1000)
    window._layout = sanitize_layout({"main": design, "day": "one"})
    window._look = sanitize_look({"knobs": {"text": text_size}})
    window._apply_appearance()
    window.resize(810, 800)
    for hour, minute, words in ((9, 5, "9:05 AM"), (12, 58, "12:58 PM")):
        held = day.replace(hour=hour, minute=minute)
        session.now_ms = lambda held=held: int(held.timestamp() * 1000)
        if words == "9:05 AM":
            window._sync_chrome()
            window._on_week()
        else:
            window._refresh_layout()
        settle(qapp, window)
        scroll = hours(window)
        scroll.scroll_to(hour * 60 + minute, None)
        settle(qapp, window)
        written.clear()
        assert not scroll.canvas.grab().isNull()
        pill = [call for call in written if call[0] == words]
        assert pill, f"{design} writes no now pill at {words}: {[call[0] for call in written]}"
        for text, box, painted, width, _height in pill:
            assert width <= box.width() + 0.5, (design, text_size, box)
            if scroll.axis.value == "down":
                assert whole(painted, scroll), (design, text_size, text, painted)
            if design == "timeline":
                # It sits in the gutter, clear of the first day's blocks.
                assert painted.right() <= scroll.canvas.tracks[0].area.left() - 2.5, (text_size, painted)
