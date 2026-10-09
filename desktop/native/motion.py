"""Short fades and slides that make a change easy to follow (decisions 28 to 35 of 0.17).

Nothing waits for an animation. The new page or week is live at once. A picture of what was there
before fades on top of it, and what comes in is painted faded and a little to one side until it
settles, while the widget itself already sits where it belongs: layouts keep it there and clicks find
it there, so a click is never slower than it was. The student's Animations setting picks the level,
and every design's own motion asks this module how far and how long.
"""

from __future__ import annotations

import contextlib
import weakref
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QElapsedTimer,
    QEvent,
    QObject,
    QPoint,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QGraphicsEffect, QLabel, QStackedWidget, QWidget


@dataclass(frozen=True)
class Level:
    """One Animations level. `pace` stretches every duration, 0 being at once; `reach` stretches
    every distance, 0 being fades only."""

    pace: float
    reach: float


# The stored ids (look.MOTION_LEVELS), which saved preferences and custom looks use. "extra" is
# shown as More. Reduce keeps the fades and nothing travels: no slide, rise, drift, zoom or lift.
# More is 2.5 times as slow, so the standard ease of 180 ms is 450 ms: at 1.45 it was only 260 ms and
# hard to tell from Normal.
LEVELS = {
    "normal": Level(1.0, 1.0),
    "extra": Level(2.5, 4 / 3),
    "reduce": Level(1.0, 0.0),
    "off": Level(0.0, 0.0),
}
# Every duration and distance below is Normal's; the level scales it.
# A page changing: the old one fades out steadily and the new one comes in PAGE_IN_AFTER_MS behind it,
# so the window is never empty (Grok Bot's 0.17.0 audit found 3 or 4 blank frames when the new page
# waited for the old one to go, as decision 28 had it).
PAGE_OUT_MS, PAGE_IN_MS, PAGE_IN_AFTER_MS = 120, 160, 30
# How far Day, Week and Month slide as they change, toward the segment chosen. At 12 no slide was seen.
SLIDE_PX = 24
LINEAR = QEasingCurve(QEasingCurve.Type.Linear)
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
# The picture of a page sliding in over another, as Settings does.
SLIDE_NAME = "motionSlide"
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


def frame_interval_ms(rate: float) -> int:
    """How many milliseconds between frames at `rate` Hz. An unknown rate, or one too low to be a
    screen, is 60. The interval is never 0, which would run the next frame inside the same turn."""
    if rate <= 1:
        return round(1000 / 60)
    return max(1, round(1000 / rate))


def screen_rate(widget: QWidget | None) -> float:
    """The refresh rate of the screen `widget` is on, or 0 when Qt cannot say. Called on the class:
    a focus panel keeps a button on `screen`, which would hide the method."""
    if widget is None:
        return 0.0
    screen = QWidget.screen(widget)
    if screen is None:
        return 0.0
    return float(screen.refreshRate())


def _fit_for_picture(widget: QWidget) -> None:
    """Give `widget` the size it will have on screen before a picture is taken of it. A stacked
    page grabbed at its old size is drawn once small, then resized, then drawn again while it
    fades."""
    parent = widget.parentWidget()
    if isinstance(parent, QStackedWidget):
        area = parent.size()
        if area.width() > 0 and area.height() > 0 and widget.size() != area:
            widget.resize(area)
    widget.ensurePolished()
    layout = widget.layout()
    if layout is not None:
        layout.activate()


def _kept(widget: QWidget) -> QPixmap | None:
    """One picture of `widget` as it looks now. A label that already holds a picture gives that,
    rather than drawing it again."""
    if isinstance(widget, QLabel):
        shot = widget.pixmap()
        if not shot.isNull():
            return shot
    shot = widget.grab()
    return None if shot.isNull() else shot


class Shift(QGraphicsEffect):
    """Paints its widget at `opacity`, `offset` pixels from where it is. The widget itself does not
    move, so its layout keeps it in place and a click lands where it will be. `far` is the furthest
    it is ever painted from home, which Qt needs to know to repaint enough. `picture`, when it is
    given, is drawn on each frame instead of asking the widget to paint itself again."""

    def __init__(self, parent: QWidget, far: QPoint, picture: QPixmap | None = None) -> None:
        super().__init__(parent)
        self.opacity = 1.0
        self.offset = QPoint()
        self._far = far
        self._picture = picture if picture is not None and not picture.isNull() else None

    def set(self, opacity: float, offset: QPoint) -> None:
        self.opacity, self.offset = opacity, offset
        self.update()

    def drop_picture(self) -> None:
        """Draw the live widget from now on, so typing or a click is seen during the fade."""
        if self._picture is None:
            return
        self._picture = None
        self.update()

    def boundingRectFor(self, rect: QRectF) -> QRectF:  # noqa: N802
        return rect.united(rect.translated(self._far))

    def draw(self, painter: QPainter) -> None:
        if self.opacity <= 0:
            return
        if self.opacity >= 1 and self.offset.isNull():
            self.drawSource(painter)
            return
        painter.save()
        painter.setOpacity(painter.opacity() * self.opacity)
        if self._picture is not None:
            painter.drawPixmap(self.offset, self._picture)
        else:
            system = Qt.CoordinateSystem.LogicalCoordinates
            pixmap = self.sourcePixmap(system, QPoint(), QGraphicsEffect.PixmapPadMode.NoPad)
            origin = self.sourceBoundingRect(system).topLeft().toPoint()
            painter.drawPixmap(origin + self.offset, pixmap)
        painter.restore()


_started = QElapsedTimer()
_started.start()


def now_ms() -> int:
    """The time every Clock reads, in milliseconds from any fixed start. Tests put their own over this
    name, so an animation can be moved to an exact moment instead of waited for."""
    return int(_started.elapsed())


# Every clock still running, so slow work can wait until nothing is moving.
_RUNNING: weakref.WeakSet[Clock] = weakref.WeakSet()


def busy() -> bool:
    """Whether any animation is running now on a widget that is on screen."""
    for clock in list(_RUNNING):
        try:
            state = clock.state()
            if state == QAbstractAnimation.State.Stopped:
                _RUNNING.discard(clock)
                continue
            if state == QAbstractAnimation.State.Paused:
                continue
            parent = clock.parent()
            if isinstance(parent, QWidget) and not parent.isVisible():
                continue
            return True
        except RuntimeError:
            _RUNNING.discard(clock)
    return False


class Clock(QObject):
    """A frame clock for one animation. Qt's own animation clock stays near 60 Hz, and this PySide
    has no way to replace it, so a precise timer follows the screen. The time it reports is how long
    the animation has been running, so a late frame still lands on the right part of the easing."""

    finished = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._total = 0
        self._step: Callable[[float], None] | None = None
        self._base = 0
        self._stopped = False
        self._done = False
        self._paused = False
        # When this stretch of the animation began on now_ms's time; None before it first starts.
        self._since: int | None = None
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self.destroyed.connect(self._dropped)

    def start(self, total: int, step: Callable[[float], None]) -> None:
        self._total = total
        self._step = step
        self._base = 0
        self._stopped = False
        self._done = False
        self._paused = False
        self._since = now_ms()
        self._retarget()
        _RUNNING.add(self)
        self._timer.start()

    def stop(self) -> None:
        self._stopped = True
        self._paused = False
        self._timer.stop()
        _RUNNING.discard(self)

    def pause(self) -> None:
        if self._paused or self._done or self._stopped or not self._timer.isActive():
            return
        self._base += self._gone()
        self._paused = True
        self._timer.stop()

    def resume(self) -> None:
        if not self._paused or self._done or self._stopped:
            return
        self._paused = False
        self._since = now_ms()
        self._timer.start()

    def duration(self) -> int:
        return self._total

    def currentTime(self) -> int:  # noqa: N802
        if self._paused or self._since is None:
            return min(self._base, self._total)
        return min(self._base + self._gone(), self._total)

    def state(self) -> QAbstractAnimation.State:
        if self._paused:
            return QAbstractAnimation.State.Paused
        if self._timer.isActive():
            return QAbstractAnimation.State.Running
        return QAbstractAnimation.State.Stopped

    def setCurrentTime(self, ms: int) -> None:  # noqa: N802
        """Jump to `ms` milliseconds in, and finish when that is the end."""
        self._base = ms
        self._since = now_ms()
        self._apply(self._base)

    def interval(self) -> int:
        return self._timer.interval()

    def _gone(self) -> int:
        return 0 if self._since is None else now_ms() - self._since

    def _dropped(self) -> None:
        _RUNNING.discard(self)

    def _retarget(self) -> None:
        parent = self.parent()
        gap = frame_interval_ms(screen_rate(parent if isinstance(parent, QWidget) else None))
        if self._timer.interval() != gap:
            self._timer.setInterval(gap)

    def _tick(self) -> None:
        if self._stopped or self._done:
            return
        self._retarget()
        self._apply(self._base + self._gone())

    def _apply(self, ms: int) -> None:
        if self._done or self._step is None:
            return
        if ms >= self._total:
            self._done = True
            self._timer.stop()
            _RUNNING.discard(self)
            self._step(float(self._total))
            self.finished.emit()
            return
        self._step(float(ms))


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
    kick = getattr(widget, "_motion_live", None)
    if kick is not None:
        kick.detach()
        widget._motion_live = None  # type: ignore[attr-defined]
    running = getattr(widget, "_motion_running", None)
    widget._motion_running = None  # type: ignore[attr-defined]
    if running is None:
        return
    animation, done = running
    with contextlib.suppress(RuntimeError):
        animation.finished.disconnect(done)
        animation.stop()
    done()
    with contextlib.suppress(RuntimeError):
        animation.deleteLater()


def _run(owner: QWidget, total: int, step: Callable[[float], None], done: Callable[[], None]) -> None:
    """Call `step` with the milliseconds gone, from 0 to `total`, each frame, then `done`. The first
    call is immediate, so the fade is on screen before the first interval. The clock belongs to
    `owner`, and `settle(owner)` ends it early."""
    if total <= 0:
        done()
        return
    step(0.0)
    clock = Clock(owner)

    def finish() -> None:
        owner._motion_running = None  # type: ignore[attr-defined]
        done()
        with contextlib.suppress(RuntimeError):
            clock.deleteLater()

    clock.finished.connect(finish)
    owner._motion_running = (clock, finish)  # type: ignore[attr-defined]
    clock.start(total, step)


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
    for leftover in (
        *host.findChildren(QLabel, FADE_NAME, direct),
        *host.findChildren(QLabel, SLIDE_NAME, direct),
        *host.findChildren(Dim, options=direct),
    ):
        leftover.hide()
        leftover.deleteLater()


def raise_pictures(host: QWidget) -> None:
    """Put the pictures and dims over `host` back on top, in the order they were. A widget given a new
    parent, or raised, lands above them and was drawn over the picture that is meant to cover it."""
    for child in host.children():
        picture = isinstance(child, QLabel) and child.objectName() in (FADE_NAME, SLIDE_NAME)
        if picture or isinstance(child, Dim):
            child.raise_()


def hold_picture(
    host: QWidget, level: str, area: QRect | None = None, *, beside: bool = False
) -> QLabel | None:
    """A picture of `host`, or of `area` of it, as it looks now, laid over it until it is let go.
    None when nothing would fade. `beside` is a second picture of the same change, which keeps the
    first rather than clearing it as a stale one."""
    if duration(EASE_MS, level) == 0 or not host.isVisible() or host.width() <= 0 or host.height() <= 0:
        return None
    if not beside:
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
        QRect(
            round(inside.x() * ratio),
            round(inside.y() * ratio),
            round(inside.width() * ratio),
            round(inside.height() * ratio),
        )
    )
    kept.setDevicePixelRatio(ratio)
    picture.setPixmap(kept)
    picture.setGeometry(inside.translated(picture.pos()))


def fade_away(
    picture: QLabel | None, level: str, *, ms: int = EASE_MS, drift: int = 0, steady: bool = False
) -> None:
    """Fade `picture` out in Normal's `ms`, drifting `drift` of Normal's pixels sideways (to the left
    when negative) where things may travel, then delete it. `steady` fades it at an even pace rather
    than fast first, for a page whose successor is still coming in under it."""
    if picture is None:
        return
    length = duration(ms, level)
    if length == 0:
        picture.deleteLater()
        return
    end = QPoint(distance(drift, level), 0)
    effect = Shift(picture, end, _kept(picture))
    picture.setGraphicsEffect(effect)
    fading = LINEAR if steady else OUT

    def step(at: float) -> None:
        share = fading.valueForProgress(at / length)
        effect.set(1 - share, end * share)

    _run(picture, length, step, picture.deleteLater)


class _LiveOnInput(QObject):
    """The first key or click on `widget` drops its fade picture so the live widget shows through."""

    def __init__(self, effect: Shift, widget: QWidget) -> None:
        super().__init__(widget)
        self._effect = effect
        self._widget = widget
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress):
            return False
        if not isinstance(watched, QWidget):
            return False
        if watched is self._widget or self._widget.isAncestorOf(watched):
            self._effect.drop_picture()
            self.detach()
        return False

    def detach(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)


def appear(
    widget: QWidget,
    level: str,
    *,
    rise: bool = False,
    shift: int = 0,
    delay_ms: int = 0,
    ms: int = EASE_MS,
    grow: bool = False,
) -> None:
    """Fade `widget` in where it already is. A notice or a sheet can rise into place, and a page can
    come in from `shift` pixels to the side. `delay_ms` keeps it unseen first, to follow the page
    before it out or to stagger a list. All in Normal's pixels and milliseconds. A window's insides
    have nothing under them to fade over, so a dialog fades its content, not itself. `grow` is for
    a widget a layout has just made room for: where things may travel its height opens from nothing,
    so what the layout puts below it moves with it rather than jumping."""
    settle(widget)
    wait, length = duration(delay_ms, level), duration(ms, level)
    if wait + length == 0 or not widget.isVisible():
        return
    start = QPoint(distance(shift, level), distance(RISE_PX, level) if rise else 0)
    live = grow and moves(level)
    if not live:
        _fit_for_picture(widget)
    # Growing changes the widget's height on every frame, so that one has to be drawn live. Anything
    # else is painted once and the picture moves.
    effect = Shift(widget, start, None if live else _kept(widget))
    widget.setGraphicsEffect(effect)
    kick = None if live else _LiveOnInput(effect, widget)
    widget._motion_live = kick  # type: ignore[attr-defined]
    full = widget.sizeHint().height() if live else 0
    limit = widget.maximumHeight()

    def step(at: float) -> None:
        share = _along(at, wait, length)
        effect.set(share, start * (1 - share))
        if full:
            widget.setMaximumHeight(round(full * share))

    def done() -> None:
        if kick is not None:
            kick.detach()
        widget._motion_live = None  # type: ignore[attr-defined]
        # An effect left in place makes every later repaint of the widget go through it.
        widget.setGraphicsEffect(None)
        widget.setMaximumHeight(limit)

    _run(widget, wait + length, step, done)


def fade_through(picture: QLabel | None, incoming: Iterable[QWidget], level: str, direction: int = 0) -> None:
    """The picture of what was there out and what replaced it in: the old fades steadily in
    PAGE_OUT_MS and each of `incoming` comes in over PAGE_IN_MS, PAGE_IN_AFTER_MS behind it, so the
    window is never empty and the two are only seen together faintly and briefly. With a `direction`
    (1 forward, -1 back) the old drifts away from it and the new slides in from its side, so the two
    are moving apart while both show."""
    if picture is None:
        return
    fade_away(picture, level, ms=PAGE_OUT_MS, drift=-direction * SLIDE_PX, steady=True)
    for widget in incoming:
        appear(widget, level, shift=direction * SLIDE_PX, delay_ms=PAGE_IN_AFTER_MS, ms=PAGE_IN_MS)


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
    coming = None
    if not back:
        _fit_for_picture(page)
        coming = page.grab()
    _slide_pictures(stack, picture, stack.rect(), level, back=back, live=page, coming=coming)


def slide_view(host: QWidget, picture: QLabel, live: QWidget, level: str, *, back: bool = False) -> None:
    """Slide a view in or out as `slide_over` slides a page, for a view that lives inside `host`
    rather than on a page of its own. `picture` is the one `hold_picture` took of `host` (or of an
    area of it) before the view changed; `live` is the part of `host` that changed. Going in, the
    picture of what was there stays under a dim and a picture of the new view slides over it. With
    `back`, the picture is of the view going away: it slides off over the live view, which brightens."""
    coming = None
    if not back:
        # The held picture lies over the very thing being grabbed.
        picture.hide()
        coming = host.grab(picture.geometry())
        picture.show()
    _slide_pictures(host, picture, picture.geometry(), level, back=back, live=live, coming=coming)


def _slide_pictures(
    host: QWidget,
    picture: QLabel,
    area: QRect,
    level: str,
    *,
    back: bool,
    live: QWidget,
    coming: QPixmap | None,
) -> None:
    """The slide itself, over `area` of `host`. `picture` is held of what was there. Going in,
    `coming` is a picture of what slides over it and `live` lies under both, with its painting
    waiting, until it lands; going back, `picture` is what slides away. The clock is `live`'s going
    in, so settling it ends the slide."""
    length = duration(OVER_MS, level)
    far = QPoint(area.width(), 0)
    dim = Dim(host if back else picture)
    dim.setGeometry(area if back else picture.rect())
    dim.show()
    # What moves is a picture either way: of the page going away, or of the page coming in. The page
    # coming in used to move itself, drawn through an effect, which painted the whole of Settings
    # again for every frame and made it stutter in.
    if back:
        moving = picture
        dim.stackUnder(picture)
        effect = Shift(moving, far, _kept(moving))
        moving.setGraphicsEffect(effect)
    else:
        moving = QLabel(host)
        moving.setObjectName(SLIDE_NAME)
        moving.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        moving.setPixmap(coming)
        # The page lies under both pictures until the slide ends. Qt would still paint it for every
        # frame the picture above it moves, so its painting waits for the landing.
        live.setUpdatesEnabled(False)
        moving.setGeometry(area.translated(far))
        moving.show()
        moving.raise_()

    def step(at: float) -> None:
        share = _along(at, 0, length)
        if back:
            effect.set(1.0, far * share)
        else:
            moving.move(area.x() + round(far.x() * (1 - share)), area.y())
        dim.share = 1 - share if back else share
        dim.update()

    def regrab() -> None:
        # The held picture and the dim on it lie over the very thing being grabbed.
        picture.hide()
        moving.hide()
        # A widget whose painting waits is drawn blank into a picture.
        live.setUpdatesEnabled(True)
        shot = host.grab(area)
        live.setUpdatesEnabled(False)
        picture.show()
        moving.show()
        moving.setPixmap(shot)

    def done() -> None:
        dim.deleteLater()
        picture.deleteLater()
        if not back:
            live._slide_regrab = None  # type: ignore[attr-defined]
            live.setUpdatesEnabled(True)
            moving.deleteLater()

    if not back:
        live._slide_regrab = regrab  # type: ignore[attr-defined]
    # The clock is the page's when it comes in, so settling the page ends its slide.
    _run(picture if back else live, length, step, done)


def sliding_in(live: QWidget) -> bool:
    """Whether a view is sliding in over the desk on `live`."""
    return getattr(live, "_slide_regrab", None) is not None


def retake_slide(live: QWidget) -> None:
    """If a view is sliding in over the desk, take its picture again: what it shows has changed since
    the slide began, such as a month whose data has just arrived. Nothing otherwise."""
    regrab = getattr(live, "_slide_regrab", None)
    if regrab is not None:
        regrab()


def slide_down(widget: QWidget, level: str, *, ms: int = EASE_MS) -> None:
    """Slide `widget` down into `target` from just above it. The widget keeps its full height on every
    frame, over what stays underneath, instead of opening layout room first."""
    settle(widget)
    target = widget.geometry()
    length = duration(ms, level)
    if length == 0 or not moves(level) or target.height() <= 0:
        widget.setGeometry(target)
        widget.show()
        return
    start = QRect(target.x(), target.y() - target.height(), target.width(), target.height())
    widget.setGeometry(start)
    widget.show()
    glide(widget, target, level, ms=ms)


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
    effect = Shift(widget, QPoint(), _kept(widget))
    widget.setGraphicsEffect(effect)
    fading = QEasingCurve(QEasingCurve.Type.InCubic)

    def step(at: float) -> None:
        effect.set(1 - fading.valueForProgress(at / length), QPoint())

    def done() -> None:
        widget.hide()
        widget.setGraphicsEffect(None)

    _run(widget, length, step, done)
