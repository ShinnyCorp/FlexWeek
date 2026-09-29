# AL's 0.16.0 design review, checked

AL's final report on 0.16.0 (40 items: six to fix first, eight on motion, then colour and type,
dialogs, the four views, and the other screens) checked against the code at v0.16.0 (`d657f92`)
and against fresh pictures of it: Today's app's Week, Day and Month on a Thursday evening, the 12-hour
clock at 1280, 1100 and 820 pixels, the Add and right-click menus, the toast, Ctrl+K, the focus
screen both ways in, My day with nothing left, Mission control in Dark, High contrast, the homework
editor in Dark, School hours, Help and About (`~/.flexweek-ui-harness/scratch/a017`, `a017b`,
`a017c`, made by `scratch/audit_017.py`), a plan and a running focus timer in Light and High
contrast (`a017d`, made by `scratch/audit_017b.py`), with Settings and setup from the 0.16
integration tour (`scratch/int016-setup`). Motion is read from the code; AL's frame-by-frame
recordings are the evidence for what it looks like on a desktop.

Verdicts: **Bug** (wrong, fix without asking), **Designed** (works as built; changing it is a
decision), **Partly** (some of it reproduced), **Not reproduced**, **Design** (taste; a decision).

## Found in this pass, not in the report

| # | What | Evidence | Needs |
| --- | --- | --- | --- |
| N2 | The 12-hour clock's hour labels are cut at the gutter's left edge: "l0:00 AM", "l2:00 PM". | `a017c/week-12h-1280.png`. The gutter was sized for "00:00". | Bug. |

## Fix first

| # | Their finding | Found | Needs |
| --- | --- | --- | --- |
| 1 | One accent everywhere: Sign in blue, Week teal, My day periwinkle, Add mint in Dark and black in Timeline; picking an accent tints the page. | Designed, and confirmed as seen. Each look carries its own accent (Slate `#3d6fc4` blue, Light frost teal, Dark frost mint, Nocturne `#7fa8ff`), a design's colourway brings its own (Timeline's paper is black, Day dial's navy periwinkle), and signed-out screens follow the device's look. A chosen accent replaces only the accent (`look.py` `resolved_palette`); the page tint is the look's own page colour. | Decision: one accent, which no look or design replaces. |
| 2 | My day turns the whole app navy in the Light look, top bar included. | Confirmed: Day dial's default colourway is dark, and while a design shows, the window takes its colours. | Decision: the day screen follows the look. |
| 3 | The plan result is a raw full-width white box with two filled buttons; its toast says "Planned 0 homework blocks" while the banner says 2 were placed; in High contrast its text is clipped. | Confirmed, with the cause of the count: the banner's heading counts every placed block in the solver's trace (`widgets.py` `PlanReview.set_trace`, `len(trace["placed"])`), homework already placed included, while the toast counts only homework this plan gave a time (`controller.py` `plan_sentence`). High contrast cuts the toast to "Planned 2 homework" and its Undo (`a017d/focus-running-high-contrast.png`). | Count and clipping: bug. A slim bar: design. |
| 4 | High contrast: unselected Day, Month and My day are pale yellow on light; sidebar items cut to "Math wo…". | Confirmed (`a017/week-high-contrast.png`): the view control is yellow words on light grey; tray chips cut ("Math worksheet · 1 ł"); the focus list gets a sideways scrollbar. | Bug. |
| 5 | Sign in says "Sign in" then "Welcome."; the heading competes with the wordmark; no shadow, an uneven empty bottom, the password field narrower than the username; Create account still shows Forgot password; "Save...". | Confirmed, except "Save…": its ellipsis is the convention for a button that opens a file dialog. The password field is narrower because Show sits beside it; Create account swaps only the two main buttons (`window.py`), so Forgot password stays. | Bug, except the week preview beside the card (design). |
| 6 | With a timer running and the plan banner up, Week stacks the timer strip, its note and the banner above the grid, which starts more than halfway down; the side panel says Now at the same time. | Confirmed (`a017d/focus-running-with-banner.png`): the running timer is a card with "Work on this until the timer ends…" above the hours, and the plan banner adds another layer. | Design: the running timer in the side panel's top, one line. |

## Motion

| # | Their finding | Found | Needs |
| --- | --- | --- | --- |
| 7 | Month to My day: the top bar turns navy on the first frame while Month is still fading; back, it snaps light over the fading dial; "Not placed yet" pops in after. | Confirmed from the code: the window's colours change in one `setStyleSheet` (`window.py` `_apply_appearance`) while `switch_page` crossfades only the content, so the two change on different frames. | Bug. |
| 8 | Every view switch is a crossfade whose middle frames show two grids at once. | Designed in 0.16: the new page fades in under a fading picture of the old. | Decision: fade through, or a short slide for Day, Week and Month. |
| 9 | Picking Timeline in Settings turns the page beige and Add black at once while Settings fades out. | Confirmed; the same cause as 7. | Bug. |
| 10 | Plan from My day shrinks the dial in one frame, then the banner fades in while the toast slides in at the bottom. | Confirmed from the code: the banner joins the layout before it fades (`appear(self.plan_review)`), and the toast is separate. | Bug-sized. |
| 11 | The homework editor and Ctrl+K appear fully drawn in one frame; Ctrl+K's backdrop at full strength. | Confirmed, with the cause: dialogs fade through window opacity (`motion.appear`, `setWindowOpacity`), which Wayland does not support, so on a Wayland desktop they appear at once; `CommandBar.open` has no fade at all. | Bug. |
| 12 | The view control's selection jumps; hovers snap. | Designed: style sheets cannot animate. | Design: a painted, sliding selection and a hover tint. |
| 13 | Settings sections don't visibly slide, though the code says they do; setup's pages do. | Partly: `SettingsPage._show_section` slides at the window's Animations level (`settings.py:840`); not seen on a desktop in this pass. | A look on the desktop, then a bug if it holds. |
| 14 | No reduce-motion setting; it should at least stop the navy flash. | Not reproduced: Settings > Appearance & layout > Every screen > Animations has Off. It cannot stop the navy flash, which is a colour change, not an animation (item 2). | With 2. |

## Colour and type

| # | Their finding | Found | Needs |
| --- | --- | --- | --- |
| 15 | Text sizes per screen; weights jump 600, 700, 800. A scale of about five sizes and two weights. | Confirmed. `look.py` sets titles at base +1, +2, +3, +4, +6 and +8 pt and 96 pt, in weights 500, 600, 700 and 800 (19 rules at 600, 24 at 700, 2 at 800). | Design; the scale is Claude's call. |
| 16 | Block colours are not one family: bright cyan Soccer, pastel School, grey Club; the red now pill on coral homework; red chip edges beside teal. | Confirmed. Activity `#a5f3fc` is lighter and more saturated than School `#bfdbfe`; Free is grey; the now pill is the error red and sits on homework coral at 21:30–22:00 (`a017b/week-evening-1280.png`); tray chips carry the homework mark on their left edge. | Design: one lightness for every category, and a now colour apart from homework. |
| 17 | The Add menu mixes actions with eight colour dots; Bento adds indigo and orange. | Confirmed for the menu (`a017/add-menu.png`: three actions, then "Then drag on the calendar" and eight dotted types). Bento not checked in this pass. | Design: the types behind a submenu. |
| 18 | Month's weekday names and My day's "TODAY, HOUR BY HOUR" are the only all-caps headers. | Confirmed: Month paints MON to SUN; `layouts/dial.py` upper-cases its heading, "IN 30 MIN", "THEN … AT" and the card's kicker. | Bug-sized. |

## Dialogs and forms

| # | Their finding | Found | Needs |
| --- | --- | --- | --- |
| 19 | Dialogs are separate windows with title bars. The homework editor in Dark has a light frame inside the window and a large empty area under More details. | Windows: Designed (every editor is a `QDialog`). Frame and empty area: confirmed (`a017/homework-editor-dark.png`: the scrolled body is framed, and a 320-pixel minimum leaves it half empty). | Frame and space: bug. In-window sheets: decision. |
| 20 | Labels sit a few pixels above their field's text; "Estimated time" wraps; Due is narrower; "or 45." alone; More details as heavy as a main button; Save left of Cancel. | Label alignment, Due's width, "or 45." and More details: confirmed (`homework-editor-dark.png`). "Estimated time" wrapping: not at 1280 with normal text. Save's place: Designed; `QDialogButtonBox` follows the platform, and Windows and KDE put Save first while GNOME and macOS put it last. | Form: bug. Button order: decision. |
| 21 | Three day pickers; unselected pills have no outline; old spin boxes of different widths. | Confirmed: pills (`setup.py` `DayPicker`, in setup and School hours), checkboxes in the event editor (`widgets.py:1297`), planning hours (`work_windows.py:50`) and alarms. Spin boxes are Qt's, with arrows, full width in some forms and narrow in others (Alerts). | Bug-sized: one day picker, one number and time field. |
| 22 | Routines: filled "Save this week as a routine", plain Delete not red, a bare list of checkboxes. | Confirmed (`int016-setup/routines.png`). | Bug. |

## Week, Day, Month and My day

| # | Their finding | Found | Needs |
| --- | --- | --- | --- |
| 23 | Names cut at full width; Club "19:00–20:00 · …"; School wraps "6 h 45 min"; with the 12-hour clock, and at 820 and 1100, times disappear. | Confirmed, all of it (`a017b/week-evening-1280.png`, `a017c/week-12h-*.png`). With 12 hours no block shows a time even at 1280: 0.16 drops a time range that cannot fit its column, and "4:00 PM–5:30 PM" never fits. Under 1150 names only is 0.16's narrow rule. | Bug: a shorter 12-hour range ("4–5:30 PM"), the length after the name, and ellipses only on what is cut. |
| 24 | Today's column is heavily tinted; on Day the whole canvas; a one-hour block is a wide flat slab with no coloured edge. | Confirmed (`a017b/day-evening-1280.png`): Day's one track is today, so all of it is washed; blocks there are fills with no mark. | Design: a lighter today, and Day's blocks with their category edge. |
| 25 | Hour rows unequal after scrolling; the first label crowds the day names; "24:00"; School nameless when scrolled out. | Rows: not reproduced; every hour is 48 px at Week's default zoom, and the short top row is the hour the view starts part-way into. "24:00" is Designed (the day ends there). School nameless: confirmed; a long block keeps its name at the top edge only while two lines of it remain on screen (`hours/canvas.py`, `words`). | Name at the edge: bug. Open at a whole hour: design. |
| 26 | Zoom − and + look like debug controls; a greyed minus looks broken; grey More looks disabled. | Confirmed. The minus greys at the lowest level by design. | Design. |
| 27 | Side panel: bold accent headings look like links; "Math worksheet  22:30" double space; Summary 3 px out; the scrollbar stuck to the panel. | Confirmed, all four (`hours/classic.py:166` joins with two spaces). | Bug. |
| 28 | Day opens on an empty evening; the now pill half cut at the bottom; "History e…" cut with room; the Next line and banner push Day's and Month's grid down. | Opening at now is Designed (0.15, `9ff5bdc`); late in the day that is empty hours. The pill at the bottom follows from it. "History e…": not reproduced at 1280. Next line above Day and Month: confirmed; Week moved it into its side, Day and Month did not. | Design: open late days at the last block; Next beside Day and Month too. |
| 29 | Month has huge, mostly empty rows; its scrollbar overlaps the grid. | Rows: Designed in 0.16 (rows grow so this week is the first row; late in a month two tall weeks show). Scrollbar over the Sunday column: confirmed (`a017/month-1280.png`). | Scrollbar: bug. Rows: decision (reverse the 0.16 choice). |
| 30 | My day repeats "Nothing else scheduled today"; the hand pokes past the ring across "22"; the big time sits on the hand's centre; pills; "task". | Confirmed (`a017/myday-dial-late.png`: the words twice in the card, as kicker and title; the hand runs past the ring; "1 task not placed yet" from `dial.py:520`). Day dial's navy also ignores a light look. | Bug, and a decision on the navy. |
| 31 | The smallest window is not 800 px; the code never sets it. | Partly. The code sets 800 (`window.py:154`, `:403`) and raises it to what the top bar needs (`_keep_bar_whole`); with normal text the window does go to 800 (asked for 700, got 800). At large text, or with wider fonts, the bar needs more, so 820 and 900 are plausible. | Bug: the bar wraps further so 800 holds at every text size. |

## Settings, menus and other screens

| # | Their finding | Found | Needs |
| --- | --- | --- | --- |
| 32 | Settings: narrow left-aligned cards; plain section list; Look and Accent dropdowns; "Experimental styles" looks pickable; 3 + 1 uneven experimental cards; "Saved preferences." in the footer; Updates misaligned; "80 %"; the last paragraph under the footer. | Cards are up to 760 px and left-aligned, so a quarter of the page is empty at 1280 (not 400 px wide here). Section list, dropdowns, uneven cards, Updates row and "80 %" (`settings.py:495`): confirmed. "Saved preferences." in the footer: not seen. Last card under the footer: it scrolls there. | Design, most of it; "80%" and Updates: bug. |
| 33 | Style names differ between setup and Settings; setup's style cards cut off. | Names: confirmed (setup's Plain calendar and Night owl; Settings' "Calendar · Today's app"). Cards cut: not reproduced at 1280×860 or 1150×768; at 768 a scrollbar appears. | Names: decision. Cards: ask for their window. |
| 34 | Ctrl+K: flat grey backdrop, a scrollbar, no icons, sections or shortcut hints. | Confirmed (`a017/command-bar.png`). | Design. |
| 35 | The toast is pale on a pale page and can cover blocks. | Confirmed (`a017/toast.png`). | Design: dark toast, clear of the hours. |
| 36 | The right-click menu: no icons, Delete and Delete homework not red, no separator; Advanced's jargon. | Confirmed (`a017/right-click-menu.png`; Advanced has "Copy the selected day", paste and reload). | Bug for the menu; words for Advanced. |
| 37 | The focus screen is light, puts "Quick focus" under the timer, small Start and Back, no ring; from More it starts at once, from Start a focus timer it waits. | Confirmed (`a017/focus-from-f.png`, `focus-from-quick.png`); More > Quick focus calls `start_quick_focus`, while F opens it ready. | Design, and one rule for starting. |
| 38 | Mission control in Dark shows internal labels; "Math w…"; floating zoom buttons. Timeline: heavy black day names and a second Add. Clay: tilted and clipped. | Mission: confirmed ("FLEXWEEK / DAY / SUNDAY 27 · LOCAL 21:30 · PLAN 1/2 PLACED", "NOT PLACED YET · CARGO BAY", zoom halfway down the left). "Math w…": not reproduced. Timeline: confirmed (its Add is plain since 0.16 but still there). Clay: not checked in this pass. | Design (all experimental except Timeline). |
| 39 | Help says a tutorial is coming; shortcuts as plain text; left cards run off with no sign; About has no logo. | Confirmed. The tutorial line was Jonathan's footnote in 0.15. | Design; the tutorial line is Jonathan's. |
| 40 | Setup: content top-left with the right third empty; no ticks on finished steps; "Add custom hours" and "Send a test reminder" filled like Next; five "▶ Play"; the school hint shown even with days picked. | Confirmed, all five; the hint is in setup (`setup.py:765`) and School hours (`widgets.py:1515`). | Bug. |

## Bugs that need no decision

N2, 3 (count and clipping), 4, 5 (all but the preview), 7, 9, 10, 11, 18, 19 (frame and space),
20 (form), 21, 22, 23, 25 (name at the edge), 27, 29 (scrollbar), 30 (repeats, hand, "task"), 31,
32 ("80%" and Updates), 36 (menu), 40.

## Decisions for Jonathan

The rest, as the report recommends or item by item: 1 (one accent), 2 (My day follows the look),
3 (a slim plan bar), 5 (a week preview at sign in), 6 (the running timer in the side panel), 8
(fade through or slide), 12 (a sliding selection), 15 (a type scale), 16 (one colour family), 17
(types in a submenu), 19 (in-window sheets), 20 (Save on the right), 24 (lighter today, edged
blocks on Day), 25 (open at a whole hour), 26 (zoom and More), 28 (late days open at the last
block; Next beside Day and Month), 29 (Month's rows), 32 to 35 (Settings, names, Ctrl+K, the
toast), 37 to 39 (the focus screen, the experimental designs, Help and About).
