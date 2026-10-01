"""The focus panel over the week (0.17.2 lane 3, Grok Bot's 0.17.0 audit X3 and X8).

A running timer is one line: its name, time and Focus screen. Now and Next, Quick focus and the
what-to-do sentence used to stack into three strips above the week.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from desktop.native import settings


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-focus-panel-test"])


NOW_NEXT = "Now: Maths until 15:00"


class _Session:
    def __init__(self, phase: str | None) -> None:
        self.focus = None if phase is None else {"title": "Essay", "phase": phase, "running": True}
        self.assignments: dict = {}

    def now_next_text(self) -> str:
        return NOW_NEXT

    def now_ms(self) -> int:
        return 0


def _shown(panel: settings.FocusPanel, widget) -> bool:
    return widget.isVisibleTo(panel)


def test_a_running_timer_is_only_its_status_line(qapp: QApplication) -> None:
    panel = settings.FocusPanel()
    panel.set_state(_Session("work"))
    panel.set_compact(False)
    assert _shown(panel, panel.task) and panel.task.text() == "Essay"
    assert _shown(panel, panel.time)
    assert _shown(panel, panel.screen)
    assert not _shown(panel, panel.now_next)
    assert not _shown(panel, panel.quick)
    assert not _shown(panel, panel.note)
    assert panel.time.toolTip().startswith("Work on this until the timer ends")
    panel.deleteLater()


def test_with_no_timer_now_and_next_shows(qapp: QApplication) -> None:
    panel = settings.FocusPanel()
    panel.set_state(_Session(None))
    assert _shown(panel, panel.now_next) and panel.now_next.text() == NOW_NEXT
    assert not panel.quick.isHidden(), "Quick focus is offered when nothing runs"
    assert not _shown(panel, panel.card)
    assert panel.time.toolTip() == ""
    panel.deleteLater()


def test_the_tooltip_goes_when_the_timer_stops(qapp: QApplication) -> None:
    panel = settings.FocusPanel()
    panel.set_state(_Session("work"))
    panel.set_state(_Session(None))
    assert panel.time.toolTip() == ""
    assert _shown(panel, panel.now_next) and not panel.quick.isHidden()
    panel.deleteLater()


def test_an_ended_session_shows_its_note_and_next_steps(qapp: QApplication) -> None:
    panel = settings.FocusPanel()
    panel.set_state(_Session("ended"))
    assert _shown(panel, panel.note) and panel.note.text() == settings.FOCUS_ENDED_NOTE
    assert _shown(panel, panel.finished)
    assert _shown(panel, panel.take_break)
    assert not _shown(panel, panel.screen), "the large timer is for a running one"
    assert panel.time.toolTip() == ""
    panel.deleteLater()


def test_a_running_timer_in_the_rail_is_also_one_line(qapp: QApplication) -> None:
    panel = settings.FocusPanel()
    panel.set_compact(True)
    panel.set_state(_Session("work"))
    assert not _shown(panel, panel.note)
    assert not _shown(panel, panel.quick)
    assert not _shown(panel, panel.now_next)
    panel.deleteLater()


def test_focus_screen_is_outlined_not_filled(qapp: QApplication) -> None:
    panel = settings.FocusPanel()
    assert panel.screen.property("outline") is True
    assert not panel.screen.property("quiet")
    panel.deleteLater()
