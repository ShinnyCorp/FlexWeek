"""Building a page never opens a window of its own. A label shown before it has a parent opens as a
separate window for a moment, which takes the keyboard from FlexWeek's window: with Settings built in
the background (J12), the week lost the keyboard after every visit to the week page."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable, Iterator

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QEvent, QObject, Qt
    from PySide6.QtWidgets import QApplication, QPushButton, QWidget

    from desktop.native.previews import render
    from desktop.native.widgets import ChoiceCard, WhyOff


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-stray-windows-test"])


def windows_shown(build: Callable[[], object]) -> list[str]:
    """The widgets that were shown as windows of their own while `build` ran. A picture taken off
    screen is shown on purpose and is not counted."""

    class Watch(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.seen: list[str] = []

        def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
            if (
                event.type() == QEvent.Type.Show
                and isinstance(watched, QWidget)
                and watched.isWindow()
                and not watched.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
            ):
                self.seen.append(f"{type(watched).__name__}#{watched.objectName()}")
            return False

    watch = Watch()
    app = QApplication.instance()
    app.installEventFilter(watch)
    try:
        build()
    finally:
        app.removeEventFilter(watch)
    return watch.seen


def test_a_choice_card_with_a_note_opens_no_window(qapp: QApplication) -> None:
    assert windows_shown(lambda: ChoiceCard("Timeline", "A line through the day", 120)) == []


def test_the_line_under_an_off_button_opens_no_window(qapp: QApplication) -> None:
    button = QPushButton("Save")
    button.setEnabled(False)
    made: list[WhyOff] = []
    assert windows_shown(lambda: made.append(WhyOff(button, "Pick a colour first."))) == []
    holder = QWidget()
    holder.resize(200, 40)
    made[0].setParent(holder)
    holder.show()
    assert made[0].isVisible(), "once it is in a sheet, the line shows while its button is off"
    button.setEnabled(True)
    assert not made[0].isVisible()
    holder.close()


def test_a_dial_picture_opens_no_window_of_its_own(qapp: QApplication) -> None:
    assert windows_shown(lambda: render("dial", None, "light-frost", None, 320)) == []
