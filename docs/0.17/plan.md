# FlexWeek 0.17: the working plan

0.17 is presentation, in three phases. First, one visual system for every screen. Second, a
revised version of every design and every look, each shown as two options in a clickable mock-up
for Jonathan to pick. Third, building what he picks. The brief is Claude's appearance review
(`look-review.md`), with AL's confirmed bugs (`design-review.md`, "Bugs that need no decision")
folded in. Where Grok's proposal and the review differ, the review's call stands; each place is
marked. Jonathan, 27 September: "Let's finalize your plan", then "for the current UI options we
should definitely focus on refining/overhauling them … revised versions that are much more
improved". Functionality changes only where a look needs it.

## Phase 0. Research (done)

`ui-ux-pro-max` was searched for each design and look (the style, typography, colour and UX
catalogues). Its generic answer for a student planner was Claymorphism with Baloo 2 and Comic Neue,
a children's app, which is wrong for high schoolers; so each design and look was searched on its
own, and the entries used are named in each brief below. UX rules taken as hard constraints:
Reduced Motion (high), Color Only (high: never colour alone), Focus States (high), Contrast
Readability (high), Continuous Animation (no decorative loops), Excessive Motion.

## Phase 1. The shared system (decisions 1 to 10)

1. **One accent, chosen once.** FlexWeek's blue by default (`#3d6fc4` on light, `#7fa8ff` on dark),
   the icon's colour; Sky, Sea, Gold and Sand as swatches. No look, design or screen replaces it,
   except High contrast, whose yellow is part of its contrast; and it is never mixed into an area
   larger than a control.
2. **Neutral surfaces.** Light: page `#f7f8fa`, cards `#ffffff`, hairlines `#e4e7ec`. Dark: page
   `#111315`, cards `#1a1d21`, hairlines `#2a2e34`. These are the looks Light and Dark (Light frost
   and Dark frost keep their ids and load as these); System follows the device.
3. **The chrome follows the look.** The top bar and the window's frame always take the look and the
   accent; a design colours only its own content (`window.py` `_chrome_palette`). A design's signature
   colourway stays as a choice; its default is Match my look.
4. **A type scale**: caption 11, body 13, heading 15, title 20, display 28 (points at Normal; Small and
   Large scale all five); weights 400 and 600, and 700 only for display numbers. Every size and weight
   in `look.py` comes from it. (Catalogue: Swiss Modernism 2.0, "clear hierarchy, mathematical
   ratios".)
5. **Spacing and shape.** Steps 4, 8, 12, 16, 24, 32. Radii 6 (controls), 10 (cards), 16 (sheets, the
   sign-in card, the toast, the command bar); pills only for chips and the segmented track.
6. **Elevation.** Two shadows only (`QGraphicsDropShadowEffect`): small (0 1 3, 8 %) and large (0 12 32,
   16 %).
7. **Icons.** Lucide (ISC) SVGs in `desktop/assets/icons/`, 16 and 20 px, 1.75 stroke, tinted to the
   text: settings, chevrons, plus, minus, search, book-open, trash, copy, check, eye, eye-off, clock,
   calendar, bell, palette, laptop, timer, log-out. No Unicode glyph stands in for an icon (checklist:
   "No emoji icons"). QtSvg is in PySide6 and both builds already ship `vectorimageformats`.
8. **Red means a problem**: "cannot go here", "past due" and destructive actions only.
9. **One category family**: fills at OKLCH L 0.92, C 0.045; marks at L 0.62, C 0.14; hues School 255,
   Homework 25, Study 295, Exercise 150, Activity 205, Meals 60, Sleep 275, Free (C 0.01). Homework also
   carries a book icon (Color Only rule).
10. **Checked by numbers** (`desktop/tests/test_tokens.py`), in every look: fills within 0.02 of each
    other in lightness; text on every fill and surface at 4.5:1 (7:1 in High contrast); homework's mark
    at least ΔE 20 from every other mark under a deuteranopia simulation; the accent never used as a
    large fill; every font size and weight on the scale.

## Phase 2. Revised versions of every design and look

### How the options are shown

A clickable mock-up, `docs/mockups/look-017/` (one self-contained `index.html` and `demo.py`, as
`look-concepts` was), with the same busy week as the review. For each design it shows the current
0.16 screen (from `scratch/look016`) beside two revised directions, A and B, drawn in the Phase 1
system. **A** refines the design in place; **B** changes its structure or interaction, per Jonathan's
standing rule that options differ in layout, not paint. Each can be switched between Light, Dark and
the design's signature colourway, and between Week and Day. A second tab shows every revised look on
Today's app's Week, and a third the system itself (type scale, colours, controls, motion as a
short loop). Jonathan picks A, B or "keep as it is" for each; his picks are written into this file as
decisions before Phase 3 starts.

### What every revised design must pass

The tokens test in every look; no clipped text at 1280x800, 1150x768 with large text, and 800 wide;
the rig's Day and Week (and My day for day screens); the accent followed; screenshots read. A design
that passes leaves "Experimental styles"; when all have, the heading goes.

### The designs

- **Today's app (Calendar).** The reference for the system; the review's sections 1 to 5 are its
  fixes (edged blocks, the Next card, the ordered focus list, the arrows before the title, opening at
  now). *A, Refined grid*: today's structure, the side panel as cards. *B, Rail*: a slim left rail
  (a mini month, Next, Not placed yet) and the week using the full width, as Notion Calendar and
  Fantastical do; the side panel goes. Catalogue: Flat Design, Swiss Modernism 2.0; Inter.
- **Timeline (Agenda).** Now: heavy black day names, homework as black slabs, a doubled title, "D" for
  every dinner. *A, Notebook*: E-Ink / Paper (off-white `#fdfbf7`, ink `#1a1a1a`, hairline rules, no
  shadows), day names in Newsreader (a serif, OFL) with Inter for the rest, blocks as ink-outlined
  cards with a category tab, the tray as sticky notes in the margin. *B, Planner spread*: the week as
  a two-page spread, Monday to Wednesday on the left page and Thursday to Sunday with notes on the
  right, each day a column, like a paper planner opened flat. Catalogue: E-Ink / Paper; Classic
  Elegant pairing (serif display, Inter body).
- **Mission control (Dashboard).** Now: internal labels ("CARGO BAY", "PLAN 3/5 PLACED"), lanes
  floating in the middle, "D" boxes. *A, Flight deck*: HUD / Sci-Fi FUI tempered by the Data-Dense
  Dashboard entry, which rates HUD's thin lines poorly for accessibility: lanes from the top, numbers
  in JetBrains Mono (OFL) and words in Inter, the accent as the only bright colour, the deadline radar
  and load chart as real small charts, 30-minute blocks as coloured ticks. *B, Ops board*: a strip of
  four figures (planned today, due this week, free time left, focus minutes), the lanes under it, a
  deadline table on the right sorted by time left. Signature colourway: dark; Light "Control room" too.
- **Bento (Dashboard).** Now: a saturated indigo board with red-orange controls and a second Add.
  *A, Bento*: the Bento Box Grid entry as written (neutral `#f5f5f7` page, white tiles at 16 to 24
  radius, 16 gaps, a hero tile of hours with an accent header, tiles for Next, Due soon, This week's
  load and Not placed); indigo as a colourway. *B, Today tiles*: today's hours as the hero and the
  other six days as small tiles showing each day's load and first item; picking a tile swaps it into
  the hero.
- **Retro desktop.** Now: a Windows 95 pastiche drawn in Inter. *A, Windows 98, faithful*: two-pixel
  bevels, Win98's navy-to-blue title gradient, a pixel UI face under an open licence (chosen in the
  mock-up; Pixel Retro's VT323 for deadlines.txt), window icons, a Start button and a taskbar clock.
  *B, System 7*: one window with tabs (Week, Deadlines, Up next) under a menu bar, one-bit black and
  white with the accent as the only colour. Catalogue: Pixel Retro pairing; Flat Design's "no
  gradients" does not apply here by design.
- **Clay deck.** Now: a different pastel per day, tilted cards cutting their first line. *A, Soft deck*:
  Claymorphism tempered by Soft UI Evolution (inner highlight and soft outer shadow, 20 radius), the
  category family instead of a pastel per day, cards straight by default and fanned at 3 degrees at
  most as an option. *B, Card carousel*: one large card per day in a row, today centred and its
  neighbours peeking, moved with the arrows or the wheel.
- **One thing (day screen).** Now: all caps, black and orange, taking over the chrome. *A, Poster*:
  Exaggerated Minimalism (one accent, the app's; display type at 96 to 140 pt, Inter 700, tight
  tracking; sentence case, with caps as an option), white in Light and black in Dark; the day bar a
  thin segmented timeline. *B, Countdown*: the screen as one large ring counting down to the next
  thing, "then" listed under it: One thing and the dial in one.
- **Day dial (day screen).** Now: the hand past the ring, the time on the hub, caps, pills, "task".
  *A, Dial*: Soft UI Evolution (a ring with 2-degree gaps in the category family, hour ticks outside
  it, the hand to the inner edge, the time under the hub, sentence case, a length column in the list),
  light in Light. *B, Next twelve hours*: an arc of the next twelve hours at twice the size, the rest
  of the day as a small ring beside it.

### The looks

Each look is a full token set (page, card, text, muted, hairline, block mode, knobs) that passes the
tokens test; none but High contrast replaces the accent.

- **Light, Dark, System**: decisions 1 and 2.
- **High contrast**: the Inclusive Design entry (7:1 text, 3 to 4 px focus rings, symbols with colour),
  rules at 40 % white, a readable view control, nothing cut; the accent yellow `#ffd400` (0.16's
  `#ffff00`, a shade warmer), whatever swatch is chosen.
- **Slate**: cool and professional (Swiss Modernism 2.0): page `#eef1f5`, white cards, ink `#0f172a`.
- **Nocturne**: Dark Mode (OLED): page `#0a0e27`, cards `#121633`, low-emission text `#e0e4f0`.
- **Paper**: E-Ink / Paper: `#fdfbf7`, ink `#1a1a1a`, Newsreader headings, no shadows, and Reduce
  motion by default ("distinct page turns, sharp transitions").
- **Ink**: Paper's night counterpart: charcoal `#1c1b19`, warm ivory text, serif headings.
- **Terminal**: the Developer Mono pairing (JetBrains Mono throughout), GitHub-dark surfaces
  (`#0d1117`, text `#c9d1d9`), green `#3fb950` only for success; no glow or scanlines, which the
  Cyberpunk entry rates poor for accessibility.
- **Poster**: Neubrutalism (2-pixel black borders, 4-pixel offset shadows, flat colour on cream,
  bold type); the one look allowed a third shadow, the offset.
- **Pastel**: Soft UI Evolution's improved-contrast pastels on lavender, 12 radius, soft shadows, and
  text at slate-900 so it passes 4.5:1.

### The knobs

- **Surface**: Flat or Layered (frost renamed for what it does).
- **Corners**: Soft (6 and 10), Sharp (0 and 2), Round (10 and 16).
- **Depth**: None, Soft (decision 6) or Bold (Poster's offset).
- **Font**: Sans (Inter), Serif (Newsreader headings, Inter body) or Mono (JetBrains Mono); Newsreader
  and JetBrains Mono are bundled like Inter, so each looks the same on every computer.
- **Blocks**: Edge (the default), Filled or Outline.
- **Density**: Comfortable or Compact. **Text**: Small, Normal or Large.

## Phase 3. The screens and motion (decisions 11 to 36)

These hold for every design; the picked directions of Phase 2 build on them.

11. **Top bar**: ‹ › Today before the title; icons; Add one pill with a divider; Plan my homework
    secondary (accent text on a 10 % tint); More in the text colour; hover 6 %, pressed 10 %, a 2-pixel
    focus ring at 40 %; the chosen segment raised with the small shadow.
12. **The grid**: overlay scroll bars; the zoom as a small "− +" pill; hour rules at 8 % white on Dark;
    the last label never cut; opening at now every time; after Plan, scrolled to the first block placed.
13. **Today**: an accent date chip in its header; a 3 % wash of the text colour at most; none on Day.
14. **Blocks**: a 3-pixel category edge, titles 600, times muted, a 3-pixel gap between neighbours, no
    "·" at a line's end, colour only below three letters of room, short 12-hour ranges ("4–5:30 PM").
15. **Side panel**: a Next card; muted section labels; the focus list in time order with times
    right-aligned; chips with a straight edge and the length right-aligned; as tall as its content,
    with a quiet "This week" row. A running timer is its first card (Grok: agreed).
16. **Day** drops its Next band and draws its summary with category dots.
17. **Month**: rows sized to their chips up to a maximum and this week banded (review, against Grok's
    six even rows); a "Due" flag, not a red box; outside days dimmed; the overlay scroll bar.
18. **The plan result**: a slim bar ("Placed 2 · 1 without a time · Details"), one filled button and one
    text button, the same count as the toast.
19. **Focus screen**: follows the look; a ring around the countdown; Pause filled, Skip and Finish as
    text; Back as a chevron. Quick focus and F both wait for Start.
20. **Toast**: dark with white text, the accent's light shade for Undo, 16 radius, the small shadow,
    bottom-right over the side panel; it belongs to its page.
21. **Ctrl+K**: a 40 % black backdrop that fades; the large shadow; Add, Go to and Homework groups;
    icons and shortcuts on the rows.
22. **Menus**: the right-click menu with icons, a separator and red for Delete and Delete homework;
    Log out after a separator; "Advanced" named for what it holds.
23. **Dialogs**: Add homework and Edit event as sheets inside the window; the rest stay windows
    (review, against Grok's "all dialogs"); every body is the card; labels on the text baseline; one
    width per kind of field; the repeat scope as a segmented control shown only for repeating blocks;
    Save where each platform puts it (review, against Grok); Account as three cards; a disabled
    primary at 40 %; one checkbox style.
24. **Settings**: the column centred up to 960; section icons and an accent bar; Look as "Light |
    Dark | System" with the other looks under "More looks"; Accent as swatches; one width per kind of
    field; nothing under the footer; the design picker showing Phase 2's revised pictures. No icons on
    individual rows (review: later).
25. **Sign in**: the wordmark above a centred 16-radius card with the large shadow; one heading; an eye
    in the password field; Create account hides Forgot password. No week preview (review: later).
    Recovery codes in Inter with tabular figures.
26. **Setup**: content centred up to 880; ticks on finished steps; Next the one filled button; the
    school hint only with no day picked; Play as an icon; the style cards showing Phase 2's pictures.
27. **Help**: keycaps; no "tutorial is coming" line; a fade at the scroll edge. **About**: the logo.
28. **Motion, fade through**: the old page out in 90 ms, the new in in 120 ms (OutCubic); Day, Week and
    Month add a 12-pixel slide in the segment's direction; ‹ › keep their drift.
29. **Chrome and content in the same frame**: the new page built first, the colours changed at the
    fade's midpoint.
30. **Settings slides in** from the right over the week dimmed 20 %, 200 ms.
31. **Sheets, dialogs and Ctrl+K** fade and rise 8 pixels through an opacity effect on their content,
    which Wayland honours.
32. **The segmented selection slides** (a painted indicator, 160 ms).
33. **Four motion levels**: Normal, More, Reduce (fades only) and Off (the Reduced Motion rule); Paper
    starts at Reduce.
34. **Plan's slide is seen**: the view scrolls to the placed blocks, then they slide.
35. **Each design's own motion** stays inside its content and within the levels: Clay's fan settles,
    the dial's hand eases, Retro's windows open with Win98's zoom rectangle, and nothing loops
    (Continuous Animation rule).
36. **Graduation**: Phase 2's checklist is the test for leaving Experimental.

## How it is run

As 0.16, on `feat/0.17-look` (from `claude/0-17-review`), each lane landed by Claude after review.

1. **The mock-up** (Phase 2's options) is built first and opened for Jonathan; no design or look of
   Phase 2 is built natively until he has picked.
2. **Lane A, tokens and colour** (1 to 3, 5, 6, 8 to 10, 13, Light, Dark, System and High contrast)
   runs beside the mock-up, since Phase 1 does not wait on the picks; the other looks and the knobs
   join it once they are picked.
3. **Then, at the same time**: B type, icons and controls (4, 7, 11, 12); C the week, blocks, side
   panel, Day, Month and plan bar (12 to 18, 34's scroll); D the focus screen, toast, Ctrl+K and menus
   (19 to 22); E sheets, dialogs and Settings (23, 24); G sign in, setup, Help and About (25 to 27);
   and one lane per picked design (H1 Today's app, H2 Timeline, H3 Mission control, H4 Bento, H5
   Retro desktop, H6 Clay deck, H7 One thing and Day dial).
4. **Lane F, motion** (28 to 35), last.

Each lane ends green on `scripts/verify.py` through `run-alone.sh`, on the mutation specs it touches,
on the rig for every design it touches, and with its screens read from
`scratch/audit_look_016.py` re-run on the lane, frames included. Subagents use Opus. Local commits
only; the PR and release come last, on Jonathan's word.

## Integration and release

- Land A, then the parallel lanes, then F.
- The gate, every mutation spec, the rig on every design and both day screens, the tokens test in
  every look, and the tour and frames read against `look-review.md` and Phase 2's checklist.
- Docs: `CHANGELOG.md` 0.17.0, `spec.md` (the system, the looks, the knobs, the motion levels),
  `docs/0.15/architecture.md` (the chrome rule, page changes), release notes, `version.py`.
- Then, on Jonathan's word: push, PR, checks, merge, release.
