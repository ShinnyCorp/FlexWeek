"""What every desktop test shares."""

from __future__ import annotations

import atexit
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
def the_clock_starts_at_24_hours() -> Iterator[None]:
    """The clock is one setting for the whole app, so a test that chose 12-hour would leave it for the
    next test."""
    from desktop.native.weekmodel import set_clock_24h

    yield
    set_clock_24h(True)
