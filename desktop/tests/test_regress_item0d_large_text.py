"""Regression for fix-specs.md item 0d: passing through High contrast silently turns Large text off.

`settings.py::_built_in_look` keeps only knobs that differ from the worn preset (`look.py::look_overrides`);
High contrast's own `text` is "large", so while it is worn the student's Large is not kept and the next
look falls back to Normal. Driven through the Settings page of a signed-in window; "restart" is a new
NativeWindow on the same device, which reads the saved look file as the app does at start.
The three that failed before the fix are guards now.
"""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QLabel, QPushButton

from desktop.native.look import effective_look, sanitize_look
from desktop.native.window import NativeWindow
from desktop.tests.window_support import free, qapp, server, settled, signed_out, window  # noqa: F401

TOKENS = {
    "Light": "pack:light-frost",
    "Dark": "pack:dark-frost",
    "High contrast": "preset:high-contrast",
    "Nocturne": "pack:nocturne",
    "Terminal": "preset:terminal",
}


def settings(qapp, window):
    window._open_settings()
    for _ in range(5):
        qapp.processEvents()
    return window._settings


def choose(qapp, page, knob: str, value: str) -> None:
    box = page.knobs[knob]
    box.setCurrentIndex(box.findData(value))
    qapp.processEvents()


def wear(qapp, page, look: str) -> None:
    page.look.setCurrentIndex(page.look.findData(TOKENS[look]))
    qapp.processEvents()


def shown(page, knob: str) -> str:
    return effective_look(page.look_choice())[knob]


def after_restart(qapp, server, knob: str) -> str:
    again = NativeWindow(server.origin)
    try:
        return effective_look(again._look)[knob]
    finally:
        again.hide()
        free(again)


def walk(qapp, page, looks: list[str], knob: str) -> list[tuple[str, str]]:
    seen = []
    for look in looks:
        wear(qapp, page, look)
        seen.append((look, shown(page, knob)))
    return seen


def test_large_text_survives_light_dark_high_contrast_nocturne_light_and_a_restart(
    qapp, server, window
) -> None:
    """The spec's guard."""
    page = settings(qapp, window)
    choose(qapp, page, "text", "large")
    looks = ["Light", "Dark", "High contrast", "Nocturne", "Light"]
    seen = walk(qapp, page, looks, "text")
    window._close_settings(save=True)
    settled(qapp, window)
    seen.append(("after restart", after_restart(qapp, server, "text")))
    assert seen == [(look, "large") for look in looks] + [("after restart", "large")]


def test_large_text_survives_terminal_and_back_and_a_restart(qapp, server, window) -> None:
    """Guard (Assistant Local's run): a look whose own text size is Normal keeps the student's Large."""
    page = settings(qapp, window)
    choose(qapp, page, "text", "large")
    seen = walk(qapp, page, ["Terminal", "Light", "Nocturne"], "text")
    window._close_settings(save=True)
    settled(qapp, window)
    seen.append(("after restart", after_restart(qapp, server, "text")))
    assert [size for _look, size in seen] == ["large"] * 4, seen


def test_sharp_corners_moved_by_hand_survive_high_contrast(qapp, window) -> None:
    page = settings(qapp, window)
    choose(qapp, page, "corners", "sharp")
    seen = walk(qapp, page, ["High contrast", "Nocturne"], "corners")
    assert seen == [("High contrast", "sharp"), ("Nocturne", "sharp")]


def test_high_contrast_suggests_large_text_instead_of_forcing_it(qapp, window) -> None:
    page = settings(qapp, window)
    assert shown(page, "text") == "normal"
    wear(qapp, page, "High contrast")
    assert shown(page, "text") == "normal", "High contrast switched text size by itself"
    chip = [
        label for label in page.findChildren(QLabel) if label.isVisible() and "Suggests Large" in label.text()
    ]
    use = [b for b in page.findChildren(QPushButton) if b.isVisible() and b.text().replace("&", "") == "Use"]
    assert chip and use


def test_an_account_saved_on_high_contrast_keeps_its_large_text_on_the_next_look(qapp, window) -> None:
    """A look saved before 0.19.0 wore High contrast with no text knob, so its Large came from the preset."""
    window._look = sanitize_look({"preset": "high-contrast", "knobs": {}})
    page = settings(qapp, window)
    assert shown(page, "text") == "large"
    assert walk(qapp, page, ["Nocturne", "Light"], "text") == [("Nocturne", "large"), ("Light", "large")]


def test_the_suggestion_goes_once_large_is_chosen_and_never_shows_on_other_looks(qapp, window) -> None:
    page = settings(qapp, window)
    wear(qapp, page, "Nocturne")
    assert not page.text_suggest.isVisibleTo(page)
    wear(qapp, page, "High contrast")
    assert page.text_suggest.isVisibleTo(page)
    use = [b for b in page.findChildren(QPushButton) if b.text() == "Use"][0]
    use.click()
    qapp.processEvents()
    assert shown(page, "text") == "large"
    assert not page.text_suggest.isVisibleTo(page)
