"""What every desktop test shares."""

from __future__ import annotations

import atexit
import gc
import importlib.util
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Qt's test mode keeps its files in ~/.qttest. Workers running side by side would share the look
# file, the kept sessions and the rest, and hand one test's state to another's, so each worker gets a
# home of its own. The cache stays the real one, so fonts are not indexed again for every worker.
# Alarms and reminders the tests ring are played at no volume (sound.SILENT).
os.environ["FLEXWEEK_SILENT"] = "1"
if os.environ.get("PYTEST_XDIST_WORKER"):
    os.environ.setdefault("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    os.environ["HOME"] = tempfile.mkdtemp(prefix=f"flexweek-{os.environ['PYTEST_XDIST_WORKER']}-")
    atexit.register(shutil.rmtree, os.environ["HOME"], True)


@pytest.fixture(autouse=True)
def the_pointer_finds_windows_past_the_screens_edge(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Qt's offscreen screen is 800 by 800, and QApplication.widgetAt finds nothing past its edge: with
    the rail on the left, Thursday and Friday of a 1280 pixel window lay past it, and a drag there
    could not find the hours to drop on. Where Qt finds nothing, the window under the point does.
    (A larger screen from offscreen's config file left Qt holding a screen that was gone, and a test
    now and then crashed on it.)"""
    if importlib.util.find_spec("PySide6") is not None:
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication

        real = QApplication.widgetAt

        def widget_at(*where: object) -> object:
            found = real(*where)
            if found is not None:
                return found
            point = where[0] if len(where) == 1 else QPoint(*where)
            for window in reversed(QApplication.topLevelWidgets()):
                if window.isVisible() and window.geometry().contains(point):
                    return window.childAt(window.mapFromGlobal(point)) or window
            return None

        monkeypatch.setattr(QApplication, "widgetAt", staticmethod(widget_at))
    yield


@pytest.fixture(autouse=True)
def no_window_is_left_showing() -> Iterator[None]:
    """A view a test shows on its own is a window of its own, and one whose signals hold it lives on
    after the test. Every one left showing lay over the next tests' windows at the top left, and where
    the pointer found one of them first, a later test's drag dropped on it and not on its own hours.
    Windows the test showed are hidden when it ends; a module's fixtures open theirs before this."""
    if importlib.util.find_spec("PySide6") is None:
        yield
        return
    from PySide6.QtWidgets import QApplication, QWidget
    from shiboken6 import getCppPointer

    def showing() -> dict[int, QWidget]:
        if QApplication.instance() is None:
            return {}
        windows = QApplication.topLevelWidgets()
        return {getCppPointer(window)[0]: window for window in windows if window.isVisible()}

    before = showing()
    yield
    for pointer, window in showing().items():
        if pointer not in before:
            window.hide()


@pytest.fixture(autouse=True)
def no_mouse_button_is_left_held() -> Iterator[None]:
    """A button QTest pressed and never released stays down in Qt for the rest of the worker, so every
    later pointer move is a drag and hover never moves to the widget under it: a later test's link
    showed no hover only when it shared a worker with the test that held the button."""
    yield
    if importlib.util.find_spec("PySide6") is None:
        return
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is not None:
        assert QApplication.mouseButtons() == Qt.MouseButton.NoButton, "left a mouse button held down"


@pytest.fixture(autouse=True)
def nothing_leaves_the_test(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No test reaches this computer's own apps. A Spotify alarm tells the Spotify app to play, over
    the session bus or by opening its address, and the developer's Spotify was running: a test would
    have started music. A test that wants to see what would be opened patches over this."""
    if importlib.util.find_spec("PySide6") is not None:
        from PySide6.QtGui import QDesktopServices

        from desktop.native import spotify

        monkeypatch.setattr(spotify, "system_remote", spotify.NoRemote)
        monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda _url: False))
    yield


@pytest.fixture(autouse=True)
def no_window_is_left_for_the_garbage_collector() -> Iterator[None]:
    """A widget Python owns that a test leaves in a reference cycle is deleted whenever the collector
    next runs, in whichever thread runs it. That was often the local server's thread in a later test,
    and a whole dialog torn down there crashed the worker with a segmentation fault. The collector runs
    here instead, on this thread, and any such widget fails the test that left it."""
    yield
    if importlib.util.find_spec("PySide6") is None:
        return
    from PySide6.QtCore import QObject
    from PySide6.QtWidgets import QApplication
    from shiboken6 import isValid, ownedByPython

    # A timer still waiting holds its widget; once it has run, the widget is either freed or garbage.
    if QApplication.instance() is not None:
        QApplication.processEvents()
    gc.set_debug(gc.DEBUG_SAVEALL)
    try:
        gc.collect()
        left = [
            f"{type(item).__name__} {item.objectName()!r}"
            for item in gc.garbage
            if isinstance(item, QObject) and isValid(item) and ownedByPython(item)
        ]
    finally:
        gc.set_debug(0)
        gc.garbage.clear()
        gc.collect()
    assert left == [], "left for the garbage collector"


@pytest.fixture(autouse=True)
def the_clock_starts_at_24_hours() -> Iterator[None]:
    """The clock is one setting for the whole app, so a test that chose 12-hour would leave it for the
    next test."""
    from desktop.native.weekmodel import set_clock_24h

    yield
    set_clock_24h(True)
