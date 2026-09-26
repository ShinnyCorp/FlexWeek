"""Focus credit, completed homework and solver-trace reminders against a real local API."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta

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
    from desktop.native.controller import NativeSession
    from desktop.server import LocalServer
    from desktop.tests.logic_support import fail_once, settled, signed_in


def essay(session: NativeSession) -> dict:
    return {
        "id": "essay",
        "title": "Essay",
        "due": sunday_due(session.week_start),
        "estimate_min": 60,
        "revision": 0,
    }


def test_a_focus_credit_is_not_lost_behind_a_failed_save(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(essay(session))
    session.blocks[0]["start"] = "16:00"
    session.blocks[0]["days"] = [0]
    session.save()
    settled(qapp, session)
    session.add_homework({**session.assignments["essay"], "notes": "Cite two sources"})
    fail_once(session, "POST", "/api/changes")
    session.save()
    settled(qapp, session)
    session.now_ms = lambda: 1_000_000
    assert session.start_focus(session.blocks[0]["id"], 0) is True
    session.now_ms = lambda: 1_000_000 + 30 * 60_000
    session.tick_focus()
    settled(qapp, session)
    assert session.conflict is False
    session.reload()
    settled(qapp, session)
    item = session.assignments["essay"]
    assert item["focus_minutes"] == 30
    assert item["notes"] == "Cite two sources"


def test_finished_after_a_focus_session_finishes_the_homework_where_it_was(
    qapp: QApplication, server: LocalServer
) -> None:
    """Finished used to write a finished day onto a session not yet marked finished, which the
    homework's own check turned away, so nothing was finished and nothing was said."""
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(essay(session))
    session.blocks[0]["start"] = "16:00"
    session.blocks[0]["days"] = [0]
    session.save()
    settled(qapp, session)
    session.now_ms = lambda: 1_000_000
    assert session.start_focus(session.blocks[0]["id"], 0) is True
    session.now_ms = lambda: 1_000_000 + 30 * 60_000
    session.tick_focus()
    settled(qapp, session)
    assert session.focus["phase"] == "ended"
    assert session.finish_focused_homework() is True
    settled(qapp, session)
    session.reload()
    settled(qapp, session)
    assert session.assignments["essay"]["completed"] is True
    block = session.blocks[0]
    assert (block["completed"], block["completed_day"], block["start"]) == (True, 0, "16:00")


def test_completed_homework_can_be_reopened_after_a_reload(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(essay(session))
    session.save()
    settled(qapp, session)
    session.complete_homework("essay")
    session.save()
    settled(qapp, session)
    session.reload()
    settled(qapp, session)
    assert session.assignments["essay"]["completed"] is True
    payload = session.week_file()
    assert payload["assignments"][0]["id"] == "essay"
    assert payload["blocks"][0]["assignment_id"] == "essay"
    session.complete_homework("essay", False)
    session.save()
    settled(qapp, session)
    assert session.assignments["essay"]["completed"] is False


def test_editing_the_week_stops_reminders_for_a_deleted_session(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    # Planned from Monday morning, so there is time left in the week whatever day the test runs.
    monday = datetime.fromisoformat(session.week_start) + timedelta(hours=9)
    session.now_ms = lambda: int(monday.timestamp() * 1000)
    session.add_homework(essay(session))
    session.save()
    settled(qapp, session)
    session.solve()
    settled(qapp, session)
    assert session.trace is not None
    placed = next(item for item in session.trace["placed"] if item["id"] == session.blocks[0]["id"])
    session.delete_block(placed["id"])
    assert session.trace is None
    notices: list = []
    session.alerts.connect(lambda items: notices.extend(items))
    session.now_ms = lambda: 12 * 3600 * 1000
    session.check_alerts()
    assert notices == []
