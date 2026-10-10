"""The sign-in card is measured by laying out its tallest page and going back (`_pin_auth_height`).
Hiding a widget that has focus moves focus off it, so the measuring must leave focus where it was
(0.18.5 review, finding 3)."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton

from desktop.native.window import NativeWindow
from desktop.tests.window_support import qapp, server, signed_out  # noqa: F401


def active(qapp: QApplication, window: NativeWindow) -> None:
    window.show()
    window.activateWindow()
    for _ in range(5):
        qapp.processEvents()


def test_dressing_the_sign_in_page_again_keeps_focus_on_forgot_password(
    qapp: QApplication, signed_out: NativeWindow
) -> None:
    window = signed_out
    active(qapp, window)
    forgot = window.findChild(QPushButton, "forgotPassword")
    forgot.setFocus()
    assert window.focusWidget() is forgot
    window._pin_auth_height()
    assert window.focusWidget() is forgot


def test_dressing_the_reset_page_again_keeps_the_cursor_in_the_recovery_code_box(
    qapp: QApplication, signed_out: NativeWindow
) -> None:
    window = signed_out
    active(qapp, window)
    window.findChild(QPushButton, "forgotPassword").click()
    qapp.processEvents()
    window.recovery_code.setFocus()
    assert window.focusWidget() is window.recovery_code
    window._pin_auth_height()
    assert window.focusWidget() is window.recovery_code
