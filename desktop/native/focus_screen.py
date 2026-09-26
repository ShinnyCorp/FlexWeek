"""The focus timer as the whole window, large enough to read from across a desk.

The timer is the session's `focus`, the same one the strip above the hours shows. This page only
draws it and says what the student pressed; the window does it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from desktop.native.focus import format_countdown, phase_duration_ms, remaining_ms

PHASE_WORDS = {"work": "Focus", "break": "Break", "long_break": "Long break", "ended": "Session finished"}
READY = "Ready when you are"
QUICK_TITLE = "Quick focus"
BACK_HINT = "Esc goes back to your week."
PROGRESS_STEPS = 1000
SKIP_TIPS = {"work": "Skip to the break", "break": "Skip the break", "long_break": "Skip the break"}


class FocusScreen(QWidget):
    back_requested = Signal()
    start_requested = Signal()
    pause_requested = Signal()
    skip_requested = Signal()
    stop_requested = Signal()
    finished_requested = Signal()
    break_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("focusPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 24)
        top = QHBoxLayout()
        self.back = self._button("Back", "focusScreenBack", self.back_requested, quiet=True)
        self.back.setToolTip("Go back to your week. The timer keeps running. Esc")
        top.addWidget(self.back)
        top.addStretch(1)
        layout.addLayout(top)
        layout.addStretch(2)
        self.phase = self._label("focusScreenPhase")
        self.time = self._label("focusScreenTime")
        self.progress = QProgressBar()
        self.progress.setObjectName("focusScreenProgress")
        self.progress.setTextVisible(False)
        self.progress.setRange(0, PROGRESS_STEPS)
        # Centred, a bar takes only its hint's width, which is a sliver.
        self.progress.setFixedWidth(360)
        self.task = self._label("focusScreenTask")
        self.task.setWordWrap(True)
        layout.addWidget(self.phase)
        layout.addWidget(self.time)
        layout.addWidget(self.progress, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(12)
        layout.addWidget(self.task)
        layout.addSpacing(24)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.start = self._button("Start", "focusScreenStart", self.start_requested)
        self.start.setToolTip("Start a focus timer now, without picking homework.")
        self.pause = self._button("Pause", "focusScreenPause", self.pause_requested, quiet=True)
        self.skip = self._button("Skip", "focusScreenSkip", self.skip_requested, quiet=True)
        self.stop = self._button("Finish", "focusScreenFinish", self.stop_requested, quiet=True)
        self.stop.setToolTip("Stop the timer and go back to your week.")
        self.finished = self._button("Finished", "focusScreenFinished", self.finished_requested)
        self.finished.setToolTip("Mark this homework as finished.")
        self.take_break = self._button("Take a break", "focusScreenBreak", self.break_requested, quiet=True)
        for button in (self.start, self.pause, self.skip, self.stop, self.finished, self.take_break):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(3)
        hint = self._label("focusScreenHint")
        hint.setText(BACK_HINT)
        layout.addWidget(hint)

    def _label(self, name: str) -> QLabel:
        made = QLabel()
        made.setObjectName(name)
        made.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return made

    def _button(self, words: str, name: str, signal: Signal, *, quiet: bool = False) -> QPushButton:
        made = QPushButton(words)
        made.setObjectName(name)
        if quiet:
            made.setProperty("quiet", True)
        made.clicked.connect(signal.emit)
        return made

    def set_state(self, session) -> None:
        """Ready with the student's focus length when no timer runs; otherwise the timer as it is."""
        state = session.focus
        prefs = session.preferences
        phase = None if state is None else state.get("phase")
        ended = phase == "ended"
        running = state is not None and not ended
        if state is None:
            self.phase.setText(READY)
            self.time.setText(format_countdown(phase_duration_ms("work", prefs)))
            self.task.setText(QUICK_TITLE)
        else:
            paused = running and not state.get("running")
            self.phase.setText(PHASE_WORDS.get(phase, "") + (" · Paused" if paused else ""))
            left = remaining_ms(state, session.now_ms())
            self.time.setText(format_countdown(left))
            self.task.setText(state.get("title") or QUICK_TITLE)
            whole = phase_duration_ms(phase, prefs) if running else 1
            self.progress.setValue(round(PROGRESS_STEPS * (1 - min(left, whole) / whole)) if running else 0)
        self.progress.setVisible(running)
        self.start.setVisible(state is None)
        self.pause.setText("Pause" if state and state.get("running") else "Resume")
        self.skip.setToolTip(SKIP_TIPS.get(phase or "", ""))
        for button in (self.pause, self.skip, self.stop):
            button.setVisible(running)
        homework = ended and state.get("assignmentId") in (session.assignments or {})
        self.finished.setVisible(bool(homework))
        self.take_break.setVisible(ended)
