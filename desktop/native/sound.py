"""Playing an alert through the sound card. The waveform itself is in tones.py.

Everything here is best-effort, exactly as the web client's audio is wrapped in a try: a machine with
no sound card, a container with no PulseAudio, or a Qt build without the multimedia plugin must ring
silently rather than crash. An alarm that raises is worse than an alarm nobody hears, because the
first one also loses the dialog.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtCore import QBuffer, QByteArray, QObject, QTimer

from desktop.native.tones import RATE, REPEAT_MS, pcm

if TYPE_CHECKING:  # QtMultimedia is imported where it is used, so a build without it still starts.
    from PySide6.QtMultimedia import QAudioSink


# Set by the tests, the rig and fwtest, so what they ring is not heard.
SILENT = "FLEXWEEK_SILENT"


class Bell(QObject):
    """One voice. Asking it to ring again while it is ringing replaces what it is playing."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sink: QAudioSink | None = None
        self._buffer: QBuffer | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(REPEAT_MS)
        self._timer.timeout.connect(self._again)
        self._tone = ""
        self._volume = 0.0

    @property
    def ringing(self) -> bool:
        return self._timer.isActive()

    def once(self, tone: str, volume: float) -> bool:
        """Sound one alert. True when it reached the sound card."""
        self._tone, self._volume = tone, volume
        return self._emit()

    def start(self, tone: str, volume: float) -> bool:
        """Sound an alert and keep sounding it until stop(), as an alarm does."""
        self.stop()
        played = self.once(tone, volume)
        if played:
            self._timer.start()
        return played

    def stop(self) -> None:
        self._timer.stop()
        self._quiet()

    def _again(self) -> None:
        if not self._emit():
            self.stop()

    def _quiet(self) -> None:
        if self._sink is not None:
            self._sink.stop()
            self._sink = None
        if self._buffer is not None:
            self._buffer.close()
            self._buffer = None

    def _emit(self) -> bool:
        data = pcm(self._tone, self._volume)
        if not data:
            return False
        self._quiet()
        try:
            from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

            device = QMediaDevices.defaultAudioOutput()
            if device is None or device.isNull():
                return False
            shape = QAudioFormat()
            shape.setSampleRate(RATE)
            shape.setChannelCount(1)
            shape.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            if not device.isFormatSupported(shape):
                return False
            self._buffer = QBuffer(self)
            self._buffer.setData(QByteArray(data))
            self._buffer.open(QBuffer.OpenModeFlag.ReadOnly)
            self._sink = QAudioSink(device, shape, self)
            if os.environ.get(SILENT):
                # Tests and the rig: everything as it would be, at no volume.
                self._sink.setVolume(0.0)
            self._sink.start(self._buffer)
        except Exception:
            # No sound card, no multimedia plugin, no audio server. The alarm still shows.
            self._quiet()
            return False
        return True
