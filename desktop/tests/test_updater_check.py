"""Checking for updates when GitHub will not answer the way the check expects.

GitHub's API answers 60 unsigned requests an hour per address. On a phone carrier's shared address
it answered 403, and the app said nothing, so "Checking for updates…" stayed on screen as if the
check were still going. A local server stands in for GitHub here.
"""

from __future__ import annotations

import importlib.util
import os
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication

    from desktop.native import updater as updater_module
    from desktop.native.updater import CHECK_FAILED, Updater

TAG_PAGE = "https://github.com/j0nsh1n/FlexWeek/releases/tag/v9.9.9"
# In the app the updater lives as long as the window. Freed at the end of a test, its network manager
# went while Qt still had events queued for it, and the next test crashed.
KEPT: list[object] = []
DOWNLOADS = "https://github.com/j0nsh1n/FlexWeek/releases/download/v9.9.9/"


class GitHub(BaseHTTPRequestHandler):
    """/api answers as told, /page redirects to a release or fails, /slow never answers in time."""

    api_status = 403
    page_status = 302

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/slow":
            time.sleep(2)
            return
        if self.path == "/api":
            self.send_response(self.api_status)
            self.end_headers()
            self.wfile.write(b'{"message": "API rate limit exceeded"}')
            return
        self.send_response(self.page_status)
        if self.page_status == 302:
            self.send_header("Location", TAG_PAGE)
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-updater-check-test"])


@pytest.fixture()
def github(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), GitHub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setattr(updater_module, "RELEASES_URL", origin + "/api")
    monkeypatch.setattr(updater_module, "RELEASE_PAGE", origin + "/page")
    monkeypatch.setattr(updater_module, "CHECK_TIMEOUT_MS", 300)
    monkeypatch.setattr(GitHub, "api_status", 403)
    monkeypatch.setattr(GitHub, "page_status", 302)
    yield origin
    server.shutdown()


def made() -> Updater:
    updater = Updater()
    KEPT.append(updater)
    return updater


def outcome(qapp: QApplication, updater: Updater, timeout: float = 5.0) -> tuple[str, object]:
    heard: list[tuple[str, object]] = []
    updater.found.connect(lambda update: heard.append(("found", update)))
    updater.none_found.connect(lambda: heard.append(("none", None)))
    updater.unreachable.connect(lambda why: heard.append(("unreachable", why)))
    updater.check()
    wait_until(qapp, lambda: bool(heard), timeout)
    return heard[0]


def wait_until(qapp: QApplication, predicate: Callable[[], bool], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("the check never finished")


def test_a_refused_api_still_finds_the_update_through_the_release_page(
    qapp: QApplication, github: str
) -> None:
    updater = made()
    updater.kind = "appimage"
    kind, update = outcome(qapp, updater)
    assert kind == "found"
    assert isinstance(update, dict) and update["url"] == DOWNLOADS + "FlexWeek-x86_64.AppImage"
    assert updater.busy is False


def test_a_check_that_cannot_be_done_says_so(
    qapp: QApplication, github: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(GitHub, "page_status", 500)
    updater = made()
    assert outcome(qapp, updater) == ("unreachable", CHECK_FAILED)
    assert updater.busy is False, "a second check can start"


def test_a_check_that_hears_nothing_gives_up(
    qapp: QApplication, github: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(updater_module, "RELEASES_URL", github + "/slow")
    monkeypatch.setattr(updater_module, "RELEASE_PAGE", github + "/slow")
    updater = made()
    assert outcome(qapp, updater, timeout=4.0) == ("unreachable", CHECK_FAILED)
