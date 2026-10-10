"""Audit finding 9: a timer length changed in Settings applies to the next phase, not the one running."""

from __future__ import annotations

import importlib.util

from desktop.tests import logic_support

pytestmark = logic_support.NEEDS_DESKTOP
qapp = logic_support.qapp
server = logic_support.server

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication

    from desktop.server import LocalServer
    from desktop.tests.logic_support import (
        FOCUS_START_MS,
        essay,
        place_on_monday,
        settled,
        signed_in,
        start_focus_on_first_block,
    )


def finish_after(qapp: QApplication, session, minutes: int) -> None:
    session.now_ms = lambda: FOCUS_START_MS + minutes * 60_000
    session.tick_focus()
    settled(qapp, session)


def test_a_longer_work_timer_chosen_mid_session_does_not_inflate_the_credit(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(essay(session))
    place_on_monday(qapp, session)
    start_focus_on_first_block(session)
    session.preferences = {**session.preferences, "timer_work_min": 60}
    finish_after(qapp, session, 30)
    assert session.assignments["essay"]["focus_minutes"] == 30


def test_a_shorter_work_timer_chosen_mid_session_does_not_shrink_the_credit(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(essay(session))
    place_on_monday(qapp, session)
    start_focus_on_first_block(session)
    session.preferences = {**session.preferences, "timer_work_min": 15}
    finish_after(qapp, session, 30)
    assert session.assignments["essay"]["focus_minutes"] == 30


def test_the_minutes_shown_while_focusing_follow_the_running_session(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(essay(session))
    place_on_monday(qapp, session)
    start_focus_on_first_block(session)
    session.preferences = {**session.preferences, "timer_work_min": 60}
    session.now_ms = lambda: FOCUS_START_MS + 10 * 60_000
    assert session.focus_elapsed_min() == 10


def test_a_session_paused_and_resumed_keeps_its_length(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(essay(session))
    place_on_monday(qapp, session)
    start_focus_on_first_block(session)
    session.now_ms = lambda: FOCUS_START_MS + 10 * 60_000
    session.toggle_focus_pause()
    session.preferences = {**session.preferences, "timer_work_min": 60}
    session.toggle_focus_pause()
    session.now_ms = lambda: FOCUS_START_MS + 30 * 60_000
    session.tick_focus()
    settled(qapp, session)
    assert session.assignments["essay"]["focus_minutes"] == 30


def test_the_next_work_phase_uses_the_new_length(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(essay(session))
    place_on_monday(qapp, session)
    start_focus_on_first_block(session)
    session.preferences = {**session.preferences, "timer_work_min": 45}
    session.focus["phase"] = "break"
    session.advance_focus(completed=False)
    assert session.focus["phase"] == "work"
    session.now_ms = lambda: session.focus["endsAt"]
    session.tick_focus()
    settled(qapp, session)
    assert session.assignments["essay"]["focus_minutes"] == 45
