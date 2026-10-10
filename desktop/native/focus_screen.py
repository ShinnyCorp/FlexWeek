"""The focus timer as the whole window, large enough to read from across a desk.

The timer is the session's `focus`, the same one the strip above the hours shows. This page only
draws it and says what the student pressed; the window does it. It wears the student's look, with
the countdown in the ring One thing's Countdown uses (decision 19 of 0.17).
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from desktop.native import icons
from desktop.native.focus import format_countdown, phase_duration_ms, phase_total_ms, remaining_ms
from desktop.native.ring import CountdownRing, ring_colours

PHASE_WORDS = {"work": "Focus", "break": "Break", "long_break": "Long break", "ended": "Session finished"}
READY = "Ready when you are"
QUICK_TITLE = "Quick focus"
BACK_HINT = "Esc goes back to your week."
SKIP_TIPS = {"work": "Skip to the break", "break": "Skip the break", "long_break": "Skip the break"}
# The ring at its largest, and what the page keeps for Back, the buttons and the hint around it.
RING_MAX = 440
RING_MIN = 240
AROUND_RING = 260


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
        self.back.setIconSize(QSize(16, 16))
        top.addWidget(self.back)
        top.addStretch(1)
        layout.addLayout(top)
        layout.addStretch(2)
        self.ring = CountdownRing()
        self.phase = self._label("focusScreenPhase")
        self.task = self._label("focusScreenTask")
        self.ring.above.addWidget(self.phase)
        self.ring.below.addWidget(self.task)
        layout.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(24)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        # One filled button, the next step: Start, Pause or Resume, or Finished once time is up.
        # Skip and Finish are outlined beside Pause; Take a break is a word.
        self.start = self._button("Start", "focusScreenStart", self.start_requested)
        self.start.setToolTip("Start a focus timer now, without picking homework.")
        self.pause = self._button("Pause", "focusScreenPause", self.pause_requested)
        self.skip = self._button("Skip", "focusScreenSkip", self.skip_requested, outlined=True)
        self.stop = self._button("Finish", "focusScreenFinish", self.stop_requested, outlined=True)
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
        self._task_words = ""
        self.set_palette({"accent": "#3d6fc4", "text": "#111827", "window": "#f7f8fa", "muted": "#5b6474"})

    def _label(self, name: str) -> QLabel:
        made = QLabel()
        made.setObjectName(name)
        made.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return made

    def _button(
        self, words: str, name: str, signal: Signal, *, quiet: bool = False, outlined: bool = False
    ) -> QPushButton:
        made = QPushButton(words)
        made.setObjectName(name)
        if quiet:
            made.setProperty("quiet", True)
        if outlined:
            made.setProperty("outlined", True)
        made.clicked.connect(signal.emit)
        return made

    def set_palette(self, palette: dict, text_scale: float = 1.0) -> None:
        """The look's colours for what a style sheet cannot reach: the ring and Back's chevron."""
        self.ring.set_colours(ring_colours(palette))
        self.ring.set_text_scale(text_scale)
        self.back.setIcon(icons.icon("chevron-left", palette["text"]))

    def set_state(self, session) -> None:
        """Ready with the student's focus length when no timer runs; otherwise the timer as it is."""
        state = session.focus
        prefs = session.preferences
        phase = None if state is None else state.get("phase")
        ended = phase == "ended"
        running = state is not None and not ended
        self.ring.set_waiting(state is None)
        if state is None:
            self.phase.setText(READY)
            self.ring.set_number(format_countdown(phase_duration_ms("work", prefs)))
            self._task_words = QUICK_TITLE
            self.ring.set_left(1.0)
        else:
            paused = running and not state.get("running")
            self.phase.setText(PHASE_WORDS.get(phase, "") + (" · Paused" if paused else ""))
            left = remaining_ms(state, session.now_ms())
            self.ring.set_number(format_countdown(left))
            self._task_words = state.get("title") or QUICK_TITLE
            whole = phase_total_ms(state, prefs) if running else 1
            self.ring.set_left(min(left, whole) / whole if running else 0.0)
        self._show_task()
        self._level_buttons()
        self.start.setVisible(state is None)
        self.pause.setText("Pause" if state and state.get("running") else "Resume")
        self.skip.setToolTip(SKIP_TIPS.get(phase or "", ""))
        for button in (self.pause, self.skip, self.stop):
            button.setVisible(running)
        homework = ended and state.get("assignmentId") in (session.assignments or {})
        self.finished.setVisible(bool(homework))
        self.take_break.setVisible(ended)

    def _level_buttons(self) -> None:
        """Every button as tall as the tallest, shown or not: the filled ones and the outlined ones
        differ by a few pixels, and the row's height moves the ring when one set replaces the other."""
        everyone = (self.start, self.pause, self.skip, self.stop, self.finished, self.take_break)
        for button in everyone:
            button.setMinimumHeight(0)
            button.ensurePolished()
        tallest = max(button.sizeHint().height() for button in everyone)
        for button in everyone:
            button.setMinimumHeight(tallest)

    def time_text(self) -> str:
        """The countdown as the ring shows it."""
        return self.ring.number()

    def _show_task(self) -> None:
        """The homework's name inside the ring, shortened to the ring's width when it is long."""
        room = max(80, round(self.ring.width() * 0.7))
        metrics = QFontMetrics(self.task.font())
        self.task.setText(metrics.elidedText(self._task_words, Qt.TextElideMode.ElideRight, room))
        self.task.setToolTip(self._task_words if self.task.text() != self._task_words else "")

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        side = max(RING_MIN, min(RING_MAX, self.height() - AROUND_RING, self.width() - 48))
        self.ring.setFixedSize(side, side)
        self._show_task()
