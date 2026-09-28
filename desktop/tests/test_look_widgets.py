"""The Blocks look knob on real Qt widgets: what each block is given and what the calendar paints.

A stylesheet cannot reach a painted block, so this knob is the one most likely to be stored and ignored.
Expected colours come from the palette and the category table, never from a grab of the current output.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QRectF, QStandardPaths
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QPushButton, QVBoxLayout, QWidget

    from desktop.native.calendar import CATEGORIES
    from desktop.native.hours.canvas import Drawn
    from desktop.native.hours.classic import ClassicWeek
    from desktop.native.hours.hand import Hand, Verdict
    from desktop.native.hours.month import MonthGrid
    from desktop.native.look import (
        LOOK_DEFAULTS,
        effective_look,
        look_menu_token,
        pack_stylesheet,
        preset_knobs,
        resolved_palette,
    )
    from desktop.native.settings import AboutDialog, SettingsPage
    from desktop.native.tokens import SINK, mix_oklab
    from desktop.native.weekmodel import build_week
    from desktop.native.widgets import DIALOG_MARGIN, use_app_style
    from desktop.native.window import NativeWindow
    from desktop.server import LocalServer
    from desktop.tests.logic_support import past_setup

WEEK = "2026-09-14"
SCHOOL = {
    "id": "school",
    "title": "School",
    "kind": "locked",
    "category": "class",
    "start": "08:00",
    "duration_min": 60,
    "days": [0],
}
CLUB = {"id": "club", "title": "Club", "kind": "locked", "start": "10:00", "duration_min": 30, "days": [1]}
# School's colours: the pale fill and strong mark of a light look, and the tone and mark of a dark one.
PALE, STRONG = "#d1e7ff", "#4687d8"
TONE, DEEP_MARK = "#65a7fa", "#65a7fa"
# The hosts of the hands these tests make: a hand is its host's Qt child and keeps no reference to it.
HOSTS: list = []


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    # The window reads flexweek-look.json from the user data folder on startup. Test mode points Qt at
    # a scratch location, so these tests neither read nor write the look saved on this machine.
    QStandardPaths.setTestModeEnabled(True)
    application = QApplication.instance() or QApplication(["flexweek-look-test"])
    yield application


def look_of(**knobs: str) -> dict:
    return {"preset": "default", "knobs": knobs}


def week(qapp: QApplication, look: dict | None, pack: str = "nocturne") -> tuple[ClassicWeek, dict]:
    """Today's app's week, opened at 07:00 so School and Club are both on screen."""
    palette = resolved_palette(pack, pack in {"nocturne", "dark-frost"}, look)
    host = QWidget()
    HOSTS.append(host)
    calendar = ClassicWeek(Hand(lambda block_id, from_day, span: Verdict(False, ""), host))
    calendar.resize(1000, 800)
    calendar.set_look(look, palette)
    calendar.set_week(build_week(WEEK, [SCHOOL, CLUB], {}, None), None, 7 * 60)
    calendar.show()
    qapp.processEvents()
    calendar.hours.relayout()
    qapp.processEvents()
    return calendar, palette


def block_on(calendar: ClassicWeek, block_id: str) -> tuple[Drawn, QRectF]:
    hours = calendar.hours
    return next(
        (drawn, rect)
        for track in hours.tracks
        for drawn, rect in hours.drawn(track)
        if drawn.block_id == block_id
    )


def shape(calendar: ClassicWeek, block_id: str) -> tuple[str, str, str | None, str | None]:
    """Fill, ink, outline and edge, as the week paints the block."""
    fill, ink, outline, edge = calendar.hours.painter.fills(block_on(calendar, block_id)[0])
    return fill.name(), ink.name(), outline and outline.name(), edge and edge.name()


def painted(window: NativeWindow, block_id: str) -> tuple[str, str | None]:
    hours = window.week_table.hours
    if not hours.tracks:
        window.show()
        hours.resize(980, 640)
        hours.relayout()
    track = hours.track_for(0, 8 * 60)
    drawn = next(item for item, _rect in hours.drawn(track) if item.block_id == block_id)
    fill, _ink, _outline, edge = hours.painter.fills(drawn)
    return fill.name(), None if edge is None else edge.name()


def pixel(calendar: ClassicWeek, block_id: str, where: str) -> str:
    rect = block_on(calendar, block_id)[1]
    image = calendar.hours.grab().toImage()
    # "left" sits on the 4px edge or the 2px outline; "inside" is past the text, clear of both.
    x = rect.left() + 1.5 if where == "left" else rect.right() - 8
    return QColor(image.pixel(int(x), int(rect.center().y()))).name()


def test_the_category_table_is_what_these_tests_assume() -> None:
    assert (CATEGORIES["class"]["color"], CATEGORIES["class"]["mark"]) == (PALE, STRONG)
    assert CATEGORIES["class"]["dark"] == (TONE, DEEP_MARK)


def test_a_filled_block_is_the_pale_category_colour_with_ink_that_reads(qapp: QApplication) -> None:
    calendar, palette = week(qapp, look_of(), pack="slate")
    assert shape(calendar, "school") == (PALE, palette["text"], None, None)
    # No category: the palette's own block colours, not a fixed light grey that glares on a dark pack.
    assert shape(calendar, "club")[:2] == (palette["block_locked"], palette["block_locked_ink"])
    assert pixel(calendar, "school", "inside") == PALE


def test_a_filled_block_on_a_dark_pack_is_deep_with_light_ink(qapp: QApplication) -> None:
    """Pale blue on near-black glared, and its black ink read as a hole in the page. The fill is
    School's tone sunk into the panel, as CSS's color-mix in OKLab makes it, in the look's own ink."""
    calendar, palette = week(qapp, look_of())
    deep = mix_oklab(TONE, palette["panel"], SINK)
    assert shape(calendar, "school") == (deep, palette["text"], None, None)
    assert pixel(calendar, "school", "inside") == deep
    assert shape(calendar, "club")[:2] == (palette["block_locked"], palette["block_locked_ink"])


def test_an_outlined_block_is_drawn_as_one_outline_in_the_strong_colour(qapp: QApplication) -> None:
    calendar, palette = week(qapp, look_of(blocks="outline"))
    assert shape(calendar, "school")[:3] == (palette["grid"], palette["text"], DEEP_MARK)
    assert pixel(calendar, "school", "left") == DEEP_MARK
    assert pixel(calendar, "school", "inside") == palette["grid"]


def test_an_edge_block_is_a_plain_card_with_the_strong_colour_down_its_left(qapp: QApplication) -> None:
    calendar, palette = week(qapp, look_of(blocks="edge"))
    fill, _ink, _outline, edge = shape(calendar, "school")
    assert (fill, edge) == (palette["panel"], DEEP_MARK)
    assert pixel(calendar, "school", "left") == DEEP_MARK
    assert pixel(calendar, "school", "inside") == palette["panel"]


def test_the_outline_stays_visible_on_a_light_pack(qapp: QApplication) -> None:
    calendar, palette = week(qapp, look_of(blocks="outline"), pack="slate")
    assert pixel(calendar, "school", "left") == STRONG
    assert palette["grid"] == "#ffffff"


def test_changing_the_look_repaints_the_week_already_on_screen(qapp: QApplication) -> None:
    calendar, palette = week(qapp, look_of(), pack="slate")
    assert shape(calendar, "school")[0] == PALE
    calendar.set_look(look_of(blocks="edge"), palette)
    fill, _ink, _outline, edge = shape(calendar, "school")
    assert (fill, edge) == (palette["panel"], STRONG)
    assert pixel(calendar, "school", "inside") == palette["panel"]


def test_days_outside_the_month_use_the_palettes_muted_ink(qapp: QApplication) -> None:
    day = {"due_ids": [], "session_count": 0, "locked_count": 0, "scheduled_min": 0, "focus_min": 0}
    snapshot = {
        "month": "2026-09",
        "days": [
            {**day, "date": "2026-08-31", "in_month": False},
            {**day, "date": "2026-09-01", "in_month": True},
        ],
        "overdue": [],
    }
    grid = MonthGrid()
    terminal = resolved_palette("slate", False, {"preset": "terminal", "knobs": {}})
    grid.set_month(snapshot, False)
    grid.set_palette(terminal)
    assert grid.canvas.cells[0].in_month is False
    assert grid.canvas.painter.c("muted").name() == terminal["muted"] == "#8b949e"


def settings(look: dict) -> SettingsPage:
    return SettingsPage(None, {}, look, {})


def test_settings_opens_on_appearance_with_fine_tune_closed(qapp: QApplication) -> None:
    dialog = settings({})
    assert dialog.nav.currentRow() == 0
    assert dialog.fine_host.isHidden() is True
    dialog.fine_tune.setChecked(True)
    assert dialog.fine_host.isHidden() is False


def choose(dialog: SettingsPage, token: str) -> None:
    index = dialog.look.findData(token)
    assert index >= 0, token
    dialog.look.setCurrentIndex(index)


def move(dialog: SettingsPage, knob: str, value: str) -> None:
    dialog.knobs[knob].setCurrentIndex(dialog.knobs[knob].findData(value))


def shown(dialog: SettingsPage) -> dict:
    return {knob: box.currentData() for knob, box in dialog.knobs.items()}


def test_choosing_terminal_in_settings_applies_every_one_of_its_knobs(qapp: QApplication) -> None:
    """The dialog once recorded all seven boxes as overrides.

    Terminal then arrived with its colours, round corners and a sans font.
    """
    dialog = settings({"preset": "default", "knobs": {}})
    assert shown(dialog) == LOOK_DEFAULTS
    choose(dialog, look_menu_token("preset", "terminal"))
    assert shown(dialog) == preset_knobs("terminal")
    chosen = dialog.look_choice()
    assert chosen == {"preset": "terminal", "knobs": {}}
    assert effective_look(chosen) == preset_knobs("terminal")


def test_a_knob_moved_by_hand_stays_when_the_look_changes(qapp: QApplication) -> None:
    dialog = settings({"preset": "default", "knobs": {}})
    move(dialog, "corners", "rounded")
    choose(dialog, look_menu_token("preset", "terminal"))
    assert shown(dialog)["corners"] == "rounded"
    assert shown(dialog)["font"] == "mono"
    assert dialog.look_choice() == {"preset": "terminal", "knobs": {"corners": "rounded"}}
    move(dialog, "depth", "bold")
    assert dialog.look_choice() == {"preset": "terminal", "knobs": {"corners": "rounded", "depth": "bold"}}
    assert effective_look(dialog.look_choice())["font"] == "mono"
    choose(dialog, look_menu_token("pack", "system"))
    assert shown(dialog)["corners"] == "rounded"
    assert shown(dialog)["depth"] == "bold"
    assert shown(dialog)["font"] == "sans"
    assert dialog.look_choice() == {"preset": "default", "knobs": {"corners": "rounded", "depth": "bold"}}


def test_opening_settings_shows_the_look_on_screen_and_changes_nothing(qapp: QApplication) -> None:
    stored = {"preset": "terminal", "knobs": {"text": "large", "corners": "rounded"}}
    dialog = settings(stored)
    # Each box shows what the student sees, not the first value in its list.
    assert shown(dialog) == {**preset_knobs("terminal"), "text": "large", "corners": "rounded"}
    # Pressing OK untouched must hand back exactly what was stored: the preset connection is made
    # after the stored preset is selected, so opening the dialog never resets a student's own knobs.
    assert dialog.look_choice() == stored
    assert dialog.findChild(QComboBox, "lookPreset") is None
    assert dialog.look.findData(look_menu_token("preset", "terminal")) >= 0
    assert dialog.look.findData(look_menu_token("pack", "system")) >= 0


def wait_until(qapp: QApplication, predicate, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was still false")


def test_a_look_chosen_in_the_window_reaches_the_calendar_not_only_the_stylesheet(
    qapp: QApplication, tmp_path: Path
) -> None:
    server = LocalServer(tmp_path / "flexweek.db")
    server.start()
    window = NativeWindow(server.origin)
    try:
        window.username.setText("look_student")
        window.password.setText("a-long-test-password")
        window.findChild(QPushButton, "createAccount").click()
        wait_until(qapp, lambda: window._stack.currentWidget().objectName() == "recoveryPage")
        window.recovery_ack.setChecked(True)
        window.recovery_continue.click()
        past_setup(qapp, window)
        window.session.add_block(dict(SCHOOL))
        window.session.save()
        wait_until(qapp, lambda: window.session.revision == 1 and not window.session.busy)
        assert painted(window, "school")[0] == PALE

        # What Settings does when the student presses OK.
        window._look = look_of(blocks="edge")
        window._apply_appearance()
        fill, edge = painted(window, "school")
        assert edge == STRONG
        assert fill != PALE
        assert "border: 1px solid" in window.styleSheet()
    finally:
        with contextlib.suppress(RuntimeError):
            window.session.client.reset()
        qapp.processEvents()
        server.stop()


def test_a_dialogs_content_sits_24_px_in_from_its_edges(qapp: QApplication) -> None:
    """Qt's styles give a dialog about 11 px. The app's style gives every dialog 24, and a layout
    inside it, or one given margins of its own, keeps what it had."""
    use_app_style(qapp)
    host = QWidget()
    HOSTS.append(host)
    about = AboutDialog(host, None, "/tmp/flexweek")
    margins = about.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (DIALOG_MARGIN,) * 4
    assert DIALOG_MARGIN == 24
    plain = QDialog(host)
    outer = QVBoxLayout(plain)
    inner_host = QWidget()
    inner = QVBoxLayout(inner_host)
    outer.addWidget(inner_host)
    assert inner.contentsMargins().left() < DIALOG_MARGIN
    outer.setContentsMargins(0, 0, 0, 0)
    assert outer.contentsMargins().left() == 0


def test_todays_name_above_the_week_is_marked_and_no_other(qapp: QApplication) -> None:
    calendar, palette = week(qapp, look_of(), pack="slate")
    assert [label.property("today") for label in calendar._name_labels] == [False] * 7
    calendar.set_week(build_week(WEEK, [SCHOOL, CLUB], {}, None), 2, 7 * 60)
    assert [label.property("today") for label in calendar._name_labels] == [False, False, True] + [False] * 4
    sheet = pack_stylesheet("slate", False, look_of())
    assert f'QLabel[today="true"] {{ color: {palette["accent"]}; font-weight: 600; ' in sheet
    assert f'border-bottom: 2px solid {palette["accent"]}; border-radius: 0; }}' in sheet
