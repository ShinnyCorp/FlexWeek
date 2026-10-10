"""Fixes from the audit of 0.18.5. Expected values come from what the student would see."""

from __future__ import annotations

import importlib.util
import os

from desktop.tests import logic_support

pytestmark = logic_support.NEEDS_DESKTOP
qapp = logic_support.qapp
server = logic_support.server

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication

    from desktop.server import LocalServer
    from desktop.tests.logic_support import (
        signed_in,
        wait_until,
    )

MINUTE = 60_000


def test_a_second_restore_point_with_the_same_name_is_a_new_backup(
    qapp: QApplication, server: LocalServer
) -> None:
    """Audit finding 4: the first call's operation id was reused, so the server handed back the old
    point and the second backup never captured the newer week."""
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.create_restore_point("Before exams")
    wait_until(qapp, lambda: len(session.restore_points) == 1 and not session.busy)
    first = session.restore_points[0]["id"]
    session.create_restore_point("Before exams")
    wait_until(qapp, lambda: len(session.restore_points) == 2 and not session.busy)
    assert session.restore_points[0]["id"] != first
