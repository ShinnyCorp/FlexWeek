"""Shared fixtures for the native logic tests: a real local API and signed-in NativeSessions."""

from __future__ import annotations

import contextlib
import importlib.util
import os
import time
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from desktop.native.calendar import sunday_due
    from desktop.native.client import _error
    from desktop.native.controller import NativeSession
    from desktop.server import LocalServer

PASSWORD = "a-long-test-password"
HELD: list[object] = []
FOCUS_START_MS = 1_000_000
NEEDS_DESKTOP = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-native-logic-test"])
    yield application


@pytest.fixture()
def server(qapp: QApplication, tmp_path: Path) -> Iterator[LocalServer]:
    running = LocalServer(tmp_path / "flexweek.db")
    running.start()
    yield running
    for session in list(HELD):
        with contextlib.suppress(RuntimeError):
            session.client.reset()  # type: ignore[attr-defined]
    HELD.clear()
    qapp.processEvents()
    running.stop()


def wait_until(qapp: QApplication, predicate, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was still false")


def past_setup(qapp: QApplication, window: object) -> None:
    """A new account opens on setup. A test about the week skips it, and waits for the skip to be
    saved, since a save still in flight turns the test's own save away."""

    def on(name: str) -> bool:
        return window._stack.currentWidget().objectName() == name  # type: ignore[attr-defined]

    wait_until(qapp, lambda: on("setupPage"))
    window.setup_page.skip_all.click()  # type: ignore[attr-defined]
    wait_until(
        qapp,
        lambda: on("weekPage")
        and window.session.preferences is not None  # type: ignore[attr-defined]
        and not window._setup_prefs  # type: ignore[attr-defined]
        and not window.session.busy,  # type: ignore[attr-defined]
    )


def settled(qapp: QApplication, session: NativeSession) -> None:
    """Wait for the foreground request and the background refreshes it starts."""
    wait_until(qapp, lambda: not session.busy)
    wait_until(qapp, lambda: not any(session.client._replies.values()))


def signed_in(qapp: QApplication, origin: str, username: str, *, create: bool) -> NativeSession:
    session = NativeSession(origin, qapp)
    HELD.append(session)
    if create:
        session.register(username, PASSWORD)
        wait_until(qapp, lambda: session.account is not None)
        session.finish_recovery()
    else:
        session.login(username, PASSWORD)
    wait_until(qapp, lambda: session.account is not None and not session.busy)
    settled(qapp, session)
    return session


def fail_once(session: NativeSession, method: str, path: str, status: int = 503) -> None:
    """Refuse the next matching request the way the client reports a real reply with that status.

    Nothing reaches the server, which is what a 503 means for a write: nothing was stored.
    """
    real = session.client.request

    def request(verb, target, payload, on_success, on_error):
        if verb != method or not target.startswith(path):
            return real(verb, target, payload, on_success, on_error)
        session.client.request = real  # type: ignore[method-assign]
        QTimer.singleShot(0, lambda: on_error(_error(status)))
        return None

    session.client.request = request  # type: ignore[method-assign]


def fixed(block_id: str, title: str, day: int, start: str) -> dict:
    return {
        "id": block_id,
        "title": title,
        "kind": "locked",
        "duration_min": 60,
        "days": [day],
        "start": start,
    }


def week_after(week_start: str) -> str:
    return (date.fromisoformat(week_start) + timedelta(days=7)).isoformat()


def titles(blocks: list[dict]) -> list[str]:
    return [block["title"] for block in blocks]


def essay(session: NativeSession, estimate_min: int = 60) -> dict:
    return {
        "id": "essay",
        "title": "Essay",
        "due": sunday_due(session.week_start),
        "estimate_min": estimate_min,
        "revision": 0,
    }


def place_on_monday(qapp: QApplication, session: NativeSession) -> None:
    """Give the first block a Monday 16:00 start and save it."""
    session.blocks[0]["start"] = "16:00"
    session.blocks[0]["days"] = [0]
    session.save()
    settled(qapp, session)


def start_focus_on_first_block(session: NativeSession) -> None:
    session.now_ms = lambda: FOCUS_START_MS
    assert session.start_focus(session.blocks[0]["id"], 0) is True


def tick_focus_after_half_an_hour(qapp: QApplication, session: NativeSession) -> None:
    session.now_ms = lambda: FOCUS_START_MS + 30 * 60_000
    session.tick_focus()
    settled(qapp, session)
