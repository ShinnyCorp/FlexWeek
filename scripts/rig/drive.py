"""Drive FlexWeek with a real pointer on a hidden desktop, and check that the saved week agrees.

    fwtest rig                                              # every design, every tab
    fwtest rig --design bento --tab day
    fwtest rig --design bento --option hero=today          # a design's saved option
    fwtest rig --design dial --tab myday                   # My day's screens: one, dial
    .venv/bin/python scripts/rig/drive.py --list

Every scenario starts from the same seeded week with the clock held at Thursday 15:40. It opens its
tab with the pointer, performs one gesture with xdotool on the hidden session's X display, waits for
the save, reloads the week from the server and asserts on what came back. A screenshot is taken
while the pointer is still held and another after the drop, and each design's run is recorded as a
video with the pointer drawn in. Without --out, results land in
~/.flexweek-ui-harness/scratch/rig-runs/<checkout id>/ (FLEXWEEK_RIG_RUNS names another folder),
and the newest 3 runs of the checkout are kept.

Surfaces are found through the hours interface below, which every hours surface provides. A surface
that has no hours fails the scenarios that need them, which is what the 0.14.3 baseline records.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

# The app the rig drives rings reminders; they play at no volume (desktop/native/sound.py).
os.environ["FLEXWEEK_SILENT"] = "1"

MARKER = "rig-week-marker"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

DESIGNS = ("classic", "timeline", "mission", "bento", "retro", "clay")
# My day's screens run only the My day scenarios, and the designs only the others.
MY_DAY = ("one", "dial")
TABS = ("day", "week", "month", "myday")
PASSWORD = "a-long-test-password"
KEEP_RUNS = 3
RUN_NAME = re.compile(r"\d{8}-\d{6}-\d+")


def parse_options(design: str | None, pairs: list[str]) -> dict[str, str]:
    """`--option key=value` pairs as the design's saved options, or a SystemExit naming what is valid."""
    from desktop.native.layouts.registry import LAYOUTS

    if not pairs:
        return {}
    if design not in LAYOUTS:
        raise SystemExit("--option sets a design's option, so it needs --design (a design with options).")
    spec = LAYOUTS[design]
    valid = {option.key: option.values for option in spec.options}
    listing = "; ".join(f"{key}: {', '.join(values)}" for key, values in valid.items()) or "none"
    chosen: dict[str, str] = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator:
            raise SystemExit(f"--option {pair!r} is not key=value. {design} options: {listing}")
        if key not in valid:
            raise SystemExit(f"{design} has no option {key!r}. {design} options: {listing}")
        if value not in valid[key]:
            raise SystemExit(
                f"{design} option {key!r} has no value {value!r}. Valid: {', '.join(valid[key])}"
            )
        chosen[key] = value
    return chosen


def default_runs_folder(runs_key: str) -> Path:
    # Runs live on disk, not in /tmp: on Jonathan's machine /tmp is RAM (tmpfs with zram swap) and a
    # day of rig runs held 767 MB of it. FLEXWEEK_RIG_RUNS moves them, since that harness folder
    # exists only there. The hidden session's own state is small and stays in /tmp.
    root = os.environ.get("FLEXWEEK_RIG_RUNS")
    base = Path(root) if root else Path.home() / ".flexweek-ui-harness" / "scratch" / "rig-runs"
    return base / runs_key


def caller_env(frozen: str, live: str) -> str:
    """Environment `fwtest rig` started with. An empty stored value means the caller had none."""
    if frozen in os.environ:
        return os.environ[frozen]
    return os.environ.get(live, "")


def session_from_fwtest() -> tuple[str, str, str]:
    """Display, private bus, and runs-folder key passed in by `fwtest rig`."""
    display = os.environ.get("FLEXWEEK_RIG_DISPLAY", "")
    bus = os.environ.get("FLEXWEEK_RIG_BUS", "")
    runs_key = os.environ.get("FLEXWEEK_RIG_RUNS_KEY", "")
    if not display or not bus or not runs_key:
        raise SystemExit("Use fwtest rig.")
    own_display = caller_env("FLEXWEEK_CALLER_DISPLAY", "DISPLAY")
    if own_display and display == own_display:
        raise SystemExit(f"Refusing display {display}, which is this process's own DISPLAY.")
    own_bus = caller_env("FLEXWEEK_CALLER_BUS", "DBUS_SESSION_BUS_ADDRESS")
    if own_bus and bus == own_bus:
        raise SystemExit("Refusing the caller's own D-Bus session bus.")
    return display, bus, runs_key


def prune_runs(folder: Path) -> None:
    runs = sorted(item for item in folder.iterdir() if item.is_dir() and RUN_NAME.fullmatch(item.name))
    for old in runs[:-KEEP_RUNS]:
        shutil.rmtree(old, ignore_errors=True)

Step = Generator[tuple, object]


@dataclass(frozen=True)
class Scenario:
    name: str
    tab: str
    run: Callable[[object], Step]
    only: tuple[str, ...] = ()


class NoSurface(Exception):
    """The tab has no hours, chip or cell to do this on."""


class Waited(AssertionError):
    """Something the scenario waited for never happened. Never a pass."""


def report_run(
    plan: list[tuple[str, str, str]],
    results: list[dict],
    finished: bool,
    python_error: str | None = None,
    stopped_in: str | None = None,
) -> tuple[str, int, list[dict]]:
    """The line printed at the end, the exit code, and results.json including scenarios that did not run."""
    ran = {(item["design"], item["scenario"]) for item in results}
    skipped = [
        {"design": design, "tab": tab, "scenario": name, "result": "SKIPPED"}
        for design, tab, name in plan
        if (design, name) not in ran
    ]
    payload = [*results, *skipped]
    passed = sum(1 for item in results if item["result"] == "PASS")
    failures = any(item.get("result") not in {"PASS"} for item in results)
    where = stopped_in or (results[-1]["scenario"] if results else (plan[0][2] if plan else ""))
    if python_error:
        return f"STOPPED in {where}: {python_error}", 1, payload
    if finished and not skipped and results and failures:
        return f"{passed}/{len(plan)} passed, {len(results) - passed} failed.", 1, payload
    if not finished or skipped or not results or failures or passed != len(plan):
        return (
            f"STOPPED in {where}: {len(results)}/{len(plan)} ran, {len(skipped)} did not run.",
            1,
            payload,
        )
    return f"{passed}/{len(plan)} passed.", 0, payload


def child_main(args: argparse.Namespace) -> int:
    from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QSize, QStandardPaths, Qt, QTimer
    from PySide6.QtGui import QColor, QCursor, QPainter, QPen
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QPushButton, QWidget

    QStandardPaths.setTestModeEnabled(True)
    app = QApplication(["flexweek-rig"])
    python_errors: list[str] = []

    def on_error(kind: type, value: BaseException, tb: object) -> None:
        python_errors.append(f"{getattr(kind, '__name__', kind)}: {value}")
        traceback.print_exception(kind, value, tb)
        app.quit()

    sys.excepthook = on_error

    from desktop.native.calendar import sunday_due
    from desktop.native.client import _error
    from desktop.native.hours.geometry import FIRST, Axis
    from desktop.native.hours.hand import surface_at
    from desktop.native.hours.zoom import HoursScroll
    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.look import sanitize_look
    from desktop.native.window import NativeWindow
    from desktop.server import LocalServer
    from desktop.tests.logic_support import past_setup, wait_until

    out = Path(args.out)
    server = LocalServer(Path(tempfile.mkdtemp()) / "rig.db")
    server.start()
    window = NativeWindow(server.origin)
    window.resize(1280, 820)
    window.move(0, 0)
    window.show()
    window.username.setText("rig_student")
    window.password.setText(PASSWORD)
    window.findChild(QPushButton, "createAccount").click()
    wait_until(app, lambda: window._stack.currentWidget().objectName() == "recoveryPage", 20)
    window.recovery_ack.setChecked(True)
    window.recovery_continue.click()
    past_setup(app, window)
    session = window.session
    thursday = datetime.fromisoformat(session.week_start) + timedelta(days=3, hours=15, minutes=40)
    session.now_ms = lambda: int(thursday.timestamp() * 1000)
    due_sunday = sunday_due(session.week_start)
    due_friday = (
        datetime.fromisoformat(session.week_start) + timedelta(days=4)
    ).date().isoformat() + "T23:59"
    session.add_block(
        {
            "id": "school",
            "title": "School",
            "kind": "locked",
            "category": "class",
            "start": "08:00",
            "duration_min": 390,
            "days": [0, 1, 2, 3, 4],
        }
    )
    session.add_block(
        {
            "id": "soccer",
            "title": "Soccer",
            "kind": "locked",
            "category": "exercise",
            "start": "16:00",
            "duration_min": 90,
            "days": [1, 3],
        }
    )
    for key, title, due in (
        ("essay", "History essay", due_sunday),
        ("math", "Math worksheet", due_sunday),
        ("poster", "Science poster", due_friday),
    ):
        session.add_homework({"id": key, "title": title, "due": due, "estimate_min": 60, "revision": 0})
    session.save()
    wait_until(app, lambda: not session.busy and not session.dirty, 20)
    essay = next(b for b in session.blocks if b.get("assignment_id") == "essay")
    session.add_block({**essay, "start": "19:00", "days": [3], "pinned": True})
    session.save()
    wait_until(app, lambda: not session.busy and not session.dirty, 20)
    seed = [dict(block) for block in session.blocks]
    # What a scenario may change on the window itself, put back before the next one.
    base_now, base_request, base_look = session.now_ms, session.client.request, dict(window._look)
    ids = {
        key: next(b["id"] for b in session.blocks if b.get("assignment_id") == key)
        for key in ("essay", "math", "poster")
    }
    thursday_iso = thursday.date().isoformat()
    seed_week = session.week_start
    seed_dues = {key: session.assignments[key]["due"] for key in ("essay", "math", "poster")}

    def block(block_id: str) -> dict | None:
        return next((b for b in session.blocks if b["id"] == block_id), None)

    def minutes(hhmm: str) -> int:
        return int(hhmm[:2]) * 60 + int(hhmm[3:])

    def hhmm(minute: int) -> str:
        # Before midnight as -00:26, not floor division's -1:34.
        sign, minute = ("-" if minute < 0 else ""), abs(minute)
        return f"{sign}{minute // 60:02d}:{minute % 60:02d}"

    class Recorder:
        """Frames of the window with the pointer drawn in, for the design's video."""

        def __init__(self) -> None:
            self.folder: Path | None = None
            self.count = 0
            self.timer = QTimer()
            self.timer.setInterval(100)
            self.timer.timeout.connect(self.frame)

        def begin(self, folder: Path) -> None:
            self.folder, self.count = folder, 0
            folder.mkdir(parents=True, exist_ok=True)
            self.timer.start()

        def frame(self) -> None:
            if self.folder is None:
                return
            image = window.grab().toImage()
            at = window.mapFromGlobal(QCursor.pos())
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor("#ffffff"), 3))
            painter.setBrush(QColor("#e11d48"))
            painter.drawEllipse(QPointF(at), 7, 7)
            painter.end()
            image.save(str(self.folder / f"{self.count:05d}.jpg"), "JPG", 82)
            self.count += 1

        def finish(self, video: Path) -> None:
            self.timer.stop()
            folder, self.folder = self.folder, None
            if folder is not None and self.count:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-loglevel",
                        "error",
                        "-y",
                        "-framerate",
                        "10",
                        "-i",
                        str(folder / "%05d.jpg"),
                        "-pix_fmt",
                        "yuv420p",
                        "-vf",
                        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                        str(video),
                    ],
                    check=False,
                )

    recorder = Recorder()

    def xdo(*parts: object) -> None:
        subprocess.run(["xdotool", *map(str, parts)], check=True)

    class Rig:
        def __init__(self) -> None:
            self.design = ""
            self.shots: Path = out
            self.scenario = ""
            # The hidden KWin session lets go of a button held through xdotool about a second after
            # the last input xdotool sent; a hand resting on a button never lets go by itself. So
            # while a drag holds the button, the pointer is sent where it already is.
            self._resting_at = QPoint()
            self._still = QTimer()
            self._still.setInterval(250)
            self._still.timeout.connect(lambda: xdo("mousemove", self._resting_at.x(), self._resting_at.y()))

        # Pointer

        def move(self, point: QPoint) -> Step:
            xdo("mousemove", "--sync", point.x(), point.y())
            yield ("wait", 30)

        def click(self, point: QPoint) -> Step:
            yield from self.move(point)
            xdo("click", 1)
            yield ("wait", 250)

        def drag(
            self,
            start: QPoint,
            end: QPoint,
            held: Callable[[], object] | None = None,
            rest: int = 200,
            after: int = 400,
        ) -> Step:
            """Press, travel in steps as a hand does, rest, let go. `held` runs while still pressed,
            and may itself be steps. `after` is how long to wait once it is let go."""
            yield from self.move(start)
            xdo("mousedown", 1)
            self._resting_at = start
            self._still.start()
            try:
                yield ("wait", 120)
                steps = 18
                for index in range(1, steps + 1):
                    point = start + (end - start) * index / steps
                    xdo("mousemove", point.x(), point.y())
                    self._resting_at = point
                    yield ("wait", 25)
                yield ("wait", rest)
                self.shot("held")
                if held is not None:
                    more = held()
                    if isinstance(more, Generator):
                        yield from more
            finally:
                self._still.stop()
            # Anything the scenario reads while it holds is only true if it still held then.
            if not QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
                raise AssertionError("the button was let go before the rig let go of it")
            xdo("mouseup", 1)
            yield ("wait", after)

        def double_click(self, point: QPoint) -> Step:
            yield from self.move(point)
            xdo("click", "--repeat", 2, "--delay", 80, 1)
            yield ("wait", 300)

        def wheel(self, point: QPoint, notches: int, ctrl: bool = True) -> Step:
            """Turn the wheel over a point, away from the student (positive) or toward, with Ctrl
            held down, as a hand zooms."""
            yield from self.move(point)
            if ctrl:
                xdo("keydown", "ctrl")
            xdo("click", "--repeat", abs(notches), "--delay", 80, 4 if notches > 0 else 5)
            if ctrl:
                xdo("keyup", "ctrl")
            yield ("wait", 300)

        def key(self, *keys: str) -> Step:
            xdo("key", *keys)
            yield ("wait", 150)

        def type(self, words: str) -> Step:
            xdo("type", "--delay", "20", words)
            yield ("wait", 150)

        def shot(self, label: str) -> None:
            window.grab().save(str(self.shots / f"{self.design}-{self.scenario}-{label}.png"))

        # Where things are

        def tab(self, name: str) -> Step:
            button = window.findChild(QPushButton, f"view{name.title()}")
            yield from self.click(button.mapToGlobal(button.rect().center()))
            yield ("wait", 150)
            # A fixed wait was short on a slow CI runner: the week was not drawn yet when the next step
            # looked for its day names.

            def shown() -> bool:
                return button.isChecked() and not self.moving()

            yield ("until", shown, 5000, f"the {name} view to show")

        def moving(self) -> bool:
            """A fade or slide is still running somewhere in the window (motion.py marks each one on
            the widget it moves)."""
            return any(getattr(widget, "_motion_running", None) for widget in window.findChildren(QWidget))

        def day_name(self, day: int) -> QPoint:
            """A day's name as it is drawn: Today's app's week keeps them in a row of their own;
            other surfaces paint them over a column or left of a lane."""
            label = window.findChild(QWidget, f"weekDayName{day}")
            if label is not None and label.isVisible():
                return label.mapToGlobal(label.rect().center())
            for surface in self.surfaces("hours"):
                with contextlib.suppress(LookupError, AttributeError):
                    return surface.day_name(day)
            raise NoSurface(f"no name drawn for day {day} in {self.design}")

        def surfaces(self, kind: str) -> list:
            """Every hours (or month) surface on screen. A design may show several: tiles of one day,
            a card per day, lanes and a dial."""
            shown = window.planner.currentWidget()
            finder = getattr(shown, "hours_surfaces" if kind == "hours" else "month_surfaces", None)
            found = [item for item in finder() if item.isVisible()] if finder is not None else []
            if not found:
                raise NoSurface(f"no {kind} on the {session.planner_view} tab of {self.design}")
            return found

        def surface(self, kind: str, day: int | None = None, minute: int | None = None) -> object:
            """The surface that shows this day and minute, or the first one when neither is asked."""
            found = self.surfaces(kind)
            if day is None:
                return found[0]
            for item in found:
                finder = getattr(item, "track_for", None)
                if finder is not None and finder(day, minute) is not None:
                    return item
            raise NoSurface(f"no {kind} shows day {day} at {minute} in {self.design}")

        def reveal(self, day: int, first: int, last: int) -> Step:
            """Scroll so this stretch of the day is on screen before anything is measured. A day shown
            only in part, as Clay's cards beside the one in front show the stretch the front shows, is
            revealed by the surface that shows it: Clay's brings the day to the front."""
            try:
                surface = self.surface("hours", day, first)
            except NoSurface:
                surface = self.surface("hours", day)
            reveal = getattr(surface, "reveal", None)
            if reveal is not None:
                reveal(day, first, last)
            yield ("wait", 150)

        def zoom(self) -> HoursScroll:
            """The zoom of the hours on screen. Hours that cannot zoom fail the zoom scenarios."""
            area = self.surface("hours")._scroll_area()
            if not isinstance(area, HoursScroll):
                raise NoSurface(f"the {session.planner_view} hours of {self.design} do not zoom")
            return area

        def minute_under(self, point: QPoint) -> float:
            hours = surface_at(point)
            local = QPointF(hours.mapFromGlobal(point)) if hours is not None else QPointF()
            track = hours.track_at(local) if hours is not None else None
            if track is None:
                raise NoSurface(f"no hours under {point.x()},{point.y()}")
            return track.minute_at(local)

        def at(self, day: int, minute: int) -> QPoint:
            """A point on the day a minute and a quarter past a minute, whichever way the design lays
            time out: inside the drag step that starts there, and nearer it than the next one, at a
            step of 5 or 15 and at every zoom. Three pixels on, as it was, is past a 5-minute step on
            a Week at 48 pixels an hour."""
            surface = self.surface("hours", day, minute)
            track = surface.track_for(day, minute)
            return surface.mapToGlobal(track.point_for(min(minute + 1.25, track.last))).toPoint()

        def carried(self, press: QPoint, start: int, day: int, to: int) -> QPoint:
            """Where to let go of a block pressed at `press`, which starts at `start`, so that it starts at
            `to` on `day`: as far into the time there as the press was into the block. Aimed by minutes,
            not by the distance between the two days, so a day drawn at another scale, as Clay's cards
            peeking beside the one in front are, is aimed at as well."""
            return self.at(day, to + round(self.minute_under(press) - start))

        def block_rect(self, block_id: str, day: int) -> QRect:
            for surface in self.surfaces("hours"):
                rect = surface.block_rect(block_id, day)
                if rect is not None:
                    return rect
            raise NoSurface(f"{block_id} is not drawn on day {day}")

        def _span(self, block_id: str, day: int) -> tuple[QPointF, QPointF, QPointF]:
            """Where a drawn block lies, from its surface's own track: the point at its start in
            time, the run from there to its end, and how far the middle of its paint sits across
            the track, where an overlap drawn beside another or a tilted card has put it."""
            got = block(block_id)
            if got is None or not got.get("start"):
                raise NoSurface(f"{block_id} has no time")
            start = minutes(got["start"])
            end = start + got["duration_min"]
            surface = self.surface("hours", day, start)
            box = surface.block_rect(block_id, day)
            track = surface.track_for(day, start)
            if box is None or track is None:
                raise NoSurface(f"{block_id} is not drawn on day {day}")
            head = QPointF(surface.point_for(day, start))
            run = QPointF(surface.point_for(day, min(end, track.last))) - head
            length = math.hypot(run.x(), run.y())
            if not length:
                raise NoSurface(f"{block_id} has no length on day {day}")
            off = QPointF(box.center()) - head
            along = (off.x() * run.x() + off.y() * run.y()) / length
            across = off - run * (along / length)
            return head, run, across

        def along(self, block_id: str, day: int, share: float) -> QPoint:
            """A point on a drawn block `share` of the way through it in time, 0.0 at its start and
            1.0 at its end, in the middle of the block across the track, whichever way the design
            lays time out."""
            head, run, across = self._span(block_id, day)
            return (head + run * share + across).toPoint()

        def edge(self, block_id: str, day: int, end: bool) -> QPoint:
            """Two pixels inside a block's start or end as drawn, where a press resizes it."""
            head, run, across = self._span(block_id, day)
            # The paint starts a pixel after the minute and stops a pixel before the next.
            inside = run * (3 / math.hypot(run.x(), run.y()))
            return (head + run - inside + across if end else head + inside + across).toPoint()

        def chip(self, block_id: str) -> QPoint:
            """This block's chip in a tray, on screen, to pick up. Not a row that only opens it, as
            Bento's Due soon lists homework ahead of its tray."""
            for widget in window.findChildren(QWidget):
                if widget.isVisible() and widget.property("tray") and widget.property("block_id") == block_id:
                    return widget.mapToGlobal(widget.rect().center())
            raise NoSurface(f"no tray on screen has a chip for {block_id}")

        def settled(self) -> Step:
            """Wait for the save, then read the week back from the server and prove it is fresh.

            A marker is put in the loaded blocks first: only a real reload can remove it, so a
            scenario can never check a week that never left memory."""
            yield ("until", lambda: not session.busy and not session.dirty, 8000, "the change to save")
            session.blocks = [
                *session.blocks,
                {
                    "id": MARKER,
                    "title": "rig marker",
                    "kind": "locked",
                    "start": "12:00",
                    "duration_min": 15,
                    "days": [],
                },
            ]
            session.load_week(session.week_start, discard=True)
            yield ("wait", 50)
            yield (
                "until",
                lambda: not session.busy and all(item["id"] != MARKER for item in session.blocks),
                8000,
                "the week to come back from the server",
            )

        def accept_dialog(self, title: str) -> Step:
            yield (
                "until",
                lambda: isinstance(QApplication.activeModalWidget(), QDialog),
                3000,
                "the Add dialog",
            )
            dialog = QApplication.activeModalWidget()
            if dialog is None:
                raise AssertionError("no dialog opened")
            field = next((f for f in dialog.findChildren(QLineEdit) if f.isVisible()), None)
            if field is not None:
                yield from self.click(field.mapToGlobal(field.rect().center()))
                yield from self.key("ctrl+a")
                yield from self.type(title)
            yield from self.key("Return")
            yield ("wait", 300)

    rig = Rig()

    # Scenarios. Each yields steps and ends with plain asserts on the reloaded week.

    def expect(condition: bool, words: str) -> None:
        if not condition:
            raise AssertionError(words)

    def middle(rect: QRect) -> QPoint:
        return rect.center()

    def show_day(iso: str) -> None:
        shown = window.planner.currentWidget()
        hours = getattr(shown, "hours", None)
        if hours is None or not hours.isVisible():
            finder = getattr(shown, "hours_surfaces", None)
            found = [item for item in finder() if item.isVisible()] if finder is not None else []
            hours = found[0] if found else None
        expect(shown.isVisible() and hours is not None, f"Day canvas is {type(shown).__name__}")
        expect(
            (session.planner_view, session.selected_day) == ("day", iso),
            f"showing {session.planner_view} {session.selected_day}",
        )

    def day_tab(r: Rig) -> Step:
        thursday_name = thursday.date().isoformat()
        yield from r.tab("day")
        yield ("wait", 400)
        show_day(session.selected_day)
        if session.selected_day != thursday_name:
            yield from r.tab("week")
            yield from r.click(r.day_name(3))
            yield ("wait", 400)
        show_day(thursday_name)

    def day_move(r: Rig) -> Step:
        yield from day_tab(r)
        yield from r.reveal(3, 18 * 60 + 30, 21 * 60 + 30)
        box = r.block_rect(ids["essay"], 3)
        yield from r.drag(middle(box), middle(box) + (r.at(3, 20 * 60 + 30) - r.at(3, 19 * 60)))
        yield from r.settled()
        got = block(ids["essay"])
        expect((got["days"], got["start"]) == ([3], "20:30"), f"essay is {got['days']} {got['start']}")

    def day_resize(r: Rig) -> Step:
        yield from day_tab(r)
        yield from r.reveal(3, 18 * 60 + 30, 21 * 60)
        edge = r.edge(ids["essay"], 3, end=True)
        yield from r.drag(edge, edge + (r.at(3, 20 * 60 + 30) - r.at(3, 20 * 60)))
        yield from r.settled()
        got = block(ids["essay"])
        expect(
            (got["start"], got["duration_min"]) == ("19:00", 90),
            f"essay is {got['start']} {got['duration_min']}",
        )

    def day_create(r: Rig) -> Step:
        yield from day_tab(r)
        yield from r.reveal(3, 20 * 60 + 30, 22 * 60 + 30)
        yield from r.drag(r.at(3, 21 * 60), r.at(3, 22 * 60))
        yield from r.accept_dialog("Club")
        yield from r.settled()
        made = [b for b in session.blocks if b["title"] == "Club"]
        expect(
            [(b["days"], b["start"], b["duration_min"]) for b in made] == [([3], "21:00", 60)],
            f"made {[(b['days'], b['start'], b['duration_min']) for b in made]}",
        )

    def day_homework_in(r: Rig) -> Step:
        yield from day_tab(r)
        yield from r.reveal(3, 17 * 60, 19 * 60)
        yield from r.drag(r.chip(ids["math"]), r.at(3, 17 * 60 + 45))
        yield from r.settled()
        got = block(ids["math"])
        expect(
            (got["days"], got.get("start"), got.get("pinned")) == ([3], "17:45", True),
            f"math is {got['days']} {got.get('start')}",
        )

    def week_move_day(r: Rig) -> Step:
        yield from r.tab("week")
        yield from r.reveal(3, 17 * 60 + 30, 20 * 60 + 30)
        box = r.block_rect(ids["essay"], 3)
        yield from r.drag(middle(box), r.carried(middle(box), 19 * 60, 4, 18 * 60))
        yield from r.settled()
        got = block(ids["essay"])
        expect((got["days"], got["start"]) == ([4], "18:00"), f"essay is {got['days']} {got['start']}")

    def week_resize_top(r: Rig) -> Step:
        yield from r.tab("week")
        yield from r.reveal(3, 18 * 60, 20 * 60 + 30)
        edge = r.edge(ids["essay"], 3, end=False)
        yield from r.drag(edge, edge + (r.at(3, 18 * 60 + 30) - r.at(3, 19 * 60)))
        yield from r.settled()
        got = block(ids["essay"])
        expect(
            (got["start"], got["duration_min"]) == ("18:30", 90),
            f"essay is {got['start']} {got['duration_min']}",
        )

    def week_create(r: Rig) -> Step:
        yield from r.tab("week")
        yield from r.reveal(5, 9 * 60 + 30, 11 * 60 + 30)
        yield from r.drag(r.at(5, 10 * 60), r.at(5, 11 * 60))
        yield from r.accept_dialog("Club")
        yield from r.settled()
        made = [b for b in session.blocks if b["title"] == "Club"]
        expect(
            [(b["days"], b["start"], b["duration_min"]) for b in made] == [([5], "10:00", 60)],
            f"made {[(b['days'], b['start'], b['duration_min']) for b in made]}",
        )

    def week_series(r: Rig) -> Step:
        yield from r.tab("week")
        yield from r.reveal(2, 8 * 60, 11 * 60)
        # An hour into School's six and a half, so the grab is on the part that is on screen.
        grab = r.along("school", 2, 60 / 390)
        yield from r.drag(grab, grab + (r.at(2, 10 * 60) - r.at(2, 9 * 60)))
        yield from r.settled()
        school = sorted((tuple(b["days"]), b["start"]) for b in session.blocks if b["title"] == "School")
        expect(school == [((0, 1, 3, 4), "08:00"), ((2,), "09:00")], f"school is {school}")

    def week_beside(r: Rig) -> Step:
        yield from r.tab("week")
        yield from r.reveal(4, 9 * 60, 11 * 60)
        yield from r.drag(r.chip(ids["math"]), r.at(4, 10 * 60))
        yield from r.settled()
        got = block(ids["math"])
        expect(
            (got["days"], got.get("start"), got.get("pinned")) == ([4], "10:00", True),
            f"math is {got['days']} {got.get('start')}",
        )

    def week_folded_waiting(r: Rig) -> Step:
        """At 800 px the rail is folded: open Not placed yet in place, then drag homework on."""
        yield from r.tab("week")
        window.resize(800, 820)
        yield ("wait", 400)
        chip = window.findChild(QPushButton, "railWaitingChip")
        expect(chip is not None and chip.isVisible(), "the folded Not placed yet chip is missing")
        yield from r.click(chip.mapToGlobal(chip.rect().center()))
        row = window.findChild(QWidget, "railWaitingRow")
        expect(row is not None and row.isVisible(), "the waiting homework row did not open")
        # Friday: the clock is Thursday 15:40, and a drop on a day already past is refused.
        yield from r.reveal(4, 15 * 60, 18 * 60)
        yield from r.drag(r.chip(ids["math"]), r.at(4, 16 * 60))
        yield from r.settled()
        got = block(ids["math"])
        expect(
            (got["days"], got.get("start"), got.get("pinned")) == ([4], "16:00", True),
            f"math is {got['days']} {got.get('start')}",
        )
        window.resize(1280, 820)
        yield ("wait", 200)

    def week_past_due(r: Rig) -> Step:
        yield from r.tab("week")
        yield from r.reveal(5, 16 * 60 + 30, 18 * 60 + 30)
        yield from r.drag(r.chip(ids["poster"]), r.at(5, 17 * 60))
        said = session.message
        yield from r.settled()
        got = block(ids["poster"])
        expect(not got.get("start"), f"poster was placed at {got['days']} {got.get('start')}")
        expect("after it is due" in said, f"said {said!r}")

    def week_open_day(r: Rig) -> Step:
        yield from r.tab("week")
        yield from r.click(r.day_name(4))
        yield ("wait", 400)
        friday = (thursday + timedelta(days=1)).date().isoformat()
        show_day(friday)

    def unchanged(revision: int) -> None:
        got = block(ids["essay"])
        expect((got["days"], got["start"]) == ([3], "19:00"), f"essay is {got['days']} {got['start']}")
        expect(session.revision == revision, f"a save was made: revision {revision} -> {session.revision}")

    def day_resize_top(r: Rig) -> Step:
        yield from day_tab(r)
        yield from r.reveal(3, 18 * 60, 20 * 60 + 30)
        edge = r.edge(ids["essay"], 3, end=False)
        yield from r.drag(edge, edge + (r.at(3, 18 * 60 + 30) - r.at(3, 19 * 60)))
        yield from r.settled()
        got = block(ids["essay"])
        expect(
            (got["start"], got["duration_min"]) == ("18:30", 90),
            f"essay is {got['start']} {got['duration_min']}",
        )

    def week_resize_bottom(r: Rig) -> Step:
        yield from r.tab("week")
        yield from r.reveal(3, 18 * 60 + 30, 21 * 60)
        edge = r.edge(ids["essay"], 3, end=True)
        yield from r.drag(edge, edge + (r.at(3, 20 * 60 + 30) - r.at(3, 20 * 60)))
        yield from r.settled()
        got = block(ids["essay"])
        expect(
            (got["start"], got["duration_min"]) == ("19:00", 90),
            f"essay is {got['start']} {got['duration_min']}",
        )

    def click_create(r: Rig, day: int, at: int) -> Step:
        """A click on free time makes up to an hour there."""
        yield from r.reveal(day, at - 60, at + 120)
        yield from r.click(r.at(day, at))
        yield from r.accept_dialog("Club")
        yield from r.settled()
        made = [b for b in session.blocks if b["title"] == "Club"]
        expect(
            [(b["days"], b["start"], b["duration_min"]) for b in made] == [([day], hhmm(at), 60)],
            f"made {[(b['days'], b['start'], b['duration_min']) for b in made]}",
        )

    def day_click_create(r: Rig) -> Step:
        yield from day_tab(r)
        yield from click_create(r, 3, 21 * 60)

    def week_click_create(r: Rig) -> Step:
        yield from r.tab("week")
        yield from click_create(r, 5, 10 * 60)

    def day_past_due(r: Rig) -> Step:
        """The poster is due Friday. Given Saturday on Day, it stays in the tray and says why."""
        yield from r.tab("week")
        yield from r.click(r.day_name(5))
        yield ("wait", 400)
        show_day((thursday + timedelta(days=2)).date().isoformat())
        yield from r.reveal(5, 16 * 60 + 30, 18 * 60 + 30)
        yield from r.drag(r.chip(ids["poster"]), r.at(5, 17 * 60))
        said = session.message
        yield from r.settled()
        got = block(ids["poster"])
        expect(not got.get("start"), f"poster was placed at {got['days']} {got.get('start')}")
        expect("after it is due" in said, f"said {said!r}")

    def day_escape(r: Rig) -> Step:
        yield from day_tab(r)
        yield from r.reveal(3, 18 * 60 + 30, 21 * 60 + 30)
        revision = session.revision
        box = r.block_rect(ids["essay"], 3)
        yield from r.drag(
            middle(box),
            middle(box) + (r.at(3, 20 * 60) - r.at(3, 19 * 60)),
            held=lambda: xdo("key", "Escape"),
        )
        yield ("wait", 400)
        unchanged(revision)

    def week_switch_away(r: Rig) -> Step:
        """Held on Week, the student presses D for Day and lets go there: nothing moves."""
        yield from r.tab("week")
        yield from r.reveal(3, 17 * 60 + 30, 20 * 60 + 30)
        revision = session.revision
        box = r.block_rect(ids["essay"], 3)

        def to_day() -> Step:
            xdo("key", "d")
            yield ("wait", 500)

        yield from r.drag(middle(box), r.carried(middle(box), 19 * 60, 4, 18 * 60), held=to_day)
        yield ("wait", 400)
        unchanged(revision)

    def day_dwell(r: Rig) -> Step:
        """Resting a held block at the start of the hours scrolls them back, and it lands earlier."""
        yield from day_tab(r)
        scroll = r.zoom()
        scroll.scroll_to(17 * 60, above=90)
        yield ("wait", 200)
        port = scroll.viewport()
        box = r.block_rect(ids["essay"], 3)
        grab = middle(box)
        # Twelve pixels inside the edge of the viewport where time starts: its top when the hours
        # run down, its left when they run across.
        if scroll.axis is Axis.DOWN:
            edge = QPoint(grab.x(), port.mapToGlobal(QPoint(0, 12)).y())
        else:
            edge = QPoint(port.mapToGlobal(QPoint(12, 0)).x(), grab.y())
        held_at = r.minute_under(grab) - 19 * 60
        reachable = r.minute_under(edge) - held_at
        under: list[float] = []
        yield from r.drag(grab, edge, held=lambda: under.append(r.minute_under(edge)), rest=1500)
        yield from r.settled()
        start = minutes(block(ids["essay"])["start"])
        expect(
            start <= reachable - 60,
            f"essay starts {hhmm(start)}; without scrolling it could reach {hhmm(round(reachable))}",
        )
        # Hours as short as Clay's scroll back to midnight while it rests, and a block held half an
        # hour in starts there, no earlier.
        let_go = max(under[0] - held_at, FIRST)
        expect(
            abs(start - let_go) <= 20,
            f"essay starts {hhmm(start)} but was let go at {hhmm(round(let_go))}",
        )

    def week_save_mid_drag(r: Rig) -> Step:
        """The clock ticks and another change is saved while the essay is held. Both land, once."""
        yield from r.tab("week")
        yield from r.reveal(3, 17 * 60 + 30, 20 * 60 + 30)
        box = r.block_rect(ids["essay"], 3)

        def meanwhile() -> Step:
            later = base_now() + 5 * 60_000
            session.now_ms = lambda: later
            session.add_block(
                {
                    "id": "rig-dinner",
                    "title": "Dinner",
                    "kind": "locked",
                    "category": "meals",
                    "start": "18:00",
                    "duration_min": 30,
                    "days": [5],
                }
            )
            session.save()
            yield ("until", lambda: not session.busy and not session.dirty, 8000, "the other save")
            window._on_week()
            yield ("wait", 200)

        yield from r.drag(
            middle(box), r.carried(middle(box), 19 * 60, 4, 18 * 60), held=meanwhile, rest=100
        )
        yield from r.settled()
        essays = [b for b in session.blocks if b.get("assignment_id") == "essay"]
        expect(
            [(b["days"], b["start"]) for b in essays] == [([4], "18:00")],
            f"essay sessions {[(b['days'], b['start']) for b in essays]}",
        )
        expect(block("rig-dinner") is not None, "the save made while it was held was lost")

    def week_second_move_in_flight(r: Rig) -> Step:
        """A second block let go while the first one's save is still on its way. Both land."""
        yield from r.tab("week")
        session.add_block(
            {
                "id": "rig-club",
                "title": "Club",
                "kind": "locked",
                "category": "extra",
                "start": "10:00",
                "duration_min": 60,
                "days": [5],
            }
        )
        session.save()
        yield from r.settled()

        def slow(method, path, payload, on_success, on_error, *rest, **named):
            late = (
                on_success
                if method == "GET"
                else (lambda data: QTimer.singleShot(1500, lambda: on_success(data)))
            )
            return base_request(method, path, payload, late, on_error, *rest, **named)

        session.client.request = slow
        yield from r.reveal(3, 17 * 60 + 30, 20 * 60 + 30)
        box = r.block_rect(ids["essay"], 3)
        yield from r.drag(middle(box), middle(box) + (r.at(3, 20 * 60) - r.at(3, 19 * 60)), after=50)
        in_flight: list[bool] = []
        yield from r.reveal(5, 9 * 60 + 30, 12 * 60 + 30)
        club = r.block_rect("rig-club", 5)
        yield from r.drag(
            middle(club),
            middle(club) + (r.at(5, 12 * 60) - r.at(5, 10 * 60)),
            held=lambda: in_flight.append(session.busy),
            rest=50,
        )
        expect(in_flight == [True], "the first save had already landed, so nothing was in flight")
        session.client.request = base_request
        yield ("wait", 1800)
        yield from r.settled()
        got = block(ids["essay"])
        expect((got["days"], got["start"]) == ([3], "20:00"), f"essay is {got['days']} {got['start']}")
        club_now = block("rig-club")
        expect(club_now["start"] == "12:00", f"club is {club_now['start']}")

    def day_open(r: Rig) -> Step:
        """A click opens the essay. A double-click, from habit, opens it once: its second click lands
        on the editor the first one opened and does nothing there."""
        yield from day_tab(r)
        yield from r.reveal(3, 18 * 60 + 30, 20 * 60 + 30)
        for how in ("click", "double-click"):
            point = middle(r.block_rect(ids["essay"], 3))
            yield from (r.click(point) if how == "click" else r.double_click(point))
            yield (
                "until",
                lambda: isinstance(QApplication.activeModalWidget(), QDialog),
                3000,
                f"the essay to open on a {how}",
            )
            dialog = QApplication.activeModalWidget()
            title = dialog.findChild(QLineEdit, "homeworkTitle")
            opened = title.text() if title is not None else dialog.windowTitle()
            dialog.reject()
            yield ("wait", 600)
            expect(opened == "History essay", f"a {how} opened {opened!r}")
            second = QApplication.activeModalWidget()
            expect(second is None, f"a {how} opened a second editor: {second!r}")
        yield from r.settled()
        expect(block(ids["essay"])["start"] == "19:00", "opening the essay moved it")

    def week_agrees_with_day(r: Rig) -> Step:
        """Moved on Week, the essay is on Friday's Day at that time, and no longer on Thursday."""
        yield from r.tab("week")
        yield from r.reveal(3, 17 * 60 + 30, 20 * 60 + 30)
        box = r.block_rect(ids["essay"], 3)
        yield from r.drag(middle(box), r.carried(middle(box), 19 * 60, 4, 18 * 60))
        yield from r.settled()
        yield from r.tab("week")
        expect(
            all(item.block_rect(ids["essay"], 3) is None for item in r.surfaces("hours")),
            "still drawn on Thursday",
        )
        yield from r.click(r.day_name(4))
        yield ("wait", 400)
        show_day((thursday + timedelta(days=1)).date().isoformat())
        yield from r.reveal(4, 17 * 60, 20 * 60)
        drawn = r.block_rect(ids["essay"], 4)
        expect(drawn.contains(r.at(4, 18 * 60 + 30)), "Day draws it somewhere other than 18:00")

    def small_and_large() -> Step:
        window.resize(1150, 768)
        window._look = sanitize_look(
            {**window._look, "knobs": {**window._look.get("knobs", {}), "text": "large"}}
        )
        window._apply_appearance()
        yield ("wait", 500)
        # The window manager's resize and the larger text can land after that wait, and the bar then
        # moves: a click on Week found from where it had been landed beside Day. Wait until the
        # window is the new size and the bar has kept still for 300 ms.
        week = window.findChild(QPushButton, "viewWeek")
        seen: dict = {"at": None, "since": 0.0}

        def still() -> bool:
            at = (window.size(), week.mapToGlobal(week.rect().center()))
            now = time.monotonic()
            if at != seen["at"]:
                seen["at"], seen["since"] = at, now
                return False
            return window.size() == QSize(1150, 768) and now - seen["since"] >= 0.3

        yield ("until", still, 5000, "the window and its top bar to settle at 1150 by 768")

    def on_screen(widget: QWidget) -> bool:
        frame = QRect(window.mapToGlobal(QPoint(0, 0)), window.size())
        return widget.isVisible() and frame.contains(QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size()))

    def name_shown(point: QPoint) -> bool:
        """Whether a day's name is on screen at this point: the hours that paint it are there, or a
        label or button of the window's is, wholly inside it."""
        widget = QApplication.widgetAt(point)
        if widget is None or widget.window() is not window:
            return False
        if getattr(widget, "takes_blocks", False):
            return True
        return isinstance(widget, (QLabel, QPushButton)) and on_screen(widget)

    def trays_whole() -> None:
        for key in ("math", "poster"):
            chip = next(
                (
                    w
                    for w in window.findChildren(QPushButton)
                    if w.property("tray") and w.property("block_id") == ids[key] and w.isVisible()
                ),
                None,
            )
            expect(chip is not None and on_screen(chip), f"the {key} chip is not wholly on screen")
            expect(chip.accessibleName().startswith(chip.held.title), f"the {key} chip lost its title")

    def week_small_large(r: Rig) -> Step:
        """At 1150 by 768 with large text: every day, the tray, and a quarter hour that moves."""
        yield from small_and_large()
        yield from r.tab("week")
        for day in range(7):
            expect(name_shown(r.day_name(day)), f"day {day}'s name is not on screen")
        trays_whole()
        yield from quarter_grab(r)

    def day_small_large(r: Rig) -> Step:
        yield from small_and_large()
        yield from day_tab(r)
        trays_whole()
        yield from quarter_grab(r)

    def reach(r: Rig) -> Step:
        """At every level the hours offer, 00:00 and 24:00 can be brought on screen."""
        scroll = r.zoom()
        for px in scroll.scale.levels:
            scroll.restore({scroll.scale.key: px})
            yield ("wait", 150)
            yield from r.reveal(3, 0, 60)
            expect(r.surface("hours", 3, 0).in_view(3, 0), f"00:00 is not on screen at {px} px an hour")
            yield from r.reveal(3, 24 * 60 - 60, 24 * 60)
            expect(
                r.surface("hours", 3, 24 * 60).in_view(3, 24 * 60),
                f"24:00 is not on screen at {px} px an hour",
            )

    def week_reach(r: Rig) -> Step:
        yield from r.tab("week")
        yield from reach(r)

    def day_reach(r: Rig) -> Step:
        yield from day_tab(r)
        yield from reach(r)

    def week_zoom_move(r: Rig) -> Step:
        """Zoom in twice with the corner button and out once with Ctrl and the wheel, then move."""
        yield from r.tab("week")
        scroll = r.zoom()
        into = scroll.buttons.into
        for _ in range(2):
            yield from r.click(into.mapToGlobal(into.rect().center()))
        twice = scroll.scale.step(scroll.scale.default, 2)
        expect(scroll.px == twice, f"two clicks on zoom in show {scroll.px} px an hour, not {twice}")
        yield from r.reveal(3, 18 * 60, 20 * 60 + 30)
        under = middle(r.block_rect(ids["essay"], 3))
        before = r.minute_under(under)
        yield from r.wheel(under, -1)
        expect(scroll.px == scroll.scale.step(twice, -1), f"the wheel left it at {scroll.px} px an hour")
        after = r.minute_under(under)
        expect(abs(after - before) <= 15, f"the pointer was over {before:.0f} and is now over {after:.0f}")
        yield from r.reveal(3, 17 * 60 + 30, 20 * 60 + 30)
        box = r.block_rect(ids["essay"], 3)
        yield from r.drag(middle(box), r.carried(middle(box), 19 * 60, 4, 18 * 60))
        yield from r.settled()
        got = block(ids["essay"])
        expect((got["days"], got["start"]) == ([4], "18:00"), f"essay is {got['days']} {got['start']}")

    def day_zoom_resize(r: Rig) -> Step:
        """Zoom in twice with Ctrl and the wheel, then stretch the essay by half an hour."""
        yield from day_tab(r)
        scroll = r.zoom()
        yield from r.reveal(3, 18 * 60 + 30, 21 * 60)
        yield from r.wheel(middle(r.block_rect(ids["essay"], 3)), 2)
        twice = scroll.scale.step(scroll.scale.default, 2)
        expect(scroll.px == twice, f"two notches show {scroll.px} px an hour, not {twice}")
        yield from r.reveal(3, 18 * 60 + 30, 21 * 60)
        edge = r.edge(ids["essay"], 3, end=True)
        yield from r.drag(edge, edge + (r.at(3, 20 * 60 + 30) - r.at(3, 20 * 60)))
        yield from r.settled()
        got = block(ids["essay"])
        expect(
            (got["start"], got["duration_min"]) == ("19:00", 90),
            f"essay is {got['start']} {got['duration_min']}",
        )

    def quarter_grab(r: Rig) -> Step:
        """A 15-minute block moves when pressed a quarter, half and three quarters of the way in."""
        session.add_block(
            {
                "id": "rig-quiz",
                "title": "Quiz",
                "kind": "locked",
                "category": "class",
                "start": "20:30",
                "duration_min": 15,
                "days": [3],
            }
        )
        session.save()
        yield from r.settled()
        start = 20 * 60 + 30
        for share in (0.25, 0.5, 0.75):
            # Two hours and more below it on screen, so the drop never rests where the hours scroll.
            yield from r.reveal(3, start - 60, start + 150)
            grab = r.along("rig-quiz", 3, share)
            # A rig aiming across the lane would press the middle of the quiz three times over.
            under = r.minute_under(grab) - start
            expect(
                abs(under - 15 * share) <= 2,
                f"aimed {share:.0%} into the quiz, the pointer is {under:.1f} min in, not {15 * share:.2f}",
            )
            yield from r.drag(grab, grab + (r.at(3, start + 30) - r.at(3, start)))
            yield from r.settled()
            start += 30
            got = block("rig-quiz")
            want = f"{start // 60:02d}:{start % 60:02d}"
            expect(
                (got["days"], got["start"], got["duration_min"]) == ([3], want, 15),
                f"pressed {share:.0%} in, the quiz is {got['days']} {got['start']} for "
                f"{got['duration_min']} min, not {want} for 15",
            )

    def week_quarter_grab(r: Rig) -> Step:
        yield from r.tab("week")
        yield from quarter_grab(r)

    def day_quarter_grab(r: Rig) -> Step:
        yield from day_tab(r)
        yield from quarter_grab(r)

    def month_times(r: Rig) -> Step:
        yield from r.tab("month")
        month = r.surface("month")
        words = month.chip_words(ids["essay"], thursday_iso)
        expect(words == "19:00 History essay", f"the chip reads {words!r}")

    def month_open_day(r: Rig) -> Step:
        yield from r.tab("month")
        month = r.surface("month")
        friday = (thursday + timedelta(days=1)).date().isoformat()
        yield from r.click(month.cell_point(friday))
        yield ("wait", 400)
        expect(
            (session.planner_view, session.selected_day) == ("day", friday),
            f"showing {session.planner_view} {session.selected_day}",
        )

    def month_move_date(r: Rig) -> Step:
        yield from r.tab("month")
        month = r.surface("month")
        saturday = (thursday + timedelta(days=2)).date().isoformat()
        yield from r.drag(month.chip_point(ids["essay"], thursday_iso), month.cell_point(saturday))
        yield from r.settled()
        got = block(ids["essay"])
        expect((got["days"], got["start"]) == ([5], "19:00"), f"essay is {got['days']} {got['start']}")

    def the_day(offset: int) -> str:
        """A date counted from Monday of the open week."""
        return (datetime.fromisoformat(seed_week) + timedelta(days=offset)).date().isoformat()

    def month_tab(r: Rig) -> Step:
        """Month on screen, once it has drawn the open week's dates. Returns the month."""
        yield from r.tab("month")

        def drawn() -> bool:
            with contextlib.suppress(NoSurface):
                return r.surface("month").index_of(thursday_iso) is not None
            return False

        yield ("until", drawn, 5000, "Month to draw this week")
        return r.surface("month")

    def month_in_view(month: object, *isos: str) -> Step:
        """Scroll the month so each of these dates is wholly on screen and clear of the edges, where
        a held chip scrolls it."""
        for iso in isos:
            if month.index_of(iso) is None:
                raise NoSurface(f"{iso} is not in the month on screen")
            month.reveal(iso)
        yield ("wait", 150)

    def drawn_chip(month: object, block_id: str, iso: str) -> QPoint:
        """The middle of a block's chip on a date, failing in words when the date hides it behind
        "+N more" although the month promises room for more than it shows."""
        at = month.index_of(iso)
        shown, more = month.chip_boxes(at)
        if not any(chip.block_id == block_id for chip, _box in shown):
            raise AssertionError(
                f"{iso} hides {block_id} behind +{more} more and shows only "
                f"{[chip.words for chip, _box in shown]}: its row is {month.cell_rect(at).height():.0f} px "
                f"with chips {month.pitch():.0f} px apart, the month keeps rows of at least "
                f"{month.least_row()} px, and is {month.height()} px tall with a minimum of "
                f"{month.minimumHeight()}"
            )
        return month.chip_point(block_id, iso)

    def essays() -> list[tuple[list[int], str | None]]:
        return [(b["days"], b.get("start")) for b in session.blocks if b.get("assignment_id") == "essay"]

    def month_many(r: Rig) -> Step:
        """Thursday holds more than its date has room for. The date says "+N more", and a click on it
        opens a Day that draws every one of them."""
        added = {
            "rig-lunch": ("Lunch club", "14:45", 45),
            "rig-piano": ("Piano", "17:45", 45),
            "rig-reading": ("Reading", "20:15", 45),
            "rig-chores": ("Chores", "21:15", 45),
            # 0.17's Month grows a row to its chips when the window has the height, so a date is only
            # short of room with more than a tall window can show.
            "rig-run": ("Run", "06:00", 30),
            "rig-stretch": ("Stretch", "06:45", 30),
            "rig-breakfast": ("Breakfast", "07:15", 30),
            "rig-journal": ("Journal", "22:00", 30),
            "rig-tidy": ("Tidy", "22:45", 30),
            "rig-podcast": ("Podcast", "23:15", 30),
        }
        for key, (title, start, length) in added.items():
            session.add_block(
                {
                    "id": key,
                    "title": title,
                    "kind": "locked",
                    "category": "extra",
                    "start": start,
                    "duration_min": length,
                    "days": [3],
                }
            )
        session.save()
        yield from r.settled()
        month = yield from month_tab(r)
        yield from month_in_view(month, thursday_iso)
        shown, more = month.chip_boxes(month.index_of(thursday_iso))
        expect(
            more > 0,
            f"Thursday shows all {len(shown)} of its chips, so nothing is behind +N more to test",
        )
        yield from r.click(month.cell_point(thursday_iso))
        yield ("wait", 400)
        show_day(thursday_iso)
        missing = []
        for key, (title, start, length) in added.items():
            yield from r.reveal(3, minutes(start) - 30, minutes(start) + length + 30)
            if all(surface.block_rect(key, 3) is None for surface in r.surfaces("hours")):
                missing.append(title)
        expect(not missing, f"Thursday's Day does not draw {missing}")

    def month_across_sunday(r: Rig) -> Step:
        """The essay, due next week, is carried from Sunday onto the Monday after. It leaves this
        week, and the next week has it once, on Monday at 19:00.

        The seeded essay is due this Sunday, which Monday is after; the date would rightly refuse
        it. So it is first given next Sunday as its deadline."""
        sunday, next_monday = the_day(6), the_day(7)
        homework = session.assignments["essay"]
        session.add_homework({**homework, "due": sunday_due(next_monday)})
        session.add_block({**block(ids["essay"]), "days": [6], "start": "19:00", "pinned": True})
        session.save()
        yield from r.settled()
        expect(essays() == [([6], "19:00")], f"before the drag the essay is {essays()}, not Sunday 19:00")
        try:
            month = yield from month_tab(r)
            yield from month_in_view(month, sunday, next_monday)
            seen: list[tuple] = []
            yield from r.drag(
                drawn_chip(month, ids["essay"], sunday),
                month.cell_point(next_monday),
                held=lambda: seen.append((window.hand.month_target, window.hand.month_verdict)),
            )
            said = session.message
            yield from r.settled()
            left = essays()
            session.load_week(next_monday)
            yield (
                "until",
                lambda: not session.busy and session.week_start == next_monday,
                8000,
                "the next week to load",
            )
            there = essays()
        finally:
            yield from clear_next_week(next_monday)
        expect(
            seen and seen[0][0] == next_monday,
            f"held over {seen[0][0] if seen else None}, not {next_monday}",
        )
        expect(left == [], f"the essay is still in this week at {left}; said {said!r}; held {seen}")
        expect(there == [([0], "19:00")], f"the next week has the essay at {there}, not once on Monday 19:00")

    def clear_next_week(next_monday: str) -> Step:
        """Take the essay out of the next week and open this week again, so no later scenario finds
        it there. Runs whether the scenario passed or not."""
        yield ("until", lambda: not session.busy, 8000, "the session to be free")
        if session.week_start != next_monday:
            session.load_week(next_monday, discard=True)
            yield (
                "until",
                lambda: not session.busy and session.week_start == next_monday,
                8000,
                "the next week to load for clearing",
            )
        kept = [b for b in session.blocks if b.get("assignment_id") != "essay"]
        if len(kept) != len(session.blocks):
            session.blocks = kept
            session.dirty = True
            session.save()
            yield ("until", lambda: not session.busy and not session.dirty, 8000, "the next week to clear")
        session.load_week(seed_week, discard=True)
        yield (
            "until",
            lambda: not session.busy and session.week_start == seed_week,
            8000,
            "this week to load again",
        )

    def month_same_date(r: Rig) -> Step:
        """The essay is picked up and let go on its own date. Nothing is saved, and Month stays open."""
        month = yield from month_tab(r)
        yield from month_in_view(month, thursday_iso)
        revision = session.revision
        yield from r.drag(drawn_chip(month, ids["essay"], thursday_iso), month.cell_point(thursday_iso))
        expect(session.planner_view == "month", f"letting go on its own date opened {session.planner_view}")
        yield from r.settled()
        unchanged(revision)

    def month_series_one_date(r: Rig) -> Step:
        """School on Wednesday carried to Saturday. Only that day moves; the others keep the series."""
        month = yield from month_tab(r)
        wednesday, saturday = the_day(2), the_day(5)
        yield from month_in_view(month, wednesday, saturday)
        yield from r.drag(drawn_chip(month, "school", wednesday), month.cell_point(saturday))
        yield from r.settled()
        school = sorted((tuple(b["days"]), b["start"]) for b in session.blocks if b["title"] == "School")
        expect(school == [((0, 1, 3, 4), "08:00"), ((5,), "08:00")], f"school is {school}")

    def month_past_due(r: Rig) -> Step:
        """The poster is due Friday and sits on Friday at 17:00. Held over Saturday, the date says it
        would be after it is due; let go there, it stays on Friday and the message says why.

        Friday rather than Thursday: Thursday already holds School, Soccer and the essay, so a fourth
        chip there sits behind "+N more", where no pointer can pick it up."""
        session.add_block({**block(ids["poster"]), "start": "17:00", "days": [4], "pinned": True})
        session.save()
        yield from r.settled()
        placed = block(ids["poster"])
        expect(
            (placed["days"], placed.get("start")) == ([4], "17:00"),
            f"before the drag the poster is {placed['days']} {placed.get('start')}, not Friday 17:00",
        )
        month = yield from month_tab(r)
        friday, saturday = the_day(4), the_day(5)
        yield from month_in_view(month, friday, saturday)
        seen: list[tuple] = []
        yield from r.drag(
            drawn_chip(month, ids["poster"], friday),
            month.cell_point(saturday),
            held=lambda: seen.append((window.hand.month_target, window.hand.month_verdict)),
        )
        said = session.message
        yield from r.settled()
        expect(seen and seen[0][0] == saturday, f"held over {seen[0][0] if seen else None}, not {saturday}")
        verdict = seen[0][1]
        expect(verdict is not None and not verdict.ok, f"Saturday took the poster: verdict {verdict}")
        expect("after it is due" in verdict.words, f"Saturday said {verdict.words!r}")
        got = block(ids["poster"])
        expect(
            (got["days"], got.get("start")) == ([4], "17:00"),
            f"poster is {got['days']} {got.get('start')}, not Friday 17:00",
        )
        expect("after it is due" in said, f"said {said!r}")

    def month_save_refused(r: Rig) -> Step:
        """The server turns the essay's move away as a conflict. The message says it was not saved,
        and after a reload the essay is where it was, once, and Thursday draws it once."""
        month = yield from month_tab(r)
        saturday = the_day(5)
        yield from month_in_view(month, thursday_iso, saturday)
        refused: list[str] = []

        def refuse(method, path, payload, on_success, on_error, *rest, **named):
            if method == "POST" and path == "/api/changes":
                session.client.request = base_request
                refused.append(path)
                QTimer.singleShot(50, lambda: on_error(_error(409)))
                return None
            return base_request(method, path, payload, on_success, on_error, *rest, **named)

        def chips_of_essay() -> dict[str, int]:
            return {
                cell.iso: sum(chip.block_id == ids["essay"] for chip in cell.chips)
                for cell in month.cells
                if any(chip.block_id == ids["essay"] for chip in cell.chips)
            }

        session.client.request = refuse
        try:
            yield from r.drag(drawn_chip(month, ids["essay"], thursday_iso), month.cell_point(saturday))
            yield ("until", lambda: bool(refused) and not session.busy, 8000, "the save to be turned away")
            yield ("wait", 200)
            said = session.message
            before_reload = chips_of_essay()
        finally:
            session.client.request = base_request
            yield from r.settled()
        yield ("wait", 200)
        after_reload = chips_of_essay()
        expect("not saved" in said.lower(), f"said {said!r}")
        expect(
            before_reload == {thursday_iso: 1},
            f"before the reload Month drew the essay on {before_reload}, not once on Thursday",
        )
        expect(essays() == [([3], "19:00")], f"after the reload the essay is {essays()}")
        expect(
            after_reload == {thursday_iso: 1},
            f"after the reload Month draws the essay on {after_reload}, not once on Thursday",
        )

    def myday_tab(r: Rig) -> Step:
        # Measured once the top bar has settled: measured straight after a save, it was still laid
        # out a button to the left, and the click landed on Month.
        yield ("wait", 300)
        button = window.findChild(QPushButton, "viewMyDay")
        yield from r.click(button.mapToGlobal(button.rect().center()))
        yield ("wait", 500)
        shown = window.planner.currentWidget()
        expect(getattr(shown, "layout_id", "") == r.design, f"My day shows {type(shown).__name__}")

    def myday_carry(r: Rig) -> Step:
        """The essay held by its middle at 19:30 and let go at 21:00, along the bar or round the dial."""
        yield from myday_tab(r)
        yield from r.drag(r.at(3, 19 * 60 + 30), r.at(3, 21 * 60))

    def myday_move(r: Rig) -> Step:
        yield from myday_carry(r)
        yield from r.settled()
        got = block(ids["essay"])
        expect((got["days"], got["start"]) == ([3], "20:30"), f"essay is {got['days']} {got['start']}")

    def myday_past_due(r: Rig) -> Step:
        """Due Thursday at 20:00, the essay cannot end at 21:30: it stays, and the screen says why."""
        session.assignments["essay"] = {**session.assignments["essay"], "due": f"{thursday_iso}T20:00"}
        session.dirty_assignments.add("essay")
        session.dirty = True
        session.save()
        yield ("until", lambda: not session.busy and not session.dirty, 8000, "the due time to save")
        revision = session.revision
        yield from myday_carry(r)
        said = session.message
        yield from r.settled()
        unchanged(revision)
        expect("after it is due" in said, f"said {said!r}")

    def myday_open(r: Rig) -> Step:
        yield from myday_tab(r)
        yield from r.click(r.at(3, 19 * 60 + 30))
        yield (
            "until",
            lambda: isinstance(QApplication.activeModalWidget(), QDialog),
            3000,
            "the essay to open",
        )
        dialog = QApplication.activeModalWidget()
        title = dialog.findChild(QLineEdit, "homeworkTitle")
        opened = title.text() if title is not None else dialog.windowTitle()
        dialog.reject()
        yield ("wait", 300)
        expect(opened == "History essay", f"opened {opened!r}")

    scenarios = [
        Scenario("day-move", "day", day_move),
        Scenario("day-resize", "day", day_resize),
        Scenario("day-create", "day", day_create),
        Scenario("day-homework-in", "day", day_homework_in),
        Scenario("day-zoom-resize", "day", day_zoom_resize),
        Scenario("day-quarter-grab", "day", day_quarter_grab),
        Scenario("day-reach", "day", day_reach),
        Scenario("day-resize-top", "day", day_resize_top),
        Scenario("day-click-create", "day", day_click_create),
        Scenario("day-past-due", "day", day_past_due),
        Scenario("day-escape", "day", day_escape),
        Scenario("day-dwell", "day", day_dwell),
        Scenario("day-open", "day", day_open),
        Scenario("day-small-large", "day", day_small_large),
        Scenario("week-move-day", "week", week_move_day),
        Scenario("week-resize-top", "week", week_resize_top),
        Scenario("week-create", "week", week_create),
        Scenario("week-series-one-day", "week", week_series),
        Scenario("week-beside", "week", week_beside),
        Scenario("week-folded-waiting", "week", week_folded_waiting, only=("classic",)),
        Scenario("week-past-due", "week", week_past_due),
        Scenario("week-open-day", "week", week_open_day),
        Scenario("week-reach", "week", week_reach),
        Scenario("week-zoom-move", "week", week_zoom_move),
        Scenario("week-quarter-grab", "week", week_quarter_grab),
        Scenario("week-resize-bottom", "week", week_resize_bottom),
        Scenario("week-click-create", "week", week_click_create),
        Scenario("week-switch-away", "week", week_switch_away),
        Scenario("week-save-mid-drag", "week", week_save_mid_drag),
        Scenario("week-second-move-in-flight", "week", week_second_move_in_flight),
        Scenario("week-agrees-with-day", "week", week_agrees_with_day),
        Scenario("week-small-large", "week", week_small_large),
        Scenario("month-times", "month", month_times),
        Scenario("month-open-day", "month", month_open_day),
        Scenario("month-move-date", "month", month_move_date),
        Scenario("month-many", "month", month_many),
        Scenario("month-across-sunday", "month", month_across_sunday),
        Scenario("month-same-date", "month", month_same_date),
        Scenario("month-series-one-date", "month", month_series_one_date),
        Scenario("month-past-due", "month", month_past_due),
        Scenario("month-save-refused", "month", month_save_refused),
        Scenario("myday-move", "myday", myday_move),
        Scenario("myday-past-due", "myday", myday_past_due),
        Scenario("myday-open", "myday", myday_open),
    ]
    if args.list:
        for scenario in scenarios:
            every = ",".join(MY_DAY) if scenario.tab == "myday" else "every design"
            print(scenario.tab, scenario.name, ",".join(scenario.only) or every)
        return 0

    chosen_designs = [args.design] if args.design else [*DESIGNS, *MY_DAY]
    chosen = [
        s
        for s in scenarios
        if (not args.tab or s.tab == args.tab) and (not args.scenario or s.name == args.scenario)
    ]
    results: list[dict] = []

    def reset() -> None:
        while QApplication.activeModalWidget() is not None:
            QApplication.activeModalWidget().reject()
            app.processEvents()
        if session.week_start != seed_week or session.conflict:
            # A scenario that stopped on another week, or with a save refused: the seed belongs to
            # this week, and a session in conflict saves nothing until it reloads.
            session.load_week(seed_week, discard=True)
            wait_until(app, lambda: not session.busy and session.week_start == seed_week, 20)
        for key, due in seed_dues.items():
            if session.assignments[key]["due"] != due:
                session.assignments[key] = {**session.assignments[key], "due": due}
                session.dirty_assignments.add(key)
        session.blocks = [dict(item) for item in seed]
        session.dirty = True
        session.save()
        wait_until(app, lambda: not session.busy and not session.dirty, 20)
        session.selected_day = thursday_iso
        session._say("")
        session.now_ms, session.client.request = base_now, base_request
        if window.size() != QSize(1280, 820) or window._look != base_look:
            window.resize(1280, 820)
            window._look = dict(base_look)
            window._apply_appearance()
            wait_until(app, lambda: True, 0.3)
        # Every scenario starts at each surface's own zoom.
        for scroll in window.findChildren(HoursScroll):
            scroll.restore({scroll.scale.key: scroll.scale.default})

    saved_options = {args.design: parse_options(args.design, args.option)} if args.option else {}

    def use_design(design: str) -> None:
        if design in MY_DAY:
            window._layout = sanitize_layout({"main": "classic", "day": design, "options": saved_options})
        else:
            window._layout = sanitize_layout({"main": design, "day": "one", "options": saved_options})
        window._apply_appearance()
        session.set_view("week")
        window._on_week()
        wait_until(app, lambda: True, 0.5)

    plan = [
        (design, scenario)
        for design in chosen_designs
        for scenario in chosen
        if (not scenario.only or design in scenario.only) and (scenario.tab == "myday") == (design in MY_DAY)
    ]
    if not plan:
        asked = " ".join(
            f"--{flag} {getattr(args, flag)}" for flag in ("design", "tab", "scenario") if getattr(args, flag)
        )
        print(f"No scenario matches {asked}; --list names them.", file=sys.stderr, flush=True)
        server.stop()
        return 2

    import gc as _gc

    if os.environ.get("RIG_GC_REPORT"):
        # Diagnosis only: keep what the collector finds instead of freeing it, and name the Qt
        # objects among it after each scenario.
        _gc.set_debug(_gc.DEBUG_SAVEALL)

    def gc_report(label: str) -> None:
        if not os.environ.get("RIG_GC_REPORT"):
            return
        _gc.collect()
        found: dict[str, int] = {}
        for item in _gc.garbage:
            if isinstance(item, QObject):
                from shiboken6 import isValid

                alive = isValid(item)
                named = repr(item.objectName()) if alive else "(C++ side already gone)"
                name = f"{type(item).__module__}.{type(item).__qualname__} {named}"
                found[name] = found.get(name, 0) + 1
        print(f"GC after {label}: {found}", flush=True)
        _gc.garbage.clear()

    def run_all() -> Step:
        current = None
        for design, scenario in plan:
            if design != current:
                if current is not None:
                    recorder.finish(out / f"{current}.mp4")
                current = design
                use_design(design)
                recorder.begin(out / "frames" / design)
            gc_report(f"{design} before {scenario.name}")
            reset()
            rig.design, rig.scenario = design, scenario.name
            started = time.monotonic()
            outcome = {"design": design, "tab": scenario.tab, "scenario": scenario.name}
            try:
                yield from scenario.run(rig)
                outcome["result"] = "PASS"
            except NoSurface as missing:
                outcome.update(result="FAIL", why=f"no surface: {missing}")
            except AssertionError as wrong:
                outcome.update(result="FAIL", why=str(wrong))
            except Exception as broken:  # noqa: BLE001 - the rig reports, it does not stop
                outcome.update(
                    result="ERROR",
                    why=f"{type(broken).__name__}: {broken}",
                    trace=traceback.format_exc(limit=4),
                )
            outcome["seconds"] = round(time.monotonic() - started, 1)
            rig.shot("end")
            results.append(outcome)
            print(
                f"{outcome['result']:5s} {design:9s} {scenario.name:22s} {outcome.get('why', '')}", flush=True
            )
            xdo("mouseup", 1)
            yield ("wait", 100)
        if current is not None:
            recorder.finish(out / f"{current}.mp4")

    finished: list[bool] = []

    def drive(steps: Step) -> None:
        def dispatch(command: tuple) -> None:
            if command[0] == "wait":
                QTimer.singleShot(command[1], advance)
                return
            predicate, limit = command[1], command[2]
            waited_for = command[3] if len(command) > 3 else "something to happen"
            deadline = time.monotonic() + limit / 1000

            def poll() -> None:
                if predicate():
                    advance(True)
                elif time.monotonic() > deadline:
                    # A wait that runs out is a failure. Carrying on would let a save that never
                    # landed, or a week that never reloaded, pass as a result.
                    fail(Waited(f"waited {limit} ms for {waited_for}"))
                else:
                    QTimer.singleShot(20, poll)

            poll()

        def carry(step: Callable[[], tuple]) -> None:
            try:
                command = step()
            except StopIteration:
                finished.append(True)
                app.quit()
                return
            except Exception as broken:  # noqa: BLE001 - the rig reports and stops rather than hanging
                traceback.print_exc()
                python_errors.append(f"{type(broken).__name__}: {broken}")
                app.quit()
                return
            dispatch(command)

        def advance(value: object = None) -> None:
            carry(lambda: steps.send(value))

        def fail(error: BaseException) -> None:
            carry(lambda: steps.throw(error))

        advance()

    def ended_early() -> None:
        # A run that stops before its last scenario says what stopped it, rather than just stopping.
        if not finished:
            print("The app was told to quit before the run finished:", flush=True)
            traceback.print_stack()

    app.aboutToQuit.connect(ended_early)
    app.lastWindowClosed.connect(lambda: print("The last window closed.", flush=True))
    QTimer.singleShot(300, lambda: drive(run_all()))
    app.exec()
    line, code, payload = report_run(
        [(design, scenario.tab, scenario.name) for design, scenario in plan],
        results,
        bool(finished),
        python_error=python_errors[0] if python_errors else None,
        stopped_in=None if finished else (rig.scenario or None),
    )
    (out / "results.json").write_text(json.dumps(payload, indent=1))
    server.stop()
    print(f"\n{line} Screenshots, videos and results.json in {out}")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--design", choices=[*DESIGNS, *MY_DAY])
    parser.add_argument("--tab", choices=TABS)
    parser.add_argument("--scenario")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--out")
    parser.add_argument(
        "--option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="set one of --design's saved options, e.g. hero=today; repeat for more",
    )
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    parse_options(args.design, args.option)
    if args.list and not args.child:
        args.out = tempfile.mkdtemp()
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if args.child or args.list:
        return child_main(args)
    display, bus, runs_key = session_from_fwtest()
    return drive(args, display, bus, runs_key)


def drive(args: argparse.Namespace, display: str, bus: str, runs_key: str) -> int:
    """Run the scenarios in a child on the hidden display, and return its exit code."""
    runs = None if args.out else default_runs_folder(runs_key)
    out = Path(args.out) if args.out else runs / f"{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}"
    out.mkdir(parents=True, exist_ok=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"WAYLAND_DISPLAY", "QT_IM_MODULE", "XMODIFIERS"}
    }
    # XInput 2 off: on the hidden display Qt never hears xdotool's wheel through it, only through
    # the core protocol, and the zoom scenarios turn the wheel. Presses and drags arrive either way.
    env.update(
        DISPLAY=display,
        DBUS_SESSION_BUS_ADDRESS=bus,
        QT_QPA_PLATFORM="xcb",
        QT_XCB_NO_XI2="1",
        XDG_DATA_HOME=str(out / "data"),
        PYTHONFAULTHANDLER="1",
    )
    command = [sys.executable, __file__, "--child", "--out", str(out)]
    for flag in ("design", "tab", "scenario"):
        if getattr(args, flag):
            command += [f"--{flag}", getattr(args, flag)]
    for pair in args.option:
        command += ["--option", pair]
    try:
        return subprocess.run(command, env=env, cwd=ROOT).returncode
    finally:
        if runs is not None:
            prune_runs(runs)


if __name__ == "__main__":
    raise SystemExit(main())
