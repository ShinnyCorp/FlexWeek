"""The first and the last hour row on screen are always named, whatever the look and wherever the
week is scrolled to: 23:00 was missing at the foot, and a larger look hid the top label."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication

    from desktop.native.hours import canvas as canvas_module
    from desktop.native.hours.classic import ClassicWeek
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import build_week
    from desktop.tests.test_classic_hours import a_hand
    from desktop.tests.test_hours_painter import Said


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-hour-labels-test"])


LOOKS = [
    ("system", None),
    ("light-frost", None),
    ("light-frost", {"text": "large"}),
    ("dark-frost", {"text": "large"}),
    ("slate", {"text": "small"}),
    ("system", {"preset": "high-contrast"}),
]


def shown(qapp: QApplication, pack: str, look: dict | None) -> ClassicWeek:
    """A week with no time now on it, so no label gives way to the pill that says the time."""
    view = ClassicWeek(a_hand())
    view.set_look(look, resolved_palette(pack, False, look))
    view.set_week(build_week("2026-09-21", [], {}, None), None, None)
    view.resize(980, 500)
    view.show()
    qapp.processEvents()
    view.hours.relayout()
    qapp.processEvents()
    return view


def hour_words(view: ClassicWeek) -> list[str]:
    Said.words = []
    view.hours.repaint()
    return [text for text, _where in Said.words if text.endswith(":00") and len(text) == 5]


@pytest.mark.parametrize(("pack", "look"), LOOKS)
def test_the_first_and_last_hour_on_screen_are_named_at_every_scroll_position(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, pack: str, look: dict | None
) -> None:
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    view = shown(qapp, pack, look)
    bar = view.scroll.verticalScrollBar()
    track = view.hours.track_for(3)
    assert track is not None and bar.maximum() > 0
    for value in sorted({*range(0, bar.maximum(), 7), bar.maximum()}):
        bar.setValue(value)
        qapp.processEvents()
        visible = view.hours._visible()
        rows = [
            hour
            for hour in range(24)
            if visible.top() <= track.area.top() + track.offset(hour * 60) <= visible.bottom()
        ]
        said = hour_words(view)
        for hour in (rows[0], rows[-1]):
            assert f"{hour:02d}:00" in said, f"scrolled to {value}: {hour:02d}:00 is on screen, unnamed"
