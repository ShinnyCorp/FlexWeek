"""Days are picked with pills everywhere (T19 and X7 of the 0.17.0 audit, 5.2 A of 0.17.2): the block
editor's Add fixed time used check boxes while setup used pills, so one choice looked two ways."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton, QWidget

from desktop.native.calendar import DAYS
from desktop.native.widgets import BlockDialog
from desktop.tests.window_support import free, host, qapp  # noqa: F401


def day_boxes(root: QWidget) -> list[str]:
    """Check boxes named for a day: what the pills replace."""
    return [box.text() for box in root.findChildren(QCheckBox) if box.text() in DAYS]


def pills(root: QWidget) -> list[QPushButton]:
    return [button for button in root.findChildren(QPushButton) if button.property("pill")]


def test_the_block_editor_picks_its_days_with_pills(qapp: QApplication, host: QWidget) -> None:  # noqa: F811
    block = {"id": "s", "title": "Soccer", "kind": "locked", "start": "16:00", "duration_min": 60}
    dialog = BlockDialog(host, {**block, "days": [1]})
    assert day_boxes(dialog) == []
    shown = pills(dialog)
    assert [pill.text() for pill in shown] == list(DAYS)
    assert [pill.isChecked() for pill in shown] == [day == 1 for day in range(7)]
    shown[3].click()
    dialog.accept()
    assert dialog.block()["days"] == [1, 3]
    free(dialog)
