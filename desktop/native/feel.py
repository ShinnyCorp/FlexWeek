"""A Setup style's feel on every page: one answer for which feel is in force.

Keyed on the student's main view (`layout["main"]`), not the colourway or text
size. Plain calendar and every design that is not one of the four keep today's
look. Night owl, Dashboard and Retro add that design's radii, spacing, faces
and chrome to Settings, sheets, Setup and sign-in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from PySide6.QtCore import QChildEvent, QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRegion,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QAbstractSlider,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGraphicsEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from desktop.native import icons
from desktop.native.elevation import lift
from desktop.native.fonts import weighted
from desktop.native.layouts import retro
from desktop.native.layouts.bento import hero_ink
from desktop.native.layouts.registry import MATCH, options_for, tokens_for
from desktop.native.layouts.timeline import COMPACT
from desktop.native.layouts.timeline import SHEET as PAPER
from desktop.native.look import (
    FONT_FAMILIES,
    HEADING_NAMES,
    pack_stylesheet,
    text_scale,
)
from desktop.native.tokens import (
    RADIUS_CARD,
    RADIUS_CONTROL,
    RADIUS_SHEET,
    SHADOW_SMALL,
    WEIGHT_STRONG,
    contrast,
    fit_lightness,
    mix_oklab,
    type_pt,
)

CARDS = ("settingsCard", "dialogCard", "setupGroup")
SHEETS = ("sheetCard", "authCard")
FIELDS = "QLineEdit, QComboBox, QSpinBox, QTimeEdit, QDateTimeEdit, QPlainTextEdit"
EXTRA_HEADINGS = ("sheetTitle", "authBrand", "setupBrand", "setupSection", "setupTitle")
RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
PAGE_TITLES = {
    "settingsPage": ("Settings - FlexWeek", "settings", ("min", "max", "close")),
    "setupPage": ("Set up FlexWeek", "settings", ("min", "max", "close")),
    "authPage": ("Sign in to FlexWeek", "log-out", ("help", "close")),
    "recoveryPage": ("Recovery codes - FlexWeek", "file-text", ("help", "close")),
    "forgotPage": ("Recover account - FlexWeek", "log-out", ("help", "close")),
}
HERO_ICONS = {
    "settingsTitle": "palette",
    "sheetTitle": "book-open",
    "setupTitle": "sparkles",
    "authBrand": "sparkles",
}
BEVEL_SKIP = {
    "sheetClose",
    "setupRailItem",
    "authSwitch",
    "forgotPassword",
    "setupSkip",
    "setupSkipAll",
    "setupOwnLook",
    "setupQuiet",
    "setupPlay",
}

# Designs that are not one of the four wear Plain's feel.
_MAIN_TO_FEEL = {
    "classic": "plain",
    "timeline": "night_owl",
    "bento": "dashboard",
    "retro": "retro",
}

_current: Context | None = None


@dataclass(frozen=True)
class Shape:
    """Corners, card edges and spacing, read from the design."""

    card: int | None = None
    control: int | None = None
    pill: int | None = None
    sheet: int | None = None
    inner: int | None = None
    edge: str = "keep"
    shadow: str = "keep"
    spacing: tuple = ("scale", 1.0)


@dataclass(frozen=True)
class Faces:
    body: str | None = None
    heading: str | None = None
    field: str | None = None
    label_heads: bool = False


@dataclass(frozen=True)
class Feel:
    """Which feel is in force: one object every page asks."""

    key: str
    layout: str
    shape: Shape
    faces: Faces
    chrome: str
    tokens_said: dict = field(default_factory=dict)


FEELS = {
    "plain": Feel("plain", "classic", Shape(), Faces(), "none"),
    "night_owl": Feel(
        "night_owl",
        "timeline",
        Shape(
            card=RADIUS_CARD,
            control=RADIUS_CONTROL,
            sheet=RADIUS_CARD,
            edge="line",
            spacing=("scale", COMPACT),
        ),
        Faces(heading=FONT_FAMILIES["serif"]),
        "paper",
    ),
    "dashboard": Feel(
        "dashboard",
        "bento",
        Shape(
            card=RADIUS_SHEET,
            control=RADIUS_CONTROL,
            sheet=RADIUS_SHEET,
            inner=RADIUS_CARD,
            edge="none",
            shadow="small",
            spacing=("set", 16, 8, 16),
        ),
        Faces(label_heads=True),
        "hero",
    ),
    "retro": Feel(
        "retro",
        "retro",
        Shape(card=0, control=0, pill=0, sheet=0, edge="bevel", shadow="none", spacing=("set", 10, 6, 12)),
        Faces(body=retro.PIXEL_FACE, heading=retro.PIXEL_FACE, field=retro.NOTE_FACE),
        "win98",
    ),
}


@dataclass(frozen=True)
class Context:
    feel: Feel
    look: dict
    palette: dict
    tokens: dict
    base_sheet: str


def feel_for(main: str | None) -> Feel:
    """The feel that belongs to this main view. Unknown designs get Plain."""
    return FEELS[_MAIN_TO_FEEL.get(main or "", "plain")]


def design_key(main: str | None) -> str:
    """What the look file stores for sign-in: the feel's design, never an account."""
    return feel_for(main).layout


def sanitize_design(value: object) -> str:
    if value in {"classic", "timeline", "bento", "retro"}:
        return str(value)
    return "classic"


def set_current(context: Context | None) -> None:
    global _current
    _current = context


def current() -> Context | None:
    return _current


def page_feel() -> Feel:
    return _current.feel if _current is not None else FEELS["plain"]


def radius_for(selector: str, old: int, shape: Shape, nested: bool = True) -> int:
    if any(name in selector for name in SHEETS):
        return old if shape.sheet is None else shape.sheet
    if "setupChoice" in selector and nested and shape.inner is not None:
        return old if shape.inner is None else shape.inner
    if any(name in selector for name in CARDS) or "setupChoice" in selector:
        return old if shape.card is None else shape.card
    if old == 0:
        return 0
    if old < 10:
        if shape.control is None:
            return old
        return max(0, shape.control + old - RADIUS_CONTROL) if shape.control else 0
    if old < 14:
        return old if shape.card is None else shape.card
    if old == RADIUS_SHEET:
        return old if shape.sheet is None else shape.sheet
    return old if shape.pill is None else shape.pill


def radius_rules(sheet: str, shape: Shape, nested: bool = True) -> str:
    made = []
    for selector, body in RULE.findall(sheet):
        changed = []
        for prop, value in re.findall(r"(border(?:-(?:top|bottom)-(?:left|right))?-radius):\s*(\d+)px", body):
            new = radius_for(selector, int(value), shape, nested)
            if new != int(value):
                changed.append(f"{prop}: {new}px;")
        if changed:
            made.append(f"{selector.strip()} {{ {' '.join(changed)} }}")
    return "".join(made)


def bevel_css(kind: str) -> str:
    standard = retro.STANDARD
    rings = {"raised": (standard["hi"], standard["shadow"]), "sunken": (standard["shadow"], standard["hi"])}
    top, bottom = rings[kind]
    return (
        f"border-style: solid; border-width: 2px; border-top-color: {top}; border-left-color: {top}; "
        f"border-bottom-color: {bottom}; border-right-color: {bottom};"
    )


def edge_rules(tokens: dict[str, str], palette: dict, shape: Shape) -> str:
    cards = ", ".join(f"QFrame#{name}" for name in CARDS) + ", QFrame#sheetCard, QWidget#authCard"
    if shape.edge == "line":
        return f"{cards} {{ border: 1px solid {tokens['line']}; }}"
    if shape.edge == "none":
        edge = tokens["line"] if palette.get("axis") == "dark" else "transparent"
        return f"{cards} {{ border: 1px solid {edge}; }}"
    if shape.edge == "bevel":
        raised, sunken = bevel_css("raised"), bevel_css("sunken")
        buttons = (
            'QPushButton, QPushButton[outlined="true"], QPushButton[tonal="true"], '
            'QPushButton[quiet="true"], QDialog QPushButton'
        )
        return (
            f"{cards} {{ {raised} }}"
            f"{FIELDS} {{ {sunken} }}"
            f'QFrame[segmented="true"] {{ {sunken} }}'
            f'QPushButton[segment="true"]:checked {{ {raised} }}'
            f"{buttons} {{ {raised} }}"
            f"QPushButton#sheetClose {{ border: none; }}"
        )
    return ""


def face_rules(feel: Feel, tokens: dict[str, str], scale: float) -> str:
    faces = feel.faces
    made = []
    if faces.body:
        made.append(f"QMainWindow, QDialog, QWidget {{ font-family: {faces.body}; }}")
    if faces.heading:
        names = ", ".join(f"QLabel#{name}" for name in (*HEADING_NAMES, *EXTRA_HEADINGS))
        made.append(f"{names} {{ font-family: {faces.heading}; }}")
    if faces.field:
        made.append(f"{FIELDS} {{ font-family: {faces.field}; font-size: {type_pt('heading', scale)}pt; }}")
    if faces.label_heads:
        made.append(
            f"QLabel#prefsHeading {{ font-size: {type_pt('caption', scale)}pt; "
            f"color: {tokens['muted']}; font-weight: {WEIGHT_STRONG}; }}"
        )
    return "".join(made)


def hero_rules(tokens: dict[str, str], scale: float, names: tuple[str, ...]) -> str:
    hero = hero_ink(tokens)
    pad = round(16 * scale)
    room = round((36 + 12) * scale) + pad
    selector = ", ".join(f"QLabel#{name}" for name in names)
    return (
        f"{selector} {{ background: {hero.ground}; color: {hero.text}; border-radius: {RADIUS_SHEET}px; "
        f"padding: {pad}px {pad}px {pad}px {room}px; }}"
    )


def extra_stylesheet(
    base: str,
    feel: Feel,
    palette: dict,
    tokens: dict[str, str],
    look: dict | None,
    hero_names: tuple[str, ...] = (),
    nested: bool = True,
) -> str:
    """Rules that remap today's sheet to this feel. Empty for Plain, so the sheet is unchanged."""
    if feel.key == "plain":
        return ""
    extra = radius_rules(base, feel.shape, nested) + edge_rules(tokens, palette, feel.shape)
    extra += face_rules(feel, tokens, text_scale(look))
    if feel.chrome == "hero" and hero_names:
        extra += hero_rules(tokens, text_scale(look), hero_names)
    return extra


def dressed_stylesheet(
    pack: object,
    system_dark: bool,
    look: dict | None,
    feel: Feel,
    accent: object = "default",
    palette: dict | None = None,
    art: dict[str, str] | None = None,
    tokens: dict[str, str] | None = None,
    hero_names: tuple[str, ...] = (),
) -> str:
    base = pack_stylesheet(pack, system_dark, look, accent, palette, art)
    if tokens is None:
        return base
    return base + extra_stylesheet(base, feel, palette or {}, tokens, look, hero_names)


def restyle_children(root: QWidget, shape: Shape) -> None:
    for widget in root.findChildren(QWidget):
        own = widget.styleSheet()
        if own and "border-radius" in own:
            extra = radius_rules(own, shape)
            if extra:
                tagged = widget.property("feelOwnSheet")
                source = tagged if isinstance(tagged, str) else own
                if widget.property("feelOwnSheet") is None:
                    widget.setProperty("feelOwnSheet", own)
                widget.setStyleSheet(source + extra)
            elif widget.property("feelOwnSheet") is not None:
                widget.setStyleSheet(str(widget.property("feelOwnSheet")))
                widget.setProperty("feelOwnSheet", None)
        elif widget.property("feelOwnSheet") is not None:
            widget.setStyleSheet(str(widget.property("feelOwnSheet")))
            widget.setProperty("feelOwnSheet", None)


def _scaled(layout: QLayout, factor: float) -> None:
    margins = layout.contentsMargins()
    layout.setContentsMargins(
        *(round(v * factor) for v in (margins.left(), margins.top(), margins.right(), margins.bottom()))
    )
    if isinstance(layout, QFormLayout):
        layout.setVerticalSpacing(round(max(layout.verticalSpacing(), 0) * factor))
    elif layout.spacing() > 0:
        layout.setSpacing(round(layout.spacing() * factor))


def _remember(layout: QLayout) -> None:
    if layout.property("feelPad") is not None:
        return
    margins = layout.contentsMargins()
    layout.setProperty("feelPad", (margins.left(), margins.top(), margins.right(), margins.bottom()))
    space = layout.verticalSpacing() if isinstance(layout, QFormLayout) else layout.spacing()
    layout.setProperty("feelSpace", space)


def _restore(layout: QLayout) -> None:
    pad = layout.property("feelPad")
    if pad is None:
        return
    layout.setContentsMargins(*pad)
    space = layout.property("feelSpace")
    if isinstance(layout, QFormLayout):
        layout.setVerticalSpacing(int(space))
    else:
        layout.setSpacing(int(space))


def respace(card_layouts: list[QLayout], column: QLayout | None, shape: Shape) -> None:
    kind, *values = shape.spacing
    for layout in card_layouts:
        _remember(layout)
        _restore(layout)
        if kind == "scale":
            if values[0] != 1.0:
                _scaled(layout, values[0])
            continue
        pad, rows, _gap = values
        layout.setContentsMargins(pad, pad, pad, pad)
        if isinstance(layout, QFormLayout):
            layout.setVerticalSpacing(rows)
        else:
            layout.setSpacing(rows)
    if column is not None:
        _remember(column)
        _restore(column)
        if kind == "scale":
            if values[0] != 1.0:
                column.setSpacing(round(column.spacing() * values[0]))
        else:
            column.setSpacing(values[2])


class PaperEdge(QGraphicsEffect):
    """Timeline's next sheet of paper under a card."""

    def __init__(self, tokens: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens

    def boundingRectFor(self, rect: QRectF) -> QRectF:  # noqa: N802
        return rect.adjusted(0, 0, 0, PAPER)

    def draw(self, painter: QPainter) -> None:
        box = self.boundingRect().adjusted(0, 0, 0, -PAPER)
        under = box.translated(0, PAPER).adjusted(1, 0, -1, 0)
        shape = QPainterPath()
        shape.addRoundedRect(under, RADIUS_CARD, RADIUS_CARD)
        card = QPainterPath()
        card.addRoundedRect(box, RADIUS_CARD, RADIUS_CARD)
        painter.setPen(QPen(QColor(self._tokens["line"]), 1))
        painter.setBrush(QColor(self._tokens["surface"]))
        painter.save()
        painter.setClipPath(QPainterPath(shape).subtracted(card))
        painter.drawPath(shape)
        painter.restore()
        self.drawSource(painter)


class HeroMark(QLabel):
    """Bento's 36 px icon square on a page or sheet title."""

    def __init__(self, name: str, tokens: dict[str, str], scale: float, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("bentoHeroIcon")
        self._name = name
        self._tokens = tokens
        self._scale = scale
        side = round(36 * scale)
        self.setFixedSize(side, side)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        hero = hero_ink(self._tokens)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(hero.tint))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS_CARD, RADIUS_CARD)
        mark = round(18 * self._scale)
        pix = icons.pixmap(self._name, hero.accent, mark, self.devicePixelRatioF())
        painter.drawPixmap(QPointF((self.width() - mark) / 2, (self.height() - mark) / 2), pix)
        painter.end()


class _HeroPlace(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Resize and isinstance(watched, QWidget):
            mark = watched.findChild(HeroMark)
            if mark is not None:
                pad = round(16 * mark._scale)
                mark.move(pad, max((watched.height() - mark.height()) // 2, 0))
        return False


_hero_place = _HeroPlace()


def bar_height(scale: float) -> int:
    font = QFont("Pixelify Sans")
    font.setPointSizeF(type_pt("body", scale))
    words = round(QFontMetricsF(weighted(font, WEIGHT_STRONG)).height()) + 8
    return max(24, words, retro.CAP.height() + 8)


class Win98TitleBar(QWidget):
    """Full-width Windows 98 title strip: gradient, icon, title widget, caption buttons."""

    def __init__(
        self,
        title: str,
        icon: str,
        caps: tuple[str, ...],
        tokens: dict[str, str],
        scale: float,
        close_host: object,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("win98TitleBar")
        self._tokens = tokens
        self._icon = icon
        self._scale = scale
        self._colours = retro.scheme(tokens)
        ink, _start, _end = title_bar_colours(tokens)
        line = QHBoxLayout(self)
        pad = max(4, (bar_height(scale) - retro.CAP.height()) // 2)
        line.setContentsMargins(4, pad, 4, pad)
        line.setSpacing(1)
        mark = QLabel()
        mark.setFixedSize(16, 16)
        mark.setPixmap(icons.pixmap(icon, ink, 16, self.devicePixelRatioF(), "2"))
        mark.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        line.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
        words = QLabel(title)
        words.setObjectName("win98Title")
        words.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        font = QFont("Pixelify Sans")
        font.setPointSizeF(type_pt("body", scale))
        words.setFont(weighted(font, WEIGHT_STRONG))
        words.setStyleSheet(f"background: transparent; color: {ink};")
        line.addWidget(words, 1, Qt.AlignmentFlag.AlignVCenter)
        labels = {"min": "Minimise", "max": "Maximise", "close": "Close", "help": "Help"}
        cap_css = (
            f"min-width: {retro.CAP.width()}px; max-width: {retro.CAP.width()}px; "
            f"min-height: {retro.CAP.height()}px; max-height: {retro.CAP.height()}px; padding: 0px;"
        )
        for cap in caps:
            button = retro.CapButton(f"win98Cap-{cap}", labels.get(cap, cap), self._colours, cap)
            button.setStyleSheet(cap_css)
            button.setFixedSize(retro.CAP)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            if cap == "close":
                button.clicked.connect(close_host)
            line.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setFixedHeight(bar_height(scale))

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        _ink, start, end = title_bar_colours(self._tokens)
        gradient.setColorAt(0, QColor(start))
        gradient.setColorAt(1, QColor(end))
        painter.fillRect(self.rect(), gradient)
        painter.end()


class Win98Chrome(QWidget):
    """A Windows 98 window or dialog frame around a page or sheet, painted over its edges."""

    def __init__(
        self,
        host: QWidget,
        title: str,
        icon: str,
        caps: tuple[str, ...],
        tokens: dict[str, str],
        scale: float,
    ) -> None:
        super().__init__(host)
        self.setObjectName("win98Frame")
        self._host = host
        self._title = title
        self._icon = icon
        self._caps = caps
        self._tokens = tokens
        self._scale = scale
        self._colours = retro.scheme(tokens)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._bar = Win98TitleBar(title, icon, caps, tokens, scale, self._close_host, host)
        host.installEventFilter(self)
        self._sync()

    def _close_host(self) -> None:
        dialog = self._host if isinstance(self._host, QDialog) else self._host.window()
        if isinstance(dialog, QDialog):
            dialog.reject()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._host and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.LayoutRequest,
        ):
            self._sync()
        return False

    def _sync(self) -> None:
        host = self._host
        self.setGeometry(host.rect())
        bar_h = max(bar_height(self._scale), retro.CAP.height() + 8)
        self._bar.setParent(host)
        self._bar.setGeometry(4, 4, max(host.width() - 8, 0), bar_h)
        self._bar.show()
        self._bar.raise_()
        inner = QRect(4, 4 + bar_h, max(host.width() - 8, 0), max(host.height() - 8 - bar_h, 0))
        self.setMask(QRegion(self.rect()).subtracted(QRegion(inner)))
        if host.property("feelMargins") is None:
            m = host.contentsMargins()
            host.setProperty("feelMargins", (m.left(), m.top(), m.right(), m.bottom()))
        host.setContentsMargins(4, 4 + bar_h, 4, 4)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        colours = self._colours
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(colours.face))
        retro.bevel(painter, self.rect(), colours, "window")
        painter.end()

    def sizeHint(self) -> QSize:  # noqa: N802
        return self._host.size()

    def restyle(self, title: str, icon: str, tokens: dict[str, str], scale: float) -> None:
        self._title = title
        self._icon = icon
        self._tokens = tokens
        self._colours = retro.scheme(tokens)
        self._scale = scale
        self._bar.hide()
        self._bar.deleteLater()
        self._bar = Win98TitleBar(title, icon, self._caps, tokens, scale, self._close_host, self._host)
        self._sync()


def _card_widgets(root: QWidget) -> list[QWidget]:
    found: list[QWidget] = []
    for name in (*CARDS, "sheetCard", "authCard", "setupChoice"):
        found.extend(root.findChildren(QWidget, name))
    return found


def _shadows(widgets: list[QWidget], feel: Feel, dark: bool) -> None:
    for widget in widgets:
        if feel.shape.shadow == "small":
            lift(widget, SHADOW_SMALL, dark)
            widget.setProperty("feelShadow", True)
        elif feel.shape.shadow == "none":
            widget.setGraphicsEffect(None)
            widget.setProperty("feelShadow", True)
        elif feel.shape.shadow == "keep":
            if widget.property("feelShadow"):
                widget.setGraphicsEffect(None)
                widget.setProperty("feelShadow", False)
        if feel.chrome == "paper" and widget.objectName() in (*CARDS, "sheetCard", "authCard"):
            tokens = current().tokens if current() is not None else {}
            widget.setGraphicsEffect(PaperEdge(tokens, widget))
            widget.setProperty("feelShadow", True)
        elif feel.chrome != "paper" and isinstance(widget.graphicsEffect(), PaperEdge):
            widget.setGraphicsEffect(None)


def _hero_titles(root: QWidget, tokens: dict[str, str], scale: float, on: bool) -> None:
    for widget in root.findChildren(QLabel):
        icon = HERO_ICONS.get(widget.objectName())
        if icon is None:
            continue
        mark = widget.findChild(HeroMark)
        if on:
            if mark is None:
                mark = HeroMark(icon, tokens, scale, widget)
                widget.installEventFilter(_hero_place)
            mark._tokens = tokens
            mark._scale = scale
            mark.show()
            pad = round(16 * scale)
            mark.move(pad, max((widget.height() - mark.height()) // 2, 0))
        elif mark is not None:
            mark.hide()
            mark.deleteLater()


def _hosts_to_frame(root: QWidget) -> list[QWidget]:
    hosts: list[QWidget] = []
    seen: set[int] = set()
    for name in PAGE_TITLES:
        pages = [root] if root.objectName() == name else []
        pages.extend(root.findChildren(QWidget, name))
        for page in pages:
            key = id(page)
            if key not in seen:
                seen.add(key)
                hosts.append(page)
    cards = [root] if root.objectName() == "sheetCard" else []
    cards.extend(root.findChildren(QFrame, "sheetCard"))
    for card in cards:
        key = id(card)
        if key not in seen:
            seen.add(key)
            hosts.append(card)
    return hosts


def _chrome_on(host: QWidget) -> Win98Chrome | None:
    kids = host.findChildren(Win98Chrome, "win98Frame")
    return next((child for child in kids if child.parent() is host), None)


def _ensure_one_frame(host: QWidget, tokens: dict[str, str], scale: float, on: bool) -> None:
    existing = _chrome_on(host)
    if not on:
        if existing is not None:
            existing.hide()
            existing._bar.hide()
            existing._bar.deleteLater()
            existing.deleteLater()
        pad = host.property("feelMargins")
        if pad is not None:
            host.setContentsMargins(*pad)
            host.setProperty("feelMargins", None)
        heading = host.findChild(QLabel, "sheetTitle")
        close = host.findChild(QPushButton, "sheetClose")
        if heading is not None:
            heading.show()
        if close is not None:
            close.show()
        return
    title, icon, caps = ("FlexWeek", "calendar-days", ("min", "max", "close"))
    if host.objectName() in PAGE_TITLES:
        title, icon, caps = PAGE_TITLES[host.objectName()]
    elif host.objectName() == "sheetCard":
        dialog = host.window()
        title = dialog.windowTitle() or "FlexWeek"
        icon = "book-open"
        caps = ("help", "close")
        heading = host.findChild(QLabel, "sheetTitle")
        close = host.findChild(QPushButton, "sheetClose")
        if heading is not None:
            heading.hide()
        if close is not None:
            close.hide()
    if existing is None:
        existing = Win98Chrome(host, title, icon, caps, tokens, scale)
    else:
        existing.restyle(title, icon, tokens, scale)
    existing.show()
    existing.raise_()
    existing._sync()


def _ensure_frame(root: QWidget, tokens: dict[str, str], scale: float, on: bool) -> None:
    for host in _hosts_to_frame(root):
        _ensure_one_frame(host, tokens, scale, on)


def bevel_kind(widget: QWidget) -> str | None:
    """Which of retro.BEVELS a widget takes: cards and buttons raised, fields and tracks sunken."""
    name = widget.objectName()
    if isinstance(widget, QPushButton):
        if (
            name in BEVEL_SKIP
            or widget.isFlat()
            or widget.property("quiet")
            or (widget.property("segment") and not widget.isChecked())
        ):
            return None
        if widget.property("segment"):
            return "raised"
        return "pressed" if widget.isCheckable() and widget.isChecked() else "raised"
    if isinstance(widget, (QLineEdit, QComboBox, QAbstractSpinBox)):
        parent = widget.parentWidget()
        inner = isinstance(widget, QLineEdit) and isinstance(parent, (QComboBox, QAbstractSpinBox))
        return None if inner else "sunken"
    if isinstance(widget, QFrame) and widget.property("segmented"):
        return "sunken"
    if name == "setupChoice" and widget.property("selected"):
        return None
    if name in (*CARDS, "sheetCard", "authCard", "setupChoice"):
        return "raised"
    return None


_BEVEL_WATCH = {
    QEvent.Type.Resize,
    QEvent.Type.Show,
    QEvent.Type.LayoutRequest,
    QEvent.Type.HoverEnter,
    QEvent.Type.HoverLeave,
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease,
    QEvent.Type.Wheel,
    QEvent.Type.ChildAdded,
}
_COVERS = ("settingsFooter", "setupNav", "setupFade")


def _bevel_clip(widget: QWidget, host: QWidget) -> QRegion:
    """The part of `widget` that is on screen, inside scroll viewports and not under the footer."""
    shown = widget.visibleRegion()
    if shown.isEmpty():
        return shown
    clip = shown.translated(widget.mapTo(host, QPoint(0, 0)))
    for name in _COVERS:
        cover = host.findChild(QWidget, name)
        if cover is None or cover is widget or not cover.isVisible():
            continue
        clip -= QRegion(QRect(cover.mapTo(host, QPoint(0, 0)), cover.size()))
    return clip


class BevelPane(QWidget):
    """Paints retro.bevel on cards, buttons, fields and tracks a stylesheet cannot reach."""

    def __init__(self, host: QWidget, tokens: dict[str, str]) -> None:
        super().__init__(host)
        self.setObjectName("win98Bevels")
        self._host = host
        self._tokens = tokens
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        host.installEventFilter(self)
        self._watch(host)
        self._sync()

    def _watch(self, widget: QWidget) -> None:
        widget.installEventFilter(self)
        widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        if isinstance(widget, QAbstractSlider):
            widget.valueChanged.connect(self.update)
        for child in widget.findChildren(QWidget):
            if child is self:
                continue
            child.installEventFilter(self)
            child.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            if isinstance(child, QAbstractSlider):
                child.valueChanged.connect(self.update)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        kind = event.type()
        if kind not in _BEVEL_WATCH:
            return False
        if kind == QEvent.Type.ChildAdded and isinstance(event, QChildEvent):
            child = event.child()
            if isinstance(child, QWidget) and child is not self:
                self._watch(child)
            return False
        if watched is self._host and kind in (QEvent.Type.Resize, QEvent.Type.Show):
            self._sync()
        else:
            self.update()
        return False

    def _sync(self) -> None:
        self.setGeometry(self._host.rect())
        self.raise_()
        for bar in self._host.findChildren(Win98TitleBar):
            bar.raise_()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        colours = retro.scheme(self._tokens)
        painter = QPainter(self)
        for widget in self._host.findChildren(QWidget):
            if widget is self or isinstance(widget, (Win98Chrome, Win98TitleBar, BevelPane, retro.CapButton)):
                continue
            parent = widget.parentWidget()
            skip = False
            while parent is not None:
                if isinstance(parent, (Win98Chrome, Win98TitleBar)):
                    skip = True
                    break
                parent = parent.parentWidget()
            if skip or not widget.isVisible() or widget.width() < 6 or widget.height() < 6:
                continue
            if _chrome_on(widget) is not None:
                continue
            kind = bevel_kind(widget)
            if kind is None:
                continue
            clip = _bevel_clip(widget, self._host)
            if clip.isEmpty():
                continue
            painter.save()
            painter.setClipRegion(clip)
            top_left = widget.mapTo(self._host, QPoint(0, 0))
            retro.bevel(painter, QRect(top_left, widget.size()), colours, kind)
            painter.restore()
        painter.end()


def _ensure_bevels(root: QWidget, tokens: dict[str, str], on: bool) -> None:
    existing = next((child for child in root.findChildren(BevelPane) if child.parent() is root), None)
    if not on:
        if existing is not None:
            existing.hide()
            existing.deleteLater()
        return
    if existing is None:
        existing = BevelPane(root, tokens)
    else:
        existing._tokens = tokens
    existing.show()
    existing.raise_()
    existing._sync()


def apply_feel(root: QWidget, context: Context, *, nested: bool = True) -> None:
    """Dress Settings, a sheet, Setup or sign-in in the feel in force."""
    feel = context.feel
    restyle_children(root, feel.shape)
    cards = [widget.layout() for widget in _card_widgets(root) if widget.layout() is not None]
    title = root.findChild(QLabel, "settingsTitle")
    column = title.parentWidget().layout() if title is not None and title.parentWidget() is not None else None
    respace([layout for layout in cards if layout is not None], column, feel.shape)
    _shadows(_card_widgets(root), feel, context.palette.get("axis") == "dark")
    _hero_titles(root, context.tokens, text_scale(context.look), feel.chrome == "hero")
    _ensure_frame(root, context.tokens, text_scale(context.look), feel.chrome == "win98")
    _ensure_bevels(root, context.tokens, feel.shape.edge == "bevel")
    for bar in root.findChildren(Win98TitleBar):
        bar.raise_()
    root.setProperty("feelKey", feel.key)


def context_for(layout: dict, look: dict, palette: dict, base_sheet: str) -> Context:
    feel = feel_for(layout.get("main") if isinstance(layout, dict) else None)
    colour = options_for(layout, feel.layout).get("colour", MATCH) if feel.key != "plain" else MATCH
    if feel.key == "plain":
        tokens = tokens_for("classic", MATCH, palette)
    else:
        tokens = tokens_for(feel.layout, colour, palette)
    return Context(feel, look, palette, tokens, base_sheet)


def hero_contrast_ok(tokens: dict[str, str]) -> bool:
    hero = hero_ink(tokens)
    return contrast(hero.text, hero.ground) >= 4.5


def title_bar_colours(tokens: dict[str, str]) -> tuple[str, str, str]:
    """Ink and the bar's two ends, with the light end darkened until the words read."""
    colours = retro.scheme(tokens)
    ink = colours.title_ink
    start, end = colours.title, colours.title_end
    for amount in (0.0, 0.15, 0.3, 0.45, 0.6, 0.8, 1.0):
        mixed = mix_oklab(start, end, amount)
        if contrast(ink, mixed) >= 4.5:
            end = mixed
            break
    else:
        ink = fit_lightness(ink, (start, end), 4.5)
    return ink, start, end


def title_bar_ink(tokens: dict[str, str]) -> str:
    return title_bar_colours(tokens)[0]


def title_bar_contrast_ok(tokens: dict[str, str]) -> bool:
    ink, start, end = title_bar_colours(tokens)
    return min(contrast(ink, start), contrast(ink, end)) >= 4.5
