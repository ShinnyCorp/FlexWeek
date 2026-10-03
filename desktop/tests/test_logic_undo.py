"""Undo and Redo against a real local API. Expected values follow frontend/history.js."""

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
        essay,
        fail_once,
        fixed,
        place_on_monday,
        settled,
        signed_in,
        start_focus_on_first_block,
        tick_focus_after_half_an_hour,
    )


def test_undo_of_new_homework_does_not_conflict(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(essay(session))
    session.save()
    settled(qapp, session)
    assert "essay" in session.assignments
    session.undo()
    settled(qapp, session)
    assert session.conflict is False
    assert "essay" not in session.assignments
    session.redo()
    settled(qapp, session)
    assert session.conflict is False
    assert session.assignments["essay"]["title"] == "Essay"


def test_undo_keeps_focus_minutes_counted_since_the_saved_step(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(essay(session))
    place_on_monday(qapp, session)
    start_focus_on_first_block(session)
    tick_focus_after_half_an_hour(qapp, session)
    assert session.assignments["essay"]["focus_minutes"] == 30
    session.add_homework({**session.assignments["essay"], "notes": "Cite two sources"})
    session.save()
    settled(qapp, session)
    session.undo()
    settled(qapp, session)
    assert session.conflict is False
    assert session.assignments["essay"]["focus_minutes"] == 30
    assert session.assignments["essay"].get("notes") in (None, "")


def test_undo_is_blocked_while_an_unsaved_edit_is_waiting(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    session.save()
    settled(qapp, session)
    session.add_block(fixed("piano", "Piano", 1, "17:00"))
    fail_once(session, "POST", "/api/changes")
    session.save()
    settled(qapp, session)
    assert session.can_undo() is False
    assert [block["title"] for block in session.blocks] == ["Soccer", "Piano"]


def test_a_failed_undo_puts_the_saved_week_back(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    session.save()
    settled(qapp, session)
    session.add_block(fixed("piano", "Piano", 1, "17:00"))
    session.save()
    settled(qapp, session)
    fail_once(session, "POST", "/api/changes")
    session.undo()
    settled(qapp, session)
    assert [block["title"] for block in session.blocks] == ["Soccer", "Piano"]
    assert session.can_undo() is True
    session.undo()
    settled(qapp, session)
    assert [block["title"] for block in session.blocks] == ["Soccer"]
