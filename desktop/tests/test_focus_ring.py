"""0.18.5 #92: a button of the top bar reached with the keyboard gets a 2 px ring in the accent with a 2 px
gap of the page's own colour, in every look, at 3 to 1 on the page."""

# ruff: noqa: F811  (pytest fixtures imported by name)

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from desktop.native.look import pack_stylesheet, resolved_palette, sanitize_look
from desktop.native.tokens import contrast
from desktop.native.widgets import Segment, SegmentTrack, control_art, keyboard_focus_rings
from desktop.tests.window_support import host, qapp  # noqa: F401

# Worked out from the requirement (mock-up round 3): the accent itself where it reads 3 to 1 on the page.
LOOKS = {
    "light": ("light-frost", False, "default", "#3d6fc4"),
    "dark": ("dark-frost", True, "default", "#7fa8ff"),
    "paper": ("light-frost", False, "paper", "#1f3a68"),
    "ink": ("light-frost", False, "ink", "#7fa8ff"),
}
BAR = (
    "prevWeek", "nextWeek", "todayWeek", "addButton", "addArrow", "solveButton", "moreButton", "settingsGear",
)


def near(first: QColor, second: str, slack: int = 6) -> bool:
    other = QColor(second)
    return all(abs(a - b) <= slack for a, b in zip(first.getRgb()[:3], other.getRgb()[:3], strict=True))


def make_bar(qapp, host: QWidget, pack: str, dark: bool, preset: str) -> tuple[dict, dict[str, QPushButton]]:
    look = sanitize_look({"preset": preset})
    palette = resolved_palette(pack, dark, look)
    host.setStyleSheet(pack_stylesheet(pack, dark, look, "default", palette, control_art(palette)))
    row = QHBoxLayout(host)
    row.setContentsMargins(24, 24, 24, 24)
    row.setSpacing(16)
    made: dict[str, QPushButton] = {}
    for name in BAR:
        button = QPushButton("" if name in ("prevWeek", "nextWeek", "settingsGear", "addArrow") else name)
        button.setObjectName(name)
        row.addWidget(button)
        made[name] = button
    track = SegmentTrack()
    track.setObjectName("segments")
    inside = QHBoxLayout(track)
    inside.setContentsMargins(0, 0, 0, 0)
    week = Segment("Week")
    week.setObjectName("viewWeek")
    week.setCheckable(True)
    track.add(week)
    row.addWidget(track)
    made["viewWeek"] = week
    made["cancel"] = QPushButton("Cancel")
    row.addWidget(made["cancel"])
    host.show()
    host.activateWindow()
    QTest.qWaitForWindowActive(host)
    for _ in range(3):
        qapp.processEvents()
    return palette, made


def ring_of(host: QWidget) -> QWidget | None:
    return next((child for child in host.children() if child.objectName() == "barFocusRing"), None)


def tab_to(qapp, button: QPushButton) -> None:
    # A window's first button already has the focus when it opens, and focusing it again says nothing.
    button.clearFocus()
    qapp.processEvents()
    button.setFocus(Qt.FocusReason.TabFocusReason)
    for _ in range(3):
        qapp.processEvents()


@pytest.mark.parametrize("look", LOOKS)
def test_a_bar_button_reached_by_key_is_ringed_2_px_with_a_2_px_gap_at_3_to_1(qapp, host, look: str) -> None:
    pack, dark, preset, expected = LOOKS[look]
    keyboard_focus_rings(qapp)
    palette, bar = make_bar(qapp, host, pack, dark, preset)
    for name in (*BAR, "viewWeek"):
        button = bar[name]
        tab_to(qapp, button)
        ring = ring_of(host)
        assert ring is not None and ring.isVisible(), (look, name)
        corner = button.mapTo(host, QPoint(0, 0))
        assert ring.geometry().topLeft() == corner - QPoint(4, 4), (look, name)
        assert ring.size().width() == button.width() + 8 and ring.size().height() == button.height() + 8
        picture = host.grab().toImage()
        mid = corner.y() + button.height() // 2
        # 4 to 2 px outside the button is the ring, the 2 px next to the button is the page.
        assert near(picture.pixelColor(corner.x() - 3, mid), expected), (look, name, "ring")
        assert near(picture.pixelColor(corner.x() - 4, mid), expected), (look, name, "ring edge")
        if name == "viewWeek":
            # Inside the view control's own track, the gap is the track's colour, not the page's.
            continue
        assert near(picture.pixelColor(corner.x() - 1, mid), palette["window"]), (look, name, "gap")
        assert near(picture.pixelColor(corner.x() - 2, mid), palette["window"]), (look, name, "gap")
        assert near(picture.pixelColor(corner.x() - 5, mid), palette["window"]), (look, name, "outside")
        assert contrast(expected, palette["window"]) >= 3.0, look


def test_high_contrast_keeps_its_yellow(qapp, host) -> None:
    keyboard_focus_rings(qapp)
    palette, bar = make_bar(qapp, host, "light-frost", False, "high-contrast")
    tab_to(qapp, bar["prevWeek"])
    corner = bar["prevWeek"].mapTo(host, QPoint(0, 0))
    mid = corner.y() + bar["prevWeek"].height() // 2
    assert near(host.grab().toImage().pixelColor(corner.x() - 3, mid), palette["accent"])
    assert contrast(palette["accent"], palette["window"]) >= 3.0


def test_a_click_and_a_plain_button_show_no_ring_and_the_ring_goes_with_the_focus(qapp, host) -> None:
    keyboard_focus_rings(qapp)
    _palette, bar = make_bar(qapp, host, "light-frost", False, "default")
    QTest.mouseClick(bar["prevWeek"], Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert ring_of(host) is None or not ring_of(host).isVisible()
    tab_to(qapp, bar["cancel"])
    assert ring_of(host) is None or not ring_of(host).isVisible()
    tab_to(qapp, bar["nextWeek"])
    assert ring_of(host).isVisible()
    bar["cancel"].setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    assert not ring_of(host).isVisible()
