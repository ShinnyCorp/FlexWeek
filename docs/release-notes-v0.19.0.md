# FlexWeek 0.19.0 release notes

Paste-ready body for the v0.19.0 GitHub release. The download sections follow
`docs/github-release.md` and are copied from 0.18.5 unchanged.

```
Places homework around school and sports. Download, open a window, create an account.

**Already on 0.18.5?** You do not need to download anything. FlexWeek offers this update itself: press Update now when it asks, or open Settings (the gear) and choose Check for updates.

## What changed
- **School is in every week.** School and your Setup activities stand in every week, so next week has school and Plan keeps homework out of it.
- **Unfinished homework shows up.** Work from last week that you never ticked done appears in More > Unfinished, and after Plan you can plan it or mark it done.
- **Plan leaves room for next week.** Work due after this Sunday gets its fair share of this week, and Plan's details say how much waits.
- **Past times are refused, and Undo stays.** Choosing a time that has already passed says "That's in the past." Plan's Undo stays up until you use it.
- **Text size is yours.** It stays the same when you change look, and High contrast no longer switches it.
- **Easier with a keyboard and a screen reader.** Segmented choices move with the arrow keys, and account errors sit beside their fields.
- **Fixed:** data that was lost or saved wrongly (quitting now saves first, focus minutes kept during a save, settings sent again after going offline, restore points and re-imported homework); the Linux download opens on desktops without the X11 keyboard libraries; a missing library or part shows one plain message.

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
