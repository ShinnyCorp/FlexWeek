"""Settings opens without rebuilding the page each time, and the slide starts at once."""

from __future__ import annotations

import importlib.util
import time
from collections.abc import Iterator

import pytest

pytest_plugins = ["desktop.tests.window_support"]

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel

    import desktop.native.motion as motion
    from desktop.native.layouts.dialog import LayoutSection
    from desktop.native.motion import SLIDE_NAME, apply_ui_effects
    from desktop.native.settings import SettingsPage
    from desktop.native.window import NativeWindow
    from desktop.tests.window_support import still, window  # noqa: F401


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-settings-open-test"])


def test_the_second_settings_open_starts_sliding_without_building_again(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """J12: closing Settings deleted the page, so every open rebuilt it for ~170 ms before the slide."""
    window._motion = "normal"
    apply_ui_effects("normal")
    built = 0
    real_init = SettingsPage.__init__

    def counting_init(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        nonlocal built
        built += 1
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(SettingsPage, "__init__", counting_init)
    window._discard_settings_page()
    for _ in range(60):
        qapp.processEvents()
        QTest.qWait(5)
    stamps: list[float] = []
    real_run = motion._run

    def spy(owner, total, step, done):  # type: ignore[no-untyped-def]
        t0 = time.perf_counter()

        def timed(at: float) -> None:
            if not stamps:
                stamps.append(time.perf_counter() - t0)
            step(at)

        real_run(owner, total, timed, done)

    monkeypatch.setattr(motion, "_run", spy)
    window._open_settings()
    still(window)
    assert built == 1
    window._settings.close_page()
    still(window)
    stamps.clear()
    t0 = time.perf_counter()
    window._open_settings()
    open_ms = (time.perf_counter() - t0) * 1000
    qapp.processEvents()
    slides = [label for label in window._stack.findChildren(QLabel, SLIDE_NAME) if label.isVisible()]
    assert built == 1, "the page was built once while idle, not again on the second open"
    assert slides, "the slide picture is on screen at once"
    assert open_ms < 50, f"the second open waited {open_ms:.0f} ms before the slide could start"
    assert stamps and stamps[0] * 1000 < 20, "the first slide frame came within one frame of the click"
    window._settings.close_page()
    still(window)


def test_settings_skips_rebuild_when_nothing_shown_has_changed(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reopening Settings with the same preferences must not rebuild its design sections; a changed
    preference must."""
    rebuilt = 0
    real = LayoutSection._rebuild

    def counting(self, fresh: bool) -> None:
        nonlocal rebuilt
        rebuilt += 1
        real(self, fresh)

    monkeypatch.setattr(LayoutSection, "_rebuild", counting)
    window._open_settings()
    still(window)
    rebuilt = 0
    window._settings.close_page()
    still(window)
    window._open_settings()
    still(window)
    assert rebuilt == 0
    window._settings.close_page()
    still(window)
    window.session.preferences["clock_24h"] = not window.session.preferences.get("clock_24h")
    rebuilt = 0
    window._open_settings()
    still(window)
    assert rebuilt >= 1
    window._settings.close_page()
    still(window)


def test_a_new_account_never_sees_the_last_accounts_settings(
    qapp: QApplication, window: NativeWindow
) -> None:
    window._open_settings()
    page = window._settings
    assert page is not None
    page.alarm_name.setText("Old account wake")
    page._add_alarm()
    assert page.updates()["alarms"]
    page.account_id = 0
    window._refresh_settings_page()
    fresh = window._settings
    assert fresh is not None
    assert fresh.account_id == window.session.account["id"]
    assert fresh.updates()["alarms"] == []
