"""A signed-in window on a real local API, for tests that drive the window as a student does."""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QStandardPaths
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from desktop.native.window import NativeWindow
from desktop.server import LocalServer
from desktop.tests.logic_support import past_setup

PASSWORD = "a-long-test-password"
USERNAME = "words_student"


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    application = QApplication.instance() or QApplication(["flexweek-words-test"])
    yield application


def wait_until(qapp: QApplication, predicate: Callable[[], bool], timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was still false")


def settled(qapp: QApplication, window: NativeWindow) -> None:
    wait_until(qapp, lambda: not window.session.busy and not window.session.dirty)


def free(widget: QWidget) -> None:
    """Delete a widget now. Left to the garbage collector, a widget a failed test still held went in
    the middle of a later test's event loop, and Qt crashed."""
    widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


@pytest.fixture()
def host(qapp: QApplication) -> Iterator[QWidget]:
    """A parent for dialogs a test makes on their own, freed when the test ends, pass or fail."""
    made = QWidget()
    yield made
    free(made)


@pytest.fixture()
def server(qapp: QApplication, tmp_path: Path) -> Iterator[LocalServer]:
    running = LocalServer(tmp_path / "flexweek.db")
    running.start()
    yield running
    running.stop()


def look_file() -> Path:
    """The device look file, shared by every suite through ~/.qttest; a test that saved a knob would
    otherwise hand it to the next."""
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(root) / "flexweek-look.json"


@pytest.fixture()
def signed_out(qapp: QApplication, server: LocalServer) -> Iterator[NativeWindow]:
    look_file().unlink(missing_ok=True)
    window = NativeWindow(server.origin)
    window.show()
    try:
        yield window
    finally:
        with contextlib.suppress(RuntimeError):
            window.session.client.reset()
        window.hide()
        free(window)


@pytest.fixture()
def window(qapp: QApplication, signed_out: NativeWindow) -> NativeWindow:
    """Signed in on the week page, setup skipped, preferences loaded."""
    signed_out.username.setText(USERNAME)
    signed_out.password.setText(PASSWORD)
    signed_out.findChild(QPushButton, "createAccount").click()
    wait_until(qapp, lambda: signed_out._stack.currentWidget().objectName() == "recoveryPage")
    signed_out.recovery_ack.setChecked(True)
    signed_out.recovery_continue.click()
    past_setup(qapp, signed_out)
    return signed_out
