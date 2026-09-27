"""Signing in, signing up and leaving, in words that say what went wrong (0.15 rows 14, 20, 36).

Sign-in said "Check the required fields, dates, times and lengths" for an empty password, a short
one and a mistyped username alike, and "Your changes may not have been saved" when the server was
gone. Sign-up repeated the hint already on screen for an empty password, so nothing seemed to
happen. Log out and Delete account went ahead on one click.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from desktop.native import window as window_module
from desktop.native.settings import AccountDialog
from desktop.native.window import NativeWindow
from desktop.server import LocalServer
from desktop.tests.window_support import (  # noqa: F401
    PASSWORD,
    USERNAME,
    qapp,
    server,
    signed_out,
    wait_until,
    window,
)


def press(qapp: QApplication, window: NativeWindow, name: str, username: str, password: str) -> str:  # noqa: F811
    wanted = window.findChild(QPushButton, name)
    if wanted.isHidden():
        window.findChild(QPushButton, "authSwitch").click()
    window.username.setText(username)
    window.password.setText(password)
    window.session._say("")
    wanted.click()
    wait_until(qapp, lambda: not window.session.busy and bool(window.auth_status.text()))
    return window.auth_status.text()


@pytest.fixture()
def returning(qapp: QApplication, window: NativeWindow) -> NativeWindow:  # noqa: F811
    """An account exists and has signed out, so the next person at the window signs in."""
    window.session.logout()
    wait_until(qapp, lambda: window.session.account is None and not window.session.busy)
    return window


WRONG = "Wrong username or password. FlexWeek doesn't say which, so no one can find out who has an account."


@pytest.mark.parametrize(
    ("username", "password", "said"),
    [
        ("", PASSWORD, "Type your username."),
        (USERNAME, "", "Type your password."),
        (USERNAME, "not-the-right-password", WRONG),
        ("nobody_by_this_name", PASSWORD, WRONG),
        (
            USERNAME,
            "short",
            "That password is too short to be right. FlexWeek passwords have 12–128 characters.",
        ),
        (
            "has spaces",
            PASSWORD,
            "No FlexWeek username looks like that. Usernames are 3–32 letters, numbers or underscores.",
        ),
    ],
)
def test_sign_in_says_what_went_wrong(
    qapp: QApplication,  # noqa: F811
    returning: NativeWindow,
    username: str,
    password: str,
    said: str,
) -> None:
    assert press(qapp, returning, "signIn", username, password) == said
    assert returning.session.account is None


def test_sign_in_says_when_flexweek_cannot_be_reached(
    qapp: QApplication,  # noqa: F811
    returning: NativeWindow,
    server: LocalServer,  # noqa: F811
) -> None:
    server.stop()
    said = press(qapp, returning, "signIn", USERNAME, PASSWORD)
    assert said == "FlexWeek can't reach its server. Close FlexWeek, open it again, then sign in."


@pytest.mark.parametrize(
    ("username", "password", "said"),
    [
        ("new_student", "", "Choose a password. It needs 12–128 characters."),
        ("new_student", "short", "That password is too short. It needs at least 12 characters."),
        ("", PASSWORD, "Choose a username: 3–32 letters, numbers or underscores."),
        (USERNAME, PASSWORD, "That username is taken. Choose another one."),
    ],
)
def test_sign_up_says_what_went_wrong(
    qapp: QApplication,  # noqa: F811
    returning: NativeWindow,
    username: str,
    password: str,
    said: str,
) -> None:
    assert press(qapp, returning, "createAccount", username, password) == said
    assert returning.session.account is None


def test_account_says_where_the_plans_are_saved_in_a_sentence(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    wait_until(qapp, lambda: window.session.storage_info is not None)
    dialog = AccountDialog(window, window.session.recovery_remaining, window.session.storage_info)
    assert dialog.findChild(QLabel, "accountLocation").text() == (
        "Signed in as words_student. Your plans are saved on this computer."
    )


def asked_with(monkeypatch: pytest.MonkeyPatch, answer: bool) -> list[tuple[str, str, str, bool]]:
    asked: list[tuple[str, str, str, bool]] = []

    def confirm(_parent, title: str, question: str, yes: str, *, danger: bool = True) -> bool:
        asked.append((title, question, yes, danger))
        return answer

    monkeypatch.setattr(window_module, "confirm", confirm)
    return asked


LOG_OUT = (
    "Log out",
    "Log out of FlexWeek on this computer? Your plans stay saved in your account. You'll need your "
    "password to sign in again.",
    "Log out",
    False,  # Nothing is lost, so the answer is not drawn red.
)


def test_log_out_asks_first_and_stays_signed_in_when_refused(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = asked_with(monkeypatch, False)
    window.findChild(QPushButton, "signOut").click()
    qapp.processEvents()
    assert asked == [LOG_OUT]
    assert window.session.account is not None and window._stack.currentWidget().objectName() == "weekPage"
    asked = asked_with(monkeypatch, True)
    window.findChild(QPushButton, "signOut").click()
    wait_until(qapp, lambda: window.session.account is None)
    assert asked == [LOG_OUT]


def open_account_and_delete(window: NativeWindow, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    def run(dialog: AccountDialog) -> int:
        dialog.current_password.setText(PASSWORD)
        dialog.findChild(QPushButton, "deleteAccount").click()
        return dialog.result()

    monkeypatch.setattr(AccountDialog, "exec", run)
    window._open_account()


DELETE = (
    "Delete account",
    "Delete the account words_student? Every week, all your homework and your settings are removed "
    "from this computer. This can't be undone.",
    "Delete words_student",
    True,
)


def test_delete_account_names_the_account_and_keeps_it_when_refused(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wait_until(qapp, lambda: window.session.storage_info is not None)
    deleted: list[str] = []
    monkeypatch.setattr(window.session, "delete_account", lambda password: deleted.append(password))
    asked = asked_with(monkeypatch, False)
    open_account_and_delete(window, monkeypatch)
    assert asked == [DELETE]
    assert deleted == []
    asked = asked_with(monkeypatch, True)
    open_account_and_delete(window, monkeypatch)
    assert asked == [DELETE]
    assert deleted == [PASSWORD]


def test_the_recovery_codes_left_are_an_ordinary_fact_until_none_are(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """"8 unused recovery codes remain." was in the error red. Red is for a problem (decision 8 of
    0.17), and codes left are not one until there are none."""
    from desktop.native.look import resolved_palette

    pack, dark, accent = window._look_inputs()
    palette = resolved_palette(pack, dark, window._look, accent)
    for remaining, colour in ((8, palette["muted"]), (0, palette["error"])):
        dialog = AccountDialog(window, remaining, {"username": "student"})
        dialog.show()
        qapp.processEvents()
        label = dialog.findChild(QLabel, "recoveryCount")
        label.ensurePolished()
        assert label.palette().color(label.foregroundRole()).name() == colour, remaining
        dialog.close()
