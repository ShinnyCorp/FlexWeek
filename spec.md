# FlexWeek

## Problem
Students plan by guilt, not by constraints: a to-do list has no idea that school
runs 08:00–14:30, practice takes the evening, and a three-hour paper is due
tomorrow. FlexWeek takes a student's fixed week (school, sport, commute, sleep)
plus their assignments, places the assignments in the gaps with a constraint
solver, and explains in plain English every time something could not be placed
or had to move. Built as a Congressional App Challenge 2026 entry. Working title
was *Reslot*; the public name is **FlexWeek**. The original Sep 6 contest brief
is archived in `docs/cac-build-plan.md`. Living schedule and remaining work live
in `roadmap.md`.

## Intended Users
High-school students using individual accounts through the FlexWeek desktop app
for Windows and Linux. New accounts start with an empty week; no anonymous demo
mode or sample-data fallback. Secondary audience: CAC judges, who create an
account and can inspect the GitHub repository.

Scope revision approved 2026-09-06: accounts, shared persistence, and light and
dark themes first. Desktop delivery, calendar interaction, cascade,
slack, focus timers and alarms later shipped under that approval. Visual
redesign and audits remain deferred. The previous Oct 3 feature freeze is
superseded by the expanded roadmap.

## Required Behavior
Contract for the finished app:

- A week is a set of `TimeBlock`s: `locked` blocks have a fixed `start`;
  `flexible` blocks are work sessions with a `duration_min` that the solver
  places.
- Homework is an account-owned assignment that outlives any one week: `title`,
  an exact `due` (naive local `YYYY-MM-DDTHH:MM`, any minute), `estimate_min`,
  progress (`focus_minutes`, `focus_sessions`) and completion (`completed`,
  `completed_at`), with its own revision. A work session points at its
  assignment with `assignment_id` and takes its title, deadline, priority,
  energy, course, category and Spotify link from it. One assignment can have
  sessions in several weeks. Details live in `docs/stage1-contract.md`.
- The solver stays day-index pure. Before solving, the backend turns an
  assignment's `due` into the week's bound: a due time inside the week bounds
  that day, a due date after the week adds no bound, and a due date before the
  week leaves the session unplaced with `DEADLINE_MISS`.
- Focus minutes never complete anything. Finishing an assignment, or adding time
  to it, is the student's explicit choice when a session ends.
- Old weekday deadlines (`latest`, `"Thursday 21:00"` or `"21:00"`) migrate once
  into assignments on start and are still accepted on saves. A save that uses
  them never changes an existing assignment.
- Optional block fields the API and storage keep: `assignment_id`, `category`,
  `completed`, `completed_day`, `missed_days`, `spotify_url`, `focus_sessions`,
  `focus_minutes`, and pomodoro split fields (`pomodoro_parent_id`,
  `pomodoro_role`, `pomodoro_index`). `completed_day` is only valid on a
  completed flexible block that has a `start` on one of its candidate days.
  `missed_days` is only valid on a locked block, and every missed day must be one
  of that block's `days`.
- A week has unique block ids. A pomodoro parent cannot be stored in the same
  week as the chunks split from it.
- The solver places every flexible block on the 15-minute grid (Mon–Sun,
  00:00–24:00), inside the account's work windows, without overlapping any
  locked block or any other placed block. A block at any minute takes every
  quarter hour it touches: one from 17:37 to 18:22 leaves no homework between
  17:30 and 18:30.
- Search order respects priority (1 = test, 2 = quiz, 3 = homework,
  4 = reading); a higher-priority block wins a contested slot.
- Energy windows (`high` / `medium` / `low`) are a soft preference on value
  order, never a hard constraint.
- Every unplaced block and every move carries a machine reason code, rendered as
  a plain-English sentence: `LOCKED_OVERLAP`, `DEADLINE_MISS`, `NO_SLOT_LEFT`,
  `PRIORITY_PREEMPT`, `ENERGY_MISMATCH` (soft), `SLEEP_GUARD`,
  `RESHUFFLE_AFTER_MISS`.
- Work windows bound where the planner places homework. Until the student sets
  any, the whole day is open, and the planner ranks the night (23:00–06:00)
  last, so it is used only when the rest of the day is full. Placing a block by
  hand at any hour is always allowed.
- Solving is capped at 150 ms. On timeout the app returns the best partial
  placement plus reasons for what is unplaced. It never hangs and never
  returns nothing.
- Cascade: marking a locked occurrence as missed re-solves remaining flexible
  blocks and lists the resulting diffs as moves. Sleep stays intact. Details
  live in `docs/scheduling-recovery.md`.
- Plans are stored: an accepted plan saves each session's start and day on the
  week. After any edit, only homework whose time no longer works (a fixed
  commitment over it, a deadline moved earlier, or outside planning hours)
  loses its time. The app names it, says why and offers "Find a new time" for
  just that work. Every other session keeps its time.
- Deadline slack is shown as ok / tight / danger.
- Edge cases: an unsolvable week returns `complete: false` with reasons rather
  than an error; a homework estimate that is not a positive multiple of 15 is
  rejected in both the app's editor and the API, while a block's start and
  length may be any minute. Files exported by earlier builds, including
  the retired browser client, import into a signed-in account; invalid data
  stays untouched and never loads a demo.
- Copy, paste, duplicate and copy-day use an in-memory clipboard that clears on
  sign-out, session expiry and account deletion. Fixed-time conflicts are previewed and must be resolved;
  pasted homework keeps the same assignment identity, stays flexible and never
  exceeds its remaining unplanned minutes.
- Account-owned weekly routines contain fixed commitments only. Applying one
  to a Monday-keyed destination week previews every occurrence and lets the
  student omit or adjust one-week exceptions without changing the routine.
- A later week reviews unfinished homework using the original assignment ID,
  exact deadline and progress. Repeated planning and request retries cannot
  duplicate or over-plan it.
- Account-owned restore points snapshot weeks and assignments. Clear week,
  routine application and restore preserve the replaced schedule first; a
  stale restore preview returns 409 and no failure stores partial state. The UI
  labels backups as local-device or hosted-server data.
- New accounts receive eight one-time recovery codes, shown once. A forgotten
  password is recovered with a username, an unused code and a new password, not
  email. Signed-in students can replace leftover codes, change the password or
  delete the account; those writes need the current password. Delete removes
  every row for that user. The username may be registered again.
- `GET /api/storage-info` reports local or hosted `mode`, a student-facing
  `label`, the signed-in `username`, the public `origin` and
  `transfer_limit_bytes` (262144). It never returns a filesystem path.
- Local-to-hosted transfer is a password-gated format-3 export and a previewed
  import of weeks, assignments, preferences and routines. Import takes a Stage 3
  restore point of the destination weeks and assignments first. Automatic
  bidirectional or offline sync is out of scope. Export returns 413 when the
  compact import apply envelope would exceed the 256 KiB write cap.
- Day and Week show the whole day, 00:00 to 24:00. Hours scroll, and the
  student can zoom: Ctrl and the wheel, Ctrl with =, - and 0, or two buttons
  beside the hours. Each surface's level is remembered per device in the look
  file. Every design draws its own Day and Week on one shared gesture engine
  (`docs/0.15/architecture.md`): a block moves with the pointer in the
  student's step, 5 minutes or 15 (the `drag_step_min` preference, 5 unless
  chosen otherwise in setup or Settings > Planning), with its times beside it
  while held; a typed time keeps any minute; an end drags to resize;
  empty time drags to create; overlaps are allowed, drawn side by side and
  named; a block moved by hand is pinned; a refusal leaves the block where it
  was and says why before it is let go.
- Day view lists one date: homework due soon, that day's work sessions and fixed
  commitments, one next action, and a workload summary that separates scheduled
  time (work that has a time), recorded focus time and time still free before
  midnight, with a breakdown by category. Due soon is open homework due that day or the next, plus anything
  already overdue. Below 800px Day is the default view and Week stays one control
  away. Quick Add homework asks only for title, due date and estimated time, with
  "Choose a time myself" for anything more. "Plan my homework" places only
  homework that has no time yet and keeps the times already planned; "Replan
  all my homework", under More and in the plan review, plans every unfinished
  session again. The `planning_style` preference says when new homework gets a
  time: `suggest` (the default) waits for Plan my homework, `auto` plans each
  new homework as it is saved, in the same Undo step, and `manual` leaves it to
  the student, with the button reading Suggest times. Homework dragged onto a
  time, or given one with Choose a time, is `pinned`: every plan, Replan all
  included, keeps it where the student put it, even beside a fixed block. Details live
  in `docs/stage2-contract.md`.
- Running late is a solve preview of a 15, 30 or 60 minute delay from a
  15-minute cutoff on one day of the open week. Fixed commitments and sleep stay
  put, and work that no longer fits stays unplaced rather than being dropped.
  Accepting it stores one locked "Running late" block and the previewed times in
  one save through `/api/changes`, without planning again, so reload and
  one-step Undo act on a real saved change. Details
  live in `docs/stage4-contract.md`.
- Spreading a project previews flexible sessions of a chosen length across the
  dates from a start date through the due date. It writes nothing until the
  student confirms, and each session is an ordinary session of the same
  assignment, not a pomodoro split.
- An assignment carries optional `notes` (at most 4000 characters), up to 20
  `links` (`http` or `https` only) and a checklist of up to 40 items. Ticking
  checklist items never completes the assignment, and focus minutes still
  complete nothing.
- Preferences carry availability: up to 21 `protected` windows (downtime,
  commute or meal), up to 21 `work_windows` (the hours the planner may use,
  set in setup and in Settings; `work_windows_defaulted` marks an account that
  has not chosen any, whose whole day is open), up to 21 soft `study_windows`
  (Settings only), and an optional `day_cutoff` that flexible work must finish
  by. A study window may name one `subject`:
  the solver tries a session in its own subject's window first, then in a
  window for any subject, then anywhere else. `POST /api/solve` loads them for
  the signed-in account, so the client never re-sends occupancy.
- Comfort preferences persist per account: `alert_volume` (0-100), `end_chime`,
  `tray_notifications`, `start_at_login`, `preferred_view` (`week` or `day`),
  `sidebar_collapsed` and `sidebar_width_px` (200-640). One `alarm_tone`
  (`chime`, `soft`, `bright`, `low`, `glass`, or `spotify`, which plays
  `default_spotify_url` in the student's own Spotify app, for alarms only)
  rings reminders, the end of a focus session and new alarms. An alarm is never
  silent: until Spotify is heard playing, the tone rings. `setup` records where first-run setup stands: its
  `step`, and `finished_at` once it is finished or skipped. Defaults stay omitted
  from stored JSON so older clients keep working, and timer rounding to the
  15-minute grid is previewed and explained rather than silent. Details live in
  `docs/stage5-contract.md`.
- Appearance preferences persist per account beside `theme`: `theme_pack`
  (`system`, `light-frost`, `dark-frost`, `nocturne`, `slate`), `accent`
  (`default`, `sky`, `gold`, `sea`, `sand`), `accent_chips`, and `motion`
  (`off`, `normal`, `extra`, `reduce`; `extra` is shown as More). Omitted pack
  leaves `theme` as today's light/dark/system choice. A set pack must be stored
  with `theme` on the matching axis (`slate` for `light-frost` and `slate`,
  `nocturne` for `dark-frost` and `nocturne`). Omitted `motion` means the
  account has never stored a level, and the app runs at the look's own: Reduce
  for Paper, a custom look's own level, and Normal for every other look. An
  explicit `"normal"` stays on the wire so a second device cannot treat it as
  unset. Details live in `docs/stage8-appearance-contract.md`, which predates
  `reduce`.
- The rest of the look is kept on each computer, in the look file
  (`flexweek-look.json` in the app's data folder), and never sent to the
  account: a preset (`high-contrast`, `paper`, `ink`, `terminal`, `poster`,
  `pastel`) or none, the knobs moved by hand, a look of the student's own, the
  saved looks, and the designs with their options. The knobs are `surface`
  (`flat`, `layered`), `corners` (`soft`, `sharp`, `rounded`), `depth`
  (`none`, `soft`, `bold`), `font` (`sans`, `serif`, `mono`), `blocks`
  (`edge`, `filled`, `outline`), `density` (`comfortable`, `compact`) and
  `text` (`small`, `normal`, `large`). 0.16's names (`frost`, `round`, `pill`,
  `flat` for depth, `hard`, `outlined`) load as today's.
- A custom look (`custom`) is a `base`, one of `light`, `dark`, `system`,
  `high-contrast`, `slate`, `nocturne`, `paper`, `ink`, `terminal`, `poster`
  or `pastel`, and what was changed on it: `accent` (a swatch or a `#rrggbb`
  colour), `colours` (`page`, `card`, `text`, `line`, `muted`), `categories`
  (each a `hue` on the category family or an exact `colour`), `corners` (0 to
  16 pixels), `spacing`, `shadows`, `body_font` and `heading_font` (`sans`,
  `serif`, `mono`), `text_scale` (0.9 to 1.3), `blocks`, `edge_width` (2 to 6
  pixels), `show_times`, `show_lengths`, `hour_lines` (`none`, `faint`,
  `clear`), `today_highlight`, `now_line` (`accent`, `text`) and `motion`.
  While one is worn it sets the accent and every knob. `saved_looks` holds
  custom looks by `name`: at most 40 letters, unique without regard to case,
  and never the name of a built-in look. A look is shared as a JSON file of
  kind `"FlexWeek look"`, version 1, at most 64 KiB; a setting the file does
  not know is left out and named, and a file from a newer FlexWeek is refused.
  `desktop/native/custom_look.py` and `look.py` are the reference.
- Month view shows one calendar month of deadlines, projects, overdue homework
  and study time, planned and completed, and any date opens Day view. A session
  pins to a date only when that date is certain: the day it was completed, or
  the day its saved plan gives it. Open work with no time yet is reported as an
  unscheduled total instead of being painted across its candidate days. Each
  date lists its timed blocks as chips that start with their time ("09:00
  History essay"), from the month reply's per-date `blocks`; the open week, and
  any week left with unsaved changes, are drawn from what the student has now.
  A chip can be dragged to another visible date and keeps its time; one
  occurrence of a repeating block moves alone; a drop the deadline refuses
  leaves the chip where it was and says why. Homework due that day is listed
  first. Details live in `docs/stage7-contract.md`.

## User Experience
Native desktop app, one window, designed at 1280px and usable down to 800px.
Under 1150px the layouts switch to a narrow arrangement: Today's app's rail
folds into one line above the hours, and blocks show their names without their
times. PySide6 Qt widgets over a
FastAPI backend started in-process on a loopback port. **No HTML, CSS or
JavaScript, no npm, no build step, no framework.** There is no browser client:
the web app was retired in September 2026 and `frontend/` deleted.

First paint with no session is Sign in, with creating an account offered as a
line of small print that switches the same card over. It says "Welcome to
FlexWeek" until someone has signed in on this computer, and "Welcome back"
after. The card offers "Keep me
signed in on this computer", on by default. A kept session opens the week at
the next launch until the server ends it (seven days after sign-in) or the
student logs out.
A new account must acknowledge its eight recovery codes, shown in Inter with
figures of one width, with Copy and Save…, then goes to first-run setup, one page at a time: a
starting style or its own look (the standard styles first, the rest under
"Experimental styles"), the week (school
days and hours, activities on their own days, and No homework after), how
homework gets a time, reminders and the alarm sound, up to three first
homework, and a summary. Every page can be skipped and is kept when the
student leaves it, so a quit resumes on the same page. Finishing or skipping is
stored in `setup`, and setup never returns unless the student picks Run setup
again in Settings. School hours stays for later under Add, in a dialog of its
own that asks the days and the times, as setup does; no day ticked takes School
off the calendar.

The top bar is the week's arrows, Today and the title on the left; on the right, Day,
Week, Month and My day as one segmented control, then Add, the one filled
button (a click adds homework; its arrow offers a fixed time, School hours and
the type the next drag makes), Plan my homework, More and the gear. Ctrl+K opens
a command bar that adds, goes to any view or opens any homework by typing a few
letters of it. Today's app has a rail left of Day and Week: a small month that
folds away, what is next, Not placed yet, and the homework a focus timer can
start on. Day lists the day beside its hours. Everything FlexWeek
says after an action (a move, a plan, a deletion, a reminder) is one toast at
the bottom right of the page, with Undo when the step can be undone; it goes after a
few seconds or on a switch to another view. There is no status line. Month opens
with the student's week as its first row. A new account with no homework sees
"Nothing here yet." and one "Add your first homework" button in place of empty
hours. A focus timer has a screen of its own (Start focus, Quick focus or F):
the countdown in a ring, the homework, Pause, Skip and Finish; Esc goes back and
the timer keeps running.

The week calendar is a painted timeline, as in Daily Scheduler: dragging a
block moves it with the pointer in the student's 5- or 15-minute step and
across days, its top or bottom edge resizes it, and dragging or clicking empty
time opens an Add dialog for that range. A click on a block opens it; a
right-click offers Open, Duplicate, Finished (homework) and Delete, and on
homework Delete homework. Homework is deleted from its editor, from its row
under Unfinished or from that menu, after a question: the server removes it and
its sessions from every week (`DELETE` in `/api/changes`) and says which it
removed, so one Undo writes the homework and each of those sessions back. Hours have
no half-hour rules; the now line and its time are in the accent, today's date
is an accent chip, and Week washes today's column with 3 % of the text colour.
After a plan, blocks slide to their new places. Blocks may overlap; they sit side by
side, each marked. A drop
is refused only outside the day's hours or when homework would end after it is
due. Dragging one day of a repeating block moves that day only. Dragging works
in every design: a block can be picked up wherever a design shows it, and every
design's Day and Week are its own hours, which take the drop at the time under
the pointer. Everywhere the drop says the
day, the time and any block it would sit beside, in the same words.

Downloads from GitHub Releases:

- **Download for Windows.** `FlexWeek-Windows-x64-Setup.exe`
- **Download for Linux.** `FlexWeek-Linux-x86_64.tar.gz`

Windows: `FlexWeek-Windows-x64-Setup.exe` installs for the student's account
without an administrator; `FlexWeek-Windows-x64.msi` installs for every account
on a PC, for schools and IT. Until the app is code-signed, SmartScreen is More
info, then Run anyway.
Linux: 64-bit desktop (GNOME, KDE Plasma, Cinnamon, Xfce), glibc 2.38 or
newer, OpenGL or EGL. The X11 cursor helper is inside the archive. A shippable
Linux tarball is built on Ubuntu 24.04, not on a newer-glibc Fedora host.
Chromebooks are not supported: there is no web version.

Run locally:

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-desktop.txt
python -m desktop.main    # starts the backend inside the app; nothing to open in a browser
```

Current account/API contract:

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/auth/register` | Create username/password account, session and eight one-time recovery codes |
| POST | `/api/auth/login` | Authenticate and rotate session |
| POST | `/api/auth/logout` | Revoke current session |
| GET | `/api/auth/me` | Current account; 401 when absent/expired |
| POST | `/api/auth/recover` | Username, unused recovery code and new password; throttled like login |
| GET | `/api/auth/recovery-status` | Unused recovery-code count |
| POST | `/api/auth/recovery-codes` | Password-gated replacement of unused codes |
| POST | `/api/auth/password` | Change password; keep this session and drop the others |
| DELETE | `/api/auth/account` | Password-gated deletion of this account and its rows |
| GET/PUT | `/api/week` | One dated week of the account, with revision-checked saves |
| GET | `/api/weeks` | The `week_start` dates this account has saved, ascending |
| GET | `/api/day` | One date's agenda: due-soon homework, that day's sessions and fixed blocks, a next action and the workload split |
| GET | `/api/month` | Month grid of deadlines, projects, overdue work, planned and completed study time, and an unscheduled total |
| GET | `/api/assignments` | Open assignments with planned and unplanned minutes for a `week_start`; completed ones only when asked |
| PUT/DELETE | `/api/assignments/{id}` | Revision-checked create, update and delete; delete removes its sessions from every week |
| POST | `/api/assignments/{id}/spread` | Preview sessions of a chosen length from a start date through the due date; writes nothing |
| POST | `/api/changes` | Several week and assignment writes, all or nothing; optional operation ID and pre-change recovery point |
| GET/PUT | `/api/preferences` | Theme, appearance pack, accent, motion, reminders, timers, alarms, alarm sound, Spotify default, planning style, setup progress, availability windows and comfort settings |
| GET | `/api/timer-presets` | Named timer presets on the 15-minute grid |
| GET | `/api/reminder-limits` | The reminder ceilings the settings dialog explains |
| POST | `/api/timer-split-preview` | Explain how a timer splits and rounds before it is saved |
| GET/PUT/DELETE | `/api/routines[/{id}]` | Account-owned, revision-checked fixed-time routine templates |
| GET/POST | `/api/restore-points[/{id}/preview or /restore]` | Create/list restore points, preview a state-tokened diff, and restore transactionally |
| GET | `/api/storage-info` | Authenticated mode, label, username, origin and 256 KiB transfer limit; no filesystem path |
| POST | `/api/account-export` | Password-gated format-3 snapshot of weeks, assignments, preferences and routines |
| POST | `/api/account-import/preview` | State-tokened diff of a format-3 snapshot against this account |
| POST | `/api/account-import` | Previewed replace of weeks, assignments, preferences and routines |
| POST | `/api/solve` | Authenticated week and its `week_start` in, SolveTrace out; no storage mutation |
| GET | `/api/health` | Public health response |

`POST /api/solve` accepts `{ "blocks": [...], "week_start": "YYYY-MM-DD" }` and
either an optional `recover` object for a missed locked occurrence or an
optional `running_late` object for a delayed start, never both. `week_start` is
required when any block carries `assignment_id`. The solve trace contains `placed`,
`unplaced`, `moves`, `explanations`, `failed_constraints`, `solve_ms`,
`complete`. Demo endpoints are removed. Test-only seed JSON remains.
Writes require `X-FlexWeek-Request: 1`; the request `Origin` must match the
API's origin. Clients send `X-FlexWeek-Account` so a request made before an
account change is rejected after it. No CORS is enabled.

Registration: normalized case-insensitive ASCII username (3–32 letters, digits,
underscores), password 12–128 characters. New accounts have an empty week, eight
one-time recovery codes (hashes only in SQLite) and a theme that follows the
device's light or dark setting. Duplicate usernames return 409, invalid input
422, expired or missing sessions 401, stale changed writes 409, throttled auth
429, oversized requests 413, transient database failures 503. Identical week
retries return success without duplicate blocks or another revision increment.
Wrong username and wrong recovery code share one 401 sentence. Account export
and import apply use the same 256 KiB write cap; export 413s when the compact
`{snapshot, state_token, operation_id}` envelope would not fit. Details live in
`docs/stage6-contract.md`.

A week is identified by `(account, week_start)`, where `week_start` is a naive
local ISO date that is always a Monday. An account holds as many dated weeks as
it saves, each with its own revision. A never-saved week reads as empty at
revision 0 rather than 404, and a `week_start` that is malformed, out of
2000-01-01..2099-12-31, or not a Monday is rejected with 422 rather than snapped
to the nearest Monday, so a client and the server cannot disagree about which
week is open while both believe they succeeded. Blocks keep their `days` index
and derive their calendar date, so the solver stays day-index pure.
A week has at most 100 uniquely identified blocks; titles 1–80,
course names at most 40, block durations any positive number of minutes up to
7140, and unique day indices. Explicit starts are any minute from 00:00 and end
by 24:00 (a block ending at midnight is stored as the next date at 00:00).
Homework estimates, spread sessions, running-late starts, split lengths,
`day_cutoff` and work, study and protected windows stay on the 15-minute grid.
An assignment's `due` is a naive local `YYYY-MM-DD`, due by the end of that day,
or `YYYY-MM-DDTHH:MM` for work due at a set time that day, between
2000-01-01 and 2099-12-31; `earliest` bounds and legacy `latest` values use a
full English weekday plus HH:MM, or HH:MM. An account holds at most 1000
assignments. API write bodies are capped at 256 KiB.

Preferences store `theme` as `system`, `slate` or `nocturne` for the light/dark
axis. Every screen is drawn in one system (`desktop/native/tokens.py`): one
accent, FlexWeek's blue (`#3d6fc4` on light looks, `#7fa8ff` on dark ones),
which Sky, Gold, Sea or Sand replace and which marks controls only, never a
large area; neutral pages and cards; one type scale (caption 11, body 13,
heading 15, title 20 and display 28 points at Normal text, which Small and
Large scale); weights 400 and 600, and 700 for display numbers; spacing in
steps from 4 to 32 pixels; corners of 6 on controls, 10 on cards and 16 on
sheets; two shadows; Lucide's icons; and red only for a problem. The ten looks
are Light, Dark, High contrast, Slate, Nocturne, Paper, Ink, Terminal, Poster
and Pastel, and System follows the device between Light and Dark. High
contrast keeps its yellow accent (`#ffd400`) whatever swatch is picked, with
text at 7 to 1 or more. Settings offers Look as Light, Dark and System, with
the other looks under More looks and the student's saved looks after them
under Your looks. Today's app is the default main view and Day dial the
default day screen, with Timeline the one standard alternative; Mission
control, Bento, Retro desktop, Clay deck and One thing are experimental. Every
saved choice still loads. The app ships Inter, Newsreader and JetBrains Mono
(Regular, Medium, SemiBold, Bold each), with figures of one width in times:
the Font knob is Sans (Inter), Serif (Newsreader headings over Inter) or Mono
(JetBrains Mono). Retro desktop also ships Pixelify Sans and VT323. Cards pad
16 pixels, 8 at Compact, and dialogs 24. The categories are one family worked
out in OKLCH, every fill at one lightness and every mark at another, so no
category outweighs the rest. Homework's mark is darker, so it stays apart from
Exercise for a student who cannot tell red from green, and homework carries a
book. On a dark look a block is its category sunk into the card, written in
the look's text colour. `clock_24h` (default true) chooses 16:00 or 4:00 PM for
every time written on screen; times are still sent and saved as HH:MM.
Settings is a page of the window, not a dialog: its sections on the left and
cards on the right, a switch for each on or off, side-by-side segments for two
or three choices, and pictures for the main view and day screen. Every dialog
has at most one filled button. `system` is the
default pack: the app follows the device's light or dark setting, uses Light
when the device reports none, and switches when that setting changes. Choosing
Slate, Nocturne or a frost pack keeps that look until the student chooses
again. Signed-out screens follow the device setting; signing out does not
change an account's saved choice. Preferences
also store reminder enable/lead/sound, `reminder_dnd_override`, pomodoro
lengths, `auto_split_pomodoro`, `default_spotify_url`, and a list of alarms.
Reminders are on unless the student turns them off; an account from before 0.15
had them turned on once (`prefs_version` 1), and a later choice stands. A block
reminds from the moment its lead begins until it starts, once, so a block saved
inside its lead reminds at once. A block with its own Spotify link plays it at
its start, as an alarm plays its song, with the same Dismiss and Snooze. On desktop, `reminder_dnd_override`
tags the Notification `flexweek-stay` so the tray presenter skips the 10-second
auto-close. Unchecked alerts still close at 10 seconds. Qt has no
`requireInteraction`.

Each design draws its own Day and Week. The top bar, the window's frame,
dialogs and Today's app always wear the student's look and accent. Every design
but Today's app has Colours, with Match my look first and the default; a
colourway of the design's own paints only the design's page. One thing's
Poster, Day dial's Night and Clay deck's Clay wear the student's accent, fitted
to read at 4.5 to 1 on their page; the other colourways name their own. The
options are the ones `desktop/native/layouts/registry.py` declares, and a show
or hide option starts at Show:

| Design | Role | What it shows | Options |
|---|---|---|---|
| Today's app | main view, default | The week grid with the rail | None; its colours are the look |
| Timeline | main view | The week as a paper planner opened flat, and a day as its page of hours beside its notes | Colours (Ruled paper, Night), Spacing (Comfortable, Compact), Finished and past items |
| Mission control | main view, experimental | Four figures across the top, the days as lanes of hours, and deadlines by time left | Colours (Flight deck, Cyan, Amber, Green), Figures across the top |
| Bento | main view, experimental | A big tile of the week's hours, or of today's with the other days as small tiles, and homework around it | Colours (Indigo, Sunset, Mono, Midnight), Hero (Week, Today), Tile corners (Soft, Square) |
| Retro desktop | main view, experimental | Windows 98: Week.exe, deadlines.txt in Notepad, Up next and a taskbar | Colours (Teal, Plum and Slate desktop), Windows open at start (All three, Main window only) |
| Clay deck | main view, experimental | One day at a time on a large card, the days either side peeking | Colours (Clay, Mint, Sunset, Dusk), Days either side |
| Day dial | day screen, default | The day as a 24-hour ring, read out hour by hour beside it | Colours (Night, Daylight), Hour by hour list, Small dials for the week |
| One thing | day screen, experimental | What is on or next, counted down on a ring, and what comes after | Colours (Poster, Paper and ink), Lead with (What is on now, What is next), Buttons, Day bar |

A saved option this build does not have, such as 0.16's Week strip, Hours
shown, deadline radar, Supporting tiles or Week cards, is dropped when read,
and the rest of the design's settings are kept.

Customise… under Look opens the look editor over Settings. Its header has Back,
Start from, the look's name, Duplicate and Delete for a saved look, and whether
the look is saved. On the left are folding cards (Readability, Colours,
Categories, Shape, Type, Blocks, Grid and Motion), each with its own Reset; on
the right is the window's own week page as the look dresses it, fitted or at
its real size; the foot has Reset all, Export, Import, Save as new and Done.
The window wears every change at once. Readability lists each pair of colours
under 4.5 to 1 with a Fix that moves the chosen colour's OKLCH lightness the
least it takes. Back or Esc with changes not saved asks Save, Keep without
saving or Discard changes. While a custom look is worn, Settings shows the
accent and Fine-tune knobs it sets, does not let them change, and says to open
Customise….

Motion (`desktop/native/motion.py`) never makes the student wait: the new page
is live at once while a picture of the old one fades over it. A page change
fades through, the old page out in 90 ms and the new one in over 120 ms; Day,
Week and Month also slide 12 pixels toward the segment chosen, and the arrows
drift the old page 16 pixels the way the student went. A change of view, My day
or design changes the top bar and the page in one frame. Settings slides in
from the right over the week, dimmed 20 %, in 200 ms. Notices, sheets, dialogs
and Ctrl+K fade in and rise 8 pixels, and the top bar's selection slides to the
view chosen in 160 ms. Animations has four levels: Normal; More (`extra`), 1.45
times as long and a third further; Reduce, the same fades with nothing
travelling (no slide, rise, drift, zoom, lift or sliding blocks); and Off,
where nothing animates. Each design's own motion asks the same module, and
nothing loops.

## Architecture
- Language/runtime: **Python 3.14**. PINNED. Verified against the local
  interpreter (3.14.7) and `.github/workflows/verify.yml` (`python-version: '3.14'`).
  Never downgrade.
- Current languages: Python, and SQL for account storage. The client is PySide6
  Qt widgets; see DESKTOP.md.
- Frameworks, pinned in `requirements.txt`: FastAPI 0.141.1,
  uvicorn[standard] 0.52.4, pytest 9.1.1, httpx 0.28.1, ruff 0.16.6, mypy 2.3.1, Pydantic 2.13.5.
- Storage: SQLite, in the user data folder for the app (`FLEXWEEK_DATABASE`,
  default `var/flexweek.db`, only when the API runs on its own), with users,
  sessions, weeks keyed `(user_id, week_start)`, assignments keyed
  `(user_id, id)`, preferences, routines, restore points, hashed recovery codes,
  bounded idempotency records and short-lived auth-attempt counters. Schema
  creation is additive on startup; related writes use transactions. The
  pre-dated single-week table migrates on first start inside one explicit
  transaction, stamping the existing row with the Monday of that day; it is
  idempotent and never drops a row. A preferences table from
  before the System theme is rebuilt once on start in one transaction: stored
  `slate` and `nocturne` are kept and any other value becomes `system`. Flexible
  blocks without `assignment_id`, and pomodoro chunk groups, migrate once on
  start into assignments with deterministic ids, inside one transaction and
  without changing week revisions (`docs/stage1-contract.md`). Browser
  localStorage is read only for explicit legacy import, then removed on success.
- Major components:
  - `backend/models.py`. Pydantic models (`TimeBlock`, `Move`, `SolveTrace`,
    `Explanation`) and slot helpers. **Zero FastAPI imports.**
  - `backend/app.py`. HTTP endpoints, authentication/ownership, static files, `/api/solve`.
    No placement logic.
  - `backend/solver.py`. Pure synchronous CSP placement. No HTTP knowledge.
  - `backend/explain.py`. Reason code and slack status to English string.
  - `backend/storage.py`. SQLite transactions, password hashing and sessions.
  - `backend/data/demo_*.json`. Test-only anonymized seed weeks.
  - `backend/tests/`. Pytest suite; the source of truth for solver behavior.
  - `desktop/native/`. The client: `window.py` (chrome, pages and dialogs),
    `controller.py` (session, saves, solve, focus and alarms), `widgets.py`
    (week grid, day agenda, month and editors), `layouts/` (the eight designs
    and the registry they are built from), `tokens.py` (the system's measures
    and colour maths), `look.py` (packs, presets, knobs and palettes),
    `custom_look.py` and `look_editor.py` (a look of the student's own),
    `motion.py` (every fade and slide), `weekmodel.py`, `pomodoro.py`,
    `tones.py` and `sound.py`. The
    client owns interaction and explanation display and **never reimplements
    placement**.
  - `desktop/`. PySide6 window, bundled uvicorn, packaging scripts and assets.
- Time model: local `HH:MM` strings and Mon–Sun day indices, plus naive local
  `YYYY-MM-DDTHH:MM` assignment deadlines, assumed America/Los_Angeles. No
  timezone conversion math anywhere in v1.
- Slot grid: Mon–Sun 00:00–24:00, 15-minute slots, 96/day × 7 = 672/week.
  The planner works in these slots; a block may start and end at any minute
  and takes every slot it touches.
  Overlap uses half-open ranges `[start, end)`. One `overlaps()` helper. There
  is no duplicate date math.
- External APIs/services: none. No OAuth, no calendar sync, no LLM at runtime.
- Deployment: the desktop client is the product; there is no web client. The
  Windows and Linux builds are PySide6 Qt widgets that run the FastAPI backend
  in-process on a loopback port, so they need no separate server and no Python
  install; the database sits in the user data directory. `FLEXWEEK_DESKTOP_ORIGIN` (or `FLEXWEEK_ORIGIN`) points that window
  at a hosted deployment instead, and an invalid value is an error rather than a
  silent fall back to local. The Windows installers are built on GitHub
  Actions (`.github/workflows/release-windows.yml`), which installs, opens and
  uninstalls each one; running them on a real PC is unverified here. Production requires HTTPS via FLEXWEEK_ORIGIN and
  persistent SQLite storage.
- GitHub Actions: `.github/workflows/verify.yml` is the source gate (mypy, not
  pyright); its second job, `rig`, installs Xvfb, Openbox and xdotool, runs
  Today's app's Day and Week with a real pointer on a hidden display, and
  uploads the screenshots, videos and results. `.github/workflows/codeql.yml`
  runs CodeQL on Python.
  The generic kit `ci.yml` is not installed: it ran pyright and looked for
  `tests/` at the repo root. Dependabot stays off.

## Security & Privacy
- No secrets in source. All credentials via environment variables. The app
  uses account session credentials generated at runtime.
- Dependencies must be pinned and reproducible. Updates are manual:
  **Dependabot is deliberately not used in this repo**. Do not add
  `.github/dependabot.yml` or re-enable it.
- Account-owned schedules are sent to the backend and stored in SQLite.
- Passwords use Python/OpenSSL scrypt, N=32768, r=8, p=3, random 16-byte salt,
  32-byte derived key; comparison is constant-time. No new hash dependency.
- Opaque random sessions expire in seven days; only SHA-256 token hashes are
  stored. Cookies are HttpOnly, SameSite=Strict, Secure on HTTPS deployments.
  Sign-out revokes the current session. Expired sessions are rejected on reads
  and cleaned when new sessions are created.
- Keep me signed in stores the session token for one database in a file only
  that user can read, in the app's data folder. It is kept once a new account's
  recovery codes are acknowledged, replaced when the password changes, and
  removed by Log out, account deletion, or the server ending the session.
- Writes use custom-header/origin CSRF checks; endpoints derive ownership from
  the session. Queries are parameterized. No credentials or schedule payloads
  are logged; validation responses omit submitted input.
- Auth attempts are bounded per username (10) and source address (30) per
  five-minute window, persisted in SQLite and expired during auth requests.
- Production needs HTTPS, deployment backups and deployment-specific proxy
  setup. Stage 3 restore points cover student recovery inside one account.
  Stage 6 recovery codes, password change, account deletion and previewed
  format-3 transfer are the supported access flows (`docs/stage6-contract.md`).
  Advanced hardening and audits remain later release work.
- The week saves itself shortly after each change. A failed save keeps its
  payload and operation id and is retried automatically, so a retry writes the
  same change once; Retry save appears while one is pending. A save that comes
  back 409 because another window changed the week is never written over:
  saving stops and the student is asked to reload the saved week, which
  discards the unsaved change. Stale revisions never silently overwrite newer
  data. Session loss hides all private content. Opening another week parks an
  unsaved week as a draft for that account. A running focus timer is kept in
  memory per account with ids and times only, never assignment text; undo
  history lives in memory and clears on sign-out, session expiry or account
  deletion.
- The Stage 3 clipboard also lives only in memory and clears on sign-out,
  session expiry and account deletion. Routine, restore and transfer routes derive
  ownership from the session; another account's opaque ID is treated as not
  found. Restore and import previews use a state token so a later edit cannot
  be overwritten silently. Password-gated export, code replacement, password
  change and deletion are not enough from a stolen session cookie alone.
- Demo data is anonymized: no real student names, schools, or addresses, and no
  copyrighted syllabus PDFs in the repo.
- License is **GPL-3.0** (`LICENSE`); the README and the page footer must agree
  with it. Chosen deliberately: copyleft means anyone who redistributes a
  modified FlexWeek has to publish their source, so the scheduler cannot be
  quietly repackaged into a closed product that students cannot inspect.
- AI assistance is disclosed in the README and the CAC form; the solver is
  handwritten.

## Validation & Tooling
The full source gate from the repo root, inside `.venv`, is:

```
.venv/bin/python scripts/verify.py
```

`--backend-only` omits desktop tests and reports desktop as unverified.
`.github/workflows/verify.yml` runs that variant on every push and pull
request (Python 3.14, `contents: read`), and its `rig` job runs the
real-pointer rig on Today's app under Xvfb. Neither builds a binary.

The commands it runs, each of which must exit 0:

- Lint: `ruff check .`. Configured in `ruff.toml` (target `py314`, line length
  110). The `DTZ` (timezone-aware datetime) rules are deliberately not selected
  because of the naive-local-time model above; the reason is written into
  `ruff.toml`. Do not add timezone math to satisfy a linter.
- Types: `mypy backend`. This repo's type checker is mypy. Do not install
  pyright.
- Tests: `pytest -q`. Run from the repo root so `backend` imports resolve.
  `--backend-only` limits pytest to `backend/tests`.
- Desktop behavior tests are part of the pytest suite and run offscreen against
  a real loopback backend. Window layout on a real display needs a separate
  manual check.
- Preserve existing solver fixture coverage; include account isolation, expiry,
  CSRF, atomic saves, revision conflict and import/retry tests.
- Solver tests are the source of truth: `solve()` stays synchronous and pure so
  pytest can exercise it without HTTP.

## Acceptance Criteria
- [ ] Only-locked week solves to an identity schedule with 0 moves (T1).
- [ ] A single homework block with room to spare is placed, energy-matched where
      possible (T2).
- [ ] Test vs. reading contending for one slot: test placed, reading unplaced
      with `PRIORITY_PREEMPT` (T3).
- [ ] 6h of homework into 2h of free time: remainder unplaced with
      `NO_SLOT_LEFT` (T4).
- [ ] Deadline before the only free window: unplaced with `DEADLINE_MISS` (T5).
- [ ] A flexible block's domain excludes slots covered by a sport block (T6).
- [ ] The packed fixture reports `solve_ms < 150` (T7).
- [ ] A malformed, oversized or newer-version import file is refused without
      touching the account week.
- [ ] Two accounts independently create, solve, save and reload weeks.
- [ ] Sign-out hides private data; expired sessions cannot read/write/solve.
- [ ] A new account follows the device's light or dark setting, and a chosen
      Light or Dark theme is saved per account and returns after logging in.
- [ ] Failed saves preserve drafts; stale saves return a recoverable conflict.
- [ ] No output block overlaps another, and no flexible block starts after its
      deadline (property tests).
- [ ] First paint with no session is Sign in, with creating an account offered
      under it.
- [ ] A pomodoro parent cannot be stored with the chunks split from it.
- [ ] Marking a locked occurrence missed reshuffles remaining flexible work and
      leaves sleep intact.
- [ ] A student enters homework due next Tuesday at 11:59 p.m., works on it
      this week and next, ends a focus session without completing it, switches
      weeks without losing the timer, and undoes an accidental delete or replan.
- [ ] A student copies one practice occurrence, applies a fixed-time routine to
      next week with one holiday exception, carries unfinished homework once,
      and previews and restores an account-owned recovery point.
- [ ] A student recovers a forgotten password with a one-time code, sees which
      account and origin they are using, and previews a format-3 account file
      onto another signed-in account without exposing it to a third account.
- [ ] A new student can see what is due tomorrow, add homework, plan it, start
      it and mark it finished at 390px and 1280px, without a context menu or
      reading scheduling documentation.
- [ ] A student who is running late previews a 30-minute delay, accepts it, and
      undoes it in one step; spreading a project adds sessions only after a
      preview.
- [ ] Protected downtime, preferred study hours and a day cutoff change where
      the solver places work without the client re-sending occupancy.
- [ ] A student opens Month, sees deadlines with planned and completed study
      time, and clicks a date to open Day view.
- [ ] A student drags a Month chip to another date and the block moves there
      with its time; dragging it past its due date is refused in words.
- [ ] A new account skips or finishes setup, and setup does not come back;
      quitting mid-way resumes on the same page.
- [ ] In every design, a student drags homework and blocks to a time on any
      day, a drop beside another block is allowed and shown side by side, and
      the design refuses what the week calendar refuses, in the same words.
- [ ] Download names are `FlexWeek-Windows-x64-Setup.exe` (with
      `FlexWeek-Windows-x64.msi` for schools) and
      `FlexWeek-Linux-x86_64.tar.gz`.
- [ ] A judge can install the Windows or Linux download and follow the README.
- [ ] `scripts/verify.py` exits 0 (`ruff check .`, `mypy backend`, and
      `pytest -q` included).
- [ ] CHANGELOG.md updated for user-visible changes.
