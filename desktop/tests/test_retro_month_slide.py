"""J17: in Retro, Month slides in over the dimmed desk as Settings does, and slides away the same way."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import pytest

pytest_plugins = ["desktop.tests.window_support"]

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

    import desktop.native.motion as motion
    import desktop.native.window as window_module
    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.motion import FADE_NAME, OVER_MS, SLIDE_NAME, Dim, apply_ui_effects, duration
    from desktop.native.window import NativeWindow
    from desktop.tests.window_support import still, wait_until, window  # noqa: F401


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-retro-month-slide-test"])


@dataclass
class Frame:
    at: float
    total: int
    slides: list[int]
    fades: int
    dims: list[float]
    offsets: list[int]


@dataclass
class Seen:
    frames: list[Frame] = field(default_factory=list)

    def with_dim(self) -> list[Frame]:
        return [frame for frame in self.frames if frame.dims]

    def slid(self, length: int) -> list[Frame]:
        """The frames of the one motion that dims, which the pieces fading beside it (other lengths)
        are not."""
        return [frame for frame in self.with_dim() if frame.total == length]

    def with_fade(self) -> list[Frame]:
        return [frame for frame in self.frames if frame.fades]

    def with_slide(self) -> list[Frame]:
        return [frame for frame in self.frames if frame.slides]


def pictures_over(page: QWidget) -> tuple[list[QLabel], list[QLabel], list[Dim]]:
    """The slide, the held pictures and the dims on `page`. Walks `children()`, not `findChildren()`."""
    labels = [kid for kid in page.children() if isinstance(kid, QLabel) and kid.isVisible()]
    slides = [label for label in labels if label.objectName() == SLIDE_NAME]
    # The picture of the desk or month, trimmed to what changed, not a small one of a part of it.
    tall = page.height() // 2
    fades = [label for label in labels if label.objectName() == FADE_NAME and label.height() > tall]
    dims = [kid for holder in (page, *fades) for kid in holder.children() if isinstance(kid, Dim)]
    return slides, fades, dims


def watch(window: NativeWindow, monkeypatch: pytest.MonkeyPatch) -> Seen:
    """Record what is over the week page after every frame of every motion that runs."""
    seen = Seen()
    page = window._week_page
    real_run = motion._run

    def spy(owner, total, step, done):  # type: ignore[no-untyped-def]
        def recorded(at: float) -> None:
            step(at)
            slides, fades, dims = pictures_over(page)
            offsets = [
                effect.offset.x()
                for effect in (label.graphicsEffect() for label in fades)
                if effect is not None and hasattr(effect, "offset")
            ]
            shares = [dim.share for dim in dims]
            seen.frames.append(Frame(at, total, [label.x() for label in slides], len(fades), shares, offsets))

        real_run(owner, total, recorded, done)

    monkeypatch.setattr(motion, "_run", spy)
    return seen


def settle_everything(qapp: QApplication, window: NativeWindow) -> None:
    wait_until(qapp, lambda: not window.session.busy and not motion.busy())
    still(window)
    qapp.processEvents()


def in_design(qapp: QApplication, window: NativeWindow, design: str, level: str = "normal") -> None:
    window.session.preferences = {**(window.session.preferences or {}), "motion": level}
    window._motion = level
    apply_ui_effects(level)
    window._layout = sanitize_layout({"main": design, "day": "one"})
    window._apply_appearance()
    window.resize(1280, 800)
    window.show()
    window.session.set_view("week")
    window._on_week()
    settle_everything(qapp, window)


def press(qapp: QApplication, window: NativeWindow, name: str, until: Callable[[], bool]) -> None:
    window.findChild(QPushButton, name).click()
    wait_until(qapp, until)
    settle_everything(qapp, window)


def month_board(window: NativeWindow) -> QWidget | None:
    return window.planner.currentWidget().findChild(QWidget, "layoutMonthBoard")


def month_is_live(window: NativeWindow) -> bool:
    board = month_board(window)
    return window.session.planner_view == "month" and board is not None and board.isVisible()


def nothing_left_over(window: NativeWindow) -> None:
    slides, fades, dims = pictures_over(window._week_page)
    assert slides == [] and fades == [] and dims == [], "no picture or dim stays on screen"
    assert window.planner.updatesEnabled(), "the planner paints again"


def test_in_retro_month_slides_in_over_the_dimmed_desk(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_design(qapp, window, "retro")
    seen = watch(window, monkeypatch)
    page = window._week_page
    press(qapp, window, "viewMonth", lambda: month_is_live(window))
    length = duration(OVER_MS, "normal")
    slide_frames = [frame for frame in seen.with_slide() if frame.total == length]
    assert slide_frames, "a picture of the month slides in, as long as Settings' slide"
    first, last = slide_frames[0], slide_frames[-1]
    assert first.slides == [page.width()] and first.dims == [0.0], "it starts off the right edge, undimmed"
    assert first.fades == 1, "the desk stays under it as a picture"
    mid = [frame for frame in slide_frames if 0 < frame.slides[0] < page.width()]
    assert mid and all(0 < frame.dims[0] < 1 for frame in mid if frame.dims[0] != 0.0), "dimming as it moves"
    assert last.slides == [0] and last.dims == [1.0], "it lands at the left edge with the desk fully dimmed"
    assert month_is_live(window)
    nothing_left_over(window)


def test_the_pictures_let_keys_and_clicks_through(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_design(qapp, window, "retro")
    real_run = motion._run
    checked: list[bool] = []

    def spy(owner, total, step, done):  # type: ignore[no-untyped-def]
        real_run(owner, total, step, done)
        slides, fades, dims = pictures_over(window._week_page)
        if dims:
            transparent = Qt.WidgetAttribute.WA_TransparentForMouseEvents
            checked.append(all(item.testAttribute(transparent) for item in (*slides, *fades, *dims)))

    monkeypatch.setattr(motion, "_run", spy)
    press(qapp, window, "viewMonth", lambda: month_is_live(window))
    assert checked and all(checked), "the slide, the desk picture and the dim pass the pointer through"


def test_in_retro_leaving_month_for_week_slides_it_away_the_same_way(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_design(qapp, window, "retro")
    press(qapp, window, "viewMonth", lambda: month_is_live(window))
    seen = watch(window, monkeypatch)
    page = window._week_page
    press(qapp, window, "viewWeek", lambda: window.session.planner_view == "week")
    length = duration(OVER_MS, "normal")
    frames = seen.slid(length)
    assert frames, "the month slides away, as long as Settings' slide"
    first, last = frames[0], frames[-1]
    assert first.offsets == [0] and first.dims == [1.0], "the month starts in place, the desk dimmed"
    assert last.offsets == [page.width()] and last.dims == [0.0], "gone off the right, the week bright"
    assert not month_board(window).isVisible(), "the live week is under it"
    nothing_left_over(window)


@pytest.mark.parametrize(("start", "target"), [("week", "day"), ("day", "week")])
def test_in_retro_day_and_week_still_crossfade(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch, start: str, target: str
) -> None:
    in_design(qapp, window, "retro")
    if start == "day":
        press(qapp, window, "viewDay", lambda: window.session.planner_view == "day")
    seen = watch(window, monkeypatch)
    button = "viewDay" if target == "day" else "viewWeek"
    press(qapp, window, button, lambda: window.session.planner_view == target)
    assert seen.with_fade(), "the old view is a picture fading away"
    assert seen.with_dim() == [] and seen.with_slide() == [], "no dim and no slide between Day and Week"
    nothing_left_over(window)


def test_another_design_keeps_its_month_crossfade(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mission has no rail, so Week and Month only fade through; Today's app slides (test_motion_0185)."""
    in_design(qapp, window, "mission")
    seen = watch(window, monkeypatch)
    press(qapp, window, "viewMonth", lambda: window.session.planner_view == "month")
    assert seen.with_fade(), "the week fades through to the month"
    assert seen.with_dim() == [] and seen.with_slide() == []
    seen.frames.clear()
    press(qapp, window, "viewWeek", lambda: window.session.planner_view == "week")
    assert seen.with_fade() and seen.with_dim() == [] and seen.with_slide() == []
    nothing_left_over(window)


@pytest.mark.parametrize("level", ["reduce", "off"])
def test_under_reduce_and_off_retro_month_does_not_slide(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch, level: str
) -> None:
    in_design(qapp, window, "retro", level)
    seen = watch(window, monkeypatch)
    held: list[object] = []
    real_hold = window_module.hold_picture

    def recording(*args, **kwargs):  # type: ignore[no-untyped-def]
        held.append(real_hold(*args, **kwargs))
        return held[-1]

    monkeypatch.setattr(window_module, "hold_picture", recording)
    press(qapp, window, "viewMonth", lambda: month_is_live(window))
    assert seen.with_dim() == [] and seen.with_slide() == [], "nothing travels or dims"
    if level == "off":
        assert held and all(picture is None for picture in held), "Off: no picture is taken at all"
        assert seen.frames == [], "Off: nothing animates, the month is simply there"
    else:
        assert seen.with_fade(), "Reduce: the week fades through to the month"
    press(qapp, window, "viewWeek", lambda: window.session.planner_view == "week")
    assert seen.with_dim() == [] and seen.with_slide() == []
    nothing_left_over(window)


def month_from_the_engine(qapp: QApplication, window: NativeWindow) -> dict:
    """A real month snapshot, kept so a test can hand it over at the moment it chooses, then back to
    the week."""
    press(qapp, window, "viewMonth", lambda: month_is_live(window))
    data = window.session.month_data
    assert data is not None
    press(qapp, window, "viewWeek", lambda: window.session.planner_view == "week")
    return data


def month_arrives(window: NativeWindow, data: dict) -> None:
    window.session.month_data = data
    window.session.week_changed.emit()


def slide_in_progress(window: NativeWindow) -> QLabel | None:
    slides, _fades, _dims = pictures_over(window._week_page)
    return slides[0] if slides else None


def live_month_now(window: NativeWindow):  # type: ignore[no-untyped-def]
    """The month on screen once the slide is over, in the area the slide covered."""
    page = window._week_page
    top = window._top_bar.geometry().bottom() + 1
    return page.grab(QRect(0, top, page.width(), page.height() - top)).toImage()


def blank_like(image):  # type: ignore[no-untyped-def]
    """An image of one colour, the page's background, the size of `image`."""
    blank = QImage(image.size(), image.format())
    blank.fill(image.pixelColor(0, image.height() - 1))
    return blank


def test_a_month_that_arrives_mid_slide_shows_on_the_moving_picture(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_design(qapp, window, "retro")
    data = month_from_the_engine(qapp, window)
    # The engine has not answered yet when the slide starts, as on a real machine.
    monkeypatch.setattr(window.session, "_fetch_month", lambda: None)
    window.findChild(QPushButton, "viewMonth").click()
    wait_until(qapp, lambda: slide_in_progress(window) is not None)
    moving = slide_in_progress(window)
    assert moving is not None and window.session.month_data is None
    placeholder = moving.pixmap().toImage()
    key = moving.pixmap().cacheKey()
    month_arrives(window, data)
    # The repaint waits one turn of the event loop, for the month to scroll to its first row.
    qapp.processEvents()
    qapp.processEvents()
    assert motion.busy() and slide_in_progress(window) is moving, "the slide is still running"
    assert moving.pixmap().cacheKey() != key, "the moving picture was taken again"
    assert moving.pixmap().toImage() != placeholder, "the real month replaced the placeholder"
    retaken = moving.pixmap().toImage()
    assert retaken != blank_like(retaken), "it is not an empty page"
    settle_everything(qapp, window)
    assert month_is_live(window)
    assert retaken == live_month_now(window), "it is the live month, laid out at its real size"
    nothing_left_over(window)


def test_a_month_that_arrives_after_landing_shows_live(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_design(qapp, window, "retro")
    data = month_from_the_engine(qapp, window)
    # An error inside a Qt slot only reaches the excepthook: a retake aimed at a deleted picture.
    raised: list[object] = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, error, trace: raised.append(error))
    monkeypatch.setattr(window.session, "_fetch_month", lambda: None)
    window.findChild(QPushButton, "viewMonth").click()
    wait_until(qapp, lambda: slide_in_progress(window) is not None)
    settle_everything(qapp, window)
    board = month_board(window)
    assert board is not None and board.isVisible() and board.warning.isVisible(), "still loading"
    month_arrives(window, data)
    qapp.processEvents()
    wait_until(qapp, lambda: not board.warning.isVisible())
    settle_everything(qapp, window)
    assert board.canvas.cells and not board.warning.isVisible(), "the live month shows"
    assert raised == [], "no retake is tried once the slide has landed"
    nothing_left_over(window)
