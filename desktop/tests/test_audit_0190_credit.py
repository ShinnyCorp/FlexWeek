"""Audit finding 5: focus minutes credited while a save is under way are kept, not overwritten by it."""

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
        wait_until,
    )


def test_focus_time_finished_during_a_save_is_kept(qapp: QApplication, server: LocalServer) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(essay(session))
    place_on_monday(qapp, session)
    start_focus_on_first_block(session)
    session.add_homework({**session.assignments["essay"], "notes": "Cite two sources"})
    real = session.client.request
    held: list[tuple] = []
    session.client.request = lambda *call: held.append(call)  # type: ignore[method-assign]
    session.save()
    assert session.busy and len(held) == 1
    session.now_ms = lambda: FOCUS_START_MS + 30 * 60_000
    session.tick_focus()
    session.client.request = real  # type: ignore[method-assign]
    real(*held[0])
    settled(qapp, session)
    wait_until(qapp, lambda: not session.dirty_assignments and not session.busy)
    session.reload()
    settled(qapp, session)
    item = session.assignments["essay"]
    assert item["focus_minutes"] == 30
    assert item["notes"] == "Cite two sources"
