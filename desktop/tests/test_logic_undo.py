"""Undo and Redo against a real local API. Expected values follow frontend/history.js."""

from __future__ import annotations

import importlib.util

import pytest

from desktop.tests import logic_support

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)
qapp = logic_support.qapp
server = logic_support.server

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication

    from desktop.native.calendar import sunday_due
    from desktop.server import LocalServer
    from desktop.tests.logic_support import fail_once, fixed, settled, signed_in


def test_undo_of_new_homework_does_not_conflict(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(
        {
            "id": "essay",
            "title": "Essay",
            "due": sunday_due(session.week_start),
            "estimate_min": 60,
            "revision": 0,
        }
    )
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
    session.add_homework(
        {
            "id": "essay",
            "title": "Essay",
            "due": sunday_due(session.week_start),
            "estimate_min": 60,
            "revision": 0,
        }
    )
    session.blocks[0]["start"] = "16:00"
    session.blocks[0]["days"] = [0]
    session.save()
    settled(qapp, session)
    session.now_ms = lambda: 1_000_000
    assert session.start_focus(session.blocks[0]["id"], 0) is True
    session.now_ms = lambda: 1_000_000 + 30 * 60_000
    session.tick_focus()
    settled(qapp, session)
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


def test_undo_takes_back_a_fixed_block_and_homework_saved_together(
    qapp: QApplication, server: LocalServer
) -> None:
    """The server deletes homework before it writes the week, and that moves the week's revision. One
    save holding both left Undo's week write one revision behind: refused, and the week left empty."""
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_block(fixed("school", "School", 0, "08:00"))
    session.add_homework(
        {
            "id": "essay",
            "title": "Essay",
            "due": sunday_due(session.week_start),
            "estimate_min": 60,
            "revision": 0,
        }
    )
    session.save()
    settled(qapp, session)
    session.solve()
    settled(qapp, session)
    assert session.blocks[-1]["start"] is not None
    session.undo()
    settled(qapp, session)
    assert session.message == "Undid planning the week."
    session.undo()
    settled(qapp, session)
    assert session.message.startswith("Undid "), session.message
    assert session.conflict is False
    assert session.blocks == []
    assert "essay" not in session.assignments
    session.redo()
    settled(qapp, session)
    assert session.conflict is False
    assert [block["title"] for block in session.blocks] == ["School", "Essay"]
    assert session.assignments["essay"]["title"] == "Essay"


def test_a_refused_undo_reloads_the_week_and_offers_undo_again(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    session.save()
    settled(qapp, session)
    fail_once(session, "POST", "/api/changes", 409)
    session.undo()
    settled(qapp, session)
    assert session.conflict is False
    assert [block["title"] for block in session.blocks] == ["Soccer"], "the week is back as it is saved"
    assert session.can_undo() is True
    session.undo()
    settled(qapp, session)
    assert session.blocks == []
    assert session.conflict is False
