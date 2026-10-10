# FlexWeek 0.18.5 release notes

Paste-ready body for the v0.18.5 GitHub release. The download sections follow
`docs/github-release.md` and are copied from 0.18.4 unchanged.

```
Places homework around school and sports. Download, open a window, create an account.

**Already on 0.18.4?** You do not need to download anything. FlexWeek offers this update itself: press Update now when it asks, or open Settings (the gear) and choose Check for updates.

## What changed
- **Pick your clock.** Setup asks for a 12-hour or 24-hour clock. New accounts start on 12-hour; accounts you already have keep 24-hour.
- **Dates read better.** "Thu 1 Oct" and "Thursday 1 October", with the year only when it is not this year.
- **The Day dial explains itself.** Its arcs carry their names and a key sits above the list.
- **Heavy days are named.** After a plan, the list says when a day has more than 3 hours of homework.
- **Pictures for looks.** Start from in the look editor is a grid of look pictures, so you can see a look before you choose it.
- **A tidier sign-in.** One heading, hints under their fields, and the card stays in the same place on all three sign-in pages.
- **Fixed:** time boxes select the whole time on the first click and keep a typed time in every time zone; buttons no longer cut their words; Tab leaves the Notes box; screen readers name each field by its label.

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
