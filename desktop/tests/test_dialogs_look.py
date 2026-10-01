"""Dialogs in the 0.17 system (decision 23 of docs/0.17/plan.md, look-review.md section 7).

Add homework, Edit event, Routines, Help, About, Running late, School hours, Choose a time and Spread
are sheets inside the window: a card over the dimmed week. Every other dialog stays a window. In each,
the body is the card, not a pale box inside it; a label sits on its field's line of words; every field
of a kind has one width; the repeat scope is a choice of two shown only for a repeating block; a
primary that cannot be pressed yet keeps its colour at 40 %; a list's ticks are the app's check boxes;
and Account is three cards.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QLabel,
    QPushButton,
    QWidget,
)

from desktop.native.look import mix, pack_stylesheet, resolved_palette, sanitize_look
from desktop.native.settings import AboutDialog, AccountDialog, HelpDialog, SettingsPage
from desktop.native.tokens import contrast, type_pt
from desktop.native.widgets import (
    SHEET_FORM,
    SHEET_LIST,
    SHEET_PAD,
    BlockDialog,
    ChooseTimeDialog,
    HomeworkDialog,
    LateDialog,
    RoutineDialog,
    SchoolHoursDialog,
    Segmented,
    SpreadDialog,
    control_art,
)
from desktop.native.window import NativeWindow
from desktop.tests.window_support import free, qapp, server, signed_out, still, window  # noqa: F401

WEEK = "2026-09-21"


def soccer(**fields: object) -> dict:
    return {
        "id": "soccer",
        "title": "Soccer practice",
        "kind": "locked",
        "category": "extra",
        "start": "16:00",
        "duration_min": 90,
        "days": [1, 3],
        **fields,
    }


def styled(qapp: QApplication, pack: str = "light-frost", text: str = "normal") -> tuple[QWidget, dict]:  # noqa: F811
    """A window-sized parent dressed in a look, at a text size, as the app's window is."""
    look = sanitize_look({"knobs": {"text": text}})
    palette = resolved_palette(pack, False, look, "default")
    made = QWidget()
    made.setStyleSheet(pack_stylesheet(pack, False, look, "default", palette, control_art(palette)))
    made.resize(1280, 800)
    made.show()
    qapp.processEvents()
    return made, palette


def shown(qapp: QApplication, dialog: QDialog) -> QDialog:  # noqa: F811
    dialog.show()
    for _ in range(4):
        qapp.processEvents()
    parent = dialog.parentWidget()
    still(dialog, *([parent.window()] if parent is not None else []))
    return dialog


def middle_y(widget: QWidget, within: QWidget) -> int:
    return widget.mapTo(within, QPoint(0, widget.height() // 2)).y()


def near(first: QColor, second: QColor, slack: int = 3) -> bool:
    pairs = zip(first.getRgb()[:3], second.getRgb()[:3], strict=True)
    return all(abs(one - two) <= slack for one, two in pairs)


ESSAY = {"id": "e", "title": "Essay", "due": WEEK, "estimate_min": 60}
WAITING = {"id": "w", "title": "Essay", "duration_min": 60, "days": [1, 2]}


def choose_time(parent: QWidget) -> ChooseTimeDialog:
    return ChooseTimeDialog(parent, WAITING, WEEK, [1, 2], [], None, 1)


def test_the_editors_and_the_seven_others_are_sheets_over_the_dimmed_week(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """Add and Edit were sheets; Routines, Help, About, Running late and School hours were windows of
    their own with title bars, and Running late opened off to one side (T6 and X7 of the 0.17.0
    audit); Choose a time and Spread, opened from the editors, were windows too. Every other dialog
    stays a window."""
    window.resize(1280, 800)
    qapp.processEvents()
    spot = QPoint(20, window.height() - 20)
    before = window.grab().toImage().pixelColor(spot)
    editors = (
        lambda: HomeworkDialog(window, today=WEEK),
        lambda: BlockDialog(window, soccer(), occurrence_day=3),
    )
    others = (
        lambda: RoutineDialog(window, {}, [soccer()], WEEK),
        lambda: HelpDialog(window),
        lambda: AboutDialog(window, {"mode": "local"}, "/nowhere"),
        lambda: LateDialog(window, "Soccer practice"),
        lambda: SchoolHoursDialog(window, None),
        lambda: choose_time(window),
        lambda: SpreadDialog(window, ESSAY, WEEK),
    )
    for make in (*editors, *others):
        dialog = shown(qapp, make())
        name = dialog.windowTitle()
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint, f"{name}: no window frame of its own"
        shade = window.findChild(QWidget, "sheetShade")
        assert shade is not None and shade.isVisible() and shade.geometry() == window.rect(), name
        dimmed = window.grab().toImage().pixelColor(spot)
        assert dimmed.lightness() < 0.75 * before.lightness(), f"{name}: the week behind is dimmed"
        card = dialog.card
        centre = card.mapToGlobal(card.rect().center()) - window.mapToGlobal(window.rect().center())
        assert abs(centre.x()) <= 2 and abs(centre.y()) <= 2, f"{name}: the card is centred on the window"
        on_window = card.rect().translated(card.mapTo(window, QPoint(0, 0)))
        assert window.rect().contains(on_window), f"{name}: the card is inside the window"
        if make in editors:
            assert QApplication.focusWidget() is dialog.title, "typing starts in the title"
            save = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Save")
            assert save.isDefault(), "Enter saves"
        # Still a modal dialog to Qt, so the week's keys wait for it and the rig can find it.
        seen: list[object] = []
        dialog.hide()

        def look_then_close(dialog: QDialog = dialog, seen: list[object] = seen) -> None:
            seen.append(QApplication.activeModalWidget())
            dialog.reject()

        QTimer.singleShot(50, look_then_close)
        dialog.exec()
        assert seen == [dialog], name
        qapp.processEvents()
        assert not any(item.isVisible() for item in window.findChildren(QWidget, "sheetShade"))
        assert window.grab().toImage().pixelColor(spot) == before, f"{name}: the dimming goes with the sheet"
        free(dialog)
    assert window.findChild(QWidget, "sheetShade") is None


@pytest.mark.parametrize("pack", ["light-frost", "dark-frost"])
def test_the_homework_body_is_the_card_not_a_box_inside_it(qapp: QApplication, pack: str) -> None:  # noqa: F811
    """The scrolled body was a pale inset inside a white card inside the window (look review, 7)."""
    parent, _palette = styled(qapp, pack)
    dialog = shown(qapp, HomeworkDialog(parent, today=WEEK))
    card = dialog.card
    picture = dialog.grab().toImage()
    paper = picture.pixelColor(card.mapTo(dialog, QPoint(6, card.height() // 2)))
    body = dialog.findChild(QWidget, "homeworkScroll").widget()
    bare = [
        QPoint(x, y)
        for x in range(4, body.width(), 23)
        for y in range(4, body.height(), 17)
        if body.childAt(QPoint(x, y)) is None and body.visibleRegion().contains(QPoint(x, y))
    ]
    assert len(bare) > 10
    painted = {picture.pixelColor(body.mapTo(dialog, point)).name() for point in bare}
    assert painted == {paper.name()}
    free(dialog)
    free(parent)


def left_x(widget: QWidget, within: QWidget) -> int:
    return widget.mapTo(within, QPoint(0, 0)).x()


def test_a_sheets_labels_sit_above_their_fields_at_one_edge(qapp: QApplication) -> None:  # noqa: F811
    """5.1 A of 0.17.2: each label above its field, so every field starts at the card's one edge.
    Beside them, the labels made a column of their own and each sheet's fields began somewhere else."""
    parent, _palette = styled(qapp)
    block = shown(qapp, BlockDialog(parent, soccer(), occurrence_day=3))
    edge = left_x(block.title, block)
    fields = {
        "Title": block.title,
        "Days": block.day_picker,
        "Apply to": block.scope_choice,
        "Start": block.start,
        "End": block.end,
        "Category": block.category,
        "Spotify link": block.spotify,
    }
    for words, field in fields.items():
        label = next(label for label in block.findChildren(QLabel) if label.text() == words)
        assert label.mapTo(block, QPoint(0, label.height())).y() <= field.mapTo(block, QPoint()).y(), words
        assert left_x(label, block) == left_x(field, block), words
        # End sits beside Start, under its own label; every other field starts at the one edge.
        assert words == "End" or left_x(field, block) == edge, words
    assert block.end.mapTo(block, QPoint()).y() == block.start.mapTo(block, QPoint()).y()
    homework = shown(qapp, HomeworkDialog(parent, today=WEEK))
    due = next(label for label in homework.findChildren(QLabel) if label.text() == "Due")
    assert due.mapTo(homework, QPoint(0, due.height())).y() <= homework.due.date.mapTo(homework, QPoint()).y()
    assert left_x(due, homework) == left_x(homework.due.date, homework) == left_x(homework.title, homework)
    free(block)
    free(homework)
    free(parent)


def test_a_settings_label_sits_beside_its_field_on_its_line_of_words(qapp: QApplication) -> None:  # noqa: F811
    """Settings keeps its labels beside their fields (decision 23 of 0.17), each level with the words in
    its field, not with the field's top edge, 4 pixels above them. A stepped number's label sits on its
    box, between the - and the +."""
    from desktop.native.fields import Stepper

    parent, _palette = styled(qapp)
    page = SettingsPage(parent, {"alarms": []}, {}, {})
    page.resize(1280, 800)
    page.show()
    page.nav.setCurrentRow(2)
    for _ in range(4):
        qapp.processEvents()
    body = page.stack.widget(2).widget()
    for box in (page.work, page.preset_timer, page.long_every):
        field = box.parentWidget() if isinstance(box.parentWidget(), Stepper) else box
        label = field.parentWidget().layout().labelForField(field)
        assert abs(middle_y(label, body) - middle_y(box, body)) <= 1, label.text()
    free(page)
    free(parent)


@pytest.mark.parametrize(
    ("make", "title"),
    [
        (lambda parent: HomeworkDialog(parent, today=WEEK), "Add homework"),
        (lambda parent: HomeworkDialog(parent, {"id": "e", "title": "Essay", "due": WEEK, "estimate_min": 60,
                                                "revision": 1}), "Edit homework"),
        (lambda parent: BlockDialog(parent, day=3, start="17:00"), "New event"),
        (lambda parent: BlockDialog(parent, soccer(), occurrence_day=3), "Edit event"),
    ],
)
def test_a_sheet_says_what_it_is_and_closes_from_its_corner(
    qapp: QApplication,  # noqa: F811
    make: object,
    title: str,
) -> None:
    """T18: no sheet had a title, and one without a window frame had nothing to close it but Cancel."""
    parent, _palette = styled(qapp)
    dialog = shown(qapp, make(parent))
    heading = dialog.findChild(QLabel, "sheetTitle")
    assert heading is not None and heading.text() == title and heading.isVisible()
    close = dialog.findChild(QPushButton, "sheetClose")
    assert close.isVisible() and close.accessibleName() == "Close"
    card = dialog.card
    corner = close.mapTo(card, QPoint(close.width(), 0))
    assert corner.x() > card.width() - 2 * SHEET_PAD and corner.y() < 2 * SHEET_PAD, "top right of the card"
    assert heading.mapTo(card, QPoint(0, heading.height())).y() <= dialog.title.mapTo(card, QPoint()).y()
    close.click()
    assert dialog.result() == QDialog.DialogCode.Rejected and not dialog.isVisible()
    free(dialog)
    free(parent)


@pytest.mark.parametrize(
    ("make", "title", "fields"),
    [
        (choose_time, "Choose a time", {"Day": "day", "Start": "start", "Length": None}),
        (
            lambda parent: SpreadDialog(parent, ESSAY, WEEK),
            "Spread homework",
            {"Sessions of": "session", "Starting": "from_date"},
        ),
    ],
)
def test_choose_a_time_and_spread_are_titled_sheets_with_their_labels_above_their_fields(
    qapp: QApplication,  # noqa: F811
    make: object,
    title: str,
    fields: dict[str, str | None],
) -> None:
    """Both opened from the editors as windows of their own, their labels beside their fields and
    nothing at the top to say what they were or to close them."""
    parent, _palette = styled(qapp)
    dialog = shown(qapp, make(parent))
    heading = dialog.findChild(QLabel, "sheetTitle")
    assert heading is not None and heading.text() == title and heading.isVisible()
    close = dialog.findChild(QPushButton, "sheetClose")
    assert close.isVisible() and close.accessibleName() == "Close"
    card = dialog.card
    corner = close.mapTo(card, QPoint(close.width(), 0))
    assert corner.x() > card.width() - 2 * SHEET_PAD and corner.y() < 2 * SHEET_PAD, "top right of the card"
    edge = left_x(heading, dialog)
    for words, name in fields.items():
        label = next(label for label in dialog.findChildren(QLabel) if label.text() == words)
        field = getattr(dialog, name) if name else next(
            item for item in dialog.findChildren(QLabel) if item is not label and item.text() == "1 h"
        )
        assert label.mapTo(dialog, QPoint(0, label.height())).y() <= field.mapTo(dialog, QPoint()).y(), words
        assert left_x(label, dialog) == left_x(field, dialog) == edge, words
    close.click()
    assert dialog.result() == QDialog.DialogCode.Rejected and not dialog.isVisible()
    free(dialog)
    free(parent)


def test_choose_a_time_and_spread_give_back_what_was_picked_and_esc_cancels(
    qapp: QApplication,  # noqa: F811
) -> None:
    """What the window reads after Choose a time and Spread is the day and minute, and the session
    length and first day, as before they were sheets. Esc is Cancel."""
    from PySide6.QtCore import QDate, QTime

    parent, _palette = styled(qapp)
    chosen = shown(qapp, choose_time(parent))
    assert chosen.choice() == (1, 16 * 60), "opens on today, Tuesday, at 16:00"
    chosen.day.setCurrentIndex(chosen.day.findData(2))
    chosen.start.setTime(QTime(17, 30))
    assert chosen.choice() == (2, 17 * 60 + 30)
    ok = chosen.buttons.button(chosen.buttons.StandardButton.Ok)
    ok.click()
    assert chosen.result() == QDialog.DialogCode.Accepted
    assert chosen.choice() == (2, 17 * 60 + 30)
    free(chosen)
    again = shown(qapp, choose_time(parent))
    QTest.keyClick(again, Qt.Key.Key_Escape)
    assert again.result() == QDialog.DialogCode.Rejected and not again.isVisible()
    free(again)
    spread = shown(qapp, SpreadDialog(parent, {**ESSAY, "unplanned_min": 120}, WEEK))
    assert spread.session_min() == 60 and spread.from_iso() == WEEK
    spread.session.setCurrentIndex(spread.session.findData(90))
    spread.from_date.setDate(QDate(2026, 9, 21))
    assert (spread.session_min(), spread.from_iso()) == (90, "2026-09-21")
    next(item for item in spread.findChildren(QPushButton) if item.text() == "Preview sessions").click()
    assert spread.result() == QDialog.DialogCode.Accepted
    free(spread)
    escaped = shown(qapp, SpreadDialog(parent, ESSAY, WEEK))
    QTest.keyClick(escaped, Qt.Key.Key_Escape)
    assert escaped.result() == QDialog.DialogCode.Rejected and not escaped.isVisible()
    free(escaped)
    free(parent)


def test_a_sheet_short_of_room_scrolls_rather_than_squeezing_its_days(qapp: QApplication) -> None:  # noqa: F811
    """In a short window the block editor scrolls. Its day pills were squeezed to a sliver instead."""
    parent, _palette = styled(qapp)
    parent.resize(1280, 520)
    qapp.processEvents()
    block = shown(qapp, BlockDialog(parent, soccer(), occurrence_day=3))
    assert block.findChild(QWidget, "blockScroll").verticalScrollBar().maximum() > 0, "it does scroll"
    for pill in block.days:
        assert pill.height() >= pill.sizeHint().height(), pill.text()
    free(block)
    free(parent)


def test_routines_and_running_late_fit_a_laptop_window_without_scrolling(
    qapp: QApplication,  # noqa: F811
) -> None:
    """Routines' lists took the height they liked, so Apply was below the sheet; Running late left an
    empty line for its summary before there was one."""
    parent, _palette = styled(qapp)
    saved = {"r": {"id": "r", "name": "School week", "blocks": [soccer()]}}
    routines = shown(qapp, RoutineDialog(parent, saved, [soccer()], WEEK))
    area = routines.findChild(QWidget, "routineScroll")
    assert area.verticalScrollBar().maximum() == 0, "everything shows at once"
    late = shown(qapp, LateDialog(parent, "School"))
    assert late.summary.isHidden()
    late.show_trace({"moves": [], "unplaced": []}, {})
    assert not late.summary.isHidden()
    free(routines)
    free(late)
    free(parent)


@pytest.mark.parametrize("text", ["normal", "large"])
def test_sheets_are_one_width_on_a_scale_of_two(qapp: QApplication, text: str) -> None:  # noqa: F811
    """T18: every sheet was its own width. Forms are 440 pixels wide and lists 600, at any text size."""
    parent, _palette = styled(qapp, text=text)
    for make, width in (
        (lambda: HomeworkDialog(parent, today=WEEK), SHEET_FORM),
        (lambda: BlockDialog(parent, soccer(), occurrence_day=3), SHEET_FORM),
        (lambda: BlockDialog(parent, day=3, start="17:00"), SHEET_FORM),
        (lambda: SchoolHoursDialog(parent, None), SHEET_FORM),
        (lambda: LateDialog(parent, "Starting from 15:40 today (Thursday)."), SHEET_FORM),
        (lambda: choose_time(parent), SHEET_FORM),
        (lambda: SpreadDialog(parent, ESSAY, WEEK), SHEET_FORM),
        (lambda: AboutDialog(parent, {"mode": "local"}, "/nowhere"), SHEET_FORM),
        (lambda: RoutineDialog(parent, {}, [soccer()], WEEK), SHEET_LIST),
        (lambda: HelpDialog(parent), SHEET_LIST),
    ):
        dialog = shown(qapp, make())
        # At Large the scale grows with the text, 13 points to 15.
        scaled = round(width * type_pt("body", text) / type_pt("body"))
        assert dialog.card.width() == scaled, dialog.windowTitle()
        assert dialog.card.minimumSizeHint().width() <= scaled, f"{dialog.windowTitle()}: nothing cut to fit"
        free(dialog)
    free(parent)


def test_every_field_of_a_kind_has_one_width(qapp: QApplication) -> None:  # noqa: F811
    """Start and End were 420 pixels for five characters; the due date 200 in a 340-pixel column."""
    parent, _palette = styled(qapp)
    block = shown(qapp, BlockDialog(parent, soccer(), occurrence_day=3))
    assert block.start.width() == block.end.width()
    assert block.start.width() < block.title.width() // 2, "a time box is as wide as a time"
    assert block.category.width() < block.title.width(), "a dropdown is as wide as its longest choice"
    free(block)
    free(parent)


def test_the_repeat_scope_is_a_choice_of_two_under_the_days_only_for_a_repeating_block(
    qapp: QApplication,  # noqa: F811
) -> None:
    parent, _palette = styled(qapp)
    one_day = shown(qapp, BlockDialog(parent, soccer(), occurrence_day=3))
    scope = one_day.findChild(Segmented, "editScope")
    assert scope.isVisibleTo(one_day)
    assert [button.text() for button in scope.buttons()] == ["This day only", "Every selected day"]
    assert one_day.findChildren(QCheckBox, "scopeOccurrence") == [], "no radio buttons over the title"
    assert middle_y(scope, one_day) > middle_y(one_day.days[0], one_day), "under the days"
    assert middle_y(scope, one_day) > middle_y(one_day.title, one_day)
    scope.buttons()[0].click()
    assert one_day.scope() == "occurrence"
    for other in (
        BlockDialog(parent, soccer(days=[3]), occurrence_day=3),
        BlockDialog(parent, day=3, start="17:00"),
        BlockDialog(parent, soccer()),
    ):
        shown(qapp, other)
        assert not other.findChild(Segmented, "editScope").isVisibleTo(other)
        free(other)
    free(one_day)
    free(parent)


@pytest.mark.parametrize("pack", ["light-frost", "dark-frost"])
def test_a_primary_that_cannot_be_pressed_yet_keeps_its_colour_at_40_percent_and_reads(
    qapp: QApplication,  # noqa: F811
    pack: str,
) -> None:
    """Running late's Accept was a grey slab until Preview, and looked broken; then its words were the
    accent's ink at 40 % on the 40 % fill, and could not be read (T6 of the 0.17.0 audit)."""
    parent, palette = styled(qapp, pack)
    late = shown(qapp, LateDialog(parent, "School"))
    button = late.accept_button

    def picture() -> QImage:
        return late.grab().toImage()

    def fill() -> QColor:
        return picture().pixelColor(button.mapTo(late, QPoint(button.width() // 2, 4)))

    assert near(fill(), QColor(mix(palette["accent"], palette["panel"], 0.4)))
    ground = fill().name()
    image = picture()
    corner = button.mapTo(late, QPoint(0, 0))
    words = max(
        (
            image.pixelColor(corner.x() + x, corner.y() + y).name()
            for x in range(button.width())
            for y in range(button.height())
        ),
        key=lambda colour: contrast(colour, ground),
    )
    assert contrast(words, ground) >= 4.5, f"{words} on {ground}"
    late.show_trace({"moves": [], "unplaced": []}, {})
    qapp.processEvents()
    assert near(fill(), QColor(palette["accent"]))
    free(late)
    free(parent)


def test_a_lists_ticks_are_the_apps_check_boxes(qapp: QApplication) -> None:  # noqa: F811
    """Routines ticked its fixed times with Qt's own marks beside the app's accent boxes."""
    parent, palette = styled(qapp)
    routines = shown(qapp, RoutineDialog(parent, {}, [soccer()], WEEK))
    listed = routines.choices
    row = listed.visualItemRect(listed.item(0))
    picture = listed.viewport().grab().toImage()
    accent = QColor(palette["accent"])
    ticked = sum(
        near(picture.pixelColor(x, y), accent, 2)
        for x in range(row.left(), row.left() + 30)
        for y in range(row.top(), row.bottom())
    )
    assert ticked > 40, "the tick's box is filled in the accent"
    free(routines)
    free(parent)


def test_account_is_three_cards_each_with_its_own_actions(qapp: QApplication) -> None:  # noqa: F811
    parent, palette = styled(qapp)
    account = shown(qapp, AccountDialog(parent, 8, {"username": "maya_r"}))
    found = account.findChildren(QFrame, "dialogCard")
    cards = {card.findChild(QLabel, "cardTitle").text(): card for card in found}
    assert list(cards) == ["Password", "Recovery codes", "Your data"]
    holds = {
        "Password": ("currentPassword", "newPassword", "changePassword"),
        "Recovery codes": ("recoveryCount", "replaceCodes"),
        "Your data": (
            "exportAccount", "importAccount", "exportWeek", "exportDay", "importFile", "deleteAccount",
        ),
    }
    for title, names in holds.items():
        for name in names:
            assert cards[title].findChild(QWidget, name) is not None, (title, name)
    delete = account.findChild(QPushButton, "deleteAccount")
    picture = delete.grab().toImage()
    red = QColor(palette["error"])
    assert any(
        near(picture.pixelColor(x, y), red, 30) for x in range(delete.width()) for y in range(delete.height())
    ), "deleting is said in red"
    loud = [
        button.objectName()
        for button in account.findChildren(QPushButton)
        if not button.property("quiet") and button.objectName() not in {"deleteAccount", ""}
    ]
    assert loud == ["changePassword"]
    free(account)
    free(parent)
