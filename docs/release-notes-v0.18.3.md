# FlexWeek 0.18.3 release notes

Paste-ready body for the v0.18.3 GitHub release. The download sections follow
`docs/github-release.md` and are copied from 0.18.2 unchanged.

```
Places homework around school and sports. Download, open a window, create an account.

**Already on 0.18.2?** You do not need to download anything. FlexWeek offers this update itself: press Update now when it asks, or open Settings (the gear) and choose Check for updates.

## What changed
- **Styles reach every page.** With Night owl, Dashboard or Retro as your view, Settings, the sheets, Setup and sign-in take its fonts, shapes and frames: Night owl's serif headings, Dashboard's title tile, Retro's pixel type, bevels and Windows 98 title bars. Plain calendar looks as before, and the week and day keep their own design.
- **One list of study hours.** Preferred study hours and planning hours are now one list, Study hours, set in Setup and in Availability. Hours saved the old way are carried over.
- **Availability at a glance.** The week as a strip, then Study hours, Protected and Cut-off as tabs, one row per day. Protected time can have a name, such as "Piano".
- **Setup, one style at a time.** The Style page shows one style large, with the others dimmed beside it, and every page lines up and fades under the footer.
- **Settings.** The look you wear is marked on its card, grids stretch to the row, controls line up, and the timer preset comes first on Focus.
- **Add homework.** Due starts tomorrow, Edit says where the homework is placed, and "Spread over days" splits longer homework when you save.
- **Sheets.** Choose a time picks a day and a length; "New event" is "Add fixed time" and guesses its kind from the time of day; Running late is greyed on another week.
- **Timeline's fold moves.** Drag the "‹ 3 | 4 ›" handle in the day names, or set "Days on the left page" in Settings.
- **Clay.** The neighbouring days are dimmed and stay still, and a sideways drag moves to the next day.
- **Focus screen.** The ring is your accent before Start, Skip and Finish sit beside Pause, and Finish asks before it ends the session.
- **Large text.** Homework names in the rail wrap onto two lines, and the top bar keeps the date clear of Day, Week and Month.
- **Sign-in.** A wrong password shows as a red line under the box, with a link explaining why. Manage account's password boxes can show what you type.

## Fixed
- The rail's focus list shows every row instead of a small scrolling box.
- At Large text the top bar could leave Plan on a second row.

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
