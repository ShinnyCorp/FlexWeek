# FlexWeek 0.16.0 release notes

Paste-ready body for the v0.16.0 GitHub release. The download sections follow
`docs/github-release.md`. The builds now carry `desktop/assets` (the Inter typeface and the
icon), and the Windows installer takes its icon from `logo.ico`.

```
Places homework around school and sports. Download, open a window, create an account.

**Already on 0.15.x?** FlexWeek offers this update itself: open Settings (the gear) and choose Check for updates.

## What changed
- **One calm default.** A new account starts in Today's app with Day dial as its day screen, in Light, Dark or High contrast with an accent of your choice. Timeline is the other standard design. Mission control, Bento, Retro desktop, Clay deck and One thing, and the looks Nocturne, Slate, Poster, Terminal, Paper, Ink and Pastel, are under "Experimental styles". Whatever you chose before still opens.
- **Add comes first.** The top bar has Day, Week, Month and My day as one control, and Add as its one filled button: a click adds homework, and its arrow adds a fixed time or School hours. Plan my homework sits plainly beside it.
- **The week gets its room back.** Week has a side, as Day does, with what is next, the homework to start a focus timer on, and Not placed yet, so the hours reach the top of the window. Under 1150 pixels the side folds into one line. The window works down to 800 pixels wide.
- **One notice.** What a drag, a plan, Finished or Delete did shows in one toast over the foot of the hours, with Undo, and goes after a few seconds or when you change view. The status line is gone.
- **Delete homework.** Homework can be deleted from its editor, from its row under Unfinished, or from its right-click menu, including homework with no time yet. It asks first; its times go too, in every week, and one Undo brings everything back.
- **Click to open, right-click for more.** A click on a block opens it and a drag still moves it. A right-click offers Open, Duplicate, Finished and Delete.
- **School hours asks what setup asks:** the days, and from and to.
- **Settings is a page.** It fills the window in cards, with switches for on or off and side-by-side choices, and the designs are picked from pictures. Done or Esc goes back to the week.
- **FlexWeek brings its own typeface,** Inter, so it looks the same on every computer, with times in figures of one width. Cards and dialogs have more room.
- **Easier colours.** Activities are teal, not pink next to homework's coral. On a dark look blocks are deep colours with white words. The hours drop their dashed half-hour lines, the now line says the time, and today's column stands out.
- **Month opens on this week** as its first row.
- **A focus screen.** Start focus, Quick focus or F shows the timer large, with Pause, Skip and Finish. Esc goes back and the timer keeps running.
- **Ctrl+K** opens a command bar: type a few letters of an action or a homework's name and press Enter.
- **A 12-hour clock,** in Settings > This computer.
- **A new account's empty week** says "Nothing here yet." with one button, Add your first homework.
- **Motion that shows what changed.** Views crossfade, dialogs ease in, and after Plan the blocks slide to their places. Animations Off turns it all off.
- **Recovery codes** are in a fixed-width face, with Copy and Save.
- **Help** is two columns, and About has an Open folder button. FlexWeek has its own icon.

## Fixed
- A one-hour block shows its name and its times instead of one shortened line.
- Sign in said "Welcome back." on the very first launch. It says "Welcome."
- Add homework's Title started as the word "Homework", so typing gave "HomeworkMath worksheet". It starts empty.
- Finished, after a focus session on homework, finishes the homework.
- Setup's planning-hours buttons read as choices that never showed as chosen. They say "+ After school" and add a row of hours you can change.
- Setup's Play buttons line up with their sounds.
- The window's icon was missing from the downloads.

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
