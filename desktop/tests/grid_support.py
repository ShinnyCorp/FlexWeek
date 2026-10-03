"""A signed-in classic Week with the clock held, and what the grid's pointer and keyboard tests share."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from desktop.native import window as window_module
from desktop.native.hours.canvas import HoursCanvas
from desktop.native.menus import Menu
from desktop.native.window import NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
)
from desktop.tests.window_support import window as signed_in  # noqa: F401

NONE = Qt.KeyboardModifier.NoModifier
WEDNESDAY = 2
PIANO = {
    "id": "piano",
    "kind": "locked",
    "title": "Piano",
    "category": "extra",
    "start": "15:00",
    "duration_min": 60,
    "days": [WEDNESDAY],
}


def hold_clock(window: NativeWindow, day: int, minute: int) -> None:
    moment = datetime.fromisoformat(window.session.week_start) + timedelta(days=day, minutes=minute)
    window.session.now_ms = lambda: int(moment.timestamp() * 1000)
    window._fill_classic()
    QApplication.processEvents()


@pytest.fixture()
def window(qapp: QApplication, signed_in: NativeWindow) -> Iterator[NativeWindow]:
    """The classic Week on Wednesday 14:07 of the open week, with one early block on Monday: a week
    with nothing in it shows a button in place of the hours."""
    signed_in.resize(1280, 860)
    signed_in._layout = {"main": "classic", "day": "one", "options": {}}
    signed_in.session.add_block({**PIANO, "id": "early", "title": "Early", "start": "06:00", "days": [0]})
    signed_in.session.save()
    settled(qapp, signed_in)
    signed_in.findChild(QPushButton, "viewWeek").click()
    settled(qapp, signed_in)
    signed_in.show()
    assert QTest.qWaitForWindowExposed(signed_in)
    signed_in.activateWindow()
    wait_until(qapp, signed_in.isActiveWindow)
    hold_clock(signed_in, WEDNESDAY, 14 * 60 + 7)
    yield signed_in


@pytest.fixture()
def menus(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Every menu shown, with its name and words and where it was asked for. None is chosen."""
    seen: list[dict] = []

    class Shown(Menu):
        def exec(self, at: QPoint | None = None, *_rest: object) -> object:
            seen.append({"name": self.objectName(), "rows": [a.text() for a in self.actions()], "at": at})
            return None

    monkeypatch.setattr(window_module, "Menu", Shown)
    return seen


def grid(window: NativeWindow) -> HoursCanvas:
    return window.week_table.hours


def key(window: NativeWindow, which: Qt.Key, mods: Qt.KeyboardModifier = NONE) -> None:
    """A key from the system, to whatever the window has focused."""
    QTest.keyClick(window.windowHandle(), which, mods)
    QApplication.processEvents()


def tab_to_grid(window: NativeWindow) -> None:
    """Tab from the top of the page until the week is reached."""
    window.prev_nav.setFocus(Qt.FocusReason.TabFocusReason)
    for _ in range(40):
        key(window, Qt.Key.Key_Tab)
        focus = window.focusWidget()
        if focus is not None and (focus is window.week_table or window.week_table.isAncestorOf(focus)):
            if window.week_table.scroll.header.isAncestorOf(focus):
                continue  # the zoom buttons come first, in the corner
            assert focus is grid(window), f"Tab reached {type(focus).__name__} before the grid"
            return
    raise AssertionError("Tab never reached the week")


def in_window(window: NativeWindow, day: int, minute: int) -> QPoint:
    hours = grid(window)
    hours.reveal(day, minute, minute + 15)
    QApplication.processEvents()
    return window.mapFromGlobal(hours.point_for(day, minute))


def right_click(window: NativeWindow, at: QPoint, jitter: QPoint | None = None) -> None:
    """A right press and release through the window's handle, as the system sends them."""
    handle = window.windowHandle()
    QTest.mousePress(handle, Qt.MouseButton.RightButton, NONE, at)
    QTest.mouseRelease(handle, Qt.MouseButton.RightButton, NONE, at + (jitter or QPoint(0, 0)))
    QApplication.processEvents()


def add_piano(qapp: QApplication, window: NativeWindow) -> None:
    window.session.add_block(dict(PIANO))
    window.session.save()
    settled(qapp, window)
    hold_clock(window, WEDNESDAY, 14 * 60 + 7)
