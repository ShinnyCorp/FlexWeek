# Contract: Stage 1 — assignments across weeks, exact deadlines, focus completion, timer lifetime, undo

Status: approved by the owner 2026-09-13 for roadmap Stage 1 of the student
experience revision. spec.md is updated to match in the same change.

Grok builds the backend parts and Claude builds the frontend parts against this
file at the same time. Neither side changes it alone.

Line references are to `main` at `c2b1b90`.

## Owner decisions (2026-09-13)

1. One assignment can have work in more than one week, in Stage 1.
2. A running focus timer survives a reload through `sessionStorage`.
3. Saves still accept the old weekday `latest` and convert it.
4. "Need more time" asks for an amount each time.

## 1. Assignments and exact deadlines

### Today

- A flexible block's deadline is `latest`, either `"Thursday 21:00"` or `"21:00"`
  (`backend/models.py:177-183`).
- `parse_deadline` turns it into `(day_index, minutes)` inside the week. A bare
  time uses the block's last candidate day (`backend/slots.py:84-105`).
- A flexible block with no deadline has no deadline bound at all; `(7, 0)` only
  orders the search (`backend/solver.py:100`, `backend/solver.py:314`). Setup
  offers due times up to 23:00 (`frontend/setup.js:126`).
- A flexible block is placed once, on one of its candidate `days`, for its whole
  `duration_min` (`backend/solver.py:302-321`).
- A block lives in exactly one week's JSON (`weeks.blocks`,
  `backend/storage.py:37-43`). Nothing links work across weeks.
- `completed` is per block. A completed block with a start keeps its slot as
  spent time when it has a `completed_day` or a single candidate day; otherwise
  it appears nowhere (`backend/solver.py:38-51`).
- Splitting into pomodoros replaces a flexible block with `locked` work and
  break chunks that share `pomodoro_parent_id`, and the chunks drop `latest`
  (`frontend/app.js:1932-1967`).

### Assignment

An assignment is account-owned and outlives any single week.

| Field | Rule |
|---|---|
| `id` | 1–80 characters, unique per account |
| `title` | 1–80 characters |
| `course`, `category`, `priority`, `energy`, `spotify_url` | Same rules as on blocks today |
| `due` | Required. Naive local `YYYY-MM-DDTHH:MM`, any minute, 2000-01-01..2099-12-31. No seconds, no timezone. |
| `estimate_min` | Total work. Positive multiple of 15, at most 1440 (a day's work; longer work is split). |
| `focus_minutes`, `focus_sessions` | Progress credited by focus sessions. 0–71400 and 0–9999. |
| `completed` | The whole assignment is finished. |
| `completed_at` | Naive local `YYYY-MM-DDTHH:MM`; required when `completed`, otherwise null. |
| `revision` | Per assignment, like weeks. |

An account holds at most 1000 assignments (422 beyond that).

### Work sessions

- A work session is a flexible block in a week with `assignment_id`. It keeps
  its own `id`, `duration_min` (this session's length), `days` (candidate days
  in that week), `start` once placed, and `completed` / `completed_day` meaning
  this session is done and holds its slot, as today.
- A locked pomodoro work chunk may carry the same `assignment_id`. Break chunks
  never do.
- A session never carries `latest` or `due`. Its `title`, `priority`, `energy`,
  `course`, `category` and `spotify_url` are copies. On every `GET` and `PUT` of
  a week, the server writes the assignment's current values into those copies,
  so the solver, exports and older clients still see complete blocks.
- Any block carrying `assignment_id`, including a locked pomodoro work chunk,
  must have block-level `focus_minutes` and `focus_sessions` of 0 (422
  otherwise). Progress lives on the assignment.
- Sessions keep `earliest` as today; the adapter passes it to the solver
  unchanged.
- One assignment may have sessions in any number of weeks, for example Sunday
  in one week and Monday in the next. Every session credits the same
  assignment.

### Progress and remaining work

- Remaining work is `max(0, estimate_min − focus_minutes)`.
- For a given week, planned work is the total `duration_min` of the
  assignment's sessions that are not completed, in that week and later weeks.
  Unplanned work is `max(0, remaining − planned)`.
- **Need more time** raises `estimate_min` by the amount the student enters
  (multiples of 15, total at most 1440).
- **Finished** sets `completed` and `completed_at`. Sessions in later weeks stay
  stored but are no longer placed, and the week shows them as not needed.

### Deadline bound (solver adapter)

The solver stays day-index pure. Before solving, and when computing slack, the
backend converts each session's assignment `due` against the week being solved:

| `due` relative to the week | Bound | Effect |
|---|---|---|
| Inside the week | `(day_index, minutes)` of `due` | Existing rule `(day, end_min) <= bound`. 23:59 allows any slot that day; Tuesday 05:00 allows Monday but no Tuesday slot. |
| After Sunday of the week | none | Same as no deadline today: any candidate day. |
| Before Monday of the week | `(0, 0)` | Nothing fits; unplaced with `DEADLINE_PASSED`. |

- For a completed assignment, its completed sessions keep their slots as spent
  time under the existing rule, and its sessions that are not completed appear
  nowhere in the trace (the adapter leaves them out of the solve).
- Slack is measured in real minutes to `due`, so it can be longer than a week.
- Explanations and moves keep the session's block id.

### API

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/assignments?week_start=YYYY-MM-DD` | `{"assignments": [...]}`: every assignment not completed, ordered by `due`; `include_completed=true` adds every completed one. Each also carries `planned_min` and `unplanned_min` for that week. `week_start` follows the Monday rule. |
| PUT | `/api/assignments/{id}` | A body with `revision` 0 creates it, stored at revision 1; otherwise it updates with a revision check (409 on mismatch). An identical body returns 200 with the revision unchanged, checked before the revision, as for weeks. |
| DELETE | `/api/assignments/{id}?revision=N` | 409 on a stale revision, 404 when unknown. Removes the assignment's sessions from every week of the account in the same transaction. Returns `changed_weeks` with their new revisions, and `removed_sessions` by `week_start` so undo can put them back. |
| PUT | `/api/week` | Every `assignment_id` must name an assignment of this account (422, without revealing whether the id exists elsewhere). Session copies are rewritten from the assignment before the identical-save comparison, and the rewritten blocks are what is stored and returned. |
| POST | `/api/solve` | Adds `week_start`. When any block has `assignment_id` and `week_start` is missing, the response is 422. `SolveRequest` currently ignores unknown fields (`backend/models.py:202-217`, no `extra="forbid"`), so the field is declared explicitly. The server reads the referenced assignments of this account; an id that is not this account's is 422. |
| POST | `/api/changes` | Applies several week and assignment writes all or nothing, in one transaction: `{"weeks": [{"week_start", "blocks", "revision"}], "assignments": [{"id", "assignment", "revision"}]}`, where a null `assignment` deletes. Any stale revision is 409 and nothing is stored. Returns the new revisions. Used for every change that touches more than one week or assignment. |

The assignment request model forbids unknown fields, like `SavedWeek`
(`backend/app.py:49-59`).

### Migration

One idempotent startup migration in `backend/storage.py`, inside one
`BEGIN IMMEDIATE` transaction, following `docs/dated-weeks.md`:

- Create the `assignments` table: `user_id`, `id`, a JSON body and `revision`,
  primary key `(user_id, id)`.
- Every flexible block without `assignment_id` becomes one assignment and one
  session:
  - Assignment id: `a-` followed by the first 32 hex characters of
    SHA-256 of `week_start + ":" + block id`. Deterministic, so reruns match.
  - `due`: a weekday `latest` becomes `week_start + weekday` at that time. A bare
    `HH:MM` or a leftover ISO value uses the block's last candidate day, as
    `parse_deadline` does. No `latest` becomes that week's Sunday at 23:59.
  - `estimate_min` is the block's `duration_min`. `focus_minutes` and
    `focus_sessions` move from the block to the assignment.
  - A completed block makes a completed assignment; `completed_at` is the end of
    its placed slot, or that week's Sunday at 23:59 without one.
  - The block gains `assignment_id`, loses `latest`, and keeps `start`,
    `completed` and `completed_day` as session history.
- Locked pomodoro chunks that share a `pomodoro_parent_id` become one assignment
  keyed by that parent id (same hashing). `due` is that week's Sunday at 23:59,
  because splitting already dropped the deadline. `estimate_min` is the total of
  the work chunks, progress comes from their focus fields, and it is completed
  when every work chunk is. Work chunks gain `assignment_id`.
- Locked blocks that are not pomodoro chunks are left as they are.
- Week revisions do not change. New assignments are stored at revision 1, the
  same as one created through the API. Blocks that already carry
  `assignment_id` are skipped, so running twice is a no-op.

### Old weekday deadlines on saves (decision 3)

`PUT /api/week` still accepts a flexible block with `latest` and no
`assignment_id`. The server applies the migration rules above using the body's
`week_start`: it creates the assignment if that id does not exist, and stores
the block as a session. An existing assignment is not changed by such a save.

### Frontend

- Adding homework creates an assignment (title, due date and time, total time)
  and one work session in the week on screen.
- Due times come in 15-minute steps plus 11:59 p.m. Due dates may be in later
  weeks.
- Candidate days run from today (in the current week) through the earlier of
  the due date and Sunday.
- A week lists open assignments due during or after it that still have
  unplanned work, as "Continuing". **Plan the rest here** adds a session with the
  unplanned minutes.
- A deadline outside the week on screen shows its date, for example
  "Tue Sep 15, 11:59 p.m.".
- Export writes format version 2 with the referenced assignments and their ids.
  Import accepts versions 1 and 2. An imported assignment reuses an existing one
  only when its id, title and `due` all match; otherwise it gets the migration's
  deterministic id against the destination week. Importing the same file into
  the same week twice adds nothing, and importing it into another week creates
  separate assignments.
- A week holds at most 100 blocks (`backend/models.py:157`). Plan the rest here,
  pomodoro splitting and any replan that would go past it are refused with a
  plain message before saving; the server's 422 stays as the backstop.

## 2. Focus minutes versus completion

### Today

A work session credits the block's `focus_sessions` and `focus_minutes`, and
the block becomes `completed` once `focus_minutes >= duration_min`
(`frontend/focus.js`, `creditFocusSession`).

### New

- Focus sessions credit the assignment, and never complete anything by
  themselves.
- When a work session ends, the student chooses:
  - **Finished**: completes the assignment and marks the current session
    completed in its slot, saved together through `POST /api/changes`.
  - **Need more time**: asks how much (15-minute steps) and adds it to the
    assignment's `estimate_min`. The assignment stays open, and the week asks to
    update the plan.
  - **Take a break**: starts the break; the assignment stays open.

## 3. Timer lifetime

### Today

Timer state lives only in page memory (`focusState`, `frontend/app.js:702`).
Switching weeks resets it (`frontend/app.js:853`), signing out resets it
(`frontend/auth.js:27`), a reload loses it, and starting another timer replaces
it without asking (`frontend/focus.js`, `startFocus`).

### New

- A running or paused timer survives switching weeks.
- Reload: the timer is kept in `sessionStorage` under
  `flexweek.focus.<account id>`. It holds only ids and times: assignment id,
  session id, `week_start`, phase, and `endsAt` or `remainingMs`. Titles are read
  after sign-in, so no assignment text is stored in the browser. After a reload
  the same account's timer resumes. If it ran out while the page was closed, the
  session-end choices appear instead of silently crediting minutes.
- Starting a timer while another is running asks before replacing it.
- Signing out or switching accounts clears it.
- **Quick focus**: a session with no assignment, labeled "Quick focus". It
  credits nothing.

## 4. Undo, redo and safer deletes

### Today

There is no undo. Delete and "Remove this day" save at once
(`frontend/app.js:989`, `frontend/app.js:1561`). Clear week asks with
`confirm()` and then saves (`frontend/app.js:2072`).

### New

All client-side, using the endpoints above.

- The client keeps, per account, a history of changes to weeks and assignments:
  create, edit, move, resize, delete, remove one day, clear week,
  missed-occurrence replan, pomodoro split, assignment edits and deletes,
  Need more time and Finished.
- History holds 50 steps in page memory. It is cleared on sign-out or account
  change and is not kept across reload; restore points are Stage 3.
- **Undo** saves the earlier state through the normal revision-checked writes.
  A step that touches one week or one assignment uses its `PUT`. A step that
  touches more than one, such as undoing an assignment delete (putting back the
  assignment and its `removed_sessions`) or undoing Finished, goes through
  `POST /api/changes`, so it is all or nothing. On 409 nothing is stored, undo
  stops and the existing conflict flow appears, so newer work is never
  overwritten. **Redo** works the same way, and any new edit clears redo.
- A replan that changes stored blocks is one undo step. A plain Solve changes no
  stored blocks, so it is not an undo step.
- Undo is visible after each change, in the status bar and in the notice after a
  delete. Keyboard: Ctrl/Cmd+Z, and Ctrl/Cmd+Shift+Z or Ctrl+Y for redo, not
  while typing in a form field.
- For repeating blocks, the menu and editor say "Remove Tuesday only" or
  "Delete all days". Deleting homework asks whether to remove this session or
  the whole assignment. Clear week moves into a secondary menu and can be
  undone.

## Ownership

- **Grok, backend:** the `assignments` table and model, `assignment_id` on
  blocks and its validation, the three assignment endpoints and
  `POST /api/changes`, the week `PUT` rules, the solve `week_start` adapter and slack, the migration including
  pomodoro chunk groups, old weekday deadlines on saves, and backend tests.
- **Claude, frontend:** assignment entry and due date and time, Continuing and
  Plan the rest here, deadline display, candidate days, export and import format
  2, session-end choices, timer lifetime, Quick focus, undo and redo, delete
  wording and the Clear week menu, frontend tests and a WebEngine probe.
- **GLM, helper:** boundary fixtures and first-pass review of both pull
  requests. Whoever asks GLM checks its output.

## Tests both sides add

- Deadlines: next Tuesday 23:59 with sessions on Sunday and the next Monday; a
  Sunday 23:59 deadline; a Monday 00:00 deadline in the following week; a
  deadline before the week starts; 23:59 against the 23:00 grid end.
- Assignments: one assignment credited from sessions in two weeks; planned and
  unplanned minutes per week; Finished stops later sessions being placed; delete
  removes sessions in every week and bumps those revisions; 409 on stale
  revisions; account isolation, including another account's `assignment_id` in a
  week save or a solve; the 1000 limit.
- Atomic changes: a batch with one stale revision stores nothing; undoing an
  assignment delete restores every removed session; a completed assignment's
  finished sessions keep their slots and its open sessions leave the trace.
- Migration: idempotent; keeps week revisions; weekday, bare-time, no-deadline
  and completed blocks; pomodoro chunk groups; a block with both `assignment_id`
  and `latest` is rejected.
- Timer: finishes without completing, survives switching weeks and a reload,
  never replaces a running timer without asking, clears on sign-out.
- Undo: after a delete, a clear week, a replan and an assignment delete; undo
  blocked by a 409; redo cleared by a new edit; history cleared on account
  change.

## spec.md changes on approval

- Required Behavior: assignments with `due`, `estimate_min`, progress and
  completion; flexible blocks are work sessions with `assignment_id`; old
  `latest` migrated and still accepted on saves; focus minutes never complete
  anything.
- API: the three assignment endpoints, `POST /api/changes`, `week_start` on
  `POST /api/solve`, and the week `PUT` rules. The deadline format sentence is replaced.
- Architecture: an `assignments` table; the time model adds naive local
  date-times for deadlines, still with no timezone math; the migration.
- Acceptance Criteria: add Stage 1's "Complete when" scenario.
- Unrelated drift fixed in the same edit: the Windows download is now
  `FlexWeek-Windows-x64-Setup.exe`, with `FlexWeek-Windows-x64.msi` for schools
  (spec.md "Downloads", the Deployment note, and the download-names criterion).

## Details confirmed by the owner (2026-09-13)

- **Finished** leaves later sessions stored but unplaced, rather than deleting
  them.
- Deleting an assignment deletes its sessions in every week.
- A save that still uses old `latest` never changes an existing assignment.
- Hiding assignments completed more than 28 days ago was not accepted. The list
  leaves out completed assignments unless the client asks with
  `include_completed=true`, which returns all of them.

## Addendum 2026-09-22: pinned sessions

`TimeBlock.pinned` is a boolean, default `false` and omitted at its default. It is
valid only on a flexible block with a `start` on exactly one day. The server refuses
the week otherwise.

A pinned session is homework the student placed by hand. The solver keeps its day
and start, counts its time as taken, and books nothing over it, in every solve
mode. A fixed block placed over a pinned session still takes its time on the
desktop, which clears `pinned` along with `start`.
