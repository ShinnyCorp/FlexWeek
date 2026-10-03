"""Week loading and navigation against a real local API. Expected values follow app.js selectWeek."""

from __future__ import annotations

import importlib.util

from desktop.native.calendar import date_for_day
from desktop.tests import logic_support

pytestmark = logic_support.NEEDS_DESKTOP
qapp = logic_support.qapp
server = logic_support.server

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication

    from desktop.native.controller import NativeSession
    from desktop.server import LocalServer
    from desktop.tests.logic_support import fail_once, fixed, settled, signed_in, titles, week_after

STORAGE_DOWN = "Storage is unavailable. Keep your changes and try again shortly."


def two_saved_weeks(qapp: QApplication, session: NativeSession) -> tuple[str, str]:
    """Soccer in the first week and Piano in the next, both at revision 1, with the first on screen."""
    first = session.week_start
    second = week_after(first)
    session.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    session.save()
    settled(qapp, session)
    session.load_week(second)
    settled(qapp, session)
    session.add_block(fixed("piano", "Piano", 1, "17:00"))
    session.save()
    settled(qapp, session)
    session.load_week(first)
    settled(qapp, session)
    assert (session.week_start, titles(session.blocks), session.revision) == (first, ["Soccer"], 1)
    return first, second


def test_a_failed_week_load_keeps_the_week_on_screen(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    first, second = two_saved_weeks(qapp, session)
    fail_once(session, "GET", "/api/week")
    session.load_week(second)
    settled(qapp, session)
    assert session.message == STORAGE_DOWN
    assert session.week_start == first
    assert titles(session.blocks) == ["Soccer"]


def test_a_save_after_a_failed_week_load_does_not_overwrite_the_other_week(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    first, second = two_saved_weeks(qapp, session)
    fail_once(session, "GET", "/api/week")
    session.load_week(second)
    settled(qapp, session)
    session.add_block(fixed("chess", "Chess", 2, "15:00"))
    session.save()
    settled(qapp, session)
    assert session.message == "Saved."
    session.load_week(second)
    settled(qapp, session)
    assert (session.week_start, titles(session.blocks), session.revision) == (second, ["Piano"], 1)
    session.load_week(first)
    settled(qapp, session)
    assert (session.week_start, titles(session.blocks), session.revision) == (first, ["Soccer", "Chess"], 2)


def test_stepping_outside_the_supported_dates_stays_on_the_edge_week(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.load_week("1999-12-27")
    settled(qapp, session)
    assert session.week_start == "1999-12-27"
    session.add_block(fixed("soccer", "Soccer", 5, "16:00"))
    session.save()
    settled(qapp, session)
    session.load_week("1999-12-20")
    settled(qapp, session)
    assert session.week_start == "1999-12-27"
    assert titles(session.blocks) == ["Soccer"]
    session.load_week("2099-12-28")
    settled(qapp, session)
    assert session.week_start == "2099-12-28"
    session.load_week("2100-01-04")
    settled(qapp, session)
    assert session.week_start == "2099-12-28"


def test_a_failed_open_day_leaves_day_view_inside_the_week_on_screen(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    first = session.week_start
    fail_once(session, "GET", "/api/week")
    session.open_day(week_after(first))
    settled(qapp, session)
    assert session.week_start == first


def test_a_failed_assignments_load_does_not_switch_the_week(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    first, second = two_saved_weeks(qapp, session)
    fail_once(session, "GET", "/api/assignments")
    session.load_week(second)
    settled(qapp, session)
    assert session.week_start == first
    assert titles(session.blocks) == ["Soccer"]
    session.add_block(fixed("chess", "Chess", 2, "15:00"))
    session.save()
    settled(qapp, session)
    session.undo()
    settled(qapp, session)
    assert titles(session.blocks) == ["Soccer"]


def test_an_unsaved_week_is_kept_when_opening_another(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    first = session.week_start
    second = week_after(first)
    session.add_block(fixed("soccer", "Soccer", 0, "16:00"))
    session.save()
    settled(qapp, session)
    session.add_block(fixed("chess", "Chess", 2, "15:00"))
    wednesday = date_for_day(first, 2)
    session.selected_day = wednesday
    session.load_week(second)
    settled(qapp, session)
    assert session.week_start == second
    assert titles(session.blocks) == []
    assert session.selected_day == date_for_day(second, 2)
    session.load_week(first)
    settled(qapp, session)
    assert session.week_start == first
    assert titles(session.blocks) == ["Soccer", "Chess"]
    assert session.selected_day == wednesday
    session.reload()
    settled(qapp, session)
    assert titles(session.blocks) == ["Soccer"]
