"""Audit finding 8: a preference that failed to save is not taken for saved."""

from __future__ import annotations

import importlib.util

import pytest

pytest_plugins = ["desktop.tests.window_support"]

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication

    from desktop.native.window import NativeWindow
    from desktop.tests.audit_support import reconnect, refuse_all
    from desktop.tests.window_support import qapp, wait_until, window  # noqa: F401

# The fixtures are used by name, so each test's argument list redefines them.
# ruff: noqa: F811


def test_a_preference_that_failed_to_save_is_sent_again_when_settings_close(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Audit finding 8: the page took a queued request for a saved one, so after the connection came
    back, closing Settings sent nothing and the old length returned."""
    window._open_settings()
    page = window._settings
    assert page is not None
    sent = refuse_all(window, "PUT", "/api/preferences")
    page.work.setValue(45)
    wait_until(qapp, lambda: len(sent) == 1)
    assert sent[0]["timer_work_min"] == 45
    wait_until(qapp, lambda: not window.session.busy)
    reconnect(window)
    window._close_settings()
    wait_until(qapp, lambda: not window.session.busy)
    assert window.session.preferences["timer_work_min"] == 45
