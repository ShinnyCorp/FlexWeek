"""J15: the dim behind a sheet starts at the click, and the sheet is built behind it.

Order is counted, never timed: a constructor that records what is on screen when it runs sees whether
the dim was already there.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QImage, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from desktop.native import window as window_module
from desktop.native.feel import set_current
from desktop.native.motion import EASE_MS, apply_ui_effects, busy, duration
from desktop.native.widgets import SHEET_DIM, Dialog, HomeworkDialog, SheetShade
from desktop.native.window import NativeWindow
from desktop.tests.test_feel import _host
from desktop.tests.window_support import free, qapp, server, signed_out, wait_until, window  # noqa: F401

# What SHEET_DIM of black is as an alpha byte; written out so a change of the dim is a change here.
DIM_ALPHA = 102


@pytest.fixture(autouse=True)
def motion_is_put_back() -> Iterator[None]:
    yield
    apply_ui_effects("normal")
    set_current(None)


def shades(host: QWidget) -> list[SheetShade]:
    """The dims over `host`, found without findChildren, which would hand a sheet to the window."""
    return [child for child in host.children() if isinstance(child, SheetShade)]


def drained(qapp: QApplication) -> None:  # noqa: F811
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def painted(shade: SheetShade) -> tuple[int, int, int, int]:
    """What the dim paints by itself, on nothing, as red, green, blue and alpha. (grab() would put it
    on an opaque backdrop and always read 255.)"""
    image = QImage(shade.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    shade.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return image.pixelColor(5, 5).getRgb()


def painted_alpha(shade: SheetShade) -> int:
    return painted(shade)[3]


def watch_the_build(
    monkeypatch: pytest.MonkeyPatch, window: NativeWindow, seen: list[dict]  # noqa: F811
) -> None:
    """HomeworkDialog records the dim as it is when its constructor starts, then builds as usual. exec
    is left out so the test decides what the sheet does next."""

    class Recorded(HomeworkDialog):
        def __init__(self, *args: object, **kwargs: object) -> None:
            on_screen = [shade for shade in shades(window) if shade.isVisible()]
            effect = on_screen[0].graphicsEffect() if on_screen else None
            seen.append(
                {
                    "dims": len(on_screen),
                    "covers": bool(on_screen) and on_screen[0].geometry() == window.rect(),
                    "opacity": getattr(effect, "opacity", None),
                }
            )
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(window_module, "HomeworkDialog", Recorded)


def test_the_dim_is_up_and_already_fading_before_the_sheet_is_built(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    apply_ui_effects("normal")
    seen: list[dict] = []
    watch_the_build(monkeypatch, window, seen)
    monkeypatch.setattr(HomeworkDialog, "exec", lambda self: 0)
    window._add_homework()
    assert len(seen) == 1
    assert seen[0]["dims"] == 1, "one dim is shown when the constructor starts"
    assert seen[0]["covers"], "and it covers the whole window"
    assert seen[0]["opacity"] is not None and seen[0]["opacity"] > 0, (
        "a frame of the fade has already been drawn, not only started"
    )


def test_the_sheet_adopts_the_dim_and_it_never_starts_over(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    apply_ui_effects("normal")
    made: list[HomeworkDialog] = []
    before: list[float] = []
    after: list[float] = []

    def run(dialog: HomeworkDialog) -> int:
        made.append(dialog)
        (dim,) = shades(window)
        before.append(dim.graphicsEffect().opacity)
        dialog.show()
        (only,) = shades(window)
        assert only is dim, "the sheet uses the dim it was given, not a second one"
        after.append(only.graphicsEffect().opacity)
        wait_until(qapp, lambda: not busy())
        return 0

    monkeypatch.setattr(HomeworkDialog, "exec", run)
    window._add_homework()
    assert after[0] >= before[0], "showing the sheet does not take the dim back to nothing"
    assert before[0] > 0
    free(made[0])


def test_the_dim_ends_at_the_same_black_it_always_did(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    apply_ui_effects("normal")
    assert round(255 * SHEET_DIM) == DIM_ALPHA
    landed: dict[str, object] = {}

    def run(dialog: HomeworkDialog) -> int:
        dialog.show()
        wait_until(qapp, lambda: not busy())
        (dim,) = shades(window)
        landed["effect"] = dim.graphicsEffect()
        landed["alpha"] = painted_alpha(dim)
        landed["colour"] = painted(dim)[:3]
        landed["covers"] = dim.geometry() == window.rect()
        return 0

    monkeypatch.setattr(HomeworkDialog, "exec", run)
    window._add_homework()
    assert landed["effect"] is None, "the fade has finished"
    assert landed["alpha"] == DIM_ALPHA
    assert landed["colour"] == (0, 0, 0)
    assert landed["covers"]


@pytest.mark.parametrize("style_key", ["plain", "night", "dashboard", "retro"])
def test_the_dim_is_the_same_in_every_design(qapp: QApplication, style_key: str) -> None:  # noqa: F811
    from desktop.native.widgets import dim_window

    apply_ui_effects("normal")
    host, _ctx = _host(qapp, style_key)
    dim = dim_window(host)
    # The dim waits for its sheet; the sheet that takes it lets the fade go on.
    sheet = Dialog(host, sheet=True)
    sheet.card_body("A sheet")
    sheet.show()
    wait_until(qapp, lambda: not busy())
    assert painted_alpha(dim) == DIM_ALPHA
    assert painted(dim)[:3] == (0, 0, 0)
    assert dim.geometry() == host.rect()
    sheet.close()
    free(sheet)
    free(host)


def test_closing_the_sheet_takes_the_dim_with_it(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    apply_ui_effects("normal")

    def run(dialog: HomeworkDialog) -> int:
        dialog.show()
        qapp.processEvents()
        assert any(shade.isVisible() for shade in shades(window))
        dialog.reject()
        return 0

    monkeypatch.setattr(HomeworkDialog, "exec", run)
    window._add_homework()
    drained(qapp)
    assert shades(window) == []


def test_escape_while_the_dim_is_still_fading_closes_it_cleanly(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    apply_ui_effects("normal")
    window.resize(1280, 800)
    qapp.processEvents()

    seen: dict[str, object] = {}

    def press() -> None:
        sheet = QApplication.activeModalWidget()
        seen["mid_fade"] = isinstance(sheet, Dialog) and busy()
        QTest.keyClick(sheet, Qt.Key.Key_Escape)

    real_exec = Dialog.exec

    def run(dialog: Dialog) -> int:
        # Started here, not at the click: the first frames of the dim are drawn while the sheet is built.
        QTimer.singleShot(10, press)
        return real_exec(dialog)

    monkeypatch.setattr(HomeworkDialog, "exec", run)
    window._add_homework()
    assert seen["mid_fade"], "Esc came while the fade was still running"
    wait_until(qapp, lambda: not busy())
    drained(qapp)
    assert shades(window) == []
    assert QApplication.activeModalWidget() is None


def test_with_animations_off_the_dim_is_there_at_once(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    apply_ui_effects("off")
    assert duration(EASE_MS) == 0
    seen: list[dict] = []
    watch_the_build(monkeypatch, window, seen)
    states: list[tuple[object, int]] = []

    def run(dialog: HomeworkDialog) -> int:
        (dim,) = shades(window)
        states.append((dim.graphicsEffect(), painted_alpha(dim)))
        assert not busy(), "nothing is moving"
        return 0

    monkeypatch.setattr(HomeworkDialog, "exec", run)
    window._add_homework()
    assert seen[0]["dims"] == 1 and seen[0]["opacity"] is None, "no fade: the dim is plain and whole"
    assert states == [(None, DIM_ALPHA)]


def test_a_sheet_that_fails_to_build_leaves_no_dim(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    apply_ui_effects("normal")

    class Broken(HomeworkDialog):
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("the form could not be built")

    monkeypatch.setattr(window_module, "HomeworkDialog", Broken)
    with pytest.raises(RuntimeError, match="could not be built"):
        window._add_homework()
    drained(qapp)
    assert shades(window) == []
    assert not busy()


def test_a_sheet_that_is_built_but_never_runs_leaves_no_dim(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    apply_ui_effects("normal")

    def run(_dialog: HomeworkDialog) -> int:
        raise RuntimeError("could not open")

    monkeypatch.setattr(HomeworkDialog, "exec", run)
    with pytest.raises(RuntimeError, match="could not open"):
        window._add_homework()
    drained(qapp)
    assert shades(window) == []


def test_every_opener_of_a_block_or_homework_sheet_dims_first(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """Each route into the add and edit sheets builds them behind the dim, not only the Add button."""
    from desktop.native.widgets import BlockDialog

    apply_ui_effects("normal")
    dims: list[int] = []

    def counted(original: type) -> type:
        class Counted(original):  # type: ignore[valid-type, misc]
            def __init__(self, *args: object, **kwargs: object) -> None:
                dims.append(sum(shade.isVisible() for shade in shades(window)))
                super().__init__(*args, **kwargs)

        return Counted

    monkeypatch.setattr(window_module, "HomeworkDialog", counted(HomeworkDialog))
    monkeypatch.setattr(window_module, "BlockDialog", counted(BlockDialog))
    monkeypatch.setattr(Dialog, "exec", lambda self: 0)
    openers: list[Callable[[], None]] = [
        window._add_homework,
        lambda: window._add_homework_due("2026-10-12"),
        lambda: window._add_fixed_at(1, 600),
        lambda: window._create_range(1, 600, 660),
        lambda: window._add_from_chip("assignments"),
        lambda: window._add_from_chip("class"),
    ]
    for opener in openers:
        opener()
        drained(qapp)
    assert dims == [1] * len(openers)
    assert shades(window) == []


def test_a_slow_build_does_not_make_the_dim_jump_ahead(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """The dim waits for the sheet: however long the build takes, the fade goes on from where its first
    frame left it, rather than leaping by the build's length in one frame."""
    import time

    apply_ui_effects("normal")
    seen: list[dict] = []

    class Slow(HomeworkDialog):
        def __init__(self, *args: object, **kwargs: object) -> None:
            (dim,) = shades(window)
            seen.append({"at_build": dim.graphicsEffect().opacity})
            super().__init__(*args, **kwargs)
            # Longer than the whole fade: a clock left running would be at the end by now.
            time.sleep(duration(EASE_MS) / 1000 + 0.05)

    made: list[HomeworkDialog] = []

    def run(dialog: HomeworkDialog) -> int:
        made.append(dialog)
        dialog.show()
        # Whatever is overdue runs now, with no time passing: a clock that ran through the build is
        # past its end and lands the dim in one step.
        for _ in range(3):
            qapp.processEvents()
        (dim,) = shades(window)
        effect = dim.graphicsEffect()
        seen.append({"at_show": None if effect is None else effect.opacity})
        wait_until(qapp, lambda: not busy())
        return 0

    monkeypatch.setattr(window_module, "HomeworkDialog", Slow)
    monkeypatch.setattr(Slow, "exec", run)
    window._add_homework()
    assert seen[0]["at_build"] > 0
    assert seen[1]["at_show"] is not None, "the fade is still going when the sheet shows"
    assert seen[1]["at_show"] == pytest.approx(seen[0]["at_build"], abs=0.05), (
        "the dim held still while it waited, and goes on from there"
    )
    made[0].close()
    free(made[0])


def test_the_dim_leaves_in_the_same_instant_as_its_sheet(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """0.18.5 #97: the dim lingered a frame after a sheet closed. It was only deleted later, so it stayed
    on screen until the event loop got to it."""
    seen: list[tuple[bool, bool]] = []

    def run(dialog: HomeworkDialog) -> int:
        dialog.show()
        qapp.processEvents()
        (dim,) = shades(window)
        wait_until(qapp, lambda: not busy())
        dialog.reject()
        # No event has run since the sheet went: the dim must already be gone with it.
        seen.append((dialog.isVisible(), dim.isVisible()))
        return 0

    for level in ("normal", "extra", "off"):
        apply_ui_effects(level)
        monkeypatch.setattr(HomeworkDialog, "exec", run)
        window._add_homework()
        drained(qapp)
    assert seen == [(False, False)] * 3


def test_a_sheet_closed_while_its_dim_is_still_fading_takes_the_dim_down_at_once(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    apply_ui_effects("extra")
    seen: list[tuple[bool, bool]] = []

    def run(dialog: HomeworkDialog) -> int:
        dialog.show()
        qapp.processEvents()
        (dim,) = shades(window)
        assert busy(), "the fade is still going"
        dialog.reject()
        seen.append((dialog.isVisible(), dim.isVisible()))
        return 0

    monkeypatch.setattr(HomeworkDialog, "exec", run)
    window._add_homework()
    drained(qapp)
    assert seen == [(False, False)]
    assert not busy(), "the fade went with the dim"
