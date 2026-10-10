"""The More menu explains itself (0.15 rows 11, 12, 31, 37).

Its actions had no hover descriptions, a greyed "Unfinished" gave no reason, and "Unfinished" did
nothing at all in every design but Today's app. There was no Help and no About.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QStandardPaths, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFontMetrics, QImage, QRegion
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolTip,
    QWidget,
    QWidgetAction,
)

from desktop.native import settings
from desktop.native.layouts.registry import sanitize_layout
from desktop.native.look import sanitize_look
from desktop.native.tokens import type_pt
from desktop.native.widgets import SHEET_LIST, FitScroll
from desktop.native.window import NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    host,
    qapp,
    server,
    settled,
    signed_out,
    still,
    wait_until,
    window,
)

NOTHING_UNFINISHED = "Nothing is unfinished: no homework from earlier weeks still needs time."
ADDING = {
    "Add homework…": (
        "Add an assignment with its due date and how long it will take. FlexWeek finds time for it."
    ),
    "Add fixed time…": (
        "Add something that happens at a set time, like practice or a lesson. Homework is planned around it."
    ),
    "School hours…": "Set the days and times you are at school, so nothing is planned then.",
}
TOOLTIPS = {
    "Running late": (
        "Behind today? Say how late you are, and FlexWeek moves the rest of today's homework later."
    ),
    "Unfinished": NOTHING_UNFINISHED,
    "Routines": "Save this week's fixed times as a routine, or add a saved routine to a week.",
    "Quick focus": (
        "Open the focus timer, ready to start 30 minutes without picking homework. "
        "Change its length in Settings > Focus."
    ),
    "Replan all my homework": (
        "Find new times for all of this week's homework, as if none had a time yet. Homework you placed "
        "yourself stays put. Use it when your week has changed a lot."
    ),
    "Help": "What each screen is for, and the keyboard shortcuts.",
    "About FlexWeek": "The version, and where your plans are saved.",
    "Sign out": "Sign out on this computer. Your plans stay saved in your account.",
    "Undo": "Nothing to undo yet.",
    "Redo": "Nothing to redo.",
    "Copy": "Copy the selected block to paste into another day. Ctrl+C",
    "Paste into (the selected day)": "Copy a block or a day first.",
    "Duplicate": "Make a copy of the selected block, with a preview first. Ctrl+D",
    "Copy (the selected day)": "Copy every block on the selected day to paste into another day.",
    "Save this week now": "Save now. FlexWeek already saves after every change. Ctrl+S",
    "Copies of this week…": (
        "Save a copy of this week, or go back to an earlier one. FlexWeek keeps a restore point "
        "before big changes."
    ),
    "Reload this week as it is saved": (
        "Load this week again as it is saved. Use it if something looks out of date."
    ),
}
PLAN = (
    "Find a time for homework that has none, around your fixed times and before it is due. Homework "
    "that already has a time keeps it."
)
SUGGEST = "Give homework without a time a suggested time. Drag any of them somewhere else if you like."


def actions(menu: QMenu) -> list[QAction]:
    """What a student can hover: every item with words, submenus opened, headings left out."""
    found = []
    for action in menu.actions():
        if action.isSeparator() or not action.text():
            continue
        if action.menu() is not None:
            found += actions(action.menu())
            continue
        found.append(action)
    return found


def opened_more(window: NativeWindow) -> QMenu:  # noqa: F811
    menu = window.more_button.menu()
    menu.aboutToShow.emit()
    return menu


def test_every_action_under_more_and_advanced_says_what_it_does(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    menu = opened_more(window)
    advanced = next(action.menu() for action in menu.actions() if action.menu() is not None)
    assert menu.toolTipsVisible() and advanced.toolTipsVisible()
    said = {named(action.text()): action.toolTip() for action in actions(menu) if action.isVisible()}
    assert said == TOOLTIPS


def test_the_add_menu_says_what_each_way_to_add_does(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """Adding left More for the Add button's menu, and its descriptions came with it."""
    menu = window.add_menu
    assert menu.toolTipsVisible()
    said = {action.text(): action.toolTip() for action in menu.actions() if action.text() in ADDING}
    assert said == ADDING
    assert window.findChild(QPushButton, "addButton").toolTip() == ADDING["Add homework…"]


def named(text: str) -> str:
    """Copy day and Paste name the selected day, which is today. What follows a tab is a note on the
    row, as Unfinished's reason, not its name."""
    text = text.partition("\t")[0]
    for verb in ("Copy ", "Paste into "):
        if text.startswith(verb):
            return verb + "(the selected day)"
    return text


def test_the_plan_button_and_the_plan_review_say_what_they_do(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    assert window.solve_button.toolTip() == PLAN
    window.session.preferences = {**window.session.preferences, "planning_style": "manual"}
    window._sync_chrome()
    assert window.solve_button.text() == "Suggest times"
    assert window.solve_button.toolTip() == SUGGEST
    assert window.findChild(QPushButton, "planReviewDismiss").toolTip() == "Hide this list."
    assert window.findChild(QPushButton, "planReviewReplan").toolTip() == TOOLTIPS["Replan all my homework"]


def unfinished_action(window: NativeWindow) -> QAction:  # noqa: F811
    return next(action for action in actions(opened_more(window)) if named(action.text()) == "Unfinished")


def test_unfinished_with_nothing_unfinished_is_greyed_and_says_why(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    window.session.save()
    settled(qapp, window)
    action = unfinished_action(window)
    assert action.isEnabled() is False
    assert action.toolTip() == NOTHING_UNFINISHED
    # On the row itself too, for anyone who does not wait for a tooltip (T23 of the 0.17.0 audit).
    assert action.text() == "Unfinished\tNone left"
    window._show_unfinished()
    assert window.toast.text() == NOTHING_UNFINISHED
    assert not window.unfinished_panel.isVisibleTo(window)


def test_unfinished_opens_its_list_in_any_design(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """Homework from last week with two hours still to plan, seen from the week after, in Timeline."""
    session = window.session
    week = date.fromisoformat(session.week_start)
    session.add_block({"id": "school", "title": "School", "kind": "locked", "start": "08:00",
                       "duration_min": 390, "days": [0, 1, 2, 3, 4]})
    session.add_homework({"id": "essay", "title": "History essay", "estimate_min": 120, "revision": 0,
                          "due": (date.today() - timedelta(days=3)).isoformat() + "T12:00"})
    session.save()
    settled(qapp, window)
    planned = next(block for block in session.blocks if block.get("assignment_id") == "essay")
    session.delete_block(planned["id"])
    session.save()
    settled(qapp, window)
    later = (week + timedelta(days=7)).isoformat()
    session.load_week(later)
    wait_until(qapp, lambda: session.week_start == later and not session.busy)
    window.unfinished_panel.hide()
    window._layout = sanitize_layout({"main": "timeline", "day": "one"})
    window._on_week()
    qapp.processEvents()
    action = unfinished_action(window)
    assert action.isEnabled()
    action.trigger()
    qapp.processEvents()
    panel = window.unfinished_panel
    assert panel.isVisibleTo(window), "Timeline showed nothing"
    rows = [label.text() for label in panel.findChildren(QLabel) if label.isVisibleTo(window)]
    assert "History essay · 2 h left" in rows
    assert action.toolTip() == "Homework from earlier weeks that still needs time. Plan it into this week."


def test_unfinished_stays_open_when_the_week_changes_after_it_is_opened(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """Opened from More, the list stayed open only until the next change to the week: a save or a
    reload arriving a moment later folded it back into its badge. It stays open until closed."""
    session = window.session
    week = date.fromisoformat(session.week_start)
    session.add_homework({"id": "essay", "title": "History essay", "estimate_min": 120, "revision": 0,
                          "due": (date.today() - timedelta(days=3)).isoformat() + "T12:00"})
    session.save()
    settled(qapp, window)
    planned = next(block for block in session.blocks if block.get("assignment_id") == "essay")
    session.delete_block(planned["id"])
    session.save()
    settled(qapp, window)
    later = (week + timedelta(days=7)).isoformat()
    session.load_week(later)
    wait_until(qapp, lambda: session.week_start == later and not session.busy)
    window._on_week()
    window.unfinished_panel.hide()
    unfinished_action(window).trigger()
    qapp.processEvents()
    assert window.unfinished_panel.isVisibleTo(window)
    window._on_week()
    qapp.processEvents()
    assert window.unfinished_panel.isVisibleTo(window), "a change to the week closed the list"
    assert not window.unfinished_badge.isVisibleTo(window)


def test_unfinished_is_greyed_when_every_item_is_not_yet_overdue(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#14: Unfinished listed work due today and tomorrow. The button stayed on while the panel
    would be empty. It follows the overdue-only list the panel shows."""
    from datetime import datetime

    from desktop.native import widgets as widgets_module
    from desktop.native import window as window_module

    now = datetime(2026, 10, 3, 18, 0)

    class Clock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return now

    monkeypatch.setattr(widgets_module, "datetime", Clock)
    monkeypatch.setattr(window_module, "datetime", Clock)
    session = window.session
    # Item 1b: the window asks with the session's own clock.
    monkeypatch.setattr(session, "now_ms", lambda: int(now.timestamp() * 1000))
    week = date.fromisoformat(session.week_start)
    session.add_block({"id": "school", "title": "School", "kind": "locked", "start": "08:00",
                       "duration_min": 390, "days": [0, 1, 2, 3, 4]})
    session.add_homework({"id": "essay", "title": "History essay", "estimate_min": 120, "revision": 0,
                          "due": "2026-10-04T15:30"})
    session.save()
    settled(qapp, window)
    planned = next(block for block in session.blocks if block.get("assignment_id") == "essay")
    session.delete_block(planned["id"])
    session.save()
    settled(qapp, window)
    later = (week + timedelta(days=7)).isoformat()
    session.load_week(later)
    wait_until(qapp, lambda: session.week_start == later and not session.busy)
    assert session.unfinished()
    action = unfinished_action(window)
    button = window.findChild(QPushButton, "unfinishedOpen")
    assert action.isEnabled() is False
    assert button is not None and button.isEnabled() is False
    window._show_unfinished()
    assert not window.unfinished_panel.isVisibleTo(window) or window.unfinished_panel.list.count() == 0


def test_about_gives_the_version_what_flexweek_is_and_opens_the_folder_its_data_lives_in(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It showed the folder as a path to read and copy; a student only wants to look inside it."""
    wait_until(qapp, lambda: window.session.storage_info is not None)
    folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    dialog = settings.AboutDialog(window, window.session.storage_info, folder)
    said = [label.text() for label in dialog.findChildren(QLabel) if label.text()]
    assert said == [
        "About FlexWeek",
        "FlexWeek 0.19.0",
        "FlexWeek plans your homework around school, sports and everything else in your week.",
        "Your week is saved on this computer, under this account.",
    ]
    assert dialog.windowTitle() == "About FlexWeek"
    logo = dialog.findChild(QLabel, "aboutLogo")
    assert logo is not None and not logo.pixmap().isNull(), "the logo beside the name"
    assert logo.pixmap().deviceIndependentSize().toSize().width() == settings.ABOUT_LOGO_PX
    opened: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url) or True))
    button = dialog.findChild(QPushButton, "aboutOpenFolder")
    assert button.text() == "Open folder"
    button.click()
    assert opened == [QUrl.fromLocalFile(folder)]


def test_about_on_a_server_names_the_server_and_has_no_folder_to_open(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
) -> None:
    dialog = settings.AboutDialog(host, {"mode": "hosted", "origin": "https://plans.example.org"}, "/nowhere")
    said = [label.text() for label in dialog.findChildren(QLabel)]
    assert said[-1] == (
        "Your week is saved on your FlexWeek server, https://plans.example.org, under this account."
    )
    assert dialog.findChild(QPushButton, "aboutOpenFolder") is None


def test_help_explains_each_screen_and_the_keys_and_promises_nothing(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
) -> None:
    """Its first line was "A tutorial and short guides are coming in a later version" (decision 27)."""
    dialog = settings.HelpDialog(host)
    rows = [row.accessibleName() for row in dialog.findChildren(QWidget, "helpKey")]
    said = "\n".join([*(label.text() for label in dialog.findChildren(QLabel)), *rows])
    assert "tutorial" not in said.lower() and "coming" not in said.lower()
    for line in (
        "Day",
        "One day hour by hour, with homework that is not placed yet beside it, ready to drag in.",
        "Week",
        "Monday to Sunday: drag a block to move it, or drag across empty time to add one.",
        "Month",
        "Each date's blocks and the homework due that day; click a date to open it in Day.",
        "My day",
        "What is on now and what comes next, to follow once your plan is made.",
        "Ctrl+K",
        "Command bar",
        "Focus screen",
        "D W M",
        "Day, Week, Month",
        "Ctrl+Z",
        "Undo",
        "Ctrl+Y or Ctrl+Shift+Z",
        "Esc while dragging",
        "Put the block back where it was",
    ):
        assert line in said, line
    assert dialog.windowTitle() == "Help"


def test_help_draws_each_shortcut_as_keycaps(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
) -> None:
    """Each key its own cap, and the words between keys plain, so Ctrl+K reads as two keys."""
    dialog = settings.HelpDialog(host)
    rows = dialog.findChildren(QWidget, "helpKey")
    said = [settings.keys_words(key) for key, _what in settings.HELP_KEYS]
    assert [row.accessibleName() for row in rows] == said

    def parts(row: QWidget) -> list[tuple[str, str]]:
        return [(label.objectName(), label.text()) for label in row.findChildren(QLabel)]

    assert parts(rows[4]) == [("helpKeycap", "F1")]
    assert parts(rows[5]) == [("helpKeycap", "Ctrl"), ("helpKeyJoin", "+"), ("helpKeycap", "N")]
    assert parts(rows[6]) == [("helpKeycap", "Ctrl"), ("helpKeyJoin", "+"), ("helpKeycap", "K")]
    assert parts(rows[2]) == [("helpKeycap", "B"), ("helpKeyJoin", "or"), ("helpKeycap", "Esc")]
    assert parts(rows[-1]) == [("helpKeycap", "Esc"), ("helpKeyJoin", "while dragging")]


def test_a_sheet_that_scrolls_uses_the_thin_bar_and_gives_its_content_the_full_width(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    assert FitScroll(QWidget(), "probeScroll").verticalScrollBar().property("overlay") is True
    window.resize(1280, 500)
    dialog = settings.HelpDialog(window)
    dialog.show()
    qapp.processEvents()
    area = dialog.findChild(QScrollArea, "helpScroll")
    bar = area.verticalScrollBar()
    assert bar.maximum() > 0, "Help is taller than its room at this height"
    assert bar.property("overlay") is True, "under the app's thin bar"
    assert area.widget().width() == area.viewport().width(), "no thick bar taking width from the words"
    cards = dialog.findChildren(QFrame, "helpCard")
    cards_right = max(card.mapTo(area, card.rect().topRight()).x() for card in cards)
    bar_left = bar.mapTo(area, QPoint(0, 0)).x()
    assert cards_right < bar_left, "the thin bar lies beside the cards, not over them"
    dialog.close()


def test_help_fades_its_words_at_an_edge_with_more_past_it(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    knobs = {**window._look.get("knobs", {}), "text": "large"}
    window._look = sanitize_look({**window._look, "knobs": knobs})
    window._apply_appearance()
    # A sheet is as tall as its window lets it be; in a short one, Help scrolls.
    window.resize(1280, 560)
    dialog = settings.HelpDialog(window)
    dialog.show()
    qapp.processEvents()
    area = dialog.findChild(QScrollArea, "helpScroll")
    bar = area.verticalScrollBar()
    top, bottom = dialog.fades
    assert bar.maximum() > 0, "Help scrolls at this height"
    assert (top.isVisible(), bottom.isVisible()) == (False, True)
    view = area.viewport()
    assert bottom.geometry().bottom() == view.height() - 1 and bottom.width() == view.width()
    # The card's colour: the words fade into the sheet they sit on.
    page = dialog.card.palette().color(dialog.card.backgroundRole())
    # Drawn alone on nothing: over the page itself its last row would be the page with no fade at all.
    fade = QImage(bottom.size(), QImage.Format.Format_ARGB32_Premultiplied)
    fade.fill(0)
    bottom.render(fade, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    last = fade.pixelColor(bottom.width() // 2, bottom.height() - 1)
    # The ramp ends a fraction of a pixel below the last row, which is all but opaque.
    assert last.alpha() >= 240 and last.rgb() == page.rgb(), "faded out to the page"
    bar.setValue(bar.maximum())
    qapp.processEvents()
    assert (top.isVisible(), bottom.isVisible()) == (True, False)
    bar.setValue(bar.maximum() // 2)
    qapp.processEvents()
    assert (top.isVisible(), bottom.isVisible()) == (True, True)
    dialog.close()


def shows_all_of_itself(label: QLabel) -> bool:
    if label.wordWrap():
        return label.height() >= label.heightForWidth(label.width())
    hint = label.sizeHint()
    return label.width() >= hint.width() and label.height() >= hint.height()


def test_help_shows_every_line_whole_at_large_text_and_fits_the_screen(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    knobs = {**window._look.get("knobs", {}), "text": "large"}
    window._look = sanitize_look({**window._look, "knobs": knobs})
    window._apply_appearance()
    dialog = settings.HelpDialog(window)
    dialog.show()
    qapp.processEvents()
    still(dialog)
    labels = dialog.findChildren(QLabel)
    assert len(dialog.findChildren(QWidget, "helpKey")) == len(settings.HELP_KEYS)
    assert [label.text() for label in labels if not shows_all_of_itself(label)] == []
    view = dialog.findChild(QScrollArea, "helpScroll").viewport()
    inside = [label for label in labels if view.isAncestorOf(label)]
    cut = [label.text() for label in inside if label.mapTo(view, label.rect().topRight()).x() > view.width()]
    assert cut == []
    card = dialog.card
    assert window.rect().contains(card.rect().translated(card.mapTo(window, QPoint()))), "inside its window"
    picture = dialog.grab().toImage()
    # Inside a box's edge and below its corner, which a 10-pixel radius rounds away from, against the
    # card's own margin beside it.
    inside = view.parentWidget().mapTo(dialog, QPoint(4, 30))
    margin = dialog.card.mapTo(dialog, QPoint(4, dialog.card.height() // 2))
    assert picture.pixelColor(inside) == picture.pixelColor(margin), "a box around the words"
    dialog.close()


@pytest.mark.parametrize("text", ["normal", "large"])
def test_help_is_a_list_sheet_with_the_screens_two_by_two_above_one_line_per_shortcut(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    text: str,
) -> None:
    """T22 of the 0.17.0 audit: Ctrl+Y or Ctrl+Shift+Z wrapped onto two lines, and the words beside
    the keys wrapped a word or two to a line ("Day, Week," then "Month"). Help is a list's sheet, 600
    wide (5.1 A of 0.17.2): the screens two by two, then each shortcut's keys on one line."""
    knobs = {**window._look.get("knobs", {}), "text": text}
    window._look = sanitize_look({**window._look, "knobs": knobs})
    window._apply_appearance()
    window.resize(1280, 800)
    dialog = settings.HelpDialog(window)
    dialog.show()
    qapp.processEvents()
    still(dialog)
    # 600 at Normal text, growing with Large as every sheet's width does.
    assert dialog.card.width() == round(SHEET_LIST * type_pt("body", text) / type_pt("body"))
    cards = dialog.findChildren(QFrame, "helpCard")
    assert [card.findChild(QLabel, "helpScreenName").text() for card in cards] == [
        name for name, _words in settings.HELP_SCREENS
    ]
    keys = dialog.findChild(QWidget, "helpKeys")
    body = keys.parentWidget()
    tops = sorted({card.mapTo(body, QPoint()).y() for card in cards})
    lefts = sorted({card.mapTo(body, QPoint()).x() for card in cards})
    assert len(tops) == 2 and len(lefts) == 2, "two by two"
    last_bottom = max(card.mapTo(body, card.rect().bottomLeft()).y() for card in cards)
    assert last_bottom < keys.mapTo(body, QPoint()).y(), "the shortcuts under the screens"
    for row in dialog.findChildren(QWidget, "helpKey"):
        caps = row.findChildren(QLabel)
        assert len({cap.mapTo(row, QPoint()).y() for cap in caps}) == 1, f"{row.accessibleName()}: one line"
        assert row.width() >= row.sizeHint().width(), f"{row.accessibleName()}: not squeezed"
    line = QFontMetrics(dialog.findChild(QLabel, "helpKeyDoes").font()).lineSpacing()
    # Badly is a word or two to a line ("Day, Week," then "Month"): each line holds 12 characters or more.
    for words in dialog.findChildren(QLabel, "helpKeyDoes"):
        lines = round(words.height() / line)
        assert lines <= max(1, len(words.text()) // 12), f"{words.text()!r} took {lines} lines"
    labels = dialog.findChildren(QLabel)
    assert [label.text() for label in labels if not shows_all_of_itself(label)] == []
    picture = dialog.grab().toImage()
    between = keys.mapTo(dialog, QPoint(keys.width() - 24, 2))
    margin = dialog.card.mapTo(dialog, QPoint(4, dialog.card.height() // 2))
    assert picture.pixelColor(between) == picture.pixelColor(margin), "the shortcuts sit on the card itself"
    dialog.close()


def test_a_description_is_as_large_as_the_text_the_student_chose(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """At Large the descriptions stayed at the system's small tooltip size."""
    for text in ("normal", "large"):
        knobs = {**window._look.get("knobs", {}), "text": text}
        window._look = sanitize_look({**window._look, "knobs": knobs})
        window._apply_appearance()
        button = window.solve_button
        QToolTip.showText(button.mapToGlobal(QPoint(0, button.height())), button.toolTip(), button)
        qapp.processEvents()
        tip = next(w for w in qapp.topLevelWidgets() if w.objectName() == "qtooltip_label" and w.isVisible())
        assert tip.font().pointSizeF() == type_pt("body", text), text
        # Gone at once, as Qt does when a tip times out: hideText() only hides after a moment, and the
        # same words on the same button again are then taken as the tip already showing, which hides.
        tip.close()
        tip.deleteLater()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_help_and_about_are_under_more(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(settings.HelpDialog, "exec", lambda dialog: opened.append(dialog.windowTitle()) or 0)
    monkeypatch.setattr(settings.AboutDialog, "exec", lambda dialog: opened.append(dialog.windowTitle()) or 0)
    for action in actions(opened_more(window)):
        if action.text() in {"Help", "About FlexWeek"}:
            action.trigger()
    assert opened == ["Help", "About FlexWeek"]


def test_every_row_under_more_has_an_icon_and_log_out_stands_apart(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """Decision 22: icons on the More menu, "Advanced" named for what it holds, and Sign out after a
    line of its own, never with Help and About."""
    from desktop.native.menus import ICON, Menu

    menu = opened_more(window)
    assert isinstance(menu, Menu)
    named = [action for action in menu.actions() if action.text()]
    assert all(action.property(ICON) for action in named), [a.text() for a in named if not a.property(ICON)]
    edits = next(action for action in named if action.menu() is not None)
    assert edits.text() == "Undo, copy and save"
    assert [action.text() for action in edits.menu().actions()][:2] == ["Undo", "Redo"]
    assert all(action.property(ICON) for action in edits.menu().actions())
    rows = [
        action.text() or "---"
        for action in menu.actions()
        if action.isVisible() and not action.menu() and not isinstance(action, QWidgetAction)
    ]
    assert rows[-5:] == ["---", "Help", "About FlexWeek", "---", "Sign out"]
    assert all(action.property(ICON) for action in window.add_menu.actions()[:3]), "the Add menu's three"


def test_more_undo_is_enabled_when_the_toast_offers_undo(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window._set_notice("Planned 1 homework block.", "Undo", lambda: None)
    qapp.processEvents()
    monkeypatch.setattr(window.session, "can_undo", lambda: False)
    menu = opened_more(window)
    undo = next(action for action in actions(menu) if action.text() == "Undo")
    assert undo.isEnabled()
    window.toast.hide()
    qapp.processEvents()
    menu = opened_more(window)
    undo = next(action for action in actions(menu) if action.text() == "Undo")
    assert not undo.isEnabled()
