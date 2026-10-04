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
# Text is drawn in grey shades, never in coloured subpixel stripes, however the computer sets it. The
# system's fontconfig turned stripes on and the developer's own turned them off, so a worker, with a
# home of its own, drew the date picker's 10 in stripes no pixel of which was the text's colour, and
# the same file run alone drew it in the text's colour.
os.environ["FONTCONFIG_FILE"] = str(Path(__file__).with_name("fontconfig.conf"))
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
    """Hidden windows still hold their widget trees, pictures and timers through signal connections.
    Delete Python-owned windows made by the test; keep module fixtures and Qt's internal windows."""
    if importlib.util.find_spec("PySide6") is None:
        yield
        return
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    from shiboken6 import getCppPointer, isValid, ownedByPython

    before = (
        {getCppPointer(window)[0] for window in QApplication.topLevelWidgets()}
        if QApplication.instance() is not None else set()
    )
    yield
    if QApplication.instance() is None:
        return
    for window in QApplication.topLevelWidgets():
        if isValid(window) and getCppPointer(window)[0] not in before:
            window.hide()
            if ownedByPython(window):
                window.close()
                window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


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
def the_pointer_starts_where_a_new_worker_has_it() -> Iterator[None]:
    """The offscreen pointer keeps its place, and the window it was last over, from one test to the
    next. Clay's arrow tests park it over a view that lives on hidden; the sign-in test's next move
    then sent that view's leave first, it took hover off the sign-in window, and Forgot password never
    showed hover. Every test starts with the pointer at (10, 10), over no window, as a new worker has
    it."""
    if importlib.util.find_spec("PySide6") is not None:
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is not None:
            QCursor.setPos(QPoint(10, 10))
    yield


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
