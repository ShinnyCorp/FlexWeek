"""0.18.5 #96: with Animations at Off nothing moves anywhere. Each main transition is walked and, right
after it, no clock has run, no picture or dim is over the page, and no widget is drawn through a fade."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable, Iterator

import pytest

pytest_plugins = ["desktop.tests.window_support"]

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

    import desktop.native.motion as motion
    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.motion import FADE_NAME, SLIDE_NAME, Dim, Shift, apply_ui_effects
    from desktop.native.widgets import HomeworkDialog, SheetShade
    from desktop.native.window import NativeWindow
    from desktop.tests.test_week_side import seeded
    from desktop.tests.window_support import qapp, settled, still, wait_until, window  # noqa: F401


@pytest.fixture(autouse=True)
def motion_is_put_back() -> Iterator[None]:
    yield
    apply_ui_effects("normal")


def moving(root: QWidget) -> list[str]:
    """Everything under `root` that is a picture, a dim or a fade. Walks `children()`: findChildren
    would hand a sheet to the window to own."""
    found: list[str] = []
    waiting: list[object] = list(root.children())
    while waiting:
        child = waiting.pop()
        if not isinstance(child, QWidget):
            continue
        waiting.extend(child.children())
        picture = isinstance(child, QLabel) and child.objectName() in (FADE_NAME, SLIDE_NAME)
        if picture and not child.isHidden():
            found.append(f"picture {child.objectName()}")
        if isinstance(child, Dim) and not child.isHidden():
            found.append("dim")
        if isinstance(child, SheetShade) and child.graphicsEffect() is not None:
            found.append("fading backdrop")
        if isinstance(child.graphicsEffect(), Shift):
            found.append(f"fade on {child.objectName() or type(child).__name__}")
    return found


def go_off(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    """The window signed in with a seeded week at Off, and a record of every clock that starts."""
    # Saved, not set on the session: a later reload of the preferences would put Normal back.
    assert window.session.save_preferences({"motion": "off"})
    settled(qapp, window)
    window._apply_appearance()
    assert window._motion == "off"
    seeded(qapp, window)
    window.resize(1280, 800)
    window.show()
    still(window)
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def design(qapp: QApplication, window: NativeWindow, main: str, day: str = "one") -> None:  # noqa: F811
    window._layout = sanitize_layout({"main": main, "day": day})
    window._apply_appearance()
    window.session.set_view("week")
    window._day_mode = False
    window._on_week()
    qapp.processEvents()


def press(qapp: QApplication, window: NativeWindow, name: str) -> None:  # noqa: F811
    window.findChild(QPushButton, name).click()
    qapp.processEvents()


def test_every_main_transition_at_off_starts_no_clock_and_leaves_nothing_moving(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    go_off(qapp, window)
    starts: list[str] = []
    real_start = motion.Clock.start

    def counted(self: motion.Clock, total: int, step: Callable[[float], None]) -> None:
        starts.append(f"{total} ms on {type(self.parent()).__name__}")
        real_start(self, total, step)

    monkeypatch.setattr(motion.Clock, "start", counted)
    seen: list[tuple[str, list[str]]] = []

    def now() -> list[str]:
        return [*moving(window), *(["a clock is running"] if motion.busy() else [])]

    def check(what: str) -> None:
        seen.append((what, now()))
        qapp.processEvents()
        seen.append((what + ", a turn later", now()))

    for main in ("classic", "timeline", "mission", "bento", "retro", "clay"):
        design(qapp, window, main)
        check(f"{main} chosen")
        for name in ("viewDay", "viewMonth", "viewWeek", "viewMyDay", "viewWeek"):
            press(qapp, window, name)
            check(f"{main}: {name}")
            if name == "viewMonth":
                wait_until(qapp, lambda: window.session.month_data is not None)
                check(f"{main}: month arrived")
        window._go_next()
        check(f"{main}: next week")
        window._go_previous()
        check(f"{main}: previous week")
    design(qapp, window, "clay")
    for name in ("clayAhead", "clayBack"):
        arrow = window.findChild(QPushButton, name)
        assert arrow is not None, name
        arrow.click()
        check(f"Clay: {name}")
    design(qapp, window, "retro")
    retro = window._layout_view("retro")
    for key in list(retro._windows):
        retro._hide(key)
        retro._bring(key, window.findChild(QPushButton, "viewWeek"))
        check(f"Retro: window {key} opened")
    for day in ("dial", "one"):
        design(qapp, window, "classic", day)
        press(qapp, window, "viewMyDay")
        check(f"My day as {day}")
    design(qapp, window, "classic")
    window._open_focus_screen()
    check("Focus opened")
    window._close_focus_screen()
    check("Focus closed")
    zooms = [
        button
        for button in window.week_table.findChildren(QPushButton)
        if button.objectName().endswith(("ZoomIn", "ZoomOut")) and button.isEnabled()
    ]
    assert zooms, "the week's zoom buttons were not found"
    for button in zooms:
        button.click()
        check(f"zoom {button.objectName()}")
    window._open_settings()
    check("Settings opened")
    window._settings.close_page()
    check("Settings closed")
    window.toast.show_message("Moved History essay to Fri 18:00.", "Undo", lambda: None)
    check("a notice said")
    window.toast.hide()
    window._open_command_bar()
    check("Ctrl+K opened")
    window.command_bar.hide()
    check("Ctrl+K closed")
    wrong = {what: sorted(set(found)) for what, found in seen if found}
    assert wrong == {}, "something moved at Off"
    assert starts == [], "a clock started at Off"


def test_a_sheet_at_off_has_a_plain_backdrop_and_takes_it_away_when_it_closes(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    go_off(qapp, window)
    seen: list[list[str]] = []

    def run(dialog: HomeworkDialog) -> int:
        dialog.show()
        qapp.processEvents()
        seen.append(moving(window))
        dialog.reject()
        seen.append(moving(window))
        return 0

    monkeypatch.setattr(HomeworkDialog, "exec", run)
    window._add_homework()
    qapp.processEvents()
    seen.append(moving(window))
    assert seen == [[], [], []]
    assert not motion.busy()


def test_choosing_off_in_settings_stops_its_own_sections_moving_at_once(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """The page took the Animations level when it opened, so the section switch right after choosing
    Off still faded and slid at the level it had been opened with."""
    apply_ui_effects("normal")
    window._motion = "normal"
    window._open_settings()
    still(window)
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    page = window._settings
    assert page is not None and page.motion_level == "normal"
    assert moving(window) == []
    starts: list[int] = []
    real_start = motion.Clock.start

    def counted(self: motion.Clock, total: int, step: Callable[[float], None]) -> None:
        starts.append(total)
        real_start(self, total, step)

    monkeypatch.setattr(motion.Clock, "start", counted)
    page.motion.setCurrentIndex(page.motion.findData("off"))
    page.nav.setCurrentRow(1 if page.nav.currentRow() == 0 else 0)
    assert moving(window) == []
    assert starts == [] and not motion.busy()
