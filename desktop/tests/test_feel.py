"""A Setup style's feel on Settings, a sheet, Setup and sign-in (J13, depth 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from desktop.native.feel import (
    Context,
    apply_feel,
    bevel_css,
    design_key,
    dressed_stylesheet,
    extra_stylesheet,
    feel_for,
    hero_contrast_ok,
    page_feel,
    sanitize_design,
    set_current,
    title_bar_contrast_ok,
)
from desktop.native.layouts.registry import MATCH, sanitize_layout, tokens_for
from desktop.native.look import pack_stylesheet, resolved_palette, sanitize_look
from desktop.native.motion import apply_ui_effects
from desktop.native.settings import SettingsPage
from desktop.native.setup import STYLES, SetupPage, style_layout, style_look
from desktop.native.tokens import RADIUS_CARD, RADIUS_SHEET
from desktop.native.widgets import HomeworkDialog, control_art
from desktop.native.window import NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    free,
    look_file,
    qapp,
    server,
    signed_out,
    still,
    window,
)

HEROES = ("settingsTitle", "sheetTitle", "setupTitle", "authBrand")

STYLE = {style.key: style for style in STYLES}


def _dressed(style_key: str) -> tuple:
    style = STYLE[style_key if style_key != "night_owl" else "night"]
    look = style_look(style)
    layout = style_layout(style, sanitize_layout(None))
    palette = resolved_palette(style.pack, False, look, "default")
    feel = feel_for(layout["main"])
    tokens = tokens_for(feel.layout, style.colour or MATCH, palette)
    base = pack_stylesheet(style.pack, False, look, "default", palette, control_art(palette))
    return style.pack, look, palette, tokens, feel, base, layout


def test_the_feel_is_the_main_view_not_the_colourway() -> None:
    assert feel_for("classic").key == "plain"
    assert feel_for("timeline").key == "night_owl"
    assert feel_for("bento").key == "dashboard"
    assert feel_for("retro").key == "retro"
    assert feel_for("clay").key == "plain"
    assert feel_for("mission").key == "plain"
    assert feel_for("dial").key == "plain"
    assert feel_for("one").key == "plain"
    assert design_key("bento") == "bento"
    assert design_key("clay") == "classic"
    assert sanitize_design("retro") == "retro"
    assert sanitize_design("nope") == "classic"


def test_plain_keeps_todays_stylesheet_byte_for_byte(qapp: QApplication) -> None:  # noqa: F811
    pack, look, palette, tokens, feel, base, _layout = _dressed("plain")
    assert extra_stylesheet(base, feel, palette, tokens, look) == ""
    art = control_art(palette)
    dressed = dressed_stylesheet(pack, False, look, feel, "default", palette, art, tokens)
    assert dressed == base


@pytest.mark.parametrize(
    ("style_key", "want"),
    [
        ("night", "Newsreader"),
        ("dashboard", f"border-radius: {RADIUS_SHEET}px"),
        ("retro", "Pixelify Sans"),
    ],
)
def test_each_style_adds_its_faces_or_radius(
    qapp: QApplication, style_key: str, want: str  # noqa: F811
) -> None:
    pack, look, palette, tokens, feel, base, _layout = _dressed(style_key)
    extra = extra_stylesheet(base, feel, palette, tokens, look, ("settingsTitle", "sheetTitle"))
    assert extra
    assert want in extra
    if style_key == "night":
        assert f"border-radius: {RADIUS_CARD}px" in extra
    if style_key == "retro":
        assert "border-radius: 0px" in extra
        assert "VT323" in extra
    if style_key == "dashboard":
        assert "hero" in extra.lower() or "background:" in extra


def test_hero_and_retro_title_bars_read_at_aa(qapp: QApplication) -> None:  # noqa: F811
    for style_key in ("dashboard", "night", "retro", "plain"):
        _pack, look, palette, tokens, feel, _base, _layout = _dressed(style_key)
        if feel.chrome == "hero":
            assert hero_contrast_ok(tokens)
        if feel.chrome == "win98":
            assert title_bar_contrast_ok(tokens)
        key = style_key if style_key != "night_owl" else "night"
        for pack, dark in (("light-frost", False), ("nocturne", True)):
            palette = resolved_palette(pack, dark, look, "default")
            tokens = tokens_for(feel.layout, STYLE[key].colour or MATCH, palette)
            if feel.chrome == "hero":
                assert hero_contrast_ok(tokens), (pack, dark)
            if feel.chrome == "win98":
                assert title_bar_contrast_ok(tokens), (pack, dark)


def _host(app: QApplication, style_key: str) -> tuple[QWidget, Context]:
    pack, look, palette, tokens, feel, base, _layout = _dressed(style_key)
    extra = extra_stylesheet(base, feel, palette, tokens, look, HEROES)
    host = QWidget()
    host.setStyleSheet(base + extra)
    host.resize(1280, 800)
    ctx = Context(feel, look, palette, tokens, base)
    set_current(ctx)
    host.show()
    app.processEvents()
    return host, ctx


def _setup_style(style_key: str):
    return STYLE["night" if style_key == "night_owl" else style_key]


def test_settings_and_a_sheet_and_setup_show_the_feel(qapp: QApplication) -> None:  # noqa: F811
    for style_key, radius, font, frame in (
        ("plain", None, None, False),
        ("night", RADIUS_CARD, "Newsreader", False),
        ("dashboard", RADIUS_SHEET, None, False),
        ("retro", 0, "Pixelify", True),
    ):
        host, ctx = _host(qapp, style_key)
        chosen = _setup_style(style_key)
        prefs = {"alarms": [], "reminders_enabled": True, "theme_pack": chosen.pack}
        layout = style_layout(chosen, sanitize_layout(None))
        page = SettingsPage(host, prefs, ctx.look, {}, layout)
        apply_feel(page, ctx)
        qapp.processEvents()
        extra = extra_stylesheet(
            ctx.base_sheet, ctx.feel, ctx.palette, ctx.tokens, ctx.look, ("settingsTitle",)
        )
        if font:
            assert font in host.styleSheet() or font in extra
        assert (page.findChild(QWidget, "win98Frame") is not None) is frame
        if ctx.feel.chrome == "hero":
            assert page.findChild(QWidget, "bentoHeroIcon") is not None
        dialog = HomeworkDialog(host, today="2026-10-01")
        dialog.show()
        apply_feel(dialog, ctx)
        qapp.processEvents()
        assert (dialog.findChild(QWidget, "win98Frame") is not None) is frame
        if radius is not None and ctx.feel.key != "plain":
            extra = extra_stylesheet(
                ctx.base_sheet, ctx.feel, ctx.palette, ctx.tokens, ctx.look, ("sheetTitle",)
            )
            assert f"border-radius: {radius}px" in extra
        setup = SetupPage(host)
        setup.motion = "off"
        apply_feel(setup, ctx)
        qapp.processEvents()
        assert (setup.findChild(QWidget, "win98Frame") is not None) is frame
        dialog.close()
        free(dialog)
        free(page)
        free(setup)
        free(host)


def test_motion_off_changes_the_feel_at_once(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    apply_ui_effects("off")
    window.session.preferences = {**(window.session.preferences or {}), "motion": "off"}
    for fade in window.findChildren(QLabel, "motionFade"):
        fade.hide()
        fade.deleteLater()
    qapp.processEvents()
    window._layout = sanitize_layout({"main": "bento", "day": "dial"})
    window._apply_appearance()
    assert window._motion == "off"
    assert page_feel().key == "dashboard"
    assert page_feel().chrome == "hero"
    still(window)


def test_large_text_does_not_cut_titles(qapp: QApplication) -> None:  # noqa: F811
    for style_key in ("plain", "night", "dashboard", "retro"):
        host, ctx = _host(qapp, style_key)
        look = sanitize_look({**ctx.look, "knobs": {**ctx.look.get("knobs", {}), "text": "large"}})
        ctx = Context(ctx.feel, look, ctx.palette, ctx.tokens, ctx.base_sheet)
        prefs = {"alarms": [], "theme_pack": "light-frost"}
        page = SettingsPage(host, prefs, look, {})
        apply_feel(page, ctx)
        title = page.findChild(QLabel, "settingsTitle")
        assert title is not None
        assert title.wordWrap() or title.text()
        dialog = HomeworkDialog(host, today="2026-10-01")
        dialog.show()
        apply_feel(dialog, ctx)
        heading = dialog.findChild(QLabel, "sheetTitle")
        assert heading is not None
        assert heading.text() == "Add homework"
        dialog.close()
        free(dialog)
        free(page)
        free(host)


def test_retro_title_sits_on_a_full_width_bar(qapp: QApplication) -> None:  # noqa: F811
    host, ctx = _host(qapp, "retro")
    prefs = {"alarms": [], "reminders_enabled": True, "theme_pack": "light-frost"}
    page = SettingsPage(host, prefs, ctx.look, {}, style_layout(STYLE["retro"], sanitize_layout(None)))
    page.resize(1280, 800)
    apply_feel(page, ctx)
    qapp.processEvents()
    bar = page.findChild(QWidget, "win98TitleBar")
    words = page.findChild(QLabel, "win98Title")
    assert bar is not None
    assert words is not None
    assert words.text() == "Settings - FlexWeek"
    assert bar.width() == page.width() - 8
    dialog = HomeworkDialog(host, today="2026-10-01")
    dialog.show()
    apply_feel(dialog, ctx)
    qapp.processEvents()
    card = dialog.findChild(QWidget, "sheetCard")
    assert card is not None
    bar = card.findChild(QWidget, "win98TitleBar")
    words = card.findChild(QLabel, "win98Title")
    assert bar is not None
    assert words is not None
    assert words.text() == "Add homework"
    assert bar.width() == card.width() - 8
    close = card.findChild(QPushButton, "win98Cap-close")
    assert close is not None
    close.click()
    qapp.processEvents()
    assert not dialog.isVisible()
    dialog = HomeworkDialog(host, today="2026-10-01")
    dialog.show()
    apply_feel(dialog, ctx)
    qapp.processEvents()
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    qapp.processEvents()
    assert not dialog.isVisible()
    free(page)
    free(host)


def test_retro_bevels_are_raised_and_sunken(qapp: QApplication) -> None:  # noqa: F811
    pack, look, palette, tokens, feel, base, _layout = _dressed("retro")
    extra = extra_stylesheet(base, feel, palette, tokens, look, ("sheetTitle",))
    assert "border-width: 2px" in extra
    assert bevel_css("raised") in extra
    assert bevel_css("sunken") in extra
    host, ctx = _host(qapp, "retro")
    dialog = HomeworkDialog(host, today="2026-10-01")
    dialog.show()
    apply_feel(dialog, ctx)
    qapp.processEvents()
    assert dialog.findChild(QWidget, "win98Bevels") is not None
    dialog.close()
    free(dialog)
    free(host)


def test_week_page_chrome_is_unchanged_by_j13(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    for main in ("classic", "timeline", "bento", "retro"):
        window._layout = sanitize_layout({"main": main, "day": "dial"})
        window._apply_appearance()
        still(window)
        pack, system_dark, accent = window._look_inputs()
        palette = resolved_palette(pack, system_dark, window._look, accent)
        base = pack_stylesheet(pack, system_dark, window._look, accent, palette, control_art(palette))
        assert window.styleSheet() == base
        page = window._page_palette(palette)
        page_sheet = ""
        if page is not None:
            page_sheet = pack_stylesheet(pack, system_dark, window._look, accent, page, control_art(page))
        assert window.planner.styleSheet() == page_sheet
        week = window.findChild(QWidget, "weekPage")
        assert week is not None
        assert week.findChild(QWidget, "win98Frame") is None
        assert window.rail.findChild(QWidget, "win98Frame") is None
        feel = feel_for(main)
        extra = extra_stylesheet(
            base, feel, palette, tokens_for(feel.layout, MATCH, palette), window._look
        )
        if extra:
            assert extra not in window.styleSheet()
            assert extra not in window.planner.styleSheet()


def test_sign_in_wears_the_last_design_this_computer_used(
    qapp: QApplication, signed_out: NativeWindow  # noqa: F811
) -> None:
    path = look_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "preset": "default",
                "knobs": {},
                "layout": {"main": "retro", "day": "dial", "options": {}},
            }
        )
    )
    signed_out._load_look()
    signed_out._apply_appearance()
    still(signed_out)
    assert page_feel().key == "retro"
    assert signed_out.findChild(QWidget, "win98Frame") is not None
    assert "Pixelify" in signed_out.findChild(QWidget, "authPage").styleSheet()
    signed_out._save_look()
    saved = json.loads(path.read_text())
    assert "design" not in saved
    assert saved["layout"]["main"] == "retro"


def test_window_imports_current_once() -> None:
    import desktop.native.feel as feel
    import desktop.native.window as native_window

    assert native_window.current is feel.current
    source = Path(native_window.__file__).read_text()
    assert source.count("from desktop.native.feel import current") == 0
    assert "current," in source.split("from desktop.native.feel import", 1)[1].split("\n", 1)[0]
