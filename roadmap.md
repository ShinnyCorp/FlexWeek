# roadmap.md — FlexWeek

Congressional App Challenge 2026. Submit **Sunday, Oct 25, 2026, 8:00 p.m. PDT**
(hard deadline Monday, Oct 26, 9:00 a.m. PDT).

History up to 0.18.0 (Phases 1–7, the student experience stages, the native
desktop units, the 0.10.1 and 0.11 polish, the web client's retirement, the
first implementation slice) was removed from this file on 2026-10-02. It is in
this file's git history, in `CHANGELOG.md`, and in `docs/cac-build-plan.md`.

## Where things stand (2026-10-02)
- v0.18.0 is released as latest: the Rust engine under the same app. Nothing a
  student sees changed.
- The Grok team's audit of 0.17.2 (102 findings) is the backlog for the 0.18.x
  series below.

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
- Overlaps: one rule everywhere. Duplicate and the paste preview stop on an
  overlap ("Resolve conflicts…") while drag and the editor only warn ("Both
  will show, side by side"). The preview gets the same warning line and Save
  stays enabled; copy day and apply routine follow the same rule. Goes in the
  0.18.1 grid and keyboard lane with finding 20.


### From Jonathan while using the app (running list)
Gripes reported in conversation. Each gets a J-number here, then a lane; the
lane entry carries the number so nothing is lost between sessions.
- J1 (2026-10-02): an End of 00:00 is refused ("End must be after Start") in
  the block editor, Setup's school and activity hours, the School hours sheet
  and study hours. Read it as 24:00, drawn as "24:00" (12:00 AM on the 12-hour
  clock); the engine already accepts a block to the end of the day. Running
  past midnight in general is not included. → 0.18.1 time entry.
- J2 (2026-10-02): Duplicate stops on an overlap while drag only warns. →
  decision above; 0.18.1 grid and keyboard.

### 0.18.1 — Broken things
Twenty Fix-first findings, the engine leftovers, and eight Next-patch items
that share code with a Fix-first one.

| Lane | Findings and work |
|---|---|
| Plumbing | Bell GC teardown error; the three adapter tests; the today.json mutation survivor; the interface-test tidy (T4); delete the differential tests, `desk_ref/` and `backend/tests/engine_ref/`; spec.md drift line for the CI desk step |
| Time entry | #1 retyping a time fails; #33 Choose a time and New event default to the past; coupled #6 drop lands a step early, #7 pointer times off the grid, #53 Running late rounds down; J1 an End of 00:00 reads as 24:00 |
| Grid and keyboard | #8 right-click rarely opens; #9 Shift+F10 at 00:00; #87 Tab never reaches a block; #39 focus jumps to ‹; #11 last hour unlabelled; coupled #42 Ctrl+Z after Plan; Duplicate and paste previews warn on overlap instead of blocking Save (decision above) |
| Plan and Undo | #38 Undo twice locks the week; #40 toast clipped at 1024; #10 rail says everything has a time; #12 Mission opens without now; coupled #46 Plan not locked while planning |
| Sheets | #49 seven OS windows become sheets; #70 Manage account layout; #34 Add homework scrolls inside itself; #48 conflict line; #91 disabled buttons unreadable; #79 clipped buttons; coupled #50 recovery codes save folder and warning, #76 Sign out as a sheet |
| Deadlines and dates | #32 Due by and Do it at; #2 Setup's blank calendar; #35 typed date jumps a year |
| Update prompt | #64 offers the running version (re-check first: the code moved to Rust in 0.18.0) |

Order: plumbing → time entry, Plan and Undo, update prompt in parallel → grid
and keyboard → sheets and deadlines after mockup round 1 (the seven sheets,
the accent swatch grid, the amber conflict row, disabled labels in the text
colour, tonal "Plan here", the Due row).
- Complete when: every finding above is closed on the shipped build or
  re-checked away with evidence; the differential tests and frozen references
  are deleted; gate, rig and mutation runs green; CHANGELOG, release notes and
  context.md updated; v0.18.1 published as latest.
- Status: [ ] not started.

### 0.18.2 — Behaviour and layout
| Lane | Findings |
|---|---|
| Setup | #3 typed sport defaults to Activity; #4 Style page cut; #5 pages don't line up; #66 (Setup part) content under the footer |
| Week behaviour | #13 short blocks lose their start; #14 due vs placed mixed; #15 drops into the past, ghost colour; #16 empty next week has no prompt; #17 top stack eats the grid; #18 timer card in Today's app; #19 Focus controls and rail timer list; #20 block menu vs free-time menu; #24 Bento and Timeline contradict |
| Narrow widths and Large text | #80 times lose meaning; #81 "2 h 15"; #82 bare "Not placed yet"; #83 "Plan" shrink rule; #84 Large text squeeze; #85 12-hour School stacks; from 0.17.3: Clay and Retro 12-hour cuts at Large 810, Bento header "F 2" |
| Designs (from 0.17.3) | Bento's now pill inside today's column; Mission names crossed by the now line; Clay's Day card hourless for 100 ms; Mission's 00:00 label 6 px left |
| Add/Edit homework | #36 defaults, hints, empty boxes; #37 Spread hard to find |
| Plan | #43 two filled buttons, "Placed" wording; #44 misleading reason late in the day; #45 Undo menu item; #98 panel pops in |
| Sheets | #51 Choose a time controls; #52 New event title and fields; #53 (rest) Running late buttons and refusal; #54 Availability layout; #55 sheets don't match |
| Settings | #65 Remove alarm keyboard selection; #66 (Settings part); #67 Appearance layout and wording; #68 forms don't line up |
| Account | #71 buttons don't look like buttons; #72 errors carry over; #73 sign-in error; #75 where data lives |
| Keyboard | #88 F1 and Ctrl+N; #89 Ctrl+K palette |
| Errors | #99 offline messages |
| Decision | #41 Plan packs weekdays and leaves weekends empty: a solver change in the engine (daily cap, spread toward the due date). Jonathan decides; if yes, its own lane with Rust tests. |

Mockup round 2 before the Add/Edit, Plan, Sheets, Settings and Account lanes.
- Complete when: the lanes above are closed on the shipped build, #41 has a
  recorded decision, gate and rig green, v0.18.2 published as latest.
- Status: [ ] not started.

### 0.18.3 — Consistency and polish
| Lane | Findings |
|---|---|
| Designs | #21 Clay tails and hour scale; #22 Retro leftovers; #25 Day view, Day dial, One thing; #26 category icons; #60 Paper edges and icons |
| Look editor | #57 preview not darkened; #58 single-row Fix; #59 layout loose ends |
| Buttons and contrast | #90 plain-text actions; #92 focus ring 1.8:1; #93 Month past-day chips; #94 "Changed" chip; #95 "Homework" placeholder |
| Sign-in pages | #74 pages don't match; #77 centred paragraph |
| Motion | #96 Animations levels; #97 mid-switch frames |
| Wording | #101 wording sweep; #102 date formats (if decided) |
| Decisions ("maybe on purpose") | #23 Retro top bar; #27 zoom hit area; #28 Month last row at 1024; #29 rail drop on Month and My day; #30 homework red in Dark; #31 stale help line; #56 Save/Cancel order; #61 Poster borders; #69 Settings as a page; #86 weekend width at 810; #102 date formats; #41 if not taken in 0.18.2 |

Mockup round 3 before the Designs, Buttons and Sign-in lanes.
- Complete when: the lanes above are closed on the shipped build, every
  "maybe on purpose" item has a recorded decision (built or left), gate and
  rig green, v0.18.3 published as latest.
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
