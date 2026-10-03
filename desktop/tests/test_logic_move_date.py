"""move_to_date against a real local API. Saved weeks are read back from the server."""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from datetime import date, timedelta

import pytest

from desktop.native.calendar import date_for_day
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
    from desktop.tests.logic_support import PASSWORD, fixed, settled, signed_in


def week_after(week_start: str) -> str:
    return (date.fromisoformat(week_start) + timedelta(days=7)).isoformat()


def read_week(qapp: QApplication, session: NativeSession, week_start: str) -> dict:
    got: dict = {}

    def ok(data: dict) -> None:
        got["week"] = data

    def err(error) -> None:
        got["error"] = error

    session.client.request("GET", f"/api/week?week_start={week_start}", None, ok, err)
    settled(qapp, session)
    assert "week" in got, got.get("error")
    return got["week"]


def titles(blocks: list[dict]) -> list[str]:
    return [block["title"] for block in blocks]


def test_move_to_date_keeps_the_time_on_another_day_of_the_same_week(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    session.save()
    settled(qapp, session)
    monday = date_for_day(session.week_start, 0)
    wednesday = date_for_day(session.week_start, 2)
    assert session.move_to_date("soccer", monday, wednesday) is True
    settled(qapp, session)
    stored = read_week(qapp, session, session.week_start)
    soccer = next(block for block in stored["blocks"] if block["id"] == "soccer")
    assert soccer["days"] == [2]
    assert soccer["start"] == "16:00"
    assert soccer["duration_min"] == 60


def test_move_to_date_writes_both_weeks_going_forward(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    first = session.week_start
    second = week_after(first)
    session.add_block({**fixed("soccer", "Soccer", 3, "16:07"), "duration_min": 43})
    session.save()
    settled(qapp, session)
    thursday = date_for_day(first, 3)
    next_tuesday = date_for_day(second, 1)
    assert session.move_to_date("soccer", thursday, next_tuesday) is True
    settled(qapp, session)
    assert session.conflict is False
    source = read_week(qapp, session, first)
    dest = read_week(qapp, session, second)
    assert titles(source["blocks"]) == []
    soccer = dest["blocks"][0]
    assert soccer["id"] == "soccer"
    assert soccer["days"] == [1]
    assert (soccer["start"], soccer["duration_min"]) == ("16:07", 43), "carried with its time exactly"
    assert session.week_start == first
    assert titles(session.blocks) == []


def test_move_to_date_writes_both_weeks_going_back(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    first = session.week_start
    second = week_after(first)
    session.load_week(second)
    settled(qapp, session)
    session.add_block(fixed("soccer", "Soccer", 1, "16:00"))
    session.save()
    settled(qapp, session)
    tuesday = date_for_day(second, 1)
    previous_thursday = date_for_day(first, 3)
    assert session.move_to_date("soccer", tuesday, previous_thursday) is True
    settled(qapp, session)
    source = read_week(qapp, session, second)
    dest = read_week(qapp, session, first)
    assert titles(source["blocks"]) == []
    soccer = dest["blocks"][0]
    assert soccer["days"] == [3]
    assert soccer["start"] == "16:00"


def test_move_to_date_splits_one_day_off_a_repeating_block(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    first = session.week_start
    second = week_after(first)
    session.add_block(
        {
            "id": "soccer",
            "title": "Soccer",
            "kind": "locked",
            "duration_min": 60,
            "days": [0, 2, 4],
            "start": "16:00",
        }
    )
    session.save()
    settled(qapp, session)
    monday = date_for_day(first, 0)
    next_monday = date_for_day(second, 0)
    assert session.move_to_date("soccer", monday, next_monday) is True
    settled(qapp, session)
    source = read_week(qapp, session, first)
    dest = read_week(qapp, session, second)
    remaining = next(block for block in source["blocks"] if block["id"] == "soccer")
    assert remaining["days"] == [2, 4]
    assert remaining["start"] == "16:00"
    moved = dest["blocks"][0]
    assert moved["id"] != "soccer"
    assert moved["days"] == [0]
    assert moved["start"] == "16:00"
    assert moved["title"] == "Soccer"


def test_date_problem_and_move_to_date_refuse_homework_past_due(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    due = date_for_day(session.week_start, 3) + "T15:00"
    session.add_homework({"id": "essay", "title": "Essay", "due": due, "estimate_min": 60, "revision": 0})
    session.save()
    settled(qapp, session)
    waiting = session.blocks[0]
    assert session.place_session(waiting["id"], 2, 16 * 60) is True
    session.save()
    settled(qapp, session)
    wednesday = date_for_day(session.week_start, 2)
    friday = date_for_day(session.week_start, 4)
    assert session.date_problem(waiting["id"], wednesday, friday) == (
        "That ends after it is due, so it stayed where it was."
    )
    before = read_week(qapp, session, session.week_start)
    assert session.move_to_date(waiting["id"], wednesday, friday) is False
    settled(qapp, session)
    after = read_week(qapp, session, session.week_start)
    assert after["blocks"] == before["blocks"]
    assert session.message == "That ends after it is due, so it stayed where it was."


def test_move_to_date_keeps_homework_pinned_on_the_new_week(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    first = session.week_start
    second = week_after(first)
    session.add_homework(
        {
            "id": "essay",
            "title": "Essay",
            "due": sunday_due(second),
            "estimate_min": 60,
            "revision": 0,
        }
    )
    session.save()
    settled(qapp, session)
    waiting = session.blocks[0]
    assert session.place_session(waiting["id"], 0, 16 * 60) is True
    session.save()
    settled(qapp, session)
    monday = date_for_day(first, 0)
    next_tuesday = date_for_day(second, 1)
    assert session.move_to_date(waiting["id"], monday, next_tuesday) is True
    settled(qapp, session)
    dest = read_week(qapp, session, second)
    essay = dest["blocks"][0]
    assert essay["assignment_id"] == "essay"
    assert essay["pinned"] is True
    assert essay["start"] == "16:00"


def test_a_409_on_the_other_week_leaves_both_weeks_untouched(qapp: QApplication, server: LocalServer) -> None:
    alice = signed_in(qapp, server.origin, "alice", create=True)
    first = alice.week_start
    second = week_after(first)
    alice.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    alice.save()
    settled(qapp, alice)
    bob = NativeSession(server.origin, qapp)
    logic_support.HELD.append(bob)
    bob.login("alice", PASSWORD)
    logic_support.wait_until(qapp, lambda: bob.account is not None and not bob.busy)
    settled(qapp, bob)
    bob.load_week(second)
    settled(qapp, bob)
    real = alice.client.request

    def request(verb, target, payload, on_success, on_error):
        if verb == "GET" and f"week_start={second}" in target:
            alice.client.request = real  # type: ignore[method-assign]

            def hooked(data):
                bob.add_block(fixed("piano", "Piano", 0, "17:00"))
                bob.save()
                settled(qapp, bob)
                on_success(data)

            return real(verb, target, payload, hooked, on_error)
        return real(verb, target, payload, on_success, on_error)

    alice.client.request = request  # type: ignore[method-assign]
    monday = date_for_day(first, 0)
    next_monday = date_for_day(second, 0)
    assert alice.move_to_date("soccer", monday, next_monday) is True
    settled(qapp, alice)
    assert alice.conflict is True
    source = read_week(qapp, alice, first)
    dest = read_week(qapp, alice, second)
    assert titles(source["blocks"]) == ["Soccer"]
    assert titles(dest["blocks"]) == ["Piano"]
    assert titles(alice.blocks) == ["Soccer"]


def test_retrying_the_same_operation_id_moves_the_block_once(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    first = session.week_start
    second = week_after(first)
    session.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    session.save()
    settled(qapp, session)
    captured: dict = {}
    real = session.client.request

    def request(verb, target, payload, on_success, on_error):
        if verb == "POST" and target.startswith("/api/changes"):
            captured["payload"] = deepcopy(payload)
        return real(verb, target, payload, on_success, on_error)

    session.client.request = request  # type: ignore[method-assign]
    monday = date_for_day(first, 0)
    next_monday = date_for_day(second, 0)
    assert session.move_to_date("soccer", monday, next_monday) is True
    settled(qapp, session)
    replayed: dict = {}

    def ok(data: dict) -> None:
        replayed["ok"] = data

    def err(error) -> None:
        replayed["err"] = error

    session.client.request("POST", "/api/changes", captured["payload"], ok, err)
    settled(qapp, session)
    assert "ok" in replayed
    dest = read_week(qapp, session, second)
    source = read_week(qapp, session, first)
    assert titles(source["blocks"]) == []
    assert titles(dest["blocks"]) == ["Soccer"]
    assert [block["id"] for block in dest["blocks"]] == ["soccer"]


def test_the_open_week_does_not_change_until_the_server_accepts_the_move(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    first = session.week_start
    second = week_after(first)
    session.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    session.save()
    settled(qapp, session)
    seen: dict = {}
    real = session.client.request

    def request(verb, target, payload, on_success, on_error):
        if verb == "POST" and target.startswith("/api/changes"):
            seen["titles"] = titles(session.blocks)
            seen["days"] = next(block["days"] for block in session.blocks if block["id"] == "soccer")
        return real(verb, target, payload, on_success, on_error)

    session.client.request = request  # type: ignore[method-assign]
    monday = date_for_day(first, 0)
    next_monday = date_for_day(second, 0)
    assert session.move_to_date("soccer", monday, next_monday) is True
    settled(qapp, session)
    assert seen["titles"] == ["Soccer"]
    assert seen["days"] == [0]
    assert titles(session.blocks) == []
    dest = read_week(qapp, session, second)
    assert titles(dest["blocks"]) == ["Soccer"]


def test_undo_puts_both_weeks_back(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    first = session.week_start
    second = week_after(first)
    session.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    session.save()
    settled(qapp, session)
    monday = date_for_day(first, 0)
    next_monday = date_for_day(second, 0)
    assert session.move_to_date("soccer", monday, next_monday) is True
    settled(qapp, session)
    session.undo()
    settled(qapp, session)
    source = read_week(qapp, session, first)
    dest = read_week(qapp, session, second)
    assert titles(source["blocks"]) == ["Soccer"]
    assert titles(dest["blocks"]) == []
    assert titles(session.blocks) == ["Soccer"]
    soccer = next(block for block in source["blocks"] if block["id"] == "soccer")
    assert soccer["days"] == [0]
    assert soccer["start"] == "16:00"


def test_a_move_into_a_week_that_already_has_blocks_keeps_them(
    qapp: QApplication, server: LocalServer
) -> None:
    """The other week is rewritten whole, so what it already held must come along: a plain block
    and one day of a repeating block both arrive beside what was there."""
    session = signed_in(qapp, server.origin, "alice", create=True)
    first = session.week_start
    second = week_after(first)
    session.load_week(second)
    settled(qapp, session)
    session.add_block(fixed("piano", "Piano", 2, "18:00"))
    session.save()
    settled(qapp, session)
    session.load_week(first)
    settled(qapp, session)
    session.add_block(fixed("soccer", "Soccer", 3, "16:00"))
    session.add_block(
        {
            "id": "band",
            "title": "Band",
            "kind": "locked",
            "duration_min": 60,
            "days": [0, 2, 4],
            "start": "17:00",
        }
    )
    session.save()
    settled(qapp, session)
    assert session.move_to_date("soccer", date_for_day(first, 3), date_for_day(second, 1)) is True
    settled(qapp, session)
    assert session.move_to_date("band", date_for_day(first, 0), date_for_day(second, 0)) is True
    settled(qapp, session)
    dest = read_week(qapp, session, second)
    assert sorted(titles(dest["blocks"])) == ["Band", "Piano", "Soccer"]
    assert next(block for block in dest["blocks"] if block["title"] == "Piano")["days"] == [2]
    source = read_week(qapp, session, first)
    assert sorted(titles(source["blocks"])) == ["Band"]
    assert next(block for block in source["blocks"] if block["title"] == "Band")["days"] == [2, 4]


def test_undo_of_a_move_refuses_when_the_other_week_changed_elsewhere(
    qapp: QApplication, server: LocalServer
) -> None:
    """A later save to the other week, not on this undo stack, is kept. Undo is a 409, the week is
    reloaded as it is saved, and both weeks stay as they are."""
    alice = signed_in(qapp, server.origin, "alice", create=True)
    first = alice.week_start
    second = week_after(first)
    alice.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    alice.save()
    settled(qapp, alice)
    monday = date_for_day(first, 0)
    next_monday = date_for_day(second, 0)
    assert alice.move_to_date("soccer", monday, next_monday) is True
    settled(qapp, alice)
    bob = NativeSession(server.origin, qapp)
    logic_support.HELD.append(bob)
    bob.login("alice", PASSWORD)
    logic_support.wait_until(qapp, lambda: bob.account is not None and not bob.busy)
    settled(qapp, bob)
    bob.load_week(second)
    settled(qapp, bob)
    bob.add_block(fixed("piano", "Piano", 0, "17:00"))
    bob.save()
    settled(qapp, bob)
    alice.undo()
    settled(qapp, alice)
    assert alice.conflict is False
    assert alice.message == "Undo did not go through. Your week was reloaded as it is saved."
    source = read_week(qapp, alice, first)
    dest = read_week(qapp, alice, second)
    assert titles(source["blocks"]) == []
    assert sorted(titles(dest["blocks"])) == ["Piano", "Soccer"]


def test_date_problem_judges_a_chip_when_its_week_is_not_loaded(
    qapp: QApplication, server: LocalServer
) -> None:
    """Month has the chip's start and length from the month reply, not from the open week."""
    session = signed_in(qapp, server.origin, "alice", create=True)
    first = session.week_start
    second = week_after(first)
    due = date_for_day(first, 3) + "T15:00"
    session.add_homework({"id": "essay", "title": "Essay", "due": due, "estimate_min": 60, "revision": 0})
    session.save()
    settled(qapp, session)
    waiting = session.blocks[0]
    assert session.place_session(waiting["id"], 2, 16 * 60) is True
    session.save()
    settled(qapp, session)
    chip = next(block for block in session.blocks if block.get("assignment_id") == "essay")
    wednesday = date_for_day(first, 2)
    friday = date_for_day(first, 4)
    tuesday = date_for_day(first, 1)
    session.load_week(second)
    settled(qapp, session)
    assert session.week_start == second
    assert all(block.get("id") != chip["id"] for block in session.blocks)
    past_due = "That ends after it is due, so it stayed where it was."
    assert (
        session.date_problem(
            chip["id"],
            wednesday,
            friday,
            start=chip["start"],
            duration_min=chip["duration_min"],
            assignment_id=chip["assignment_id"],
        )
        == past_due
    )
    assert (
        session.date_problem(
            chip["id"],
            wednesday,
            tuesday,
            start=chip["start"],
            duration_min=chip["duration_min"],
            assignment_id=chip["assignment_id"],
        )
        is None
    )
