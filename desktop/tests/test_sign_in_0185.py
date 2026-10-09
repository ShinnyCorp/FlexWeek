"""0.18.5 #74: the sign-in pages. One heading, a wordmark and card top that never move, hints under their
own field, a readable eye, field edges at 3 to 1, and the device's own look whoever was here last."""

# ruff: noqa: F811  (pytest fixtures imported by name)

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QSize
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QToolButton, QWidget

from desktop.native.look import resolved_palette, sanitize_look
from desktop.native.tokens import contrast
from desktop.native.window import NativeWindow
from desktop.tests.test_auth_words import kept, launched, on_recovery_page, page  # noqa: F401
from desktop.tests.window_support import (  # noqa: F401
    PASSWORD,
    USERNAME,
    look_file,
    qapp,
    server,
    signed_out,
    wait_until,
    window,
)

MODES = ("sign in", "create", "reset")
# Worked out from the requirement, not read off the code: System pack, Light and Dark.
DEVICE_LIGHT_PAGE, DEVICE_DARK_PAGE = "#f7f8fa", "#111315"
PASTEL_PAGE = "#f3ecff"


def pump() -> None:
    for _ in range(4):
        QApplication.processEvents()


def go(window: NativeWindow, mode: str) -> None:
    window._entry_mode = mode
    window._sync_auth_mode()
    pump()


def card_of(window: NativeWindow) -> QFrame:
    return window._stack.currentWidget().findChild(QFrame, "authCard")


def page_pixel(window: NativeWindow, x: int = 6, y: int = 6) -> QColor:
    return window.grab().toImage().pixelColor(x, y)


def near(colour: QColor, hex_colour: str, slack: int = 4) -> bool:
    other = QColor(hex_colour)
    return all(abs(a - b) <= slack for a, b in zip(colour.getRgb()[:3], other.getRgb()[:3], strict=True))


# One heading.


def test_the_heading_is_sign_in_on_a_first_launch_and_on_a_return(qapp, server, kept) -> None:
    with launched(server, kept) as window:
        assert window.auth_heading.text() == "Sign in"
        on_recovery_page(qapp, window)
        window.recovery_ack.setChecked(True)
        window.recovery_continue.click()
        wait_until(qapp, lambda: not window.session.busy)
        window.session.logout()
        wait_until(qapp, lambda: page(window) == "authPage" and not window.session.busy)
        assert kept.signed_in_before()
        assert window.auth_heading.text() == "Sign in"
    with launched(server, kept) as window:
        assert kept.signed_in_before()
        assert window.auth_heading.text() == "Sign in"


# A wordmark and a card top that stay put.


def test_the_wordmark_and_the_card_top_do_not_move_between_the_three_pages(signed_out) -> None:
    window = signed_out
    window.resize(1366, 768)
    pump()
    seen = {}
    for mode in MODES:
        go(window, mode)
        stage = window._stack.currentWidget()
        brand = stage.findChild(QLabel, "authBrand")
        seen[mode] = (
            brand.mapTo(stage, QPoint(0, 0)).y(),
            card_of(window).mapTo(stage, QPoint(0, 0)).y(),
            card_of(window).height(),
        )
    assert seen["sign in"][:2] == seen["create"][:2] == seen["reset"][:2], seen
    # The shorter pages simply end sooner; they are not stretched to the Create card's height.
    assert seen["sign in"][2] < seen["create"][2], seen


def test_the_pinned_position_is_the_one_the_create_card_needs(signed_out) -> None:
    """Centred as the tallest page makes it: as much room above the wordmark as under the Create card."""
    window = signed_out
    window.resize(1366, 768)
    go(window, "create")
    stage = window._stack.currentWidget()
    brand = stage.findChild(QLabel, "authBrand")
    above = brand.mapTo(stage, QPoint(0, 0)).y()
    held = card_of(window)
    below = stage.height() - (held.mapTo(stage, QPoint(0, 0)).y() + held.height())
    assert abs(above - below) <= 40, (above, below)
    go(window, "sign in")
    assert brand.mapTo(stage, QPoint(0, 0)).y() == above


# Hints.


def test_a_hint_sits_4_px_under_its_own_field_and_16_px_before_the_next(signed_out) -> None:
    window = signed_out
    go(window, "create")
    held = card_of(window)

    def top(widget: QWidget) -> int:
        return widget.mapTo(held, QPoint(0, 0)).y()

    def bottom(widget: QWidget) -> int:
        return top(widget) + widget.height()

    assert top(window.username_hint) - bottom(window.username) == 4
    assert top(window.password) - bottom(window.username_hint) == 16
    assert top(window.password_hint) - bottom(window.password) == 4
    assert top(window.keep_signed_in) - bottom(window.password_hint) == 16


def test_a_wrong_sign_in_is_still_said_right_under_the_password_box(signed_out) -> None:
    window = signed_out
    go(window, "sign in")
    window.auth_error.setVisible(True)
    pump()
    held = card_of(window)
    gap = window.auth_error.mapTo(held, QPoint(0, 0)).y() - (
        window.password.mapTo(held, QPoint(0, 0)).y() + window.password.height()
    )
    assert gap == 4


# The eye.


def test_the_eye_is_a_24_px_glyph_in_a_32_px_box_at_3_to_1(signed_out) -> None:
    window = signed_out
    eye = window.password.findChild(QToolButton, "passwordReveal")
    assert eye.iconSize() == QSize(24, 24)
    assert (eye.width(), eye.height()) == (32, 32)
    image = eye.grab().toImage()
    field = QColor(resolved_palette("system", False, sanitize_look(None))["field"])
    background = image.pixelColor(0, 0)
    drawn = [
        (x, image.pixelColor(x, y))
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y) != background
    ]
    assert drawn, "the eye is not drawn"
    xs = [x for x, _pixel in drawn]
    assert 18 <= max(xs) - min(xs) + 1 <= 24, "a 24 px glyph"
    ink = [pixel for _x, pixel in drawn]
    darkest = min(ink, key=lambda pixel: pixel.lightness())
    assert contrast(darkest.name(), field.name()) >= 3.0


# The device's own look.


def sign_out_from_a_pastel_account(qapp, window: NativeWindow) -> None:
    """A signed-in account whose look is Pastel, then Sign out."""
    window._look = sanitize_look({"preset": "pastel"})
    window._apply_appearance()
    pump()
    assert PASTEL_PAGE in window.styleSheet(), "the account wears its own look"
    window.session.logout()
    wait_until(qapp, lambda: page(window) == "authPage" and not window.session.busy)
    pump()


def test_after_sign_out_the_page_is_the_devices_look_not_the_last_accounts(qapp, window) -> None:
    sign_out_from_a_pastel_account(qapp, window)
    assert near(page_pixel(window), DEVICE_LIGHT_PAGE), page_pixel(window).name()
    assert PASTEL_PAGE not in window.styleSheet()


def test_after_a_restart_the_page_is_the_devices_look_despite_a_stored_pastel(qapp, server, kept) -> None:
    look_file().parent.mkdir(parents=True, exist_ok=True)
    look_file().write_text(json.dumps({"preset": "pastel", "knobs": {}}) + "\n")
    try:
        with launched(server, kept) as window:
            pump()
            assert near(page_pixel(window), DEVICE_LIGHT_PAGE), page_pixel(window).name()
    finally:
        look_file().unlink(missing_ok=True)


def test_a_dark_computer_gets_a_dark_sign_in_page_and_light_goes_back_to_light(qapp, server, kept) -> None:
    original = QGuiApplication.palette()
    dark = QPalette(original)
    dark.setColor(QPalette.ColorRole.Window, QColor("#202124"))
    QGuiApplication.setPalette(dark)
    try:
        with launched(server, kept) as window:
            pump()
            assert near(page_pixel(window), DEVICE_DARK_PAGE), page_pixel(window).name()
    finally:
        QGuiApplication.setPalette(original)


def test_signing_in_puts_the_accounts_own_look_back_on(qapp, window) -> None:
    sign_out_from_a_pastel_account(qapp, window)
    assert PASTEL_PAGE not in window.styleSheet(), "signed out: the device's look"
    window.username.setText(USERNAME)
    window.password.setText(PASSWORD)
    window.sign_in_button.click()
    wait_until(qapp, lambda: window.session.account is not None and not window.session.busy)
    pump()
    assert PASTEL_PAGE in window.styleSheet(), "signed in: the account's look"


# Field edges.


@pytest.mark.parametrize("dark", [False, True], ids=["light computer", "dark computer"])
def test_the_sign_in_fields_have_an_edge_at_3_to_1_on_field_and_card(qapp, server, kept, dark) -> None:
    original = QGuiApplication.palette()
    if dark:
        night = QPalette(original)
        night.setColor(QPalette.ColorRole.Window, QColor("#202124"))
        QGuiApplication.setPalette(night)
    try:
        with launched(server, kept) as window:
            window.resize(1366, 768)
            go(window, "create")
            palette = resolved_palette("system", dark, sanitize_look(None))
            for field in (window.username, window.password):
                image = field.grab().toImage()
                edge = image.pixelColor(0, image.height() // 2)
                assert contrast(edge.name(), palette["field"]) >= 3.0, (field.objectName(), edge.name())
                assert contrast(edge.name(), palette["panel"]) >= 3.0, (field.objectName(), edge.name())
    finally:
        QGuiApplication.setPalette(original)


def test_the_focused_sign_in_field_still_shows_the_accent(qapp, signed_out) -> None:
    window = signed_out
    go(window, "sign in")
    window.username.setFocus()
    pump()
    image = window.username.grab().toImage()
    palette = resolved_palette("system", False, sanitize_look(None))
    edge = image.pixelColor(0, image.height() // 2)
    assert near(edge, palette["accent"], slack=8), edge.name()
