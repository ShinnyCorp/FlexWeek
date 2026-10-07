# Contract: Stage 4 — adapt plans to real student days

Status: approved 2026-09-15 by the owner. Claude owns the browser/desktop frontend. Grok owns
persistence, the solver, and authenticated API work. Both clients continue to
use the same HTML, CSS and JavaScript frontend.

This contract is based on `claude/stage3-frontend` at `9759a23`. It does not
port Daily Scheduler's AI tool execution, and it does not drop work that no
longer fits.

## Goal

A student can spread a project's hours across days before the due time, run
late by 15, 30 or 60 minutes and preview the revised plan, keep notes and a
small checklist on the assignment, and protect downtime so the solver does not
treat every gap as homework time.

## Owner decisions (proposed defaults)

1. **Running late** is a solve preview, like missed-block recovery. Accepting it
   writes one one-off locked block titled "Running late" for the occupied
   interval through `/api/changes`, then re-solves. That stored interval is what
   reload and Undo see. Undo of an accepted replan is one frontend Undo entry,
   already Stage 1.
2. Delay choices are **15, 30 and 60 minutes** only.
3. The cutoff is an explicit `from_start` on the 15-minute grid. The frontend
   supplies "now" snapped down to a slot when the day is today.
4. Fixed commitments and sleep stay put. Flexible work that no longer fits
   remains in `unplaced` with its usual reason. Nothing is deleted.
5. **Spread** creates extra flexible sessions of the chosen length on the same
   assignment. It does not place start times and is not pomodoro splitting.
6. Spread is a **preview**. Confirmation writes sessions through `/api/changes`.
7. Assignment **notes, links and checklist** live on the assignment, not on
   sessions. Empty values are omitted from stored JSON the same way optional
   TimeBlock fields are.
8. Protected downtime, commute/meal buffers and a day cutoff live on
   **preferences**, so they apply every week without painting extra blocks.
   Preferred study hours are a soft placement preference, like energy.
9. No new reason code is required for cluster advice. It is an explanation with
   `reason: null`. Running late reshuffles reuse `RESHUFFLE_AFTER_MISS` with a
   distinct sentence in that path only.

## 1. Running late

`POST /api/solve` accepts `running_late` instead of `recover` (not both):

```json
{
  "blocks": [],
  "week_start": "2026-09-14",
  "running_late": {
    "day": 0,
    "minutes": 30,
    "from_start": "14:30",
    "previous_placed": []
  }
}
```

- `day` is 0–6 in that week. `from_start` is HH:MM on a 15-minute slot in
  06:00–22:45. Occupancy is `[from_start, from_start + minutes)` clipped to
  23:00, on that day only.
- That occupancy is extra locked time. School, sport and sleep blocks are
  unchanged. Sleep 23:00–06:00 stays a hard guard.
- The solver re-places incomplete flexible work. Moves vs `previous_placed`
  use the same reshape as missed-block recovery. Work that cannot fit is
  unplaced, never dropped from the week payload.
- Invalid combinations return 422. Solve still does not mutate storage.
- Accepting the preview does not send `running_late` again. It stores the
  occupied interval as a locked block (`title` "Running late", one day, start
  and duration on the grid, clipped so it ends by 23:00) alongside every
  existing block, using a stable `operation_id`. A later solve treats that
  block as ordinary locked time.

## 2. Spread a project

`POST /api/assignments/{id}/spread` is authenticated and CSRF-protected. It
does not write:

```json
{"session_min": 60, "from_date": "2026-09-14"}
```

`session_min` is 15–180 and a multiple of 15. `from_date` is YYYY-MM-DD.

Response:

```json
{
  "assignment_id": "hw-essay",
  "session_min": 60,
  "remaining_min": 0,
  "sessions": [
    {"week_start": "2026-09-14", "date": "2026-09-14", "days": [0], "duration_min": 60}
  ]
}
```

Rules:

- Remaining minutes are `unplanned_minutes(estimate, focus, planned open
  sessions)`, the Stage 1/3 quantity. Completed assignments return 422.
- Sessions round-robin across calendar dates from `from_date` through the due
  date inclusive. Dates after the due date are unused.
- Chunks are `session_min` until the remainder, which is also a multiple of 15.
  This is not a pomodoro parent/chunk split: each session is a normal flexible
  block with `assignment_id` and no `pomodoro_*` fields.
- The preview does not assign block ids or start times. The frontend supplies
  ids when it confirms through `/api/changes`.
- A week that would exceed 100 blocks after confirm is rejected by the existing
  week validator, not by this preview.

## 3. Assignment notes, links and checklist

On `AssignmentContent`:

- `notes`: at most 4000 characters. Default empty and omitted when empty.
- `links`: at most 20 `{label, url}` pairs. Label 1–80 characters. URL is an
  `http` or `https` URL at most 500 characters, no userinfo.
- `checklist`: at most 40 `{id, text, done}` items. Ids unique within the
  assignment, 1–80 characters. Text 1–80 characters. `done` defaults false.

Checklist completion does not complete the assignment. Focus minutes still
never complete anything.

## 4. Protected time and study hours

On preferences (defaults omitted when empty, so existing clients keep working):

- `protected`: at most 21 windows `{kind, days, start, duration_min}` where
  `kind` is `downtime`, `commute` or `meal`. Days unique 0–6. Start and
  duration on the 15-minute grid, fitting 06:00–23:00.
- `study_windows`: at most 21 windows `{days, start, duration_min}` with the
  same grid rules. Soft preference only.
- `day_cutoff`: HH:MM on the grid, 06:15–23:00, or omitted. Flexible work must
  finish by that time every day.

`POST /api/solve` loads the signed-in account's preferences and applies them.
The frontend does not re-send occupancy. Packed-fixture `solve_ms < 150`
remains required.

## 5. Deadline-cluster explanations

When two or more incomplete flexible tasks are unplaced or have danger slack,
the trace includes one extra explanation (`reason` null) naming concrete
choices: shorten a session, pick another day, or adjust availability. It must
not claim the solver made an impossible week fit.

## Out of scope

- Frontend UI, copy, and Undo wiring (Claude).
- Dropping blocks that no longer fit.
- Daily Scheduler AI tools, Google Calendar, LMS import.
- Changing sleep, accounts, restore points, or routines.
- Spec.md edits until the owner approves this contract.

## Verification (backend)

- Solver fixtures: late occupancy does not move locked blocks or sleep; overflow
  is unplaced; packed fixture stays under 150 ms with protected hours.
- Spread: remaining minutes, due-date bounds, 15-minute chunks, same
  `assignment_id`, no pomodoro fields.
- Assignment PUT round-trip for notes/links/checklist; rejected javascript:
  URLs and duplicate checklist ids.
- Preferences reject overlapping-the-grid protected windows; solve honors
  cutoff.
- Cluster explanation appears only when two or more tasks are in trouble.
- Account isolation: another account's assignment spread is 404.
- `.venv/bin/python scripts/verify.py --web-only` from this worktree.

## Addendum 2026-09-22: study windows for one subject

A study window may carry `subject`, 1 to 40 characters after trimming, omitted when
absent. The solver ranks each candidate time for a session:

1. inside a window whose subject matches the session's course, compared without
   regard to case, first;
2. inside a window with no subject, next;
3. anywhere else, last. A window for another subject counts as anywhere else.

Energy preference, then day and slot, break ties as before. `POST /api/solve` takes
each session's course from its assignment, so an unsaved session still finds its
window.

## Addendum 2026-10-07: one Study hours list (J7)

Preferred study hours merge into the planning hours. `work_windows` is the one list,
shown to the student as Study hours: Setup fills it and Availability edits it, and the
solver takes it as its only window input. It bounds placement as before, and it orders
it: inside a window kept for the session's subject first, inside a window for any
subject next (the ranking of the 2026-09-22 addendum, read from this list).

`study_windows` is no longer a preference. Where saved preferences are read
(`preferences_fields` and the solver's availability in `engine/store`), and when a
client or an import file still sends it, each preferred window joins the list as
`{days, start, end, subject}` after the windows already there. One that the list
already covers on each of its days, for the same subject, is left out, and none is
added past the limit of 21. The next save writes the one list alone.
