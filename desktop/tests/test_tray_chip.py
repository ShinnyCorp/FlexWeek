"""The tray chip every design's Not placed yet is made of."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from collections.abc import Iterator

from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionButton, QWidget

from desktop.native.hours.chips import TrayChip
from desktop.native.hours.hand import Hand
from desktop.native.weekmodel import Waiting


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-tray-chip-test"])


def test_a_chip_shortens_its_words_again_when_a_new_look_makes_them_larger(qapp: QApplication) -> None:
    """A new look can make the words larger without changing the chip's width, and at High contrast's
    large text they ran off its edge. The title gives way first; the length stays whole."""
    host = QWidget()
    host.setStyleSheet("QPushButton { font-size: 11pt; padding: 4px 8px; }")
    waiting = Waiting("poster", "Science poster for the fair", "assignments", 90, "poster", None, "")
    chip = TrayChip(Hand(lambda *_args: None, host), waiting, host)
    host.show()
    qapp.processEvents()
    chip.setFixedWidth(chip.sizeHint().width())
    qapp.processEvents()
    assert chip.text() == "Science poster for the fair · 1 h 30 min"
    host.setStyleSheet("QPushButton { font-size: 16pt; padding: 4px 8px; }")
    qapp.processEvents()
    option = QStyleOptionButton()
    chip.initStyleOption(option)
    room = chip.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, chip).width()
    assert chip.fontMetrics().horizontalAdvance(chip.text()) <= room, chip.text()
    assert chip.text().endswith("… · 1 h 30 min"), chip.text()
