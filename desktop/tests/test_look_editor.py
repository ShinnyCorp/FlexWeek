"""The look editor (0.17's Customise, option B): the controls on the left in the look it starts from,
the window wearing every change at once and pictured on the right, saved looks kept by name and
offered under More looks, and one question on the way out when something is not saved."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from desktop.native import look_editor
from desktop.native.calendar import CATEGORIES
from desktop.native.custom_look import Problem, readability, save_look
from desktop.native.look import FONT_FAMILIES, MOTION_LEVELS, category_paint, resolved_palette
from desktop.native.look_editor import (
    Draft,
    LookEditor,
    hex_colour,
    open_draft,
    problem_rows,
    setting,
    with_setting,
)
from desktop.native.settings import SettingsPage
from desktop.native.tokens import MARK, WEIGHT_REGULAR, WEIGHT_STRONG, oklch, type_pt
from desktop.native.window import NativeWindow
from desktop.tests.window_support import look_file, qapp, server, signed_out, wait_until, window  # noqa: F401


def pump(qapp: QApplication, times: int = 12) -> None:  # noqa: F811
    for _ in range(times):
        qapp.processEvents()


def palette_of(window: NativeWindow) -> dict:  # noqa: F811
    pack, dark, accent = window._look_inputs()
    return resolved_palette(pack, dark, window._look, accent)


def open_editor(qapp: QApplication, window: NativeWindow) -> tuple[SettingsPage, LookEditor]:  # noqa: F811
    window.resize(1280, 800)
    window._open_settings()
    page = window._settings
    pump(qapp)
    page.customise.click()
    pump(qapp)
    return page, page.editor


def type_colour(qapp: QApplication, editor: LookEditor, name: str, colour: str) -> None:  # noqa: F811
    field = editor.findChild(QWidget, f"lookColour-{name}")
    field.hex.setText(colour)
    field.hex.textEdited.emit(colour)
    pump(qapp)


def shown(editor: LookEditor, kind: type, name: str) -> list:
    return [child for child in editor.findChildren(kind, name) if child.isVisibleTo(editor)]


def name_look(qapp: QApplication, editor: LookEditor, name: str) -> None:  # noqa: F811
    editor.name.setText(name)
    editor.name.textEdited.emit(name)
    editor.name.editingFinished.emit()
    pump(qapp)


# The editor's model, without Qt.


def test_a_setting_is_read_and_set_where_it_sits_in_a_custom_look() -> None:
    look = {"name": "Mine", "base": "light", "colours": {"page": "#101010"}}
    assert setting(look, ("colours", "page")) == "#101010"
    assert setting(look, ("colours", "card")) is None and setting(look, ("corners",)) is None
    changed = with_setting(look, ("categories", "class"), {"hue": 140})
    assert changed["categories"] == {"class": {"hue": 140}} and "categories" not in look
    # Back to the base's own: the setting goes, and a set left empty goes with it.
    assert with_setting(look, ("colours", "page"), None) == {"name": "Mine", "base": "light"}
    assert with_setting(changed, ("corners",), 4)["corners"] == 4


def test_the_editor_opens_on_the_look_worn_with_what_is_still_to_save() -> None:
    plain = open_draft("light-frost", {"preset": "default", "knobs": {}}, "default", [])
    assert plain.look["base"] == "light" and not plain.changed() and plain.state() == ""
    night = {"name": "Night study", "base": "nocturne", "corners": 4}
    saved = save_look([], night, "Night study")
    kept = open_draft("system", {"custom": dict(night)}, "default", saved)
    assert kept.saved_as == "Night study" and kept.state() == "Saved"
    moved = open_draft("system", {"custom": {**night, "corners": 12}}, "default", saved)
    assert moved.saved_as == "Night study" and moved.changed() and moved.state() == "Changed, not saved"
    assert moved.changed((("corners",),)) and not moved.changed((("spacing",),))
    # A look kept without saving has every change still to save, against the look it starts from.
    worn = {"custom": {"name": "Mine", "base": "paper", "accent": "sea"}}
    loose = open_draft("system", worn, "default", [])
    assert loose.saved_as is None and loose.start == {"name": "Mine", "base": "paper"} and loose.changed()


def test_three_block_colours_or_more_are_one_line_whose_fix_fixes_them_all() -> None:
    def problem(words: str, ratio: float, field: tuple[str, ...]) -> Problem:
        return Problem(words, "#000000", "#777777", ratio, field, "#aaaaaa")

    text = problem("Text on the page", 3.04, ("colours", "text"))
    blocks = [problem(f"Text on {key} blocks", ratio, ("categories", key)) for key, ratio in
              (("class", 4.49), ("study", 2.26), ("meals", 3.9))]
    rows = problem_rows([text, *blocks])
    assert [row.words for row in rows] == [
        "Text on the page is 3.0:1",
        "Text on 3 block colours is 2.2:1 at worst",
    ]
    assert rows[1].fixes == tuple(blocks)
    assert [row.words for row in problem_rows([text, *blocks[:2]])] == [
        "Text on the page is 3.0:1",
        "Text on class blocks is 4.4:1",
        "Text on study blocks is 2.2:1",
    ], "two block colours are two lines, and 4.49 never reads as 4.5"


def test_a_colour_is_typed_as_a_hex_code_with_or_without_its_hash() -> None:
    assert hex_colour("#3D6FC4") == "#3d6fc4"
    assert hex_colour(" 3d6fc4 ") == "#3d6fc4"
    assert hex_colour("#36c") == "#3366cc"
    assert [hex_colour(text) for text in ("#3d6fc", "blue", "#3d6fc44", "")] == [None] * 4


# The editor in the window.


def test_customise_fills_the_window_and_a_change_is_worn_at_once_while_the_controls_keep_their_look(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    before = palette_of(window)
    page, editor = open_editor(qapp, window)
    assert editor.isVisible() and editor.geometry() == page.rect()
    assert editor.state.text() == ""
    type_colour(qapp, editor, "page", "#1e2430")
    type_colour(qapp, editor, "text", "#999999")
    worn = window._look["custom"]
    assert worn["colours"]["page"] == "#1e2430" and worn["colours"]["text"] == "#999999"
    assert window.week_table.hours.painter.colours["window"] == "#1e2430"
    assert editor.state.text() == "Changed, not saved"
    assert editor.groups["colours"].tag.isVisible() and not editor.groups["shape"].tag.isVisible()
    # A grey the student is trying never greys out the editor: it keeps the look it started from.
    label = editor.findChild(QLabel, "lookFieldLabel")
    label.ensurePolished()
    assert label.palette().color(QPalette.ColorRole.WindowText).name() == before["text"]
    page.close_page()


def test_the_preview_is_the_window_as_it_is_worn(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    page, editor = open_editor(qapp, window)
    new_page = QColor("#1e2430")

    def pixels() -> int:
        image = editor.pictures[0].source.toImage()
        return sum(
            1
            for x in range(0, image.width(), 8)
            for y in range(0, image.height(), 8)
            if image.pixelColor(x, y) == new_page
        )

    assert editor.pictures[0].source.width() >= 1000, "the whole window, at its size"
    assert pixels() == 0
    type_colour(qapp, editor, "page", "#1e2430")
    assert pixels() > 50
    editor.zoom.buttons()[1].click()
    pump(qapp)
    shown = editor.pictures[0].image
    assert shown.width() == editor.pictures[0].source.deviceIndependentSize().width(), "actual size"
    assert editor.zoom_note.text() == look_editor.ACTUAL_NOTE
    page.close_page()


def test_done_keeps_the_look_by_its_name_and_more_looks_offers_it_beside_the_ten(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    page, editor = open_editor(qapp, window)
    type_colour(qapp, editor, "card", "#262d3b")
    name_look(qapp, editor, "Night study")
    editor.done.click()
    pump(qapp)
    assert page.editor is None and page.body.isVisible()
    assert [look["name"] for look in window._saved_looks] == ["Night study"]
    stored = json.loads(look_file().read_text())
    assert [look["name"] for look in stored["saved_looks"]] == ["Night study"]
    assert stored["custom"]["colours"]["card"] == "#262d3b"
    more = page.look.more
    listed = [more.itemText(index) for index in range(more.count())]
    assert listed[-2:] == ["Your looks", "Night study"] and "High contrast" in listed
    assert more.currentText() == "Night study", "Look shows the saved look worn"
    assert not page.accent.isEnabled() and not page.knobs["density"].isEnabled(), "the look sets them"
    page.look.main.buttons()[0].click()
    pump(qapp)
    assert "custom" not in window._look, "another look takes it off"
    assert page.accent.isEnabled() and page.knobs["density"].isEnabled()
    at = more.findData("saved:Night study")
    more.setCurrentIndex(at)
    more.activated.emit(at)
    pump(qapp)
    assert window._look["custom"]["name"] == "Night study"
    assert window.week_table.hours.painter.colours["panel"] == "#262d3b"
    page.close_page()


def test_leaving_with_changes_not_saved_asks_once_to_save_keep_or_discard(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers: list[str | None] = []
    asked: list[bool] = []

    def ask(_editor: LookEditor) -> str | None:
        asked.append(True)
        return answers.pop(0)

    monkeypatch.setattr(LookEditor, "ask_leave", ask)
    page, editor = open_editor(qapp, window)
    editor.back.click()
    pump(qapp)
    assert page.editor is None and not asked, "nothing changed, nothing to ask"
    page.customise.click()
    pump(qapp)
    editor = page.editor
    type_colour(qapp, editor, "page", "#1e2430")
    answers.append(None)
    editor.back.click()
    pump(qapp)
    assert page.editor is editor and len(asked) == 1, "Cancel stays in the editor"
    answers.append("keep")
    editor.back.click()
    pump(qapp)
    assert page.editor is None and len(asked) == 2
    assert window._look["custom"]["colours"]["page"] == "#1e2430", "kept on without saving"
    assert window._saved_looks == []
    assert page.look.more.placeholderText() == "My look (not saved)"
    page.customise.click()
    pump(qapp)
    editor = page.editor
    assert editor.state.text() == "Changed, not saved"
    answers.append("discard")
    editor.back.click()
    pump(qapp)
    assert page.editor is None and len(asked) == 3
    assert "custom" not in window._look, "discarded: the look from before any of the student's own"
    assert window.week_table.hours.painter.colours["window"] != "#1e2430"
    page.customise.click()
    pump(qapp)
    editor = page.editor
    type_colour(qapp, editor, "page", "#1e2430")
    answers.append("save")
    editor.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    pump(qapp)
    assert page.editor is None and len(asked) == 4, "Esc leaves as Back does"
    assert [look["name"] for look in window._saved_looks] == ["My look"]
    page.close_page()


def test_every_pair_under_four_and_a_half_to_one_has_a_fix_and_fix_all_makes_them_read(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    page, editor = open_editor(qapp, window)
    assert shown(editor, QLabel, "lookEverythingReads")
    type_colour(qapp, editor, "text", "#bbbbbb")
    type_colour(qapp, editor, "accent", "#ffee00")
    rows = problem_rows(readability(editor._draft.look))
    assert len(shown(editor, QPushButton, "lookFix")) == min(look_editor.READABILITY_ROWS, len(rows)) >= 2
    assert not shown(editor, QLabel, "lookEverythingReads")
    assert editor.fix_all.isVisibleTo(editor)
    editor.fix_all.click()
    pump(qapp)
    assert readability(editor._draft.look) == []
    assert shown(editor, QLabel, "lookEverythingReads") and not shown(editor, QPushButton, "lookFix")
    assert window._look["custom"]["colours"]["text"] != "#bbbbbb", "the fixed colour is worn"
    page.close_page()


def test_grey_text_is_written_on_the_blocks_and_their_colours_are_one_line_with_a_fix(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """The mock-up's bad colours: grey text on Light. The week writes the grey on its blocks as the
    student chose it, so the picture shows what Readability says, and the block colours are one line
    whose Fix moves them, not the text, until the grey reads."""
    school = {"id": "school", "title": "School", "kind": "locked", "category": "class",
              "start": "08:00", "duration_min": 405, "days": [0]}
    window.session.add_block(school)
    window.session.save()
    wait_until(qapp, lambda: not window.session.busy and not window.session.dirty)
    page, editor = open_editor(qapp, window)
    editor._start_from(editor.start_from.findData("base:light"))
    pump(qapp)
    type_colour(qapp, editor, "text", "#999999")
    said = [label.text() for label in shown(editor, QLabel, "lookWarnText")]
    assert said[-1] == "Text on 8 block colours is 2.2:1 at worst", said

    hours = window.week_table.hours
    if not hours.tracks:
        hours.resize(980, 640)
        hours.relayout()
    rect = next(
        rect for track in hours.tracks for drawn, rect in hours.drawn(track) if drawn.block_id == "school"
    )
    image = hours.grab().toImage()
    inside = [
        image.pixelColor(x, y)
        for x in range(int(rect.left()) + 8, int(rect.right()) - 2)
        for y in range(int(rect.top()) + 2, int(rect.bottom()) - 2)
    ]
    assert not [c for c in inside if max(c.red(), c.green(), c.blue()) < 0x50], "no black ink stands in"
    assert [c for c in inside if max(abs(c.red() - 0x99), abs(c.green() - 0x99), abs(c.blue() - 0x99)) < 8]

    fix = next(b for b in shown(editor, QPushButton, "lookFix") if b.accessibleName().endswith("at worst"))
    fix.click()
    pump(qapp)
    assert not [label for label in shown(editor, QLabel, "lookWarnText") if "block" in label.text()]
    custom = window._look["custom"]
    assert custom["colours"]["text"] == "#999999" and set(custom["categories"]) == set(CATEGORIES)
    page.close_page()


def test_the_editors_words_take_the_type_scale_of_the_look_it_starts_from(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """Decision 4: the editor's type is the window stylesheet's roles, as every screen's is, so it
    grows with the look's text. Its title and group names are headings in the heading face, its notes
    and small buttons captions, and a setting's name body text in the strong weight."""
    page, editor = open_editor(qapp, window)
    looks = (("light", 1.0, "sans"), ("high-contrast", 1.2, "sans"), ("paper", 1.0, "serif"))
    for base, scale, face in looks:
        editor._start_from(editor.start_from.findData(f"base:{base}"))
        pump(qapp)
        for kind, name, role, weight in (
            (QLabel, "lookEditorTitle", "heading", WEIGHT_STRONG),
            (QLabel, "lookGroupName", "heading", WEIGHT_STRONG),
            (QLabel, "lookFieldLabel", "body", WEIGHT_STRONG),
            (QLabel, "lookCategoryName", "body", WEIGHT_STRONG),
            (QLabel, "lookNote", "caption", WEIGHT_REGULAR),
            (QLabel, "lookOut", "caption", WEIGHT_REGULAR),
            (QLabel, "lookTag", "caption", WEIGHT_STRONG),
            (QLabel, "lookEverythingReads", "body", WEIGHT_REGULAR),
            (QLabel, "lookChip", "body", WEIGHT_STRONG),
            (QPushButton, "lookReset-colours", "caption", None),
        ):
            widget = editor.findChild(kind, name)
            widget.ensurePolished()
            font = widget.font()
            where = (base, name)
            assert font.pointSizeF() == type_pt(role, scale), where
            if weight is not None:
                assert font.weight().value == weight, where
        title = editor.findChild(QLabel, "lookEditorTitle")
        assert title.font().family() == FONT_FAMILIES[face].split(",")[0], base
    page.close_page()


def test_a_category_is_a_hue_on_the_family_or_an_exact_colour(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    page, editor = open_editor(qapp, window)
    editor.groups["categories"].toggle.setChecked(True)
    pump(qapp)
    row = editor.categories["class"]
    assert row.hue.isVisible() and not row.colour.isVisible()
    row.hue.setValue(140)
    pump(qapp)
    assert window._look["custom"]["categories"]["class"] == {"hue": 140.0}
    colours = window.week_table.hours.painter.colours
    family = colours.get("family", "light")
    assert category_paint("class", colours)[1] == oklch(*MARK[family], 140), "the family's mark at its hue"
    row.exact.click()
    pump(qapp)
    spec = window._look["custom"]["categories"]["class"]
    assert set(spec) == {"colour"} and hex_colour(spec["colour"]) == spec["colour"]
    assert row.colour.isVisible() and not row.hue.isVisible()
    row.exact.click()
    pump(qapp)
    assert set(window._look["custom"]["categories"]["class"]) == {"hue"}
    page.close_page()


def test_a_look_exports_to_a_small_file_imports_back_and_a_file_that_is_not_one_says_so(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    tmp_path: Path,
) -> None:
    page, editor = open_editor(qapp, window)
    type_colour(qapp, editor, "page", "#1e2430")
    name_look(qapp, editor, "Exams")
    shared = tmp_path / "exams.flexweek-look.json"
    assert editor.export_to(shared) and editor.said() == "Exported Exams."
    assert json.loads(shared.read_text())["kind"] == "FlexWeek look"
    assert editor.import_from(shared)
    pump(qapp)
    assert editor._draft.saved_as == "Exams" and editor.state.text() == "Saved"
    assert window._look["custom"]["colours"]["page"] == "#1e2430"
    other = tmp_path / "notes.json"
    other.write_text(json.dumps({"kind": "a shopping list"}))
    assert not editor.import_from(other)
    assert editor.said() == "This file is not a FlexWeek look."
    assert [look["name"] for look in editor._saved] == ["Exams"]
    assert not editor.import_from(tmp_path / "missing.json")
    assert editor.said() == look_editor.NOT_OPENED
    page.close_page()


@pytest.mark.parametrize("base", ["light", "high-contrast"])
def test_every_group_open_fits_the_column(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    base: str,
) -> None:
    """Four motion levels, a category row with its switch and a group's name with its tag were each wider
    than the 360-pixel column, which cut them at its edge; at High contrast's large text the column
    widens instead."""
    page, editor = open_editor(qapp, window)
    at = editor.start_from.findData(f"base:{base}")
    editor.start_from.setCurrentIndex(at)
    editor.start_from.activated.emit(at)
    pump(qapp)
    for card in editor.groups.values():
        card.toggle.setChecked(True)
    type_colour(qapp, editor, "page", "#f0f0f0")
    editor.categories["study"].exact.click()
    pump(qapp, 20)
    column = editor.column
    assert column.widget().width() <= column.viewport().width()
    for card in editor.groups.values():
        assert card.name.width() >= card.name.sizeHint().width(), card.group.name
        for control in card.findChildren(QWidget):
            if control.isVisibleTo(card):
                right = control.mapTo(column.widget(), control.rect().topRight()).x()
                assert right <= column.viewport().width(), (card.group.name, control.objectName())
    page.close_page()


def test_start_from_another_look_dresses_the_editor_in_it_and_the_motion_levels_are_the_looks(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    page, editor = open_editor(qapp, window)
    at = editor.start_from.findData("base:dark")
    editor.start_from.setCurrentIndex(at)
    editor.start_from.activated.emit(at)
    pump(qapp)
    dark = resolved_palette("dark-frost", True, {"custom": {"base": "dark"}})
    head = editor.findChild(QWidget, "lookEditorHead")
    assert head.grab().toImage().pixelColor(head.width() // 2, 4).name() == dark["window"]
    motion = editor.findChild(QWidget, "lookMotion")
    assert [motion.itemData(index) for index in range(motion.count())] == list(MOTION_LEVELS)
    assert [motion.itemText(index) for index in range(motion.count())] == ["Normal", "More", "Reduce", "Off"]
    motion.buttons()[2].click()
    pump(qapp)
    assert window._look["custom"]["motion"] == "reduce"
    page.close_page()


def test_a_saved_look_is_renamed_duplicated_and_deleted_from_the_editors_bar(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(look_editor, "confirm", lambda *_args, **_kwargs: True)
    page, editor = open_editor(qapp, window)
    assert not editor.delete.isVisibleTo(editor), "a new look has nothing to delete"
    editor.save_new.click()
    pump(qapp)
    assert editor._draft.saved_as == "My look" and editor.delete.isVisibleTo(editor)
    name_look(qapp, editor, "Paper")
    assert "one of FlexWeek's own looks" in editor.said() and editor.name.text() == "My look"
    name_look(qapp, editor, "Revision")
    assert [look["name"] for look in window._saved_looks] == ["Revision"]
    editor.duplicate.click()
    pump(qapp)
    assert [look["name"] for look in window._saved_looks] == ["Revision", "Revision copy"]
    editor.delete.click()
    pump(qapp)
    assert [look["name"] for look in window._saved_looks] == ["Revision copy"]
    assert editor._draft.saved_as is None and editor.name.text() == "My look"
    page.close_page()


def test_a_draft_with_nothing_changed_from_a_saved_look_says_saved() -> None:
    look = {"name": "Mine", "base": "ink"}
    assert Draft(look, dict(look), "Mine").state() == "Saved"
    assert Draft({**look, "corners": 2}, dict(look), "Mine").state() == "Changed, not saved"
