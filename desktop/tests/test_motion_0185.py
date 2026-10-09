"""0.18.5 #96, #97 and #29 on the real window: Month keeps its last grid while the next one loads, the
Undo toast survives a view switch, a sheet's dim goes with it, and Month and My day slide the rail away."""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator

import pytest

pytest_plugins = ["desktop.tests.window_support"]

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication, QPushButton

    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.motion import apply_ui_effects
    from desktop.native.window import NativeWindow
    from desktop.tests.test_week_side import seeded
    from desktop.tests.window_support import qapp, settled, still, wait_until, window  # noqa: F401


@pytest.fixture(autouse=True)
def motion_is_put_back() -> Iterator[None]:
    yield
    apply_ui_effects("normal")


def month_days(window: NativeWindow) -> list[str]:
    return [cell.iso for cell in window.month_grid.canvas.cells]


def test_week_to_month_to_the_next_month_never_shows_an_empty_grid(
    qapp: QApplication, window: NativeWindow  # noqa: F811
) -> None:
    seeded(qapp, window)
    window.findChild(QPushButton, "viewMonth").click()
    wait_until(qapp, lambda: window.session.month_data is not None)
    still(window)
    first = month_days(window)
    assert first
    # The next month is on its way: the session has dropped the old one and asked for the new.
    window.next_nav.click()
    assert window.session.month_data is None, "the next month has not arrived yet"
    assert month_days(window) == first, "the last month stays drawn while it loads"
    assert window.month_grid.warning.text() == "Loading month…"
    wait_until(qapp, lambda: window.session.month_data is not None)
    assert month_days(window) and month_days(window) != first
    assert window.month_grid.warning.text() == ""


def test_the_undo_toast_survives_a_design_change_and_still_undoes(
    qapp: QApplication, window: NativeWindow  # noqa: F811
) -> None:
    seeded(qapp, window)
    window.toast.hide()
    steps = len(window.session._undo)
    assert steps, "the seeding left a change to take back"
    window._set_notice("Moved History essay to Fri 18:00.", "Undo", window._undo_from_notice)
    for main in ("clay", "retro", "classic"):
        window._layout = sanitize_layout({"main": main, "day": "one"})
        window._apply_appearance()
        window._on_week()
        qapp.processEvents()
        assert window.toast.isVisible() and window.toast.button.isVisible(), main
    window.findChild(QPushButton, "viewMonth").click()
    settled(qapp, window)
    assert window.toast.button.isVisible()
    window.toast.button.click()
    settled(qapp, window)
    assert len(window.session._undo) == steps - 1, "the Undo used from Month took the step back"
    assert window.toast.text() != "Moved History essay to Fri 18:00.", "used, the old notice goes"


def test_the_toast_goes_when_the_week_changes_because_its_undo_is_for_that_week(
    qapp: QApplication, window: NativeWindow  # noqa: F811
) -> None:
    """Undo says "applies to the week where that change was saved" anywhere else, so a toast offering
    it would offer something that does nothing."""
    seeded(qapp, window)
    window._set_notice("Moved History essay to Fri 18:00.", "Undo", window._undo_from_notice)
    window._go_next()
    settled(qapp, window)
    assert not window.toast.isVisible() and not window.toast.button.isVisible()
