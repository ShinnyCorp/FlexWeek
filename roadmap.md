# roadmap.md — FlexWeek

Congressional App Challenge 2026. Submit **Sunday, Oct 25, 2026, 8:00 p.m. PDT**
(hard deadline Monday, Oct 26, 9:00 a.m. PDT). Phases map to build weeks; a
phase may span several implementation slices. The original Sep 6 contest brief
(working title Reslot) is archived in [docs/cac-build-plan.md](docs/cac-build-plan.md).

FlexWeek is one Python desktop app: see [native Python desktop](#native-python-desktop-2026-09-17)
and [web client retired](#web-client-retired-2026-09-19). The browser client is
gone, so any `frontend/` path below is history and is marked where it stands.
0.11.0 has no open leftovers: its Windows `backdrop-filter` flicker check went
with the web client, because Qt widgets have no `backdrop-filter` to flicker.
The [student experience revision](#student-experience-revision-2026-09-12) stays
the stage map for everything still open. Earlier phase descriptions and the
first implementation slice retain their dated planning history.

## Phase 1 — Skeleton (Sep 6–12, 2026)
- Tasks:
  - Repo, GPL-3.0 license, README, ARCHITECTURE
  - `models.py`: `TimeBlock`, `Move`, `SolveTrace`, slot helpers — no solver
  - Seed `demo_alex.json` and `demo_jordan.json` from partner data
  - `index.html` + `styles.css`: 7-column grid 06:00–23:00, locked blocks
    painted, flexible tasks in the sidebar
  - `app.py` serves `frontend/` and `GET /api/demos` (the browser client was
    retired on 2026-09-19; `app.py` is an API only)
  - Governance files: spec.md, roadmap.md, context.md, CHANGELOG.md
  - Partner: interview 3 students; two anonymized weeks, 8 tasks each
  - Register for CAC; confirm congressional district and that the Member hosts
- Complete when: `uvicorn` shows two demo weeks and `pytest` has ≥10 helper
  tests green.
- Status: [~] Code exit green 2026-09-06 (15 tests, both demos 8 flexible,
  logo in the topbar). Open: partner interviews/pitch, CAC registration,
  district confirmation.

## Phase 2 — Solver v1 (Sep 13–19, 2026)
- Tasks:
  - `solve(blocks) -> SolveTrace`: backtracking + MRV + forward checking
  - Locked intervals and deadlines; sleep 23:00–06:00 as a locked guard
  - Fixtures: empty, packed, impossible, one 3-hour paper due tomorrow
  - Debug panel in JS: `solve_ms`, placed count, unplaced titles
  - Partner: three break-it cases on paper, then in the app
- Complete when: 20 fixture tests green; the packed fixture solves or fails with
  `NO_SLOT_LEFT` under 150 ms and never hangs.
- Status: [~] Code exit green 2026-09-06 (37 tests, packed and both demos
  under 150 ms). Open: partner break-it cases.

## Phase 3 — Usable app (Sep 20–26, 2026)
- Tasks:
  - HTML forms: add / edit / delete, locked vs. flexible
  - Persist the last week in `localStorage`; demos stay as Python JSON files
  - Solve button → `POST /api/solve` → paint the trace
  - Validate `duration_min % 15 == 0` in the form and in the API
  - Corrupt `localStorage` resets to a demo instead of crashing
  - Partner: build a week from scratch; 10-row bug list; 8 realistic assignments
- Complete when: a new user can create, solve, refresh, and still see the week
  without the author's help.
- Status: [x] Complete per owner 2026-09-06 (40 tests, create/solve/refresh and
  corrupt-storage reset verified in the browser). Open: partner bug list.

## Revised scope — 2026-09-06

Phase 3 is complete per the project owner. Earlier partner tasks remain recorded
above as outstanding non-code work. The next work expands FlexWeek into an
account-based app and web app, with Daily Scheduler's calendar interactions and
Nocturne dark appearance. Visual redesign and auditing are deferred.

Daily Scheduler reference: `../Local-Schedule-Assistant`, specifically
`views.py`, `dialogs.py`, `mainwindow.py`, `core.py`, and `theme.py`.
Its Qt widgets need browser equivalents; the existing FlexWeek solver remains
the scheduling engine. `../LitSieve` currently contains no application source,
so an authentication comparison is unavailable.

The phases below replace the old Phase 4–7 scope. Dates are planning targets;
the larger scope makes the previous Oct 3 feature-freeze target obsolete.
The owner selected a separate desktop application plus web app. Windows/Linux
are provisional desktop targets, matching Daily Scheduler. A shared web UI in a
desktop shell is proposed; shell selection follows compatibility testing.

## Phase 4 — Accounts and shared persistence
- Registration, sign-in, sign-out, and session restoration.
- New accounts start with an empty week; account screens replace the demo picker.
- Server-side, account-owned schedules replace anonymous browser persistence.
- Explicit import of an existing browser week into the signed-in account;
  successful import is repeatable without duplicating blocks.
- Basic protection: password hashing, expiring/revocable sessions, protected
  schedule and solve endpoints, ownership checks, CSRF protection, login
  throttling, bounded input, and secure production cookies.
- Daily Scheduler's Nocturne palette and Slate alternative, with a saved theme
  preference; functional layout first, visual redesign later.
- Completion target: two accounts can independently create, solve, save, and
  reload their weeks; sign-out removes the previous user's schedule from view.
- Status: [x] Complete 2026-09-07. Account/editor/solve/reload/theme/sign-out
  and two-account isolation verified in the real Qt WebEngine at 1280px and
  390px, alongside API and frontend state tests.

## Phase 5 — Daily Scheduler interaction port and app delivery
- Separate desktop packaging plus browser delivery, sharing the web UI and
  account backend where practical; Windows/Linux are provisional targets.
- Day/week/month/year navigation, previous/next and Today controls.
- Drag empty space to create, drag to move, edge resize, click to edit,
  context-menu actions, and equivalent form/keyboard/touch controls.
- Colored activity categories, copy/paste, duplicate/copy day, undo/redo.
- Recurring activities with explicit single-occurrence versus series edits.
- Export/import and completion state, followed by reminders where supported.
- Calendar dates and week selection added before cross-week editing; the
  existing day-index solver receives an adapter for the selected week.
- Completion target: the same account's saved changes appear in both clients;
  edits preserve valid times and show save errors without discarding work.
- Build order for the remaining interaction port (2026-09-08): A calendar
  drag/resize/create/context menus (15-minute snap) → D recurring occurrence
  vs series edit → F reminders → B categories → E export/import and
  completion. Clipboard, duplicate-day, and undo/redo were deferred at this
  point in the plan. Daily Scheduler AI chat, Google Calendar OAuth and Qt
  custom painting remain outside the port.
- Status: [~] Linux desktop shell built and running 2026-09-07
  (`dist/FlexWeek/FlexWeek`), with popup/download fixes and preserved rebuilds.
  Dated weeks landed 2026-09-08: weeks keyed by calendar Monday, navigation,
  per-week client state, and a migration verified against the real desktop
  database. Slice A calendar interactions landed 2026-09-08 on
  `feat/phase5-calendar-interactions` (15-minute snap drag create/move/resize,
  select, double-click edit, context Edit/Delete, thin category colors).
  Slices D/F/B/E landed 2026-09-08: occurrence vs series edits, start reminders
  (web Notification + in-app toast; tray deferred), full category chips,
  export/import and completion. Undo/redo landed with student-experience Stage
  1 on 2026-09-13. Still open: Windows execution, copy-paste and duplicate day.

## Phase 6 — Scheduling explanations, later design and hardening
- Priority and energy controls, explanation panel, click reason to highlight.
  The model already has priority/energy fields; remaining behavior is checked
  against the actual solver when this slice begins.
- Missed-block rescheduling, change list, and slack indicators.
- Dedicated UI design revision after the interaction port.
- Later security hardening, recovery flows, accessibility review and audits.
- Deployment preparation: persistent database storage, backup/restore and
  client compatibility checks, account-based onboarding instructions.
- Completion target: a signed-in user creates a week, solves it, understands
  unplaced work, and recovers from a missed block in both clients.
- Status: [~] Scheduling explanations, slack indicators and per-occurrence
  missed-block recovery completed 2026-09-08. Design, hardening, recovery-flow
  expansion, audits and deployment preparation remain.

## Phase 7 — Pomodoro timers, alarms, Spotify and Daily Scheduler features
- Pomodoro focus timer attached to placed blocks: configurable work/break
  lengths, long-break cadence, pause/skip/reset, and alerts on phase changes;
  timer state stays client-side per session.
- Split long blocks into pomodoro work chunks with break blocks on the grid,
  as a manual action and optional solver pass (Daily Scheduler's split-block
  behavior without the AI chat).
- Focus session counts per task in the sidebar, rolling into the existing
  completion state.
- Spotify links on tasks and blocks that open in Spotify, with optional
  embedded playback where the platform allows it; playback control needs a
  Spotify Premium account and is best-effort per platform.
- Built-in alarms independent of schedule blocks: named alarm times with a
  popup that must be dismissed or snoozed. Web alarms fire only while the
  app is open; the desktop shell can alert in the background where the
  platform allows.
- Alarm sound selector: Daily Scheduler's built-in tones (chime, soft,
  bright, low, glass) or a linked Spotify track/playlist as the alarm sound;
  if Spotify is unreachable at fire time, fall back to the built-in tone.
- Live "Now / Next" status line and a current-time line in the day grid.
- Block-start notifications with lead time, sound toggle and Do Not Disturb
  override; system tray with quick-open on supported platforms, building on
  the Phase 5 reminders work.
- Free-gap visualization highlighting openings for unplaced work.
- Settings dialog consolidating theme, notifications, alarms, timer defaults,
  Spotify links and account actions.
- Completion target: a student starts a pomodoro from a placed block, sets an
  alarm that plays a linked Spotify playlist (tone fallback when Spotify is
  unreachable), and split chunks survive save/reload in both clients.
- Status: [~] Focus tools are implemented in current source and recorded as
  released in local history. Stage 1 completed the focus outcome and timer
  lifetime work. Reminder usability and device checks remain in Stages 5–7.

## Later (post-contest or only if Phase 5–7 are green)
- Stronger deadline-cluster insight on top of existing slack ok/tight/danger
  badges (no mental-health or IEP product claims).
- Simple assignment list or ICS file import — not live Canvas / Blackboard /
  Google Classroom OAuth, and not syllabus-photo ML for the contest demo.
- Rejected for CAC scope: syllabus OCR, LLM auto-reschedule chat, LMS API
  bridges, offline-first AI mobile shell.

## Phase 8 — Contest delivery (target Oct 18–25)
- Release bug fixes, app distribution and hosted web URL.
- README with account setup, both contributors and AI-assistance disclosure.
- Contest recording using an account-created schedule, plus submission form.
  This recording is separate from the removed product demo mode.
- Completion target: submission on Oct 25 evening, 2026.
- Status: [~] Normie first-open slice landed 2026-09-10 on
  `feat/normie-first-open`: Download for Windows / Linux labels, Linux tar.gz
  with README/icon/desktop entry and vendored libxcb-cursor, Windows zip with
  SmartScreen note, Create account first, first-week setup. v0.9.1
  (2026-09-11) reopens a page that stopped and fixed the AppImage checksum.
  v0.9.2 (2026-09-11) replaced the Windows zip, whose shortcut pointed at the
  build machine, with installers (Setup.exe per account, .msi for every
  account) that CI installs, opens and uninstalls. Hosted web URL and a hand
  check of the installers on a real PC remain.

## Student experience revision (2026-09-12)

The owner requested a staged plan combining the student-perspective review with
Daily Scheduler's useful features. Stages below are the next implementation
order, not a renumbering of Phases 1–8 or a promise to finish every addition before
the contest. Phase 8 delivery continues alongside this backlog. The contest
release can ship a verified subset; remaining stages continue after submission.

The original reviews used current source and the committed FlexWeek screenshots.
Stage 1 later received live-browser and Qt WebEngine walkthroughs. Broader
usability findings remain hypotheses to confirm in student trials. Existing
category colors, themes, dragging, Now/Next, reminders, tray support and export
are refinements, not new ports. The earlier first-slice proposal below is
historical.

Current scope mapping:
- Phase 5's remaining navigation, clipboard and duplicate-day work moves into
  Stages 2, 3 and 7. Stage 1 completed Undo/Redo; the previous deferral is
  superseded by this revision.
- Phase 6's remaining usability, recovery, accessibility and deployment work is
  organized into Stages 1, 2, 5, 6 and 7.
- Phase 7 focus tools are implemented in the current source and recorded as
  released in local history. Stage 1 completed the revised completion semantics;
  reminder usability and platform verification continue in Stages 5–7.
- Windows installers and theme redesign have progressed beyond the older phase
  entries. Actual Windows behavior, including the reported setup flicker, still
  needs physical-device verification.

### Stage 1. Make deadlines, focus and edits trustworthy
- [x] Separate exact deadline dates and times from 15-minute work placement.
  Support 11:59 p.m., next-week deadlines and work spanning Sunday to Monday.
  Preserve existing weekday deadlines through an explicit migration and adapter.
- [x] Separate focus minutes from assignment completion. At session end offer
  Finished, Need more time, and Take a break. Add “I need 30 more minutes.”
- [x] Keep the active timer while navigating between weeks. Make restart and
  reload behavior explicit, and avoid silently replacing an active session.
- [x] Add a quick focus timer without first placing an assignment.
- [x] Add visible Undo and keyboard undo/redo for create, edit, move, resize and
  delete. Treat a replan as one reversible operation. Preserve account isolation
  and revision conflicts when applying undo across saved weeks.
- [x] Move Clear week into a secondary menu. Make “Delete this day” versus
  “Delete all occurrences” explicit and provide recovery for either action.
- Complete when: a student enters next Tuesday at 11:59 p.m., works on it this
  week, finishes a timer without falsely completing the assignment, switches
  weeks without losing the timer, and reverses an accidental deletion or replan.
- Verification: deadline migration and Sunday/Monday boundary tests; timer state
  and completion tests; undo after reload/session loss/conflicting saves;
  browser and desktop walkthrough with save/reload and two-account isolation.
- Status: [x] Merged to `main` in PR #12 on 2026-09-16. Was complete locally 2026-09-13. The approved contract and spec
  reconciliation are included with the backend and frontend implementation.
  Verification passed with 139 frontend tests and 241 Python tests, including
  the Stage 1 Qt WebEngine walkthrough; the live browser covered assignment
  entry, next-week Continuing, Solve and the focus outcome prompt.

### Stage 2. Make today's work easy to find and add
- [x] Add a Today/Day agenda alongside Week view. Prioritize due soon, today's
  homework, total remaining planned work and a clear next action.
- [x] Make the phone layout a day agenda with a persistent Add action and visible
  edit, complete and focus controls. Keep Week view available for planning.
- [x] Simplify quick entry to title, due date and estimated time, with “Choose a
  time myself” and advanced scheduling options available when needed.
- [x] Replace “Solve” with student-facing wording such as “Plan my homework” or
  “Update my plan”; confirm wording in the student trial.
- [x] Reduce duplicated task lists and hide empty sections. Collapse successful
  placement explanations while keeping unplaced work and useful next actions
  visible. Express deadline room in understandable dates/days, not large hour counts.
- [x] Move import/export and duplicate account/theme actions out of primary
  navigation. Preserve the current light/dark visual system while simplifying it.
- [x] Add a daily workload summary by category, distinguishing scheduled time,
  recorded focus time and genuinely available time before the student's cutoff.
- Complete when: a new student can identify what is due tomorrow, add homework,
  plan it, start it and mark it finished without using a context menu or reading
  scheduling documentation. The same path is usable at phone and laptop widths.
- Verification: real browser/desktop walkthroughs at 390px and 1280px; keyboard,
  touch-target, screen-reader and both-theme checks; empty, busy and unplaced
  states. Record student task time and wrong turns before and after the change.
- Status: [x] Merged to `main` in PR #12 on 2026-09-16; developed on `feat/stage2-student-experience` (the same
  commits as `claude/stage2-frontend`). The contract is approved and spec.md
  carries Day view and `GET /api/day`; the status line in
  `docs/stage2-contract.md` said "proposed" until 2026-09-15 by mistake.
  Confirming the "Plan my homework" wording in a student trial is still open, as
  are the recorded task-time comparisons. Builds on Stage 1 deadline and
  completion behavior.

### Stage 3. Reuse routines and recover past work
- [ ] Port block copy/paste, duplicate, and copy-day actions with keyboard and
  visible controls. Preview destination conflicts instead of silently overlapping.
- [ ] Add “Copy routine to…” for selected days or next week. Default to fixed
  commitments and exclude completed homework and historical focus counts.
- [ ] Add reusable weekly routines with holiday, canceled-practice and differing
  school-day exceptions. Keep single-occurrence and series edits explicit.
- [ ] Review unfinished assignments when moving into a new week, retaining their
  identity, actual deadline and progress without duplicating them.
- [ ] Add account-owned restore points and a preview before restoring a schedule.
  Restore is distinct from short-term Undo and preserves a recovery point for the
  schedule being replaced. Expose local versus hosted backup location clearly.
- Complete when: a student prepares next week from a routine, changes one practice,
  carries unfinished homework forward once and restores an earlier schedule.
- Verification: cross-week identity and recurrence tests, collision previews,
  repeated-click/retry idempotency, maximum-size weeks, account isolation, stale
  saves and restore failure rollback; real save/reload in both clients.
- Status: [x] Merged to `main` in PR #12 on 2026-09-16; developed on `claude/stage3-frontend`. Not released: clipboard actions, fixed-only routines, unfinished-homework review
  and restore points, with Grok's account-owned persistence and routes. Real
  WebEngine walkthroughs cover save, apply, restore, a retried operation,
  reload, a second account and a 390px dark-theme carry-forward. Its Stage 1
  dependency is complete.

### Stage 4. Adapt plans to real student days
- [x] Add a direct “Running late” action with 15/30/60-minute choices and a preview
  of changed work. Build on missed-block recovery; fixed commitments and sleep
  remain protected, and work that no longer fits stays visibly unplaced.
- [x] Spread a project across dates before its deadline, with total effort and
  preferred session length. Keep sessions linked to one assignment and distinguish
  this from contiguous pomodoro splitting.
- [x] Add assignment notes, links and small checklists for larger projects.
- [x] Add protected downtime, commute/meal buffers and preferred study hours.
  Show the effect on available time rather than treating every gap as work time.
- [x] Improve priority/energy wording and actionable deadline-cluster explanations.
  Prefer concrete choices such as shorten a session, choose another day, or adjust
  availability; avoid implying that an impossible workload has been solved.
- Complete when: a student spreads four hours of project work across several days,
  runs 30 minutes late, and accepts a revised plan without losing tasks, moving
  fixed commitments or consuming protected downtime.
- Verification: pure solver fixtures for impossible and crowded schedules,
  deadline/session totals, missed_days recovery and cross-week persistence;
  atomic failure/retry tests and real preview/accept/undo walkthroughs. Retain the
  existing packed-fixture performance target and measure longer project planning.
- Status: [x] Merged to `main` in PR #12 on 2026-09-16; developed on `feat/stage4-adaptive-plans`. Accepting Running
  late stores a one-off locked interval. The contract is approved 2026-09-15 and
  spec.md lists the Stage 4 routes, availability windows and assignment fields.
  Depends on Stages 1 and 3. Borrows Daily Scheduler actions, not its
  AI tool execution or its behavior of dropping work that no longer fits.

### Stage 5. Make reminders and settings comfortable
- [x] Group settings into appearance, focus, notifications and account sections.
  Offer timer presets and explain any rounding before splitting work onto the grid.
- [~] Add Test reminder/Preview alert, volume control and an optional quiet
  end-of-block chime. The shared page is complete; desktop tray Test remains in
  the Qt shell follow-up.
- [x] Keep web-open and desktop-background reminder limits visible. Describe
  Spotify as a best-effort link with sound fallback, without promising playback.
- [~] Add an optional start-at-login preference for supported desktop platforms.
  The account preference is stored and editable; applying it at OS login remains
  in the Qt shell follow-up.
- [x] Add a collapsible/resizable sidebar and remember layout and preferred view.
- Complete when: a student previews an alert, chooses a comfortable volume,
  configures a timer without learning grid rules, and returns to a remembered
  layout. Disabled sounds remain silent and reminders do not duplicate.
- Verification: preference persistence, timer/split validation and duplicate-alert
  tests; physical sound, tray, startup, sleep/wake and notification checks on
  supported OSes. OS delivery limits remain separately recorded from test results.
- Status: [~] Merged to `main` in PR #12 on 2026-09-16; developed on
  `feat/stage5-comfort-frontend`. The contract is approved 2026-09-15 and
  spec.md lists the comfort fields and the three comfort routes. The source gate
  includes 207 frontend tests,
  243 backend tests and a real Stage 5 WebEngine walkthrough. The Qt shell still
  must apply start-at-login and expose tray Test; physical sound, tray, startup
  and sleep/wake checks remain platform work. No executable was built.

### Stage 6. Make account access and delivery dependable
- [x] Add account recovery appropriate to local and hosted modes, plus visible
  storage/sync status. Explain which account/database a student is using.
- [x] Provide a normal hosted-account path in both clients so a student can open
  the same saved week on another device. Keep local-to-hosted transfer explicit
  and previewed; automatic bidirectional/offline synchronization is separate scope.
- [~] Security/accessibility review run 2026-09-15 (own review plus GLM passes
  on backend security, month correctness and frontend a11y). Backend findings
  fixed on `grok/stage7-month-backend`; three minor accessibility items remain
  for the frontend (live regions for recovery status and transfer preview,
  focus after account deletion).
- Hosted Render deployment, Windows installer verification, Linux packaging/tray
  checks and Safari/iPhone compatibility: skipped by owner 2026-09-15.
- Complete when: a student understands where their week is stored, can recover
  access through the supported flow, and can use the same hosted account in the
  browser and desktop without data loss or exposure to another account.
- Verification: recovery abuse/expiry/revocation tests, ownership and CSRF checks,
  and cross-client revision conflicts. Hosted backup drills, installer smoke
  checks and physical-device evidence are out of this slice.
- Status: [~] Merged to `main` in PR #12 on 2026-09-16; developed on
  `feat/stage6-access-frontend`, with transfer size limits reconciled on
  `grok/stage6-transfer-limit`. The Stage 6 contract is approved 2026-09-15 and
  recorded in `spec.md`. Export and import share the 256 KiB write cap. Hosted
  deployment, installers and physical Safari/iPhone checks are skipped. The
  security/accessibility review remains. No executable was built.

### Stage 7. Add longer-range navigation and validate the student experience
- [x] Add Month view for deadlines and projects with date-to-Day navigation.
  The shared browser and desktop frontend reads `GET /api/month` without
  loading month summaries into editable week state. Year view remains optional
  later work.
- [ ] Run student trials covering first use, adding several assignments, an
  impossible workload, a missed session, next-week reuse and recovery from an edit.
- [ ] Compare completion rates, task time and wrong turns with the initial UI.
  Address observed clutter and confusion before adding more permanent controls.
- [ ] Extend automated coverage with each implemented stage and run
  `fwtest gate` for the resulting release. Keep real UI,
  physical-device and notification evidence separate from automated test counts.
- [ ] Complete PR review for each implementation slice before calling the slice
  ready to merge; record unresolved findings and verification limitations.
- Complete when: students can complete the core planning/recovery paths without
  author assistance, the release gate passes, and device-specific gaps are either
  resolved or explicitly reflected in the supported release scope.
- Verification: month/year boundary and date-navigation tests; repeat the same
  student scenarios on the baseline and revised UI; record observed completion,
  assistance needed, device/browser and screenshots alongside release-gate output.
- Status: [~] Merged to `main` in PR #12 on 2026-09-16; developed on
  `feat/stage7-month-frontend` and integrated with Grok's audit fixes from
  `grok/stage7-month-backend`. `docs/stage7-contract.md` is approved 2026-09-15
  with a planned-work amendment: Month shows planned and completed study time,
  pins a session only to a date that is certain, and reports work with several
  possible days as an unscheduled total. spec.md lists `GET /api/month`. Year
  view, student trials, measured comparisons and PR review remain. The full
  source gate passes 242 frontend and 364 Python tests, including the real Qt
  WebEngine Month walkthrough at desktop and phone widths. No executable was
  built.

### Scope and contract follow-up

The existing pure solver, account ownership, Monday-keyed weeks, missed_days
recovery and 15-minute placement remain the foundation for these stages. Stage
1's exact deadlines, cross-week assignment identity, timer lifetime and undo
semantics are reconciled with spec.md. Routine exceptions, restore semantics and
account recovery still need contract changes before their implementation.

AI chat/Ollama, Google Calendar OAuth, LMS bridges, syllabus OCR and Qt custom
painting remain outside this plan. More category chips, a social feed, streaks and
productivity scores are not proposed. Existing alarms, Spotify links and themes
receive targeted improvements rather than a wholesale replacement.

## Native Python desktop (2026-09-17)

Jonathan chose a full Python desktop: Qt widgets, no WebEngine, no JavaScript.
The existing FastAPI app still owns accounts and the database on a loopback
port; the browser page was optional then and is gone now (see "Web client
retired" below). Plan: `docs/native-python-migration.md`.
Launch: `python -m desktop.main` (native widgets). `python -m desktop.native`
is the same entry.

- Unit 1 foundation: [x] 2026-09-17. Register, recovery codes, login, dated
  week, fixed time, homework, Solve, atomic save, restart, isolation, stale
  replies, 409 drafts, no WebEngine import.
- Unit 2 calendar and homework parity: [x] 2026-09-17. Day, Month, drag
  create/move/resize, series refuse, occurrence vs series, type chips, exact
  due times, notes/links/checklist, completion, W/D/M and Delete.
- Unit 3 planning and reuse: [x] 2026-09-17. Undo/redo, internal clipboard and
  collision previews, locked-only routines, unfinished homework, missed
  recovery, running late, spread, availability. Native session is one week at
  a time (undo of another week is refused).
- Unit 4 focus and preferences: [x] 2026-09-17. Timers, once-only credit, packs,
  device-only look knobs, reminders, alarms/snooze, Spotify, tray.
  Layouts (2026-09-18): six main views and two day screens with per-design
  options, device-only, native only; see Amendment C of the appearance contract.
- Unit 5 account recovery and files: [x] 2026-09-17. Forgotten-password recovery,
  password/code replacement, deletion, week/day files, restore points, transfer.
- Unit 6 retirement: [x] 2026-09-17. Native is the default launcher. Smoke is
  native widgets. The Chromium shell is deleted.

Complete when unit 6 has switched the normal launcher and packaging smoke uses
native widgets. Executables stay unbuilt until Jonathan asks. Packaging for
0.12.0 compiles `desktop/main.py` and the native package, so the Windows
and Linux downloads are the native client.

## Release polish (2026-09-16): 0.10.1, then 0.11

v0.10.0 is published, so classmates can install FlexWeek and hit its rough
edges. The owner's plan of 2026-09-16 splits the response into two releases.
0.10.1 is a hotfix: only the things that stop or mislead a first-time student.
0.11 is the polish release: nothing flashes or looks ignored, motion is added
where it explains a change, and a student can choose how the app looks. Neither
release adds a stage. Stage 7's open trials and Phase 8 delivery continue
alongside them.

### 0.10.1 — hotfix, ship first

Shipped. Every `frontend/` path below points into the web client, which was
retired on 2026-09-19; the findings are kept as written because that is where
they were found, not moved onto desktop files they were never about.

- **P0. The assignment name field loses and duplicates letters.** Typing fast
  into the setup step 3 name box (`setup-homework-title`) and the Add homework
  dialog (`f-title`, `frontend/editor.js:287`) drops characters; one report
  ended up with a single "H". Reproduce on the packaged build before changing
  anything: no code in `frontend/setup.js` or `frontend/editor.js` rebuilds
  either input on a keystroke today, so the cause is not yet identified. Open
  suspects are the 30-second live and reminder ticks
  (`frontend/app.js:2690-2691`) landing mid-word, and Qt WebEngine's own text
  input path. Whatever the cause, the fix must never rebuild the element or
  reassign its value while it holds focus. Needs a node test that types a long
  name one character at a time into both fields and asserts the whole string
  survives.
- **P0. Running late has to show that it did something.** Every refusal inside
  `openRunningLate` (`frontend/adapt.js:172-199`) only writes to the status
  line, which a student does not look at, so the button reads as dead. On the
  other side, accepting a preview calls `clearSolveResult()`, wiping the moves
  at the moment they matter. Wanted: the preview lists what moves, accepting
  leaves a visible locked "Running late" block on the grid, and a toast states
  the outcome — including "nothing moved" when no work shifted. A quiet click
  is the bug, not a nuance.
- **P1. The week is too dense to read.** Thin the sidebar, and rename "Why the
  rest fit" (`frontend/app.js:1950`) to something a 15-year-old reads without
  stopping. Day view stays the plain view; it gets no new controls here.
- **P1. A nearly empty month looks broken.** Make the date numbers larger
  (`frontend/styles.css:654-656`, cells built in `frontend/month.js:176-186`)
  and add one line of copy — along the lines of "only this is due so far" — so
  a month holding one assignment reads as correct rather than failed. Build it
  on the existing `#month-unscheduled` note rather than a new region.
- **P2. Setup should not name the sport for the student.** The placeholder on
  `frontend/index.html:284` is "Sports", and students accept it as the name.
  Use an example instead, such as "Soccer, band…". The category label in
  `frontend/app.js:19` stays "Sports".
- Out of 0.10.1: new animation, the appearance workshop, Chromebook and hosted
  web, Year view.
- Complete when: a classmate installs 0.10.1, types a real assignment name that
  survives intact, presses Running late and can see what changed, and opens
  Month without asking whether the app is broken.
- Verification: node tests for fast typing in both name fields and for the
  Running late outcome message; a real Qt WebEngine walkthrough of setup step 3,
  Running late and a one-assignment month at desktop and phone widths;
  `.venv/bin/python scripts/verify.py` green before the tag.
- Status: [~] Code landed 2026-09-16 on `fix/0-10-1-hotfix`. Running late, the
  sparse-month line, the larger date numbers, the "See the rest of your plan"
  rename, the sport placeholder and the week-chrome regroup are all done, with
  ten new node tests and the gate green at 253 frontend and 365 Python tests.
  The P0 name field is only half closed: a search of every frontend script
  found nothing that rewrites either name box while you type, and the Qt shell
  does not touch key input, so the reported letter loss has no cause in this
  code. What landed is a guard against re-opening setup over a half-typed name
  plus regression tests that type a whole name one character at a time while
  the timers and renders fire. Closed unfixed on 2026-09-19: the field, the
  timers and the WebEngine text path it was reported against were all part of
  the web client, which is retired. Whether fast typing drops characters in the
  Qt dialogs is a separate question and has not been reported.

### 0.11 — seamless, motion and appearance

**Seamless.** Solve, Spread and Running late each show a wait state: no blank
flash while the request is out, and no silent result when the honest answer is
"nothing changed". Moving between Week, Day and Month keeps the selected date.
Adding work from a category chip stays a single gesture.

**Motion, only where it explains something.** Fade or slide on a view switch,
new blocks popping in after Solve, dialogs opening, and the Running late block
drawing itself onto the grid. Never animate `backdrop-filter` — it flickers on
Windows. Honour `prefers-reduced-motion` everywhere.

**Appearance: packs first, then a Customize submenu.**
- One tap picks a theme pack: System, Light frost, Dark frost, plus Nocturne
  and Slate while those still ship (now `desktop/native/look.py`). A pack sets
  the background, the chrome, the accent and the default motion level.
- "Customize…" stays collapsed and holds three things: accent colour, an
  optional "use the accent for category chips", and Motion set to Off, Normal
  or Extra. Extra means pop-in plus the view slide. Off behaves exactly like
  `prefers-reduced-motion` and is the safe setting on Windows. No blur sliders
  and no per-widget curves.
- Choices persist on the account, next to the existing theme preference.
- On phones the menu offers the pack and motion only; the submenu must not take
  over the screen.
- Contest cap: packs, accent, and Off/Normal/Extra. A full per-surface colour
  picker is post-CAC work unless the owner says otherwise.

**P2. Account copy.** Soften `frontend/access.js:45-46` so "It does not sync
automatically" does not read as a defect. Storing the week on this device is
the design, and the sentence should say so. Closed 2026-09-19: the sentence was
browser-only and went with the web client. The desktop account dialog never
carried it.

- Complete when: a student picks a pack in one tap, sets Motion to Off and sees
  no animation anywhere, and both choices survive sign-out and a reinstall;
  Solve, Spread and Running late never flash blank and never look ignored.
- Verification: desktop tests for the wait states, for date continuity across
  Week/Day/Month, and for the persisted pack, accent and motion level. Neither
  the `backdrop-filter` flicker hand-check nor the `prefers-reduced-motion` pass
  applies any more: both were about the browser client's CSS, and Qt widgets have
  no `backdrop-filter` and no such media query. The Motion setting is the app's
  own.
- Status: [~] Code for 0.11.0 is tagged. Seamless, chip-opens-Add, packs,
  Customize and account motion shipped. The Windows flicker hand-check, the P2
  account copy and the `prefers-reduced-motion` pass all closed with
  the web client on 2026-09-19: all three were browser-only.

### Looks and knobs (owner request, 2026-09-17)

After 0.11.0 the owner asked for more control over the interface and for
presets that look drastically different from the frost family. The plan is one
idea: a preset is a bundle of knob values plus a palette, and Customize edits
the same knobs, so more presets and more control are the same work.

- Knobs, each one attribute on `<html>`, one control, one field, one test:
  surface, corners, depth, font, blocks, density, text. Accent and motion
  already exist on the account.
- Presets: Terminal first as the proof, then Poster, Ink and High contrast for
  the contest, Paper and Pastel after, subject to the owner's choice.
- Complete when: the owner has picked the presets from a real example, the
  seven fields and the new pack values are approved in Amendment A of
  `docs/stage8-appearance-contract.md`, the knobs persist on the account, and
  every preset palette passes the same-tokens, AA and accent-distance audits.
- Status: [~] Architecture and all six presets landed device-only on
  `feat/native-python` (2026-09-18): Terminal, Poster, Ink, High contrast, then
  Paper and Pastel, the two soft looks, in both clients. Preset is folded into
  Look. A look keeps knobs set by hand. High contrast is menu-only. Settings
  still says the look stays on this computer.
  Approval of the `look_*` fields is still required before anything is saved
  to the account.

## Web client retired (2026-09-19)

The owner chose one client. FlexWeek had been two over one backend: the Qt
widgets desktop app, and a vanilla-JS browser client kept at parity by hand.
Every feature landed twice, and the features/functions audit of 2026-09-19
found that most of the app's half-built controls were the desktop half of a
pair whose web half worked.

Removed: `frontend/` (11,677 lines of JS, CSS and HTML; 6,982 lines of Node
tests), the static mount and `serve_frontend`, the JavaScript steps in the
gate, Node from CI and from CodeQL's languages, and `frontend` as bundle data
in both installers. `backend/app.py` answers the API and 404s everything else.
`logo.png` and `favicon.png` moved to `desktop/assets/`. `--web-only` became
`--backend-only`.

- Consequence, accepted by the owner: there is no browser way in. Anyone trying
  FlexWeek, including Congressional App Challenge judges, installs the desktop
  build.
- Two parity tests died with their counterpart: native colours against
  `styles.css`, and category marks against `app.js`. The colours live in
  `look.py` and `calendar.py` either way, and the readability the web audit was
  for is checked directly across all 700 looks.
- `spec.md` updated with owner approval: User Experience, the language list,
  the file map, and the validation commands.
- Open: nothing from this work. Items above that were browser-only are marked
  closed where they stand.

## First implementation slice — approved 2026-09-06

### Goal and user stories
1. As a student, I want an account so my schedule belongs to me across clients.
2. As a student, I want an empty starting week and reliable saves so I can plan
   my own work without sample schedules replacing it.
3. As a student, I want Daily Scheduler's dark theme so the planner feels familiar.

### Acceptance criteria
1. Given a new visitor, when they open FlexWeek, then they see sign-in and
   registration; protected APIs return 401 without a valid session.
2. Given valid registration details, when registration succeeds, then the
   student enters an empty week with clear add-block and add-task actions.
3. Given an existing account or invalid/oversized input, when registration is
   submitted, then a safe error is shown and no partial account is created.
4. Given a signed-in account, when a valid week is saved and the page reloads,
   then the same week is returned from that account's server-side storage.
5. Given two accounts, when either reads, saves, imports, or solves a week,
   then the other account's stored data cannot be accessed or overwritten.
6. Given expired or revoked credentials, when a request is made, then it fails
   with 401 and the client returns to sign-in without exposing cached data.
7. Given a save in another tab, when a stale save arrives, then it returns 409
   and offers reload/retry rather than silently overwriting newer work.
8. Given an old browser week, when its owner chooses import, then it is validated
   and saved once; retries do not duplicate blocks. Corrupt input shows a
   recovery message and never loads a demo or overwrites a saved account week.
9. Given the theme setting, when Nocturne or Slate is selected and reloaded,
   then the selected theme persists for that account.
10. Given an empty week or invalid duration, when Solve is pressed, then empty
    input returns an empty trace and non-15-minute durations return validation
    errors; existing overlap, sleep, deadline, and timeout behavior is retained.
11. Given a timeout or failed save, when the response fails, then the client
    preserves unsaved edits and clearly distinguishes them from saved work.

### Data and interface impact
- SQLite tables: users (unique normalized username, password hash),
  sessions (hashed opaque token, user, expiry), weeks (user, blocks JSON,
  revision), and preferences (user, theme). Foreign keys and unique ownership
  constraints link data; writes are transactional. No database exists today.
- Initial scope is one current week per account using the existing `TimeBlock`
  payload. Dated multi-week storage is a separate Phase 5 migration.
- Endpoints: POST `/api/auth/register`, `/api/auth/login`,
  `/api/auth/logout`; GET `/api/auth/me`; GET/PUT `/api/week`;
  GET/PUT `/api/preferences`. Saves carry an expected revision.
- POST `/api/solve` keeps its current payload/trace shape but requires a session.
  Demo endpoints and demo-loading UI leave the product; seed JSON can remain
  solely as test fixtures.
- Passwords use a maintained password-hashing implementation; sessions use
  HttpOnly, SameSite cookies with Secure in production and server revocation.
  CSRF/origin checks protect writes; SQL queries are parameterized. No password,
  token, or schedule contents enter logs. Python/OpenSSL scrypt provides password
  hashing without a new dependency; existing direct dependencies are pinned.
- Screens: register/login, account identity/logout, empty planner, theme control,
  import prompt, loading/saving/saved/error states. No background jobs initially;
  expired sessions are rejected at request time and cleaned periodically.
- Production storage includes the account database and backups; account deletion
  and retention policy are part of the later hardening scope before public release.

### Edge cases
- Empty and oversized usernames/passwords/week payloads; duplicate usernames;
  double-submit registration and import; atomic rollback on database failure.
- Expired session during edits, logout in another tab, cross-account browser
  reuse, stale revisions, offline/retry and server restart persistence.
- Existing anonymous data stays local until explicit import; invalid data is
  recoverable without sample-data fallback. Private API responses are not cached
  by a future service worker.
- Existing local day-index/time model stays intact for this slice. Calendar-date,
  midnight, recurrence, and daylight-saving boundaries belong to Phase 5's
  date-model work, before month/year navigation or cross-week drag is shipped.

### Deferred scope and open decisions
- First slice excludes desktop packaging, drag editing, recurrence, reminders,
  advanced security, audits, visual redesign, performance rewrites and unrelated
  refactors. These first-slice exclusions do not remove later roadmap work.
- AI chat/Ollama and Google Calendar OAuth are not part of the proposed port;
  native mobile store builds, payments and shared team schedules remain outside
  the proposed scope.
- Confirmed: separate desktop app plus web app (owner, 2026-09-06); provisional
  Windows/Linux targets match Daily Scheduler.
- Approved: username/password accounts and SQLite on the existing Python/FastAPI
  backend, with no demo mode; spec.md updated to match.
- Desktop shell recommendation (2026-09-07): PySide6 QWebEngineView loading the
  hosted origin; see DESKTOP.md. Installer implementation remains Phase 5.

## Spec reconciliation — 2026-09-07
- Accounts, storage, installed-app delivery, demo-free onboarding and expanded
  interactions replace the old explicit exclusions.
- spec.md now describes Pydantic models, HH:MM/day indices, the working solver
  and authenticated API. Demo endpoints have been removed.
- requirements.txt now pins the installed direct dependency versions listed
  in spec.md, including Pydantic, Ruff and mypy.
