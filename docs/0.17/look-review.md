# How 0.16.0 looks: Claude's review

Presentation only: what a student sees and how it moves, not what it does. Taken from a busy
student's week (school, soccer twice, piano, robotics club, gym, dinner every day, five homework
with three placed) at 1280x800, in every look and design, with frames captured 40 ms apart through
the view switches, My day, Settings, the toast and Plan (`~/.flexweek-ui-harness/scratch/look016/`,
made by `scratch/audit_look_016.py`), and the style code in `desktop/native/look.py` and
`motion.py`. It is meant to sit beside AL's report (`design-review.md`) and Grok's proposal; where
this agrees with them it says so in a line, and where it differs it says why.

## What already works

Inter at one weight step for titles, the segmented view control, the filled Add, the time pill on
the now line, deep blocks on Dark, the recovery-code card, Ctrl+K's shape, Settings in cards, and
the 800-pixel fold of Week (names on two lines, "Next … · Not placed yet: 2"). The motion curves
are right (OutCubic, 180 ms). What is wrong is almost never a single screen; it is that each screen
chose its own answer.

## 1. What sets the tone in the first thirty seconds

1. **The app has no fixed colour identity.** Sign in is blue `#3d6fc4`, Light frost's Week is teal
   `#0f7490`, Dark frost is mint `#5eead4`, Nocturne periwinkle `#7fa8ff`, Day dial navy with
   periwinkle, One thing black with orange, Timeline black. A student who changes nothing sees three
   accents before homework is placed. Agree with AL and Grok: one accent, chosen once.
2. **The page is tinted, the cards are white.** Light frost's page is a pale cyan (`#e6f3f8`-ish)
   with a white side panel and a white Month card, so every white surface looks stuck on, and the
   pastel blocks sit on a coloured page instead of paper. Today's column is washed a darker cyan on
   top of that. A near-white neutral page (`#f7f8fa`) with white cards, or a white page with
   `#f4f5f7` cards, lets the category colours be the only colour.
3. **The week opens on the night.** After a look change (and on some opens) Week shows 01:00 to
   15:00 at 15:40: the now line is off screen, and the first thing on screen is fourteen empty
   rows of night above School (`b-light-week.png`). A calendar that opens on empty night looks
   empty.
4. **The top bar moves.** The title's width changes with the view ("21 – 27 September", "Thursday
   24 September", "September 2026"), and ‹ › Today sit right after it, so they jump 70 pixels
   sideways on every switch between Day, Week and Month. Put the arrows and Today before the title,
   or give the title a fixed column.
5. **Blocks are flat slabs.** In Today's app a block is a pale fill with no edge (School is
   `#bfdbfe` on a blue-grey page, Thursday's School on a blue-grey wash is almost invisible). Bento,
   Clay, Retro and Timeline all give blocks a 3-pixel category edge; the default design is the one
   that does not.

## 2. Top bar, control by control

- The gear is the Unicode "⚙" drawn by a fallback font: thinner and lower than the text beside it.
  ‹ › and ▾ are text glyphs too. A small icon set (Lucide or Phosphor, 16 px, 1.75 stroke) for gear,
  chevrons, the Add arrow, zoom, and the menus.
- Add's arrow is a second filled button with a 2-pixel gap, so Add reads as two buttons. One pill
  with a 1-pixel divider in a darker accent.
- More is a quiet button with muted text and a 6-pixel "▾": it reads as disabled. Text colour, with
  a chevron icon.
- Plan my homework has a border like Today and More but is a much more important action; all three
  look equal. A secondary style (accent text, no border, or a tinted fill) would rank it second.
- No button has a pressed state and filled buttons have no hover (`look.py` has hover only for
  quiet buttons), so pressing Add gives no feedback. No button shows keyboard focus.
- The segmented control's selected segment is white on grey with a hairline: in Light frost it is a
  white rectangle on a grey track on a cyan page. A 1-pixel shadow on the selected segment reads as
  raised; the track should be the page colour darkened 4 %, not a grey.

## 3. The week grid

- Hour labels are grey 11 pt at the rule's height, which is right; "15:00" at the bottom is cut in
  half by the window edge, and the top one crowds the day names.
- The scroll bar sits between the grid and the side panel and reads as a grey divider line stuck to
  the panel (AL 27). Overlay scroll bars that appear on hover, or 4 pixels of space and a rounded
  track.
- The zoom − and + are 28-pixel bordered squares on the gutter's corner (AL 26). A single pill
  "− 100 % +" or no visible control (Ctrl and the wheel, and a View menu) would look intended.
- Dark frost's rules are `hairline_strong` cyan-grey at full length: the grid looks like graph
  paper. Hour rules at about 8 % white, and no vertical rules between days, only the column gap.
- Today: the whole column is washed and its header underlined; on Day the whole canvas is washed, so
  it marks nothing (AL 24). Only the header (accent text, accent dot, or a filled date chip as in
  Month) and a 3 % wash at most.
- After Plan the new blocks land off screen (Science poster at 14:45 Friday, Spanish at 16:15)
  while the view stays on 01:00 to 15:00; the slide the code does is invisible (`h-plan-after.png`).
  Scroll to the first thing a plan placed.

## 4. Blocks

- Title 13 pt bold (700) and time 11 pt regular in the same colour at 80 %: 700 is heavy for a
  label that repeats forty times a week. 600 for the title, and the time in the muted colour.
- The line break "08:00–14:45 ·" / "6 h 45 min" leaves a dangling "·" at a line end. Break before
  the dot, or put the length on its own line without it.
- Blocks touch: Dinner (18:30–19:00) and History essay (19:00) have a 2-pixel gap; nearby blocks
  need at least 3 pixels so two blocks never read as one.
- A 30-minute block in Timeline and Mission control is a tall narrow box saying only "D", seven times
  down the week. Below the room for three letters, show the category colour and nothing, or an
  icon.
- The colours are not one family (AL 16). Measured: School `#bfdbfe` (light, soft), Activity
  `#a5f3fc` (light, saturated, neon), Exercise `#a7f3d0`, Meals `#fed7aa`, Homework `#fecaca`, Free
  grey. Same lightness and chroma for every fill (about L 90, C 0.05 in OKLCH), marks at L 60.
- Colour-blind students: homework red and exercise green are the two categories most often next to
  each other, and red and green are the pair deuteranopes lose. With a mark on every block, give
  homework a second cue (a small book glyph, or a dotted edge) that is not colour.

## 5. The side panel

- "Next: Soccer practice at 16:00 (in 20 min)" is bold 13 pt and wraps to two lines; a small muted
  "Next" label over "Soccer practice" and "16:00 · in 20 min" would read in a glance.
- "Start a focus timer" and "Not placed yet" headings are accent bold and look like links (AL 27).
  Section labels in the muted colour, small caps-free 11 pt 600.
- The focus list is a bordered box of plain rows, "History essay  19:00" with a double space (AL
  27), not in time order after a plan (19:00, 19:00, 20:00, 14:45, 16:15 in `h-plan-after.png`).
  Rows with the time right-aligned in the muted colour, in time order.
- Tray chips draw the homework mark as a thick red bar with a rounded left corner, so each chip
  starts with a red "(" (`b-light-week.png`); and "Science po… · 1 h 30 min" shortens the name while
  the panel has room. A straight 3-pixel inset edge, and the length right-aligned so the name gets
  the width.
- Below two chips the panel is 400 pixels of white. Either the panel ends where its content ends, or
  it holds a small "This week" summary (hours of homework planned per day, as Mission control's load
  chart does, drawn quietly).

## 6. Day, Month, My day and the focus screen

- **Day** puts "Next: …" alone in a 40-pixel band above the hours; the same sentence is in Week's
  side panel. One place for it.
- **Day's summary** is four plain lines; with the category dot before each, or as a thin stacked bar,
  it becomes something to look at.
- **Month's day numbers** are 13 pt regular with today in a filled accent circle (good), but the
  cells outside the month take the same tint the week uses for today, so September 1 to 4 look like
  "today". Dim their numbers instead.
- **Month's due chips** are red-outlined boxes, five in a row on Sunday: a column of red outlines is
  the most alarming thing in the app for the most ordinary fact, that homework is due. A small "Due"
  flag or a bold title, not a red box.
- **My day, Day dial**: the hand runs past the ring and across "22"; the time sits on the hand's hub;
  "UP NEXT · 16:00 · IN 20 MIN" and "TODAY, HOUR BY HOUR" are the only all-caps text in the default
  look; the past row is struck through with its middle dots misaligned ("Dinner   · 30 min" against
  "Soccer practice · 1 h 30 min"); the buttons are pills (AL 30). Stop the hand at the ring's inner
  edge, put the time under the hub, sentence case, a right-aligned length column.
- **My day, One thing** is the most striking screen in the app, and the only one that is entirely
  caps and entirely black-and-orange. Its colours should be a colourway you choose, not the
  default, and its top bar should stay the app's.
- **The focus screen** is a large number on an empty page with three equal outlined buttons and a
  grey 360-pixel line for progress, while My day has a 400-pixel dial. A ring around the countdown
  (the dial's own drawing, one colour), Pause as the filled button, Skip and Finish as text.
- A toast that says "Planned 2 homework blocks." stays on screen over the focus screen, which has
  nothing to do with planning (`i-focus-running.png`). A toast belongs to the page it was said on.

## 7. Dialogs and forms

- Every form dialog draws its scrolled body as a pale inset inside a white card, so a dialog is a
  box inside a box inside a window (`e-homework-new.png`, and the white frame AL 19 saw in Dark).
  The body should be the card.
- Labels are top-aligned with their fields' top edge instead of their text's baseline, 4 pixels high
  (AL 20); the Due box is 200 pixels in a 340-pixel column; Start and End are 420-pixel spin boxes
  for five characters.
- The event editor opens on two radio buttons ("This day only", "Every selected day") with no
  heading, above Title; the choice only matters for repeating blocks. A segmented control under the
  days, shown only when the block repeats.
- The Account dialog is eight buttons in three wrapped rows with Replace password filled, two tall
  empty gaps, and "8 unused recovery codes remain." in the error red (`e-account.png`): an ordinary
  fact in alarm colour. Three cards (Password, Recovery codes, Your data) with one action each.
- Running late's primary button is disabled until Preview, drawn as a solid grey slab that looks
  broken; a disabled primary should keep its shape at 40 % opacity.
- Routines mixes two checkbox styles: the app's accent checkboxes for days, and Qt's list-item ticks
  ("☑") for the fixed times (`e-routines.png`).
- The recovery codes are DejaVu Sans Mono, a second typeface family heavier and wider than Inter.
  Inter with tabular figures and 0.5 px letter-spacing reads as code without a new face.

## 8. Settings

- The cards stop at 760 pixels and hug the left, so a quarter of a 1280 window is empty on the
  right (AL 32). Either centre the column or let cards run to the page edge with a max of 960.
- The section list is plain 13 pt text with a flat tinted block for the chosen one: icons (palette,
  calendar, timer, bell, laptop) and a 3-pixel accent bar on the chosen one.
- "Experimental styles" is a grey heading in the same weight as a card title, and the experimental
  cards run under the footer with no fade or divider, cut mid-sentence (`f-settings-light-0.png`).
  A hairline above the footer and 24 pixels of bottom padding in each section.
- Focus's number boxes are four different widths (30, 15, 30, "4 focus sessions") because each is
  sized to its text (`f-settings-light-2.png`). One width per kind of field.
- Opening Settings is a crossfade of the whole Settings page over the week, so for 100 ms the section
  list sits on top of the week's title and hours (`h-settings-open-180ms.png`).

## 9. Toast, Ctrl+K, menus, tooltips

- The toast is white on a pale page with a hairline border and no shadow, placed over the hours'
  foot, where it covers blocks (Gym in `i-week-with-timer.png`). Dark (`#1f2937`) with white text and
  the Undo in the accent's light shade, 8-pixel radius, a soft shadow, and 16 pixels above the side
  panel's bottom rather than over the grid.
- Ctrl+K's backdrop desaturates the week to a flat grey instead of dimming it (`g-command-bar-typed.png`);
  the box has no shadow and its input a different fill from the box. 40 % black backdrop, a 24-pixel
  blur-like shadow on the box, the input borderless on the box's fill, a group label ("Homework",
  "Go to", "Add"), and the shortcut on the right of each row.
- The More menu is fine but plain: a "Planning" group label, then "Advanced ›"; Log out is not set
  apart from Help. Log out after a separator, in the text colour, never with the others.
- The right-click menu has Delete and Delete homework as the last two plain rows (AL 36): a
  separator, red text for both, and icons.
- Tooltips are the text colour on the page colour (inverted), which is right; they appear instantly
  and cut at the window edge on the side panel.

## 10. Sign in, recovery and setup

- Sign in is a 380-pixel white card, no shadow, content left-aligned, logo and wordmark in the old
  blue (`#3d6fc4`, which no longer matches Light frost's teal), "Sign in" then "Welcome." as two
  headings, a 40-pixel empty band at the bottom, and a flat pale-blue page (AL 5). The card centred
  with a 16-pixel radius and a 12 % shadow, one heading ("Welcome to FlexWeek" or "Welcome back"),
  the wordmark on the page above the card rather than inside it, and the page in the look's colour.
- The Show button beside the password makes the password field 76 pixels narrower than the username
  field: an eye icon inside the field.
- Setup's content is pinned top-left with the right third empty, finished steps get no tick, and
  "Add custom hours" and "Send a test reminder" are filled like Next (AL 40).

## 11. Dark, High contrast, accents

- Dark frost is blue-black `#0a1016` with mint; Nocturne is navy with periwinkle; both are dark
  *and* tinted. A neutral dark (`#111315` page, `#1a1d21` cards) is what most dark-mode users mean,
  and it makes the deep block colours read as colour instead of as more blue.
- Mint on Dark (`#5eead4` Add with dark text) is the brightest thing on screen; a dark accent should
  be at most as bright as the text.
- High contrast: the view control is yellow on light grey and unreadable, the side panel list grows
  a horizontal scroll bar, chips are cut, and the grid is bright white lines on black (AL 4). High
  contrast means text at 7:1, not every line at full white: rules at 40 % white.
- Picking Gold as the accent turns today's column khaki on the cyan page (`b-gold-week.png`): the
  wash mixes the accent into the page. The accent should never be mixed into large areas.

## 12. The experimental designs

Timeline doubles the title ("21 – 27 September" in the top bar and "This week … 21 September – 27
September" below it) and draws homework as black slabs with white text cut to "Hist…". Mission
control centres its lanes vertically, leaving 100 pixels of nothing between its header and Monday.
Bento adds a second red-orange Add and red-orange zoom buttons on indigo. Clay deck's columns are
five different pastels, and its tilted cards cut the first line off the top. Each is fine as a
novelty; none should be one click from the default, which Settings' picture cards now make them.

## 13. Motion, from the frames

- **View switches cross two grids.** At 80 ms Week and Month are both at half strength, text over
  text (`h-week-to-month-080ms.png`). Fade out in 90 ms, then in in 120 ms, both OutCubic; or, for
  Day, Week and Month only, a 12-pixel slide in the direction of the segment with the fade.
- **My day changes the chrome first and the content 150 ms later.** At 40 and 120 ms the top bar and
  the window's edge are navy around the untouched light week; at 320 ms the dark dial is still
  half-faded over the light week, a grey that is neither (`h-week-to-myday-*.png`). The page is
  built after the chrome changes. Build the new page first, then change both in the same frame.
- **Settings fades over the week**, so the section list sits on the week's title for most of the
  fade. Settings should slide in from the right over a dimmed week, or cut.
- **Dialogs and Ctrl+K appear in one frame** on Wayland, because they fade through window opacity,
  which Wayland ignores. An opacity effect on the dialog's content does work there.
- **The toast rises and fades in at 180 ms**, which is right; its exit is a 120 ms fade with no
  movement, which is right; it should not rise over the grid.
- **Nothing responds to the pointer.** No hover tint on filled buttons, no press state, the view
  control's selection jumps. Hover and press are the motion people feel most: a 6 % darker fill on
  hover and 10 % on press need no animation at all.
- **Motion levels.** Normal (180 ms), More (260 ms) and Off exist; there is no "Reduce", which keeps
  fades and drops slides, drifts and the plan's sliding blocks. Off is too blunt for students who
  only mind movement.

## 14. Copy that shapes the look

Double spaces in lists, a "·" left at a line's end, "…" that hides only the length ("19:00–20:00 ·
…"), caps in two screens, "task" in one, "Dashboard · Bento" and "Agenda · Timeline" as double
names, and Help's "A tutorial and short guides are coming in a later version" as the first thing a
student reads there. Each is small; together they are what makes a screen look unfinished.

## Where this differs from Grok's proposal

- **One accent: yes, but keep colourways.** One accent everywhere, and the page never tinted by it.
  A design's colourway should still exist, as an option you pick ("Night" for My day), not as the
  default.
- **My day follows the look: yes.** The dark dial is the best screen in the app for the students
  who pick it; it should be one of the day screen's colourways.
- **Save on the right: no.** Most students run FlexWeek on Windows, where the primary button comes
  first; Qt already follows each platform. Leave it.
- **Dialogs inside the window: only the two editors.** Add homework and Edit event are opened many
  times a week and are worth drawing as sheets; Account, Help, About and Routines are opened a few
  times a year and can stay windows once they look like the app.
- **Fade through: yes, and slide only Day, Week and Month.** The prev and next arrows already drift
  the content; that should stay.
- **Month's rows: keep them, trim them.** Rows sized to their chips up to a maximum, and this week
  marked with a tinted band, rather than a return to six even rows.
- **A plan bar: yes, and scroll to what it placed.** A slim bar says little if the blocks it names are
  off screen.
- **The timer in the side panel: yes**, as the side panel's first card while a timer runs, with the
  Next card under it.
- **Additions I would not do yet**: a week preview at sign in, and icons on every Settings row. Get
  the colours, type and motion into one system first; decoration on an unsettled base is what the
  report is complaining about.

## Who would like what

- **The student with a job and practice five days a week.** Needs Compact spacing to fit 08:00 to
  22:00 without scrolling at 1366x768 (the most common school laptop), names before times, and the
  side panel folded into the top line. Every decorative pixel is a lost hour of the week.
- **The perfectionist planner** (colour-codes everything, came from Notion or Google Calendar). Will
  notice the dangling "·", the double spaces and the uneven field widths before anything else, and
  wants to choose each category's colour.
- **The night studier.** Wants a neutral dark, not blue-black; deep blocks; no mint glow; and the
  now pill dimmer than the blocks around it at 23:00.
- **The student with ADHD or time blindness.** The dial and a ring on the focus screen, a large
  "next" at the top, and fewer places saying the same thing: today "Next" is in the panel, the
  timer card and the Day band at once.
- **The anxious student.** Red is everywhere a problem is not: the not-placed edges, the due chips,
  "8 unused recovery codes remain", the now line. Keep red for "cannot go here" and "past due".
- **Middle schoolers (11 to 13).** Like Bento's colour, Clay's cards and One thing's drama, bigger
  targets, and category icons or emoji; will not mind pills.
- **Older high schoolers (16 to 18).** Read neon cyan, pills and caps headlines as childish. Want
  Light with one muted accent, 600 not 800 titles, and Ctrl+K with shortcut hints.
- **Colour-blind students (about 1 in 12 boys).** Cannot tell homework red from gym green, or the red
  not-placed edge from nothing. Need a shape or text cue on homework, and category colours checked
  with a deuteranopia filter.
- **Low-vision students.** Need High contrast that works (7:1 text, readable view control, no cut
  chips) and large text that does not wrap the top bar into two rows at 1280.
- **Motion-sensitive students.** Want "Reduce" rather than "Off": fades yes, slides and sliding blocks
  no, and never the navy flash.
- **Students who screenshot their week for a group chat or a parent.** Month and Week are the images
  that leave the app; a clean Month (no red boxes, no empty rows, no scroll bar over Sunday) is the
  app's advertisement.
- **Contest judges.** Sign in, the empty week of a new account, the first Plan, and whether the accent
  stays put. They will not open Retro desktop.
