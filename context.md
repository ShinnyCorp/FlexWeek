# context.md — FlexWeek

## Current State
- 2026-10-11: v0.19.0 on `release/0.19.0` (worktree `~/.worktrees/flexweek-0190`, `.venv` is
  `venv-0190`): the QA handoff's remaining Fix first items and the Codex audit of 0.18.5. School and
  Setup's activities are a standing week in the store (`standing_blocks`, one row per Setup id and
  the week it stands from; `/api/changes` takes `standing`; restore points and exports carry it);
  unfinished homework from earlier weeks shows in More and after Plan; work due after Sunday gets a
  fair share of this week (`desk/planning.rs` `fair_share`); a time already past is refused (engine
  `past_problem`); the Undo toast stays at least 10 s and pauses under the pointer; Text size is its own
  setting in every look; segmented choices are radio buttons for screen readers; account errors sit
  under their fields; a folded week list for screen readers (Ctrl+Shift+L); 3:1 control edges; the
  focus phase keeps its own work length in the engine (`workMin`). Audit findings 1, 3-11 fixed; 2
  (revision reuse after restore/import) waits for the 1.0 sync store. Built by five lane worktrees
  (Opus, Grok 4.7, GPT-6 Luna, Sonnet, Haiku) and an audit-fix lane, merged and checked by Claude.
- Tests that pick a day of the current week on the real clock can fail on later weekdays since item
  2: hold the clock (`grid_support.hold_clock`, `session.now_ms`).
- 2026-10-10: v0.18.5 on `release/0.18.5` (worktree `~/.worktrees/flexweek-0185`, `.venv` is
  `venv-0185-engine`): roadmap's Consistency and polish. New accounts start on a 12-hour clock
  (`clock_24h`, Rust migration `keep_24_hour_clock` stamps older accounts 24-hour; the desktop
  conftest sets 24-hour per test unless a test chooses); one short and one long date format from
  `engine/engine/src/desk/datetext.rs`; time boxes keep what was typed and show a problem card
  (`fields.ClockField`, `ProblemLine`); buttons re-measure after a look change (`widgets.fit_buttons`);
  a click moves the week's keyboard spot and a closed sheet leaves it on the week (Jonathan,
  2026-10-10, over the QA handoff's "back to the button"). Tests fail on any error inside a Qt slot
  (`no_error_is_lost_inside_a_qt_slot`; pass `QTimer.singleShot(0, receiver, fn)`, never a bare
  bound method); `fwtest gate` checks mutation patterns first. Built by Haiku 5.5 and Sonnet 5.5
  lanes, reviewed by Claude.
- Probing motion: `~/.flexweek-ui-harness/scratch/0.18.4/j14/claude-r3/probe_noprof.py` (copy into
  `desktop/tests/` as `test_zz_*.py`, run through fwtest with `-s`; `PROBE_DRAIN=1` waits for
  Settings' design previews, which otherwise land in the timed window; `PROBE_NOPROF=1` for real
  times). On-screen frames: `scratch/0.18.4/j15/clay_frames.py`.
- Rust (`engine/`, contract `docs/engine/contract.md`, wrappers `docs/engine/adapters.md`): the
  planner and solver, slots, weeks, day, month, explain, restore, recovery codes, the store's SQL
  helpers and database connection, and the desktop's Qt-free logic (`desk`: calendar, custom looks
  with saving, naming and import, files, focus, history, pomodoro, remind, reuse, tokens, update,
  week model). Python calls it through the `flexweek_engine` module; the Python wrappers only
  encode, call and decode.
- Python: the FastAPI routes (about 40 SQL statements remain in the route bodies of `create_app`),
  password hashing's random salt, the clock, the environment and file reads (the engine core is
  pure), the pydantic checks, `backend/models.py`'s Spotify and due-date copies, the `CATEGORIES`
  table in `calendar.py`, `TYPE_PT` in `tokens.py`, `custom_look.readability`, all Qt drawing, and
  `scripts/rig/drive.py`.
- Tests: 396 Rust engine tests (engine, store and bindings; clippy and fmt clean). The Python gate on
  `release/0.18.1`: 2790 passed in 7 min 8 s (`fwtest gate --workers 4`). The differential tests and
  the frozen Python copies are deleted; the Python tests that remain guard Python-only code and the
  interface.
- Speed (`log.tsv`, pr35 review at 2e2f76a): placing the probe week 1.1 ms (0.17.2: 2.9 ms; with a
  busy second thread 1.0 ms against 8.0). Drawing a frame of the hours 10.2 ms median (0.17.2:
  9.1 ms; the limit is 16 ms).
- Known differences from the Python originals: integers past 64 bits and JSON only Python reads
  (NaN, lone surrogates) in stored rows; an assignment estimate past 2^63 raises `OverflowError` in
  the engine where Python returned a number (seen once under hypothesis); `build_month` returns a
  month where Python raised `TypeError` on a finished session with no start.
- 0.18.1 plumbing done on `release/0.18.1`: the Bell teardown, the three adapter tests, the
  `today.json` baseline and the deletion of the differential tests, `desk_ref/` and
  `backend/tests/engine_ref/`. About 100 cases those tests pinned have no Rust test of the same case
  (list in the scratch report); `hypothesis` is now used by no test and awaits Jonathan's word to go.
- spec.md drift: its CI desk step says "the desk parity files and the wrapper modules' tests"; it now
  runs the parity files plus `test_tokens.py` and `test_update.py`.

## Repo Landmarks
```
engine/engine/          pure Rust core: plan, solve, day, month, restore, desk modules; tests/ are the Rust twins
engine/store/           Rust SQL helpers per table (assignments, ledger, prefs, routines, weeks, rules)
engine/py/              PyO3 binding built as `flexweek_engine` (`pip install ./engine/py`)
engine/clippy.toml      forbids key-reordering removes; `Cargo.toml` builds the engine at opt-level 2 in debug
docs/engine/            contract.md, adapters.md (every wrapper's class), interface-logic.md
tools/fwtest/           Rust test runner: gate, mutate, rig, run, clean; builds with cargo
scripts/mutations/      mutation specs (JSON); engine cases point at `cargo:` tests
scripts/rig/            Python rig driver for the hidden desktop (fwtest starts and stops the session)
backend/app.py          FastAPI routes: account, session, ownership; serves no pages
backend/storage.py      Python adapter over the engine's connection; scrypt and sessions
backend/{slots,weeks,limits,...}.py  wrappers that re-export or call the engine
desktop/main.py         launcher: starts the backend in-process, then the native window
desktop/server.py       bundled uvicorn on a loopback port, no Qt imports
desktop/native/window.py     chrome, pages, dialogs, autosave, updater wiring
desktop/native/controller.py session: saves, solve, focus, alarms, reminders
desktop/native/widgets.py    week grid, day agenda, month, editors, Add menu
desktop/native/layouts/      the eight designs; registry.py builds the dialog
desktop/native/look.py       packs, presets, palettes, the one stylesheet
desktop/native/version.py    VERSION, kept equal to the newest CHANGELOG heading
desktop/native/*.py          the Qt-free modules are thin wrappers over engine::desk
desktop/{build_*,package_*}  Linux and Windows builds; packaging/ holds AppImage, Inno, WiX
desktop/tests/          widget tests, engine desk parity tests, `--smoke-test`
.github/workflows/      verify, codeql, release packages
```

## Domain Model
SQLite: users → sessions, many dated weeks keyed (user_id, week_start), one preference row. Default
desktop mode uses a local per-user database; hosted mode uses the configured deployment. There is no
automatic synchronization between them. Only the engine opens the database; the format is unchanged
from 0.17.2, so earlier passwords, sessions and recovery codes still work.
Assignments are keyed (user_id, id) with a JSON body and revision. A flexible block with
`assignment_id` is a work session of that assignment. Routines are keyed (user_id, id) as named
templates of locked blocks. Restore points snapshot all of an account's weeks and assignments.
Recovery codes are hashed per user and shown only once. A format-3 export can copy weeks,
assignments, preferences and routines onto another account after a preview. Recorded `operation_id`
values make a retried write return the first result.

## Non-Obvious Decisions
- The engine core is pure: Python reads the clock, environment, files and randomness and passes
  them in. JSON text crosses the boundary (a 12-block week costs about 0.02 ms to encode and decode).
- `serde_json` has `preserve_order` on, and `engine/clippy.toml` forbids the removes that reorder
  keys, so stored JSON keeps Python's key order.
- Colour maths calls the C library's `cbrt`, `pow`, `atan2`, `sin` and `cos`, looked up at run time
  (`desk/cmath.rs`: `libm.so.6`, `ucrtbase.dll` on Windows), so results match Python's to the bit.
- Case folding uses a table generated from this interpreter (`engine/tools/generate_casefold.py`),
  not a crate.
- The engine crate builds at opt-level 2 in debug so the solver's 150 ms budget holds under load
  (Jonathan's choice).
- A week's identity is its Monday. Blocks store a day index and derive their date. `weeks` pins the
  ISO shape before parsing, because `date.fromisoformat` also accepts "20260907" and "2026-W37-1".
- GET /api/week 422s a non-Monday rather than snapping it, so client and server cannot disagree about
  which week is open.
- The identical-blocks short-circuit runs before the revision check, as the pre-dated code did.
- The migration is guarded on the weeks table existing and runs in an explicit BEGIN IMMEDIATE.
  Registration seeds no weeks row; a missing row already means an empty week.
- A new flexible task in the week on screen may use today onward, since the solver does not know
  today's date. The dialog offers Fixed or Flexible only for a new item; editing keeps the kind.
- The desktop app bundles the backend and runs it in-process (owner's choice 2026-09-07). The
  loopback port is chosen by binding a socket before `create_app`, because the backend pins its CSRF
  origin check and TrustedHostMiddleware to one origin; uvicorn gets the bound socket and runs with
  `loop="asyncio"`, `http="h11"`.
- An invalid FLEXWEEK_*_ORIGIN is an error, not a fall back to local, so a typo cannot quietly open
  a different, empty database.
- `profile_root()` reads QStandardPaths AppDataLocation, so `main()` sets the application name first.
- Nuitka is called directly, since `pyside6-deploy` rewrites its spec with machine paths.
- `theme` is `system|slate|nocturne` (default `system`, owner decision 2026-09-10).
  `allow_system_theme()` rebuilds an older preferences table once, keeping stored slate/nocturne.
- The accent stays at least CIE76 distance 15 from every category colour; a test in
  `desktop/tests/test_look.py` holds it.
- Windows installers: the Inno `AppId` and the MSI `UpgradeCode` are fixed forever so upgrades find
  the installed copy. The .exe is per account, the .msi per machine. Inno Setup 7.1.0 is downloaded in
  CI with its SHA-256 checked; WiX is pinned to 6.0.2 because v7 blocks on an EULA. Windows ICU is
  required from Windows 10 1809 rather than copied out of System32.
- Linux leads with a tar.gz so the executable bit survives. The AppImage needs FUSE; without it use
  `--appimage-extract` then `squashfs-root/AppRun`, or the tarball.
- The smoke test decides a week was drawn by counting colours in a grab of the window
  (`PAINTED_MIN_COLORS`, 8 px grid): a blank window is one flat colour.
- The release workflow stops a Windows installer or smoke test that hangs after ten minutes.

## Session Handoff
- 2026-10-11, `release/0.19.0`: all five lanes and the audit fixes merged; version, CHANGELOG,
  `docs/release-notes-v0.19.0.md`, roadmap and spec.md (standing week, unfinished from earlier weeks,
  fair share, past times, the toast, Text size, the week list) written under Jonathan's overnight
  grant. Release via PR to main on Jonathan's word, then `gh release create v0.19.0 --latest`.
- Next: 1.0.0 with the Android companion (Rust core via UniFFI, Kotlin and Compose) and iroh device
  sync with background sync on the phone (about Oct 22); plan in
  `~/.flexweek-ui-harness/scratch/PLAN-0185-to-100.md`.
- Open for Jonathan: at Large text Retro's window cannot get below 782 px tall (rig week-small-large
  and day-small-large fail at 1150x768): the hidden sign-in page sets every window's least height,
  and 0.19.0's taller Reset card pushed it past 768. A fix that lets hidden pages stop sizing the
  window is saved in `~/.flexweek-ui-harness/scratch/0.19.0/hidden-pages-dont-size-window.patch`; it
  lets windows shrink to 434-550 px, never laid out before, so it waits for his call.
- Open for Jonathan: "12:00 AM" for the end of the day on the 12-hour clock (or "midnight"); the
  shortened sign-in reset note; a series-wide typed start in the past is still allowed (single days
  are refused); the dated day chips now stack the date under the day.
