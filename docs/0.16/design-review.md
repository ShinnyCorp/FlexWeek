# Timmy and AL's 0.15.0 design review, checked

Their agreed list (34 items, numbered R1 to R34 here in their order) checked against the code at
v0.15.0 and against fresh pictures of the app: every design's Day, Week and Month, both My day
screens, sign in, the recovery codes, every setup page, Settings, the More menu, the editors,
Routines and Help, at 1280x860, at 1150x768 with large text, and at 800 and 650 wide
(`~/.flexweek-ui-harness/scratch/audit2/` and `audit3/`, made by `audit_tour_2.py` and
`audit_setup.py` there). Each row says what was found and what it needs. "Decision" means the app
does what it was built to do and the change is a product choice, Jonathan's to make.

Verdicts: **Bug** (wrong, fix without asking), **Designed** (works as built; changing it is a
decision), **Not reproduced**, **Design** (their taste against ours; a decision).

## Fix first

| # | Their finding | Found | Needs |
| --- | --- | --- | --- |
| R1 | Add homework is under More > Adding in Today's app; Timeline, Bento and Clay show an Add button. | Designed. Today's app's top bar is Day, Week, Month, My day, Plan my homework, More, gear; Add is `More > Adding`. The designs with an Add button have it in their own chrome. | Decision 1. |
| R2 | The Next line, the focus-timer strip and Not placed yet stack above Week's grid. | Confirmed: at 1280x860 they take about 215 px of 860, a quarter of the window, before the day names (`audit2/laptop-classic-week.png`). Day already has a sidebar for the tray and the summary. | Decision 2. |
| R3 | Too many looks: 6 designs x 10 looks x 5 accents x knobs. | Designed. Six main designs (`layouts/registry.py`), five packs and six presets (`look.py` `PACKS`, `LOOK_PRESETS`), five accents, seven knobs. | Decision 3. |
| R4 | The top bar stays the same while the content switches style; My day changes palette. | Designed: the window's chrome takes the pack, a design paints its own content in its tokens (`docs/0.15/architecture.md`). | Decision 3. |
| R5 | Unfinished does nothing. | Designed, and explained on hover: it is greyed until an earlier week was saved and homework from it still needs time (`reuse.py` `unfinished_items`: nothing before the first saved week counts). On a new account it is always grey; the tooltip says "Nothing is unfinished". Both reviewers had new accounts. | Nothing to fix. If a greyed menu item reads as "does nothing", that is R6's segmented-control question. |

## Layout and visual design

| # | Their finding | Found | Needs |
| --- | --- | --- | --- |
| R6 | Day, Week, Month and My day should be one segmented control; the bar has eight equal buttons. | Confirmed as described: prev, next, Today, Day, Week, Month, My day, Plan my homework, More, gear. | Decision 4. |
| R7 | Bundle a font. | Confirmed: `look.py` `FONT_FAMILIES` asks for Noto Sans, then DejaVu Sans, then the system sans; nothing is shipped, so Windows draws it in whatever it has. Block titles are the bold weight of that face. | Decision 5. |
| R8 | Cards and dialogs pad about 8 px. | Confirmed: `DENSITY_PAD["comfortable"] = 8` is every frame's padding; sign in and the recovery card show it (`audit3/signin.png`). | Bug-sized change, but it moves every screen: decision 6. |
| R9 | Field labels sit off the middle of their boxes in Add homework, New event and the block editor. | Not reproduced at 1280x860: Title, Due, Estimated time, Start and End labels are centred on their boxes (`audit2/laptop-add-homework.png`, `laptop-edit-block.png`). May be a Windows or large-text case; ask for a picture. | Ask. |
| R10 | One filled button per dialog: More details, Routines' four, sign in's Show. | Confirmed. Every `QPushButton` is filled unless it is marked `quiet`; "More details" (`widgets.py:1302`), Routines' Save, Apply, Delete and Close (`audit3/routines.png`) and Show (`window.py:476`) are not. | Bug. |
| R11 | Settings as a full page with grouped cards, toggles and segmented controls, design thumbnails; headings cut when scrolling. | Half confirmed: Settings is a 685x596 dialog with a list on the left and a scrolled page; Spacing and Colours are dropdowns of two or three choices. Headings were not cut in a scrolled picture (`audit3/settings-appearance-scrolled.png`). | Decision 7. |
| R12 | Dark looks need darker block colours and stronger grid lines. | Confirmed: `look.py` `block_paint` fills a block with the category's pale colour on every pack (`#fbcfe8`, `#bfdbfe`) and only picks the ink; on Dark frost pale pink sits on near-black, and the half-hour rules nearly vanish (`audit3/classic-week-dark-frost.png`). | Bug. |
| R13 | Homework and activities look alike: pink against coral. | Confirmed: Activity is `#fbcfe8`, Homework `#fecaca` (`calendar.py` `CATEGORIES`); side by side in `audit3/classic-week-club.png`. | Bug, with a palette choice: decision 8. |
| R14 | Block text is cut when there is room, such as Club in a full hour. | Confirmed: a one-hour block at the default zoom (48 px an hour) shows one elided line, "Club · 19:00–20:00 · …", although its name and its times would fit on two. `canvas.py` `words` takes the two-line form only when the block is taller than two bold lines (`room.height() < 2 * line`), and the second line is drawn in the smaller plain font, so the test is a line too strict. | Bug. |
| R15 | Drop the dashed half-hour lines; 14:00–15:00 is shorter than other rows. | Half-hour rules are drawn on purpose (`canvas.py` `track`). Unequal rows not reproduced: rows are 48 px each at that zoom in every picture; the hour pitch is an integer at every level. Ask which zoom and window. | Dashes: decision 9. Rows: ask. |
| R16 | Label the now line with the time; highlight today more. | Confirmed: `canvas.py` `now` draws a dot and a line, no time; today's column has a 5 % accent wash. | Design; small. Decision 9. |
| R17 | One toast instead of the status line and the Undo notice; it should go on a view switch and never sit off the bottom. | Designed: the status line is the record, the Undo notice sits beside it under the hours (0.15's fix for a drag that moved the page), reminders and Advanced use the toast under the top bar. Whether it can sit off the bottom: the window's minimum height is what keeps it on; not seen in any picture. | Decision 10. |
| R18 | Raw-widget screens: the focus-timer list, Routines, Running late's empty box, Quick focus's three buttons. | Confirmed for Routines (`audit3/routines.png`: a list box, an empty box, a date dropdown, four filled buttons) and the focus strip (a bare list under "Start a focus timer:"). | Design; decision 7 covers the dialogs. |
| R19 | Day's homework blocks are flat slabs; Summary is plain text. | Confirmed as described (`audit2/laptop-classic-day.png`). | Design; decision 9. |
| R20 | Month should open on the current week, not with past weeks on top. | Designed: Month is the calendar month, six rows, scrolled so the current week is in view (`month.py` `reveal`); at 1280x860 the whole month fits, so the past rows are above. | Decision 11. |
| R21 | Setup: style cards cut at the bottom; the "When may FlexWeek plan?" chips show no selection; the alarm Play buttons do not line up. | Cards: not reproduced at 1280x860 or 1150x768 (`audit3/setup-0-step0.png`, `setup-small-step0.png`; a scrollbar appears at the smaller size). Chips: confirmed, and worse than it looks: After school, Evenings and Weekend mornings are not toggles but buttons that add a row of hours under them (`work_windows.py` `PRESETS`), drawn as filled pills that read as choices (`audit3/setup-2-step4.png`). Play: confirmed, the five "▶ Play" links sit in a three-column grid with the radio buttons and do not line up (`setup-3-step5.png`). | Chips and Play: bug. Cards: ask for their window size. |
| R22 | Help is a wall of text; About shows a raw path. | Help has headings and a shortcut table (`audit3/help.png`); it is long. About shows the folder as text. | Design; decision 12. |
| R23 | Plain wordmark, a lime dumbbell icon, "Welcome back" on first launch. | Confirmed: "Welcome back." is the sign-in note whenever the form is not creating an account (`window.py:392`), first launch included. The wordmark is a bold accent label. | "Welcome" on first launch: bug. Icon and wordmark: decision 12. |
| R24 | Recovery codes in monospace with Copy and Save. | Confirmed: a plain `QLabel` of eight codes, selectable by mouse, no buttons (`audit3/recovery-codes.png`). | Bug. |
| R25 | A literal "→" in the Now/Next line; offer a 12-hour clock. | Not reproduced in the Next line ("Next: Soccer practice at 16:00 (in 20 min)"). The arrow is in Running late's preview rows (`widgets.py:2177`) and setup's "Choose my own look instead →". No 12-hour clock anywhere. | Arrows: bug-sized. Clock: decision 13. |
| R26 | Narrow windows: titles cut at 800, "Plan" and a wide sidebar at 650. | Confirmed (`audit2/narrow-800-classic-week.png`, `narrow-650-classic-week.png`): at 800 the top bar wraps to two rows and Soccer practice is "Soccer …"; at 650 blocks are "Socc…" and "Dinner…". Plan my homework becoming Plan is 0.15's rule. | Decision 14: what is the smallest window FlexWeek is for? |

## Motion

| # | Their finding | Found | Needs |
| --- | --- | --- | --- |
| R27 | The fade lays a picture of the old screen over the new one; use a crossfade; slide blocks after Plan; ease dialogs and toasts in. | Designed: `motion.py` `hold_picture` grabs the old screen and fades the picture out over the new one, which is a crossfade of the whole surface; a stale picture can show for a frame when the new screen lays out late. Blocks jump into place after Plan; the toast fades in (`appear`), dialogs do not. | Decision 9. |

## Functional

| # | Their finding | Found | Needs |
| --- | --- | --- | --- |
| R28 | Add homework's Title starts as the word "Homework", not a hint; typing appends; Ctrl+A does not select it. | Prefill confirmed: More > Add homework opens with the armed category's label as the title (`widgets.py` `HomeworkDialog`: `"title": info["label"]`), so a student who types gets "HomeworkMath worksheet". Ctrl+A not reproduced: in a probe it selects the word and typing replaces it (`scratch/ctrl_a_probe.py`). | Bug: an empty title with a placeholder. |
| R29 | No right-click menu; opening takes a double-click. | Designed: a click selects, a double-click opens, a drag moves (`canvas.py` `mouseDoubleClickEvent`); there is no `contextMenuEvent`. | Decision 15. |
| R30 | School hours opens the generic Edit event dialog. | Designed: `window.py` `_school_hours` opens the block editor on the School block, or a new one filled in Monday to Friday 08:00–14:30. | Decision 15. |
| R31 | Pastel is in the code but not offered. | Not reproduced: Pastel is in Settings > Appearance & layout > Look, with the other device presets (`look.py` `look_menu_items`). Setup offers styles and designs, not looks, which may be where they looked. | Nothing to fix; maybe a word in setup. |

## Add

| # | Their finding | Found | Needs |
| --- | --- | --- | --- |
| R32 | An empty-week screen with one "Add your first homework" button. | Confirmed absent: an empty week is an empty grid; Day's summary says "Nothing planned." | Decision 16. |
| R33 | A full-screen focus timer. | Absent; focus runs in the strip under the Next line and in One thing. | Decision 16. |
| R34 | A Ctrl+K command bar. | Absent. | Decision 16. |

## Bugs that need no decision

Fix in one lane, with tests and the rig: R10 (quiet buttons where a dialog has more than one),
R12 (dark packs get their own block fills and stronger rules), R14 (the two-line test counts the
second line at its own font), R21 (the planning-hours presets drawn as add buttons with their
rows, and Play buttons in a column), R23 ("Welcome" on first launch), R24 (codes in the mono face
with Copy and Save), R25 (words for the arrows), R28 (an empty title with a placeholder).

## Decisions for Jonathan

1. **Add on the default view** (R1). Add as the filled button and Plan my homework plain, in
   Today's app's top bar; or keep Plan as the one filled button and Add under More.
2. **Week's strips** (R2). Fold the Next line, the focus strip and Not placed yet into one line, or
   into a sidebar as Day has, or leave them.
3. **How many looks** (R3, R4). Keep all six designs and every look as they are; or one polished
   default (Today's app, Day dial, light and dark, an accent) with Timeline as the alternative and
   the rest under "Experimental"; and whether the chrome should take the design's tokens.
4. **The top bar** (R6). A segmented Day | Week | Month | My day, or the buttons as they are.
5. **A bundled font** (R7). Ship one face (Inter or Noto Sans, two or three weights, tabular
   numbers) so every computer draws the same app, at about 1 MB per weight; or keep the system's.
6. **Padding** (R8). 16 px comfortable and 8 px compact, or as it is.
7. **Settings' shape** (R11, R18). A full page with cards, toggles and segmented choices, and the
   dialogs restyled; or the dialog as it is.
8. **Category colours** (R13). Move Activity away from Homework's coral; which of the two changes.
9. **Grid and blocks** (R15, R16, R19, R27). Dashed half hours, a time on the now line, a stronger
   today, shaped homework blocks on Day, blocks sliding after Plan, dialogs easing in.
10. **Notices** (R17). One toast for everything, or the status line and Undo notice as they are.
11. **Month's first view** (R20). Open scrolled to the current week at the top, or the whole month.
12. **Help, About and the brand** (R22, R23). A laid-out Help, About's folder as a button, a
    wordmark and an icon in the app's colours.
13. **A 12-hour clock** (R25). A setting, or 24-hour only.
14. **The smallest window** (R26). Name a floor (1024 wide?) and stop things breaking below it, or
    design the 650-wide case.
15. **Opening blocks** (R29, R30). A single click to open, a right-click menu, and a School hours
    dialog of its own; or the current click-selects, double-click-opens and the shared editor.
16. **Additions** (R32 to R34). An empty-week screen, a full-screen focus timer, a Ctrl+K bar:
    which, and in which version.
