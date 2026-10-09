"""Sign in as 0.17 draws it (decision 25): the wordmark on the page above one card, rounded as a sheet
and lifted with the large shadow, one heading, an eye inside the password box, Forgot password only
where there is a password to forget, and nothing cut at Large text.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics
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

from desktop.native.look import resolved_palette, sanitize_look
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
    # Signed out, the page wears the device's look (#74); these tests dress it as an account's.
    window.session.account = {"id": "dressed", "username": "dressed"}
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
    page = signed_out._stack.currentWidget()
    brand = page.findChild(QLabel, "authBrand")
    logo = page.findChild(QLabel, "authLogo")
    assert brand is not None and logo is not None, "the sign-in page has no wordmark and logo"
    assert not held.isAncestorOf(brand), "the wordmark is on the page, not in the card"
    brand_box = brand.geometry().united(logo.geometry())
    # The card sits in a holder, so its place on the page is mapped, not read off its own geometry.
    card_top = held.mapTo(page, QPoint(0, 0)).y()
    card_centre = held.mapTo(page, QPoint(held.width() // 2, 0)).x()
    assert brand.mapTo(page, QPoint(0, brand.height())).y() < card_top
    assert abs(brand_box.center().x() - card_centre) <= 2, "centred over the card"


def test_the_card_has_one_heading_and_create_account_hides_forgot_password(
    signed_out: NativeWindow,  # noqa: F811
) -> None:
    window = signed_out
    assert window.auth_heading.text() == "Sign in"
    assert not window.auth_note.isVisibleTo(window), "no second heading under the first"
    assert shown(window, "forgotPassword")
    window.auth_switch.click()
    assert window.auth_heading.text() == "Create your account"
    assert window.auth_note.isVisibleTo(window)
    assert window.auth_note.text() == (
        "FlexWeek fits homework around school and sports. "
        "Your week is saved on this computer, under this account."
    )
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
    assert window.auth_heading.text() == "Sign in"
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


def test_the_name_is_said_once_not_again_in_the_heading(signed_out: NativeWindow) -> None:  # noqa: F811
    """The wordmark sat right above "Welcome to FlexWeek"."""
    window = signed_out
    page = window._stack.currentWidget()
    for mode in ("sign in", "create", "reset"):
        window._entry_mode = mode
        window._sync_auth_mode()
        QApplication.processEvents()
        assert "FlexWeek" not in window.auth_heading.text(), (mode, window.auth_heading.text())
        marks = [label for label in page.findChildren(QLabel) if label.text() == "FlexWeek"]
        assert [label.objectName() for label in marks] == ["authBrand"], mode


def test_creating_an_account_carries_more_weight_than_forgot_password(
    signed_out: NativeWindow,  # noqa: F811
) -> None:
    """The two links under Sign in were drawn alike; most students on a first run need the one that
    makes an account."""
    window = signed_out
    assert shown(window, "forgotPassword") and shown(window, "authSwitch")
    assert window.auth_switch.font().weight() > window.forgot_button.font().weight()
    assert window.auth_switch.font().weight() == QFont.Weight.DemiBold
    assert window.forgot_button.font().weight() == QFont.Weight.Normal


def ink(widget: QWidget) -> QColor:
    """The darkest fully drawn pixel of a link: its words' colour, not the faded edge of a letter."""
    image = widget.grab().toImage()
    solid = [
        image.pixelColor(x, y)
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() == 255
    ]
    return min(solid, key=lambda pixel: pixel.lightness())


def underlined(widget: QPushButton) -> bool:
    """A row drawn across nearly the whole width of the words: a letter's bar never is."""
    image = widget.grab().toImage()
    words = QFontMetrics(widget.font()).horizontalAdvance(widget.text())
    wide = range(image.width())
    rows = (sum(image.pixelColor(x, y).alpha() == 255 for x in wide) for y in range(image.height()))
    return max(rows) >= words * 0.9


def distance(one: QColor, other: QColor) -> int:
    return abs(one.red() - other.red()) + abs(one.green() - other.green()) + abs(one.blue() - other.blue())


@pytest.mark.parametrize("name", ["forgotPassword", "authSwitch"])
@pytest.mark.parametrize("how", ["keyboard", "pointer"])
def test_a_link_in_reach_keeps_the_accent_darker_and_underlined(
    signed_out: NativeWindow,  # noqa: F811
    name: str,
    how: str,
) -> None:
    """It went near-black on hover and, reached by the keyboard, showed nothing at all."""
    window = signed_out
    pack, dark, accent = window._look_inputs()
    palette = resolved_palette(pack, dark, window._look, accent)
    link = window.findChild(QPushButton, name)
    resting = ink(link)
    assert distance(resting, QColor(palette["accent"])) <= 12, "at rest it is the accent"
    assert not underlined(link)
    if how == "keyboard":
        window.activateWindow()
        QTest.qWaitForWindowActive(window)
        link.setFocus(Qt.FocusReason.TabFocusReason)
    else:
        QTest.mouseMove(link, QPoint(link.width() // 2, link.height() // 2))
    QApplication.processEvents()
    reached = ink(link)
    assert underlined(link), "underlined, so the colour is not the only sign"
    assert reached.lightness() < resting.lightness(), "darker than at rest"
    assert distance(reached, QColor(palette["accent"])) < distance(reached, QColor(palette["text"])), (
        f"still the accent, not near-black: {reached.name()}"
    )


def test_a_wrong_sign_in_is_a_short_red_line_under_the_password_box(
    signed_out: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#73: the sentence is "Wrong username or password." in the look's error colour with a warning
    icon, directly under the password box and above Keep me signed in; the explanation is a link."""
    window = signed_out
    window.show()
    QApplication.processEvents()
    before = card(window).height()
    window._on_status("Wrong username or password.")
    QApplication.processEvents()
    text = window.auth_error_text
    assert window.auth_error.isVisibleTo(window)
    assert text.text() == "Wrong username or password."
    assert not window.auth_status.isVisibleTo(window), "the long sentence is not also at the foot"
    pack, dark, accent = window._look_inputs()
    error = resolved_palette(pack, dark, window._look, accent)["error"]
    text.ensurePolished()
    assert text.palette().color(text.foregroundRole()).name() == error
    assert not window.auth_error_icon.pixmap().isNull()
    top = window.auth_error.mapTo(window, QPoint(0, 0)).y()
    assert top >= window.password.mapTo(window, QPoint(0, window.password.height())).y()
    assert top + window.auth_error.height() <= window.keep_signed_in.mapTo(window, QPoint(0, 0)).y()
    assert window.auth_why.text() == "Why doesn't it say which?"
    # The line and its link, plus the one gap the card puts between rows, and no more: the old
    # sentence added 75 px.
    gap = card(window).layout().spacing()
    assert card(window).height() - before <= window.auth_error.height() + gap

    shown_sheets = []
    monkeypatch.setattr(
        "desktop.native.window.ConfirmSheet.exec", lambda self: shown_sheets.append(self.question.text())
    )
    window.auth_why.click()
    assert shown_sheets == ["FlexWeek doesn't say which, so no one can find out who has an account."]
