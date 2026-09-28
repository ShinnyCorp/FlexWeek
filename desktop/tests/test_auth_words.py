"""The sign-in card's greeting and the recovery codes page (0.16 review rows R23 and R24).

"Welcome back." greeted a student who had never been there. The recovery codes were a plain label of
eight lines, kept only by selecting them with the mouse. Since 0.17 the greeting is the card's one
heading (decision 25), where it sat as a second heading under "Sign in".
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from desktop.native.kept import KeptSession
from desktop.native.window import NativeWindow
from desktop.server import LocalServer
from desktop.tests.window_support import (  # noqa: F401
    PASSWORD,
    USERNAME,
    free,
    qapp,
    server,
    wait_until,
)

FIRST = "Welcome to FlexWeek"
AGAIN = "Welcome back"


def page(window: NativeWindow) -> str:
    return window._stack.currentWidget().objectName()


@pytest.fixture()
def kept(tmp_path: Path) -> KeptSession:
    return KeptSession(tmp_path / "signed-in" / "flexweek.json")


@contextlib.contextmanager
def launched(server: LocalServer, kept: KeptSession) -> Iterator[NativeWindow]:  # noqa: F811
    window = NativeWindow(server.origin, kept=kept)
    window.show()
    try:
        yield window
    finally:
        with contextlib.suppress(RuntimeError):
            window.session.client.reset()
        window.hide()
        free(window)


def on_recovery_page(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    window.findChild(QPushButton, "authSwitch").click()
    window.username.setText(USERNAME)
    window.password.setText(PASSWORD)
    window.findChild(QPushButton, "createAccount").click()
    wait_until(qapp, lambda: page(window) == "recoveryPage")


def codes(window: NativeWindow) -> list[str]:
    return window.recovery_list.text().splitlines()


def greeting(window: NativeWindow) -> str:
    """The card's heading, once it is the only one: no line of small print is shown under it."""
    assert window.auth_note.isHidden(), window.auth_note.text()
    return window.auth_heading.text()


def test_a_first_launch_says_welcome_and_a_return_says_welcome_back(
    qapp: QApplication,  # noqa: F811
    server: LocalServer,  # noqa: F811
    kept: KeptSession,
) -> None:
    with launched(server, kept) as window:
        assert greeting(window) == FIRST
        on_recovery_page(qapp, window)
        window.recovery_ack.setChecked(True)
        window.recovery_continue.click()
        wait_until(qapp, lambda: not window.session.busy)
        window.session.logout()
        wait_until(qapp, lambda: page(window) == "authPage" and not window.session.busy)
        # Log out forgets the session, not that someone has been here.
        assert kept.token() is None
        assert greeting(window) == AGAIN
    with launched(server, kept) as window:
        assert greeting(window) == AGAIN
        window.findChild(QPushButton, "authSwitch").click()
        assert window.auth_note.text().startswith("FlexWeek fits homework around school and sports.")
        window.findChild(QPushButton, "authSwitch").click()
        assert greeting(window) == AGAIN


def test_signing_in_without_keeping_the_session_still_counts_as_having_been_here(
    qapp: QApplication,  # noqa: F811
    server: LocalServer,  # noqa: F811
    kept: KeptSession,
    tmp_path: Path,
) -> None:
    with launched(server, KeptSession(tmp_path / "other" / "flexweek.json")) as window:
        on_recovery_page(qapp, window)
    with launched(server, kept) as window:
        assert greeting(window) == FIRST
        window.keep_signed_in.setChecked(False)
        window.username.setText(USERNAME)
        window.password.setText(PASSWORD)
        window.sign_in_button.click()
        wait_until(qapp, lambda: window.session.account is not None and not window.session.busy)
        assert kept.token() is None
    with launched(server, kept) as window:
        assert greeting(window) == AGAIN


@pytest.fixture()
def recovering(qapp: QApplication, server: LocalServer, kept: KeptSession) -> Iterator[NativeWindow]:  # noqa: F811
    with launched(server, kept) as window:
        on_recovery_page(qapp, window)
        yield window


def evenly_spaced(font: QFont) -> bool:
    """Every letter as wide as every other, so 1 and l, 0 and O line up and read apart."""
    metrics = QFontMetrics(font)
    return metrics.horizontalAdvance("iiii1111") == metrics.horizontalAdvance("WWWW0000")


def test_the_codes_are_in_inter_with_figures_of_one_width(recovering: NativeWindow) -> None:
    """DejaVu Sans Mono was a second face, heavier and wider than Inter around it (decision 25)."""
    assert len(codes(recovering)) == 8
    font = recovering.recovery_list.font()
    assert font.family() == "Inter"
    assert not evenly_spaced(font), "not a fixed-width face"
    metrics = QFontMetrics(font)
    assert metrics.horizontalAdvance("1111") == metrics.horizontalAdvance("0000"), "figures of one width"


def test_copy_puts_every_code_on_the_clipboard_and_says_so_for_a_moment(
    qapp: QApplication,  # noqa: F811
    recovering: NativeWindow,
) -> None:
    QApplication.clipboard().clear()
    recovering.recovery_copy.click()
    assert QApplication.clipboard().text().splitlines() == codes(recovering)
    assert recovering.recovery_copy.text() == "Copied"
    wait_until(qapp, lambda: recovering.recovery_copy.text() == "Copy", timeout=4.0)


def test_save_writes_the_codes_one_per_line_where_the_student_chose(
    qapp: QApplication,  # noqa: F811
    recovering: NativeWindow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chosen = tmp_path / "my-codes.txt"
    monkeypatch.setattr(recovering, "_choose_recovery_file", lambda: str(chosen))
    assert recovering.recovery_save.text() == "Save…"
    recovering.recovery_save.click()
    assert chosen.read_text().splitlines() == codes(recovering)
    assert recovering.recovery_save.text() == "Saved"
    wait_until(qapp, lambda: recovering.recovery_save.text() == "Save…", timeout=4.0)


def test_save_cancelled_writes_nothing_and_a_folder_it_cannot_write_says_so(
    recovering: NativeWindow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recovering, "_choose_recovery_file", lambda: "")
    recovering.recovery_save.click()
    assert list(tmp_path.glob("*.txt")) == []
    assert recovering.recovery_save.text() == "Save…"
    monkeypatch.setattr(recovering, "_choose_recovery_file", lambda: str(tmp_path / "missing" / "codes.txt"))
    recovering.recovery_save.click()
    assert recovering.recovery_status.isVisibleTo(recovering)
    assert recovering.recovery_status.text() == "FlexWeek could not save the codes there. Try another folder."
    assert recovering.recovery_save.text() == "Save…"


def test_the_default_file_name_is_offered_to_the_dialog(
    recovering: NativeWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from desktop.native import window as window_module

    asked: list[str] = []

    def answer(_parent: object, _caption: str, name: str, _kinds: str) -> tuple[str, str]:
        asked.append(name)
        return "", ""

    monkeypatch.setattr(window_module.QFileDialog, "getSaveFileName", staticmethod(answer))
    recovering.recovery_save.click()
    assert asked == ["flexweek-recovery-codes.txt"]


def test_both_cards_show_the_icon_beside_the_wordmark(
    qapp: QApplication,  # noqa: F811
    recovering: NativeWindow,
) -> None:
    for name in ("authPage", "recoveryPage"):
        card = next(page for page in recovering._stack.findChildren(QWidget) if page.objectName() == name)
        icon = card.findChild(QLabel, "authLogo")
        brand = card.findChild(QLabel, "authBrand")
        assert brand.text() == "FlexWeek"
        assert icon is not None and not icon.pixmap().isNull(), name
        assert icon.pixmap().deviceIndependentSize().toSize() == QSize(28, 28)
        assert icon.parentWidget() is brand.parentWidget()
        assert icon.geometry().right() < brand.geometry().left(), "the icon comes first"
        assert abs(icon.geometry().center().y() - brand.geometry().center().y()) <= 4
