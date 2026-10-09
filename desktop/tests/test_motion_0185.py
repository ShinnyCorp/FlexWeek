"""0.18.5 #96, #97 and #29 on the real window: Month keeps its last grid while the next one loads, the
Undo toast survives a view switch, a sheet's dim goes with it, and Month and My day slide the rail away."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator

import pytest

pytest_plugins = ["desktop.tests.window_support"]

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication, QPushButton

    import desktop.native.motion as motion
    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.motion import OVER_MS, PAGE_OUT_MS, apply_ui_effects, duration
    from desktop.native.window import NativeWindow
    from desktop.tests.test_retro_month_slide import (
        in_design,
        nothing_left_over,
        press,
        settle_everything,
        watch,
    )
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


def classic_with_panels(qapp: QApplication, window: NativeWindow, level: str = "normal") -> None:  # noqa: F811
    """Today's app, with the rail beside Week and the plan bar on screen."""
    seeded(qapp, window)
    session = window.session
    session.add_homework({"id": "poster", "title": "Science fair poster", "estimate_min": 600, "revision": 0,
                          "due": f"{session.week_start}T08:00"})
    session.save()
    settled(qapp, window)
    session.solve()
    wait_until(qapp, lambda: session.trace is not None and not session.busy)
    in_design(qapp, window, "classic", level)
    assert window.rail.isVisible() and window.plan_review.isVisible()


def live_view(window: NativeWindow, view: str) -> bool:
    return window.session.planner_view == view and not motion.busy() and window.session.month_data is not None


def test_week_to_month_and_back_slide_as_settings_does_when_the_rail_goes_and_returns(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """#29: Month drops the rail, so the page jumped sideways. It slides in over the dimmed week and the
    month slides away to the right the same way, each as long as Settings' slide, then nothing is left."""
    classic_with_panels(qapp, window)
    seen = watch(window, monkeypatch)
    page = window._week_page
    length = duration(OVER_MS, "normal")
    press(qapp, window, "viewMonth", lambda: live_view(window, "month"))
    settle_everything(qapp, window)
    going = [frame for frame in seen.with_slide() if frame.total == length]
    assert going, "a picture of the month slides in"
    first, last = going[0], going[-1]
    assert first.slides == [page.width()] and first.dims == [0.0], "it starts off the right edge, undimmed"
    assert first.fades == 1, "the week stays under it as one picture"
    assert last.slides == [0] and last.dims == [1.0], "it lands at the left edge, the week fully dimmed"
    assert not window.rail.isVisible() and window.planner.currentWidget() is window.month_grid
    assert not [frame for frame in seen.frames if frame.total == duration(PAGE_OUT_MS, "normal")], (
        "no cross-fade of the old page runs beside the slide"
    )
    nothing_left_over(window)
    seen.frames.clear()
    press(qapp, window, "viewWeek", lambda: window.session.planner_view == "week")
    settle_everything(qapp, window)
    leaving = seen.slid(length)
    assert leaving, "the month slides away"
    first, last = leaving[0], leaving[-1]
    assert first.offsets == [0] and first.dims == [1.0], "the month starts in place over the dimmed week"
    assert last.offsets == [page.width()] and last.dims == [0.0], "gone off the right, the week bright"
    assert window.rail.isVisible() and window.planner.currentWidget() is window.week_table
    nothing_left_over(window)


def test_week_to_my_day_and_back_slide_too(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    classic_with_panels(qapp, window)
    seen = watch(window, monkeypatch)
    page = window._week_page
    length = duration(OVER_MS, "normal")
    press(qapp, window, "viewMyDay", lambda: window._day_mode and not motion.busy())
    settle_everything(qapp, window)
    going = [frame for frame in seen.with_slide() if frame.total == length]
    assert going and going[0].slides == [page.width()] and going[-1].slides == [0]
    assert not window.rail.isVisible()
    seen.frames.clear()
    press(qapp, window, "viewWeek", lambda: not window._day_mode and not motion.busy())
    settle_everything(qapp, window)
    leaving = seen.slid(length)
    assert leaving and leaving[0].offsets == [0] and leaving[-1].offsets == [page.width()]
    assert window.rail.isVisible()
    nothing_left_over(window)


def test_a_panel_is_drawn_once_while_the_rail_slides_away_not_at_both_of_its_places(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """0.18.5 #97: the plan bar and the Unfinished card sat beside the rail, then at the left edge, and
    the cross-fade drew both. They are not faded or moved while the slide runs, and the only pictures
    are the week as it was and the month coming in."""
    classic_with_panels(qapp, window)
    seen = watch(window, monkeypatch)
    effects: list[list[str]] = []
    real_run = motion._run

    def spy(owner, total, step, done):  # type: ignore[no-untyped-def]
        def checked(at: float) -> None:
            step(at)
            effects.append(
                [
                    name
                    for name, piece in (
                        ("plan bar", window.plan_review),
                        ("Unfinished", window.unfinished_panel),
                        ("planner", window.planner),
                    )
                    if piece.graphicsEffect() is not None
                ]
            )

        real_run(owner, total, checked, done)

    monkeypatch.setattr(motion, "_run", spy)
    press(qapp, window, "viewMonth", lambda: live_view(window, "month"))
    settle_everything(qapp, window)
    assert effects and all(found == [] for found in effects), "no panel is faded in beside the slide"
    assert all(frame.fades <= 1 for frame in seen.frames), "one picture of the old page, never two"
    nothing_left_over(window)


def test_day_and_week_keep_the_rail_and_only_cross_fade(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    classic_with_panels(qapp, window)
    seen = watch(window, monkeypatch)
    press(qapp, window, "viewDay", lambda: window.session.planner_view == "day" and not motion.busy())
    assert window.rail.isVisible()
    assert seen.with_slide() == [] and seen.with_dim() == [], "nothing slides over or dims"
    nothing_left_over(window)


def test_under_reduce_the_rail_going_fades_through_and_moves_nothing(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    classic_with_panels(qapp, window, "reduce")
    seen = watch(window, monkeypatch)
    press(qapp, window, "viewMonth", lambda: live_view(window, "month"))
    settle_everything(qapp, window)
    assert seen.with_slide() == [] and seen.with_dim() == [], "nothing travels or dims"
    assert seen.with_fade(), "the week fades through to the month"
    nothing_left_over(window)


def test_the_plan_bar_is_laid_over_the_planners_column_without_an_error(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """_layout_plan_review asked the column, which is a layout, where it was on the page, and raised
    in every Qt slot that called it, so the bar was never placed or slid down."""
    raised: list[object] = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, error, trace: raised.append(error))
    classic_with_panels(qapp, window)
    window._layout_plan_review()
    column, bar = window._column.geometry(), window.plan_review
    assert raised == []
    assert (bar.x(), bar.width()) == (column.left(), column.width())
    assert bar.y() >= column.top()


@pytest.mark.parametrize(("month_arrives", "plan_bar"), [(False, False), (False, True), (True, True)])
def test_nothing_live_is_drawn_over_the_pictures_while_the_rail_slides_away(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
    month_arrives: bool, plan_bar: bool,
) -> None:
    """0.18.5 #97: the running timer (moved from the rail into the column) and the plan bar (raised
    again as the month arrived) were drawn over the pictures, so they showed twice: once in the
    picture at the old place and once live at the new one."""
    from PySide6.QtWidgets import QLabel, QWidget

    from desktop.native.motion import FADE_NAME, SLIDE_NAME, Dim

    NAMES = (FADE_NAME, SLIDE_NAME)

    classic_with_panels(qapp, window)
    if not plan_bar:
        window.plan_review.hide()
    # A timer on screen, which moves from the rail into the column as the rail goes.
    monkeypatch.setattr(window.focus_panel, "set_state", lambda *_: None)
    window.focus_panel.show()
    page = window._week_page
    over: list[list[str]] = []
    real_run = motion._run

    def spy(owner, total, step, done):  # type: ignore[no-untyped-def]
        def checked(at: float) -> None:
            step(at)
            # The month arriving mid-slide lays the plan bar out, and raises it, again.
            if month_arrives:
                window._layout_plan_review()
            kids = page.children()
            pictures = [
                at_
                for at_, kid in enumerate(kids)
                if isinstance(kid, Dim) or (isinstance(kid, QLabel) and kid.objectName() in NAMES)
            ]
            if pictures:
                over.append(
                    [
                        kid.objectName() or type(kid).__name__
                        for index, kid in enumerate(kids[min(pictures) + 1 :], min(pictures) + 1)
                        if index not in pictures and isinstance(kid, QWidget) and kid.isVisible()
                    ]
                )

        real_run(owner, total, checked, done)

    monkeypatch.setattr(motion, "_run", spy)
    press(qapp, window, "viewMonth", lambda: live_view(window, "month"))
    settle_everything(qapp, window)
    assert over, "frames were seen"
    assert all(found == [] for found in over), over
