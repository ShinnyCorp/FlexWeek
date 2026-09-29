# context.md — FlexWeek

## Current State
- Date: 2026-09-25 (0.15 Lane C), branch `claude/0-15-homework-planning`.
  Five inherited fixes cover the DueField signal, due-today default, homework
  length bounds, full-month date picker and planning after now (`7b9d19b`,
  `225908e`, `8709df9`, `85c5312`, `e123f55`). `1c6d3e6` completes Plan and
  Replan all Undo with a notice only after a successful save, keeps automatic
  planning in Add homework's Undo step, and gives plain homework validation
  messages. Plan waits when an earlier save is pending, and a no-op plan makes
  no misleading Undo step. All 24 focused tests and 1329 full tests passed;
  ruff and backend mypy passed; all 15 planner and due mutations were caught.
  `scripts/verify.py` timed out at its known 300-second pytest budget near 92%,
  so the full suite was run separately.
  Offscreen screenshots at both requested sizes are in the UI harness scratch
  directory. No executable build, merge, push, PR or `spec.md` change. Claude
  reviews this branch before it lands.
- Date: 2026-09-24 (Retro desktop unit 12), branch `chatgpt/0-15-retro` from
  `feat/0.15-tabs` at `8e3634a`. Day uses Schedule.exe for one live hours
  column; Week.exe shows seven live columns with pinned day names. Both use
  the window's Hand and retain separate scroll and zoom. The deadlines.txt
  notepad and the main window have draggable "No time yet" chips; Up next,
  movable windows, the taskbar and the shared Month remain. Day passed all
  14 real-pointer scenarios and Week passed all 17. Held and end screenshots
  for tray placement and cross-day movement were inspected at 1280x820 and
  1150x768 with large text. Full source gate: 1311 tests passed, ruff and
  mypy clean; all 11 target mutations were caught. Cartographer skipped
  because `traceworks` is absent from the project venv. No executable build,
  push, PR, or `spec.md` edit. Next: Claude reviews this branch before
  integration.
- Date: 2026-09-24 (Bento unit 13), branch `chatgpt/0-15-bento` from
  `feat/0.15-tabs` at `8e3634a`. Day is Hero clock and Week is Hero board,
  each with painted full-day tracks, a retained zoomable scroll, and a
  draggable "Not placed yet" tray on the window's Hand. Week's pinned day
  names open Day. The supporting tiles option keeps its purpose: "Hero and
  tray only" hides the optional deadline/tonight rail tile. Month remains the
  shared grid. The 1150x768 large-text rig exposed a nested-scroll clipping
  issue; reducing the hero's minimum height kept the target and tray in view.
  Real-pointer rig: Day 14/14 and Week 17/17, with held/end screenshots read.
  Full source gate: 1296 tests passed, lint and backend types clean; all 11
  target mutations caught. Cartographer skipped because `traceworks` is absent
  from the project venv. No executable build, push, PR, or `spec.md` edit.
  Next: Claude reviews this branch before integration.
- Date: 2026-09-24 (Clay deck unit 11), branch `chatgpt/0-15-clay` from
  `feat/0.15-tabs` at `082e9fa`. Clay Day is one large live hours card with a
  "No time yet" tray; Week is seven live cards fanned from -8 to +8 degrees.
  Both use the window's shared Hand, retain separate scroll and zoom positions,
  and use the shared Month. The flat Week option remains available; the old
  three/five card setting was removed because Week now always shows seven days.
  The angled fan passed its grab check and the real-pointer rig: Day 14/14 and
  Week 17/17. Reviewed held and end screenshots for Day move, Week cross-day
  move, Week quarter-grab, and small/large windows; long Week titles shorten
  in the narrow cards, while grab points remain usable. Full source gate:
  1305 tests passed, ruff and mypy clean; all 11 target mutations were caught.
  Cartographer skipped because `traceworks` is absent from the project venv.
  No executable build, push, PR, or `spec.md` edit. Next: Claude reviews the
  branch before integration.
- Date: 2026-09-23 (rig private D-Bus), branch `chatgpt/0-15-rig-ci`.
  Merged `feat/0.15-tabs` at `048814b` (including the private-bus fix at
  `6525429`) into the checkout-isolated KWin/Xvfb rig. Each hidden session now
  starts its own no-activation D-Bus before the display server; the bus is an
  owned process stopped after the servers, and FlexWeek inherits its address.
  Rig ownership tests 10/10; full source gate 1282 tests, ruff and mypy clean.
  Live Classic Day on KWin passed 14/14; no desktop-bus name was owned by its
  PID and the user journal had zero global-shortcut registration failures
  since launch. Stop removed the private bus socket and owned KWin. A scan of
  readable same-user process environments found no holder of its address;
  some older desktop processes deny environment reads. Local Xvfb could not
  run because the executable is absent; its failed start cleaned up the bus.
  No executable build, push, PR, or `spec.md` edit. Next: Claude reviews this
  branch again.
- Date: 2026-09-23, branch `chatgpt/0-15-rig-ci` from `feat/0.15-tabs`
  at `12456d2`. The pointer rig supports Xvfb with Openbox when KWin is absent;
  a ten-minute CI job runs Classic Day and Week and uploads its artifacts.
  State, logs, KWin socket, and default run output now belong to the checkout
  directory; KWin finds the X display through its own Xwayland child. The old
  main-checkout state file remains separate. Both checkouts passed a concurrent
  real-pointer Day scenario on distinct displays, and two updated launchers
  started simultaneously on distinct KWin displays.
  Before this isolation fix, KWin, local Xvfb, and a clean Python 3.14 container
  each passed Day 14/14 and Week 17/17; the container rig took 176 seconds.
  After the fix, a local Xvfb zoom scenario passed, and the full source gate
  passed 1269 tests, including seven rig ownership tests.
  No scenarios, native app code, executable, or remote changed. `spec.md` still
  describes CI as backend-only; the new job extends that behavior.
- Date: 2026-09-23 (month blocks). Branch `grok/0-15-month-blocks` from
  `feat/0.15-tabs` at `062f292`. Each date in `GET /api/month` now lists its
  timed blocks as chips (`id`, `title`, `start`, `duration_min`, `category`,
  `kind`, `assignment_id`, `repeats`, `pinned`, `completed`). A packed
  September (5 blocks a day, 175 chips) is 37,206 bytes compact JSON; one
  week of the same density is 6,911. Source gate: 1278 passed,
  `scripts/verify.py` green. spec.md was not edited. Nothing pushed.
- Date: 2026-09-23 (move-date follow-up). Branch `grok/0-15-move-date-2` from
  `feat/0.15-tabs` at `062f292`. Undo of a cross-week move sends the revision
  each week last saw; a later save to the other week is a 409 and both weeks
  stay. `date_problem` judges a chip whose week is not open from optional
  `start`, `duration_min`, and `assignment_id`. Source gate: 1274 passed,
  `scripts/verify.py` green. `scripts/mutate.py scripts/mutations/planner.json`
  caught every break. spec.md was not edited. Nothing pushed.
- Date: 2026-09-24 (Mission short-block text), branch `chatgpt/0-15-mission`.
  The initial appears only when the shared painter has no room for words;
  drawing it leaves the painter's font as the shared painter set it. A new
  default-zoom render test failed on the 30-minute overlap before the fix and
  passes with a visible 15-minute initial. An offscreen Week render showed
  shortened Dinner words without the extra initial and Quiz with its initial.
  All 14 Mission tests and the full 1248-test source gate passed; ruff and
  mypy were clean. No rig, executable build, push, PR, or `spec.md` edit.
  Next: Claude reviews the Mission branch again.
- Date: 2026-09-23 (Mission review fix), branch `chatgpt/0-15-mission`.
  Parked Day and Week scrolls stay children of the Mission page after leaving
  the layout, so closing the host destroys them. The new host-deletion test
  failed before the fix and passed afterward; all 13 Mission tests passed.
  Full source gate: 1247 tests passed, ruff and mypy clean. No rig, executable,
  push, PR, or `spec.md` change. Next: Claude reviews this branch again.
- Date: 2026-09-23 (0.15 Mission control). Local branch
  `chatgpt/0-15-mission` from `feat/0.15-tabs` at `ab0ef57`. Day uses Scope
  lane and Week uses Lane ops, both on the window's Hand. Pending homework is
  in a draggable "Not placed yet" tray. Week keeps its radar and load bars.
  The 15-minute horizontal grab check passed at 25%, 50%, and 75% on both
  tabs, so Column watch was not needed. Along-the-lane resize and scroll dwell
  also passed with horizontal real-pointer targets. The stock rig passed 10/14 Day
  and 14/17 Week scenarios. Its remaining failures aim at vertical resize or
  dwell coordinates on horizontal hours, or look for Today's app's fixed day
  name ids. Full source gate: 1,246 tests passed, ruff and mypy clean; all 11
  target mutations were caught. Cartographer skipped (not installed in the
  project venv). Nothing pushed or built; `spec.md` unchanged.
- Date: 2026-09-22 (0.15 reach check). Branch `fix/015-rig-reach` from
  `grok/0-15-audit-01` at `841586f`. A partial hours track no longer reports
  00:00 or 24:00 as visible by substituting its own edge. Full source gate:
  1181 tests passed; Classic Week reach pointer rig: 1/1. No build or push.
  `spec.md` is unchanged.
- Date: 2026-09-21 (UI and setup). Branch `feat/ui-setup` off `main` at the
  0.14.2 release. The nine-PR plan in
  `~/.claude/orchestrate/flexweek-ui-setup/docs/plan.md`, built here as one
  commit per unit plus a motion pass: themed controls, motion, pinned
  sessions, the three new preferences, subject study windows, the drag
  outline and cross-day moves, drag-to-place and Choose a time, one alarm
  sound, the planning style, and first-run setup (`desktop/native/setup.py`,
  pictures from `desktop/native/previews.py`), which replaces the first-week
  card. Setup writes each page as it is left; `_flush_setup` in the window
  sends one request at a time because a second request replaces the first on
  the session. Tests that create an account call `past_setup` from
  `desktop/tests/logic_support.py`. Plan corrections: `prepare_solve` copies
  the course, the plan-review drag was not built, and due dates show the year.
  Gate: 1098 Python tests, `scripts/verify.py` VERIFIED (pytest 225 s of its
  300 s budget, after `_apply_appearance` stopped restyling an unchanged
  look on every week change). Nothing pushed, no PR, no executable. VERSION stays
  0.14.2. spec.md not edited; proposed lines are in the session report.
- Date: 2026-09-21 (0.14.1 trust). Branch `fix/0-14-1-trust` off `origin/main`
  at the 0.14.1 merge. The 0.14.1 AppImage audit and Claude's review of that
  run: leftover homework is one WeekModel rule on every layout and both day
  screens; Running late undoes in one step; a covering commitment takes only
  the blocked homework and offers Find a new time; Plan my homework keeps
  working times; Month hides the whole week surface; username, estimate error,
  More details, Today, and Start/End are in. Dialog height from the audit
  (~150 px) was not reproduced, so it is not claimed as fixed. Gate: 977
  Python tests, `scripts/verify.py` VERIFIED. Development window driven
  offscreen at 1024×768 and 1280×800. Packaged AppImage not rebuilt. Nothing
  pushed. VERSION stays 0.14.1. spec.md was not edited. Drift to flag: Month's
  decision 7 still says the solver's choice is never stored, and Running late
  still says it re-solves after the locked block is saved. The native app now
  stores placements and applies the Running late preview in the same save.
  spec.md does not still describe a web app or a WebEngine shell (PR #22).
  Second review round (Claude): a missed day no longer stops the week saving
  (apply_plan writes only unfinished homework), the week title fits beside
  its arrows with a short form, fixed activities are Start and End only, views
  say what they are for, notices speak once and name every lost session, and
  a failed replan keeps the newest reason. Gate after that: 987 Python tests,
  `scripts/verify.py` exit 0.
  Third round (Claude, same day): the audit's ~150 px dialogs are explained
  and fixed. 154 px was the 0.14.1 minimum height of Settings and the homework
  editor; the audit's desktop gave them that minimum. Reproduced on the real
  KDE desktop with the shipped AppImage, and the fixed source holds 480 px
  there. The dialog test now squeezes each dialog and fails on 0.14.1. Also:
  Day counts only work with a time as planned (stage 2 contract line updated),
  solver reasons and deadline tags reworded with Jev, Running late moves no
  longer say a day was missed, School hours under More > Adding, Settings
  hides Look/Accent/Surface/Corners/Blocks where they change nothing, and
  Bento's empty Up next says its title once. Close-out (Jonathan: "finish up
  the work"): Month pins open work only where its plan put it (decision 7
  updated), spec.md now describes stored plans, Plan vs Replan all, Running
  late's single save, Day/Month counting and School hours under More. The
  older GLM findings on overdue homework, "only" mode and finished sessions do
  not hold against the current code. A Jev copy sweep of the branch's 55 new
  strings found nothing to change. Keep me signed in on this computer is on
  the sign-in card (on by default): the session token is kept per database in
  `<data>/signed-in/<instance>.json` (0600), resumed through /api/auth/me at
  launch, and forgotten on Log out, account deletion or a 401. Checked on the
  real KDE desktop through `desktop.main`. Check for updates hung on the
  installed 0.14.0 AppImage because GitHub's API answered 403 (rate limit for a
  shared carrier address) and the updater stopped silently; it now falls back
  to the releases/latest redirect, times out, and reports failure when asked.
  The packaged app is not rebuilt. Next: owner review, then a 0.14.2 bump and package when asked.
- Date: 2026-09-21 (IA harden). 0.14.1 shipped: Plan my homework and More stay
  in every design; Settings is a gear; Appearance & layout is one Settings
  section; summaries speak minutes; Running late toasts the reason or the
  locked start; first-week sport name is a placeholder; Settings saves as you
  go. PRs #23 and #24.
- Date: 2026-09-20 (layout surfaces). Branch `feat/layout-surfaces` off
  `origin/main` at 993c003, local only in `~/.worktrees/flexweek-layout-surfaces`.
  Day and Month rebuild for the chosen week layout (classic stays the clock
  Day and chip Month). Settings is a four-pane rail with Fine-tune. First-week
  setup is a card over an empty week after recovery codes. My day was not
  changed. Gate: 835 Python tests, ruff, mypy 48 files. Cartographer skipped
  (project venv cannot import traceworks). spec.md still describes a web app
  and WebEngine shell; first-week setup now exists on the native app, which
  closes part of that drift without editing spec.md. Next: owner review, then
  push/PR if asked.
- Date: 2026-09-19 (native UI screenshot audit). Branch `grok/ui-fixes` off
  `origin/main` at 4ad2855, local only in `~/.worktrees/flexweek-ui-grok`. Four
  native fixes: the week grid opens on now, Retro Week.exe stays on the desk
  with a scrollable weekend, Mission bars get an initial or a tooltip and the
  radar elides, and `contrast_failures` now fails a `card_*` that matches `bg`.
  Fill contrast is held at 1.01 so a vanished bar is caught without asking
  4.5:1 of a tint (muted-on-card 4.5 and fill-on-bg 3 cannot both hold for
  every look). Claude still owns bento/clay/timeline/dial/one_thing/base/
  settings. spec.md still describes a WebEngine desktop shell; that drift is
  unchanged and was not edited. Next: Claude reviews the native layout work.
- Date: 2026-09-19 (retire Chromium shell). Branch `feat/retire-webengine` off
  `main` at the 0.12.0 merge. `desktop/webengine.py`, `desktop/sandbox.py`, and
  the leftover probe tests are deleted. Native `--smoke-test` stays in
  `desktop/tests/test_smoke.py`. Packaging still refuses Chromium in the
  bundle. Local gate: 291 frontend and 686 Python tests. spec.md still
  describes a WebEngine desktop shell; that drift is unchanged and was not
  edited. Next: merge this cleanup, then delete merged leftover remote
  branches.
- Date: 2026-09-19 (0.12.0). Branch `feat/0-12-release` off `main` after PR #15.
  Packaging compiles the native window and refuses Chromium in the bundle.
  CHANGELOG closed as 0.12.0. Local gate: 291 frontend and 712 Python tests.
  spec.md still describes a WebEngine desktop shell; that drift is unchanged
  and was not edited. Next: tag `v0.12.0` and publish the GitHub release so CI
  attaches Windows and Linux downloads.
- Date: 2026-09-18 (PR #15). Branch `feat/native-python`, GitHub PR
  https://github.com/j0nsh1n/FlexWeek/pull/15 onto `main`. Claude's native
  layouts and Paper/Pastel are on the branch. Reviewer fixes: T from the week
  grid, day list and month grid opens My day (the same event filter as W/D/M);
  Tools keeps Copy, Paste and Duplicate when a layout owns the window. Local
  gate: 291 frontend and 709 Python tests, `scripts/verify.py` VERIFIED. CI
  Verify web is green; desktop is local only. Open for the
  owner: merge, Amendment A `look_*` fields, Amendment C `layout_*` fields.
  spec.md drift: native launcher, six presets, proposed look/layout account
  fields. Packaging still launches WebEngine.
- Date: 2026-09-18 (native layouts built). Branch `feat/native-python`, local only.
  The native client now has layouts as well as looks: six main views to plan in
  (Today's app, Timeline, Mission control, Bento, Retro desktop, Clay deck) and
  two day screens to watch once the plan is made (One thing, Day dial), each with
  its own colourways, Match my look, and fine-tune options. **Layout** in the top
  bar picks them, **My day** or T opens the day screen, and a design of its own
  gets the window while the planning controls move into **Tools**. It all lives
  in `desktop/native/layouts/` on top of `desktop/native/weekmodel.py`, one
  reading of the week every layout shares. Device-only; Amendment C of
  `docs/stage8-appearance-contract.md` proposes the account fields. The web
  client has no layouts. The design reference is `docs/mockups/look-concepts/`.
- Earlier on 2026-09-18 (looks complete), same branch.
  Paper and Pastel are built in both clients, which finishes the six presets of
  Amendment A: Terminal, Poster, Ink, High contrast, Paper, Pastel. They are
  the two soft looks (rounded, with depth) where the other four are flat and
  sharp, and both are light over any pack. Each is a full token map in
  `frontend/styles.css`, a row in `desktop/native/look.py`, and an entry in the
  one Look menu; the native rows are held equal to the web tokens by
  `test_native_colours_are_the_audited_web_tokens`. The native contrast audit
  now covers 700 look combinations. Still device-only: the account `look_*`
  fields and joining presets to `theme_pack` wait on the owner's approval of
  Amendment A, and spec.md is untouched. GLM through OpenCode answered nothing,
  not even a one-line prompt, on 2026-09-18, so no part of this was drafted by it.
- Date: 2026-09-18 (native). Branch `feat/native-python`, local only. Owner
  answers for look and navigation are in: Preset is folded into Look; a look
  keeps knobs set by hand; High contrast is menu-only; Paper and Pastel stay
  for Claude; large text enlarges More; native weeks park unsaved drafts and
  keep the weekday; today's reminders fire on any page. Full source gate: 290
  frontend and 545 Python tests. Look still never enters `/api/preferences`. spec.md drift: native launcher, four presets,
  proposed `look_*` fields. Nothing pushed.
- Date: 2026-09-17 (native). Branch `feat/native-python` off look-knobs at
  a92feef, local only. All six units of `docs/native-python-migration.md` are
  in. `python -m desktop.main` (and `python -m desktop.native`) starts Qt
  widgets against the existing Python API with browser files disabled. Focus
  timers, packs, device-only look knobs, tray hide, forgotten-password recovery,
  restore points, week/day files and account transfer are on that window.
  `--smoke-test` no longer loads Chromium. The old WebEngine shell remains in
  `desktop/webengine.py` for leftover probe tests. Packaging and installers are
  untouched. Native widget tests plus focus/look/remind/files helpers. GLM
  5.3 Flash audited units 4–6; native now matches the web client on lead-0
  reminders, queued alarms, this-week-only reminder sources, week-file replace
  confirm, restore/undo/focus cleanup, and account-import preview timing.
- Date: 2026-09-17 (native, earlier). Units 1–3 of the native overhaul: register,
  dated week, Week/Day/Month, drag, series refuse, homework notes, undo, copy,
  paste, routines, unfinished, missed, running late, spread and availability.
- Date: 2026-09-17 (after 0.11.0). Branch `feat/look-knobs` off `main` at
  30e0724, local only. The owner asked for more control over the UI and for
  presets that look drastically different, and chose architecture first with
  one preset to judge by. Built: seven look knobs (surface, corners, depth,
  font, blocks, density, text) as `data-*` attributes on `<html>` set by the
  head script `frontend/look.js`, stored device-only under `flexweek-look`,
  never sent to `/api/preferences`; a Terminal preset with its own full token
  map, audited by the same tests as a pack; blocks now carry category colour as
  `--block-color`. Gate: 287 frontend and 372 Python tests, including the real
  WebEngine stage5 probe proving the preset changes computed font and hour
  height. `docs/stage8-appearance-contract.md` Amendment A proposes the seven
  `look_*` fields and Terminal as a pack; spec.md is untouched until the owner
  approves it.
- Date: 2026-09-17 (release). v0.11.0 is prepared on `feat/0-11-seamless`: packs,
  Customize, account motion, wait-states and the 0.10.1 hotfix. P2 account copy,
  a reduced-motion WebEngine pass and a Windows flicker hand-check remain after
  the tag. Next work is those leftovers, not a new stage.
- Date: 2026-09-17. Appearance contract approved. `docs/stage8-appearance-contract.md`
  records the owner's answers: Light frost and Dark frost are new token sets,
  pack sits beside `theme` with an axis pairing, motion uses `None` for never-set
  so an explicit Normal stays on the wire, accents are `default`/`sky`/`gold`/
  `sea`/`sand`. `GET`/`PUT /api/preferences` stores the four fields in
  `comfort_json`. Pack UI, Customize, and wiring motion onto the account are
  still Claude's. Branch `feat/0-11-seamless`, local only.
- Date: 2026-09-16 (later). v0.10.0 is published as the Latest release, not a
  draft and not a prerelease, from `main` at d17647a. All eight assets are
  attached: `FlexWeek-Linux-x86_64.tar.gz`, `FlexWeek-x86_64.AppImage`,
  `FlexWeek-Windows-x64-Setup.exe`, `FlexWeek-Windows-x64.msi`, and a `.sha256`
  for each. Packaging run 35055532872 finished green on both jobs (linux 6m50s,
  windows 13m14s). Windows is the slower job by design: its Nuitka compile took
  750s against Linux's 495s in the comparable run, then it spends about 152s
  building the Inno Setup and WiX installers and 38s installing, opening and
  uninstalling each one, where Linux only builds a 24s AppImage and has no
  install step. Nothing has been run on a real Windows PC yet. The next work is
  the 0.10.1 hotfix in roadmap.md, not a new stage.
- Date: 2026-09-16. Stages 1-7 are merged to `main` in PR #12 (merge commit
  aca3068), together with the roadmap PR #11 at a7936b2. PR checks were green:
  CodeQL, `analyze` and both `web` verify jobs, matching the local gate of 243
  frontend and 365 Python tests. Local `main` was stale at 3f19d33 and is
  fast-forwarded to aca3068. Packaging run 35053629863 (`workflow_dispatch`, no
  tag, so nothing uploads to a release) built the Linux bundle on the runner in
  9m43s; the Windows installers build in the same run and stay as run artifacts.
  `desktop/build_linux.sh` does NOT complete on this machine: Nuitka compiles,
  but `desktop/check_bundle.py` enforces `MAX_GLIBC` 2.38 while this host runs
  glibc 2.43, so `libpython3.14.so.1.0` and `libuuid.so.1` fail on
  `GLIBC_ABI_GNU2_TLS`, and PySide6 6.11.2's `libpyside6.abi3.so.6.11` and
  `libshiboken6.abi3.so.6.11` are not vendored into the bundle. No release tag
  exists, and Windows execution on a real PC is still unverified.
- Date: 2026-09-15. `feat/stage7-month-frontend` now holds the integrated Stage
  7 branch: Grok's Stage 6/7 audit backend fixes merged with this branch's Month
  UI and accessibility fixes. `GET /api/day` no longer counts a completed
  session on every candidate day, matching `occurrenceDays` and the month grid.
  Month shows planned as well as completed work: a session pins to a date only
  when that date is certain, each day carries `focus_min`, and open work with
  several candidate days is reported in a new `unscheduled` total rather than
  painted across the week. The owner approved the Stage 4, 5 and 7 contracts on
  2026-09-15, so spec.md now lists `GET /api/month`, the spread route, the three
  comfort routes, `running_late` on solve, availability windows, assignment
  notes/links/checklist and the comfort fields. Full source gate: 242 frontend
  and 364 Python tests, mypy over 47 files, whitespace clean. The Stage 2
  contract was already approved and its status line was wrong; it is corrected
  and spec.md now carries Day view and `GET /api/day`, which closes the last
  documented drift. Year view, student trials, measured comparisons and PR
  review remain. Nothing pushed.
- Date: 2026-09-15. Three accessibility defects from Grok's Stage 6 audit are
  fixed on `feat/stage7-month-frontend` (3bdcfc3). The account sharing note and
  recovery-code status sit in polite live regions; the transfer preview is a
  named group that takes focus when it appears; sign-out moves focus to the auth
  screen only when someone was signed in, so first load keeps browser focus.
  Full source gate: 238 frontend and 353 Python tests. Grok's backend fixes from
  the same audit (password checked inside the write transaction, completed
  sessions pinned to `completed_day` in month, ASCII-only month parsing) are on
  `grok/stage7-month-backend` at c61fab6 and are not merged here. Two product
  questions are open for the owner: stored open sessions carry no `start`, so
  month counts reflect completed work and pomodoro chunks only; and
  `GET /api/day` over-counts a completed multi-candidate session the way month
  did before its fix, disagreeing with `occurrenceDays` in the frontend.
  Nothing pushed.
- Date: 2026-09-15. Stage 7 Month is complete locally on
  `feat/stage7-month-frontend`, based on Grok's backend at 6ab42d6. The shared
  frontend shows due work, completed deadlines, scheduled time, projects and
  overdue homework at desktop and phone widths. A date opens Day only after its
  editable week loads. Month state stays separate from editable weeks and
  assignments, and stale month or account replies cannot redraw it. The single
  lower-edge week start `1999-12-27` lets January 1 and 2, 2000 open without
  accepting any other 1999 date. The full source gate passes 235 frontend and
  353 Python tests. The real `stage7_month` WebEngine case also passes at
  1280px and 390px. Year view, student trials, measured comparisons and PR review remain.
  spec.md drift: the proposed Month route and grid rules are not in the public
  API table. No executable was built and nothing was pushed.
- Date: 2026-09-15. Audit of the Stage 6 backend, Stage 6 frontend and Stage 7
  month API on `grok/stage7-month-backend`: one own review plus three
  read-only GLM 5.3 Flash passes through `opencode` (security, month
  correctness, frontend security/accessibility). Fixed: password check moved
  inside the write transaction for recovery-codes, delete and export; month
  label rejects Unicode digits; completed sessions pin `completed_day` only.
  Tests added for wrong-password 401s, CSRF on every Stage 6 write, recover
  dropping other sessions, pomodoro chunks, completed-overdue and Unicode
  labels. Open for Claude: `aria-live` on `#recovery-status` and
  `#account-sync-note`, announcing or focusing the transfer preview, focusing
  the auth screen after account deletion. Open for the owner: stored open
  sessions never carry `start` (placements live only in the page), so month
  `session_count` and project `session_dates` reflect completed sessions and
  pomodoro chunks; `GET /api/day` counts a completed multi-candidate session
  on every candidate day (Stage 2 shape, unchanged). Nothing pushed.
- Date: 2026-09-15. Stage 7 month API is on `grok/stage7-month-backend` (worktree
  `~/.worktrees/flexweek-stage7-backend`), based on `grok/stage6-transfer-limit`
  at f268b7e. `GET /api/month` returns a clipped complete-week grid, deadlines,
  placed-session counts, projects and overdue homework against the proposed
  contract in `docs/stage7-contract.md`. Claude still owns Month view and
  date-to-Day navigation. Year view is out of this slice. spec.md drift:
  `GET /api/month` and the month grid rules are not in the public API table
  until the owner approves the contract. Full source gate
  (`scripts/verify.py`, desktop included): 221 frontend tests, 351 Python
  tests; a live uvicorn probe of the month route matched the contract. No
  executable was built. Nothing pushed.
- Date: 2026-09-15. Stage 6 contract approved and recorded in `spec.md` on
  `grok/stage6-transfer-limit`. Recovery, deletion, storage identity, previewed
  format-3 transfer and the 256 KiB import-apply envelope are product contract.
  Hosted Render deployment, installers and Safari/iPhone checks are skipped by
  the owner. Remaining Stage 6 work is the security/accessibility review.
  Stages 4 and 5 stay proposed and off the public API table. Web-only gate
  unchanged: 221 frontend tests, 263 Python tests. Nothing pushed.
- Date: 2026-09-15. Transfer size limits are reconciled on
  `grok/stage6-transfer-limit`, based on `feat/stage6-access-frontend` at
  bdfbb61. Export 413s when the import apply envelope would exceed 256 KiB.
  More than 400 small weeks can export when they still fit.
  `storage-info.transfer_limit_bytes` is 262144. Hosted deployment,
  security/accessibility review, installers and physical platform checks remain.
  spec.md drift: Stage 6 routes, storage-info fields including
  `transfer_limit_bytes`, and the transfer envelope rule await approval of
  `docs/stage6-contract.md`. Web-only gate: 221 frontend tests, 263 Python
  tests. Nothing pushed.
- Date: 2026-09-15. Stage 6 backend and shared frontend are complete locally on
  `feat/stage6-access-frontend`, based on Grok's backend at 6a5e3aa. Registration
  shows recovery codes once before setup; Forgot password, code replacement,
  password change and typed-username account deletion are wired. Settings name
  the username, local/hosted storage mode, origin and sync limit. Account
  transfer separates format-3 files from week files, names removals and requires
  review before replacement. The final source gate passes 218 frontend and 331
  Python tests, including real WebEngine and packaged-app smoke paths. A
  read-only Cartographer scan found 42 modules, 37 production routes and no
  parse errors, circular imports or scanner warnings. Hosted deployment, full
  security/accessibility review, installers and physical Safari/iPhone checks
  remain. The backend still needs one transfer-limit follow-up: a valid export
  can grow past the import request cap, and accounts above the 400-week export
  validation cap can fail to export. spec.md drift: the Stage 6 routes and
  storage fields await approval of `docs/stage6-contract.md`. No executable was
  built and nothing was pushed.
- Date: 2026-09-14. The Stage 5 shared frontend is complete locally on
  `feat/stage5-comfort-frontend`, based on Grok's backend at 10c9334. Settings
  now use Appearance, Focus, Notifications and Account sections; presets and
  split preview explain 15-minute rounding; local alert previews honor volume
  and never spend reminder keys; and the preferred view plus sidebar state
  survive reload. Live browser verification caught and fixed null sidebar width
  saves and collapsed-sidebar phone overflow. A Stage 5 WebEngine walkthrough
  covers the same path. The Qt shell still needs to apply start-at-login and a
  tray Test action. spec.md drift remains pending contract approval. No packaged
  executable was built and nothing was pushed.
- Date: 2026-09-14. Student-experience Stage 5 backend is on
  `grok/stage5-comfort-backend` (worktree
  `~/.worktrees/flexweek-stage5-backend`), based on `feat/stage4-adaptive-plans`
  at 6ae893c. Comfort preference fields, timer-split preview, timer presets and
  reminder-limit copy live behind the proposed contract in
  `docs/stage5-contract.md`. Claude still owns the Settings grouping, Test
  reminder, volume slider and remembered-layout UI. Desktop start-at-login and
  tray Test are stored as prefs, not applied by the Qt shell yet. spec.md
  drift: those fields and routes are not in the public API table until the
  owner approves the contract. Web-only gate: 195 frontend tests, 243 Python
  tests. Nothing pushed.
- Date: 2026-09-14. Student-experience Stage 4 is complete locally on
  `feat/stage4-adaptive-plans` (worktree
  `~/.worktrees/flexweek-stage4-adaptive-plans`). Running late previews 15/30/60
  minute delays and stores one locked interval on accept. Spread, assignment
  notes/links/checklist, protected time, preferred study hours and cutoff are
  in. Priority and energy labels changed; stored values did not. Cluster advice
  stays visible. spec.md drift: `running_late`, spread, assignment project
  fields, availability prefs and the stored late block are not in the public
  API table until the owner approves `docs/stage4-contract.md`. Full source gate
  green: 195 frontend tests and 303 Python tests, including the Stage 4
  WebEngine walkthrough. Packaged binaries were not run. Nothing pushed.
- Date: 2026-09-14. Student-experience Stage 4 backend is on
  `grok/stage4-adapt-backend` (worktree
  `~/.worktrees/flexweek-stage4-backend`), based on `claude/stage3-frontend` at
  9759a23. Running-late solve preview, project-spread preview, assignment
  notes/links/checklist, preference occupancy (protected windows, study hours,
  day cutoff) and a deadline-cluster explanation live behind the proposed
  contract in `docs/stage4-contract.md`. Claude still owns the shared frontend.
  Nothing pushed. Web-only gate on this tree: 163 frontend tests, 229 Python
  tests (`ruff check .`, `mypy backend`, `pytest` on `backend/tests`). Desktop
  and packaged binaries were not run.
- Date: 2026-09-14. Student-experience Stage 3 is complete locally on
  `claude/stage3-frontend`: Codex's frontend (copy, paste, duplicate and copy
  day with conflict previews, fixed-only routines, unfinished-homework review,
  restore points and the Settings storage label) on Grok's backend (routines,
  restore points, storage-info, operation ids and snapshot labels on
  `/api/changes`, cherry-picked unchanged as a6b484f). Claude finished the
  WebEngine step and reviewed the code with two GLM adversarial passes, fixing
  seven defects. GLM findings that did not hold up against the source are
  listed as rejected in the commit messages. Jonathan confirmed the contract
  on 2026-09-14, and spec.md lists the Stage 3 routes.
- Full source gate green on the final tree: 163 frontend tests and 278 Python
  tests, including the real Qt WebEngine `stage3` case (copy, routine apply,
  restore, a retried operation, reload, a second account) and `stage3_mobile`
  (390px dark theme, unfinished homework carried once). The T3 preview browser
  could not load a local server, so no separate live browser pass ran. No
  package or executable build ran. Nothing pushed.
- Date: 2026-09-14. Student-experience Stage 2 is complete locally on
  `feat/stage2-student-experience` (the same commits as
  `claude/stage2-frontend`): Grok's `GET /api/day` plus the Day agenda, Day
  first at 800px and narrower, quick Add homework, Plan my homework / Update my
  plan wording, collapsed results with slack in days, Export and Import in
  Settings, and Edit / Finished / Start focus in agenda rows. It follows the six
  owner decisions in `docs/stage2-contract.md`, which is approved; spec.md lists
  Day view and `/api/day` from 2026-09-15. Full source gate green: 145 frontend tests
  and 250 Python tests, including the stage2 WebEngine probe at 390px and
  1280px. No remote branch changed.
- Date: 2026-09-13. Student-experience Stage 1 is complete locally on
  `feat/stage1-student-experience`. The branch combines the seven-stage roadmap,
  approved contract, reviewed backend and finished frontend: exact assignment
  deadlines and cross-week sessions, Continuing and Plan the rest here, focus
  outcomes and reload-safe timers, Undo/Redo, safer deletes, and version 2
  export/import. No remote branch changed.
- Full source verification after integration is green: 139 frontend tests and
  241 Python tests, including the Stage 1 Qt WebEngine walkthrough. A live
  browser check also covered assignment entry, next-week Continuing, Solve,
  and the Finished / Need more time / Take a break prompt. A read-only
  Cartographer scan found 28 Python files, 16 routes, no parse errors, no
  circular imports and no scanner warnings.
- Date: 2026-09-11. v0.9.2 is released (PR #9, tag at a20831f).
  `feat/frost-reference-look` (5ca38b7, restyle after the owner's reference
  dashboards) is parked and in neither release.
- v0.9.1 shipped: a page renderer that stops reopens solved and solid instead of
  a blank window; `--smoke-test` walks setup to its Solve with a pixel check;
  the AppImage `.sha256` names only the file; AppImage FUSE doc tip.
- v0.9.2 replaced the Windows zip with per-account Setup.exe and per-machine
  MSI installers, built and exercised on the GitHub Windows runner.
- The owner sees flicker in the setup dialog on Windows and is investigating
  that directly. On the owner's Linux PC (KDE Wayland, RX 9070, Mesa 26.2.2) blur on,
  blur off and GPU off all looked the same, with no flicker.
- Hybrid frost visual system is in: one token map per theme in
  `frontend/styles.css` (`:root` = nocturne/dark, `[data-theme="slate"]` =
  light), frosted chrome with a solid fallback, near-opaque week grid, soft blue
  accent, Figtree font and a duotone SVG icon sprite in `index.html`.
- Gates green 2026-09-10 via `scripts/verify.py`: ruff, mypy over 22 files,
  184 Python tests (real WebEngine probes, now checking the Figtree face loads
  and signed-out pages start light) and 95 frontend tests.
- Windows execution on a real PC, Safari/iPhone, physical touch and OS
  notification delivery remain unverified. Hosted web URL is not online.
- Default desktop mode uses a local database. Hosted mode uses the configured
  server; there is no automatic synchronization between them.

## Repo Landmarks
The web client was deleted on 2026-09-19; there is no `frontend/`. FlexWeek is the
Qt widgets app below, over the FastAPI backend it starts in-process.
```
docs/cac-build-plan.md   original Sep 6 contest brief (working title Reslot)
.github/workflows/       verify.yml (mypy), codeql.yml (Python), release packages
DESKTOP.md               packaging now at the top; WebEngine-era sections marked
desktop/main.py          launcher: starts the backend, then the native window
desktop/server.py        bundled uvicorn on a loopback port, no Qt imports
desktop/origin.py        origin resolution, no Qt imports (unit-tested)
desktop/native/window.py     chrome, pages, dialogs, autosave, updater wiring
desktop/native/controller.py session: saves, solve, focus, alarms, reminders
desktop/native/widgets.py    week grid, day agenda, month, editors, Add menu
desktop/native/layouts/      the eight designs; registry.py builds the dialog
desktop/native/look.py       packs, presets, palettes, the one stylesheet
desktop/native/weekmodel.py  one shared reading of the week for every design
desktop/native/pomodoro.py   focus-session splitting around a solve, no Qt
desktop/native/tones.py      alarm tones as PCM, no Qt; sound.py plays them
desktop/native/update.py     update decisions, no Qt; updater.py fetches/swaps
desktop/native/version.py    VERSION, kept equal to the newest CHANGELOG heading
desktop/native/autostart.py  start-at-login entry (XDG file / Windows Run key)
desktop/assets/          logo.png and favicon.png for the window and installers
desktop/build_linux.sh   staged Linux build, previous artifacts preserved
desktop/package_linux.sh release tar.gz with README, icon and .desktop
desktop/check_bundle.py  glibc and missing-library check, no Qt imports
desktop/build_windows.ps1 Windows standalone build
packaging/               AppImage script, Inno Setup and WiX installers
desktop/tests/           native helpers, widget tests, `--smoke-test`
backend/app.py           account/session/ownership APIs; serves no pages
backend/storage.py       SQLite, scrypt, hashed sessions
backend/weeks.py         week-date helpers, no framework import
backend/recovery.py      one-time recovery codes, no HTTP
backend/limits.py        256 KiB write-body cap
backend/transfer.py      import apply envelope size, no HTTP
backend/restore.py       restore-point snapshot diff and token, no HTTP
```

## Domain Model
SQLite: users → sessions, many dated weeks keyed (user_id, week_start), one
preference row. Default desktop
mode uses a local per-user database; hosted mode uses the configured deployment.
There is no automatic synchronization between those databases.
Assignments are keyed (user_id, id) with a JSON body and revision. A
flexible block with `assignment_id` is a work session of that assignment.
Routines are keyed (user_id, id) as named templates of locked blocks.
Restore points snapshot all of an account's weeks and assignments.
Recovery codes are hashed per user and shown only once at register or regenerate.
A format-3 export can copy weeks, assignments, preferences and routines onto
another account after a preview. There is no automatic local/hosted sync.
Recorded `operation_id` values make a retried write return the first result.

## Non-Obvious Decisions
- A week's identity is its Monday. Blocks store a day index and derive their
  date, which is why the day-index solver needed no adapter at all.
- `weeks.py` pins the ISO shape with a regex before parsing, because
  `date.fromisoformat` also accepts "20260907" and "2026-W37-1".
- The migration is guarded on the weeks table existing, since PRAGMA
  table_info returns nothing for a missing table and ALTER TABLE would raise on
  a fresh database. It runs in an explicit BEGIN IMMEDIATE, not in
  executescript, which issues an implicit COMMIT.
- Registration no longer seeds a weeks row; the NOT NULL key would reject it,
  and a missing row already means an empty week.
- GET /api/week 422s a non-Monday rather than snapping it, so a client and
  server cannot disagree about which week is open while both think they won.
- The identical-blocks short-circuit deliberately runs before the revision
  check, preserving what the pre-dated code and tests already did.
- The desktop app bundles the backend and runs it in-process (owner asked for
  this 2026-09-07). It supersedes DESKTOP.md section 1, which said not to; that
  section's reasoning was about a *second process*, which this is not.
- The loopback port is chosen by binding a socket before create_app is called,
  because the backend pins its CSRF origin check and TrustedHostMiddleware to
  one exact origin. uvicorn is handed the already-bound socket.
- uvicorn runs with loop="asyncio" and http="h11" so the build does not depend
  on uvloop/httptools surviving being frozen.
- An invalid FLEXWEEK_*_ORIGIN is an error, not a silent fall back to local:
  a typo must not quietly open a different, empty database.
- `profile_root()` reads QStandardPaths AppDataLocation, which derives from the
  application name, so main() sets the name before reading the data folder.
- Nuitka is called directly instead of via pyside6-deploy, which rewrites its own
  spec with absolute machine paths on every run.
- PySide6 6.10+ documents Python 3.14.
- License file is GPL-3.0. Qt for Python is LGPLv3/GPLv2/commercial.
- The tray icon path is anchored on the `backend` package, because Nuitka puts
  `desktop/main.py` at the bundle root as `__main__`.
- A new flexible task in the week on screen may use today onward. The solver
  does not know today's date, so without this it placed new homework on days
  already over.
- The dialog offers Fixed or Flexible only for a new item; editing keeps the
  existing kind, because converting needs completed_day and start cleanup that
  no flow asks for yet.
- Windows installers: the Inno `AppId` and the MSI `UpgradeCode` are fixed
  forever, since upgrades find the installed copy by them. The .exe is per
  account (`PrivilegesRequired=lowest`) for students; the .msi is per machine
  for school IT. Inno Setup is not on windows-latest, so CI downloads 7.1.0 and
  checks its SHA-256. WiX is pinned to 6.0.2 because v7 blocks every command
  until someone accepts its EULA.
- Windows ICU (icuuc/icuin) is a system DLL since 1703. Copying it out of
  System32 would redistribute Microsoft's files; the bundle check requires the
  import to be satisfied by Windows 10 1809+ instead.
- `theme` is `system|slate|nocturne` (default `system`, owner decision
  2026-09-10). System follows the device light or dark setting. Signed-out
  screens always follow the device.
- SQLite cannot alter a CHECK, so `allow_system_theme()` rebuilds an older
  preferences table once in one transaction; stored slate/nocturne are kept.
- The accent must stay at least CIE76 distance 15 from every category color
  (School blue is the near miss, about 18). Enforced by
  `test_every_accent_stays_clearly_apart_from_every_category_colour` in
  desktop/tests/test_look.py; the web test that used to guard it was deleted
  with the web client, and for a day nothing did.
- Linux leads with a tar.gz so the executable bit survives and no extra runtime
  is required. The AppImage ships too, but needs FUSE (libfuse2); without it
  the docs say `--appimage-extract` then `squashfs-root/AppRun`, or the tarball.
  Unused Qt `.qm` files are dropped.
- The smoke test decides a week was really drawn by counting colours in a grab of
  the window (`PAINTED_MIN_COLORS`, on an 8 px grid): a blank window is one flat
  colour. The WebEngine renderer recovery that used to sit beside it went with
  the WebEngine shell, and so did the 0.9.0 blank-window investigation, whose
  suspect was a CSS `backdrop-filter` that Qt widgets cannot draw.

## Session Handoff
- 2026-09-29, `feat/0.17-look`: 0.17.0 prepared on Jonathan's word to release once the UI was done:
  version, dated changelog, `docs/release-notes-v0.17.0.md`, and README's usage text (ten looks,
  Customise…, four animation levels). 0.17 is the design system and ten looks, the six designs he
  picked (One thing's Countdown, Day dial, Timeline's Planner spread, Mission control's Ops board,
  Bento with Hero: Week | Today, Clay deck's Card carousel, Retro desktop's Windows 98), the Look
  editor, and motion with four levels. Written by lane subagents, then verified: Grok's pass found 13
  failing tests and a rig that could not start (scratch XDG config broke Xwayland); the rig on the
  normal environment then found a Retro segfault (a kept widget leaving its row by setParent, so
  PySide held a freed layout item) and Bento and Clay drag failures; all fixed and merged, every
  design 40/40 or 3/3 on the rig. Deferred to a patch: `~/.flexweek-ui-harness/scratch/017-patch-list.md`,
  including the parked test-suite segfault with a lead from the Retro fix. The Rust engine contract
  waits on branch `engine/contract` for Jonathan to read; fwtest's S1b fixes are with Grok.
- 2026-09-28, `tooling/fwtest`: the Rust test harness `fwtest` is set up for Grok to build. The
  contract is `docs/tooling/fwtest.md`; `tools/fwtest` is an empty crate that builds; spec.md's
  Validation lists its cargo checks. Grok builds it on `grok/fwtest-harness` in
  `~/.worktrees/flexweek-fwtest-grok` from the sealed slices in that worktree's `.handoff/`
  (S1 the harness, S2 GLM's fixture, S3 parity). Next: review Grok's branch against the
  contract, then move README, AGENTS.md and CI to `fwtest` and delete `scripts/verify.py`,
  `scripts/mutate.py` and `run-alone.sh`. The 0.17 redesign waits on `feat/0.17-look`.
- 2026-09-26, `feat/0.16-polish`: 0.16.0 prepared on Jonathan's "let's finalize": version,
  dated changelog, `docs/release-notes-v0.16.0.md` and README's usage text. Since the review round:
  homework can be deleted with Undo across weeks (eaa326a), and the gate runs pytest on every core
  with a private Qt test home per worker (401c41a), 1576 tests in about 38 s. The packages were
  not built on this computer; the pull request's Release packages run builds and smoke-tests them
  before the release is made. A Windows install was not hand-checked.
- 2026-09-26, `feat/0.16-polish`: every row of Timmy and AL's 0.15.0 design review
  (`docs/0.16/design-review.md`) is built, on Jonathan's "Do all of them", in the six lanes of
  `docs/0.16/plan.md`, each merged after review. Fixed at integration: the focus countdown forced
  Inter on mono looks; `window_support.signed_out` now deletes the device look file, which one
  suite's saved knob had been handing to the next; a zoom mutation lane F's empty week had left
  uncaught now has a unit test (`test_hours_that_grow_twice_while_opening_still_open_where_they_were_asked`).
  Not released: version is still 0.15.0 and the changelog heading says Unreleased.
- 2026-09-25, `feat/0.15-tabs`: 0.15.0 prepared on Jonathan's "make a PR,
  after the code checks are verified merge, and then make the releases": the
  changelog is dated, `docs/release-notes-v0.15.0.md` covers lanes C and D1,
  and the changelog, notes and architecture say the Undo notice sits under the
  hours. The gate passed 1447 tests, every mutation spec was caught, every
  design's rig passed locally, and CI's rig passed 14/14 and 17/17. A Windows
  install was not hand-checked before the release.
- 2026-09-25, `claude/0-15-homework-planning`: Lane C code is committed at
  `1c6d3e6` after the five row-specific commits listed in Current State. The
  final focused suite passed 24/24 and full pytest passed 1329/1329. The
  verifier's fixed 300-second budget expired, while its ruff and mypy stages
  passed; running full pytest outside that budget passed. Planner and due
  mutations were caught 15/15. The two date-picker popups and the homework
  editor, including a length refusal, were visually
  checked at 1280x860 and 1150x768 with large text. Claude reviews before
  integration; do not merge this branch yet. No binary or remote action.
- 2026-09-24, `chatgpt/0-15-retro`: Retro Day and Week run on the shared
  hours engine as Schedule.exe and Week.exe. The pointer rig passed 14/14 Day
  and 17/17 Week; source verification passed 1311 tests; target mutations
  caught 11/11. The status bar no longer repeats an accepted drag time.
  Claude review remains before integration. No build or remote change.
- 2026-09-24, `chatgpt/0-15-bento`: Unit 13 implements Hero clock on Day and
  Hero board on Week from base `8e3634a`; it does not use the Retro branch.
  Bento owns only layout and paint. `HoursCanvas`, `TrayChip`, `HoursScroll`,
  and the window Hand supply the gestures. Part-of-day tiles were not built:
  the selected concepts use full-day tracks; any later tile must set its own
  `LinearTrack(first, last)` without new boundary logic. Day 14/14, Week 17/17;
  source gate 1296 passed; targets mutation set 11/11 caught. See the rig's
  checkout-scoped `runs/` for held/end images and videos. No binary, remote,
  or product contract change. Claude reviews before landing.
- 2026-09-23, `chatgpt/0-15-rig-ci`: The rig's per-checkout state now owns a
  private D-Bus as well as KWin or Xvfb/Openbox. The exact no-activation
  config from `6525429` is used; KWin and the app inherit its address, and
  `stop()` waits for each server before the bus. Source gate 1282/1282; live
  KWin Classic Day 14/14; shortcut-registration failures 0. The private
  socket and owned KWin were gone after stop. Local Xvfb is unavailable on
  this host. No build or remote change.
- 2026-09-23, `chatgpt/0-15-rig-ci`: Xvfb/Openbox and KWin share one hidden
  session interface scoped to each checkout. A concurrent old/new checkout
  pointer run passed 1/1 on each display; simultaneous updated KWin launches
  chose distinct displays and survived independent stop. The CI job saves
  Day/Week screenshots, results and video; its ownership tests now run in CI
  and normal pytest collection. The previous full pointer matrix passed 31/31
  locally and in a container; the isolation checks above and the 1269-test
  source gate passed afterward. The next external check is the GitHub Actions
  run after owner review. `spec.md` has the CI description drift noted above.
  Nothing pushed.
- 2026-09-23, `grok/0-15-month-blocks`: Each `days` entry of `GET /api/month`
  has `blocks`, the timed work on that date in start then title order. A
  repeating block keeps one id on each of its dates with `repeats` true.
  Homework with a time carries `assignment_id`; homework without a time is
  absent. A chip looks like
  `{"id": "school", "title": "School", "start": "08:00", "duration_min": 390,
  "category": "School", "kind": "locked", "assignment_id": null, "repeats": true,
  "pinned": false, "completed": false}`. Busy September 37,206 bytes / 175
  chips. Desktop was not edited; `month_cells` already reads `day["blocks"]`.
  Gate: 1278 passed. spec.md was not edited. Nothing pushed. Claude reviews
  before it lands.
- 2026-09-23, `grok/0-15-move-date-2`: Cross-week move follow-up on `062f292`.
  History steps keep each week's last-seen revision from the save reply and
  send it on undo and redo. A later save to the other week is a 409, same
  words as other saves, both weeks untouched.
  `date_problem(block_id, from_iso, to_iso, start=None, duration_min=None,
  assignment_id=None) -> str | None` judges from start and length when the
  week is not local. Tests:
  `test_undo_of_a_move_refuses_when_the_other_week_changed_elsewhere`,
  `test_date_problem_judges_a_chip_when_its_week_is_not_loaded`. Gate: 1274
  passed, `scripts/verify.py` green. spec.md was not edited. Nothing pushed.
  Claude reviews before it lands.

- 2026-09-23, `grok/0-15-month-weeks`: Unit 8. `NativeSession.move_to_date(block_id, from_iso, to_iso) -> bool` moves a block to another date. Same week keeps the time; another week writes both documents through `POST /api/changes` in one Undo step. A repeating block moves only that day. Homework keeps its pin. The open week does not change until the reply. `date_problem` is the same `span_problem` words for a held chip. No backend change. Gate: 1261 passed, `scripts/verify.py` green. spec.md was not edited. Nothing pushed. Window still holds the Month placeholder; Unit 9 can call `move_to_date`.

- 2026-09-24, `chatgpt/0-15-mission`: The extra Week initial no longer
  overlaps shortened shared words on a 30-minute block. A 15-minute block
  still gets its initial, and Mission restores the painter's font after it.
  Render regression red before, green after; Mission 14/14, source gate
  1248/1248. Awaiting Claude review. No rig, build, push, or PR.
- 2026-09-23, `chatgpt/0-15-mission`: `MissionView` retains parked scrolls
  under its page rather than orphaning them. A Week → Day → Week host-deletion
  test failed on the old behavior and passes on the fix. Mission 13/13; full
  source gate 1247/1247 with ruff and mypy clean. Awaiting Claude review;
  no rig, build, push, PR, or `spec.md` edit.
- 2026-09-23, `feat/0.15-tabs`: Unit 5 done. Rig matrix for Today's app: Day 14/14, Week 17/17,
  including Escape, switching away, dwell, a save landing mid-drag, a second move while a save
  is in flight, double-click to open, Day and Week agreeing, and 1150x768 with large text.
  Found and fixed on the way: a held block dropped after switching views; tray chips cut off at
  large text; a hang when the garbage collector freed the look pictures' leftovers mid-paint.
  `RIG_GC_REPORT=1` makes the rig name any Qt object left in cyclic garbage. Mutation runner:
  `.venv/bin/python scripts/mutate.py`. Gate 1240 passed. Nothing pushed.
- 2026-09-22, `grok/0-15-night-last`: Night slots sort last. A 60-minute low
  session with 17:00–23:00 locked went to Monday 00:00 on `e7e5206` and goes
  to Monday 06:00 here. Night is still used when 06:00–23:00 is full.
  `test_generated_weeks_preserve_grid_bounds_occupancy_and_input` now also
  runs under `DEFAULT_WORK_WINDOWS`. Busy-week, 20 solves of the same
  fixture: median 7.971 ms / max 12.819 ms, all complete, all under 150 ms
  (was median 7.215 / max 10.773 on the audit branch). Source gate: 1203
  passed, `scripts/verify.py` green. spec.md was not edited. The full-day
  worktree's uncommitted spec.md was left alone. Nothing pushed.

- 2026-09-22, `feat/0.15-tabs`: Unit 3, zoom and scrolling on hours. `hours/zoom.py` holds the
  levels, the header kept above the hours and the scroll that keeps a minute in place; Today's
  app's Day and Week use it, and the level is kept in the look file. Resize zones never take
  more than a fifth of a block. Source gate 1202 passed; Classic rig Day 7/7, Week 10/10 with
  the real pointer zooming. The rig's app runs with `QT_XCB_NO_XI2=1`, because Qt on the hidden
  display never hears xdotool's wheel otherwise. Nothing pushed.
- 2026-09-22, `fix/015-rig-reach`: `HoursCanvas.in_view` requires a track that
  contains the requested minute. A scrolled 06:00–22:00 track test failed
  before the fix and passes after it. Full source gate: 1181 passed; Classic
  Week reach pointer rig: 1/1. The branch is local and ready to integrate with
  the 0.15 work.
- 2026-09-22, `grok/0-15-audit-01` at `3d1fab2`: Chat's three follow-up
  findings (`df34b9d`, `6a1e672`, `3d1fab2`). Midnight on 31 December 2099
  stores `2099-12-31T23:59` so `PUT /api/week` does not 500. The leftover
  homework list uses `due_sort_key`. Week-reach checks the hours viewport,
  not the window. Source gate: 1180 passed, `scripts/verify.py` green.
  Classic Week pointer rig 8/8. spec.md was not edited. Nothing pushed.
  Still planned: Unit 3 zoom and the full reach matrix, 3b work windows in
  setup/Settings, due dialogs, and 5–17.

- 2026-09-22, `grok/0-15-audit-01` at `ff5df31`: Chat's six audit findings are
  on this branch, merged from `grok/0-15-full-day` (`d4bfd92`) and
  `grok/0-15-optional-due` (`dc9b7fa`) onto `feat/0.15-tabs` at `248a318`.
  Midnight completions save as the next date at 00:00. Due lists use the
  parsed deadline. Date-only 23:45 is allowed. The 15 stale Classic widget
  tests read the hours canvas. The pointer opens Day from the Day tab. The
  week scrolls at 48 pixels an hour with day names at the top, so a block
  can be grabbed; 00:00 and 24:00 can be scrolled on screen. Source gate:
  1177 passed, `scripts/verify.py` green. Classic pointer rig: Day 4/4, Week
  8/8. Month 0/3 (no `month_surfaces` yet, Unit 9). Busy-week solver, 20
  solves of school 08:00–14:30 Mon–Fri, a 22:00–23:00 lock daily, twelve
  45-minute tasks due Sunday 21:00: median 2.229 ms / max 5.695 ms at
  `248a318`, median 7.215 ms / max 10.773 ms here; all under 150 ms, all
  complete. spec.md was not edited. Nothing pushed. Next: Chat's independent
  review. Still planned: Unit 3 zoom and the full reach matrix, 3b work
  windows in setup/Settings, due dialogs, and 5–17.

- 2026-09-22, `feat/ui-setup`: 0.14.3 prepared on Jonathan's "Ship it":
  version, changelog heading, `docs/release-notes-v0.14.3.md`, and the
  first-open text in README and `docs/github-release.md` now describe the
  paged setup. Spotify Dismiss on a real alarm and a Windows install were not
  hand-checked before the release.
- 2026-09-22, `feat/ui-setup`: Daily Scheduler's drag, on Jonathan's four
  answers (15-minute snap, overlaps side by side, a repeat moves one day,
  other designs drop onto a day's hours). `desktop/native/canvas.py` is the
  week (a port of `views.py` TimelineWidget; `WeekCanvas` replaced
  `WeekTable`, `laid_out` applies the live preview). `layouts/drawer.py` is the
  day drawer for Timeline, Bento, Retro and Clay; Mission, dial and One thing
  keep their own hours. One judge, `NativeWindow._judge_span`: `span_problem`
  refuses only outside hours and past due, `span_clash` names the neighbour.
  Pinned sessions are exempt from `settle_placements` clashes. A move made
  while a save is in flight is held in `_move_waiting` and replayed, since the
  save's reply replaces `session.blocks`.
- 2026-09-22, `feat/ui-setup`: dragging in every design (Jonathan's ask before
  the spec edit). `desktop/native/layouts/drag.py` holds the pick-up, the drop
  zones and the view-owned outline, line and hint; the window's `_judge_drop`
  is the one rule, `span_problem` as on the grid. A drop on a day plans waiting
  homework through `solve(on_day=...)` and pins it; a placed block keeps its
  time. Views hold re-renders while a drag is on (the minute tick would delete
  the source). Gate: 1121 tests, pytest 252 s of the 300 s budget.
- 2026-09-21, `feat/ui-setup`: the UI and setup plan, implemented on
  Jonathan's go with the Appendix E defaults (guided pages starting from a
  style, all three planning styles with Suggest as default, a drop pins, one
  alarm sound). Backend units built by Claude, not Grok, since he said
  implement now. Real-desktop screenshots and a setup video in
  `~/.claude/orchestrate/flexweek-ui-setup/docs/media/final`. Next: owner
  review of the pictures, then PRs if asked.
- 2026-09-21, `fix/0-14-1-trust`: 0.14.2 release prep (VERSION, CHANGELOG
  heading, `docs/release-notes-v0.14.2.md`). Published as the latest full
  release, not a pre-release, so 0.14.x installs are offered it. 0.14.0 and
  0.14.1 carry the old updater, which hangs when GitHub's API rate-limits the
  address; the notes tell those students to download by hand if it seems stuck.
- 2026-09-21, `fix/0-14-1-trust`: Claude's fixes from the second review of
  Grok's run, one commit each: missed-day and Running late saves (apply_plan
  writes only unfinished homework), the week title (FittedLabel with a short
  form), Start/End-only fixed activities, view names with a purpose, notices
  said once and naming everyone, and the latest reason after a failed plan.
  No push, no executable, VERSION 0.14.1, spec.md not edited. GLM skipped on
  Jonathan's instruction; Jev used. Next: owner review, then 0.14.2 when asked.
- 2026-09-21, `fix/0-14-1-trust`: Claude's trust-review items on the 0.14.1
  audit branch. Leftover copy, one-step Running late undo, settle/keep-plan,
  Month host, username/estimate/More details/Today/Start+End, offscreen 1024
  gear. Dialog 150 px still unverified. spec.md not edited; flagged Month
  decision 7 and Running late re-solve drift. Gate: 977 Python tests,
  `scripts/verify.py` VERIFIED. No push, no executable, VERSION
  0.14.1. Next: owner review.
- 2026-09-21, `feat/0-14-1-release`: 0.14.1 shipped (PRs #23 and #24). It was
  published as a pre-release first, then marked latest so 0.14.0 installs can
  be offered it. Windows installers still want a hand-check on a real PC.
- 2026-09-21, `claude/0-14-1-ia-fixes` on `grok/0-14-1-ia`: review fixes for
  0.14.1, the spread-preview wording, and Settings that apply as they change
  (Jonathan's addition to 0.14.1: no OK/Cancel, account prefs saved 600 ms
  after the last change and on Close), worktree
  `~/.worktrees/flexweek-ui-claude`. No push, no spec.md edit, VERSION still
  0.14.0. Next: Jonathan decides on push/PR for both branches together, then
  the 0.14.1 version bump and release when asked.
- 2026-09-21, `grok/0-14-1-ia`: 0.14.1 IA harden, seven local commits, worktree
  `~/.worktrees/flexweek-ui-grok`. Chrome, Settings, minutes, Running late
  toast, setup placeholder. No push, no spec.md edit. Next: Claude review.
- 2026-09-20, `feat/layout-surfaces`: Day/Month follow the week layout,
  Settings rail, first-week setup card. Worktree
  `~/.worktrees/flexweek-layout-surfaces`. Nothing pushed. Next: owner
  feedback, then PR if asked.
- 2026-09-19, `grok/ui-fixes`: four native screenshot-audit fixes, one commit
  each, worktree `~/.worktrees/flexweek-ui-grok`. Next: Claude reviews the
  frontend. spec.md still says WebEngine desktop.
- 2026-09-19, `feat/retire-webengine`: deleted the retired Chromium shell and
  leftover probes. Native smoke stays. Next: merge, then delete merged remote
  branches. spec.md still says WebEngine desktop.
- 2026-09-19, `feat/0-12-release`: 0.12.0 packaging and release notes. Nuitka
  skips `desktop.webengine`. Release jobs fail if WebEngine lands in the
  package. Next: merge, tag `v0.12.0`, `gh release create`, wait for assets.
- 2026-09-18, `feat/native-python`: finishing PR #15 after Claude's UI. T from
  an item view now reaches My day, and Tools keeps Copy, Paste and Duplicate
  when a layout hides the planning bar. Next for the owner: merge #15, then
  Amendment A/C if the fields should live on the account. Web layouts and
  packaged native builds are still out of this PR.
- 2026-09-18, `feat/native-python`: Claude built the eight layouts the owner
  picked from the look-concepts mock-up, one verified unit per commit: the week
  model, the registry, My day with One thing and the Layout dialog, Day dial,
  Bento with the Tools menu, Timeline, Mission control, Clay deck, Retro desktop.
  Open for the owner: approve Amendment C's `layout_*` account fields, and the
  spec.md drift it lists. Not done: layouts in the web client; a per-session
  "done" (the product only finishes whole homework, so day screens say Homework
  finished). GLM checked Amendment C through OpenCode and three of its findings
  were right: Today's app has no colourways, Timeline's strip stored `hide` for
  a choice the contract calls never hidden (now `bars` and `names`), and one
  option label was shortened. Earlier reports that GLM was down were wrong:
  `opencode run` waits for stdin to close, so call it with `< /dev/null`. Defects
  found by looking at screenshots rather than by tests, each now pinned by one:
  a design's rule losing to the reset's more specific selector; a wrapped title
  and a three-line card cut off because a stylesheet min-height beats
  setMinimumHeight; Bento as a 300 pixel letterbox under the week grid's
  controls; three designs pushing the window past a 768 pixel laptop; closing a
  Retro window crashing the view. `Homework finished` wired straight to
  `complete_homework` did not save, which a window test caught.
- 2026-09-18, `feat/native-python`: Claude committed Grok's finished but
  uncommitted owner-answers work as 8d351d2 after the gate passed on it, then
  built Paper and Pastel in both clients. Red checks: a pale lavender accent, an
  accent parked on a category colour, native colours drifting from the web's,
  Paper going sharp or losing its serif, Pastel dropped from the menus, a token
  missing from a map, and Pastel losing its raised panels each turned a named
  test red. One red was first reported for the wrong reason: same-length edits
  to one .py file inside a second reuse stale bytecode, so mutation runs now set
  PYTHONDONTWRITEBYTECODE and clear the module's .pyc. Offscreen grabs of both
  clients were checked by eye. Next: the owner's approval of Amendment A, then
  the `look_*` fields and presets joining `theme_pack`. Nothing pushed.
- 2026-09-18, `feat/native-python`: owner answers 1–7. Look is one menu
  (packs then Terminal/Poster/Ink/High contrast). Knobs set by hand survive a
  look change. High contrast is opt-in only. Native More holds overflow
  actions; large text enlarges that menu and the web More menu. Dirty weeks
  park as drafts and the selected weekday maps into the opened week. Reminders
  use today's week, fetched silently when another week is on screen. Paper and
  Pastel are still Claude's. Amendment A account `look_*` fields and joining
  presets to `theme_pack` wait on approval. Nothing pushed.
- 2026-09-18, `feat/native-python`: finished the post-unit native review and
  the next three look presets. `fix/native-logic` and `fix/native-ui` merged
  locally. Week loads apply week+assignments together; dirty navigation is
  refused; undo keeps live focus counters; W/D/M and Ctrl+C reach the window
  from the calendar. Poster, Ink and High contrast are selectable device-only
  presets. Amendment B in `docs/stage8-appearance-contract.md` records how Qt
  draws frost, depth and hairlines. Nothing pushed.
- 2026-09-17, `feat/native-python`: GLM 5.3 Flash parity audit of units 4–6.
  Native now matches the web client on lead-0 reminders, queued alarms, this-
  week-only reminder sources, week-file replace confirm, restore clearing undo
  and a vanished focus timer, expiry forgetting the timer, completed-flexible
  day export, and the week-file reject list. Nothing pushed.
- 2026-09-17, `feat/native-python`: units 4–6 of the native Python overhaul are
  in. Default launcher is native widgets. Focus credit, prefs packs, recovery,
  restore points, week files and `--smoke-test` without Chromium. Packaging
  still points at WebEngine in its scripts and stays unbuilt. Nothing pushed.
- 2026-09-17, `feat/native-python`: unit 3 of the native Python overhaul is in.
  Internal clipboard and collision previews, locked-only routines with
  `snapshot_label`, unfinished homework identity, missed recovery, running late,
  spread and availability prefs. Undo/Redo of the week on screen stay. Next is
  unit 4 (focus timers, packs, tray). The WebEngine app stays the default.
  Nothing pushed.
- 2026-09-17, `feat/native-python`: unit 1 of the native Python overhaul is in.
  `python -m desktop.native` is the experimental launcher. Next is unit 2,
  calendar and homework parity (Day, Month, drag, occurrence vs series). The
  WebEngine app stays the default. Nothing pushed.
- 2026-09-17, `feat/look-knobs`: presets-and-knobs architecture with Terminal
  as the proof, device-only. Knob rules are constrained by a static test that
  lets each move only what it names; the flat surface must clear blur on
  exactly the frosted panels; any preset palette is audited for same tokens, AA
  text and accent distance automatically once named in the token test. Red
  checks caught a real gap: the payload test only guarded preferencesPayload()
  while the Save button spreads readComfortEdit(); it now captures the real PUT
  on submit. A real offscreen grab caught what no test could: pill corners
  turned tall blocks into capsules that clipped their titles; blocks now cap
  their radius at 0.5rem and a static test holds it. Next: owner decides on
  Amendment A (fold Preset into Look, which
  presets next, reset-on-preset), then Grok adds the fields and the knobs move
  to the account. Poster, Ink and High contrast are the recommended next three.
- 2026-09-17, `feat/0-11-seamless` (latest): pack UI, frost token maps,
  Customize and account-backed motion are in. First sign-in writes omitted
  motion from the device copy. Phone width hides Customize. P2 account copy
  is still open. Nothing pushed.
- 2026-09-17, `feat/0-11-seamless`: owner approved the appearance
  contract. Light frost / Dark frost are new token sets; pack sits beside
  `theme`; motion seeds once from omitted/`None` then the account wins; accents
  are `default`, `sky`, `gold`, `sea`, `sand`. spec.md lists the fields.
  Backend round-trips them on `/api/preferences`. Frontend still keeps motion
  device-only and has no pack picker. Next: Claude's pack UI and account-wired
  motion. Nothing pushed.
- 2026-09-17, `feat/0-11-seamless`: `docs/stage8-appearance-contract.md`
  is written and proposed, not approved. GLM drafted it through OpenCode; the
  channel that works is passing the brief as an attached file (`-f`), not as a
  long argv, which failed three times. One chunk still returned empty on its
  first try and worked on retry, so treat it as flaky rather than fixed.
  Corrections to GLM's draft are listed in the contract's header note. Five
  owner decisions are open, including Light frost / Dark frost and which
  accents to offer. No spec.md change until the owner approves.
- 2026-09-17, `feat/0-11-seamless`: accepting a late start now marks that one
  block so it draws onto the grid, on the re-plan's redraw rather than the one
  before it, which would have been replaced mid-animation; a failed re-plan
  takes the mark back down. Settings splits Appearance into "Theme and layout"
  (account) and "This device only" (Motion). Gate green: 274 frontend, 365
  Python. Note for whoever reads the history: commit 3157f1d overwrote
  CHANGELOG.md with a copy of context.md through a scripting mistake, and
  2ddc3b4 did not catch it. Restored from 9b03f60. Nothing in the gate reads
  CHANGELOG.md, so no test could have caught it.
- 2026-09-17, `feat/0-11-seamless`: added the chip gesture and the motion
  slice on top of the seamless work. A sidebar type chip now opens Add with
  that category; the calendar WebEngine probe encoded the old contract and was
  updated, which is real-browser evidence for the change. Motion lives in a new
  head script `frontend/motion.js` writing `<html data-motion>`, device-only in
  localStorage under `flexweek-motion`, with the Settings control wired from
  comfort.js so no head script touches page elements. The CSS gate is static:
  theme-tokens.test.mjs now proves no rule animates backdrop-filter, keyframes
  move only opacity and transform, every animation sits inside
  prefers-reduced-motion: no-preference, Off animates nothing, and no frosted
  panel is animated. Gate green: 270 frontend, 365 Python. GLM is drafting
  docs/stage8-appearance-contract.md; packs, accent and the account-persisted
  motion level wait on that contract and owner approval.
- 2026-09-17, `feat/0-11-seamless`: PR #13 merged the 0.10.1 hotfix and the
  release-polish roadmap to `main` at 251c59a. Started 0.11 with the seamless
  slice: showBusy() in app.js swaps a button's label while its request is out
  and restores it only if nothing else wrote a new one, wired into Solve,
  Spread and Running late; leaving Month for Week or Day now anchors to the
  month on screen through openMonthAnchor() in month.js. Seven new node tests,
  all red-checked. Gate green: 260 frontend, 365 Python. Still open in 0.11:
  motion, the appearance packs and Customize submenu (needs a contract and
  owner approval before spec.md changes, since preferences gain fields), the
  P2 account copy, and a decision on what "add-from-chip stays one gesture"
  refers to.
- 2026-09-16, `fix/0-10-1-hotfix`: implemented the 0.10.1 hotfix. Running late
  now reports every refusal and every outcome, Month says when a month is early
  rather than looking broken, the date numbers are larger, the collapsed
  explanation list is "See the rest of your plan", setup stops suggesting
  "Sports" as a sport name, and Hide sidebar moved out of the date controls.
  Ten new node tests, each red-checked. Gate green: 253 frontend, 365 Python.
  The reported name-field letter loss could not be reproduced and has no cause
  in the frontend or the Qt shell; only a re-open guard and regression tests
  landed for it. Next step: reproduce that symptom on Jonathan's machine, then
  the Qt WebEngine walkthrough before tagging 0.10.1.
- 2026-09-16, `docs/roadmap-0-10-1`: recorded the owner's post-0.10.0 plan in
  roadmap.md as "Release polish (2026-09-16): 0.10.1, then 0.11", and pointed
  the roadmap header at it. 0.10.1 is five fixes (two P0: the assignment name
  field losing letters, and Running late giving no visible result); 0.11 is wait
  states, targeted motion, and theme packs with a small Customize submenu.
  Nothing in the app changed yet. Next step: reproduce the name-field bug on the
  packaged build, since no code path rebuilds that input on a keystroke today.
- 2026-09-16, `main`: PR #12 merged the seven student-experience stages, so
  `main` now carries Stages 1-7 and a spec.md that matches every approved
  contract. Follow-up work starts from `main` at aca3068, not from the stage
  branches. Two packaging facts matter for whoever builds next: the CI runner
  builds the Linux bundle successfully, and this workstation cannot, because its
  glibc is newer than the 2.38 portability baseline the bundle check enforces.
  Open product work: the Stage 2 student trial of the "Plan my homework"
  wording, Stage 7 student trials and measured comparisons, Year view, hosted
  deployment, and the Qt shell's Stage 5 start-at-login and tray Test.
- 2026-09-15, `feat/stage7-month-frontend`: integrated `grok/stage7-month-backend`
  (merge 398531e; only CHANGELOG.md and context.md conflicted, both additive, and
  backend/app.py plus backend/weeks.py were checked against both parents). Then
  fixed the `GET /api/day` over-count (e8b7b5e) and added planned work to Month
  (fc95fc7). `backend/month.py` pins a session by `completed_day`, or by a lone
  candidate day for open work; `unscheduled` carries the rest; `focus_min` is the
  completed part of `scheduled_min`. `frontend/month.js` renders "all done" /
  "1 h done" per cell and a note for undated work. Ten mutations were red-checked
  across the three commits. The owner approved the Stage 4, 5 and 7 contracts, so
  spec.md and the contract status lines were updated. Gate: 242 frontend, 364
  Python. Nothing pushed.
- 2026-09-15, `feat/stage7-month-frontend`: accessibility fixes from Grok's
  Stage 6 audit. `aria-live="polite"` on `#account-sync-note` and
  `#recovery-status`; `#account-import-preview` is a named `role="group"` with
  `tabindex="-1"` that `renderTransferPreview` focuses; `signedOut` focuses the
  target screen's username field only when an account was signed in. A focus
  move beats a live region on the preview because it holds the whole diff and
  the destructive confirm button. Each of the four new rules was broken in turn
  and its named test went red. Gate: 238 frontend, 353 Python. Grok's matching
  backend fixes are still unmerged on `grok/stage7-month-backend`. Nothing
- 2026-09-15, `grok/stage7-month-backend`: Audit done (own review + three GLM
  passes). Backend findings fixed and tested; three minor accessibility
  findings handed to Claude (see Current State); two product questions for the
  owner on what a month "session" means when placements are not stored.
  Nothing pushed.
- 2026-09-15, `grok/stage7-month-backend`: Stage 7 backend slice. Proposed
  contract is `docs/stage7-contract.md`. `GET /api/month?month=YYYY-MM` is
  authenticated and CSRF-free. Claude owns the Month UI. spec.md drift: the
  month route. Full gate: 221 frontend tests, 351 Python tests. Nothing
  pushed.
- 2026-09-15, `feat/stage7-month-frontend`: Stage 7 Month API and shared UI are
  complete. `frontend/month.js` owns read-only Month state and stale-response
  guards. The real WebEngine case checks actual API data at 1280px and 390px,
  then opens Day. The full source gate passes 235 frontend and 353 Python tests.
  The request-token mutation overwrites the newer reply with two deadlines and
  fails as expected. Student trials, metrics and PR review remain. The Month
  contract is proposed, so `spec.md` still omits its route. No executable was
  built and nothing was pushed.
- 2026-09-15, `grok/stage6-transfer-limit`: Owner approved the Stage 6 spec
  updates and skipped hosted deployment, installers and iOS checks.
  `docs/stage6-contract.md` is approved 2026-09-15. `spec.md` now lists recovery,
  password, deletion, storage-info fields, transfer routes and the 256 KiB
  apply-envelope rule. Stages 4 and 5 remain proposed. Remaining Stage 6 work is
  the security/accessibility review. Nothing pushed.
- 2026-09-15, `grok/stage6-transfer-limit`: Export and import now share the
  256 KiB write cap. Export 413s when the compact `{snapshot, state_token,
  operation_id}` envelope would not fit import apply. The 400-week transfer cap
  is gone; `storage-info` reports `transfer_limit_bytes`. The page measures that
  envelope rather than raw file size. Remaining Stage 6 work is hosted
  deployment, security/accessibility review, installers and physical platform
  checks. `docs/stage6-contract.md` remains proposed; spec.md drift includes the
  new field and envelope rule. Web-only gate: 221 frontend tests, 263 Python
  tests. Nothing pushed.
- 2026-09-15, `feat/stage6-access-frontend`: Shared Stage 6 UI complete over
  backend 6a5e3aa. `frontend/access.js` owns displayed recovery codes, storage
  identity and previewed transfer state; `auth.js` owns the recovery session
  transition. Wrong password errors keep valid sessions, and account changes
  clear codes and snapshots. A WebEngine case transfers a real saved week
  between accounts. The final gate passes 218 frontend and 331 Python tests;
  the 401 guard mutation fails by clearing the signed-in account as expected.
  Remaining Stage 6 work is deployment, broader review and physical platform
  evidence. `docs/stage6-contract.md` remains proposed; `spec.md` still omits
  its routes. No executable built; nothing pushed.
- 2026-09-14, `feat/stage5-comfort-frontend`: Shared Stage 5 UI complete over
  backend 10c9334. New `frontend/comfort.js` owns presets, split previews, alert
  previews and remembered layout. Settings writes wait for in-flight layout
  writes; account changes discard stale previews. The Qt shell still needs
  start-at-login application and tray Test. `spec.md` still omits the proposed
  comfort fields and three routes. No executable built; nothing pushed.
- 2026-09-14, `grok/stage5-comfort-backend`: Grok's Stage 5 backend slice.
  Contract is `docs/stage5-contract.md` (still proposed). Comfort fields omit
  defaults so Phase 7 GET still matches. Split preview snaps 25/5 to 30/15.
  Auto-split with a 25-minute work length is 422. Claude still owns the
  Settings UI. Desktop autostart/tray Test is not wired. spec.md drift: comfort
  fields, `/api/timer-split-preview`, `/api/timer-presets` and
  `/api/reminder-limits`. Web-only gate: 195 frontend tests, 243 Python tests.
  Cartographer skipped (not installed in the project venv). Nothing pushed.
- 2026-09-14, `feat/stage4-adaptive-plans`: Stage 4 finished in this tree.
  Accepting Running late writes a locked "Running late" block through
  `/api/changes` then re-solves; a failed re-solve keeps its error status.
  spec.md drift: Stage 4 routes and fields stay off the public API table until
  the contract is approved. Nothing pushed.
- 2026-09-14, `grok/stage4-adapt-backend`: Grok's Stage 4 backend slice.
  Contract is `docs/stage4-contract.md` (still proposed). Running late is a
  solve preview that occupies `[from_start, from_start + minutes)` on one day,
  reuses `RESHUFFLE_AFTER_MISS` with a distinct sentence, and never drops
  unplaced work. Spread is `POST /api/assignments/{id}/spread` and does not
  write. Assignment notes, links and checklist omit empties. Preferences keep
  protected / study / cutoff in `availability_json`; `POST /api/solve` loads
  them. spec.md drift: those fields, `running_late` and the spread route are
  not in the public API table until the owner approves the contract. Claude
  still owns UI. Web-only gate: 163 frontend tests, 229 Python tests.
  Cartographer skipped (not installed in the project venv). Nothing pushed.
- 2026-09-14, `claude/stage3-frontend`: Stage 3 finished by Claude. Codex's
  frontend (857f43d, 1f569aa) and WebEngine case (d666a92) sit on Grok's backend
  (a6b484f, the same patch as cfb8c48 on `grok/stage3-reuse-backend`). a438d3a
  fixes a batch paste over-planning homework, long routine names failing Apply,
  a 409 leaving a save stuck, restore jumping to this week, shortcuts firing
  behind open dialogs and invalid preview rows starting checked. b8d74b2 extends
  the WebEngine walkthrough and adds `stage3_mobile`. 25d0884 keeps a stale
  preview from saving after a 409. Grok's docs commit 4bada61 is folded into
  this branch's CHANGELOG and context. Gotchas: runJavaScript does not hand
  arrays back reliably, so probes pass JSON text; port 8765 belongs to another
  local service; the T3 preview browser could not load a local server. Nothing
  pushed.
- 2026-09-14, `docs/stage3-contract`: proposed Stage 3 contract based on
  `claude/stage2-frontend` at 3b1f1c9. Claude owns the shared browser/desktop
  frontend; Grok owns migrations, routes and backend tests. The contract keeps
  clipboard, fixed-only routines, assignment-preserving carry-forward and
  durable restore points separate. Nothing implemented, built or pushed.
- 2026-09-14, `claude/stage2-frontend` and `feat/stage2-student-experience`:
  Claude's Stage 2 frontend on Grok's `254e086`. The Day agenda and quick Add
  homework live in `frontend/day.js`. Day view session times come from the week
  in memory and its plan, because placements are not stored; `/api/day` supplies
  the workload and each due-soon homework's unplanned minutes. Update my plan
  stays once a week has been planned in this page session (`planned` on the
  week state). Gate lessons: the theme guard reads an id such as `#add-…` as a
  hex color, so style by class; the desktop smoke flow waits on the setup
  button's text. Grok has not reviewed these commits. Nothing pushed.
- 2026-09-13, `grok/stage2-day-backend`: Grok's Stage 2 slice, `GET /api/day`.
  Claude still owns Day/Week UI, Add homework and Plan my homework copy.
  spec.md drift: the day endpoint is not in the public API table until the
  contract is approved. Nothing pushed.
- 2026-09-13, `docs/stage2-contract`: proposed Stage 2 contract in
  `docs/stage2-contract.md`. Base is `feat/stage1-student-experience` at
  130ee99.
- 2026-09-13, `feat/stage1-student-experience`: locally integrates the staged
  student-experience roadmap with the approved Stage 1 contract, reviewed
  backend, five frontend feature commits and the Qt WebEngine probe. Stage 1 is
  marked complete; Stage 2 is next. The full source verifier is green (139
  frontend, 241 Python), and packaging was not run during integration.
- 2026-09-11, `docs/readme-screenshots`: README screenshots in `docs/images/`
  (week light, week dark, setup), taken offscreen at 1.5x from the real app with
  a demo week and a Wednesday 16:20 clock; a readme test keeps every shown image
  present and none unused. v0.9.2 released with the Windows installers.
- Open: the owner is diagnosing the Windows setup-dialog flicker with a separate
  prompt (GPU/ANGLE/Qt renderer switches, then DevTools CSS toggles).
- 2026-09-11, `feat/windows-installers`: Inno Setup and WiX scripts in
  `packaging/windows/`, workflow builds, installs, shortcut-checks, smokes and
  uninstalls both; pull requests touching packaging run it without uploading.
  Docs and `desktop/tests/test_windows_installers.py` updated. Release notes in
  `docs/release-notes-v0.9.2.md`.
- 2026-09-11, `fix/0.9.1`: renderer recovery (shell reload with
  `?recovered=1`, solid panels, re-Solve, native panel on a repeat), extended
  smoke with pixel check and throwaway data, WebEngine `recovery` probe,
  basename AppImage checksum plus workflow check, AppImage FUSE and Windows
  shortcut doc lines, release notes in `docs/release-notes-v0.9.1.md`.
- v0.9.1 released and marked latest after CI smoke passed on all three builds.
- 2026-09-10, `feat/hybrid-frost`: token maps, frosted chrome, grid tokens,
  Light/Dark labels, slate signed-out default, Figtree, duotone icons, theme
  token tests and CHANGELOG. Before/after screenshots were taken offscreen in
  /tmp/fw-frost (not committed). Nothing pushed.
- Theme defaults to System per the owner's spec change (same day): API,
  storage migration, theme.js, menus and probes updated.
- Next: owner review of both themes on a real screen.
- Open: hosted web URL, a hand check of close-to-tray and of the Windows zip
  on a real PC.
