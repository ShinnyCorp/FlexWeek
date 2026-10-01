# FlexWeek 0.17.2 release notes

Paste-ready body for the v0.17.2 GitHub release. The download sections follow
`docs/github-release.md` and are copied from 0.17.1 unchanged.

```
Places homework around school and sports. Download, open a window, create an account.

**Already on 0.17.1?** You do not need to download anything. FlexWeek offers this update itself: press Update now when it asks, or open Settings (the gear) and choose Check for updates.

## What changed
- **Switching views never flashes blank.** The old page fades as the new one arrives, so the window is never empty, and the title changes with the page instead of a moment before it. Reduce now cross-fades without sliding, visibly calmer than Normal. Plan my homework no longer flashes the top bar or jumps the hours, and its notice comes once, with Undo.
- **Every window is a sheet now.** Routines, Help, About, Running late, School hours, Choose a time and Spread open inside FlexWeek over the dimmed week, like Add and Edit. Every sheet has a title and a close button, labels above their fields, and one of two widths.
- **Easier fields.** Dates open a month drawn in your look. Numbers have a minus and a plus big enough to hit, and a homework's length has quick 15 to 90 minute pills. Times are typed without tiny arrows. Days are picked with pills everywhere, so an alarm's days fit on one row.
- **Buttons look like buttons.** Actions such as Availability…, Manage account…, Check for updates, Add alarm and the recovery codes' Copy and Save… are outlined. The one filled button on a page is its main answer.
- **Looks are easier to find.** Settings' Appearance page starts with Colours, More looks is a grid of small pictures of each look, and Ctrl+K has Look and Settings commands.
- **One strip above the week.** While a timer runs, a single line names it, shows the time left and links to the Focus screen, instead of three stacked strips.
- **Right-click free time to fill it.** The menu offers Add fixed time at that time, Add homework due that day, and Paste, which is greyed out until you have copied something. Each opens its sheet with the day and time already filled in. With the hours focused, Shift+F10 or the Menu key opens the same menu.
- **Blocks carry a small picture of their category.** A house for School, a pencil for Study, a target for Sports, sparkles for an Activity, a clock for Meals, a moon for Sleep. The picture is in the category's own colour. Free time has none. A block too small for all three keeps its name, then its start time: a half-hour Dinner says "Dinner 18:30".
- **Category colours are easier to tell apart.** School, Study and Sleep no longer look alike, and Sleep is darker than the rest.
- **The line for now and the ring round a chosen block use your accent.** They are made only as light or dark as they need to be to show, so in Light the blue stays close to the one you picked.
- **Mission control opens with now in view and as much of the evening as fits.** Its lanes used to open zoomed out. They now show through 22:00, or the end of the day's last block if that is later; when that would push now off the left edge, now sits near the left and the evening is a scroll. Names written beside a block stay inside what shows, so "History" is no longer cut to "Histor".
- **Timeline fills every block with its colour.** School, Dinner and the rest were page-coloured outlined cards unlike every other design.
- **Timeline's two pages meet at a fold line only.** The grey shade either side of it is gone.
- **Paper and Pastel got a fresh coat.** Paper is a cream planner page with an ink-blue accent, serif words and figures, and no shadows. Pastel has tinted cards and fuller block colours. The Sand accent is a clay brown now, so it no longer looks like Gold. In Dark, the chosen view is a lighter chip with a ring round it.
- **Setup speaks plainly and keeps your choices.** Each sport, club and job says whether it is Sports or an Activity, and keeps that when setup opens again; School sits in a card like them, so the times line up down the page, and the example week's Soccer is Sports. The planning-hours choices are pills, and Send a test reminder and Add custom hours are outlined buttons, so none reads as plain text. The example homework is a grey "e.g. History essay"; leave it empty and Done says "None yet". Setup names each design as Settings does: "Today's app", not "Calendar · Today's app".
- **Sign in says the name once.** It is in the wordmark, and the heading is "Welcome" or "Welcome back". Creating an account is the stronger link under Sign in, and Forgot password is lighter. A link under the pointer or reached by the keyboard turns a darker shade of the accent and is underlined.
- **An empty Saturday or Sunday takes less room on Week.** The days with something in them share the rest, and the empty day widens as soon as you put something on it.
- **Blocks that share a time drop the black dot.** They already sit side by side, and the dot covered the end of the name.

## Fixed
- Today's app's hours end at 23:00: the "24:00" label under them is gone, in Day and Week.
- Beside the hours, a homework's title is cut only when the row has no room for it: "Math worksheet" beside "Today 16:15" is now said whole.
- The line for now crosses a block over its colour and stops a few pixels short of its words and picture, in every design. Timeline's and Clay deck's time pills sit beside the hours instead of on a block.
- Timeline's time pill sits beside the hour labels, in place of the one it is nearest, or in the right page's margin at the fold. It lay on the day before and covered its blocks.
- Mission control's time pill no longer lies over an hour label when the view is zoomed out: the label it would cover is left out.
- In the look editor, Readability lists each place a pale accent of your own is used as words (the plan, today's name, the line for now), each with a Fix, and the app draws those words darker until then. The built-in accents are never listed.
- Terminal's Next card wraps the time left instead of cutting it off.
- The look pictures in Settings widen with the text, so at Large text, as in High contrast, each look's name stays on one line.
- Day keeps Now on the hours grid rather than between the day's rows.
- Week titles, time labels, recovery codes and the spacing between a tick and its action are clearer at narrow widths.
- On a week that runs into a new month, Month and the mini month show the month that holds today, so today is no longer faded like last month's days. Month to Day opens the day you picked, and My day's title names the day.
- Day, Week and every design keep the hours where you scrolled them when you switch views, open the focus screen or Settings, or change the look. They open at now when FlexWeek starts, when you press Today, and when you come back to this week; the week you pressed Today from stays where you left it.
- Help and the other scrolling sheets use the app's thin scroll bar instead of a thick one that took width from the words.
- At a narrow window, Week's day header shows a day's homework as "1 h 30" when "1 h 30 min" would be cut off.
- Setup's style and look cards fit a narrow window: they run one to a row when two would not fit, instead of running off the right edge.
- Clay deck's side days are whole, label their hours and show homework by name; they were cut by the window's edge.
- Bento's Week says when each block starts, and Bento and Retro write a placed time as "placed Wed 19:00", so it is not read as the due time.
- Mission control's Focus minutes say "Focusing now" while a session runs, not "None yet this week".
- School hours says no school days are picked only when none are.
- Ctrl+K tints the row Enter will run, shows the whole list when it fits, and draws key hints as keycaps.
- Every More menu group has a heading, and a greyed Unfinished says "None left".
- A new alarm starts at 07:00, its Spotify field is labelled, and Remove alarm shows only when there is an alarm.
- In Retro desktop a notice no longer covers the taskbar's bell and clock.
- With the 12-hour clock, hour labels and the time-now pill show whole in every design; 9:00 AM read ":00 AM".

## Download for Windows
`FlexWeek-Windows-x64-Setup.exe`

Run it to install FlexWeek for your Windows account (no administrator needed), then open FlexWeek from the Start menu. If Windows shows "Windows protected your PC", choose More info, then Run anyway. FlexWeek is not code-signed yet. Unicode text support (ICU) is part of Windows 10 version 1809 and later.

Schools and IT: `FlexWeek-Windows-x64.msi` installs FlexWeek for every account on the PC and needs an administrator. Use one installer or the other.

## Download for Linux
`FlexWeek-Linux-x86_64.tar.gz`

Extract, then open the file named FlexWeek. Needs a 64-bit Linux desktop (GNOME, KDE Plasma, Cinnamon, Xfce), glibc 2.38 or newer (Ubuntu 24.04, Linux Mint 22, Debian 13, Fedora 39 or newer), and working graphics (OpenGL or EGL). It uses libraries every desktop has, starting with libEGL.so.1; the README's "Linux libraries" lists them and shows how to find one that is missing. The X11 helpers many desktops leave out (libxcb-cursor and five others) are inside this download. Alarm sounds use your desktop's audio (PulseAudio or PipeWire); without it the alarm still appears, silently.

`FlexWeek-x86_64.AppImage` is the same app in one file. If it won't start (missing FUSE), run `chmod +x FlexWeek-x86_64.AppImage && ./FlexWeek-x86_64.AppImage --appimage-extract`, which unpacks a `squashfs-root` folder, then run `./squashfs-root/AppRun`. Without FUSE, the tarball above is the reliable choice.

## Chromebooks
Not supported. FlexWeek is a Windows and Linux desktop app, and there is no web version.

## Checksums
Optional. `FlexWeek-Windows-x64-Setup.exe.sha256`, `FlexWeek-Windows-x64.msi.sha256`, `FlexWeek-Linux-x86_64.tar.gz.sha256` and `FlexWeek-x86_64.AppImage.sha256` on this page. Each names only its file, so `sha256sum -c` works in the folder you downloaded to.

## First open
The first screen is Sign in. Choose "New here? Create an account" under it. Setup then goes a page at a time: a style, your week, how homework gets a time, reminders and the alarm sound, and your first homework. You can skip any page.
```
