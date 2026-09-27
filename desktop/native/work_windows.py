"""The work hours shared by first-run setup and Settings."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.native.weekmodel import hhmm_text

DAYS =("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
START_TIMES = tuple(f"{minute // 60:02d}:{minute % 60:02d}" for minute in range(0, 1440, 15))
END_TIMES = tuple(f"{minute // 60:02d}:{minute % 60:02d}" for minute in range(15, 1441, 15))
MAX_WORK_WINDOWS = 21
PRESETS = (
    ("After school", [0, 1, 2, 3, 4], "15:30", "18:00"),
    ("Evenings", [0, 1, 2, 3, 4], "19:00", "21:00"),
    ("Weekend mornings", [5, 6], "10:00", "12:00"),
)
PRESETS_NOTE = "Each adds a row of hours you can change."


class _WorkWindowRow(QFrame):
    def __init__(
        self,
        window: dict,
        subjects: list[str],
        on_change: Callable[..., None],
        on_remove: Callable[[], None],
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("workWindowRow")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        days_line = QHBoxLayout()
        days_line.addWidget(QLabel("Days"))
        self.days = []
        for day, name in enumerate(DAYS):
            check = QCheckBox(name)
            check.setObjectName(f"workWindowDay{day}")
            check.setChecked(day in window["days"])
            check.toggled.connect(lambda checked, field=check: self._day_toggled(field, checked))
            self.days.append(check)
            days_line.addWidget(check)
        days_line.addStretch()
        layout.addLayout(days_line)

        fields = QHBoxLayout()
        self.start = QComboBox()
        self.start.setObjectName("workWindowStart")
        self.start.setAccessibleName("Work window start")
        for value in START_TIMES:
            self.start.addItem(hhmm_text(value), value)
        self.start.setCurrentIndex(max(0, self.start.findData(window["start"])))
        self.start.currentIndexChanged.connect(on_change)
        fields.addWidget(QLabel("From"))
        fields.addWidget(self.start)

        self.end = QComboBox()
        self.end.setObjectName("workWindowEnd")
        self.end.setAccessibleName("Work window end")
        for value in END_TIMES:
            self.end.addItem(hhmm_text(value), value)
        self.end.setCurrentIndex(max(0, self.end.findData(window["end"])))
        self.end.currentIndexChanged.connect(on_change)
        end_field = QVBoxLayout()
        end_choice = QHBoxLayout()
        end_choice.addWidget(QLabel("to"))
        end_choice.addWidget(self.end)
        end_field.addLayout(end_choice)
        self.end_error = QLabel()
        self.end_error.setObjectName("validationError")
        self.end_error.setTextFormat(Qt.TextFormat.PlainText)
        self.end_error.setAccessibleName("Problem with the end time")
        end_field.addWidget(self.end_error)
        fields.addLayout(end_field)

        self.subject = QComboBox()
        self.subject.setObjectName("workWindowSubject")
        self.subject.setAccessibleName("Subject for this work window")
        self.subject.setEditable(True)
        self.subject.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.subject.lineEdit().setPlaceholderText("Any subject")
        self.subject.lineEdit().setMaxLength(40)
        self.set_subjects(subjects)
        self.subject.setEditText(window.get("subject") or "")
        fields.addWidget(self.subject, 1)

        remove = QPushButton("Remove")
        remove.setObjectName("workWindowRemove")
        remove.setProperty("quiet", True)
        remove.setAccessibleName("Remove work window")
        remove.clicked.connect(on_remove)
        fields.addWidget(remove)
        layout.addLayout(fields)

    def _day_toggled(self, field: QCheckBox, checked: bool) -> None:
        if not checked and not any(day.isChecked() for day in self.days):
            field.setChecked(True)

    def set_subjects(self, subjects: list[str]) -> None:
        current = self.subject.currentText()
        self.subject.clear()
        for subject in dict.fromkeys(subjects):
            self.subject.addItem(subject)
        self.subject.setEditText(current)

    def window(self) -> dict:
        window = {
            "days": [day for day, check in enumerate(self.days) if check.isChecked()],
            "start": self.start.currentData(),
            "end": self.end.currentData(),
        }
        subject = self.subject.currentText().strip()
        if subject:
            window["subject"] = subject
        return window

    def problem(self) -> str | None:
        start = self.start.currentData()
        end = self.end.currentData()
        problem = "End must be after Start." if end <= start else None
        self.end_error.setText(problem or "")
        self.end_error.setVisible(problem is not None)
        return problem


class WorkWindowsEditor(QWidget):
    def __init__(
        self, windows: list[dict], subjects: list[str] | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("workWindowsEditor")
        self._subjects = list(subjects or [])
        self._rows: list[_WorkWindowRow] = []
        layout = QVBoxLayout(self)
        self.message = QLabel()
        self.message.setObjectName("workWindowsMessage")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        # These add rows; they are not choices. Drawn as filled pills they read as options to pick, and
        # nothing showed as picked.
        presets_note = QLabel(PRESETS_NOTE)
        presets_note.setObjectName("workWindowsPresetsNote")
        presets_note.setWordWrap(True)
        layout.addWidget(presets_note)
        presets = QHBoxLayout()
        self._add_buttons = []
        for name, days, start, end in PRESETS:
            button = QPushButton(f"+ {name}")
            button.setObjectName("workWindowPreset" + name.replace(" ", ""))
            button.setProperty("quiet", True)
            button.setAccessibleName(f"Add {name.lower()}")
            button.clicked.connect(
                lambda _checked=False, d=days, s=start, e=end: self._add_window(
                    {"days": d, "start": s, "end": e}
                )
            )
            presets.addWidget(button)
            self._add_buttons.append(button)
        presets.addStretch()
        layout.addLayout(presets)
        self._row_layout = QVBoxLayout()
        layout.addLayout(self._row_layout)
        self.add_button = QPushButton("Add custom hours")
        self.add_button.setObjectName("workWindowAdd")
        self.add_button.clicked.connect(
            lambda: self._add_window(
                {"days": [0, 1, 2, 3, 4], "start": "16:00", "end": "18:00"}
            )
        )
        layout.addWidget(self.add_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.limit = QLabel()
        self.limit.setObjectName("workWindowsLimit")
        layout.addWidget(self.limit)
        self.set_windows(windows)

    def set_subjects(self, subjects: list[str]) -> None:
        self._subjects = list(subjects)
        for row in self._rows:
            row.set_subjects(self._subjects)

    def set_windows(self, windows: list[dict]) -> None:
        if len(windows) > MAX_WORK_WINDOWS:
            raise ValueError("Up to 21 work windows.")
        for row in self._rows:
            self._row_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        for window in windows:
            self._add_window(window)
        self._refresh()

    def windows(self) -> list[dict]:
        return [row.window() for row in self._rows]

    def problem(self) -> str | None:
        problems = [row.problem() for row in self._rows]
        return next((problem for problem in problems if problem), None)

    def _add_window(self, window: dict) -> None:
        if len(self._rows) >= MAX_WORK_WINDOWS:
            return
        row = _WorkWindowRow(
            window,
            self._subjects,
            self._refresh,
            lambda: self._remove_row(row),
            self,
        )
        self._rows.append(row)
        self._row_layout.addWidget(row)
        self._refresh()

    def _remove_row(self, row: _WorkWindowRow) -> None:
        self._rows.remove(row)
        self._row_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._refresh()

    def _refresh(self, *_args: object) -> None:
        count = len(self._rows)
        self.message.setText(
            "Homework is only planned between these times."
            if count
            else "Homework can be planned at any time of day."
        )
        # Said only when it matters: a count under every list was the model's word, not the student's.
        full = count >= MAX_WORK_WINDOWS
        self.limit.setText(f"{MAX_WORK_WINDOWS} is the most you can add." if full else "")
        self.limit.setVisible(full)
        self.add_button.setEnabled(count < MAX_WORK_WINDOWS)
        for button in self._add_buttons:
            button.setEnabled(count < MAX_WORK_WINDOWS)
        self.problem()
