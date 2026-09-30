"""The fields every sheet, setup page and Settings page shares (5.2 A of 0.17.2): days picked as a row of
pills. One module, so the block editor, Routines, alarms, work hours and setup draw a day the same way;
it imports nothing of the app's own widgets, so each of those can use it."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from desktop.native.calendar import DAY_FULL, DAYS


class DayPicker(QWidget):
    """The seven days as pills on one line, each a checkable button named `name` and its index.
    `changed` says any of them was ticked or unticked."""

    changed = Signal()

    def __init__(self, days: list[int] | tuple[int, ...] = (), name: str = "day") -> None:
        super().__init__()
        self.setObjectName("setupRow")
        # Its height is the pills'; a form short of room squeezed the row to a sliver without this.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        self.buttons: list[QPushButton] = []
        for index, short in enumerate(DAYS):
            button = QPushButton(short)
            button.setObjectName(f"{name}{index}")
            button.setProperty("pill", True)
            button.setCheckable(True)
            button.setChecked(index in days)
            button.setAccessibleName(DAY_FULL[index])
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAutoDefault(False)
            button.toggled.connect(self.changed)
            line.addWidget(button)
            self.buttons.append(button)
        line.addStretch(1)

    def days(self) -> list[int]:
        return [index for index, button in enumerate(self.buttons) if button.isChecked()]

    def set_days(self, days: list[int]) -> None:
        for index, button in enumerate(self.buttons):
            button.setChecked(index in days)
