"""#86: at a narrow window an empty Saturday and Sunday take less than a weekday's width in Retro, Bento
and Timeline, as they already do in Today's app, so the days with something in them have the room."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication

    from desktop.native.hours.canvas import HoursCanvas
    from desktop.tests import test_layout_bento as bento
    from desktop.tests import test_layout_retro as retro
    from desktop.tests import test_layout_timeline as timeline
    from desktop.tests.test_weekmodel import block

WEEKDAYS = [
    block("school", "locked", [0, 1, 2, 3, 4], "08:00", 390, title="School"),
    block("history", "locked", [0, 2, 4], "16:00", 60, title="History essay", category="extra"),
]
SATURDAY = block("match", "locked", [5], "10:00", 90, title="Match", category="exercise")


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-empty-weekend-test"])


def week_canvas(qapp: QApplication, design: str, blocks: list[dict]) -> HoursCanvas:
    if design == "retro":
        view = retro.shown(qapp, 810, 700, blocks=blocks)
    elif design == "bento":
        view = bento.shown(qapp, "week", size=(810, 700), blocks=blocks)
    else:
        view = timeline.shown(qapp, "week", (810, 700), blocks=blocks)
    found = [surface for surface in view.hours_surfaces() if len(surface.tracks) == 7]
    assert len(found) == 1, (design, [len(surface.tracks) for surface in view.hours_surfaces()])
    return found[0]


def widths(canvas: HoursCanvas) -> dict[int, float]:
    return {track.day: track.area.width() for track in canvas.tracks}


@pytest.mark.parametrize("design", ["retro", "bento", "timeline"])
def test_an_empty_weekend_is_narrower_than_a_weekday_and_not_below_its_least(
    qapp: QApplication, design: str
) -> None:
    wide = widths(week_canvas(qapp, design, WEEKDAYS))
    # Timeline's two pages give each page's days their own width; compare within the right page.
    weekday = wide[4] if design == "timeline" else wide[0]
    assert wide[5] == wide[6] and wide[5] < 0.8 * weekday, (design, wide)
    assert wide[5] >= 36, (design, wide)
    assert wide[0] == pytest.approx(wide[1]) and wide[2] == pytest.approx(wide[1]), (design, wide)


@pytest.mark.parametrize("design", ["retro", "bento", "timeline"])
def test_a_weekend_day_with_something_on_it_keeps_a_full_column(qapp: QApplication, design: str) -> None:
    wide = widths(week_canvas(qapp, design, [*WEEKDAYS, SATURDAY]))
    assert wide[5] == pytest.approx(wide[0] if design != "timeline" else wide[4]), (design, wide)
    assert wide[6] < wide[5], "Sunday is still empty, so it is narrower"
