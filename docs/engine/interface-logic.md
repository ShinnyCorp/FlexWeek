# Logic that stays in the interface

The engine ports the planning and the Qt-free helpers. Anything that builds or paints a Qt widget stays in Python. This is the map of that code on v0.17.2, so a later rewrite knows where a decision is made. Nothing here moved.

A module is on this list because it imports PySide. The functions named under it are the ones that are not private. A test file is listed when `desktop/tests/test_<module>.py` exists. Widget tests that drive a whole window also cover `window.py` and the layouts without a file of that exact name (`test_layouts_window.py`, `test_native.py`, `test_hours_open.py`).

These stay even though some of them do not import Qt, because they write stylesheets, sounds, or the process environment: `desktop/native/look.py`, `desktop/native/layouts/registry.py`, `desktop/native/autostart.py`, `desktop/native/kept.py`, `desktop/native/tones.py`.

## Where a decision is made

- `desktop/native/window.py`. `NativeWindow` owns which page is showing, when a save runs, and how a dialog answers. `brand_row` is the small brand mark. Covered by the window tests in `desktop/tests/test_native.py` and `test_layouts_window.py`.
- `desktop/native/hours/canvas.py`. `HoursCanvas` and `BlockPainter` decide how a block is drawn: `fit_lines`, `word_elide`, `name_kept`, `block_layout`, `held_layout`. Covered by the hours tests (`test_hours_open.py` and the layout tests).
- `desktop/native/hours/zoom.py`. `sanitize_zoom` and `opening_minute` decide the zoom level and where the hours open. `HoursScroll` keeps that place. Covered by `test_hours_open.py`.
- `desktop/native/hours/hand.py`. `Gesture`, `Verdict`, `Held`, `Preview`, `Move`, and `Place` decide a drag. `span_words` is the sentence under the pointer.
- `desktop/native/hours/geometry.py`. `snap`, `drag_step`, and `overlap_columns` decide where a block sits on a track.
- `desktop/native/controller.py`. `NativeSession` decides save, solve, focus, and alarms. `plan_sentence` and `first_placed` are the words and the first placed block it shows.
- `desktop/native/layouts/`. Each design (`bento`, `clay`, `dial`, `mission`, `one_thing`, `retro`, `timeline`, `base`) decides its own arrangement and paint. The functions on those modules (for example Mission's `lanes_end` and `minutes_left`, Dial's `segments` and `turn`, Retro's `scheme` and `arrange`) are the design's rules. `layouts/registry.py` builds the dialog and stays. Covered by `test_layout_*.py` and `test_layouts_window.py`.
- `desktop/native/look.py` and `look_editor.py`. The stylesheet and the editor stay. The editor's `open_draft`, `problem_rows`, and `fix_all` decide what a custom look shows. Checks that do not need Qt are in the engine (`readability`, saved names). Covered by `test_look_editor.py` and `test_look.py`.
- `desktop/native/motion.py`. `motion_level`, `duration`, `distance`, and `settle` decide how far and how fast something moves. Covered by `test_motion.py`.
- `desktop/native/settings.py` and `setup.py`. Settings and first-run decide which controls exist and what they write. `style_layout` and `style_look` pick the setup pairing.
- `desktop/native/widgets.py`. Shared controls. `steady_wheel`, `keyboard_focus_rings`, and `fit_scroll_dialog` decide focus and scrolling.

## The other Qt modules

These also import PySide. Their public names are the decisions they own. A matching `desktop/tests/test_<name>.py` is marked when it exists.

| Module | What it decides | Matching test file |
|---|---|---|
| `client.py` | `sign_in_problem`, `sign_up_problem`, `auth_error` | no |
| `command_bar.py` | `match_rank`, `ranked`, `grouped` | yes |
| `elevation.py` | `lift` | no |
| `fields.py` | day, date, and clock fields | no |
| `focus_screen.py` | the focus screen widget | yes |
| `fonts.py` | `load_fonts`, `time_font`, `at_scale` | yes |
| `hours/chips.py` | tray chips | no |
| `hours/classic.py` | `open_hours`, `column_widths`, `day_shares` | no |
| `hours/month.py` | `month_cells` and the month canvas | no |
| `hours/rail.py` | `next_words`, `next_item`, `focus_when` | no |
| `icons.py` | `svg`, `pixmap`, `tint` | yes |
| `layouts/dialog.py` | the design picker | no |
| `layouts/empty.py` | `nothing_yet` | no |
| `look_preview.py` | `look_choice`, `look_preview` | no |
| `menus.py` | `menu_colours`, `words_and_keys` | yes |
| `previews.py` | `sample_week`, `render` | yes |
| `ring.py` | `ring_colours`, `arc_angles` | yes |
| `sound.py` | the bell | no |
| `spotify.py` | `playing_words`, `open_in_app` | yes |
| `updater.py` | `bundle_root`, `writable`, `apply_update` | no |
| `work_windows.py` | the work-window editor | no |
