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
