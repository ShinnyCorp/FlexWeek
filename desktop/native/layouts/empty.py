"""What Today's app shows in place of the hours while a new account has nothing in its week.

A new account's week was an empty grid of hours, which says nothing about where to start. This says
one thing and offers one button, and the hours come back as soon as the week has a block or homework.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from desktop.native.weekmodel import WeekModel

EMPTY_HEADING = "Nothing here yet."
EMPTY_LINE = "Add your first homework and FlexWeek will find it a time."
EMPTY_BUTTON = "Add your first homework"


def nothing_yet(week: WeekModel, assignments: dict) -> bool:
    """The week has no blocks and nothing waiting for a time, and the account has no homework at all.

    Every week nobody has saved is empty, so going by the week alone would take the hours away from
    each next week of a student who has homework, and tell them to add their "first".
    """
    return not assignments and week.leftover_kind(None) == "no_homework"


class EmptyWeek(QWidget):
    add_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("emptyWeek")
        layout = QVBoxLayout(self)
        layout.addStretch(2)
        heading = QLabel(EMPTY_HEADING)
        heading.setObjectName("emptyWeekHeading")
        line = QLabel(EMPTY_LINE)
        line.setObjectName("emptyWeekLine")
        line.setWordWrap(True)
        for label in (heading, line):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
        layout.addSpacing(16)
        self.add = QPushButton(EMPTY_BUTTON)
        self.add.setObjectName("emptyWeekAdd")
        self.add.clicked.connect(self.add_requested.emit)
        layout.addWidget(self.add, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(3)
