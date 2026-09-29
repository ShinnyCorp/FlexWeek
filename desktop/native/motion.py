"""Short fades and slides that make a change easy to follow (decisions 28 to 35 of 0.17).

Nothing waits for an animation. The new page or week is live at once. A picture of what was there
before fades on top of it, and what comes in is painted faded and a little to one side until it
settles, while the widget itself already sits where it belongs: layouts keep it there and clicks find
it there, so a click is never slower than it was. The student's Animations setting picks the level,
and every design's own motion asks this module how far and how long.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPoint,
    QRect,
    QRectF,
    Qt,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsEffect, QLabel, QStackedWidget, QWidget


@dataclass(frozen=True)
class Level:
    """One Animations level. `pace` stretches every duration, 0 being at once; `reach` stretches
    every distance, 0 being fades only."""

    pace: float
    reach: float


# The stored ids (look.MOTION_LEVELS), which saved preferences and custom looks use. "extra" is
# shown as More. Reduce keeps the fades and nothing travels: no slide, rise, drift, zoom or lift.
LEVELS = {
    "normal": Level(1.0, 1.0),
    "extra": Level(1.45, 4 / 3),
    "reduce": Level(1.0, 0.0),
    "off": Level(0.0, 0.0),
}
# Every duration and distance below is Normal's; the level scales it.
# A page changing fades through: the old one out, then the new one in (decision 28).
PAGE_OUT_MS, PAGE_IN_MS = 90, 120
# How far Day, Week and Month slide as they change, toward the segment chosen.
SLIDE_PX = 12
# How far a picture of the old week drifts as it fades, the way the student went with ‹ ›.
DRIFT_PX = 16
# How far a notice, a sheet, a dialog and Ctrl+K rise as they appear (decision 31).
RISE_PX = 8
# Notices, dialogs, blocks settling after a plan: long enough to see where things went, short
# enough never to feel like waiting.
EASE_MS = 180
# Settings sliding in over the week, and how much the week behind it dims (decision 30).
OVER_MS, OVER_DIM = 200, 0.2
# The segmented control's selection sliding to the segment chosen (decision 32).
SEGMENT_MS = 160
FADE_NAME = "motionFade"
OUT = QEasingCurve(QEasingCurve.Type.OutCubic)

# The level the whole app runs at, for what has no window to ask: dialogs, designs, painted hours.
_app_level = "normal"


def motion_level(preference: object, look_default: object) -> str:
    """The student's Animations setting, or the look's own when they never chose one."""
    if preference in LEVELS:
        return str(preference)
    return str(look_default) if look_default in LEVELS else "normal"


def apply_ui_effects(level: str) -> None:
    """The app's level: Qt's own fades for menus and tooltips, on unless animations are off, its
    sliding dropdown lists only where things may travel, and the level `app_level` gives the rest."""
    global _app_level
    _app_level = level if level in LEVELS else "normal"
    on = duration(EASE_MS) > 0
    for effect in (
        Qt.UIEffect.UI_AnimateMenu,
        Qt.UIEffect.UI_FadeMenu,
        Qt.UIEffect.UI_AnimateTooltip,
        Qt.UIEffect.UI_FadeTooltip,
    ):
        QApplication.setEffectEnabled(effect, on)
    QApplication.setEffectEnabled(Qt.UIEffect.UI_AnimateCombo, moves())


def app_level() -> str:
    return _app_level


def duration(ms: int, level: str | None = None) -> int:
    """How long Normal's `ms` takes at `level`, or at the app's; 0 is at once."""
    return round(ms * LEVELS[level or _app_level].pace)


def distance(px: int, level: str | None = None) -> int:
    """How far Normal's `px` goes at `level`, or at the app's; 0 under Reduce and Off."""
    return round(px * LEVELS[level or _app_level].reach)


def moves(level: str | None = None) -> bool:
    """Whether things travel at `level`, or at the app's, rather than only fading or not moving."""
    return LEVELS[level or _app_level].reach > 0


class Shift(QGraphicsEffect):
    """Paints its widget at `opacity`, `offset` pixels from where it is. The widget itself does not
    move, so its layout keeps it in place and a click lands where it will be. `far` is the furthest
    it is ever painted from home, which Qt needs to know to repaint enough."""

    def __init__(self, parent: QWidget, far: QPoint) -> None:
        super().__init__(parent)
        self.opacity = 1.0
        self.offset = QPoint()
        self._far = far

    def set(self, opacity: float, offset: QPoint) -> None:
        self.opacity, self.offset = opacity, offset
        self.update()

    def boundingRectFor(self, rect: QRectF) -> QRectF:  # noqa: N802
        return rect.united(rect.translated(self._far))

    def draw(self, painter: QPainter) -> None:
        if self.opacity <= 0:
            return
        if self.opacity >= 1 and self.offset.isNull():
            self.drawSource(painter)
            return
        system = Qt.CoordinateSystem.LogicalCoordinates
        pixmap = self.sourcePixmap(system, QPoint(), QGraphicsEffect.PixmapPadMode.NoPad)
        painter.save()
        painter.setOpacity(painter.opacity() * self.opacity)
        painter.drawPixmap(self.sourceBoundingRect(system).topLeft().toPoint() + self.offset, pixmap)
        painter.restore()


class Dim(QWidget):
    """Black laid over what is under it at `share` of OVER_DIM, letting the pointer through."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.share = 0.0

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, round(255 * OVER_DIM * self.share)))
        painter.end()


def settle(widget: QWidget) -> None:
    """End an animation still running on `widget` where it would have ended, so a second one starts
    from where the widget belongs. Stopping one does not emit `finished`, so its tidying runs here."""
    running = getattr(widget, "_motion_running", None)
    widget._motion_running = None  # type: ignore[attr-defined]
    if running is None:
        return
    animation, done = running
    with contextlib.suppress(RuntimeError):
        animation.finished.disconnect(done)
        animation.stop()
    done()


def _run(owner: QWidget, total: int, step: Callable[[float], None], done: Callable[[], None]) -> None:
    """Call `step` with the milliseconds gone, from 0 to `total`, each frame, then `done`. The clock
    belongs to `owner`, and `settle(owner)` ends it early."""
    step(0.0)
    clock = QVariantAnimation(owner)
    clock.setStartValue(0.0)
    clock.setEndValue(float(total))
    clock.setDuration(total)
    clock.valueChanged.connect(lambda value: step(float(value)))

    def finish() -> None:
        owner._motion_running = None  # type: ignore[attr-defined]
        done()

    clock.finished.connect(finish)
    owner._motion_running = (clock, finish)  # type: ignore[attr-defined]
    clock.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def between(start: QRectF, end: QRectF, share: float) -> QRectF:
    """The rectangle `share` of the way from `start` to `end`."""
    return QRectF(
        start.x() + (end.x() - start.x()) * share,
        start.y() + (end.y() - start.y()) * share,
        start.width() + (end.width() - start.width()) * share,
        start.height() + (end.height() - start.height()) * share,
    )


def _along(at: float, wait: int, length: int) -> float:
    """How far along, eased, is something that starts `wait` milliseconds in and takes `length`."""
    if at < wait:
        return 0.0
    return OUT.valueForProgress((at - wait) / length) if length else 1.0


def clear_fades(host: QWidget) -> None:
    """Drop pictures still fading over `host`, and dimming left from Settings sliding away, so a new
    picture never captures an old one."""
    direct = Qt.FindChildOption.FindDirectChildrenOnly
    for leftover in (*host.findChildren(QLabel, FADE_NAME, direct), *host.findChildren(Dim, options=direct)):
        leftover.hide()
        leftover.deleteLater()


def hold_picture(host: QWidget, level: str, area: QRect | None = None) -> QLabel | None:
    """A picture of `host`, or of `area` of it, as it looks now, laid over it until it is let go.
    None when nothing would fade."""
    if duration(EASE_MS, level) == 0 or not host.isVisible() or host.width() <= 0 or host.height() <= 0:
        return None
    clear_fades(host)
    shown = area if area is not None else host.rect()
    picture = QLabel(host)
    picture.setObjectName(FADE_NAME)
    picture.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    picture.setPixmap(host.grab(shown))
    picture.setGeometry(shown)
    picture.show()
    picture.raise_()
    return picture


def trim_picture(picture: QLabel, area: QRect) -> None:
    """Keep only `area` of the picture, given in its host's coordinates."""
    inside = area.translated(-picture.pos()) & picture.rect()
    whole = picture.pixmap()
    ratio = whole.devicePixelRatio()
    kept = whole.copy(
        QRect(round(inside.x() * ratio), round(inside.y() * ratio),
              round(inside.width() * ratio), round(inside.height() * ratio))
    )
    kept.setDevicePixelRatio(ratio)
    picture.setPixmap(kept)
    picture.setGeometry(inside.translated(picture.pos()))


def fade_away(picture: QLabel | None, level: str, *, ms: int = EASE_MS, drift: int = 0) -> None:
    """Fade `picture` out in Normal's `ms`, drifting `drift` of Normal's pixels sideways (to the left
    when negative) where things may travel, then delete it."""
    if picture is None:
        return
    length = duration(ms, level)
    if length == 0:
        picture.deleteLater()
        return
    end = QPoint(distance(drift, level), 0)
    effect = Shift(picture, end)
    picture.setGraphicsEffect(effect)

    def step(at: float) -> None:
        share = _along(at, 0, length)
        effect.set(1 - share, end * share)

    _run(picture, length, step, picture.deleteLater)


def appear(
    widget: QWidget,
    level: str,
    *,
    rise: bool = False,
    shift: int = 0,
    delay_ms: int = 0,
    ms: int = EASE_MS,
) -> None:
    """Fade `widget` in where it already is. A notice or a sheet can rise into place, and a page can
    come in from `shift` pixels to the side. `delay_ms` keeps it unseen first, to follow the page
    before it out or to stagger a list. All in Normal's pixels and milliseconds. A window's insides
    have nothing under them to fade over, so a dialog fades its content, not itself."""
    settle(widget)
    wait, length = duration(delay_ms, level), duration(ms, level)
    if wait + length == 0 or not widget.isVisible():
        return
    start = QPoint(distance(shift, level), distance(RISE_PX, level) if rise else 0)
    effect = Shift(widget, start)
    widget.setGraphicsEffect(effect)

    def step(at: float) -> None:
        share = _along(at, wait, length)
        effect.set(share, start * (1 - share))

    # An effect left in place makes every later repaint of the widget go through it.
    _run(widget, wait + length, step, lambda: widget.setGraphicsEffect(None))


def fade_through(picture: QLabel | None, incoming: Iterable[QWidget], level: str, direction: int = 0) -> None:
    """The picture of what was there out, then what replaced it in (decision 28): the old fades in
    PAGE_OUT_MS and each of `incoming` in PAGE_IN_MS after it, so two pages are never read on top of
    each other. With a `direction` (1 forward, -1 back) the old drifts away from it and the new
    slides in from its side."""
    if picture is None:
        return
    fade_away(picture, level, ms=PAGE_OUT_MS, drift=-direction * SLIDE_PX)
    for widget in incoming:
        appear(widget, level, shift=direction * SLIDE_PX, delay_ms=PAGE_OUT_MS, ms=PAGE_IN_MS)


def switch_page(stack: QStackedWidget, page: QWidget, level: str, direction: int = 0) -> None:
    """Show `page` at once, the page it replaces fading through to it."""
    if stack.currentWidget() is page:
        return
    # A page still on its way in is taken as it will be, not half faded.
    settle(stack.currentWidget())
    picture = hold_picture(stack, level)
    stack.setCurrentWidget(page)
    fade_through(picture, [page], level, direction)


def slide_over(stack: QStackedWidget, page: QWidget, level: str, *, back: bool = False) -> None:
    """Show `page` as Settings is shown (decision 30): it slides in from the right over the page it
    covers, which dims. `back` slides the page on screen off to the right again and brightens the
    one it uncovers. Where things may not travel the pages fade through instead, since one read
    through the other is what the slide is for avoiding."""
    if not moves(level):
        switch_page(stack, page, level)
        return
    if stack.currentWidget() is page:
        return
    settle(stack.currentWidget())
    settle(page)
    picture = hold_picture(stack, level)
    stack.setCurrentWidget(page)
    if picture is None:
        return
    length = duration(OVER_MS, level)
    far = QPoint(stack.width(), 0)
    dim = Dim(stack if back else picture)
    dim.setGeometry(stack.rect() if back else picture.rect())
    dim.show()
    # What moves: the picture of the page going away, or the page coming in, over the one that stays.
    moving = picture if back else page
    if back:
        dim.stackUnder(picture)
    else:
        picture.stackUnder(page)
    effect = Shift(moving, far)
    moving.setGraphicsEffect(effect)

    def step(at: float) -> None:
        share = _along(at, 0, length)
        effect.set(1.0, far * (share if back else 1 - share))
        dim.share = 1 - share if back else share
        dim.update()

    def done() -> None:
        dim.deleteLater()
        picture.deleteLater()
        if not back:
            page.setGraphicsEffect(None)

    _run(moving, length, step, done)


def glide(widget: QWidget, target: QRect, level: str, *, ms: int = EASE_MS + 60) -> None:
    """Move and resize `widget` to `target`, easing there rather than jumping where things may
    travel."""
    settle(widget)
    length = duration(ms, level)
    if length == 0 or not moves(level) or not widget.isVisible() or widget.geometry() == target:
        widget.setGeometry(target)
        return
    start = QRectF(widget.geometry())

    def step(at: float) -> None:
        widget.setGeometry(between(start, QRectF(target), _along(at, 0, length)).toRect())

    _run(widget, length, step, lambda: widget.setGeometry(target))


def vanish(widget: QWidget, level: str) -> None:
    """Fade `widget` out, then hide it."""
    settle(widget)
    length = duration(EASE_MS, level)
    if length == 0 or not widget.isVisible():
        widget.hide()
        return
    effect = Shift(widget, QPoint())
    widget.setGraphicsEffect(effect)
    fading = QEasingCurve(QEasingCurve.Type.InCubic)

    def step(at: float) -> None:
        effect.set(1 - fading.valueForProgress(at / length), QPoint())

    def done() -> None:
        widget.hide()
        widget.setGraphicsEffect(None)

    _run(widget, length, step, done)
