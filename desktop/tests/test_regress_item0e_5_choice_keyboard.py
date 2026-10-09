"""Regression for fix-specs.md items 0e and 5 (choice controls and Text size, Settings > Appearance).

0e: in `widgets.py::Segmented` only the first segment takes Tab focus, focus does not follow the
chosen one, and Left/Right/Home/End do nothing. The spec's
guard: for every Segmented in Settings and Add homework, Tab in lands on the chosen one, Right changes
the value, End picks the last, and no mouse event is used.
5: Text size is hidden behind "Show shape, spacing and type" on a fresh account.

Keys go through the window system's path (QTest on the window's QWindow). Known failures are
xfail(strict=True).
"""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from desktop.native.settings import KNOB_LABELS, SECTIONS
from desktop.native.widgets import HomeworkDialog, Segmented
from desktop.tests.window_support import free, qapp, server, signed_out, window  # noqa: F401

KNOWN_0E = (
    "known failure (item 0e): only the first segment is a Tab stop and Left/Right/Home/End do nothing"
)
KNOWN_5 = "known failure (item 5): Text size is hidden until 'Show shape, spacing and type' is on"
# (section of Settings, or "homework" for the Add homework sheet; objectName), found on 0.18.4.
CONTROLS = [
    (0, "prefThemeMain"), (0, "lookSurface"), (0, "lookCorners"), (0, "lookDepth"), (0, "lookFont"),
    (0, "lookBlocks"), (0, "lookDensity"), (0, "lookText"), (0, "prefMotion"),
    (1, "prefDragStep"), (4, "prefPreferredView"), (4, "prefClock"),
    ("homework", "homeworkWhen"), ("homework", "homeworkSpread"),
]


def press(widget: QWidget, key) -> None:
    QTest.keyClick(widget.window().windowHandle(), key)
    QApplication.processEvents()


def control(qapp, window, where, name: str, made: list) -> Segmented:
    if where == "homework":
        dialog = HomeworkDialog(window, today=window.session.week_start, category="assignments")
        dialog.show()
        assert QTest.qWaitForWindowExposed(dialog)
        dialog.activateWindow()
        made.append(dialog)
        root = dialog
    else:
        window._open_settings()
        page = window._settings
        page.fine_tune.setChecked(True)
        page.nav.setCurrentRow(where)
        root = page
    qapp.processEvents()
    found = root.findChild(Segmented, name)
    assert found is not None and found.isVisible(), f"{name} not shown in {where}"
    return found


def tab_into(segmented: Segmented) -> QWidget | None:
    """Focus the widget before the control in the focus chain and press Tab, as a student does."""
    first = segmented.buttons()[0]
    before = first.previousInFocusChain()
    while before is not None and (
        before in segmented.buttons()
        or not (before.isVisible() and before.focusPolicy() & Qt.FocusPolicy.TabFocus)
    ):
        before = before.previousInFocusChain()
    assert before is not None
    before.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()
    press(before, Qt.Key.Key_Tab)
    return QApplication.focusWidget()


@pytest.mark.parametrize(("where", "name"), CONTROLS, ids=[name for _w, name in CONTROLS])
@pytest.mark.xfail(strict=True, reason=KNOWN_0E)
def test_a_choice_control_works_from_the_keyboard(qapp, window, where, name) -> None:
    made: list = []
    try:
        box = control(qapp, window, where, name, made)
        chosen = box.currentIndex()
        landed = tab_into(box)
        said = f"Tab landed on {landed and landed.objectName()}, chosen {chosen}"
        assert landed is box.buttons()[chosen], said
        step = Qt.Key.Key_Right if chosen < box.count() - 1 else Qt.Key.Key_Left
        press(box, step)
        assert box.currentIndex() != chosen, "Right/Left did not change the value"
        press(box, Qt.Key.Key_End)
        assert box.currentIndex() == box.count() - 1, "End did not pick the last"
        press(box, Qt.Key.Key_Home)
        assert box.currentIndex() == 0, "Home did not pick the first"
        assert QApplication.focusWidget() is box.buttons()[0], "focus did not follow the chosen segment"
    finally:
        for widget in made:
            widget.hide()
            free(widget)


def appearance(qapp, window):
    window.resize(1280, 800)
    window._open_settings()
    page = window._settings
    page.nav.setCurrentRow(SECTIONS.index("Appearance & layout"))
    for _ in range(5):
        qapp.processEvents()
    return page


@pytest.mark.xfail(strict=True, reason=KNOWN_5)
def test_5_text_size_is_shown_on_a_fresh_account_without_any_switch(qapp, window) -> None:
    page = appearance(qapp, window)
    assert not page.fine_tune.isChecked()
    text = page.findChild(Segmented, "lookText")
    assert text is not None and text.isVisible()
    viewport = page.stack.currentWidget().viewport()
    top = text.mapTo(viewport, text.rect().topLeft()).y()
    assert top >= 0 and top + text.height() <= viewport.height(), "not visible without scrolling at 1280x800"


@pytest.mark.xfail(strict=True, reason=KNOWN_5)
def test_5_choosing_large_leaves_the_switch_off(qapp, window) -> None:
    page = appearance(qapp, window)
    text = page.findChild(Segmented, "lookText")
    assert text.isVisible(), "Text size not reachable without the switch"
    text.setCurrentIndex(text.findData("large"))
    qapp.processEvents()
    assert not page.fine_tune.isChecked()


def test_5_text_size_is_listed_once_with_the_switch_on(qapp, window) -> None:
    """Guard (acceptance check 3)."""
    page = appearance(qapp, window)
    page.fine_tune.setChecked(True)
    qapp.processEvents()
    rows = [
        label
        for label in page.findChildren(QLabel)
        if label.isVisible() and label.text() == KNOB_LABELS["text"]
    ]
    assert len(rows) == 1
