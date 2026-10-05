# FlexWeek 0.18.2 release notes

Paste-ready body for the v0.18.2 GitHub release. The download sections follow
`docs/github-release.md` and are copied from 0.18.1 unchanged.

```
Places homework around school and sports. Download, open a window, create an account.

**Already on 0.18.1?** You do not need to download anything. FlexWeek offers this update itself: press Update now when it asks, or open Settings (the gear) and choose Check for updates.

## What changed
- **Blocks say what and when.** A short block shows its name, then its start, in every design. A time range stays on one line ("08:30–14:15"), the title is cut before the time, and lengths read "2h 15m". The line for now runs on under a block's words.
- **Plan says why.** A deadline that has passed says "That time has already passed.", homework due today with no study time left says so, and Plan that places nothing says "Nothing placed." Offline, Plan and Save say what is true and point to Retry save.
- **An empty week offers a start.** A card over the hours offers "Copy last week's fixed times" and "Use a routine"; the hours round it still take clicks and drags.
- **Narrow windows.** Below 1100 px, "Not placed yet" is a chip that opens the homework waiting for a time on a row under it, ready to drag onto the week. The top bar shortens in one order: the date, then More to its icon, then "Plan homework", then "Plan".
- **One menu.** A block's menu matches the free-time menu, has Copy, and its Delete asks whether to delete this time or the whole homework.
- **Keys.** F1 opens Help and Ctrl+N opens Add homework. Ctrl+K highlights the letters you type and lists Alerts, This computer and Choose a time.
- **Calmer screens.** Settings opens without a pause, Plan's review slides in over the week, Unfinished lists only homework that is late and folds into a one-line badge, and a running timer in Today's app is one line.
- **Designs.** "Planned" means placed homework time in every design. Mission control keeps a block's bar and icon down to 8 px wide.

## Fixed
- In Timeline, Mission control, Bento, Retro, Clay and One thing, homework blocks lost their edge and the hours stopped drawing after the first one.
- A block dropped on a day that has passed is refused with "That's in the past." and goes back, and a dragged block keeps its colour, name and icon.
- Going back a week after Copy last week's fixed times could stop the app.
- The sign-in card's message clears when you change page.
- A new sports row named after a sport (soccer, swim, tennis) starts as Sports; "Piano practice" stays Activity.
- Bento's now pill, Mission's midnight label and beside-names, Clay's Day card while it slides in, and 12-hour times at Large text in Clay and Retro are drawn right.

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
