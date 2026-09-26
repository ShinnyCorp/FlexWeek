# FlexWeek 0.16: the working plan

Timmy and AL's design review of 0.15.0, checked in `design-review.md`, is done in full. Jonathan's
answer to its sixteen decisions was "Do all of them" (25 September), so each decision below takes
the reviewers' recommendation, with Claude's call where the recommendation left room. The result is
0.16.0: one polished default look, a calmer week, one notice, and the eight bugs fixed.

## Decisions (25 September)

1. **Add is the main action** (R1). Today's app's top bar has Add as the one filled button; a click
   adds homework, its arrow offers Fixed time and School hours. Plan my homework is plain beside it.
2. **Week gets Day's sidebar** (R2). The Next line, the focus list and Not placed yet move into a
   sidebar on the right of Week, as Day has. Under 1150 px the sidebar folds into one slim line.
3. **One polished default** (R3, R4). Today's app is the default main view, Day dial the default
   day screen, and Timeline the one alternative offered beside it. Mission control, Bento, Retro
   desktop and Clay deck stay, under "Experimental styles" in setup and Settings. Looks are System,
   Light, Dark and High contrast with an accent; Nocturne, Slate, Poster, Terminal, Paper, Ink and
   Pastel are experimental. Nothing is deleted and every saved id still loads. The chrome and the
   default designs share one type scale, one button style and one set of corner radii.
4. **A segmented control** (R6) for Day, Week, Month and My day.
5. **Inter is bundled** (R7): Regular, Medium, SemiBold and Bold from Inter 4.1 (OFL), loaded at
   start, with tabular numbers on every time. The system's font is the fallback.
6. **Padding** (R8): 16 px comfortable and 8 px compact on cards; dialogs 24 px.
7. **Settings is a page** (R11, R18), not a dialog: a section list on the left, grouped cards on
   the right, toggles for on/off, segmented controls for two or three choices, and the design
   picker uses setup's pictures. Routines, Running late and Quick focus are laid out as cards.
8. **Activity is teal** (R13), not pink, so it never reads as homework's coral. Dark looks draw
   blocks in deeper fills with light ink.
9. **Grid and blocks** (R15, R16, R19, R27). Half-hour rules go; the now line carries the time;
   today's column is stronger; Day's homework blocks have a mark stripe and a shadow at depth;
   Summary is rows. A view switch crossfades; blocks slide to their places after Plan; dialogs and
   toasts ease in.
10. **One toast** (R17) carries every notice and its Undo, floats over the foot of the hours, goes
    on a view switch, and never sits below the window. The status line is gone.
11. **Month opens on the current week** (R20) as its first row.
12. **Help, About and the brand** (R22, R23). Help is a two-column page; About's folder is an
    "Open folder" button; the wordmark and icon are the app's own, in its blue; "Welcome" on first
    launch.
13. **A 12-hour clock** (R25) is a Settings choice, off by default, honoured everywhere a time is
    written.
14. **The smallest window is 800 px wide** (R26). Below 1150 the sidebar folds and blocks use short
    forms; nothing is cut in half at 800.
15. **A click opens a block** (R29, R30); a drag moves it. Right-click offers Open, Duplicate,
    Finished (homework) and Delete. School hours has its own dialog: days and times, as setup asks.
16. **Three additions** (R32 to R34): an empty-week screen with one "Add your first homework"
    button, a full-screen focus timer, and a Ctrl+K command bar for adding and jumping.

Bugs with no decision: R10 quiet buttons, R12 dark fills, R14 the two-line test, R21 setup's
presets and Play column, R23 "Welcome", R24 recovery codes, R25 arrows, R28 the title placeholder.

## How it is run

Lanes on branches off `feat/0.16-polish` (from `claude/0-16-review` at 8392ed3), each landed by
Claude after review. Lane A first, since its type, spacing and colours change every picture; C1,
C2 and F start with it; B and E start once A has landed, since they share `window.py` and
`canvas.py` with it. Each lane ends green on `scripts/verify.py` through `run-alone.sh`, on the
mutation specs it touches, on the rig where it touches hours, and with its screens read from the
two tours (`~/.flexweek-ui-harness/scratch/audit_tour_2.py`, `audit_setup.py`). Subagents use
Opus. Local commits only; the PR and release come last, on Jonathan's word.

## Lane A. Type, space and colour (foundation)

Files: `desktop/assets/fonts/`, `desktop/main.py`, `desktop/build_linux.sh`,
`desktop/build_windows.ps1`, `desktop/native/look.py`, `desktop/native/calendar.py`,
`desktop/native/hours/canvas.py`, `desktop/native/layouts/mission.py:67`, tests.

Build:
- Inter Regular, Medium, SemiBold and Bold from `~/.flexweek-ui-harness/scratch/inter/extras/ttf/`
  into `desktop/assets/fonts/` with `LICENSE.txt`. `main.py` loads them with
  `QFontDatabase.addApplicationFont` before the window. `FONT_FAMILIES["sans"]` starts with Inter.
  Both build scripts pass `--include-data-dir` for `desktop/assets` (this also ships `logo.png`,
  which `app_icon_path` looks for and the bundle never had). `check_bundle.py` and the packaging
  tests know the folder.
- Tabular numbers: a `time_font(base)` in `look.py` that sets the `tnum` feature (Qt 6.7+
  `QFont.setFeature`), used by the hour labels, block times, the now label, the Next line and every
  `QTimeEdit`.
- `DENSITY_PAD` 16 and 8; `QDialog` content margins 24. Buttons and fields keep their heights.
- `CATEGORIES["extra"]` teal (`#a5f3fc`, mark `#06b6d4`). `block_paint` on a dark pack mixes the
  category colour into the panel (about 35 % colour) and uses light ink; rules on dark packs use a
  `grid` token two steps lighter.
- `canvas.py` `track`: no half-hour rule; today's wash 10 % and a 2 px accent line under its day
  name; `now` writes the time on a small pill at the left of the line; `words` takes the two-line
  form when `room.height() >= bold_line + small_line`.

You see: every screen in Inter; Club at 19:00 shows its name and its times; Soccer practice teal
beside coral homework; Dark frost blocks deep, not pastel; no dashed lines; "15:40" on the now line.

Verify: `test_look.py` (padding, font stack, dark fills), `test_hours_painter.py` (two-line rule,
now label, no half-hour rule), `test_native_packaging.py` (fonts in the bundle args); the gate; rig
classic Day and Week; `audit_tour_2.py` read.

## Lane B. Chrome: the top bar, Week's sidebar, one toast, Month, the floor

Files: `desktop/native/window.py`, `desktop/native/widgets.py` (Toast, EndsLayout),
`desktop/native/hours/classic.py`, `desktop/native/hours/month.py`, `desktop/native/look.py` (the
segment and toast rules), tests, `scripts/rig/` selectors if a name changes.

Build:
- Top bar: `viewDay/Week/Month/MyDay` in one `QFrame#segments` drawn as a segmented control; an
  `addButton` (filled, with a menu: Add homework, Add fixed time, School hours) replaces the More >
  Adding group; `solveButton` plain. `_keep_bar_whole` and `EndsLayout` keep the wrap at 800.
- Week sidebar: a `WeekSide` (250 px, `hours/classic.py`) holding the Next line, the focus tasks
  and Not placed yet, shown by `_sync_chrome` when main is classic; `focus_panel` keeps only its
  running state above the hours. Under 1150 px the side folds into one slim line above the hours.
- One toast: `Toast` grows a button (`Undo`, `Find a new time`, `Open release page`), floats at
  the foot of the planner, centred, mouse-transparent except its button, eases in, goes after 6 s
  or on a view switch, and never extends below the window. `_set_notice` and `week_status` route
  to it; `_status_row`, `action_notice` and `week_status` are removed with their tests updated.
  A reminder left on screen still uses `alert_strip`.
- Month: `MonthGrid.reveal` scrolls the scroll bar to the top of the current week's row, after
  the canvas has its height (a second `singleShot` when the height is still the minimum).
- `WINDOW_MIN_WIDTH` 800; block words use `PLAN_SHORT`-style short forms under 1150 px.

You see: Day | Week | Month | My day as one control; Add filled, Plan plain; Week's hours reach
the top; a toast "Moved History essay to Fri 18:00. Undo" over the foot of the hours; Month with
this week first.

Verify: `test_drag_results.py` (notice tests move to the toast), `test_hours_month.py` (first
row), a new `test_week_side.py`; the gate; rig classic Day, Week and Month; both tours read at
1280x860, 1150x768 large text, 800 and 650.

## Lane C1. Settings as a page, Experimental styles, dialogs' buttons, setup

Files: `desktop/native/settings.py`, `desktop/native/layouts/dialog.py`,
`desktop/native/layouts/registry.py`, `desktop/native/look.py` (`look_menu_items`, switch and
segmented QSS), `desktop/native/setup.py`, `desktop/native/work_windows.py`,
`desktop/native/widgets.py` (dialog buttons), tests.

Build:
- `LayoutSpec.experimental`; `layouts_for(role, experimental=False)`; `MAIN_DEFAULT = "classic"`,
  `DAY_DEFAULT = "dial"`. `look_menu_items` returns groups. Every picker (Settings main view, day
  screen and Look; setup's style cards, look cards and day chips) shows the standard entries first
  and an "Experimental styles" heading before the rest. `sanitize_layout` and `sanitize_look`
  unchanged, so saved ids load.
- Settings becomes `settingsPage` in the window's stack (`_show_page("settingsPage")`, Esc or
  Done returns): nav on the left, cards on the right, a `Switch` (styled `QCheckBox`) for on/off, a
  `Segmented` control for two or three choices (spacing, corners, depth, blocks, text, motion,
  preferred view, drag step), the main-view picker as cards with setup's pictures, and the
  Appearance page in the order design, colours, day screen, every screen.
- Every dialog has one filled button: `quiet` on More details, Show, Routines' Apply, Delete and
  Close, and any other second filled button found by a test that walks every dialog's buttons.
  Routines, Running late and Quick focus laid out as cards with a heading and a sentence each.
- Setup: the planning-hours presets are quiet "+ After school" buttons under a sentence that says
  each adds a row; the alarm sounds are a two-column form with Play in its own column, aligned.

You see: Settings fills the window with cards; Spacing as Comfortable | Compact; Retro under
Experimental styles; one blue button per dialog; "+ After school" adds a row.

Verify: `test_layouts_registry.py`, `test_settings_words.py`, `test_setup_wizard.py`, a new
`test_one_filled_button.py`; the gate; `audit_setup.py` and the Settings pictures read.

## Lane C2. Sign in, words, Help, About, the brand, the clock

Files: `desktop/native/window.py` (the auth and recovery pages, `_open_about`), `desktop/native/
settings.py` (`HelpDialog`, `AboutDialog`), `desktop/native/widgets.py` (`HomeworkDialog` title,
Running late's rows), `desktop/native/setup.py` ("Choose my own look instead"), `desktop/assets/
logo.png`, `desktop/native/weekmodel.py` (`clock_label`), `backend/app.py` (`clock_24h`),
`backend/slots.py` callers, tests.

Build:
- "Welcome" on first launch (no account on this computer), "Welcome back." after. Recovery codes
  in `MONO_FAMILY` with Copy (clipboard) and Save (a text file through `QFileDialog`).
- `HomeworkDialog` starts with an empty title and the category label as `placeholderText`.
- "→" becomes words: "from 16:00 to 17:30" in Running late's rows; "Choose my own look instead".
- Help as two columns (screens left, shortcuts right) at 900 px, one column at large text. About
  shows "Open folder" (`QDesktopServices.openUrl`) instead of the path.
- A new `logo.png` (and a 256 px `logo.ico` for Windows) drawn by a script in `scripts/brand.py`:
  a rounded blue square with a white week-block glyph, in the accent `#3b6fc9` family. The
  wordmark label uses Inter SemiBold in the accent, with the icon beside it on sign in.
- `clock_24h` preference (default true) through the schema, storage and Settings > This computer
  ("Clock: 24-hour | 12-hour"); `clock_label` and `minutes_to_hhmm` callers that write a time to
  the screen go through one `clock_text(minute)` that reads the preference; time boxes keep
  `HH:mm` or take `h:mm AP`.

You see: "Welcome" with the icon; codes in mono with two buttons; an empty Title with "Homework"
greyed; "4:00 PM" everywhere after the switch.

Verify: `test_auth_words.py`, `test_homework_dialog.py`, `test_clock.py` (both formats at every
call site, by a walk of the screens), backend tests for the preference; the gate; sign-in and
recovery pictures read.

## Lane E. Opening blocks, the context menu, School hours, motion

Files: `desktop/native/hours/hand.py`, `desktop/native/hours/canvas.py` (press paths, context
menu, settle animation), `desktop/native/window.py` (`_edit_block`, the menu's actions, School
hours), `desktop/native/widgets.py` (`SchoolHoursDialog`), `desktop/native/motion.py`, tests,
`scripts/mutations/targets.json`.

Build:
- A tap on a block opens it (`Hand.press(..., tap=lambda: self.hand.open(id))`); a drag still
  moves; Enter still opens the selection. `contextMenuEvent` on the canvas, month chips and tray
  chips emits `menu_requested(block_id, day, global_pos)`; the window shows Open, Duplicate,
  Finished (homework only) and Delete, each through the existing actions.
- `SchoolHoursDialog`: days and start/end as setup's Your week page, writing the School block
  through the same controller path; More > School hours and the Add menu open it.
- Motion: `switch_page` crossfades by fading the new page in over the held picture (opacity on
  the new page, not only the old); `HoursCanvas.set_week` keeps the last rects per block and, at a
  motion level above off, animates changed blocks from old to new over `DURATION_MS`; dialogs
  `appear` on show (a `Dialog` base in `widgets.py`); the toast already eases in.

You see: a click opens the editor; right-click shows four items; School hours asks days and
times; after Plan the new blocks slide into place.

Verify: `test_hours_hand.py` (tap opens, drag still moves), `test_context_menu.py`,
`test_school_hours.py`, `test_motion.py`; `targets.json` gains the tap rule; the gate; rig classic
Day and Week (the rig's open-by-tap scenario changes from double to single click).

## Lane F. The empty week, the focus screen, Ctrl+K

Files: new `desktop/native/layouts/empty.py`, `desktop/native/focus_screen.py`,
`desktop/native/command_bar.py`; `desktop/native/window.py` (the stack, `keyPressEvent`,
`eventFilter`); `desktop/native/settings.py` (`HELP_KEYS`); tests.

Build:
- Empty week: when `leftover_kind == "no_homework"` and the week has no blocks, the planner shows
  `EmptyWeek` in place of the hours: one sentence and one "Add your first homework" button; the
  hours return with the first block or homework.
- Focus screen: `FocusScreen`, a page in the stack opened by Start focus, Quick focus or F: the
  countdown in Inter Bold at 96 pt, the task, the phase, Pause, Skip and Finish, the pack's colours
  with the accent, Esc returns. `FocusPanel` shrinks to its running-state line.
- Ctrl+K: `CommandBar`, a centred box over the window with a line edit and a list; commands are
  Add homework, Add fixed time, School hours, Day, Week, Month, My day, Plan my homework, Settings,
  Help, and every homework title (opens it). Typing filters; Enter runs; Esc closes.

You see: a new account's week says "Add your first homework"; the focus screen fills the window;
Ctrl+K, "ma", Enter opens Math worksheet.

Verify: `test_empty_week.py`, `test_focus_screen.py`, `test_command_bar.py`; the gate; pictures
of the three screens read.

## Integration and release

- Land A, then B, C1, C2, E and F on `feat/0.16-polish`, resolving overlaps in `window.py`.
- The gate through `run-alone.sh`; every mutation spec; the rig for classic Day, Week and Month,
  Timeline Day and Week, and one design from each of the other four, plus both My day screens; the
  two tours at four sizes read against `design-review.md` row by row.
- Docs: `CHANGELOG.md` 0.16.0, `spec.md` (the default look, the click-to-open rule, the toast, the
  clock), `README.md` and `docs/github-release.md` first-open text, `docs/0.15/architecture.md`
  notes on the tap and the toast, `docs/release-notes-v0.16.0.md`, `version.py` 0.16.0.
- Then, on Jonathan's word: push, PR, checks, merge, release.
