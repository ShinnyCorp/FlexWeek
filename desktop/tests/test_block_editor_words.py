"""The block editor as a student reads it (0.15 rows 17, 26, 27 and decision 4).

"Edit fixed commitment" was nobody's word for practice. Seven day boxes said nothing about what
ticking another one does. Save and Cancel looked the same, with a floppy disk and a red X, and
Delete was the biggest button in the dialog and deleted without asking.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProxyStyle,
    QPushButton,
    QStyle,
    QWidget,
)

from desktop.native import widgets
from desktop.native.look import resolved_palette, sanitize_look
from desktop.native.widgets import AppStyle, BlockDialog
from desktop.native.window import NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    host,
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
    window,
)


def soccer(**fields: object) -> dict:
    return {
        "id": "soccer",
        "title": "Soccer practice",
        "kind": "locked",
        "category": "sport",
        "start": "16:00",
        "duration_min": 90,
        "days": [1, 3],
        **fields,
    }


class WantsIcons(QProxyStyle):
    """KDE's style, as far as dialog buttons go: it asks for a floppy disk on Save."""

    def styleHint(self, hint, option=None, widget=None, data=None):  # noqa: N802
        if hint == QStyle.StyleHint.SH_DialogButtonBox_ButtonsHaveIcons:
            return 1
        return super().styleHint(hint, option, widget, data)


@pytest.fixture()
def icon_style(qapp: QApplication) -> Iterator[None]:  # noqa: F811
    # The app's own style is a proxy with no name to restore it by.
    ours = isinstance(qapp.style(), AppStyle)
    name = qapp.style().name()
    qapp.setStyle(WantsIcons(name))
    yield
    qapp.setStyle(AppStyle() if ours else name)


def test_the_editor_is_titled_as_a_student_says_it(qapp: QApplication, host: QWidget) -> None:  # noqa: F811
    assert BlockDialog(host, day=3, start="17:15").windowTitle() == "New event"
    assert BlockDialog(host, soccer()).windowTitle() == "Edit event"


def test_it_says_that_ticking_another_day_repeats_it(qapp: QApplication, host: QWidget) -> None:  # noqa: F811
    dialog = BlockDialog(host, day=3, start="17:15", duration_min=30, from_range=True)
    dialog.show()
    note = dialog.findChild(QLabel, "blockRepeatNote")
    assert note.text() == "Tick more days to repeat it this week."
    assert note.isVisibleTo(dialog)
    series = BlockDialog(host, soccer(), occurrence_day=3)
    series.show()
    series.scope_occurrence.setChecked(True)
    note = series.findChild(QLabel, "blockRepeatNote")
    assert not note.isVisibleTo(series), "the days cannot be changed for this day only"


@pytest.mark.parametrize("text", ["normal", "large"])
def test_the_repeat_note_sits_whole_under_the_day_boxes(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    text: str,
) -> None:
    window._look = sanitize_look({**window._look, "knobs": {**window._look.get("knobs", {}), "text": text}})
    window._apply_appearance()
    dialog = BlockDialog(window, day=3, start="17:15", duration_min=30, from_range=True)
    dialog.show()
    qapp.processEvents()
    note = dialog.findChild(QLabel, "blockRepeatNote")
    thursday = dialog.findChild(QCheckBox, "blockDay3")
    below = note.mapTo(dialog, QPoint(0, 0)).y() - thursday.mapTo(dialog, QPoint(0, thursday.height())).y()
    needed = note.heightForWidth(note.width()) if note.wordWrap() else note.sizeHint().height()
    assert note.height() == needed, "taller than its words, so it floated, or shorter, so it was cut"
    assert note.wordWrap() or note.width() >= note.sizeHint().width()
    assert 0 <= below <= 8, below
    dialog.close()


def test_the_missed_box_names_the_day(qapp: QApplication, host: QWidget) -> None:  # noqa: F811
    dialog = BlockDialog(host, soccer(), occurrence_day=3)
    assert dialog.missed.text() == "I missed it on Thursday"


def test_no_button_in_the_editor_has_an_icon(
    qapp: QApplication,  # noqa: F811
    icon_style: None,
    host: QWidget,  # noqa: F811
) -> None:
    dialog = BlockDialog(host, soccer(), occurrence_day=3)
    buttons = dialog.findChildren(QPushButton)
    assert {button.text() for button in buttons} >= {"Save", "Cancel", "Delete"}
    assert [button.text() for button in buttons if not button.icon().isNull()] == []


def test_save_is_the_one_filled_button_and_delete_is_quiet_at_the_bottom_left(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    dialog = BlockDialog(window, soccer(), occurrence_day=3)
    dialog.show()
    qapp.processEvents()
    box = dialog.findChild(QDialogButtonBox)
    save = box.button(QDialogButtonBox.StandardButton.Save) or next(
        button for button in box.buttons() if button.text() == "Save"
    )
    cancel = next(button for button in box.buttons() if button.text() == "Cancel")
    delete = dialog.findChild(QPushButton, "deleteBlock")
    assert delete not in box.buttons(), "Delete is not one of the dialog's answers"
    assert save.isDefault()

    picture = dialog.grab().toImage()
    background = picture.pixelColor(2, 2)

    def fill(button: QPushButton) -> QColor:
        # Above the words, inside the edge: the button's own paint and nothing else.
        at = button.mapTo(dialog, QPoint(button.width() // 2, 4))
        return picture.pixelColor(at.x(), at.y())

    def centre(button: QPushButton) -> QPoint:
        return button.mapTo(dialog, button.rect().center())

    assert fill(save) != background, "Save is filled"
    assert fill(cancel) == background, "Cancel is plain"
    assert fill(delete) == background, "Delete is words, not a button"
    assert abs(centre(delete).y() - centre(save).y()) <= 4, "Delete sits on the button row"
    assert centre(delete).x() < min(centre(save).x(), centre(cancel).x()), "Delete is at the left"
    dialog.close()


def test_delete_asks_first_and_does_nothing_when_refused(
    qapp: QApplication,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    host: QWidget,  # noqa: F811
) -> None:
    asked: list[tuple[str, str, str]] = []
    answer = [False]

    def confirm(_parent, title: str, question: str, yes: str) -> bool:
        asked.append((title, question, yes))
        return answer[0]

    monkeypatch.setattr(widgets, "confirm", confirm)
    dialog = BlockDialog(host, soccer())
    dialog.show()
    dialog.delete_button.click()
    assert asked == [("Delete event", "Delete Soccer practice? You can undo this.", "Delete")]
    assert dialog.result() != QDialog.DialogCode.Accepted and dialog.deleted() is False
    assert dialog.isVisible(), "refusing leaves the editor open"
    answer[0] = True
    dialog.delete_button.click()
    assert dialog.deleted() is True and dialog.result() == QDialog.DialogCode.Accepted
    one_day = BlockDialog(host, soccer(), occurrence_day=3)
    one_day.scope_occurrence.setChecked(True)
    one_day.delete_button.click()
    assert asked[-1][1] == "Delete Soccer practice on Thursday? You can undo this."


def test_a_deleted_block_can_be_undone_from_the_notice(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = window.session
    session.add_block(soccer())
    session.save()
    settled(qapp, window)
    monkeypatch.setattr(widgets, "confirm", lambda *_args: True)
    dialog = BlockDialog(window, session.blocks[0])

    def run() -> int:
        dialog.show()
        dialog.delete_button.click()
        return dialog.result()

    monkeypatch.setattr(dialog, "exec", run, raising=False)
    window._commit_block(dialog)
    settled(qapp, window)
    assert session.blocks == []
    assert window.toast.text() == "Deleted Soccer practice."
    assert window.toast.button.text() == "Undo"
    window.toast.button.click()
    wait_until(qapp, lambda: [block["id"] for block in session.blocks] == ["soccer"])


def test_a_series_opened_on_one_day_does_not_also_say_every_day_changes(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
) -> None:
    one_day = BlockDialog(host, soccer(), occurrence_day=3)
    one_day.show()
    assert one_day.findChild(QWidget, "editScope").isVisibleTo(one_day)
    note = one_day.findChild(QLabel, "seriesScope")
    assert not note.isVisibleTo(one_day), "it stood over This day only and said the opposite"
    whole = BlockDialog(host, soccer())
    whole.show()
    assert not whole.findChild(QWidget, "editScope").isVisibleTo(whole)
    assert whole.findChild(QLabel, "seriesScope").isVisibleTo(whole)


def test_the_question_before_deleting_draws_its_answer_red_and_cancel_plain(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    pack, dark, accent = window._look_inputs()
    red = QColor(resolved_palette(pack, dark, window._look, accent)["error"])
    box = widgets.confirm_box(window, "Delete event", "Delete Soccer practice? You can undo this.", "Delete")
    box.show()
    qapp.processEvents()
    yes = box.findChild(QPushButton, "confirmYes")
    cancel = box.findChild(QPushButton, "confirmCancel")
    assert sorted(button.text() for button in box.buttons() if button.isVisible()) == ["Cancel", "Delete"]
    picture = box.grab().toImage()

    def fill(button: QPushButton) -> QColor:
        at = button.mapTo(box, QPoint(button.width() // 2, 4))
        return picture.pixelColor(at.x(), at.y())

    assert fill(yes) == red, fill(yes).name()
    assert fill(cancel) == picture.pixelColor(2, 2), "Cancel is plain"
    box.close()
    leave = widgets.confirm_box(window, "Log out", "Log out?", "Log out", danger=False)
    leave.show()
    qapp.processEvents()
    picture = leave.grab().toImage()
    answer = leave.findChild(QPushButton, "confirmYes")
    at = answer.mapTo(leave, QPoint(answer.width() // 2, 4))
    assert picture.pixelColor(at.x(), at.y()) not in (red, picture.pixelColor(2, 2)), "filled, not red"
    leave.close()
