# FlexWeek 0.17.0 release notes (draft)

Paste-ready body for the v0.17.0 GitHub release, drafted before the release is cut:
`desktop/native/version.py` and the CHANGELOG heading take 0.17.0 then. The download sections
follow `docs/github-release.md` and are copied from 0.16.0 unchanged. The builds carry four more
typefaces in `desktop/assets/fonts` (Newsreader, JetBrains Mono, Pixelify Sans and VT323, each with
its OFL licence); both build scripts ship `desktop/assets` whole, so packaging did not change.

```
Places homework around school and sports. Download, open a window, create an account.

**Already on 0.16.x?** FlexWeek offers this update itself: open Settings (the gear) and choose Check for updates.

## What changed
- **One system for every screen.** FlexWeek's blue is the one accent, and Sky, Sea, Gold and Sand still replace it. Pages and cards are neutral, text is on one scale, corners and shadows are the same everywhere, and red means a problem. The category colours are one family, homework carries a book, and homework's colour stays apart from Exercise's for a student who cannot tell red from green.
- **Ten looks, redrawn.** Light, Dark, High contrast, Slate, Nocturne, Paper, Ink, Terminal, Poster and Pastel, with System following your computer between Light and Dark. Ink is new: Paper's night counterpart. Look in Settings is Light, Dark or System, with the others under More looks. FlexWeek now brings Newsreader for serif headings and JetBrains Mono, as it brings Inter. Whatever you chose before still opens.
- **A look of your own.** Customise… under Look opens the look editor. Start from any look and change the accent, the colours, each category's colour, corners, spacing, shadows, fonts, text size, how blocks are drawn, the grid and the motion, and the week changes as you go. If a colour is hard to read, Readability says so, and Fix makes it readable. Save the look by name, and share it as a small file with Export and Import.
- **Today's app has a rail** on the left of Day and Week: a small month you can fold away, what is next, homework not placed yet, and the homework to start a focus timer on. The week gets the rest of the width, and Day lists the day beside its hours.
- **Timeline is a paper planner opened flat:** Monday to Wednesday on the left page, Thursday to Sunday on the right, with sticky notes for homework not placed yet and what is due.
- **Mission control is an ops board:** four figures across the top, the days as lanes of hours, and a table of deadlines by time left.
- **Bento lets you pick its big tile:** "Hero: Week | Today" in its settings. Today puts today's hours in the big tile, with the other days as small tiles you can click into it.
- **Clay deck is a row of cards,** one day at a time, with the days either side peeking. The arrows, or the wheel over the side cards, slide it a day.
- **Retro desktop is Windows 98:** bevels, navy title bars, Notepad for your deadlines, a taskbar and Start. Its windows minimise, maximise and close.
- **One thing counts down on a ring** to what is next, with what comes after listed under it.
- **Day dial is the whole day on a 24-hour ring,** noon at the top, with Up next and the day's list beside it.
- **Some design options are renamed or gone.** One thing's Black and orange is now Poster, in your accent. Day dial's Midnight is now Night, Clay deck's Pastel is now Clay, and Timeline's Paper is now Ruled paper. Mission control adds Flight deck. Day dial's and Mission control's Hours shown, Mission control's deadline radar, Timeline's Week strip, Bento's Supporting tiles and Clay deck's Week cards are gone. Your other settings for those designs are kept.
- **Motion that shows where you went.** Pages fade from one to the next, Day, Week and Month slide a little toward the view you picked, Settings slides in over the week, and dialogs fade in and rise. Animations has four levels: Normal, More, Reduce (fades only, nothing slides) and Off. Paper starts at Reduce and every other look at Normal, until you choose.
- **The top bar's arrows come first.** ‹ › and Today sit before the title, so they stay put when the title changes width. The controls are icons, Add is one pill, and Plan my homework is accent words.
- **The focus screen** counts down in a ring and wears your look.
- **Sign in** is one centred card, with an eye in the password box to show the password.
- **Add homework and Edit event open inside the window,** and every dialog's fields line up. Settings is a centred column with an icon for each section.
- **Ctrl+K and the menus** have icons, groups and the keys beside what they do.

## Fixed
- In the homework editor, Enter saves. It pressed More details.
- Month's deadlines are quiet "Due" chips that turn red only once the date has passed without the homework being finished.
- Changing the look with the week open no longer runs the words of the Not placed yet chips off their edge.
- While a look of your own is worn, Settings shows the accent and Fine-tune choices it sets and says to change them in Customise…. They looked changeable and did nothing.
- A switch whose words take more than one line, as at Large text, shows every line.

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
