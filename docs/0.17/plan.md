# FlexWeek 0.17: the working plan

0.17 is presentation: one visual system for every screen and motion that shows what changed.
It takes Claude's appearance review (`look-review.md`) as the brief, with AL's confirmed bugs
(`design-review.md`, "Bugs that need no decision") folded in. Where Grok's proposal and Claude's
review differ, the review's call stands; each is marked below. Jonathan: "Let's finalize your plan"
(27 September). Functionality changes only where a look needs it.

## Decisions (27 September)

### The system

1. **One accent, chosen once.** The default is FlexWeek's blue (`#3d6fc4` on light, `#7fa8ff` on
   dark), the icon's colour. Settings offers it and the existing Sky, Sea, Gold and Sand as
   swatches. No look, design or screen replaces it, and it is never mixed into an area larger than a
   control: not the page, not today's column.
2. **Neutral surfaces.** Light: page `#f7f8fa`, cards `#ffffff`, hairlines `#e4e7ec`. Dark: page
   `#111315`, cards `#1a1d21`, hairlines `#2a2e34`. These become the looks called Light and Dark
   (Light frost and Dark frost keep their ids and load as these). System follows the device. Slate,
   Nocturne and the presets stay under Experimental with their tints.
3. **Designs follow the look.** Every design's Colours option defaults to Match my look; the old
   colourways stay as choices. Day dial's navy becomes its "Night" colourway, One thing's black and
   orange its "Poster". The window's chrome always takes the look and the accent, never a design's
   colourway (`window.py` `_chrome_palette` returns the look's palette for the chrome).
4. **A type scale** of five sizes over the text knob: caption 11, body 13, heading 15, title 20,
   display 28 (points at Normal; Small and Large scale all five). Two weights, 400 and 600; 700
   only for display numbers (the focus countdown and the dial's time). Every `font-size` and
   `font-weight` in `look.py` comes from the scale.
5. **Spacing and shape.** Spacing steps 4, 8, 12, 16, 24, 32. Radii: 6 for controls, 10 for cards,
   16 for sheets, the sign-in card, the toast and the command bar; pills only for chips and the
   segmented track.
6. **Elevation.** Two shadows only, drawn with `QGraphicsDropShadowEffect`: a small one (0 1 3, 8 %)
   for the raised segment and cards that float (toast), a large one (0 12 32, 16 %) for sheets, the
   command bar and the sign-in card. Nothing else casts a shadow.
7. **Icons.** Lucide (ISC licence) SVGs in `desktop/assets/icons/`, 16 and 20 px, 1.75 stroke, tinted
   to the text colour: settings, chevron-left, chevron-right, chevron-down, plus, minus, search,
   book-open (homework), trash, copy, check, eye, eye-off, clock, calendar, bell, palette, laptop,
   timer, log-out. No Unicode glyph stands in for an icon.
8. **Red means a problem.** Red is kept for "cannot go here", "past due" and destructive actions.
   Due chips, not-placed edges and the recovery-code count are drawn in neutral or category colour.
9. **One category family.** Fills at the same lightness and chroma (OKLCH L 0.92, C 0.045), marks at
   L 0.62, C 0.14, hues: School 255, Homework 25, Study 295, Exercise 150, Activity 205, Meals 60,
   Sleep 275, Free (C 0.01). Dark fills use the marks sunk into the card, as 0.16 does. Homework
   also carries a non-colour cue: a book icon at the start of its title when the block is 20 px or
   taller, and in chips.
10. **Checked by numbers.** A test holds decisions 1, 2, 8 and 9: every fill within 0.02 lightness of
    the others; text on every fill at 4.5:1; homework's mark at least ΔE 20 from every other mark
    under a deuteranopia simulation; High contrast text at 7:1; the accent never used as a large
    fill.

### Screens

11. **Top bar**: ‹ › Today, then the title, so the arrows never move when the title's width changes.
    Icons from 7. Add is one pill with a 1-pixel divider before its arrow. Plan my homework is a
    secondary button (accent text on a 10 % accent tint). More in the text colour with a chevron.
    Every button has hover (6 % darker), pressed (10 %) and a 2-pixel focus ring in the accent at
    40 %. The segmented control's chosen segment is raised with the small shadow; the track is the
    page darkened 4 %.
12. **The grid**: thin overlay scroll bars (6 px, shown on hover, never a divider); zoom as one small
    "− +" pill with the level between; hour rules at 8 % white on Dark and no day rules there; the
    last label never cut. The week opens at now every time, after a look change too, and after Plan
    it scrolls to the first block the plan placed.
13. **Today**: its header gets the accent (a filled date chip, as Month has); its column at most a 3 %
    wash of the text colour, never the accent; Day has no wash.
14. **Blocks in Today's app** get a 3-pixel category edge, titles 600, times in the muted colour, a
    3-pixel gap between neighbours, no "·" left at a line's end, and below three letters of room only
    the colour. The 12-hour clock writes short ranges ("4–5:30 PM"). The "…" never hides only the
    length.
15. **Side panel**: a Next card (a small "Next" label, the title, "16:00 · in 20 min"); section labels
    in the muted colour at caption 600; the focus list in time order with times right-aligned and
    no double space; chips with a straight 3-pixel inset edge in the category colour and the length
    right-aligned; the panel as tall as its content, with a quiet "This week" row of homework hours
    per day under it. While a focus timer runs, it is the panel's first card (Grok: agreed), and no
    card stacks above the hours.
16. **Day** drops its Next band (the side panel has it) and draws its summary with category dots.
17. **Month** sizes its rows to their chips up to a maximum and marks this week with a tinted band
    (review, against Grok's six even rows); due is a small "Due" flag, not a red box; days outside
    the month dim their numbers instead of taking a tint; its scroll bar is the overlay one.
18. **The plan result** is a slim one-line bar under the top bar ("Placed 2 · 1 without a time ·
    Details"), one filled button (Got it) and one text button (Details); its count and the toast's
    count are the same number (Grok and AL: agreed).
19. **My day, Day dial**: the hand stops at the ring's inner edge; the time sits below the hub;
    sentence case everywhere; rounded rectangles, not pills; "homework", not "task"; one "Nothing
    else today" line; lengths in a right-aligned column.
20. **Focus screen**: follows the look; a ring around the countdown drawn as the dial's ring; Pause
    filled, Skip and Finish as text buttons; Back as a chevron button. Quick focus and F both open it
    ready and wait for Start.
21. **Toast**: dark (`#1f2937`, and `#e8eaed` on Dark), white text, Undo in the accent's light
    shade, 16 radius, the small shadow, bottom-right over the side panel rather than over the hours;
    it belongs to the page it was said on and goes when the page changes.
22. **Ctrl+K**: a 40 % black backdrop that fades in; the large shadow; groups (Add, Go to,
    Homework) with labels; an icon and the shortcut on each row; an overlay scroll bar.
23. **Menus**: the right-click menu has icons, a separator above Delete and Delete homework, and
    both in red. More puts Log out after a separator, and "Advanced" says what it holds (Copy and
    paste, Restore points, Reload).
24. **Dialogs**: Add homework and Edit event open as sheets inside the window (a card over a dimmed
    window); the rest stay windows (review, against Grok's "all dialogs"). Every form's body is the
    card, not a box in a card; labels on their fields' text baseline; one width per kind of field;
    the event editor's "This day only | Every selected day" is a segmented control under the days,
    shown only when the block repeats; Save stays where each platform puts it (review, against
    Grok's "Save on the right"). Account is three cards: Password, Recovery codes, Your data. A
    disabled primary keeps its shape at 40 %. Routines uses the app's checkboxes throughout.
25. **Settings**: the column centred, up to 960 pixels; section icons and a 3-pixel accent bar on the
    chosen one; Look as "Light | Dark | System" with "More looks" (the experimental ones) under it;
    Accent as swatches; one field width per kind; a hairline above the footer and 24 pixels at the
    end of each section, so nothing runs under the footer; "Experimental" as a small tag, not a
    heading that looks pickable. No icons on individual rows (review: later).
26. **Sign in**: the wordmark above a centred card of radius 16 with the large shadow; one heading
    ("Welcome to FlexWeek", then "Welcome back"); the password's Show as an eye inside the field;
    Create account hides Forgot password; the page is the look's page. No week preview (review:
    later). Recovery codes in Inter with tabular figures.
27. **Setup**: content centred up to 880 pixels; a tick on finished steps; Next the one filled
    button; the school hint only when no day is picked; each sound's Play as a play icon.
28. **Help**: shortcuts drawn as keycaps; no "tutorial is coming" line; a fade at the scroll edge.
    **About**: the logo.
29. **High contrast**: 7:1 text, the view control readable, rules at 40 % white, no cut chips, no
    sideways scroll bar in the side panel.
30. **Timeline** (the standard alternative): no second date line under the top bar's title, day
    names at 600, homework in its category fill (no black slabs), short blocks colour only, and no
    own Add (the top bar's). **Mission control**: words for its labels ("Not placed yet",
    "Week 39"), lanes from the top. **Bento**: its Add secondary in the accent. **Clay deck**: the
    first line of a tilted card never cut.

### Motion

31. **Fade through, not cross.** Every page change fades the old page out in 90 ms and the new one
    in in 120 ms (OutCubic), so no frame shows two pages at half strength. Day, Week and Month add a
    12-pixel slide in the direction of the segment; the week's ‹ › keep their drift.
32. **Chrome and content change in the same frame.** The new page is built before anything changes;
    the chrome's colours change at the fade's midpoint, with the content.
33. **Settings slides in** from the right over the week dimmed 20 %, 200 ms; Done slides it back.
34. **Sheets, dialogs and Ctrl+K** fade and rise 8 pixels through an opacity effect on their content,
    which Wayland honours; the backdrop fades with them.
35. **The segmented selection slides** (a painted indicator, 160 ms), and hover and press tints need
    no animation (11).
36. **Four motion levels**: Normal, More, Reduce (fades only: no slides, drifts or sliding blocks)
    and Off.
37. **Plan's slide is seen**: the view scrolls to the placed blocks first (12), then they slide.

## How it is run

As 0.16: lanes on branches off `feat/0.17-look` (from `claude/0-17-review`), each landed by Claude
after review. Lane A first, since its tokens are what every other lane draws with. Then B, C, D, E
and G at the same time, with F (motion) last, since it moves the final pages. Each lane ends green
on `scripts/verify.py` through `run-alone.sh`, on the mutation specs it touches, on the rig where it
touches hours, and with its screens read from `~/.flexweek-ui-harness/scratch/audit_look_016.py`
re-run on the lane (the same week, looks and frames as the review). Subagents use Opus. Local
commits only; the PR and release come last, on Jonathan's word.

## Lane A. Tokens and colour (decisions 1, 2, 3, 8, 9, 10, 13, 29)

Files: `desktop/native/look.py` (palettes, accents, `resolved_palette`, `block_paint`, a new
`tokens.py` for the scale, spacing, radii and shadows), `desktop/native/calendar.py` (categories),
`desktop/native/layouts/registry.py` (Match my look as the default colourway),
`desktop/native/window.py` (`_chrome_palette`), `desktop/native/hours/canvas.py` (today, now pill
halo), `desktop/native/hours/month.py` (due flag, outside days), tests.

Build: the palettes and accents of 1 and 2; categories of 9 computed from OKLCH in one function with
the hex values checked in; the chrome from the look only; today's marker of 13; red only where 8
allows; High contrast of 29; `desktop/tests/test_tokens.py` for 10 (lightness spread, contrast,
deuteranopia distance, accent area).

You see: one blue on every screen; a near-white page with white cards; School, Soccer, Gym and
Dinner as one family; My day in the look's colours; no red on a normal Sunday in Month.

## Lane B. Type, icons and controls (4, 5, 6, 7, 11, 12 but the opening scroll)

Files: `desktop/native/look.py` (every size and weight from the scale; button states; focus ring;
scroll bars; segmented), `desktop/native/icons.py` (new: load and tint an SVG), `desktop/assets/icons/`,
`desktop/native/window.py` (top bar order and icons), `desktop/native/hours/zoom.py` (the zoom pill),
`desktop/native/widgets.py` (the Add pill), build scripts only if the SVG plugin needs it, tests.

You see: the top bar's arrows still after a switch; real icons; hover and press on every button; a
focus ring on Tab; thin scroll bars; a quiet zoom pill.

## Lane C. The week, blocks, side panel, Day and Month (12's scroll, 14, 15, 16, 17, 18)

Files: `desktop/native/hours/canvas.py` (block words and edges), `desktop/native/hours/classic.py`
(side panel, Day), `desktop/native/hours/month.py` (row heights, this week's band),
`desktop/native/widgets.py` (`PlanReview` as a bar), `desktop/native/window.py` (open at now after a
look change, scroll to a plan's first block, the timer card into the panel), `desktop/native/weekmodel.py`
(short 12-hour ranges), tests.

You see: edged blocks with whole times; a Next card; an ordered focus list; a slim plan bar and the
placed blocks on screen; Month with this week banded and no empty half-page.

## Lane D. My day, the focus screen, the toast, Ctrl+K and menus (19, 20, 21, 22, 23)

Files: `desktop/native/layouts/dial.py`, `desktop/native/layouts/one_thing.py`,
`desktop/native/focus_screen.py`, `desktop/native/widgets.py` (`Toast`), `desktop/native/command_bar.py`,
`desktop/native/window.py` (the right-click and More menus), tests.

## Lane E. Dialogs, sheets and Settings (24, 25)

Files: `desktop/native/widgets.py` (a `Sheet` host, `HomeworkDialog`, `BlockDialog`, `LateDialog`,
`RoutineDialog`, form layout), `desktop/native/settings.py` (`SettingsPage`, `AccountDialog`),
`desktop/native/window.py` (the sheet host over the planner), tests.

## Lane G. Sign in, setup, Help, About and the designs (26, 27, 28, 30)

Files: `desktop/native/window.py` (the auth and recovery pages), `desktop/native/setup.py`,
`desktop/native/settings.py` (`HelpDialog`, `AboutDialog`), `desktop/native/layouts/timeline.py`,
`mission.py`, `bento.py`, `clay.py`, tests; the rig for Timeline's Day and Week.

## Lane F. Motion (31 to 37), last

Files: `desktop/native/motion.py`, `desktop/native/window.py` (page changes, the chrome swap,
Settings' slide), `desktop/native/widgets.py` (the segmented indicator, the sheet's appearance),
`desktop/native/command_bar.py` (its fade), `desktop/native/settings.py` (the Reduce level), tests
that grab frames: no frame of a page change shows two pages above 20 % each; the chrome and the
content change in the same frame; Reduce moves nothing sideways.

## Integration and release

- Land A, then B, C, D, E and G, then F, on `feat/0.17-look`.
- The gate, every mutation spec, the rig on every design and both My day screens, and
  `audit_look_016.py` read against `look-review.md` section by section, with the frame captures of
  section 13 re-taken and read.
- Docs: `CHANGELOG.md` 0.17.0, `spec.md` (the system: accent, surfaces, scale, motion levels),
  `docs/0.15/architecture.md` (the chrome rule and page changes), release notes, `version.py`.
- Then, on Jonathan's word: push, PR, checks, merge, release.
