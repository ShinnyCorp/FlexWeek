"""FlexWeek desktop app: native Qt widgets over the local Python API.

`python -m desktop.main` starts widgets, not Chromium. The backend runs on a
loopback port in this process unless `--database` already names a file next to
a running test. Hosted HTML is not loaded. Set FLEXWEEK_DESKTOP_ORIGIN only to
point the native client at another loopback API.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import secrets
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


def report_missing_part(error: ImportError) -> None:
    # Qt may be the part that failed, so this uses only the standard library and, on Windows,
    # the system message box. The Windows build runs without a console, so stderr alone is not seen.
    message = f"FlexWeek could not start because a part it needs did not load:\n{error}"
    if sys.platform.startswith("linux"):
        message += "\nThe Linux libraries section of the README lists what it needs."
    print(message, file=sys.stderr)
    if sys.platform == "win32":
        mb_iconerror = 0x10
        ctypes.windll.user32.MessageBoxW(None, message, "FlexWeek", mb_iconerror)


try:
    from PySide6.QtCore import QStandardPaths, QTimer
    from PySide6.QtGui import QIcon, QImage
    from PySide6.QtNetwork import QLocalSocket
    from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

    import backend
    from desktop.native.calendar import sunday_due
    from desktop.native.fonts import load_fonts
    from desktop.native.kept import KeptSession
    from desktop.native.setup import DONE as SETUP_DONE
    from desktop.native.updater import collect_stale_downloads
    from desktop.native.window import NativeWindow
    from desktop.origin import configured_origin
    from desktop.server import LocalServer
except ImportError as error:
    report_missing_part(error)
    raise SystemExit(1) from error

INSTANCE_WAIT_MS = 500
SMOKE_FLAG = "--smoke-test"
SMOKE_TIMEOUT_MS = 90_000
SMOKE_POLL_MS = 250
SMOKE_PASSED = "week shown after setup Solve"
PAINTED_MIN_COLORS = 8
DESKTOP_FILE_NAME = "flexweek"


def app_icon_path() -> Path:
    return Path(backend.__file__).resolve().parents[1] / "desktop" / "assets" / "logo.png"


def instance_name(root: str) -> str:
    return "flexweek-" + hashlib.sha256(root.encode()).hexdigest()[:16]


def show_running_instance(name: str) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(INSTANCE_WAIT_MS):
        return False
    socket.write(b"show")
    socket.waitForBytesWritten(INSTANCE_WAIT_MS)
    socket.disconnectFromServer()
    return True


def profile_root() -> str:
    return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)


def parse_database(argv: list[str]) -> tuple[list[str], Path | None]:
    filtered = [argv[0]]
    database: Path | None = None
    index = 1
    while index < len(argv):
        if argv[index] == "--database" and index + 1 < len(argv):
            database = Path(argv[index + 1])
            index += 2
            continue
        filtered.append(argv[index])
        index += 1
    return filtered, database


def smoke_report_path(argv: list[str]) -> Path | None:
    if SMOKE_FLAG not in argv:
        return None
    index = argv.index(SMOKE_FLAG)
    if index + 1 >= len(argv):
        raise SystemExit(f"{SMOKE_FLAG} needs a file path for the report")
    return Path(argv[index + 1])


def painted_colors(image: QImage, step: int = 8) -> int:
    colors = set()
    for y in range(0, image.height(), step):
        for x in range(0, image.width(), step):
            colors.add(image.pixel(x, y))
    return len(colors)


def origin_reachable(origin: str) -> bool:
    try:
        with urllib.request.urlopen(origin + "/api/health", timeout=2) as response:
            return 200 <= response.status < 300
    except urllib.error.URLError, TimeoutError, OSError, ValueError:
        return False


class NativeSmoke:
    """Registers a throwaway account, places a week, and writes a startup report."""

    def __init__(self, window: NativeWindow, report: Path, walk_setup: bool) -> None:
        self._window = window
        self._report = report
        self._walk = walk_setup
        self._done = False
        self._stage = "first screen"
        self._poll = QTimer(window)
        self._poll.setInterval(SMOKE_POLL_MS)
        self._poll.timeout.connect(self._check)
        QTimer.singleShot(SMOKE_TIMEOUT_MS, self._time_out)
        QTimer.singleShot(0, self._poll.start)

    def _time_out(self) -> None:
        self._finish(False, f"timed out waiting for {self._stage}")

    def _check(self) -> None:
        if self._done:
            return
        window = self._window
        if not window.isVisible():
            return
        page = window._stack.currentWidget().objectName() if window._stack.currentWidget() else ""
        if not self._walk:
            if page == "authPage":
                self._finish(True, "first screen shown")
            return
        if self._stage == "first screen":
            if page != "authPage":
                return
            username = "smoke_" + secrets.token_hex(6)
            password = secrets.token_urlsafe(18)
            window.username.setText(username)
            window.password.setText(password)
            create = window.findChild(QPushButton, "createAccount")
            if create is None:
                self._finish(False, "create account control missing")
                return
            create.click()
            self._stage = "recovery codes"
            return
        if self._stage == "recovery codes":
            if page != "recoveryPage":
                return
            codes = [line for line in window.recovery_list.text().splitlines() if line.strip()]
            if len(codes) != 8:
                return
            window.recovery_ack.setChecked(True)
            window.recovery_continue.click()
            self._stage = "setup"
            return
        if self._stage == "setup":
            # One page per poll, each skipped, so every page of setup is drawn in the build under test.
            if page == "setupPage":
                setup = window.setup_page
                (setup.next if setup.step == SETUP_DONE else setup.skip).click()
                return
            if page == "weekPage":
                self._stage = "week"
            return
        if self._stage == "week":
            if page != "weekPage" or window.session.account is None or window.session.busy:
                return
            if window._setup_prefs or window._setup_week:
                return
            session = window.session
            session.add_block(
                {
                    "id": "soccer",
                    "title": "Soccer",
                    "kind": "locked",
                    "duration_min": 60,
                    "days": [0],
                    "start": "16:00",
                    "category": "exercise",
                }
            )
            session.add_homework(
                {
                    "id": "math",
                    "title": "Math worksheet",
                    "due": sunday_due(session.week_start),
                    "estimate_min": 60,
                    "revision": 0,
                }
            )
            session.save()
            self._stage = "saved week"
            return
        if self._stage == "saved week":
            session = window.session
            if session.busy or session.revision < 1:
                return
            if not any(block.get("id") == "soccer" for block in session.blocks):
                self._finish(False, "window blank after setup Solve")
                return
            self._facts_colors = painted_colors(window.grab().toImage())
            self._finish(True, SMOKE_PASSED)

    def _finish(self, ok: bool, stage: str) -> None:
        if self._done:
            return
        self._done = True
        self._poll.stop()
        window = self._window
        facts = {
            "ok": ok,
            "stage": stage,
            "window_visible": window.isVisible(),
            "window_icon_loaded": not window.windowIcon().isNull(),
            "tray_icon_installed": window._tray_icon is not None,
            "block_count": len(window.session.blocks),
            "painted_colors": getattr(self, "_facts_colors", 0),
            "message": window.session.message,
        }
        self._report.write_text(json.dumps(facts, indent=2) + "\n")
        window.quit_app()
        application = QApplication.instance()
        if application is not None:
            application.exit(0 if ok else 1)


def main(argv: list[str] | None = None) -> int:
    arguments, database_arg = parse_database(list(argv if argv is not None else sys.argv))
    report = smoke_report_path(arguments)
    app = QApplication(arguments)
    app.setApplicationName("FlexWeek")
    app.setDesktopFileName(DESKTOP_FILE_NAME)
    load_fonts()
    collect_stale_downloads()

    try:
        origin = configured_origin()
    except ValueError as error:
        QMessageBox.critical(None, "FlexWeek configuration", str(error))
        return 2

    root = tempfile.mkdtemp(prefix="flexweek-smoke-") if report is not None else profile_root()
    instance = instance_name(str(database_arg) if database_arg is not None else root)
    if report is None and show_running_instance(instance):
        return 0

    hosted = origin is not None and database_arg is None
    if hosted and report is not None and not origin_reachable(origin):
        payload = json.dumps({"ok": False, "stage": "page failed to load", "window_visible": False})
        report.write_text(payload + "\n")
        shutil.rmtree(root, ignore_errors=True)
        return 1

    server: LocalServer | None = None
    if not hosted:
        database = database_arg if database_arg is not None else Path(root) / "flexweek.db"
        try:
            database.parent.mkdir(parents=True, exist_ok=True)
            server = LocalServer(database)
            origin = server.start()
        except (OSError, RuntimeError, TimeoutError) as error:
            QMessageBox.critical(None, "FlexWeek", f"Could not start FlexWeek: {error}")
            return 3
        app.aboutToQuit.connect(server.stop)
    assert origin is not None

    # Keep me signed in is per database, like the running-instance check.
    kept = KeptSession(Path(root) / "signed-in" / f"{instance}.json")
    window = NativeWindow(origin, icon=QIcon(str(app_icon_path())), kept=kept)
    if report is None:
        window.listen_for_instances(instance)
    smoke = NativeSmoke(window, report, walk_setup=not hosted) if report is not None else None
    window.show()
    status = app.exec()
    del smoke
    if report is not None:
        shutil.rmtree(root, ignore_errors=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
