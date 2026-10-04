"""What Today's app shows in place of the hours while a new account has nothing in its week.

A new account's week was an empty grid of hours, which says nothing about where to start. This says
one thing and offers one button, and the hours come back as soon as the week has a block or homework.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget

from desktop.native.weekmodel import WeekModel

EMPTY_HEADING = "Nothing here yet."
EMPTY_LINE = "Add your first homework and FlexWeek will find it a time."
EMPTY_BUTTON = "Add your first homework"
BLANK_HEADING = "This week is empty."
BLANK_LINE = "Copy school and sports from last week, or bring in a routine you saved."
EMPTY_COPY_LAST = "Copy last week's fixed times"
EMPTY_USE_ROUTINE = "Use a routine"


def nothing_yet(week: WeekModel, assignments: dict) -> bool:
    """The week has no blocks and nothing waiting for a time, and the account has no homework at all.

    Every week nobody has saved is empty, so going by the week alone would take the hours away from
    each next week of a student who has homework, and tell them to add their "first".
    """
    return not assignments and week.leftover_kind(None) == "no_homework"


def start_here_week(week: WeekModel, assignments: dict, week_start: str, saved_weeks: list[str]) -> bool:
    """The one-button card for a brand-new account, not the copy/routine card for a later empty week."""
    if not nothing_yet(week, assignments):
        return False
    return not any(saved != week_start for saved in saved_weeks)


class EmptyWeek(QWidget):
    add_requested = Signal()
    copy_last_requested = Signal()
    routine_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("emptyWeek")
        layout = QVBoxLayout(self)
        self._top = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        layout.addItem(self._top)
        self.heading = QLabel(EMPTY_HEADING)
        self.heading.setObjectName("emptyWeekHeading")
        self.line = QLabel(EMPTY_LINE)
        self.line.setObjectName("emptyWeekLine")
        self.line.setWordWrap(True)
        for label in (self.heading, self.line):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
        layout.addSpacing(16)
        self.add = QPushButton(EMPTY_BUTTON)
        self.add.setObjectName("emptyWeekAdd")
        self.add.clicked.connect(self.add_requested.emit)
        self.copy_last = QPushButton(EMPTY_COPY_LAST)
        self.copy_last.setObjectName("emptyWeekCopyLast")
        self.copy_last.clicked.connect(self.copy_last_requested.emit)
        self.use_routine = QPushButton(EMPTY_USE_ROUTINE)
        self.use_routine.setObjectName("emptyWeekRoutine")
        self.use_routine.clicked.connect(self.routine_requested.emit)
        for button in (self.add, self.copy_last, self.use_routine):
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        self._bottom = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        layout.addItem(self._bottom)
        self.set_blank(False)

    def set_over_hours(self, over: bool) -> None:
        """A later empty week sits as a card on the grid; a new account still fills the page."""
        stretch = QSizePolicy.Policy.Ignored if over else QSizePolicy.Policy.Expanding
        self._top.changeSize(0, 0, QSizePolicy.Policy.Minimum, stretch)
        self._bottom.changeSize(0, 0, QSizePolicy.Policy.Minimum, stretch)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed if over else QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed if over else QSizePolicy.Policy.Preferred,
        )
        self.layout().invalidate()
        if over:
            self.adjustSize()

    def sizeHint(self) -> QSize:  # noqa: N802
        if self.copy_last.isVisible():
            return QSize(max(280, super().sizeHint().width()), 200)
        return super().sizeHint()

    def set_blank(self, blank: bool) -> None:
        """A brand-new account, or a later empty week that already has homework somewhere."""
        self.heading.setText(BLANK_HEADING if blank else EMPTY_HEADING)
        self.line.setText(BLANK_LINE if blank else EMPTY_LINE)
        self.add.setVisible(not blank)
        self.copy_last.setVisible(blank)
        self.use_routine.setVisible(blank)
