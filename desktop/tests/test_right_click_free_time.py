"""A right-click on free time opens its menu every time, with a mouse or a touchpad: a press and release that
moves a few pixels still counts."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from desktop.native.window import NativeWindow
from desktop.tests.grid_support import (  # noqa: F401
    WEDNESDAY,
    in_window,
    menus,
    right_click,
    window,
)
from desktop.tests.window_support import (  # noqa: F401
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
)
from desktop.tests.window_support import window as signed_in  # noqa: F401


def test_every_right_click_on_free_time_opens_the_menu(
    qapp: QApplication, window: NativeWindow, menus: list[dict]
) -> None:
    at = in_window(window, WEDNESDAY, 10 * 60)
    for attempt in range(30):
        right_click(window, at)
        assert len(menus) == attempt + 1, f"right-click {attempt + 1} opened no menu"
    assert {shown["name"] for shown in menus} == {"spotMenu"}


def test_a_right_click_that_slides_a_few_pixels_still_opens_the_menu(
    qapp: QApplication, window: NativeWindow, menus: list[dict]
) -> None:
    at = in_window(window, WEDNESDAY, 10 * 60)
    for attempt, jitter in enumerate((QPoint(3, 2), QPoint(-2, 4), QPoint(0, -3), QPoint(4, 0))):
        right_click(window, at, jitter)
        assert len(menus) == attempt + 1, f"a right-click that moved {jitter} opened no menu"
