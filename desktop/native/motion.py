"""Short fades and slides that make a change easy to follow.

Nothing waits for an animation. The new page or week is live at once, and only a picture of what was
there before fades away on top of it, so a click is never slower than it was. The student's
Animations setting picks the level, and Off turns every one of them off.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSequentialAnimationGroup,
    Qt,
)
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QLabel, QStackedWidget, QWidget

LEVELS = ("off", "normal", "extra")
# Long enough to see where things went, short enough never to feel like waiting.
DURATION_MS = {"off": 0, "normal": 180, "extra": 260}
# How far a picture of the old week drifts as it fades, in the direction the student moved.
DRIFT_PX = {"off": 0, "normal": 16, "extra": 32}
# How far a notice rises as it appears.
RISE_PX = {"off": 0, "normal": 8, "extra": 14}
# How far a page of setup travels as it comes in, from the side the student is heading.
SLIDE_PX = {"off": 0, "normal": 28, "extra": 48}
# How much of a slide the old page takes to fade, and how far in the new one starts to appear.
FADE_THROUGH_OUT, FADE_THROUGH_DELAY = 0.6, 0.3
FADE_NAME = "motionFade"

# The level the whole app runs at, for what has no window to ask: dialogs and painted hours.
_app_level = "normal"


def motion_level(preference: object, look_default: object) -> str:
    """The student's Animations setting, or the look's own when they never chose one."""
    if preference in LEVELS:
        return str(preference)
    return str(look_default) if look_default in LEVELS else "normal"


def apply_ui_effects(level: str) -> None:
    """The app's level: Qt's own fades for menus, dropdown lists and tooltips, on unless animations
    are off, and the level `app_level` gives dialogs and the hours."""
    global _app_level
    _app_level = level if level in LEVELS else "normal"
    on = _app_level != "off"
    for effect in (
        Qt.UIEffect.UI_AnimateMenu,
        Qt.UIEffect.UI_FadeMenu,
        Qt.UIEffect.UI_AnimateCombo,
        Qt.UIEffect.UI_AnimateTooltip,
        Qt.UIEffect.UI_FadeTooltip,
    ):
        QApplication.setEffectEnabled(effect, on)


def app_level() -> str:
    return _app_level


def clear_fades(host: QWidget) -> None:
    """Drop pictures still fading over `host`, so a new one never captures an old one."""
    for picture in host.findChildren(QLabel, FADE_NAME, Qt.FindChildOption.FindDirectChildrenOnly):
        picture.hide()
        picture.deleteLater()


def hold_picture(host: QWidget, level: str) -> QLabel | None:
    """A picture of `host` as it looks now, laid over it until `fade_away` lets it go."""
    if DURATION_MS.get(level, 0) == 0 or not host.isVisible() or host.width() <= 0 or host.height() <= 0:
        return None
    clear_fades(host)
    picture = QLabel(host)
    picture.setObjectName(FADE_NAME)
    picture.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    picture.setPixmap(host.grab())
    picture.setGeometry(host.rect())
    picture.show()
    picture.raise_()
    return picture


def fade_away(picture: QLabel | None, level: str, direction: int = 0, share: float = 1.0) -> None:
    """Fade `picture` out, drifting it by `direction` (-1 left, 1 right, 0 still), then delete it.
    `share` shortens the fade to that part of the level's duration."""
    if picture is None:
        return
    duration = round(DURATION_MS.get(level, 0) * share)
    if duration == 0:
        picture.deleteLater()
        return
    effect = QGraphicsOpacityEffect(picture)
    picture.setGraphicsEffect(effect)
    group = QParallelAnimationGroup(picture)
    fade = QPropertyAnimation(effect, b"opacity", group)
    fade.setDuration(duration)
    fade.setStartValue(1.0)
    fade.setEndValue(0.0)
    fade.setEasingCurve(QEasingCurve.Type.OutCubic)
    group.addAnimation(fade)
    if direction:
        slide = QPropertyAnimation(picture, b"pos", group)
        slide.setDuration(duration)
        slide.setStartValue(picture.pos())
        slide.setEndValue(picture.pos() + QPoint(direction * DRIFT_PX[level], 0))
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(slide)
    group.finished.connect(picture.deleteLater)
    group.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def switch_page(stack: QStackedWidget, page: QWidget, level: str) -> None:
    """Show `page` at once, fading in under a picture of the page it replaces as that fades away: a
    crossfade, so a page that lays itself out a moment late is never hidden by a stale picture."""
    if stack.currentWidget() is page:
        return
    picture = hold_picture(stack, level)
    stack.setCurrentWidget(page)
    if picture is not None:
        appear(page, level)
    fade_away(picture, level)


def slide_page(stack: QStackedWidget, page: QWidget, level: str, direction: int) -> None:
    """Show `page` at once. It comes in from the side the student is heading (1 forward, -1 back)
    while the page it replaces fades away toward the other side."""
    if stack.currentWidget() is page:
        return
    picture = hold_picture(stack, level)
    stack.setCurrentWidget(page)
    # Fade through rather than cross-fade: the old page is mostly gone before the new one shows, so
    # the two are never read on top of each other.
    fade_away(picture, level, -direction, share=FADE_THROUGH_OUT)
    delay = round(DURATION_MS.get(level, 0) * FADE_THROUGH_DELAY)
    appear(page, level, shift=direction * SLIDE_PX.get(level, 0), delay_ms=delay)


def settle(widget: QWidget) -> None:
    """End an animation still moving `widget` where it would have ended, so a second one starts from
    where the widget belongs. Stopping one does not emit `finished`, so its tidying runs here."""
    running = getattr(widget, "_motion_running", None)
    widget._motion_running = None  # type: ignore[attr-defined]
    if running is None:
        return
    animation, done = running
    with contextlib.suppress(RuntimeError):
        animation.finished.disconnect(done)
        animation.stop()
    done()


def _track(widget: QWidget, animation: QAbstractAnimation, done: Callable[[], None]) -> None:
    def finish() -> None:
        widget._motion_running = None  # type: ignore[attr-defined]
        done()

    animation.finished.connect(finish)
    widget._motion_running = (animation, finish)  # type: ignore[attr-defined]
    animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def appear(widget: QWidget, level: str, *, rise: bool = False, shift: int = 0, delay_ms: int = 0) -> None:
    """Fade `widget` in where it already is. A free-floating widget can also rise into place, and a
    page can come in from `shift` pixels to the side. `delay_ms` staggers a list of them. A window,
    such as a dialog, fades in as a whole."""
    duration = DURATION_MS.get(level, 0)
    if duration == 0 or not widget.isVisible():
        return
    if widget.isWindow():
        # An opacity effect draws a window's insides over nothing; the window's own opacity fades it.
        # Nothing here holds the window: a dialog is freed with its last reference, even mid-fade,
        # and its child animation with it.
        widget.setWindowOpacity(0.0)
        show = QPropertyAnimation(widget, b"windowOpacity", widget)
        show.setDuration(duration)
        show.setStartValue(0.0)
        show.setEndValue(1.0)
        show.setEasingCurve(QEasingCurve.Type.OutCubic)
        show.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        return
    settle(widget)
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0 if delay_ms else 1.0)
    widget.setGraphicsEffect(effect)
    group = QSequentialAnimationGroup(widget)
    if delay_ms:
        group.addPause(delay_ms)
    moves = QParallelAnimationGroup(group)
    fade = QPropertyAnimation(effect, b"opacity", moves)
    fade.setDuration(duration)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(QEasingCurve.Type.OutCubic)
    moves.addAnimation(fade)
    end = widget.pos()
    offset = QPoint(shift, RISE_PX[level] if rise else 0)
    if not offset.isNull():
        slide = QPropertyAnimation(widget, b"pos", moves)
        slide.setDuration(duration)
        slide.setStartValue(end + offset)
        slide.setEndValue(end)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        moves.addAnimation(slide)
        widget.move(end + offset)
    group.addAnimation(moves)

    def done() -> None:
        # An opacity effect left in place makes every later repaint of the widget go through it.
        widget.setGraphicsEffect(None)
        if not offset.isNull():
            widget.move(end)

    _track(widget, group, done)


def glide(widget: QWidget, target: QRect, level: str) -> None:
    """Move and resize `widget` to `target`, easing there rather than jumping."""
    settle(widget)
    duration = DURATION_MS.get(level, 0)
    if duration == 0 or not widget.isVisible() or widget.geometry() == target:
        widget.setGeometry(target)
        return
    move = QPropertyAnimation(widget, b"geometry", widget)
    move.setDuration(duration + 60)
    move.setStartValue(widget.geometry())
    move.setEndValue(target)
    move.setEasingCurve(QEasingCurve.Type.OutCubic)

    _track(widget, move, lambda: widget.setGeometry(target))


def vanish(widget: QWidget, level: str) -> None:
    """Fade `widget` out, then hide it."""
    duration = DURATION_MS.get(level, 0)
    if duration == 0 or not widget.isVisible():
        widget.hide()
        return
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    fade = QPropertyAnimation(effect, b"opacity", widget)
    fade.setDuration(duration)
    fade.setStartValue(1.0)
    fade.setEndValue(0.0)
    fade.setEasingCurve(QEasingCurve.Type.InCubic)

    def done() -> None:
        widget.hide()
        widget.setGraphicsEffect(None)

    fade.finished.connect(done)
    fade.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
