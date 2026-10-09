"""Regression (item 4): no button clips its label, in every design and every look, at Small, Normal
and Large text. "Accept late start" on Running late is the known case ("ccept late sta").

For every visible QPushButton with words, on the main window, every Settings section and the sheets
(Add homework, Edit block, School hours, Choose a time, Routines, Running late, Spread, Study hours), two
checks:

* test_no_button_clips_its_words: the box the style gives the words (SE_PushButtonContents, which
  includes the stylesheet's padding) is at least as wide as the words' font-metrics advance plus icon.
  That is "the label is not cut off" as rendered here.
* test_every_button_has_the_roomy_padding: the fix-spec rule (fix-specs.md item 4): width >= words +
  2 x 20 px (+ icon and gap) and height >= 36 (40 at Large). Exceptions as the spec lists them: step,
  segment, pill, chip, small, sheetClose.

Offscreen with the test fonts (desktop/tests/fontconfig.conf). The clip students saw on the AppImage
depends on real fonts/platform style, which this cannot reproduce (Coder could not either).
"""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton, QStyle, QStyleOptionButton, QWidget

from desktop.native.layouts.registry import LAYOUTS
from desktop.native.look import LOOK_PRESETS, ROOMY_MIN, ROOMY_MIN_LARGE, ROOMY_SIDE, VIEW_BUTTONS
from desktop.native.settings import SECTIONS
from desktop.native.widgets import (
    AvailabilityDialog,
    BlockDialog,
    ChooseTimeDialog,
    HomeworkDialog,
    LateDialog,
    RoutineDialog,
    SchoolHoursDialog,
)
from desktop.tests.window_support import free, qapp, server, settled, signed_out, window  # noqa: F401

EXEMPT_PROPS = ("step", "segment", "pill", "chip", "small")
# The top bar's four views are segments of one control in a track, so they are exempt like segments.
EXEMPT_NAMES = {"sheetClose", *VIEW_BUTTONS}
SIZES = ("small", "normal", "large")

# The no-clip check: every design x every look x Small/Normal/Large. The roomy rule: every design on the
# default look and every look on Today's app (classic).
ALL_COMBOS = [(design, preset) for design in LAYOUTS for preset in LOOK_PRESETS]
ROOMY_COMBOS = [(design, "default") for design in LAYOUTS] + [
    ("classic", preset) for preset in LOOK_PRESETS if preset != "default"
]


def params(combos) -> list:
    return [
        pytest.param(design, preset, size, id=f"{design}-{preset}-{size}")
        for design, preset in combos
        for size in SIZES
    ]


def dress(qapp: QApplication, w, design: str, preset: str, size: str) -> None:
    w.resize(1280, 860)
    w._layout = {"main": design, "day": "one", "options": {}}
    w._look = {"preset": preset, "knobs": {"text": size}}
    w.session.look = w._look
    w._apply_appearance()
    settled(qapp, w)
    qapp.processEvents()


def words_room(button: QPushButton) -> tuple[int, int]:
    """(width the style leaves for the words, width the words and icon need)."""
    option = QStyleOptionButton()
    button.initStyleOption(option)
    contents = button.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, button)
    need = button.fontMetrics().horizontalAdvance(button.text().replace("&", ""))
    if not button.icon().isNull():
        need += button.iconSize().width() + 4
    return contents.width(), need


def exempt(button: QPushButton) -> bool:
    return button.objectName() in EXEMPT_NAMES or any(button.property(p) for p in EXEMPT_PROPS)


def visible_buttons(root: QWidget) -> list[QPushButton]:
    return [
        b
        for b in root.findChildren(QPushButton)
        if b.isVisible() and b.text().strip() and b.width() > 0
    ]


def each_screen(qapp: QApplication, w):
    """Yield (screen name, root widget) for the window, every Settings section and the sheets."""
    yield "week", w
    w._open_settings()
    settled(qapp, w)
    for index, section in enumerate(SECTIONS):
        w._settings.nav.setCurrentRow(index)
        qapp.processEvents()
        yield f"settings/{section}", w
    w._close_settings(save=False)
    settled(qapp, w)
    week = w.session.week_start
    waiting = {
        "id": "h1", "title": "Essay", "duration_min": 60, "days": list(range(7)), "assignment_id": "a1"
    }
    sheets = {
        "add-homework": lambda: HomeworkDialog(w, today=week, category="assignments"),
        "block-editor": lambda: BlockDialog(w, day=2, start="16:00", duration_min=60),
        "school-hours": lambda: SchoolHoursDialog(w),
        "choose-a-time": lambda: ChooseTimeDialog(w, waiting, week, list(range(7)), [], None),
        "routines": lambda: RoutineDialog(w, {}, [], week),
        "running-late": lambda: LateDialog(w, "Starting from 14:15 today (Wednesday)."),
        "study-hours": lambda: AvailabilityDialog(w, {}),
    }
    for name, make in sheets.items():
        dialog = make()
        dialog.show()
        qapp.processEvents()
        settled(qapp, w)
        yield f"sheet/{name}", dialog
        dialog.hide()
        free(dialog)


def measure(qapp, w, design, preset, size):
    dress(qapp, w, design, preset, size)
    clipped, cramped = [], []
    minimum = ROOMY_MIN_LARGE if size == "large" else ROOMY_MIN
    for screen, root in each_screen(qapp, w):
        for button in visible_buttons(root):
            room, need = words_room(button)
            label = f"{screen}: {button.text()!r} ({button.objectName() or type(button).__name__})"
            if room < need:
                clipped.append(f"{label} words {need}px in {room}px")
            too_small = button.width() < need + 2 * ROOMY_SIDE or button.height() < minimum
            if not exempt(button) and too_small:
                cramped.append(f"{label} {button.width()}x{button.height()} for {need}px words")
    if os.environ.get("REGTEST_BUTTON_LOG"):
        with open(os.environ["REGTEST_BUTTON_LOG"], "a") as log:
            for line in clipped:
                log.write(f"CLIP {design}/{preset}/{size} {line}\n")
            for line in cramped:
                log.write(f"ROOMY {design}/{preset}/{size} {line}\n")
    return sorted(set(clipped)), sorted(set(cramped))


@pytest.mark.parametrize(("design", "preset", "size"), params(ALL_COMBOS))
def test_no_button_clips_its_words(qapp, window, design, preset, size) -> None:
    clipped, _ = measure(qapp, window, design, preset, size)
    assert clipped == []


@pytest.mark.parametrize(("design", "preset", "size"), params(ROOMY_COMBOS))
def test_every_button_has_the_roomy_padding(qapp, window, design, preset, size) -> None:
    _, cramped = measure(qapp, window, design, preset, size)
    assert cramped == []


def test_accept_late_start_keeps_its_words_at_large_in_retro(qapp, window) -> None:
    """The known case, in the widest font (Retro's pixel font) at Large text."""
    dress(qapp, window, "retro", "default", "large")
    dialog = LateDialog(window, "Starting from 14:15 today (Wednesday).")
    dialog.show()
    qapp.processEvents()
    try:
        room, need = words_room(dialog.accept_button)
        assert room >= need, f"'Accept late start' needs {need}px, has {room}px"
    finally:
        dialog.hide()
        free(dialog)


def test_no_button_with_words_has_a_fixed_or_largest_width(qapp, window) -> None:
    """Item 4: never a fixed or maximum width on a button with words; a row with no room wraps."""
    from desktop.native.look import ROOMY_PAD

    assert ROOMY_PAD  # the numbers the sheets use
    held = []
    for size in ("normal", "large"):
        dress(qapp, window, "classic", "default", size)
        for screen, root in each_screen(qapp, window):
            for button in visible_buttons(root):
                if exempt(button):
                    continue
                if button.maximumWidth() < 16777215:
                    held.append(f"{size} {screen}: {button.text()!r} max {button.maximumWidth()}")
    assert held == []


def test_a_button_in_an_open_sheet_measures_again_when_the_text_size_changes(qapp, window) -> None:
    """Item 4, acceptance 3: Normal to Large with a sheet open. Qt kept each button's first size."""
    dress(qapp, window, "classic", "default", "normal")
    dialog = LateDialog(window, "Starting from 14:15 today (Wednesday).")
    dialog.show()
    qapp.processEvents()
    try:
        for size in ("large", "small", "large"):
            window._look = {"preset": "default", "knobs": {"text": size}}
            window.session.look = window._look
            window._apply_appearance()
            qapp.processEvents()
            for button in (dialog.accept_button, dialog.findChild(QPushButton, "latePreview")):
                room, need = words_room(button)
                assert room >= need, f"{size}: {button.text()!r} needs {need}px, has {room}px"
    finally:
        dialog.hide()
        free(dialog)


def test_the_running_late_answers_go_under_preview_when_the_row_has_no_room(qapp, window) -> None:
    """The sheet keeps its width on the scale; its row wraps instead of squeezing a button."""
    dress(qapp, window, "classic", "terminal", "large")
    dialog = LateDialog(window, "Starting from 14:15 today (Wednesday).")
    dialog.show()
    qapp.processEvents()
    try:
        preview = dialog.findChild(QPushButton, "latePreview")
        assert dialog.accept_button.width() >= dialog.accept_button.sizeHint().width()
        assert dialog.accept_button.mapTo(dialog, dialog.accept_button.rect().topLeft()).y() > preview.mapTo(
            dialog, preview.rect().topLeft()
        ).y(), "the answers sit under Preview"
    finally:
        dialog.hide()
        free(dialog)
