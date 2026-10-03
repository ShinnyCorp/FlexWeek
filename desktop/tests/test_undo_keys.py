"""Ctrl+Z and Ctrl+Y work for the week wherever the keyboard is on its page, except in a box with typed
text of its own to undo."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QSpinBox, QWidget

from desktop.native.window import NativeWindow
from desktop.tests.grid_support import (  # noqa: F401
    add_piano,
    key,
    window,
)
from desktop.tests.window_support import (  # noqa: F401
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
)
from desktop.tests.window_support import window as signed_in  # noqa: F401


@pytest.fixture()
def undoable(qapp: QApplication, window: NativeWindow) -> NativeWindow:
    """One change made, so Undo has something to take back."""
    add_piano(qapp, window)
    window.session.delete_block("piano")
    window.session.save()
    settled(qapp, window)
    assert window.session.can_undo()
    return window


def a_box_in_the_week(window: NativeWindow, kind: type) -> QWidget:
    box = kind(window._week_page)
    box.setObjectName("probeBox")
    box.show()
    return box


@pytest.mark.parametrize("kind", [QLineEdit, QSpinBox, QComboBox])
def test_ctrl_z_undoes_the_week_from_a_box_with_nothing_typed(
    qapp: QApplication, undoable: NativeWindow, kind: type
) -> None:
    box = a_box_in_the_week(undoable, kind)
    box.setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    key(undoable, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    wait_until(qapp, lambda: any(block["id"] == "piano" for block in undoable.session.blocks))
    settled(qapp, undoable)
    assert undoable.session.can_redo()
    key(undoable, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    wait_until(qapp, lambda: not any(block["id"] == "piano" for block in undoable.session.blocks))
    box.deleteLater()


def test_ctrl_z_belongs_to_a_box_with_typed_text_until_it_is_undone(
    qapp: QApplication, undoable: NativeWindow
) -> None:
    box = a_box_in_the_week(undoable, QLineEdit)
    box.setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    for letter in (Qt.Key.Key_A, Qt.Key.Key_B):
        key(undoable, letter)
    assert box.text() == "ab"
    key(undoable, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert box.text() == "", "the box's own undo took the typing back"
    assert not any(block["id"] == "piano" for block in undoable.session.blocks), "the week was left alone"
    box.deleteLater()
