"""Audit finding 6: leaving the app saves what is unsaved first."""

from __future__ import annotations

import importlib.util

import pytest

pytest_plugins = ["desktop.tests.window_support"]

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication

    import desktop.native.window as window_module
    from desktop.native.window import NativeWindow
    from desktop.tests.audit_support import reconnect, refuse_all
    from desktop.tests.logic_support import fixed
    from desktop.tests.window_support import qapp, wait_until, window  # noqa: F401

# The fixtures are used by name, so each test's argument list redefines them.
# ruff: noqa: F811


class Leaving:
    """Stands in for QApplication.quit, noting what was still unsaved at the moment of leaving."""

    def __init__(self, window: NativeWindow) -> None:
        self.window = window
        self.calls: list[bool] = []

    def __call__(self) -> None:
        session = self.window.session
        self.calls.append(bool(session.dirty or session.dirty_assignments or session.pending_save))


@pytest.fixture()
def leaving(window: NativeWindow, monkeypatch: pytest.MonkeyPatch) -> Leaving:
    gone = Leaving(window)
    monkeypatch.setattr(QApplication, "quit", staticmethod(gone))
    return gone


def test_quit_saves_a_preference_that_has_not_reached_the_server(
    qapp: QApplication, window: NativeWindow, leaving: Leaving
) -> None:
    """Audit finding 6: Quit before the 600 ms timer fired dropped the change."""
    window._open_settings()
    window._settings.work.setValue(45)
    window.quit_app()
    wait_until(qapp, lambda: bool(leaving.calls))
    assert window.session.preferences["timer_work_min"] == 45


def test_quit_waits_for_a_week_save_that_failed_and_is_being_retried(
    qapp: QApplication, window: NativeWindow, leaving: Leaving
) -> None:
    session = window.session
    sent = refuse_all(window, "POST", "/api/changes")
    session.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    session.save()
    wait_until(qapp, lambda: len(sent) >= 1 and not session.busy)
    assert session.pending_save is not None
    reconnect(window)
    window.quit_app()
    wait_until(qapp, lambda: bool(leaving.calls))
    assert leaving.calls == [False]
    session.reload()
    wait_until(qapp, lambda: not session.busy and [b["id"] for b in session.blocks] == ["soccer"])


def test_quit_that_cannot_save_stays_open_and_says_so(
    qapp: QApplication, window: NativeWindow, leaving: Leaving
) -> None:
    session = window.session
    refuse_all(window, "POST", "/api/changes")
    session.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    session.save()
    wait_until(qapp, lambda: not session.busy and session.pending_save is not None)
    window.quit_app()
    wait_until(qapp, lambda: "Not saved" in session.message and not window._quitting)
    assert leaving.calls == []
    assert window._quitting is False
    assert session.pending_save is not None


def test_a_wait_that_runs_out_stays_open_and_says_so(
    qapp: QApplication, window: NativeWindow, leaving: Leaving, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = window.session
    real = session.client.request
    session.client.request = lambda *call: None if call[1].startswith("/api/changes") else real(*call)  # type: ignore[method-assign]
    monkeypatch.setattr(window_module, "LEAVE_WAIT_MS", 300)
    session.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    window.quit_app()
    wait_until(qapp, lambda: "Not saved" in session.message)
    assert leaving.calls == []


def test_closing_the_window_waits_for_unsaved_changes(qapp: QApplication, window: NativeWindow) -> None:
    session = window.session
    sent = refuse_all(window, "POST", "/api/changes")
    session.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    session.save()
    wait_until(qapp, lambda: len(sent) >= 1 and not session.busy)
    reconnect(window)
    window.close()
    assert window.isVisible()
    wait_until(qapp, lambda: not window.isVisible())
    assert session.pending_save is None and not session.dirty
