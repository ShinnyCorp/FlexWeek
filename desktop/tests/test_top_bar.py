"""The top bar and the controls every screen shares: 0.17's decisions 7 (icons), 11 (the top bar and
the button states) and 12 (overlay scroll bars and the zoom pill), read off the screen."""

# ruff: noqa: F811  (pytest fixtures imported by name)

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractScrollArea,
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QStyleOptionButton,
    QWidget,
)

from desktop.native.look import mix, pack_stylesheet, resolved_palette, sanitize_look
from desktop.native.widgets import control_art, keyboard_focus_rings
from desktop.native.window import NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    host,
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
    window,
)

# The glyphs that stood in for icons before 0.17 (decision 7).
GLYPHS = "‹›⚙▾▸✕×✓⏱⋯＋−"


def dress(
    qapp: QApplication, window: NativeWindow, pack: str = "light-frost", preset: str = "default"
) -> dict:
    window.session.preferences = {**(window.session.preferences or {}), "theme_pack": pack}
    window._look = sanitize_look({"preset": preset})
    window._apply_appearance()
    for _ in range(3):
        qapp.processEvents()
    chosen_pack, dark, accent = window._look_inputs()
    return resolved_palette(chosen_pack, dark, window._look, accent)


SCHOOL = {
    "id": "school",
    "title": "School",
    "kind": "locked",
    "category": "class",
    "start": "08:00",
    "duration_min": 405,
    "days": [0, 1, 2, 3, 4],
}


def shown(qapp: QApplication, window: NativeWindow, view: str) -> None:
    """`view` of a week with school in it: an empty week shows its welcome instead of the hours."""
    if not window.session.blocks:
        window.session.add_block(SCHOOL)
        window.session.save()
        settled(qapp, window)
    window.findChild(QPushButton, f"view{view.title()}").click()
    wait_until(qapp, lambda: not window.session.busy)
    for _ in range(3):
        qapp.processEvents()


def bar(window: NativeWindow, name: str) -> QPushButton:
    found = window.findChild(QPushButton, name)
    assert found is not None, name
    return found


def box(window: NativeWindow, widget: QWidget) -> QRect:
    return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())


def near(seen: QColor, wanted: str, slack: int = 3) -> bool:
    other = QColor(wanted)
    return (
        max(abs(seen.red() - other.red()), abs(seen.green() - other.green()), abs(seen.blue() - other.blue()))
        <= slack
    )


def icon_inks(button: QAbstractButton) -> set[str]:
    """The colours an icon is drawn in, from its strokes' most covered pixels."""
    image = button.icon().pixmap(20, 20).toImage()
    return {
        image.pixelColor(x, y).name()
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() >= 160
    }


def test_no_glyph_stands_in_for_an_icon_in_the_chrome(qapp: QApplication, window: NativeWindow) -> None:
    """Decision 7: the gear was "⚙" in a fallback font, thinner and lower than the words beside it,
    and the arrows, Add's arrow and the zoom were text too. Nothing on Week, Day or Month writes one."""
    window.resize(1280, 800)
    for view in ("week", "day", "month"):
        shown(qapp, window, view)
        page = window._stack.currentWidget()
        written = [
            (widget.objectName(), widget.text())
            for kind in (QAbstractButton, QLabel)
            for widget in page.findChildren(kind)
            if widget.isVisible() and any(glyph in widget.text() for glyph in GLYPHS)
        ]
        assert written == [], view
    for name in ("prevWeek", "nextWeek", "settingsGear", "addArrow", "weekZoomOut", "weekZoomIn"):
        button = bar(window, name)
        assert button.text() == "" and not button.icon().isNull(), name
        assert button.accessibleName() or button.toolTip(), f"{name} has no words for a screen reader"


def test_the_arrows_and_today_come_before_the_title_and_stay_put(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Decision 11. After the title, ‹ › and Today moved sideways with its width, some 70 pixels on
    every switch between Day, Week and Month."""
    window.resize(1280, 800)
    places = set()
    for view in ("week", "day", "month"):
        shown(qapp, window, view)
        left = [box(window, bar(window, name)).left() for name in ("prevWeek", "nextWeek", "todayWeek")]
        assert left == sorted(left), view
        title = box(window, window.week_title)
        assert box(window, bar(window, "todayWeek")).right() < title.left(), view
        assert title.right() < box(window, window.findChild(QWidget, "segments")).left(), view
        places.add(tuple(left))
    assert len(places) == 1, places


def test_the_bars_icons_are_in_the_words_colour_and_follow_the_look(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Tinted to the text, and drawn again when the look changes: a dark icon on Dark's page could not
    be seen."""
    for pack in ("light-frost", "dark-frost"):
        palette = dress(qapp, window, pack)
        for name, ink in (
            ("prevWeek", "text"),
            ("nextWeek", "text"),
            ("settingsGear", "text"),
            ("addArrow", "accent_ink"),
            ("addButton", "accent_ink"),
        ):
            inks = icon_inks(bar(window, name))
            assert inks and all(near(QColor(seen), palette[ink]) for seen in inks), (pack, name, inks)


def test_add_is_one_pill_split_by_a_line_of_its_ink(qapp: QApplication, window: NativeWindow) -> None:
    """Add's arrow was a second filled button 2 pixels away, so Add read as two buttons."""
    palette = dress(qapp, window)
    window.resize(1280, 800)
    qapp.processEvents()
    add, arrow = box(window, bar(window, "addButton")), box(window, bar(window, "addArrow"))
    assert add.right() + 1 == arrow.left() and add.top() == arrow.top()
    picture = window.grab().toImage()
    middle = arrow.center().y()
    assert near(picture.pixelColor(arrow.left(), middle), mix(palette["accent_ink"], palette["accent"], 0.3))
    assert near(picture.pixelColor(add.right() - 1, middle), palette["accent"])
    assert near(picture.pixelColor(arrow.left() + 2, middle), palette["accent"])


def test_plan_is_second_to_add_and_more_is_in_the_text_colour(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Plan my homework had a border like Today and More, so all three looked equal; More was muted and
    read as disabled."""
    palette = dress(qapp, window)
    window.resize(1280, 800)
    qapp.processEvents()
    picture = window.grab().toImage()
    plan = box(window, window.solve_button)
    assert near(
        picture.pixelColor(plan.left() + 4, plan.center().y()), mix(palette["accent"], palette["window"], 0.1)
    )
    assert window.solve_button.palette().buttonText().color().name() == palette["accent"]
    more = bar(window, "moreButton")
    assert more.palette().buttonText().color().name() == palette["text"]
    spot = box(window, more)
    assert near(picture.pixelColor(spot.left() + 3, spot.center().y()), palette["window"])


def states_host(
    qapp: QApplication, host: QWidget, palette: dict
) -> tuple[QPushButton, QPushButton, QPushButton]:
    host.setStyleSheet(pack_stylesheet("light-frost", False, None, "default", palette, control_art(palette)))
    row = QHBoxLayout(host)
    made = []
    for words, kind in (("Add", None), ("Preview", "secondary"), ("More", "quiet")):
        button = QPushButton(words)
        if kind:
            button.setProperty(kind, True)
        row.addWidget(button)
        made.append(button)
    host.show()
    host.activateWindow()
    QTest.qWaitForWindowActive(host)
    for _ in range(3):
        qapp.processEvents()
    return made[0], made[1], made[2]


def hover_fill(button: QPushButton) -> QColor:
    """The colour just inside a button's left edge as the style draws it with the pointer on it.

    Drawn from the style with the hover state set: a moved pointer on the offscreen platform reaches
    whichever test window is on top, which in a parallel run can be one an earlier test left open."""
    option = QStyleOptionButton()
    button.initStyleOption(option)
    option.state |= QStyle.StateFlag.State_MouseOver
    image = QImage(button.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    button.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, button)
    painter.end()
    return image.pixelColor(4, button.height() // 2)


def fill(button: QPushButton) -> QColor:
    """The colour just inside a button's left edge, clear of its words and its 2-pixel edge."""
    return button.grab().toImage().pixelColor(4, button.height() // 2)


def test_every_button_answers_hover_press_and_disabled(qapp: QApplication, host: QWidget) -> None:
    """Decision 11: no button had a pressed state and filled buttons had no hover, so pressing Add gave
    no feedback. 6 % of the text colour on hover, 10 % pressed; a disabled button at 40 %."""
    palette = resolved_palette("light-frost", False, None)
    primary, secondary, quiet = states_host(qapp, host, palette)
    text, page = palette["text"], palette["window"]
    tint = mix(palette["accent"], page, 0.1)
    for button, rest in ((primary, palette["accent"]), (secondary, tint)):
        assert near(fill(button), rest), button.text()
        assert near(hover_fill(button), mix(text, rest, 0.06)), f"{button.text()} on hover"
        button.setDown(True)
        assert near(fill(button), mix(text, rest, 0.10)), f"{button.text()} pressed"
        button.setDown(False)
        button.setEnabled(False)
        assert near(fill(button), mix(rest, page, 0.4)), f"{button.text()} disabled"
        button.setEnabled(True)
    quiet.setDown(True)
    pressed = fill(quiet)
    quiet.setDown(False)
    assert not near(pressed, fill(quiet)), "a quiet button shows no press"


def test_the_key_that_reaches_a_button_rings_it_and_a_click_does_not(
    qapp: QApplication, host: QWidget
) -> None:
    """No button showed keyboard focus. Qt's focus also holds after a click, which would ring every
    button pressed, so only Tab rings one: 2 pixels at 40 % of the accent."""
    keyboard_focus_rings(qapp)
    palette = resolved_palette("light-frost", False, None)
    primary, _secondary, quiet = states_host(qapp, host, palette)
    ring = mix(palette["accent"], palette["window"], 0.4)

    def edge(button: QPushButton) -> QColor:
        return button.grab().toImage().pixelColor(0, button.height() // 2)

    for button in (primary, quiet):
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        qapp.processEvents()
        assert button.hasFocus() and not near(edge(button), ring), f"{button.text()} ringed by a click"
        # Tab round to it again, as a student does.
        for _ in range(3):
            QTest.keyClick(host.focusWidget(), Qt.Key.Key_Tab)
        qapp.processEvents()
        assert button.hasFocus() and near(edge(button), ring), button.text()


def test_the_chosen_view_is_raised_on_its_track(qapp: QApplication, window: NativeWindow) -> None:
    """The chosen segment was white on grey with a hairline; it is the card colour on a track of 6 % of
    the text, lifted by the small shadow. High contrast keeps its outlined track and yellow choice."""
    window.resize(1280, 800)
    shown(qapp, window, "week")
    for pack, preset in (
        ("light-frost", "default"),
        ("dark-frost", "default"),
        ("light-frost", "high-contrast"),
    ):
        palette = dress(qapp, window, pack, preset)
        picture = window.grab().toImage()
        week, day = box(window, bar(window, "viewWeek")), box(window, bar(window, "viewDay"))
        contrast_look = preset == "high-contrast"
        chosen = palette["accent"] if contrast_look else palette["panel"]
        track = palette["window"] if contrast_look else mix(palette["text"], palette["window"], 0.06)
        assert near(picture.pixelColor(week.left() + 6, week.center().y()), chosen), (pack, preset)
        assert near(picture.pixelColor(day.left() + 4, day.center().y()), track), (pack, preset)
        under = picture.pixelColor(week.center().x(), week.bottom() + 1)
        if contrast_look:
            assert near(under, track), "High contrast has no shadows"
        else:
            assert under.lightness() < QColor(track).lightness(), f"{pack}: the chosen view casts no shadow"


def laid_over(area: QAbstractScrollArea) -> bool:
    """The vertical bar lies over the right of what scrolls, not in a strip beside it."""
    bar_ = area.verticalScrollBar()
    port = area.viewport().mapTo(area, QPoint(0, 0)).x()
    held = bar_.mapTo(area, QPoint(0, 0)).x()
    inside = port <= held and held + bar_.width() <= port + area.viewport().width()
    return bool(bar_.property("overlay")) and inside


def painted(bar_: QWidget) -> QImage:
    """What the bar itself paints, on nothing. grab() fills a widget's background first, and a bar laid
    over the hours has none of its own: on screen the hours show through round its handle."""
    image = QImage(bar_.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    bar_.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return image


def inked_columns(image: QImage) -> int:
    """How wide the handle is drawn: columns with any pixel at a fifth of full ink or more. The faint
    groove laid under a wide bar is a sixteenth, and is not the handle."""
    return sum(
        1
        for x in range(image.width())
        if any(image.pixelColor(x, y).alpha() >= 51 for y in range(image.height()))
    )


def test_the_hours_scroll_under_a_thin_bar_that_widens_under_the_pointer(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Decision 12: the bar took a strip of its own beside the hours. It lies over their edge, thin,
    and widens when the pointer is on it."""
    window.resize(1280, 800)
    shown(qapp, window, "week")
    scroll = window.week_table.scroll
    bar_ = scroll.verticalScrollBar()
    assert bar_.isVisible() and bar_.maximum() > 0
    assert laid_over(scroll), "the bar still takes a strip beside the hours"
    rest = inked_columns(painted(bar_))
    QApplication.sendEvent(bar_, QEvent(QEvent.Type.Enter))
    wide = inked_columns(painted(bar_))
    QApplication.sendEvent(bar_, QEvent(QEvent.Type.Leave))
    assert 0 < rest < wide, (rest, wide)
    assert rest <= 6, f"{rest} pixels wide at rest"


def test_month_and_settings_scroll_under_the_same_bars(qapp: QApplication, window: NativeWindow) -> None:
    window.resize(1280, 800)
    shown(qapp, window, "month")
    month = window.month_grid.scroll
    month.widget().setMinimumHeight(month.height() * 2)
    qapp.processEvents()
    assert month.verticalScrollBar().isVisible() and laid_over(month)
    window._open_settings()
    wait_until(qapp, lambda: window._settings is not None and window._settings.isVisible())
    area = window._settings.stack.currentWidget()
    assert area.verticalScrollBar().isVisible() and laid_over(area)
    window._settings.close_page()


def test_the_zoom_is_a_small_minus_plus_pill(qapp: QApplication, window: NativeWindow) -> None:
    """Decision 12: two bold text buttons became a 24-pixel pill of two icons with a line between."""
    window.resize(1280, 800)
    shown(qapp, window, "week")
    out, into = bar(window, "weekZoomOut"), bar(window, "weekZoomIn")
    pill = out.parentWidget()
    assert pill is into.parentWidget() and pill.property("zoomPill") and pill.height() == 24
    assert box(window, out).right() < box(window, into).left()
    assert out.icon().isNull() is False and into.icon().isNull() is False
