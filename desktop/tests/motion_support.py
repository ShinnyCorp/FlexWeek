"""A clock a test moves by hand, for animations that would otherwise be waited for on the wall clock."""

from __future__ import annotations

import pytest

from desktop.native import motion


class ManualTime:
    """The time motion.Clock reads. It stands still until `advance` moves it, so an animation is at an
    exact place on its easing however busy the machine is."""

    def __init__(self) -> None:
        self.now = 1_000

    def __call__(self) -> int:
        return self.now

    def advance(self, ms: int) -> None:
        """Move the time `ms` on, and give every clock that is running the frame it would have had."""
        self.now += ms
        for clock in list(motion._RUNNING):
            # A paused clock has stopped its timer, so no frame comes for it.
            if clock._timer.isActive():
                clock._tick()


@pytest.fixture()
def manual_time(monkeypatch: pytest.MonkeyPatch) -> ManualTime:
    manual = ManualTime()
    monkeypatch.setattr(motion, "now_ms", manual)
    return manual
