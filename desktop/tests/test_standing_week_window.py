"""Deleting School or a Setup activity asks "Just this week" or "Every week" (fix-specs item 1)."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton

from desktop.native.widgets import ConfirmSheet
from desktop.native.window import NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
)
from desktop.tests.window_support import window as signed_in  # noqa: F401

SOCCER = {"id": "activity-1", "title": "Soccer", "kind": "locked", "category": "extra", "start": "16:00",
          "duration_min": 90, "days": [1, 3]}


@pytest.fixture()
def window(qapp: QApplication, signed_in: NativeWindow) -> Iterator[NativeWindow]:
    """Setup's Soccer in the open week."""
    signed_in.findChild(QPushButton, "viewWeek").click()
    settled(qapp, signed_in)
    signed_in.session.set_setup_blocks([dict(SOCCER)])
    signed_in.session.save()
    wait_until(qapp, lambda: not signed_in.session.busy and not signed_in.session.dirty)
    settled(qapp, signed_in)
    yield signed_in


def pick(monkeypatch: pytest.MonkeyPatch, key: str) -> list[str]:
    asked: list[str] = []

    def run(sheet: ConfirmSheet) -> int:
        asked.append(sheet.windowTitle() or sheet.objectName())
        sheet.answer = key
        return 0

    monkeypatch.setattr(ConfirmSheet, "exec", run)
    return asked


def soccer(window: NativeWindow) -> dict | None:
    return next((b for b in window.session.blocks if b["id"] == "activity-1"), None)


def delete_soccer(qapp: QApplication, window: NativeWindow) -> None:
    window._delete_block(soccer(window), "series", None)
    wait_until(qapp, lambda: not window.session.busy and not window.session.dirty)
    settled(qapp, window)


def test_just_this_week_keeps_soccer_here_missed_on_every_day(qapp, window, monkeypatch) -> None:
    asked = pick(monkeypatch, "week")
    delete_soccer(qapp, window)
    assert asked
    assert soccer(window)["missed_days"] == [1, 3]
    assert window.toast.text() == "Deleted Soccer."


def test_every_week_takes_soccer_out_and_says_so(qapp, window, monkeypatch) -> None:
    pick(monkeypatch, "every")
    delete_soccer(qapp, window)
    assert soccer(window) is None
    assert window.toast.text() == "Removed Soccer from this week and every week after it."


def test_cancel_deletes_nothing(qapp, window, monkeypatch) -> None:
    pick(monkeypatch, "stay")
    delete_soccer(qapp, window)
    kept = soccer(window)
    assert kept is not None and not kept.get("missed_days")
