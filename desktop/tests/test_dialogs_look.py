"""Dialogs in the 0.17 system (decision 23 of docs/0.17/plan.md, look-review.md section 7).

Add homework and Edit event are sheets inside the window: a card over the dimmed week. Every other
dialog stays a window. In each, the body is the card, not a pale box inside it; a label sits on its
field's line of words; every field of a kind has one width; the repeat scope is a choice of two shown
only for a repeating block; a primary that cannot be pressed yet keeps its colour at 40 %; a list's
ticks are the app's check boxes; and Account is three cards.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QLabel,
    QPushButton,
    QWidget,
)

from desktop.native.look import mix, pack_stylesheet, resolved_palette
from desktop.native.settings import AccountDialog
from desktop.native.widgets import (
    BlockDialog,
    HomeworkDialog,
    LateDialog,
    RoutineDialog,
    Segmented,
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


def styled(qapp: QApplication, pack: str = "light-frost") -> tuple[QWidget, dict]:  # noqa: F811
    """A window-sized parent dressed in a look, as the app's window is."""
    palette = resolved_palette(pack, False, None, "default")
    made = QWidget()
    made.setStyleSheet(pack_stylesheet(pack, False, None, "default", palette, control_art(palette)))
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


def test_the_two_editors_are_sheets_over_the_dimmed_week_and_the_rest_stay_windows(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    window.resize(1280, 800)
    qapp.processEvents()
    spot = QPoint(20, window.height() - 20)
    before = window.grab().toImage().pixelColor(spot)
    for make in (
        lambda: HomeworkDialog(window, today=WEEK),
        lambda: BlockDialog(window, soccer(), occurrence_day=3),
    ):
        dialog = shown(qapp, make())
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint, "no window frame of its own"
        shade = window.findChild(QWidget, "sheetShade")
        assert shade is not None and shade.isVisible() and shade.geometry() == window.rect()
        dimmed = window.grab().toImage().pixelColor(spot)
        assert dimmed.lightness() < 0.75 * before.lightness(), "the week behind is dimmed"
        card = dialog.card
        centre = card.mapToGlobal(card.rect().center()) - window.mapToGlobal(window.rect().center())
        assert abs(centre.x()) <= 2 and abs(centre.y()) <= 2, "the card is centred on the window"
        on_window = card.rect().translated(card.mapTo(window, QPoint(0, 0)))
        assert window.rect().contains(on_window), "the card is inside the window"
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
        assert seen == [dialog]
        qapp.processEvents()
        assert not any(item.isVisible() for item in window.findChildren(QWidget, "sheetShade"))
        assert window.grab().toImage().pixelColor(spot) == before, "the dimming goes with the sheet"
        free(dialog)
    late = shown(qapp, LateDialog(window, "Soccer practice"))
    assert not late.windowFlags() & Qt.WindowType.FramelessWindowHint, "Running late stays a window"
    assert window.findChild(QWidget, "sheetShade") is None
    free(late)


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


def test_a_label_sits_on_its_fields_line_of_words(qapp: QApplication) -> None:  # noqa: F811
    """Labels were level with their fields' top edge, 4 pixels above the words in them."""
    parent, _palette = styled(qapp)
    block = shown(qapp, BlockDialog(parent, soccer(), occurrence_day=3))
    form = block.findChild(QFormLayout)
    for field in (block.title, block.start, block.end, block.category, block.spotify, block.scope_choice):
        label = form.labelForField(field)
        assert abs(middle_y(label, block) - middle_y(field, block)) <= 1, label.text()
    days = next(label for label in block.findChildren(QLabel) if label.text() == "Days")
    assert abs(middle_y(days, block) - middle_y(block.days[0], block)) <= 1, "Days sits on the boxes' line"
    homework = shown(qapp, HomeworkDialog(parent, today=WEEK))
    due = next(label for label in homework.findChildren(QLabel) if label.text() == "Due")
    assert abs(middle_y(due, homework) - middle_y(homework.due.date, homework)) <= 1
    free(block)
    free(homework)
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


def test_a_primary_that_cannot_be_pressed_yet_keeps_its_colour_at_40_percent(
    qapp: QApplication,  # noqa: F811
) -> None:
    """Running late's Accept was a grey slab until Preview, and looked broken."""
    parent, palette = styled(qapp)
    late = shown(qapp, LateDialog(parent, "School"))
    button = late.accept_button

    def fill() -> QColor:
        return late.grab().toImage().pixelColor(button.mapTo(late, QPoint(button.width() // 2, 4)))

    assert near(fill(), QColor(mix(palette["accent"], palette["window"], 0.4)))
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
