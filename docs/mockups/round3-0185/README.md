# 0.18.5 mockup round 3

Plain calendar, default look, Light unless stated. Each PNG puts today's build (0.18.4, captured from the
app drawn offscreen, then redrawn in HTML) beside the proposal. Colours, fonts and sizes come from
`desktop/native/look.py`, `tokens.py` and the bundled Inter and Newsreader. Contrast ratios were worked out with the
app's own `tokens.contrast`; the numbers are in `numbers.txt`. Nothing in the repo was touched. `*.html` are the
sources, `shoot.sh <page> <w> <h>` photographs one (the old Playwright path is gone; it uses the T3
headless Chrome). `cur/` holds the raw app captures.

The six PNGs are in this folder. The HTML sources stayed in Claude's scratch folder.

## #25 Day: `25_day.png`
Four rows. Noon stays at the top of the dial (your decision).
- **Dial with blocks.** Words are written along the arcs: "School" and "Soccer" in #0b1224 on the blue and green
  (5.13 and 5.45 to 1), "Earlier today" on the pale grey (#5b6474 on #eceef1, 5.13) and "Free until 22:00" on the dark
  wedge (4.68 on #e2e4e7). A small "Reading the ring" key under the Today list names the four kinds of arc. The wedge
  is free time still ahead; the pale grey is free time already gone.
- **Dial with nothing else planned.** The card heading drops from 20 pt (title) to 15 pt / 600 (heading), with a
  muted line "Your evening is free until 22:00." The title size is kept for the date and a running block.
- **One thing, empty.** No minute ring scale (no 0/15/30/45, no ticks), as no countdown runs: a plain 10 px ring,
  centre "Free until 22:00 / Nothing else scheduled today / 8 h 20 min free". The bar keeps its colour (#c9cacd) and gains
  06:00 to 22:00 hour labels, a "Now 13:40" label on its mark, and a caption "Today, 06:00 to 22:00. Nothing planned."
- **Zoom and headings.** "Hours" and "Agenda" both in the text colour at 15 pt / 600 (17.74 to 1 on the card; Hours
  was the accent blue). A greyed − or + stays, with one caption line under the pill: "Smallest zoom reached" or
  "Largest zoom reached" (#5b6474 on white 5.97). The zoom buttons also get their 24 x 24 hit areas (#27).
Questions: (1) The key plus labels is one option; a lighter one is the key alone, without text on the arcs. Say if the
arcs feel crowded. (2) Keep a quiet ring in One thing's empty state (shown) or drop it and centre the words alone?
(3) Recommendation for the zoom, as the checker said: the reason line, not hiding. A disabled Qt button shows no tooltip,
so a tooltip alone would not work.

## #26 Icons: `26_icons.png`
- **School:** the Lucide `school` building (already shipped, used by "School hours…") for the category, the Add menu's
  category list and the block. Today the block and category use `house`, #398ad6 on #cfe8ff = 2.88 to 1. Icon drawn in
  #0e69b3 on #cfe8ff = 4.51 to 1 (5.69 on white); in Dark #69bbff on #304962 = 4.50 to 1 (today #59aaf8, 3.78).
  The block's 3 px edge keeps the #398ad6 mark; only the icon darkens. Size 14 to 16 px.
- **Replan all my homework:** a calendar with two circling arrows (Lucide `calendar-sync`). Every shipped icon that
  could stand for it is already taken in the same menu (clock, list-todo, repeat, timer, rotate-ccw, redo-2), and
  sparkles stays with Activity. The mock draws an approximation; the real SVG has to be added to
  `desktop/assets/icons` (with `LICENSE.txt` covering it). `icons/calendar-sync-mock.svg` is only my drawing.
Question: is one new icon file acceptable, or reuse an existing icon for Replan despite the clash?

## #60 Paper: `60_paper.png`
- **Card edge:** 1 px #8f877a on every card. Page #f7f0e1: 3.13 to 1. Card #fbf6ea: 3.29 to 1 (card_2 #f6f1e8: 3.16). Found by
  moving only the lightness of Paper's `hairline_strong` (#cfc7b9), so the hue stays warm. The exact 3.00 floor is
  #928a7d (3.01 / 3.16); I took a little margin. Today: card vs page 1.05 to 1, `depth none` sets the edge transparent
  (`look.py:1248`), so nothing draws.
- **Block icons:** 16 px (was 11) in a darker mark so each reaches 4.5 to 1 on its own fill: School #0e69b3 (4.51),
  Sports #007835 (4.50), Activity #00727c (4.54), Meals #995500 (4.51), Study #8d4c9c (4.50); Homework #831a1d is
  already 7.67. Today's marks are 2.60 to 3.03 to 1.
- **Timer digits:** I could not reproduce sans or mono digits. On 0.18.4 the Focus screen, the dial clock, One
  thing's countdown and the rail's Session chip all draw Newsreader in Paper. The mock shows Newsreader lining and
  tabular figures (`tnum`) as the proposal, so 29:59 and 28:11 keep one width.
- **Ink** (Paper's dark twin) is shown too: edge #706c65, 3.30 on the page, 3.01 on the card.
Questions: (1) Does Ink get the edge as well? The roadmap says Paper only. (2) Where did you see sans or mono timer
digits in Paper? (3) A 3:1 edge on every card makes Paper busier than today; the board shows it on every card, with the
hairlines inside unchanged. If that is too heavy, the edge could go on the outer cards only.

## #74 Sign-in: `74_signin.png`
- **Wordmark:** fixed at the position the Create card needs (y 125 in a 1366 x 768 window), and the card top fixed
  at y 173. Today the group is centred as a whole, so the wordmark sits at 173 on Sign in and 125 on Create (a 48 px jump).
- **Heading, a real choice.** A (recommended): one heading, "Sign in", on first run and on return. B: keep "Welcome" and
  "Welcome back" (position still fixed). The code today switches on `signed_in_before()`.
- **Hints:** 4 px under their own field and 16 px before the next one. Today they float 10 px and 10 px between two fields.
  Hint text #5b6474 on white 5.97 to 1.
- **Eye:** 24 px glyph in a 32 px box (today 16 in 28), #5b6474 on the white field, 5.97 to 1 (3:1 needed).
- **Background:** after a restart #f7f8fa and after Sign out the last account's look (Pastel's #f3ecff). Proposal: both
  use the device's own look: the System pack, #f7f8fa, or #111315 when the computer is dark.
Questions: (1) A or B for the heading? (2) Sign out showing the device look means a Pastel user sees grey on the
sign-in page, then their own look after sign-in: fine? (3) The field outline on that page (hairline #e4e7ec on white,
1.24 to 1) is below 3:1; it is outside #74's list, so I left it. Want it in?

## #90 Buttons: `90_buttons.png`
- **Unfinished "Hide"** and **Settings restore "Preview"** become outlined: transparent, text colour, 1 px edge
  #7c8088 (the app's `outline_edge`: 3.96 to 1 on a white card; Dark #8b8e91, 5.14), 6 px radius.
- Also proposed: "Save restore point" outlined too (a second bare-text action on the same dialog). "Close" stays plain
  because it only dismisses. Restore stays the one filled button.
- **The exception:** Plan my homework, and its row twin "Plan here", stay tinted: accent 14 % on the card #e4ebf7,
  words #2e518d, 6.54 to 1 (Dark #283040 / #a4bff9, 7.18). Filled buttons: #fff on #3d6fc4, 4.92. The bottom of the
  board is the three-style legend that would go into spec.md (filled / outlined / tinted), which needs your approval to write.
Question: do you want "Save restore point" outlined, and is "Close" plain acceptable?

## #92 Focus ring: `92_focus_ring.png`
Shown at 2.4x, Light and Dark. Today a keyboard-focused top-bar button only recolours a 1 px border to the accent mixed 40 %
into the page: Light #adc1e4 on #f7f8fa = 1.71 to 1; Dark #3d4f73 on #111315 = 2.27 to 1 (the roadmap's 1.8 uses another page tint).
Proposed: a 2 px ring in the accent itself, with a 2 px gap of page colour, outside the 34 px button (46 px
square in all): Light #3d6fc4 = 4.63 to 1; Dark #7fa8ff = 7.93 to 1. Paper 9.93, Ink 7.33, High contrast keeps its yellow.
The top-bar buttons share one rule, so › Today, More and the gear get the same ring; the board shows ‹ only.
Qt note: a 2 px gap is not a stylesheet feature; it would be a border plus the button's own margin, or a painted
ring (the week grid already does one). I did not check which is simpler.

## Not covered
Dark was drawn for #26, #60 (Ink) and #92 only, as asked. #74 shows Dark only for the background. No mockup was run at
Large text or 1024 x 640. Offscreen captures of the app showed some mid-animation artefacts (a title double-drawn and
clipped rows); I redrew those screens in HTML rather than use them as-is.

## Approved by Jonathan, 2026-10-09
- #74: one heading, "Sign in", on first run and on return; the wordmark and card top are fixed; the sign-in page always uses the device's own look; the field edges reach 3:1.
- #25: words on the arcs and a "Reading the ring" key; One thing keeps a quiet ring; the zoom says why it is greyed.
- #26: School uses the `school` icon everywhere; Replan gets Lucide `calendar-sync` (one new icon file).
- #60: the warm 3:1 edge on every card, in Paper and Ink; timer digits in Newsreader with tabular figures.
- #90: "Hide", "Preview" and "Save restore point" are outlined; "Close" stays plain; Plan keeps its tint (into spec.md).
- #92: the 2 px accent ring with a 2 px gap on every top-bar button.
