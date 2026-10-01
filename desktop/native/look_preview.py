"""A look drawn as a small week in its own colours, for the picture on More looks' cards."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap

from desktop.native.custom_look import wear
from desktop.native.look import (
    CORNER_RADIUS,
    category_paint,
    effective_look,
    parse_look_menu_token,
    resolved_palette,
)

SAVED_PREFIX = "saved:"
PICTURE_RATIO = 0.625
# (day, top, height) as shares of the week's body, and the category each block is drawn in.
BLOCKS = (
    (0, 0.05, 0.42, "class"),
    (1, 0.30, 0.30, "assignments"),
    (2, 0.05, 0.42, "class"),
    (3, 0.52, 0.30, "extra"),
    (4, 0.18, 0.30, "assignments"),
)
DAYS = 5
SCALE = 2


def look_choice(token: str, saved: list[dict]) -> tuple[str, dict]:
    """The pack and look a More looks card stands for: a built-in look by its menu token, or a saved
    look by its name. A token that is neither draws as Light."""
    if token.startswith(SAVED_PREFIX):
        name = token.removeprefix(SAVED_PREFIX)
        custom = next((look for look in saved if look["name"] == name), None)
        if custom is not None:
            return "system", wear(None, custom)
    parsed = parse_look_menu_token(token)
    if parsed is None:
        return "light-frost", {}
    kind, name = parsed
    return (name, {}) if kind == "pack" else ("system", {"preset": name})


def look_preview(pack: str, look: dict, width: int) -> QPixmap:
    """The look's page, top bar and five days with a few blocks, in its palette (its light form, for
    System) and its corners."""
    palette = resolved_palette(pack, False, look)
    height = round(width * PICTURE_RATIO)
    radius = CORNER_RADIUS[effective_look(look)["corners"]][0] / 3
    picture = QPixmap(width * SCALE, height * SCALE)
    picture.setDevicePixelRatio(SCALE)
    picture.fill(QColor(palette["window"]))
    painter = QPainter(picture)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    bar = height * 0.2
    painter.setBrush(QColor(palette["panel"]))
    painter.drawRect(QRectF(0, 0, width, bar))
    painter.setBrush(QColor(palette["hairline_strong"]))
    painter.drawRect(QRectF(0, bar, width, 1))
    painter.setBrush(QColor(palette["text"]))
    painter.drawRoundedRect(QRectF(width * 0.06, bar * 0.36, width * 0.22, bar * 0.28), 2, 2)
    painter.setBrush(QColor(palette["accent"]))
    painter.drawRoundedRect(QRectF(width * 0.78, bar * 0.28, width * 0.16, bar * 0.44), radius, radius)
    body_top, body_height = bar + 4, height - bar - 8
    column = (width - 8) / DAYS
    painter.setBrush(QColor(palette["hairline"]))
    for day in range(1, DAYS):
        painter.drawRect(QRectF(4 + column * day, body_top, 1, body_height))
    for day, top, tall, category in BLOCKS:
        fill, mark = category_paint(category, palette)
        area = QRectF(4 + column * day + 2, body_top + body_height * top, column - 4, body_height * tall)
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(area, radius, radius)
        painter.setBrush(QColor(mark))
        painter.drawRect(QRectF(area.left(), area.top() + radius, 2, area.height() - 2 * radius))
    painter.end()
    return picture
