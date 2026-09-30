# FlexWeek

Places homework around school and sports, then explains why something moved.

Congressional App Challenge 2026. No chatbot. No product demo mode.

![FlexWeek's week view after Solve: school, soccer practice and a piano lesson are fixed, and four homework and study tasks are placed around them](docs/images/week-light.png)

## Download

From the [latest GitHub Release](https://github.com/j0nsh1n/FlexWeek/releases/latest):

- **Download for Windows.** `FlexWeek-Windows-x64-Setup.exe`
- **Download for Linux.** `FlexWeek-Linux-x86_64.tar.gz`

Checksum files (`.sha256`) sit next to those downloads if you want to confirm the file is complete. You can ignore them and still open FlexWeek.

**Windows.** Run `FlexWeek-Windows-x64-Setup.exe`. It installs FlexWeek for your Windows account without an administrator, then open FlexWeek from the Start menu. If Windows shows "Windows protected your PC", choose More info, then Run anyway. FlexWeek is not code-signed yet; the warning is SmartScreen not recognizing a new publisher, not a virus finding. Schools and IT can deploy `FlexWeek-Windows-x64.msi` instead, which installs for every account on the PC. Uninstall from Settings, then Apps.

**Linux.** Extract the archive and open the file named FlexWeek. You need a 64-bit Linux desktop (GNOME, KDE Plasma, Cinnamon, Xfce), glibc 2.38 or newer (Ubuntu 24.04, Linux Mint 22, Debian 13, Fedora 39 or newer), and working graphics (OpenGL or EGL). A remote or headless session without a display will not work. The system libraries it uses are listed under [Linux libraries](#linux-libraries).

**Linux AppImage.** If `FlexWeek-x86_64.AppImage` won't start (missing FUSE), run `chmod +x FlexWeek-x86_64.AppImage && ./FlexWeek-x86_64.AppImage --appimage-extract`, which unpacks a `squashfs-root` folder, then run `./squashfs-root/AppRun`. Without FUSE, the tarball above is the reliable choice.

**Chromebooks.** Not supported. FlexWeek is a Windows and Linux desktop app; there is no web version.

Open FlexWeek. The first screen is Sign in; choose "New here? Create an account" under it, then follow setup a page at a time: a style, your week, how homework gets a time, reminders and the alarm sound, and your first homework. You can skip any page.

### Linux libraries

The Linux download carries Qt and Python inside it, including the X11 helpers many desktops leave out (`libxcb-cursor` and five others). It uses these libraries from your system, and a desktop install already has them:

| For | Libraries |
| --- | --- |
| Graphics | `libEGL.so.1`, `libGL.so.1` |
| Keyboard | `libxkbcommon.so.0`, and on X11 `libxkbcommon-x11.so.0` |
| Text | `libfontconfig.so.1`, `libfreetype.so.6` |
| X11 | `libX11.so.6`, `libX11-xcb.so.1`, and `libxcb.so.1` with its `randr`, `render`, `shape`, `shm`, `sync`, `xfixes` and `xkb` parts |
| Wayland | `libwayland-client.so.0`, `libwayland-cursor.so.0`, `libwayland-egl.so.1` |
| Desktop services | `libglib-2.0.so.0`, `libdbus-1.so.3` |
| Network | `libgssapi_krb5.so.2`, `libbrotlidec.so.1` |
| Sound, optional | `libpulse.so.0` from PulseAudio or PipeWire, and `libbz2.so.1`, `libdrm.so.2`, `libXext.so.6` and `libXrandr.so.2` for Qt's sound plugin. Without them, reminders and alarms still show, silently. |

If FlexWeek does not start, this lists any that are missing:

```bash
find FlexWeek -name '*.so*' -exec ldd {} + 2>/dev/null | grep 'not found' | sort -u
```

On Debian or Ubuntu without a full desktop, such as a container or a minimal install, `sudo apt install libegl1 libgl1 libxkbcommon-x11-0 libdbus-1-3` adds the ones FlexWeek's own test machines lacked.

## Screenshots

| First-week setup | Dark theme |
| --- | --- |
| ![The first-week setup asks what homework is due first, how long it takes and when it is due](docs/images/setup.png) | ![The same solved week in the dark theme](docs/images/week-dark.png) |

## Run from source

Requires Python 3.14.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-desktop.txt
python -m desktop.main
```

On Linux, pip's PySide6 does not include the X11 helpers that the download carries, so a checkout also needs `libxcb-cursor.so.0`, `libxcb-icccm.so.4`, `libxcb-image.so.0`, `libxcb-keysyms.so.1`, `libxcb-render-util.so.0` and `libxcb-util.so.1`, besides the [Linux libraries](#linux-libraries) above. On Debian or Ubuntu: `sudo apt install libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-util1`.

Building the Linux download (`./desktop/build_linux.sh`) also needs a C compiler (GCC), Python 3.14's development headers, `patchelf` (installed by `requirements-desktop.txt`) and `readelf` (binutils). The six X11 helpers must be installed, because the build copies them into the bundle. A release is built on Ubuntu 24.04, so nothing in it needs a glibc newer than 2.38; [DESKTOP.md](DESKTOP.md) has the details.

The backend starts inside the app on a loopback port; there is no separate
server to run and no page to open in a browser. The first screen is Sign in,
with "New here? Create an account" under it. Usernames use 3–32 letters,
numbers or underscores; passwords use 12–128 characters. A new account opens
setup a page at a time: a style, the week (school, activities and a cutoff),
how homework gets a time, reminders and the alarm sound, and up to three first
homework. You can skip any page, and Settings can run it again.

To add more, press **Add** in the top bar for homework, or its arrow for a fixed
time or School hours, or drag on the calendar. A **Fixed time** (school,
practice) never moves when you plan; **Homework** is placed by Plan my homework
in a free time before it is due. The type you picked determines which you get. A
click opens anything on the calendar and a right-click offers Open, Duplicate,
Finished and Delete; homework, with all its times, is deleted from its editor,
its right-click menu or the Unfinished list, and Undo brings it back. Ctrl+K
finds any action or homework by typing. Every change saves to your account on
its own; planning previews placement without replacing what you entered.

The look starts on System, which follows your device's light or dark setting,
in Today's app with Day dial as the day screen. The gear opens Settings in
place of the week, where look and layout live together; Timeline is the other
standard design, and the rest are under Experimental styles. Every design can
be dark: Today's app through its look, the others through a dark colourway of
their own. Under Look there are ten looks, and **Customise…** opens the Look
editor, where any look's colours, categories, corners, type, blocks, grid and
motion can be changed, checked for readability and saved as your own. Animations
can be Normal, More, Reduce (fades only) or Off. The week saves itself a moment after each change and retries on
its own if a save fails. A save that conflicts with another window is never written over: saving
stops and FlexWeek asks you to reload the saved week. A forgotten password is recovered
with one of the eight recovery codes shown when the account was made.

Weeks exported from an older browser-based build can be explicitly imported
after logging in. Import replaces the account's current week after confirmation;
invalid legacy data is left untouched.

## Data and configuration

FlexWeek keeps its database in your user data folder (on Linux,
`~/.local/share/FlexWeek/flexweek.db`) and starts its own backend on a private
loopback port. Nothing needs configuring to use it.

| Setting | Effect |
|---|---|
| `--database FILE` | Use this database file instead of the one in your data folder |
| `FLEXWEEK_DESKTOP_ORIGIN` (or `FLEXWEEK_ORIGIN`) | Use a FlexWeek API running elsewhere instead of starting one; an invalid value is an error, never a quiet fall back to local |

The API can also run on its own, for development or as a server other copies
point at: `uvicorn backend.app:app` reads `FLEXWEEK_DATABASE` (default
`var/flexweek.db`) and `FLEXWEEK_ORIGIN` (default `http://127.0.0.1:8000`) and
serves the API only, no pages. Non-local origins require HTTPS, and HTTPS uses
Secure session cookies. A hosted API needs a persistent database directory and
backups, and trusted reverse proxies configured explicitly so client-address
throttling sees the real source.

The database and its journals are gitignored. Back up the database with SQLite's
backup API or with the app stopped; protect backups as private account data.

## Checks

The checks run through `fwtest`, a small Rust program in `tools/fwtest`. Build
it once, and again after it changes:

```bash
(cd tools/fwtest && cargo build --release)
tools/fwtest/target/release/fwtest gate
```

`fwtest gate` runs the backend and desktop source checks at low priority, one
suite at a time on the machine, and stops everything it started when it ends.
Where PySide6 is absent, use `fwtest gate --backend-only`; desktop is then
explicitly unverified. `fwtest mutate [SPEC]` checks that the tests catch
deliberate breaks, `fwtest rig ...` drives the app with a real pointer,
`fwtest run -- CMD` runs any other command the same way, and `fwtest clean`
stops what a killed run left behind. It uses `.venv/bin/python` unless you pass
`--python` or set `FWTEST_PYTHON`. The contract is
[docs/tooling/fwtest.md](docs/tooling/fwtest.md). See the
[coverage map and feature verification guide](docs/verification.md) for focused
checks and release limitations.

## Progress

Phases 3 and 4 are complete: accounts, saved weeks and Daily Scheduler themes
are verified in the native desktop app. See the [roadmap](roadmap.md) for
the separate desktop app, calendar interaction port, later design work and
contest delivery. Windows/Linux are desktop targets. Windows packages are
built on GitHub Actions when a release is published; a Windows machine still
needs a person to run the installer and click through SmartScreen.

A Linux desktop build exists: a native Qt window with the FastAPI backend
bundled inside it. It needs no separate server, no Python install and no
Chromium. Build it with `pip install -r requirements-desktop.txt` then
`./desktop/build_linux.sh`. Package the download with
`./desktop/package_linux.sh` to get `FlexWeek-Linux-x86_64.tar.gz` (and a
`.sha256`) containing README, icon, `.desktop` file and the app. Releases
attach that archive rather than committing `dist/`; see [DESKTOP.md](DESKTOP.md).
The paste-ready GitHub release text is in [docs/github-release.md](docs/github-release.md).
Set `FLEXWEEK_DESKTOP_ORIGIN` to point the window at a hosted deployment instead;
local and hosted accounts are separate, without automatic synchronization.

Windows packages are built on GitHub Actions when a release is published
(`desktop/build_windows.ps1`, then `packaging/windows/`) and attached as the
installers `FlexWeek-Windows-x64-Setup.exe` (Inno Setup, per account) and
`FlexWeek-Windows-x64.msi` (WiX, every account).
ICU (`icuuc`/`icuin`) is part of Windows 10 1809+; the bundle check requires
those imports to be satisfied without copying Microsoft's DLLs. The saved
theme names `nocturne` and `slate` come from Daily Scheduler (the GPL-3.0
`Local-Schedule-Assistant` project); the hybrid frost colors replaced its
palette in September 2026. AI assistance was used in development,
including Codex and GLM-5.3 Flash test contribution; the runtime uses no AI
service.

The original Sep 6 contest brief (working title Reslot) is in
[docs/cac-build-plan.md](docs/cac-build-plan.md). The living schedule is the
[roadmap](roadmap.md).

Submit by Sunday, October 25, 2026, 8:00 p.m. PDT.

License: GPL-3.0. Contributor listing is pending completion before submission.
