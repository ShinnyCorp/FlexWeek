"""Deleting homework: with its times in every week, in one step that Undo brings back, from its
editor, from Unfinished and from its right-click menu. Weeks are read back from the server."""

from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta

import pytest

from desktop.tests import logic_support

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

qapp = logic_support.qapp
server = logic_support.server

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton

    from desktop.native import widgets
    from desktop.native.calendar import sunday_due
    from desktop.native.controller import NativeSession
    from desktop.native.reuse import copied_homework_block
    from desktop.native.widgets import HomeworkDialog, UnfinishedPanel
    from desktop.server import LocalServer
    from desktop.tests.logic_support import settled, signed_in


def week_after(week_start: str) -> str:
    return (date.fromisoformat(week_start) + timedelta(days=7)).isoformat()


def read(qapp: QApplication, session: NativeSession, path: str) -> dict:
    got: dict = {}
    session.client.request("GET", path, None, lambda data: got.update(data=data), lambda e: got.update(e=e))
    settled(qapp, session)
    assert "data" in got, got.get("e")
    return got["data"]


def essay_times(qapp: QApplication, session: NativeSession, week_start: str) -> list[str]:
    blocks = read(qapp, session, f"/api/week?week_start={week_start}")["blocks"]
    return sorted(block.get("start") or "" for block in blocks if block.get("assignment_id") == "essay")


def essay_saved(qapp: QApplication, session: NativeSession) -> bool:
    listed = read(qapp, session, f"/api/assignments?week_start={session.week_start}")["assignments"]
    return any(item["id"] == "essay" for item in listed)


def essay_in_two_weeks(qapp: QApplication, server: LocalServer) -> tuple[NativeSession, str, str]:
    """History essay at Monday 16:00 this week and Tuesday 17:00 next week, back on this week."""
    session = signed_in(qapp, server.origin, "alice", create=True)
    first, second = session.week_start, week_after(session.week_start)
    session.add_homework(
        {"id": "essay", "title": "History essay", "due": sunday_due(second), "estimate_min": 60,
         "revision": 0}
    )
    session.save()
    settled(qapp, session)
    waiting = next(block for block in session.blocks if block.get("assignment_id") == "essay")
    assert session.place_session(waiting["id"], 0, 16 * 60) is True
    session.save()
    settled(qapp, session)
    session.load_week(second)
    settled(qapp, session)
    later = copied_homework_block(session.assignments["essay"], 1, 60, "essay-next-week")
    later["start"] = "17:00"
    session.blocks = [*session.blocks, later]
    session._touch("adding a time next week")
    session.save()
    settled(qapp, session)
    session.load_week(first)
    settled(qapp, session)
    assert essay_times(qapp, session, first) == ["16:00"]
    assert essay_times(qapp, session, second) == ["17:00"]
    return session, first, second


def test_deleting_homework_takes_its_times_off_every_week_and_undo_brings_them_back(
    qapp: QApplication, server: LocalServer
) -> None:
    session, first, second = essay_in_two_weeks(qapp, server)
    assert session.delete_homework("essay") is True
    settled(qapp, session)
    assert session.message == "Deleted History essay."
    assert "essay" not in session.assignments
    assert not any(block.get("assignment_id") == "essay" for block in session.blocks)
    assert not essay_saved(qapp, session)
    assert essay_times(qapp, session, first) == []
    assert essay_times(qapp, session, second) == [], "next week's time goes too, unloaded as it was"

    session.undo()
    settled(qapp, session)
    assert session.message == "Undid deleting History essay."
    assert session.assignments["essay"]["title"] == "History essay"
    assert essay_saved(qapp, session)
    assert essay_times(qapp, session, first) == ["16:00"]
    assert essay_times(qapp, session, second) == ["17:00"]

    session.redo()
    settled(qapp, session)
    assert not essay_saved(qapp, session)
    assert essay_times(qapp, session, first) == []
    assert essay_times(qapp, session, second) == []


def test_homework_with_no_time_yet_is_deleted_and_nothing_else_moves(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_block(logic_support.fixed("soccer", "Soccer", 1, "16:00"))
    session.add_homework(
        {"id": "essay", "title": "History essay", "due": sunday_due(session.week_start),
         "estimate_min": 60, "revision": 0}
    )
    session.save()
    settled(qapp, session)
    assert session.delete_homework("essay") is True
    settled(qapp, session)
    week = read(qapp, session, f"/api/week?week_start={session.week_start}")
    assert [block["title"] for block in week["blocks"]] == ["Soccer"]
    assert not essay_saved(qapp, session)
    session.undo()
    settled(qapp, session)
    assert essay_saved(qapp, session)
    assert sorted(block["title"] for block in session.blocks) == ["History essay", "Soccer"]


def test_a_change_still_saving_is_finished_before_anything_is_deleted(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(
        {"id": "essay", "title": "History essay", "due": sunday_due(session.week_start),
         "estimate_min": 60, "revision": 0}
    )
    assert session.dirty
    assert session.delete_homework("essay") is False
    assert "still saving" in session.message


def test_the_editor_offers_delete_only_for_homework_that_exists(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    new = HomeworkDialog(None, today="2026-09-21")
    assert not new.delete_button.isVisibleTo(new)
    saved = {"id": "essay", "title": "History essay", "due": "2026-09-27", "estimate_min": 60, "revision": 3}
    editing = HomeworkDialog(None, saved)
    assert editing.delete_button.isVisibleTo(editing)
    assert editing.delete_button.property("quiet") is None, "drawn as quiet red words by its own name"
    asked: list[str] = []

    def answer(_parent: object, title: str, words: str, _yes: str) -> bool:
        asked.append(words)
        return True

    monkeypatch.setattr(widgets, "confirm", answer)
    editing.delete_button.click()
    assert editing.requested() == "delete"
    assert asked and "History essay" in asked[0] and "undo" in asked[0]


def test_each_unfinished_row_has_its_own_delete(qapp: QApplication) -> None:
    panel = UnfinishedPanel()
    panel.set_items(
        [{"id": "essay", "title": "History essay", "remaining_min": 60, "due": "2000-01-15T12:00"}]
    )
    asked: list[str] = []
    panel.delete_requested.connect(asked.append)
    delete = panel.findChild(QPushButton, "deleteUnfinished-essay")
    assert delete is not None and delete.property("outlined") is True and not delete.property("quiet")
    delete.click()
    assert asked == ["essay"]


def test_the_unfinished_list_holds_only_overdue_homework(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#14: Unfinished listed work due today and tomorrow. It keeps only what is already late."""
    now = datetime(2026, 10, 3, 18, 0)

    class Clock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return now

    monkeypatch.setattr(widgets, "datetime", Clock)
    panel = UnfinishedPanel()
    panel.set_items(
        [
            {"id": "late", "title": "History essay", "remaining_min": 60, "due": "2026-10-02T21:00"},
            {"id": "today", "title": "Math worksheet", "remaining_min": 45, "due": "2026-10-03T23:59"},
            {"id": "tomorrow", "title": "Chem lab", "remaining_min": 90, "due": "2026-10-04T15:30"},
            {"id": "earlier_today", "title": "Quiz", "remaining_min": 30, "due": "2026-10-03T09:00"},
        ]
    )
    rows = [label.text() for label in panel.findChildren(QLabel) if label.objectName() == "unfinishedRow"]
    assert rows == ["History essay · 1 h left", "Quiz · 30 min left"]
