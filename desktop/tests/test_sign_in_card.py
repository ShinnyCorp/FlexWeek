"""Sign in as 0.17 draws it (decision 25): the wordmark on the page above one card, rounded as a sheet
and lifted with the large shadow, one heading, an eye inside the password box, Forgot password only
where there is a password to forget, and nothing cut at Large text.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from desktop.native.look import sanitize_look
from desktop.native.tokens import SHADOW_LARGE
from desktop.native.window import NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    qapp,
    server,
    signed_out,
    wait_until,
)


def card(window: NativeWindow, page: str = "authPage") -> QFrame:
    holder = next(child for child in window._stack.findChildren(QWidget) if child.objectName() == page)
    return holder.findChild(QFrame, "authCard")


def dress(window: NativeWindow, monkeypatch: pytest.MonkeyPatch, pack: str, **look: object) -> None:
    monkeypatch.setattr(window, "_look_inputs", lambda: (pack, False, "default"))
    window._look = sanitize_look(look)
    window._apply_appearance()
    QApplication.processEvents()


def shown(window: NativeWindow, name: str) -> bool:
    return window.findChild(QWidget, name).isVisibleTo(window)


def whole(widget: QWidget) -> bool:
    if isinstance(widget, QLabel) and widget.wordWrap():
        return widget.height() >= widget.heightForWidth(widget.width())
    hint = widget.sizeHint()
    return widget.width() >= hint.width() and widget.height() >= hint.height()


def test_the_wordmark_sits_on_the_page_centred_above_the_card(signed_out: NativeWindow) -> None:  # noqa: F811
    held = card(signed_out)
    brand = signed_out._stack.currentWidget().findChild(QLabel, "authBrand")
    assert not held.isAncestorOf(brand), "the wordmark is on the page, not in the card"
    page = signed_out._stack.currentWidget()
    brand_box = brand.geometry().united(page.findChild(QLabel, "authLogo").geometry())
    card_box = held.geometry()
    assert brand.mapTo(page, QPoint(0, brand.height())).y() < card_box.top()
    assert abs(brand_box.center().x() - card_box.center().x()) <= 2, "centred over the card"


def test_the_card_has_one_heading_and_create_account_hides_forgot_password(
    signed_out: NativeWindow,  # noqa: F811
) -> None:
    window = signed_out
    assert window.auth_heading.text() == "Welcome to FlexWeek"
    assert not window.auth_note.isVisibleTo(window), "no second heading under the first"
    assert shown(window, "forgotPassword")
    window.auth_switch.click()
    assert window.auth_heading.text() == "Create your account"
    assert not shown(window, "forgotPassword"), "a new account has no password to forget"
    window.auth_switch.click()
    assert shown(window, "forgotPassword")


def test_forgot_password_is_the_cards_own_page_with_one_filled_button(
    signed_out: NativeWindow,  # noqa: F811
) -> None:
    """It opened a second form under Sign in: two filled buttons and two passwords at once."""
    window = signed_out
    window.findChild(QPushButton, "forgotPassword").click()
    assert window.auth_heading.text() == "Reset your password"
    answers = [name for name in ("signIn", "createAccount", "recoverAccount") if shown(window, name)]
    assert answers == ["recoverAccount"]
    assert not window.password.isVisibleTo(window), "only the new password is asked for"
    assert window.recovery_code.isVisibleTo(window) and window.new_recovery_password.isVisibleTo(window)
    assert not shown(window, "forgotPassword")
    assert window.auth_switch.text() == "Back to sign in"
    window.auth_switch.click()
    assert window.auth_heading.text() == "Welcome to FlexWeek"
    assert [name for name in ("signIn", "createAccount", "recoverAccount") if shown(window, name)] == [
        "signIn"
    ]
    assert not window.recovery_code.isVisibleTo(window)


def test_the_eye_sits_inside_the_password_box_and_shows_and_hides_it(
    qapp: QApplication,  # noqa: F811
    signed_out: NativeWindow,  # noqa: F811
) -> None:
    window = signed_out
    QApplication.processEvents()
    assert window.password.width() == window.username.width(), "the box keeps the card's full width"
    eye = window.password_reveal
    assert eye.parentWidget() is window.password
    assert window.password.rect().contains(eye.geometry())
    assert eye.geometry().right() > window.password.width() - 12, "at the box's right edge"
    assert eye.toolTip() == "Show password"
    window.password.setText("a-long-test-password")
    eye.setFocus(Qt.FocusReason.TabFocusReason)
    QTest.keyClick(eye, Qt.Key.Key_Space)
    assert window.password.echoMode() == QLineEdit.EchoMode.Normal, "the keyboard shows it too"
    assert eye.toolTip() == "Hide password"
    window._on_account(None)
    assert window.password.echoMode() == QLineEdit.EchoMode.Password, "a log out hides it again"


def test_the_card_is_a_sheet_lifted_with_the_large_shadow_where_the_look_has_shadows(
    signed_out: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = signed_out
    dress(window, monkeypatch, "dark-frost")
    for name in ("authPage", "recoveryPage"):
        effect = card(window, name).graphicsEffect()
        assert isinstance(effect, QGraphicsDropShadowEffect), name
        assert (effect.yOffset(), effect.blurRadius()) == (SHADOW_LARGE.y, SHADOW_LARGE.blur)
    held = card(window)
    picture = window.grab().toImage()
    top_left = held.mapTo(window, QPoint(3, 3))
    middle = held.mapTo(window, QPoint(held.width() // 2, 4))
    corner, inside = picture.pixelColor(top_left), picture.pixelColor(middle)
    assert inside == QColor("#1a1d21"), inside.name()
    # Three pixels in lies clear of a 16-pixel corner, and on the edge of a 10-pixel one, a card's.
    assert inside.lightness() - corner.lightness() >= 5, "the corner is rounded as a sheet"
    dress(window, monkeypatch, "light-frost", preset="default", knobs={"depth": "none"})
    assert card(window).graphicsEffect() is None, "a look with no shadows lifts nothing"


@pytest.mark.parametrize("mode", ["sign in", "create", "reset"])
def test_every_line_on_the_card_is_whole_at_large_text(
    signed_out: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    window = signed_out
    dress(window, monkeypatch, "light-frost", knobs={"text": "large"})
    if mode == "create":
        window.auth_switch.click()
    if mode == "reset":
        window.findChild(QPushButton, "forgotPassword").click()
    QApplication.processEvents()
    held = card(window)
    parts = [*held.findChildren(QLabel), *held.findChildren(QCheckBox), *held.findChildren(QPushButton)]
    cut = [part.text() for part in parts if part.isVisibleTo(window) and part.text() and not whole(part)]
    assert cut == []
