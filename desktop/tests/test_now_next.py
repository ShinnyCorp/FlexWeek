"""The line over Today's app's week that says what is on now and what is next. Its countdown moves with
the clock, not only while a focus timer ticks."""

from __future__ import annotations

import contextlib
import importlib.util
import os
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtWidgets import QApplication, QPushButton

    from desktop.native.window import NativeWindow
    from desktop.server import LocalServer
    from desktop.tests.logic_support import past_setup

PASSWORD = "a-long-test-password"


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-now-next-test"])


def wait_until(qapp: QApplication, predicate: Callable[[], bool], timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was still false")


def pump(qapp: QApplication, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)


@pytest.fixture()
def window(qapp: QApplication, tmp_path: Path) -> Iterator[tuple[NativeWindow, list[datetime]]]:
    """Today's app's Week, signed in, with Dinner every day at 18:00 and the clock held at Thursday
    15:40. The clock is the list's one item; a test moves it on."""
    server = LocalServer(tmp_path / "flexweek.db")
    server.start()
    made = NativeWindow(server.origin)
    made.resize(1280, 860)
    made.show()
    try:
        made.username.setText("countdown_student")
        made.password.setText(PASSWORD)
        made.findChild(QPushButton, "createAccount").click()
        wait_until(qapp, lambda: made._stack.currentWidget().objectName() == "recoveryPage")
        made.recovery_ack.setChecked(True)
        made.recovery_continue.click()
        past_setup(qapp, made)
        session = made.session
        clock = [datetime.fromisoformat(session.week_start) + timedelta(days=3, hours=15, minutes=40)]
        session.now_ms = lambda: int(clock[0].timestamp() * 1000)
        session.add_block(
            {"id": "dinner", "title": "Dinner", "kind": "locked", "category": "meals",
             "start": "18:00", "duration_min": 30, "days": [0, 1, 2, 3, 4, 5, 6]}
        )
        session.save()
        wait_until(qapp, lambda: not session.busy and not session.dirty)
        made.findChild(QPushButton, "viewWeek").click()
        # The refreshes a save starts redraw the week when they land; none may be left to land
        # during the test and redraw the line for it.
        wait_until(qapp, lambda: not session.busy and not any(session.client._replies.values()))
        pump(qapp, 0.2)
        yield made, clock
    finally:
        with contextlib.suppress(RuntimeError):
            made.session.client.reset()
        made.hide()
        qapp.processEvents()
        server.stop()


def test_the_next_and_now_countdowns_move_with_the_minute_without_a_focus_timer(
    qapp: QApplication, window: tuple[NativeWindow, list[datetime]]
) -> None:
    made, clock = window
    # On the week, what is next is the rail's card: "Next", what, and when.
    card = made.rail.next

    def said() -> tuple[str, str, str]:
        return card.label.text(), card.title.text(), card.when.text()

    line = card
    assert made.session.focus is None
    assert card.isVisible()
    assert said() == ("Next", "Dinner", "18:00 · in 2 h 20 min")
    # The window looks at the clock on its own timer; here it looks every 20 ms, not every 20 s.
    made._layout_tick.setInterval(20)
    clock[0] += timedelta(minutes=1)
    pump(qapp, 0.3)
    assert said() == ("Next", "Dinner", "18:00 · in 2 h 19 min")
    clock[0] += timedelta(hours=2, minutes=29)
    pump(qapp, 0.3)
    assert said() == ("Now", "Dinner", "until 18:30 · 20 min left")
    clock[0] += timedelta(minutes=1)
    pump(qapp, 0.3)
    assert said() == ("Now", "Dinner", "until 18:30 · 19 min left")
    clock[0] += timedelta(minutes=19)
    pump(qapp, 0.3)
    assert not line.isVisible(), "nothing now or next today, so the card takes no room"
