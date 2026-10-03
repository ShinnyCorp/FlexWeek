# FlexWeek 0.18.1 release notes

Paste-ready body for the v0.18.1 GitHub release. The download sections follow
`docs/github-release.md` and are copied from 0.18.0 unchanged.

```
Places homework around school and sports. Download, open a window, create an account.

**Already on 0.18.0?** You do not need to download anything. FlexWeek offers this update itself: press Update now when it asks, or open Settings (the gear) and choose Check for updates.

## What changed
- **Times you can type.** Every time box takes typing like a text box: "1515", "15:15" and "3:15 pm" all mean 15:15, and typing replaces what you selected. An End of 00:00 now means the end of the day and reads 24:00.
- **"Due by" and "Do it at".** "At a set time" is now "Due by", and a deadline that has passed is refused. A new "When" choice lets FlexWeek pick the time or lets you say "Do it at" a day and time. Dragging homework on the hours does the same, and Plan works round it. Planned homework has a dashed edge, homework you placed a solid one.
- **The week from the keyboard.** Tab reaches the Week grid, the arrow keys move through it, Enter opens what is there and Shift+F10 opens its menu. After Plan or Undo the keyboard stays in the week.
- **Everything opens inside the window.** Availability, Manage account, the colour picker, Sign out and the app's other questions are sheets now, with one filled button and an outlined Cancel. A button you cannot press yet says why.
- **Overlaps are allowed everywhere.** Duplicate and paste no longer stop on an overlap; they warn and save, as a drag does.
- **Spotify when a block starts.** A block plays its own Spotify link, or your default link when the sound is Spotify.

## Fixed
- Undo after Plan no longer ends in "Not saved" with an empty week.
- Plan takes one click, and its notice is no longer cut off in a narrow window.
- Right-clicking free time opens its menu every time.
- New event and Choose a time no longer open on a time that has passed.
- Mission control opens with the time now in view late in the evening.
- The first and last hour in Week are always labelled.
- Settings slides in smoothly instead of stuttering.
- Manage account's fields no longer overlap, and Add homework no longer scrolls inside itself.
- Setup's first homework calendar draws its days.
- The reminder lead starts at 5 minutes everywhere, and "No homework after" offers the same times in Setup and Availability.

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
