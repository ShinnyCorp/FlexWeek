"""Pictures of each design, drawn by the real views from a sample week, for setup to choose from.

A mock-up of a design goes stale the day the design changes. These are the views themselves, handed a
week that shows what each one is for, so the picture a student chooses is the app they get.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QPalette, QPixmap
from PySide6.QtWidgets import QWidget

from desktop.native.calendar import monday_of
from desktop.native.hours.classic import ClassicWeek
from desktop.native.hours.hand import Hand, Verdict
from desktop.native.layouts.base import Scene
from desktop.native.layouts.registry import options_for, tokens_for
from desktop.native.layouts.views import VIEW_CLASSES
from desktop.native.look import effective_look, resolved_palette
from desktop.native.tokens import TEXT_SCALE
from desktop.native.weekmodel import build_week

# Drawn at a laptop's window size and scaled down, so each design lays out as it does in use.
CANVAS = QSize(1040, 650)
# Wednesday at ten past four: school is over, and there is homework to do and more due.
SAMPLE_DAY, SAMPLE_MINUTE = 2, 16 * 60 + 10


def _block(
    block_id: str,
    title: str,
    kind: str,
    category: str,
    days: list[int],
    start: str | None,
    minutes: int,
    **extra: object,
) -> dict:
    return {
        "id": block_id,
        "title": title,
        "kind": kind,
        "category": category,
        "days": days,
        "start": start,
        "duration_min": minutes,
        **extra,
    }


def sample_week(today: date | None = None) -> tuple[str, list[dict], dict[str, dict]]:
    """This week, so the dates in the picture are the student's own."""
    monday = monday_of((today or date.today()).isoformat())
    start = date.fromisoformat(monday)

    def due(days: int, hhmm: str) -> str:
        return f"{(start + timedelta(days=days)).isoformat()}T{hhmm}"

    homework = {
        "essay": {"id": "essay", "title": "History essay", "due": due(4, "21:00"), "completed": False},
        "chem": {"id": "chem", "title": "Chem lab report", "due": due(3, "23:59"), "completed": False},
        "poster": {"id": "poster", "title": "Science poster", "due": due(6, "20:00"), "completed": False},
    }
    blocks = [
        _block("school", "School", "locked", "class", [0, 1, 2, 3, 4], "08:00", 390),
        _block("soccer", "Soccer", "locked", "extra", [1, 3], "15:30", 90),
        _block("dinner", "Dinner", "locked", "meals", [0, 1, 2, 3, 4, 5, 6], "18:00", 30),
        _block(
            "essay-1", "History essay", "flexible", "assignments", [2], "19:00", 60, assignment_id="essay"
        ),
        _block(
            "chem-1", "Chem lab report", "flexible", "assignments", [3], "20:00", 90, assignment_id="chem"
        ),
        _block(
            "poster-1", "Science poster", "flexible", "assignments", [], None, 120, assignment_id="poster"
        ),
    ]
    return monday, blocks, homework


def system_dark() -> bool:
    return QGuiApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128


def _settle(widget: QWidget) -> None:
    # Laid out and painted without ever reaching the screen.
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.resize(CANVAS)
    widget.show()
    layout = widget.layout()
    if layout is not None:
        layout.activate()


def render(main: str, colour: str | None, pack: str, look: dict | None, width: int) -> QPixmap:
    """A picture of `main` in `colour` (or, for Today's app, in `pack`), `width` pixels wide."""
    dark = system_dark()
    palette = resolved_palette(pack, dark, look)
    monday, blocks, homework = sample_week()
    host: QWidget | None = None
    if main in VIEW_CLASSES:
        view = VIEW_CLASSES[main]()
        options = {**options_for(None, main), **({"colour": colour} if colour else {})}
        view.show_week(
            Scene(
                week=build_week(monday, blocks, homework, None),
                today=SAMPLE_DAY,
                minute=SAMPLE_MINUTE,
                options=options,
                tokens=tokens_for(main, options["colour"], palette),
                scale=TEXT_SCALE[effective_look(look)["text"]],
                iso_day=(date.fromisoformat(monday) + timedelta(days=SAMPLE_DAY)).isoformat(),
            )
        )
        widget: QWidget = view
    else:
        # Today's app's week, as it does in use. A picture takes no gestures, so its hand never
        # judges anything.
        host = QWidget()
        widget = ClassicWeek(Hand(lambda block_id, from_day, span: Verdict(False, ""), host))
        widget.set_look(look, palette)
        widget.set_week(build_week(monday, blocks, homework, None), SAMPLE_DAY, SAMPLE_MINUTE)
    _settle(widget)
    picture = widget.grab()
    widget.close()
    widget.deleteLater()
    return picture.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)


class Previews:
    """Each picture drawn once, the first time it is asked for, and kept for the rest of the run, so
    running setup again, or a second account on this computer, shows them at once."""

    _kept: dict[tuple, QPixmap] = {}

    @staticmethod
    def _key(main: str, colour: str | None, pack: str, look: dict | None, width: int) -> tuple:
        # The week they show is this one, and a pack that follows the system follows it light or dark.
        this_week = monday_of(date.today().isoformat())
        return (
            main,
            colour if main in VIEW_CLASSES else pack,
            effective_look(look)["text"],
            width,
            this_week,
            system_dark(),
        )

    def get(self, main: str, colour: str | None, pack: str, look: dict | None, width: int) -> QPixmap:
        key = self._key(main, colour, pack, look, width)
        if key not in self._kept:
            self._kept[key] = render(main, colour, pack, look, width)
        return self._kept[key]
