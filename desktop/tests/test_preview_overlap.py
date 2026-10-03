"""One overlap rule everywhere: a second block at the same time is allowed, and says so. Duplicate,
paste, copy day and apply routine previews used to refuse such a row while a drag and the editor only
warned that both would show side by side."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLabel

from desktop.native.widgets import PreviewDialog
from desktop.native.window import NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
)
from desktop.tests.window_support import window as signed_in  # noqa: F401

SOCCER = {
    "id": "soccer",
    "kind": "locked",
    "title": "Soccer practice",
    "category": "extra",
    "start": "16:00",
    "duration_min": 90,
    "days": [0],
}
WARNING = "Soccer practice is at that time too. Both will show, side by side."


@pytest.fixture()
def window(qapp: QApplication, signed_in: NativeWindow) -> NativeWindow:
    signed_in.session.add_block(dict(SOCCER))
    signed_in.session.save()
    settled(qapp, signed_in)
    signed_in.session.select_block("soccer", 0)
    return signed_in


def on_top_rows(window: NativeWindow) -> list[dict]:
    window.session.copy_selected()
    rows = window.session.paste_proposals(0, "16:00")
    assert rows is not None
    return rows


def test_a_preview_row_that_lands_on_a_block_warns_in_the_editors_words_and_can_be_saved(
    qapp: QApplication, window: NativeWindow
) -> None:
    dialog = PreviewDialog(window, "Preview paste", "", on_top_rows(window), window.session.blocks)
    try:
        assert dialog.findChild(QLabel, "previewDetail0").text() == WARNING
        assert dialog.findChild(QCheckBox, "previewInclude0").isChecked()
        assert dialog.confirm.isEnabled()
        assert dialog.error.text() == ""
    finally:
        dialog.deleteLater()


def test_only_selecting_nothing_still_blocks_a_preview(qapp: QApplication, window: NativeWindow) -> None:
    dialog = PreviewDialog(window, "Preview paste", "", on_top_rows(window), window.session.blocks)
    try:
        dialog.findChild(QCheckBox, "previewInclude0").setChecked(False)
        assert not dialog.confirm.isEnabled()
        assert dialog.error.text() == "Select at least one item before saving."
        assert dialog.rows()[0]["checked"] is False
        assert window.session.confirm_preview(dialog.rows(), label="the copied block") is False
        assert window.session.message == "Select at least one item before saving."
    finally:
        dialog.deleteLater()


def test_duplicate_saves_its_copy_on_top_of_the_original(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, bool, bool]] = []

    def accept(dialog: PreviewDialog) -> int:
        seen.append(
            (
                dialog.findChild(QLabel, "previewDetail0").text(),
                dialog.findChild(QCheckBox, "previewInclude0").isChecked(),
                dialog.confirm.isEnabled(),
            )
        )
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PreviewDialog, "exec", accept)
    window._duplicate_selected()
    wait_until(qapp, lambda: not window.session.busy and len(window.session.blocks) == 2)
    assert seen == [(WARNING, True, True)]
    assert [(block["days"], block["start"]) for block in window.session.blocks] == [([0], "16:00")] * 2


def test_a_copied_day_pastes_onto_the_same_day_and_both_stay(
    qapp: QApplication, window: NativeWindow
) -> None:
    assert window.session.copy_day(0)
    rows = window.session.paste_proposals(0, None)
    assert rows is not None and all(row["checked"] for row in rows)
    assert window.session.confirm_preview(rows, label="the copied day")
    wait_until(qapp, lambda: not window.session.busy and len(window.session.blocks) == 2)
