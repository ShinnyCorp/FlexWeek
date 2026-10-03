"""Sheets in 0.18.1: the seven dialogs that were windows of their own, and what shares their shape
(#49, #34, #70, #48, #91, #79, #50, #76).

Each of the seven opens inside its window as a sheet, Esc closes it, and focus goes back to where it was.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
)

from desktop.native import window as window_module
from desktop.native.look import ACCENT_COLORS, ACCENTS, CONFLICT_FILL, CONFLICT_TEXT
from desktop.native.look_editor import (
    LEAVE_TITLE,
    PICKER_HUES,
    ColourField,
    ColourSheet,
    leave_sheet,
)
from desktop.native.settings import AccountDialog
from desktop.native.tokens import contrast
from desktop.native.widgets import (
    ChooseTimeDialog,
    ConfirmSheet,
    Dialog,
    HomeworkDialog,
    LateDialog,
    PreviewDialog,
    UnfinishedPanel,
    confirm,
)
from desktop.native.window import NativeWindow
from desktop.tests.test_dialogs_look import WEEK, near, shown, soccer, styled
from desktop.tests.test_look_editor import open_editor
from desktop.tests.window_support import (  # noqa: F401
    free,
    qapp,
    server,
    signed_out,
    still,
    wait_until,
    window,
)


def settle_layout(qapp: QApplication) -> None:  # noqa: F811
    """The dialog sizes itself again after the style sheet and each change arrive, on the next turn of
    the event loop."""
    for _ in range(6):
        qapp.processEvents()


# The seven dialogs that were windows of their own, and the Add homework sheet's size (#34).


def test_add_homework_grows_to_90_percent_of_the_window_before_it_scrolls(
    qapp: QApplication,  # noqa: F811
) -> None:
    """#34: ticking "At a set time" put a second scroll bar inside the sheet and cut Finished and More
    details. A sheet is as tall as its content up to 90 % of its window, and only past that scrolls."""
    parent, _palette = styled(qapp)
    dialog = shown(qapp, HomeworkDialog(parent, today=WEEK))
    area = dialog.findChild(QScrollArea, "homeworkScroll")
    dialog.findChild(QCheckBox, "homeworkDueTimed").setChecked(True)
    settle_layout(qapp)
    assert area.verticalScrollBar().maximum() == 0, "nothing to scroll while the content fits"
    viewport = area.viewport().rect()
    for name in ("homeworkCompleted", "homeworkMoreDetails"):
        field = dialog.findChild(QWidget, name)
        spot = field.mapTo(area.viewport(), QPoint(0, 0))
        assert viewport.contains(spot) and viewport.contains(spot + QPoint(0, field.height() - 1)), name
    assert dialog.card.height() <= 0.9 * parent.height()
    free(dialog)
    free(parent)


def test_add_homework_with_its_details_open_is_90_percent_of_the_window_and_then_scrolls(
    qapp: QApplication,  # noqa: F811
) -> None:
    parent, _palette = styled(qapp)
    dialog = shown(qapp, HomeworkDialog(parent, today=WEEK))
    dialog.findChild(QCheckBox, "homeworkDueTimed").setChecked(True)
    dialog.more_details.setChecked(True)
    settle_layout(qapp)
    area = dialog.findChild(QScrollArea, "homeworkScroll")
    assert area.verticalScrollBar().maximum() > 0, "more than 90 % of a 800 pixel window's height"
    assert abs(dialog.card.height() - 0.9 * parent.height()) <= 2
    free(dialog)
    free(parent)


def test_add_homeworks_answers_sit_in_a_footer_under_a_thin_divider(qapp: QApplication) -> None:  # noqa: F811
    """#34: Save and Cancel are outside the scrolled body, under a 1 pixel line across the card."""
    parent, _palette = styled(qapp)
    dialog = shown(qapp, HomeworkDialog(parent, today=WEEK))
    line = dialog.findChild(QFrame, "sheetFooterLine")
    area = dialog.findChild(QScrollArea, "homeworkScroll")
    assert line is not None and line.isVisible() and line.height() == 1
    assert line.width() == area.width(), "across the card's content, as wide as the body above it"
    buttons = dialog.findChild(QWidget, "dialogButtons")
    assert area.mapTo(dialog, QPoint(0, area.height())).y() <= line.mapTo(dialog, QPoint(0, 0)).y()
    assert line.mapTo(dialog, QPoint(0, 1)).y() <= buttons.mapTo(dialog, QPoint(0, 0)).y()
    assert not area.isAncestorOf(buttons)
    free(dialog)
    free(parent)


# Every sheet: inside its window, closed by Esc, focus given back.

PREVIEW_ROWS = [
    {
        "block": {
            "id": "b0",
            "title": "History essay",
            "kind": "flexible",
            "days": [0],
            "start": "16:00",
            "duration_min": 60,
            "category": "assignments",
        },
        "day": 0,
        "fixed": False,
        "checked": True,
    }
]


def sheet_over(window: NativeWindow, sheet: QWidget, title: str) -> None:  # noqa: F811
    """What every sheet is: a frameless dialog over a dimmed window, its card inside the window, and no
    framed dialog of the system's beside it."""
    assert isinstance(sheet, Dialog) and sheet.sheet, "a sheet, not a window"
    assert sheet.windowFlags() & Qt.WindowType.FramelessWindowHint
    shade = window.findChild(QWidget, "sheetShade")
    assert shade is not None and shade.isVisible() and shade.geometry() == window.rect()
    heading = sheet.findChild(QLabel, "sheetTitle")
    assert heading is not None and heading.text() == title and heading.isVisible()
    assert sheet.findChild(QPushButton, "sheetClose").isVisible()
    # Globally: a sheet opened from a field is a child of that field, not of the window.
    corner = sheet.card.mapToGlobal(QPoint(0, 0)) - window.mapToGlobal(QPoint(0, 0))
    assert window.rect().contains(QRect(corner, sheet.card.size())), "the card is inside the window"
    framed = [
        dialog
        for dialog in window.findChildren(QDialog)
        if dialog.isVisible() and not dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    ]
    assert framed == [], "no dialog with a window frame of its own"


def escape_closes(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    launch: Callable[[], object],
    title: str,
    anchor: QWidget,
    during: Callable[[Dialog], None] | None = None,
) -> object:
    """Open the sheet with `launch`, check it is a sheet of `title` over `window`, press Esc, and check
    it closed unanswered, the dimming went, and focus is back on `anchor`."""
    window.resize(1280, 800)
    window.activateWindow()
    qapp.processEvents()
    anchor.setFocus()
    qapp.processEvents()
    assert QApplication.focusWidget() is anchor
    seen: dict[str, object] = {}

    def inside() -> None:
        sheet = QApplication.activeModalWidget()
        seen["sheet"] = sheet
        try:
            sheet_over(window, sheet, title)
            if during is not None:
                during(sheet)
        except BaseException as error:  # noqa: BLE001 - re-raised below, outside Qt's event loop
            seen["error"] = error
        QTest.keyClick(sheet, Qt.Key.Key_Escape)

    QTimer.singleShot(200, inside)
    result = launch()
    if "error" in seen:
        raise seen["error"]  # type: ignore[misc]
    sheet = seen["sheet"]
    assert sheet.result() == QDialog.DialogCode.Rejected and not sheet.isVisible()
    qapp.processEvents()
    assert not any(shade.isVisible() for shade in window.findChildren(QWidget, "sheetShade"))
    assert QApplication.focusWidget() is anchor, "focus is back where it was"
    return result


def week_anchor(window: NativeWindow) -> QWidget:  # noqa: F811
    return window.findChild(QPushButton, "todayWeek")


def test_availability_is_a_sheet_that_esc_closes(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    escape_closes(qapp, window, window._open_availability, "Availability", week_anchor(window))


def test_plan_unfinished_homework_is_a_sheet_that_esc_closes(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    def launch() -> None:
        window._show_preview(
            "Plan unfinished homework",
            "History essay keeps its original deadline and progress.",
            PREVIEW_ROWS,
            label="unfinished homework",
        )

    escape_closes(qapp, window, launch, "Plan unfinished homework", week_anchor(window))


def test_manage_account_is_a_sheet_that_esc_closes(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    escape_closes(qapp, window, window._open_account, "Manage account", week_anchor(window))


def test_the_sign_out_question_is_a_sheet_that_esc_closes_and_stays_signed_in(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    button = window.findChild(QPushButton, "signOut")
    escape_closes(qapp, window, button.click, "Sign out", week_anchor(window))
    assert window.session.account is not None


def test_saving_the_recovery_codes_starts_on_a_sheet_and_esc_never_reaches_the_file_dialog(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def never() -> str:
        raise AssertionError("the file dialog opened")

    monkeypatch.setattr(window, "_pick_recovery_file", never)
    path = escape_closes(
        qapp, window, window._choose_recovery_file, "Save recovery codes", week_anchor(window)
    )
    assert path == ""


def test_the_accent_picker_is_a_sheet_that_esc_closes_and_puts_the_colour_back(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    _page, editor = open_editor(qapp, window)
    field = editor.findChild(ColourField, "lookColour-accent")
    tried: list[str] = []
    field.picked.connect(tried.append)
    before = field._colour

    def try_one(sheet: Dialog) -> None:
        sheet.dots[6].click()

    escape_closes(qapp, window, field.swatch.click, "Any colour", field.swatch, try_one)
    assert tried[-1] == before and tried[0] == PICKER_HUES[1], "tried live, then put back"


def test_leaving_the_look_editor_asks_on_a_sheet_that_esc_closes_and_stays(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    _page, editor = open_editor(qapp, window)
    answer = escape_closes(qapp, window, editor.ask_leave, LEAVE_TITLE, editor.back)
    assert answer is None, "Esc stays in the editor"


# What is on each sheet.


def test_the_leave_sheet_has_a_filled_save_an_outlined_red_discard_and_quiet_cancel_and_keep(
    qapp: QApplication,  # noqa: F811
) -> None:
    parent, palette = styled(qapp)
    sheet = shown(qapp, leave_sheet(parent, "Evening", True))
    save, discard = sheet.buttons["save"], sheet.buttons["discard"]
    assert [button.text() for button in sheet.buttons.values()] == [
        "Cancel",
        "Discard changes",
        "Save",
        "Keep without saving",
    ]
    assert save.isDefault() and not save.property("outlined") and not save.property("quiet")
    assert discard.property("outlined") and discard.property("danger")
    assert sheet.buttons["stay"].property("quiet") and sheet.buttons["keep"].property("quiet")
    picture = discard.grab().toImage()
    red = QColor(palette["error"])
    assert any(near(picture.pixelColor(discard.width() // 2, y), red, 30) for y in (0, 1)), (
        "its edge is the error colour"
    )
    free(sheet)
    free(parent)


@pytest.mark.parametrize("text", ["normal", "large"])
def test_the_leave_sheets_four_answers_all_fit_their_words(
    qapp: QApplication,  # noqa: F811
    text: str,
) -> None:
    parent, _palette = styled(qapp, text=text)
    sheet = shown(qapp, leave_sheet(parent, "Evening", True))
    for key, button in sheet.buttons.items():
        assert button.width() >= button.sizeHint().width(), f"{key} is squeezed"
        assert button.width() >= button.fontMetrics().horizontalAdvance(button.text()), key
    free(sheet)
    free(parent)


@pytest.mark.parametrize(
    ("key", "expected"), [("save", "save"), ("keep", "keep"), ("discard", "discard"), ("stay", None)]
)
def test_each_answer_on_the_leave_sheet_is_the_one_the_editor_gets(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    key: str,
    expected: str | None,
) -> None:
    _page, editor = open_editor(qapp, window)
    QTimer.singleShot(200, lambda: QApplication.activeModalWidget().buttons[key].click())
    assert editor.ask_leave() == expected


def test_the_accent_picker_offers_the_five_accents_then_a_dozen_hues_and_a_code(
    qapp: QApplication,  # noqa: F811
) -> None:
    parent, _palette = styled(qapp)
    picker = shown(qapp, ColourSheet(parent, "#3d6fc4"))
    assert len(picker.dots) == 5 + 12 == len(ACCENTS) + len(PICKER_HUES)
    named = [dot.fill for dot in picker.dots[:5]]
    assert named == [ACCENT_COLORS[name]["light"][0] for name in ACCENTS], "the named accents first"
    assert [dot.fill for dot in picker.dots[5:]] == list(PICKER_HUES)
    assert picker.dots[0].isChecked() and picker.code.text() == "#3d6fc4"
    heard: list[str] = []
    picker.picked.connect(heard.append)
    picker.dots[7].click()
    assert heard == [PICKER_HUES[2]] and picker.colour() == PICKER_HUES[2]
    assert picker.code.text() == PICKER_HUES[2] and PICKER_HUES[2] in picker.chip.styleSheet()
    assert picker.dots[7].isChecked() and not picker.dots[0].isChecked()
    free(picker)
    free(parent)


def test_the_accent_pickers_code_box_takes_a_typed_colour_and_says_why_it_will_not_use_a_bad_one(
    qapp: QApplication,  # noqa: F811
) -> None:
    parent, _palette = styled(qapp)
    picker = shown(qapp, ColourSheet(parent, "#3d6fc4"))
    hint = picker.findChild(QLabel, "whyOff")
    assert picker.use.isEnabled() and not hint.isVisible()
    heard: list[str] = []
    picker.picked.connect(heard.append)
    picker.code.setText("#12")
    picker.code.textEdited.emit("#12")
    assert not picker.use.isEnabled() and hint.isVisible() and heard == []
    picker.code.setText("#c0392b")
    picker.code.textEdited.emit("#c0392b")
    assert picker.use.isEnabled() and not hint.isVisible()
    assert heard == ["#c0392b"] and picker.dots[5].isChecked(), "the matching swatch is ringed"
    free(picker)
    free(parent)


def test_use_this_colour_keeps_the_colour_and_cancel_puts_the_first_back(
    qapp: QApplication,  # noqa: F811
) -> None:
    parent, _palette = styled(qapp)
    field = ColourField("Accent")
    field.setParent(parent)
    field.show()
    field.show_colour("#3d6fc4")
    heard: list[str] = []
    field.picked.connect(heard.append)

    def pick_then(answer: str) -> None:
        sheet = QApplication.activeModalWidget()
        sheet.dots[9].click()
        sheet.findChild(QPushButton, answer).click()

    QTimer.singleShot(200, lambda: pick_then("colourUse"))
    field.swatch.click()
    assert heard[-1] == PICKER_HUES[4]
    heard.clear()
    QTimer.singleShot(200, lambda: pick_then("colourCancel"))
    field.swatch.click()
    assert heard[-1] == "#3d6fc4"
    free(field)
    free(parent)


def test_the_sign_out_sheet_says_where_the_week_lives_and_does_not_draw_sign_out_red(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, str, str, bool]] = []

    def confirm_it(_parent: object, title: str, question: str, yes: str, *, danger: bool = True) -> bool:
        asked.append((title, question, yes, danger))
        return False

    monkeypatch.setattr(window_module, "confirm", confirm_it)
    wait_until(qapp, lambda: window.session.storage_info is not None)
    window.findChild(QPushButton, "signOut").click()
    assert asked == [
        ("Sign out", "Your week stays saved on this computer. Sign in again to see it.", "Sign out", False)
    ]
    window.session.storage_info = {"mode": "hosted"}
    window.findChild(QPushButton, "signOut").click()
    assert asked[-1][1] == "Your week stays saved on your FlexWeek server. Sign in again to see it."


def test_the_app_says_sign_out_and_never_log_out(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    """#76: the top bar's button, and the Manage account note about the codes."""
    assert window.findChild(QPushButton, "signOut").text() == "Sign out"
    account = AccountDialog(window, 0, {"username": "student"})
    assert account.findChild(QLabel, "recoveryCount").text() == (
        "No unused recovery codes remain. Replace them before signing out."
    )
    free(account)


def test_a_confirmation_is_a_sheet_whose_default_is_cancel_and_whose_answer_is_red_only_when_it_destroys(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    pack, dark, accent = window._look_inputs()
    from desktop.native.look import resolved_palette

    red = QColor(resolved_palette(pack, dark, window._look, accent)["error"])
    for danger in (True, False):
        answers = (("stay", "Cancel", "outlined"), ("yes", "Delete", "danger" if danger else ""))
        sheet = ConfirmSheet(window, "Delete event", "Delete Soccer?", answers, default="stay")
        shown(qapp, sheet)
        assert sheet.buttons["stay"].isDefault() and not sheet.buttons["yes"].isDefault()
        picture = sheet.grab().toImage()
        yes = sheet.buttons["yes"]
        at = yes.mapTo(sheet, QPoint(yes.width() // 2, 4))
        assert near(picture.pixelColor(at.x(), at.y()), red, 2) == danger
        QTest.keyClick(sheet, Qt.Key.Key_Escape)
        assert sheet.answer is None and sheet.result() == QDialog.DialogCode.Rejected
        free(sheet)


def test_confirm_answers_true_only_for_the_yes_button(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    QTimer.singleShot(200, lambda: QApplication.activeModalWidget().buttons["yes"].click())
    assert confirm(window, "Sign out", "Sure?", "Sign out", danger=False) is True
    QTimer.singleShot(200, lambda: QApplication.activeModalWidget().buttons["stay"].click())
    assert confirm(window, "Sign out", "Sure?", "Sign out", danger=False) is False


def test_the_recovery_file_sheet_says_to_keep_it_private_then_opens_the_file_dialog_on_documents(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#50: the sheet comes first, and the system's file dialog starts in Documents."""
    from PySide6.QtCore import QStandardPaths

    asked: list[str] = []

    def answer(_parent: object, _caption: str, start: str, _kinds: str) -> tuple[str, str]:
        asked.append(start)
        return "/somewhere/codes.txt", ""

    monkeypatch.setattr(window_module.QFileDialog, "getSaveFileName", staticmethod(answer))
    said: list[str] = []

    def choose() -> None:
        sheet = QApplication.activeModalWidget()
        said.append(sheet.question.text())
        sheet.buttons["choose"].click()

    QTimer.singleShot(200, choose)
    assert window._choose_recovery_file() == "/somewhere/codes.txt"
    assert said[0].startswith("Keep this file somewhere private")
    documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    assert asked == [f"{documents}/flexweek-recovery-codes.txt"]


# Manage account (#70).


@pytest.mark.parametrize("text", ["normal", "large"])
def test_manage_account_puts_each_label_above_its_field_and_shows_delete_whole(
    qapp: QApplication,  # noqa: F811
    text: str,
) -> None:
    """#70: New password was drawn over Current password, and a red action was cut off."""
    parent, palette = styled(qapp, text=text)
    account = shown(qapp, AccountDialog(parent, 8, {"username": "maya_r"}))

    def box(widget: QWidget) -> QRect:
        return QRect(widget.mapTo(account, QPoint(0, 0)), widget.size())

    label = next(item for item in account.findChildren(QLabel) if item.text() == "New password")
    current_label = next(item for item in account.findChildren(QLabel) if item.text() == "Current password")
    assert box(current_label).bottom() < box(account.current_password).top()
    assert box(account.current_password).bottom() < box(label).top() < box(account.new_password).top()
    assert not box(account.current_password).intersects(box(account.new_password))
    area = account.findChild(QScrollArea, "accountScroll")
    area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
    settle_layout(qapp)
    delete = account.findChild(QPushButton, "deleteAccount")
    assert area.viewport().rect().contains(QRect(delete.mapTo(area.viewport(), QPoint(0, 0)), delete.size()))
    assert delete.height() >= delete.sizeHint().height() and delete.width() >= delete.sizeHint().width()
    assert delete.property("outlined") and delete.property("danger")
    picture = delete.grab().toImage()
    assert near(picture.pixelColor(delete.width() // 2, 0), QColor(palette["error"]), 12), "its edge is red"
    footer = account.findChild(QFrame, "sheetFooterLine")
    assert footer is not None and footer.height() == 1
    free(account)
    free(parent)


def test_manage_account_keeps_one_filled_button_and_its_actions(qapp: QApplication) -> None:  # noqa: F811
    parent, _palette = styled(qapp)
    account = shown(qapp, AccountDialog(parent, 8, {"username": "maya_r"}))
    for name in (
        "currentPassword",
        "newPassword",
        "changePassword",
        "recoveryCount",
        "replaceCodes",
        "exportAccount",
        "importAccount",
        "exportWeek",
        "exportDay",
        "importFile",
        "deleteAccount",
    ):
        assert account.findChild(QWidget, name) is not None, name
    loud = [
        button.objectName()
        for button in account.findChildren(QPushButton)
        if not (button.property("quiet") or button.property("outlined")) and button.objectName() != ""
    ]
    assert loud == ["changePassword"]
    free(account)
    free(parent)


# #48, the conflict line of Choose a time.


@pytest.mark.parametrize("pack", ["light-frost", "dark-frost"])
def test_choose_a_times_conflict_line_is_the_amber_row_with_a_warning_mark(
    qapp: QApplication,  # noqa: F811
    pack: str,
) -> None:
    parent, _palette = styled(qapp, pack)
    waiting = {"id": "w", "title": "Essay", "duration_min": 60, "days": [1, 2]}
    sheet = shown(qapp, ChooseTimeDialog(parent, waiting, WEEK, [1, 2], [soccer()], None, 1))
    row = sheet.beside_row
    assert row.objectName() == "conflictRow" and row.isVisible()
    assert sheet.beside.text() == "Soccer practice is at that time too. Both will show, side by side."
    picture = sheet.grab().toImage()
    spot = row.mapTo(sheet, QPoint(row.width() - 6, row.height() // 2))
    assert near(picture.pixelColor(spot), QColor(CONFLICT_FILL), 2), picture.pixelColor(spot).name()
    sheet.beside.ensurePolished()
    assert sheet.beside.palette().color(sheet.beside.foregroundRole()).name() == CONFLICT_TEXT
    assert contrast(CONFLICT_TEXT, CONFLICT_FILL) >= 7
    mark = row.findChild(QLabel, "conflictMark")
    assert mark is not None and not mark.pixmap().isNull(), "a warning mark, drawn as the app's icons are"
    sheet.day.setCurrentIndex(sheet.day.findData(2))
    settle_layout(qapp)
    assert not row.isVisible(), "no clash, no row"
    free(sheet)
    free(parent)


# #91, a main button that is off says so and still reads.


def label_and_fill(widget: QWidget, button: QPushButton) -> tuple[str, str]:
    """The strongest colour and the fill of `button`, read off a picture of `widget`."""
    image = widget.grab().toImage()
    corner = button.mapTo(widget, QPoint(0, 0))
    fill = image.pixelColor(corner.x() + button.width() // 2, corner.y() + 4).name()
    words = max(
        (
            image.pixelColor(corner.x() + x, corner.y() + y).name()
            for x in range(button.width())
            for y in range(button.height())
        ),
        key=lambda colour: contrast(colour, fill),
    )
    return words, fill


def test_continue_to_my_week_is_pale_with_its_words_at_7_to_1_and_a_line_saying_why(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    window._show_recovery(["aaaa-bbbb", "cccc-dddd"])
    for _ in range(4):
        qapp.processEvents()
    still(window)
    button = window.recovery_continue
    hint = window.findChild(QLabel, "whyOff")
    assert not button.isEnabled() and hint.isVisible() and hint.text() == "Tick the box above to continue."
    words, fill = label_and_fill(window, button)
    assert contrast(words, fill) >= 7.0, f"{words} on {fill}"
    window.recovery_ack.setChecked(True)
    qapp.processEvents()
    assert button.isEnabled() and not hint.isVisible()


def test_running_lates_accept_says_to_preview_first_and_is_roomy(
    qapp: QApplication,  # noqa: F811
) -> None:
    parent, _palette = styled(qapp)
    late = shown(qapp, LateDialog(parent, "School"))
    hint = late.findChild(QLabel, "whyOff")
    assert not late.accept_button.isEnabled() and hint.isVisible()
    words, fill = label_and_fill(late, late.accept_button)
    assert contrast(words, fill) >= 7.0
    late.show_trace({"moves": [], "unplaced": []}, {})
    settle_layout(qapp)
    assert late.accept_button.isEnabled() and not hint.isVisible()
    free(late)
    free(parent)


@pytest.mark.parametrize(("text", "least"), [("normal", 36), ("large", 40)])
def test_accept_late_start_is_as_wide_as_its_words_and_20_pixels_each_side(
    qapp: QApplication,  # noqa: F811
    text: str,
    least: int,
) -> None:
    """#79: "Accept late start" was too narrow for its words."""
    parent, _palette = styled(qapp, text=text)
    late = shown(qapp, LateDialog(parent, "School"))
    accept = late.accept_button
    words = accept.fontMetrics().horizontalAdvance(accept.text())
    assert accept.width() >= words + 40
    assert accept.height() >= least and accept.height() - accept.fontMetrics().height() >= 16
    free(late)
    free(parent)


def test_the_preview_save_is_off_with_a_line_saying_why_until_something_is_ticked(
    qapp: QApplication,  # noqa: F811
) -> None:
    parent, _palette = styled(qapp)
    rows = [{**PREVIEW_ROWS[0], "checked": False}]
    preview = shown(qapp, PreviewDialog(parent, "Paste", "", rows, []))
    hint = preview.findChild(QLabel, "whyOff")
    assert not preview.confirm.isEnabled() and hint.isVisible()
    assert hint.text() == "Select at least one item before saving."
    words, fill = label_and_fill(preview, preview.confirm)
    assert contrast(words, fill) >= 7.0
    preview.findChild(QCheckBox, "previewInclude0").setChecked(True)
    settle_layout(qapp)
    assert preview.confirm.isEnabled() and not hint.isVisible()
    free(preview)
    free(parent)


# #79, the Unfinished panel.


def panel_with(qapp: QApplication, text: str, count: int) -> tuple[QWidget, UnfinishedPanel]:  # noqa: F811
    parent, _palette = styled(qapp, text=text)
    panel = UnfinishedPanel(parent)
    panel.move(20, 20)
    panel.resize(900, 600)
    items = [{"id": f"a{n}", "title": f"History essay {n}", "remaining_min": 60} for n in range(count)]
    panel.set_items(items)
    settle_layout(qapp)
    return parent, panel


@pytest.mark.parametrize(("text", "least"), [("normal", 36), ("large", 40)])
def test_plan_here_and_delete_are_whole_tall_buttons_with_room_above_and_below_their_words(
    qapp: QApplication,  # noqa: F811
    text: str,
    least: int,
) -> None:
    parent, panel = panel_with(qapp, text, 2)
    answers = ("planUnfinished", "deleteUnfinished")
    buttons = [b for b in panel.findChildren(QPushButton) if b.objectName().split("-")[0] in answers]
    assert len(buttons) == 4
    for button in buttons:
        assert button.height() >= least, (button.text(), button.height())
        assert button.height() >= button.sizeHint().height(), "not cut top or bottom"
        assert button.height() - button.fontMetrics().height() >= 16, "8 pixels above and below the words"
        assert button.width() >= button.fontMetrics().horizontalAdvance(button.text()) + 40, "20 at each side"
        row = panel.list.itemWidget(panel.list.item(0 if button.objectName().endswith("a0") else 1))
        assert row.rect().contains(QRect(button.mapTo(row, QPoint(0, 0)), button.size())), "inside its row"
    plan = panel.findChild(QPushButton, "planUnfinished-a0")
    delete = panel.findChild(QPushButton, "deleteUnfinished-a0")
    assert plan.property("tonal") and not plan.property("outlined")
    assert delete.property("outlined") and not delete.property("quiet")
    free(parent)


@pytest.mark.parametrize("text", ["normal", "large"])
def test_the_unfinished_panel_grows_to_about_three_and_a_half_rows_before_it_scrolls(
    qapp: QApplication,  # noqa: F811
    text: str,
) -> None:
    parent, panel = panel_with(qapp, text, 2)
    row = panel.list.sizeHintForRow(0)
    assert panel.list.verticalScrollBar().maximum() == 0, "two rows fit"
    assert panel.list.height() < 3 * row
    parent2, many = panel_with(qapp, text, 8)
    row = many.list.sizeHintForRow(0)
    inside = many.list.height() - 2 * many.list.frameWidth() - 4
    assert abs(inside - 3.5 * row) <= 1, (inside, row)
    assert many.list.verticalScrollBar().maximum() > 0, "the fourth row scrolls"
    free(parent)
    free(parent2)


def test_the_unfinished_rows_are_measured_again_when_the_look_reaches_them(
    qapp: QApplication,  # noqa: F811
) -> None:
    """#79's cut buttons: the rows were measured before the style sheet reached their buttons. A panel
    filled first and styled after (a look chosen while it is open) still fits its buttons."""
    looks, _palette = styled(qapp)
    parent = QWidget()
    parent.resize(940, 640)
    parent.show()
    panel = UnfinishedPanel(parent)
    panel.resize(900, 600)
    panel.set_items([{"id": "a0", "title": "History essay", "remaining_min": 60}])
    settle_layout(qapp)
    parent.setStyleSheet(looks.styleSheet())
    settle_layout(qapp)
    button = panel.findChild(QPushButton, "planUnfinished-a0")
    row = panel.list.itemWidget(panel.list.item(0))
    assert button.height() >= 36 and button.height() >= button.sizeHint().height()
    assert row.rect().contains(QRect(button.mapTo(row, QPoint(0, 0)), button.size())), "inside its row"
    free(parent)
    free(looks)
