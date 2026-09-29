"""The system's two shadows (decision 6) put on a widget."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

from desktop.native.tokens import Shadow


def lift(widget: QWidget, shadow: Shadow, dark: bool = False) -> QGraphicsDropShadowEffect:
    """Give `widget` `shadow`, replacing any effect it had. A widget holds one effect, so a fade on the
    same widget (motion.py) goes on a child instead."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setOffset(0, shadow.y)
    effect.setBlurRadius(shadow.blur)
    effect.setColor(QColor(0, 0, 0, round(255 * (shadow.dark_opacity if dark else shadow.opacity))))
    widget.setGraphicsEffect(effect)
    return effect
