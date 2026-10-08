# roadmap.md — FlexWeek

Congressional App Challenge 2026. Submit **Sunday, Oct 25, 2026, 8:00 p.m. PDT**
(hard deadline Monday, Oct 26, 9:00 a.m. PDT).

History up to 0.18.0 (Phases 1–7, the student experience stages, the native
desktop units, the 0.10.1 and 0.11 polish, the web client's retirement, the
first implementation slice) was removed from this file on 2026-10-02. It is in
this file's git history, in `CHANGELOG.md`, and in `docs/cac-build-plan.md`.

## Where things stand (2026-10-04)
- v0.18.1 is released as latest. v0.18.0 brought the Rust engine.
- 0.18.2 is batch A alone (seven lanes, written by Grok, reviewed and fixed
  by Claude), versioned and checked on `release/0.18.2`: whole suite and all
  seven rigs pass. It waits for Jonathan's look at #98 and his word to ship.
- Batch B moves to 0.18.3 and still waits for mockup round 2.
- Decisions left open by 0.18.1 are listed under "Open after 0.18.1".
- 21 days to the contest submission (Phase 8).

## Phase 8 — Contest delivery (Oct 25, 2026)
- README with account setup, both contributors and the AI-assistance disclosure.
- Contest recording using an account-created schedule, plus the submission form.
- A hand check of the Windows installers on a real PC (never done; CI installs,
  opens and uninstalls them).
- Which 0.18.x build the recording uses is Jonathan's call. 0.18.1 is the
  earliest with the Fix-first findings closed.
- Complete when: submission on Oct 25 evening, 2026.
- Status: [ ] open.

## Open from earlier plans
- Student trials (first use, several assignments, an impossible workload, a
  missed session, next-week reuse, recovery from an edit) and the task-time
  comparison against the first UI. Year view stays optional.
- Looks live on this computer, not on the account. The account fields for
  them (Amendment A of `docs/stage8-appearance-contract.md`) were never
  approved; whether looks should follow the account is an open decision.
- A Test or Preview of a reminder from the desktop tray was planned in the
  comfort stage; it is not in the native Settings. Confirm it was dropped on
  purpose, or add it.

## 0.18.x series — from the 0.17.2 audit (planned 2026-10-02)

Source: the merged audit `final-report.md` (Timmy, UI Designer, Coder, Assistant
Local), 102 findings, every one seen on 0.17.2. Each release re-checks its
findings on the current build first; a finding that no longer reproduces is
closed with the frame that shows it. Restyles are chosen from mockups drawn
with the app's own stylesheet before they are built; behaviour fixes do not
wait for mockups.

Decisions taken 2026-10-02:
- Everything goes into the series: Fix first in 0.18.1, Next patch over 0.18.2
  and 0.18.3, the "maybe on purpose" items decided at 0.18.3.
- Finding 32: rename "At a set time" to "Due by" on the Due row, refuse a past
  deadline, AND add a separate, clearly named "Do it at" choice.
- J3 (Spotify): a block start plays its own link, else the Settings link when
  Sound is Spotify; reminders stay Chime. J7: preferred study hours merge into
  allowed as one Study hours list. (Both 2026-10-02.)
- 0.18.2 is written by Grok and reviewed by Claude (2026-10-03).
- Overlaps: one rule everywhere. Duplicate and the paste preview stop on an
  overlap ("Resolve conflicts…") while drag and the editor only warn ("Both
  will show, side by side"). The preview gets the same warning line and Save
  stays enabled; copy day and apply routine follow the same rule. Goes in the
  0.18.1 grid and keyboard lane with finding 20.

### From Jonathan while using the app (running list)
Gripes reported in conversation. Each gets a J-number here, then a lane; the
lane entry carries the number so nothing is lost between sessions.
J1 to J6 shipped in 0.18.1, with the first two parts of J12. J7 to J12 are
in 0.18.2.
- J1 (2026-10-02): an End of 00:00 is refused ("End must be after Start") in
  the block editor, Setup's school and activity hours, the School hours sheet
  and study hours. Read it as 24:00, drawn as "24:00" (12:00 AM on the 12-hour
  clock); the engine already accepts a block to the end of the day. Running
  past midnight in general is not included. → 0.18.1 time entry.
- J2 (2026-10-02): Duplicate stops on an overlap while drag only warns. →
  decision above; 0.18.1 grid and keyboard.
- J3 (2026-10-02): the Spotify link has six surfaces and three rules. Settings
  Reminders, Setup's Reminders page, the alarm form, the fixed-block editor,
  the homework editor and the Focus screen all take a link; reminders never
  play it, alarms use the default link, a block start uses only its own link,
  Focus uses the default. The Settings Play button previews what reminders
  never do, and the "one sound for everything" note is untrue for Spotify.
  Decided 2026-10-02: a block start plays its own link, else the Settings
  link when Sound is Spotify; reminder notices stay Chime; the field is
  relabelled as the default link for alarms and block starts; Play previews
  that; the start window widens to the reminder lead. → 0.18.1 one source
  per setting.
- J4 (2026-10-02): the reminder lead has three defaults: Setup's first run
  sets 10 min, Settings and the backend default to 5, Setup's summary line
  says 5 when the key is missing. → one source per setting.
- J5 (2026-10-02): the homework cutoff has two pickers: Setup offers 20:00 to
  23:00 in half hours, Availability's unlabelled dropdown every quarter hour
  from 06:15 to 23:45. → one source per setting.
- J6 (2026-10-02): the snooze length and the reminder window are defined in
  both the Python reminder module and the engine's Rust one; the snooze
  button label reads one copy, the logic runs the other. → one source per
  setting (the Python copies read the engine's).
- J7 (2026-10-02): three overlapping ways to say when homework may go:
  Setup's Homework time writes the planning hours; Availability shows
  "Preferred study hours" as a second list, then the planning hours again
  under "When may FlexWeek plan homework?", then a cutoff. Both lists reach
  the solver, and Setup fills only one. Audit finding 54 saw the symptom.
  Decided 2026-10-02: merge preferred into allowed. One list named Study
  hours, filled by Setup and edited in Availability; the solver gets one
  input; protected time and the cutoff stay. → 0.18.2 sheets lane with #54.
- J8 (2026-10-02): Timeline's fold is fixed at half the width with Mon to Wed
  on the left page and Thu to Sun on the right; nothing adjusts it. Decided:
  a draggable fold, remembered per design, with a rule for which day moves
  pages as it slides. → 0.18.2 Designs lane; mocked up first.
- J9 (2026-10-02): Mission draws any block of 30 minutes or less as a tick,
  named only on hover, in its day and week lanes. Decided: every block keeps
  its bar and icon down to a minimum width, title cut first; a tick only
  when there is truly no room. → 0.18.2 Designs lane.
- J10 (2026-10-02): Clay's day cards share one scroll, so scrolling the
  front card scrolls its neighbours; the neighbours peek at full strength;
  only the arrows and the wheel switch days. Decided: neighbours dimmed and
  still, only the front card scrolls, a horizontal drag on the row switches
  days as the arrows do. → 0.18.2 Designs lane; mocked up first.
- J11 (2026-10-02): the now line stops 3 px short of a block's words and
  icon and resumes after them, which reads as the line being cut. Decided:
  one continuous line drawn under the text. → 0.18.2 Week behaviour lane.
- J12 (2026-10-02): the Settings slide-in stuttered. Done in 0.18.1: a
  picture of the page slides instead of the page drawn through an effect
  (13 paints a slide became at most 3), and the design preview pictures wait
  until the slide has landed (the first open went from 3 or 4 frames to 13).
  Left, decided 2026-10-03 for 0.18.2: Settings takes about 170 ms to build
  before the slide can start, on every open, because the page is rebuilt each
  time; build it ahead or keep it between opens. → 0.18.2 Plan lane with #98
  (same motion code).
- J14 (2026-10-08): the animations still lag, everywhere about equally:
  changing page or view, sheets opening, dragging and sliding. Widgets draw
  on the CPU, so a GPU switch alone would not help much. Likely costs: fades
  through an opacity effect on whole page parts (`motion.appear`,
  `fade_through`), drop-shadow effects re-blurred under anything that
  repaints (`elevation.lift`), a widget re-laid out each frame (`glide`), and
  the hours repainting while things move. Decided: measure first (frame
  times for each animation on the built app, worst first), then animate
  still pictures where effects are the cost, as J12 did for the Settings
  slide. → 0.18.4.
- Noted, no new item: appearance lives on the account (pack and accent from
  short lists) and on the device (look, any-colour accent, knobs); this is
  the open decision about looks following the account.

### 0.18.1 — Broken things (released 2026-10-03)
The 20 Fix-first findings, J1 to J6, the engine leftovers and eight coupled
Next-patch items (#6, #7, #42, #46, #50, #53 rounding, #76 sheet), plus the
first two parts of J12. Built in eight lanes on `release/0.18.1`, merged as PR
40, published as latest; `CHANGELOG.md` lists every change.
- Re-checked away with evidence: #64 (the code never offered the running
  version; a test now pins it), #10 (rail and panel agree; guard test added),
  #6 as worded (a carried block lands where it is dropped; a new block's start
  was fixed with #7).
- Status: [x] released 2026-10-03. Gate 2790 passed; rig passed on classic,
  Timeline, Mission, Clay, Bento and Retro; CI green including the whole
  mutation job.

### Open after 0.18.1 (decisions and checks for Jonathan)
Decisions, each with the recommendation:
- **Typed dates.** A date typed without a year means the next time it comes,
  so typing 1 Oct on 2 Oct gives 2027, the symptom #35 complained about.
  Recommended: keep this year for a date just passed and let "That time has
  already passed." speak instead.
- **Two placement buttons in Edit homework.** "Choose a time…" and "Let
  FlexWeek move it" now double the When row in other words. Recommended:
  remove both, after moving the conflict warning into the When row. (Goes
  with batch B's Add/Edit homework lane.)
- **Delete key.** It deletes the focused block at once with Undo in the
  toast; the menu's Delete asks first. Keep, or make the key ask.
- **Drag step.** Clicks, the free-time menu and new blocks snap to 15 minutes;
  moving and resizing follow the 5 or 15 setting. Keep, or snap all to 15 and
  drop the setting.
- **Blocks that share a time.** The arrow keys reach only the first; add a way
  to cycle (for example Tab inside the slot), or leave.
- **Amber conflict row in dark looks.** It keeps its light fill: readable but
  bright. Keep, or a dark amber in dark looks.
- **Running late notice.** The toast's 420 px maximum is unchanged, so
  "Running late: 16:30–17:00 is now locked. 2 moved." takes two lines. Widen
  the toast, or keep.
- **Setup's First homework page** has no Save on the date, so the
  past-deadline refusal does not cover it. Add it there, or leave.
- **`hypothesis`** is used by no test since the differential tests went.
  Remove it from `requirements-dev.txt`, or keep.
- **Lost cover.** About 100 cases the deleted differential tests pinned have
  no Rust test of the same case. By module: solver (subject windows and case
  folding in the reschedulers; empty work and study windows; a clock error
  after the first reading); casefold (no tests at all); slots and weeks (year
  9999 bound, Arabic-digit and full-width inputs); plan (`due_from_latest`,
  `completed_at_for_block`, `prepare_solve` outputs); restore and transfer
  (`canonical` on 2^64, `diff_snapshots`, `diff_transfer`, the 300 000-byte
  limit); explain (`slack_sentence` pairs); store migration (22 odd stored-row
  cases); store helpers (weeks, assignments, routines, preferences, restore
  points, operations, `replace_account`, recovery codes, sessions,
  `delete_account`); desktop logic (`release_from_page` hostile tags, DST
  `clock_parts`, the alarm window, pasted series day order, planner titles in
  Berlin and New York, deep-nested week files). Port a chosen subset to Rust
  tests, or accept the gap. Recommended: port the solver, store-helper and
  `release_from_page` cases.
- **Test tidy.** The logic tests' shared helpers are merged; cutting
  overlapping and slow tests by break-it was not done. Do it, or drop it.

spec.md drift, proposed wording awaiting approval (spec.md is changed only
with Jonathan's word):
- Validation, the CI desk step: "the desktop engine suites offscreen (the
  token and updater tests, `test_tokens.py` and `test_update.py`, which do not
  depend on fonts)".
- Reminders: "A block that starts plays its own Spotify link; with none, the
  Settings 'Default Spotify link' if Sound is Spotify. Reminder notices before
  a block, and the end of a focus session, always play Chime. The song window
  is the reminder lead, never under 2 minutes."
- "The reminder lead defaults to 5 minutes everywhere; the engine owns that
  number."
- "'No homework after' offers No limit and 20:00 to 23:00 in half hours, in
  Setup and in Availability."

Not yet checked on real hardware: the Windows installers on a real PC (Phase
8); the right-click fix on a real X11 or Wayland session; alarm sound and
Spotify on a real speaker; the new time box and the keyboard grid under real
hands.

### 0.18.2 — Behaviour and layout
Decided 2026-10-03: Grok 4.7 writes the code; Claude writes Grok's prompts,
reviews every branch (reads the diff, reruns lint, types and tests) and
merges into `release/0.18.2`; Jonathan decides what ships. Batch A needs no
mockups and goes first. Batch B waits for mockup round 2. Branches:
`grok/0182-<lane>`. Each finding is reproduced by a failing test before it is
fixed; one that does not reproduce on the current build is closed with that
test. Decided 2026-10-04: 0.18.2 ships batch A alone; batch B moves to 0.18.3.

#### Batch A, lane 0: repairs to what 0.18.1 shipped (merged 2026-10-04)
- Homework blocks in Timeline, Mission, Bento, Retro, Clay and One thing lost
  their time line and edge, and the hours stopped painting after them (the
  now line ended at that day): their colour tables had no `block_edge`. Done:
  every design's table has one, and a test paints planned and pinned homework
  through every design's painter in light and dark.
- The rig printed "4/4 passed" after stopping at scenario 5 of 17 on that
  error, which is how it shipped. Done: a run that ends early or logs a Python
  error says STOPPED, names the scenario, exits 1 and lists the scenarios that
  did not run.
- Add homework's past-deadline check took the date from one clock and the time
  of day from another, so a test failed every afternoon. Done: one clock.
- `test_every_field_in_a_forms_column_starts_at_the_same_left_edge` failed
  only in the whole suite: after a test that cached the design pictures it
  read the page while Settings was still sliding in. Done: it waits for the
  slide to finish. Each test's windows are now deleted after it, which kept a
  4-worker run to about 1.4 GB.

#### Batch A, lane 1: times and words on blocks (merged 2026-10-04)
- #13 In Today's app, Paper and Timeline a 45-minute "Math worksheet"
  (17:00–17:45) shows its name only; Clay and Retro show "Math worksheet
  17:00". Done when every design writes a short block as its name, then its
  start.
- #80, #85 At 810 px wide, and in the 12-hour Week, a block shows "08:30" and
  "14:15" (or "8:30 AM" / "2:15 PM") on two lines with no dash, which reads as
  two events; overlapping blocks read "Soccer | Pract… extra"; the rail's
  timer list clips "Mon 06:0(". Done when the time stays whole and the title
  is cut first: the range on one line ("08:30–14:15", "8:30 AM–2:15 PM"), the
  duration dropped first, then the start alone; never two stacked times.
- #81 Friday's header at 810 px and Bento's day cards show "2 h 15", which
  reads like a time of day. Done when it is "2h 15m" at every width.
- #14 Timeline's "Due this week" and Day list placed times ("History essay
  Fri 15:30" though it is due Sun 4 Oct); "Unfinished homework from earlier
  weeks" lists items due today and tomorrow. Done when a deadline reads "due
  Sun 4 Oct" and a block "placed Fri 15:30", as Bento and Retro do, and the
  Unfinished list holds only overdue items.
- J11 The now line stops 3 px short of a block's words and icon and resumes
  after them, which reads as the line being cut. Done when it is one
  continuous line drawn under the block's text and icon, in every design that
  draws through the shared hours canvas.

#### Batch A, lane 2: week behaviour (after lane 1; both touch the canvas) (merged 2026-10-04)
- #15 A block can be dropped onto a past day with no warning; the drag ghost is
  tan and cuts "Math worksh…" with room to spare; the placed block loses its
  book icon. Done when a drop in the past is refused with "That's in the past."
  and the block goes back, the ghost takes its category's colour and writes
  the whole name when it fits, and the icon stays.
- #16 An empty week shows no prompt, and the Routines sheet is a blank list.
  Done when an empty week offers "Copy last week's fixed times" and "Use a
  routine", and an empty Routines list says "No routines saved yet."
- #17 The Unfinished card, the "Hide" row and the plan panel take the top
  300 px, so an 800 px tall window shows about 3 hours of Day. Done when the
  Unfinished card collapses to a one-line badge after its first showing in a
  session, and the badge opens it again.
- #18 While a timer runs, Today's app shows a three-line rail card saying
  "focus" four times; other designs show a one-line strip. Done when Today's
  app shows the same strip ("Session · 29:42 left · Focus screen").
- #20 The block menu has both "Delete" and "Delete homework", a "Finished" tick
  that looks checked, no Copy (though Paste's hint says "Copy a block or a day
  first."), and is 155 px wide against 390 px for the free-time menu. Done
  when both menus share one width and keycap style, there is one Delete (for
  homework it asks which, as the editor does), and Copy is there.
- #82 Below 1100 px "Not placed yet: 1" is a bare bold line that does not look
  clickable. Done when it is a chip with the book icon and a chevron.
- #83 "Plan my homework" shrinks to "Plan" at Large text and at 1100 px but not
  at 900 px. Done when one rule holds at every width and text size: the label
  keeps its words while they fit, then "More" collapses to its icon, then the
  label drops "my".

#### Batch A, lane 3: designs (merged 2026-10-04)
- J9 Mission draws any block of 30 minutes or less as a tick, named only on
  hover, in its day and week lanes. Done when every block keeps its bar and
  icon down to a minimum width, the title cut first, and a tick appears only
  when the bar would be under 8 px.
- From the 0.17.3 list: Bento's now pill sits inside today's column; Mission's
  names beside a block are crossed by the now line; Clay's Day card has no
  hours for about 100 ms as it slides in; Mission's 00:00 label sits 6 px left
  of the canvas; 12-hour times are cut at Large text and 810 px in Clay's Day
  summary and Retro's deadlines; Bento's header shortens to "F 2" there. Done
  when each is gone.
- #24 Bento shows "8 h 15 min planned" twice and counts School and Soccer while
  Mission says "Planned today 0 min"; Bento says "Nothing free before 22:00" at
  22:49; Timeline's "0 not placed yet" repeats "Nothing is waiting for a
  time." Done when "planned" means placed homework time in every design,
  counted in one place; after the last study hour it says "Nothing free now";
  and each doubled line is said once.

#### Batch A, lane 4: keys (merged 2026-10-04)
- #88 F1 opens no Help and Ctrl+N does not open Add homework. Done when both
  work from the week page and both are listed in Help and in Ctrl+K.
- #89 The Ctrl+K palette is cut at the window's bottom; the hovered row and the
  Enter row look the same; it says "Customise look…"; typed letters are not
  highlighted; "choose" finds nothing. Done when the list fits the window,
  hover is a lighter tint than the Enter row, matches are highlighted, it lists
  Alerts, This computer and Choose a time, and the look entry uses the app's
  word for it.

#### Batch A, lane 5: messages (may change the engine) (merged 2026-10-04)
- #44 Late in the day Plan says "That does not fit in the times you set aside
  for work." when today's hours are over or the deadline has passed; the
  nothing-placed toast reads "Planned 0 homework blocks. 1 still needs a
  time." Done when a passed deadline says "That time has already passed.", due
  today with no study time left says "Due today and no study time is left
  today.", and nothing placed says "Nothing placed. 1 still needs a time." The
  first two are new reasons from the engine, with Rust tests.
- #99 Offline, Plan says "Could not reach FlexWeek. Your changes may not have
  been saved. Try again." though Plan changed nothing; Save says "Not saved.
  … may not have been saved." Done when Plan says "Can't reach FlexWeek, so
  nothing was planned. Try again." and Save says "Not saved yet. Your changes
  are kept on this computer, and FlexWeek will try again."
- #72 "Wrong username or password…" shows on Reset your password before
  anything is typed; "Incorrect username or recovery code." follows back to
  Sign in; "Signed out." stays on the Reset page. Done when a page's message
  clears whenever the page changes.
- #75 About and Manage account say "Your plans are saved on this computer.",
  Create account says "Your week is saved to your account.", Sign out says
  "Your week stays saved on this computer." Done when one true sentence is used
  everywhere: the week is saved on this computer, under this account.
- #45 More › "Undo, copy and save" showed Undo greyed right after a replan
  though the toast offered Undo; the submenu says "Save / Restore / Reload"
  without saying what. Done when the menu's Undo is enabled exactly when the
  toast's is, and each action is named in full ("Save a copy of this week…").
- #3 A new row in Setup's "Sports, clubs and jobs" defaults to Activity, so a
  typed "Soccer" gets the Activity colour everywhere. Done when common sport
  names in the title (soccer, football, basketball, swim, track, tennis,
  volleyball, baseball, hockey, practice, …) make it Sports, else Activity,
  and the student can still change it.

#### Batch A, lane 6: opening Settings and the plan panel (merged 2026-10-04)
- J12 (rest) Settings takes about 170 ms to build before its slide can start,
  on every open, because closing deletes the page and opening builds it again.
  Done when the slide starts within one frame of the click (build ahead while
  idle, or keep the page between opens), it still shows what the account holds
  when it opens, and another account never sees the previous one's settings.
  Measured before and after.
- #98 After Plan the toast appears, then the plan panel pops in with "Got it"
  drawn as a blank grey bar for one frame, pushing the week down about 78 px.
  Done when the panel slides in over the space it takes, drawn whole in the
  same frame, at the app's motion level (no movement at Off).
- #65 In Settings › Alerts the alarm list shows no focus or selection with Tab
  or the arrow keys, so a keyboard user cannot tell what Remove will remove.
  Done when alarm rows show a focus ring and a selection.

#### Batch A: checks before 0.18.2 ships (2026-10-04)
- Fixed after the whole-suite and rig runs: with the rail folded, waiting homework opens in place
  under the line (no popup) and can be dragged with a real pointer (its chips were 0 px wide);
  the page margins are back, and the top bar shortens in one order (date, More, "Plan
  homework", "Plan"), fitted as Large text arrives; Unfinished opened by the student stays open
  when the week changes (the whole-suite failure of
  `test_unfinished_opens_its_list_in_any_design`).
- Final check (2026-10-04): whole suite 2893 passed, 0 failed; rigs classic week 18/18, timeline
  week 17/17, timeline day 14/14, mission week 17/17, bento week 17/17, clay day 14/14, retro
  week 17/17 (after the rig's Large-text step waited for the bar to settle).
- Left: Jonathan's look at #98's sliding plan panel; then the PR and the release on his word.
  `test_ui_dialogs.py::test_work_windows_can_be_added_edited_and_removed_in_settings` fails when
  its file runs alone (622 px against 640), on main too.

#### Batch B (moved to 0.18.3 on 2026-10-04; after mockup round 2)
Mockup round 2: Setup's Style page and page layout; Add and Edit homework with
Spread beside Estimated time, the Placed line and the empty link and step
lists; the Placed panel; Choose a time; Add fixed time; Availability with one
Study hours list; Help, Routines and About as one sheet family; the Appearance
page; the Settings forms; the sign-in error and the password eye; the Focus
screen's controls; Timeline's fold handle; Clay's dimmed neighbours. Drawn
with the app's own widgets and stylesheet; Jonathan picks; behaviour inside
them waits for the pick.
Picked 2026-10-07 (boards in `docs/mockups/round2-0183/`), final after a second
look: Add and Edit homework B, a segmented "In one go / Spread over days" under
Estimated time with a grey line saying what Plan will do; Availability the B+C
mix with tabs (board 2b): a Mon–Sun strip of study hours, protected time and
the cut-off on top, then Study hours day by day as chips, Protected and
Cut-off as the other tabs; Setup's Style page C, one big preview at a time
with the neighbours peeking, arrows and dots; Timeline's fold B, a "‹ 3 | 4 ›"
handle on the fold in the day-name row, dragged or stepped, keyboard too; Clay
A at a 60 % veil (board 5b), neighbours still, a horizontal drag on a neighbour
or the gap switches days, never on the front card's hours; Focus A, Pause
filled with Skip and Finish outlined in one row, the ring at full accent
before Start, and Finish asking "End this session?". Group 2 (boards 7 to 9,
one proposal each to the "done when" below) approved with three calls: Running
late's row is Accept late start filled (greyed until a preview), Preview
outlined, Cancel bare; at Large text the title keeps 16 px from the switcher
even where that shortens Plan to "Plan" (1157 px); Add fixed time's Spotify
link moves under More details ("New event" is that sheet's old title, renamed,
not a second entry). Mockup round 2 is complete; batch B can start.

- **J13 Styles on every page (new 2026-10-07).** A style (Plain calendar,
  Night owl, Dashboard, Retro) changes only the week and day views; Settings,
  the sheets, Setup and sign-in take the look's colours and nothing else.
  Jonathan wants each style's feel on every page, including Setup (previewed
  as it is picked) and sign-in (the last style this computer used), keeping
  each page's layout, and the change made smoothly. Depth (fonts, shapes and
  chrome, or shapes and spacing only) is decided from a mockup: Settings and
  one sheet in each style at both depths. Mocked up first; built in 0.18.3
  after the pick. Picked 2026-10-07: depth 1, fonts, shapes and chrome (boards
  `10_styles_*`): Night owl's serif headings, tighter gaps and paper edge;
  Dashboard's title on the hero tile, its tiles and small shadow; Retro's
  pixel faces, bevels and Windows 98 frames. Plain calendar is unchanged.
  Merged 2026-10-07; the week and day pages keep their own design.

Batch B decisions, 2026-10-07 (from the lanes' reports): protected time can
carry an optional name (up to 40 characters; the chip shows it, else the kind);
old accounts whose only hours were "preferred" get those as their Study hours,
no whole-day fallback; the strip's legend says "Coloured: study hours"; the
Appearance page's design grids stretch like the look grids; Timeline's feet
follow the fold and reflow, and the fold is also a Settings option ("Days on
the left page"); Clay's neighbours open at the stretch the front card opened
at, and a long drag moves up to two days; Save with "Spread over days" drops
the open time and writes the spread sessions (no second sheet); "Do it at"
and Spread are exclusive; Setup previews Plain calendar as its page opens.
Merged into `release/0.18.3`: clay, settings, focus, account, availability,
timeline-fold, homework, setup, the Settings design-grid follow-up, sheets,
large-text, and J13 (2026-10-07, after three review rounds).

- **Setup.** #4 At 1280×800 the second row of style cards (Dashboard, Retro)
  is cut by the footer with no fade, the default card shows no selected state,
  each card shows two names, and only two columns are used. Done when the page
  scrolls with a fade above the footer, each card has one name, and the
  default is marked chosen. #5 The left edge shifts a few pixels between pages
  and each page mixes styles (day pills 10 px above the time fields, Bedtime
  not in a card, dropdowns with arrows and a black "Remove", "Takes" centred
  oddly, "Today's app in System", mixed ";" and "·"). Done when every Setup
  page has one content column and left edge, the same time box, and Remove and
  Skip outlined. #66 (Setup part) The planning-hours card on Homework time runs
  under the fixed footer. Done with a fade above the footer and bottom padding
  equal to its height.
- **Add and Edit homework.** #36 Due defaults to today even at 22:41, and the
  due time to 09:00 for something due today at 23:21; the "multiple of 15"
  hint leaves "45." alone on a line and stays when 60 is picked; the checkbox
  sits 6 px from the date; the title placeholder is "Homework" where Setup
  says "e.g. History essay"; Edit does not say when the block is placed; Notes
  has no label; two big empty boxes under "Add link" and "Add step" look like
  fields. Done when due defaults to tomorrow and the time to the end of the
  school day; Edit shows "Placed Fri 15:30" under the title; the toggle reads
  "More details ⌄" / "Fewer details ⌃"; Notes has a label; the gap to the
  scrollbar is 16 px; the year shows only when it is not this year; the hint
  shows only for an invalid value, in the error colour; and the link and step
  lists are hidden until they have entries (or one grey line, "No links yet").
  #37 Spread across days is offered only in Edit, at the bottom of More
  details. Done when a tinted "Spread across days" button sits next to
  Estimated time whenever the estimate is 60 minutes or more, in Add and Edit,
  its preview uses the unsaved values, and it comes after Estimated time in the
  Tab order. Plus the 0.18.1 decision on the two old placement buttons.
- **Placed panel.** #43 "+ Add" and "Got it" are both filled (both yellow in
  High contrast), and the panel repeats the toast with another verb ("Placed 2
  · 1 without a time" against "Planned 2 homework blocks. 1 still needs a
  time."). Done when Got it is tinted, + Add is the only filled button, and
  both places say "Placed".
- **Sheets.** #51 Choose a time: Day is a dropdown instead of day pills, Start
  is a borderless field, "Length 45 min" cannot be changed, and the button says
  "OK". Done with Mon–Sun pills, the outlined field, a "− 60 min +" stepper with
  length pills, the button "Choose this time", and one outlined input style
  with an accent focus ring. #52 New event: the menus say "Add fixed time…" but
  the sheet is titled "New event", its help says "Tick more days" though the
  days are pills, the "1 h" duration has no label, Category defaults to None,
  and there is a Spotify field. Done when it is titled "Add fixed time", says
  "Pick more days to repeat it", labels the duration and guesses the category
  from the time of day. #53 (rest) Running late's Preview is plain text, and
  while viewing next week it refuses with "Open this week before using Running
  late." though the menu item is enabled. Done when Preview is outlined and
  the item either jumps to this week or is greyed with the reason. #54 and J7
  Availability: "Protected time" and "Preferred study hours" are big empty
  boxes with no hint, the add buttons are borderless text, a "From 19:00 to
  21:00 Any subject" row floats between sections with no remove control, and
  Preferred study hours is empty though Setup set planning hours. Decided
  2026-10-02 (J7): merge preferred into allowed, one list named Study hours,
  filled by Setup and edited here; the solver gets one input (an engine change
  with Rust tests, and saved preferred windows carried into the one list);
  protected time and the cutoff stay. Done when each question sits above its
  control, empty lists have a grey hint, add buttons are outlined, and the one
  list shows what Setup set. #55 Help, Routines and About open at different
  heights and Help's last row touches the bottom; Routines repeats its heading
  as its button, writes "Mon, Tue, Wed, Thu, Fri" not "Mon–Fri", and shows
  Apply and Delete with no routines; School hours mixes inline "from/to" with
  labels above. Done with one top offset, bottom padding, a reworded Routines
  heading, day ranges, and labels above fields.
- **Settings.** #66 (Settings part) The Alerts form, the "Use the accent on
  category chips" row and the accent names at 1024 px run under the fixed
  footer. Done with a fade and padding. #67 Appearance: "Wearing Poster" sits
  under the grid instead of under the chosen card, and nothing shows for Light
  or System; the grids leave 75–190 px empty on the right; the button says
  "Customise…"; Today's app's description says "Its colours are the Look
  menu." Done when the chosen card is ringed, the grids stretch, the button
  reads "Edit your own look…", and the sentence is fixed. #68 In Focus the
  steppers are about 205 px wide while "Timer preset" is 115 px and sits below
  the values it sets; Alerts' widths are uneven and "No alarms yet." is black
  between grey hints; This computer's value column drifts. Done with one
  control width per column, the preset first, and every hint grey.
- **Account.** #71 Manage account's other actions looked like plain text and
  its password fields have no show/hide eye, unlike Sign in. Re-check the
  buttons after 0.18.1's sheets; done when the eye is there. #73 The sign-in
  error sits under the two links in plain black, grows the card, and reads
  "Wrong username or password. FlexWeek doesn't say which, so no one can find
  out who has an account." Done with a short red line with an icon under the
  password field and a "Why doesn't it say which?" link.
- **Focus.** #19 Before Start the ring is pale blue on white; Skip and Finish
  are plain text beside a filled Pause; Finish ends the session with no
  question; "Quick focus" hops 4 px on Start; the rail timer is bold mono; the
  rail's "Start a focus timer" list is a tiny scrolling box clipping "Fri
  17:0(". Done when the ring is at least 3:1, Skip and Finish are outlined,
  Finish asks "End this session?", and the rail list grows to its content.
- **Large text.** #84 The rail shows "Math worksh…", the block "Math…",
  "History / essay" wraps, and Week's day names are cramped; in High contrast
  the title sits 9 px from the view switcher and "High contrast" wraps in the
  look grid. Done when rail names wrap to two lines, the title keeps 16 px
  from the switcher, and look cards are as wide as their names.
- **Designs.** J8 Timeline's fold is fixed at half the width, Mon–Wed left and
  Thu–Sun right. Decided: a draggable fold, remembered per design, with a rule
  for which day moves pages as it slides; mocked up first. J10 Clay's day cards
  share one scroll, so scrolling the front card scrolls its neighbours, and the
  neighbours peek at full strength. Decided: neighbours dimmed and still, only
  the front card scrolls, and a horizontal drag on the row switches days as
  the arrows do; mocked up first.
- **Decision #41.** On a 60-item week Plan put 9 h 45 min of homework on
  Monday and 10 h on Friday, back to back from 06:00 to 23:00, while Saturday
  had 5 h and Sunday 5 h 30 min with empty evenings; work due Sunday went on
  Friday night. A fix spreads work toward the due date with a daily cap: a
  solver change in the engine. Jonathan decides; if yes, its own lane with
  Rust tests.

- Complete when: batch A and batch B are closed on the shipped build (or
  re-checked away with a test), #41 and the "Open after 0.18.1" decisions each
  have a recorded answer, the gate, the rig and CI's mutation job are green,
  `CHANGELOG.md` and the release notes are written, and v0.18.2 is published
  as latest.
- Status: [~] batch A released as v0.18.2 (2026-10-04). Batch B and J13 are
  merged on `release/0.18.3` (2026-10-08): whole suite, mypy, engine cargo
  checks and every rig green, CHANGELOG and release notes written, version
  0.18.3. Left: #41 and the "Open after 0.18.1" decisions, the push, CI and
  publishing, on Jonathan's word.

### 0.18.3 — Consistency and polish
Mockup round 3 before the Designs, Buttons and Sign-in lanes: the Day dial and
One thing (#25), the icons (#26), Paper's edges (#60), the sign-in pages
(#74), the focus ring (#92), outlined secondary actions (#90).

- **Designs.** #21 Clay: Soccer's visible sliver is a bare bar and Friday's
  side card an outlined bar with no name; the side cards use a smaller hour
  scale (27 against 38 px per hour), so rows do not line up. Done when every
  sliver writes its name and the cards share one hour scale (or the side cards
  become lists). #22 Retro: Week.exe's grid ends at "24:00" where every other
  design ends at 23:00, the Notepad's last line is cut, and "History…" and
  "Math…" are cut with no times. Done when it ends at 23:00, the Notepad
  scrolls, and a cut name shows its start. #25 Day: "Hours" is blue while
  "Agenda" is black, and the zoom − and + are greyed with no reason; Day dial:
  12 at the top, an unexplained dark wedge, unlabelled arcs, and an oversized
  "Nothing else scheduled today"; One thing: the empty state draws a full
  minute ring and an unlabelled bottom bar. Done when the wedge and arcs are
  labelled or gone, the heading is smaller, the bottom bar has times and
  labels, and the greyed zoom says why (midnight or noon at the dial's top is a
  choice to make). #26 "School hours…" in the Add menu uses a school building
  while School blocks use a faint light-blue house on pale blue, and "Replan
  all my homework" uses Activity's sparkles. Done with one School icon at 3:1
  or better and Replan's own icon. #60 Paper's cards are about 1.05:1 against
  the page, so their edges vanish; block icons are tiny and pale; timer digits
  are sans or mono in a serif look. Done with a 1 px warm-grey card edge at
  about 3:1 and darker icons.
- **Look editor.** #57 While a readability warning stands, the preview draws
  "Replan all my homework" and "Hide details" in lime at about 1:1, though the
  0.17.2 notes said a pale accent is drawn darker until fixed; and "Plan button
  words is 4.1:1" is ungrammatical. Done when affected words are drawn in the
  darkened colour while the warning stands and it reads "The Plan button's
  words are 4.1:1". #58 A single row's Fix darkens only enough for that row, so
  another row can still fail, and it can turn a pale colour into a hueless
  grey. Done when each Fix aims for the hardest check and changes lightness
  only. #59 The "Any colour" swatch and code box do not line up with the
  Page/Cards/Text/Lines column; Reset all, Export and Import have no outline;
  "Start from" is a plain dropdown; the "…follow from these four" note is cut
  by the footer. Done with one label column, outlined buttons and the preview
  grid for Start from (re-check after 0.18.1's colour picker sheet).
- **Buttons and contrast.** #90 Many actions are still plain text ("Hide",
  "Skip this step", Availability's add buttons, Running late's Preview, Focus's
  Skip and Finish), and "Plan my homework" is a third, tinted style. Done when
  every secondary action is outlined, one button per page is filled, and the
  tinted style is written into spec.md (re-check what 0.18.1 already
  outlined). #92 The focus ring on ‹ previous week is #b7bece on #f2f5ff, about
  1.8:1. Done with a 2 px accent ring and a 2 px gap everywhere, as the week
  grid got in 0.18.1. #93 Month's past-day chips are about 3.0:1 at 15 px. Done
  when the fill is dimmed instead of the text (about 6:1). #94 The look
  editor's "Changed" chip is #809dce on #e6e9f3, 2.3:1. Done in the accent text
  colour (about 5:1). #95 The title placeholder is #89898d on white, 3.5:1, and
  says "Homework". Done at #6e6c76 (about 5:1) with "e.g. History essay".
- **Sign-in pages.** #74 After a restart the page is grey and after Sign out
  it is lavender; headings switch between "Welcome to FlexWeek" and "Welcome
  back"; the wordmark jumps about 30 px between pages; Create account's hints
  sit halfway between fields; the password eye is tiny and faint. Done with one
  background, a fixed wordmark, hints under their own field, and a 24 px eye at
  3:1 or better. #77 The recovery codes paragraph is centred over four lines
  above left-aligned codes. Done when it is left-aligned.
- **Motion.** #96 Normal, More and Reduce look much alike (a Normal switch
  about 0.3 s, More about 0.23 s); with Off, Settings still slides for about two
  frames and Week to Month flashes an empty "Loading month…" grid. Done when
  Off moves nothing anywhere, the new page is drawn before the old one goes,
  and More is clearly longer (about 0.45 s). #97 Both titles overlap mid-fade;
  on the Month and My day rail toggle the plan panel and Unfinished card are
  drawn twice; the dim backdrop lingers a frame after a sheet closes; the Undo
  toast vanishes on the first view switch. Done when the title snaps, the
  panels stay anchored, the backdrop fades with its sheet, and the toast
  survives a view switch.
- **Wording.** #101 The look is named four ways ("Customise…", "Customise
  look…", "Look and colours", "Appearance & layout"), study time four ways,
  and Plan uses both "Planned" and "Placed"; Help reads "Ctrl + = - 0" as one
  chord; the Plan toast has no final full stop; Retro's description uses the
  "Windows 98" trademark. Done with one term per idea ("Look", "Study hours",
  "Placed") and one punctuation pass.
- **Decisions ("maybe on purpose"), each to be recorded built or left:**
  #23 Retro keeps the modern top bar and Start opens the modern menu (leave
  unless an immersive Retro is wanted); #27 the zoom − and + are about 16 px,
  under the 24 px target (give each a 24×24 hit area if the look stays); #28
  with the plan panel open at 1024×640, Month's last row is half cut and a
  scrollbar appears (shrink rows, or hide the plan panel in Month); #29 Month
  and My day drop the rail, so the page jumps sideways (slide instead of jump);
  #30 homework is red with red due dots, hard to see under the mini month in
  Dark (at most a lighter red in Dark); #31 the help's "opens at now every time"
  line is stale (reword); #56 sheets put Save right of Cancel, the platform
  order (leave); #61 Poster's 2 px borders against its 10 px corners (leave);
  #69 Settings is a full page, not a sheet (leave); #86 at 810 px empty Sat and
  Sun keep full width while weekdays truncate (narrow to about 60 %, or keep);
  #102 dates are written many ways ("October 2026", "28 Sep – 4 Oct",
  "Thursday 1 October", "Thu 1 Oct 2026", "Fri 2", "Monday, October 5"), even
  two on My day (one short and one long format per locale, or leave); #41 if
  not taken in 0.18.2.

- Complete when: the lanes above are closed on the shipped build, every
  "maybe on purpose" item has a recorded decision, gate, rig and CI green,
  v0.18.3 published as latest.
- Status: [ ] not started.

### Closed, no work ("Deliberate, leave it")
#47 a toast replaces the plan bar; #62 five accent swatches; #63 now line and
ring at 3:1; #78 empty sign-in fields and Inter recovery codes; #100 the
clock-change "2 h".

Coverage: Fix first (20) all in 0.18.1. Next patch (65): #6 #7 #42 #46 #50 #53
#76 ride along in 0.18.1, the other 58 are in 0.18.2 and 0.18.3. Maybe on
purpose (12) decided at 0.18.2 (#41) and 0.18.3. Deliberate (5) closed.

## Later
- Android, after the contest; decide phone–laptop sync first.
- Simple assignment list or ICS file import. Not live Canvas, Blackboard or
  Google Classroom OAuth, and not syllabus-photo ML.
- Stronger deadline-cluster insight on top of the slack badges, without
  mental-health or IEP product claims.
- Rejected: syllabus OCR, LLM auto-reschedule chat, LMS API bridges,
  offline-first AI mobile shell.
