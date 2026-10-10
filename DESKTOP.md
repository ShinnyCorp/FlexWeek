# FlexWeek desktop

## What FlexWeek is (current, 2026-09-19)

One Python application. PySide6 **Qt widgets** draw the window; the FastAPI
backend runs in the same process on a loopback port and owns accounts, the week
and the database. There is no Chromium, no `QWebEngineView`, and since
2026-09-19 no browser client at all: `frontend/` was deleted and `backend/app.py`
answers the API and 404s everything else.

Run from a checkout: `python -m desktop.main` (`python -m desktop.native` is the
same entry).

**Builds.** Nuitka standalone, driven directly rather than through
`pyside6-deploy`, which rewrites its own spec on every run.

| | Linux | Windows |
| --- | --- | --- |
| Script | `desktop/build_linux.sh` | `desktop/build_windows.ps1` |
| Output | `dist/FlexWeek/FlexWeek` | `dist\FlexWeek-Windows\FlexWeek.exe` |
| Installer | `packaging/make-appimage.sh` | `packaging/windows/flexweek.iss` (Inno), `flexweek.wxs` (WiX) |

Both exclude `PySide6.QtWebEngineCore`, `QtWebEngineWidgets` and
`QtWebEngineQuick`, and both ship the Qt plugins the app actually needs:
`multimedia` (alarms are synthesised PCM through `QAudioSink`; without this
plugin the app starts, shows the alarm and makes no sound), plus
`networkinformation`, `platforminputcontexts`, `position`, `qmllint`,
`qmltooling` and `vectorimageformats`. `--onefile` is not used, because Qt
plugins ship as a folder.

Icons come from `desktop/assets/logo.png`. The SQLite database lives under the
user data directory, never inside the read-only bundle.

**What is still true below.** Section 6 (the Linux build), section 7 (the
bundled server), section 9 and the sections after it (the Windows build and installers, releasing the Linux build,
reminders, and window/tray/quit behaviour). Read those.

**What is superseded.** Sections 1 to 5 recommended a `QWebEngineView` window
pointed at a hosted origin. That decision was reversed on 2026-09-17 in favour
of native widgets, and the browser client it assumed was retired on 2026-09-19.
They are kept because they record why the choice was made and what the evidence
was at the time. Do not build from them. The first section 8 ("Desktop completion
checks") is a WebEngine-era record as well: the WebEngine wrapper's defects and
API references. Section 6 describes the current Linux build, which is about
250 MB with no Chromium in it.

---

Date: 2026-09-07. Sources are official docs (links dated below). This is a
packaging choice, not a UI redesign or security audit.

As of 0.12.0 the shipped window is native Qt widgets (`python -m desktop.main`).
The Chromium shell and its probe tests are gone. The sections below are the
2026-09-07 packaging recommendation that led to the first desktop builds.

## 1. Recommendation

> **Superseded 2026-09-17.** Reversed in favour of native Qt widgets with the
> backend in-process. Sections 1 to 5 are kept as the record of the original
> decision and its evidence. See the top of this file for what FlexWeek is now.

Use a **minimal PySide6 `QWebEngineView` window** that loads the hosted FlexWeek
origin. Do not embed a second FastAPI process in v1.

**Evidence**

- Qt for Python’s compatibility matrix marks Python **3.14** as supported on
  PySide **6.10.x–6.13.x** (wiki retrieved 2026-08-24):
  https://wiki.qt.io/Qt_for_Python
- Windows and Linux are listed platforms; 32-bit is not.
- `QWebEngineView.load` / `setUrl`, `loadFinished(ok)`, and `createWindow` are
  documented for this wrapper (Qt for Python docs, 2026-08-19):
  https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineWidgets/QWebEngineView.html
- Official deploy path is `pyside6-deploy` (Nuitka) on Windows/Linux/macOS
  (2026-08-19):
  https://doc.qt.io/qtforpython-6/deployment/
- Qt WebEngine **static builds are not supported** (Qt 6.11.2 platform notes):
  https://doc.qt.io/qt-6/qtwebengine-platform-notes.html
  That is a packaging constraint (ship a directory of Qt/Chromium libs), not a
  Python 3.14 blocker.

**pywebview** is the alternative: native WebView2 on Windows, GTK/Qt on Linux,
`pip install pywebview` / `pywebview[gtk|qt|pyside6]`.
https://pywebview.flowrl.com/guide/installation.html

It is not the first choice here: current `pyproject.toml` has
`requires-python >= 3.8` but classifiers only through **3.13**. That is not a
stated “3.14 fails” blocker, but it is not an official 3.14 claim either.
Default `private_mode=True` also discards cookies unless the wrapper opts out
(https://pywebview.flowrl.com/api/). Linux still needs GTK+WebKit or a Qt
WebEngine stack. No third option is required; PySide6 has no 3.14 hard blocker.

PySide6 is LGPLv3/GPLv2/commercial (same wiki). A GPL-3.0 app may link LGPLv3
Qt. WebEngine onedir builds are large because they include Chromium.

## 2. Smallest useful first release

- **Entrypoint:** `desktop/main.py` — `QApplication`, persistent
  `QWebEngineProfile`, one `QWebEngineView`, load `FLEXWEEK_DESKTOP_ORIGIN`
  (fallback `FLEXWEEK_ORIGIN`, then `http://127.0.0.1:8000`).
- **URL/env:** exact origin including port, matching the web app’s origin check.
- **Login persistence:** profile `setPersistentCookiesPolicy(AllowPersistentCookies)`
  and a writable `setPersistentStoragePath` under the user config dir. SameSite
  Strict cookies stay first-party if the view’s URL is that origin.
- **Connection errors:** `loadFinished(False)` shows a native Retry page (Reload
  the origin). Do not invent offline editing.
- **External links:** reimplement `createWindow` so `target=_blank` / popups
  open with `QDesktopServices.openUrl` instead of a second web view.
- **Artifacts:** `pyside6-deploy desktop/main.py` → Windows `.exe` + Qt/WebEngine
  libs; Linux `.bin` + the same libs. Prefer onedir, not `--onefile`. Qt’s
  PyInstaller page still warns Qt 6 plugin copy is partial and `--onefile` is
  not viable without extra steps
  (https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html).

## 3. One UI / session model, no extra bridge

The desktop window is a browser tab pointed at the hosted app. Leave
`HttpOnly` / `SameSite=Strict` cookies and CSRF origin/header checks unchanged.
Do not enable Qt WebChannel, do not inject Python `js_api`, and do not read
cookies from native code. The page already owns login, save, and solve.

## 4. Checklist and acceptance tests

1. Window opens the configured origin at 1280×800.
2. Register/login, refresh, still signed in (persistent profile).
3. Unplug / bad origin → Retry UI; after recovery, draft still in the page.
4. Link with `target=_blank` opens the OS browser, not a second Qt window.
5. Sign-out in the page clears the session; a new login is another account.
6. Windows onedir and Linux onedir both start without a local Python install.

Observable: cookie file appears under the profile path after login; killing and
reopening the app restores the session until the seven-day cookie expiry.

## 5. Unresolved product decisions

- Production origin URL (local vs hosted) and whether the desktop build may
  ever target localhost. *Settled: the backend runs in-process on loopback;
  `FLEXWEEK_DESKTOP_ORIGIN` remains for pointing at another deployment.*
- Windows WebEngine onedir size vs asking users to install WebView2 (that would
  be a pywebview revisit, not this slice). *Moot: no Chromium ships.*
- Code signing / SmartScreen: Windows README tells a student to use More info,
  then Run anyway. Linux ships a tar.gz (not AppImage) so the executable bit
  survives; `.desktop` + icon go in the archive.
- Whether a future slice bundles a local server; v1 should not. *Settled
  2026-09-07 the other way: section 7 bundles it, and it is how the app runs.*

---

<!-- End of the superseded WebEngine recommendation. Sections 6 onward are current. -->

## 6. Linux build (current as of 0.15)

First built on 2026-09-07 around Chromium; since 0.12 the window is native Qt
widgets and no Chromium is compiled in. The WebEngine build this section used
to describe, with its ~390 MB artifact and checklist, is in git history.

```bash
pip install -r requirements.txt -r requirements-desktop.txt
./desktop/build_linux.sh          # -> dist/FlexWeek/FlexWeek
./desktop/package_linux.sh        # -> dist/release/FlexWeek-Linux-x86_64.tar.gz
```

Pinned in `requirements-desktop.txt`: PySide6 6.11.2 (`cp310-abi3` wheels,
so the stable ABI covers Python 3.14), Nuitka 4.2.1 and patchelf 0.19.1. The
machine also needs a C compiler (GCC), Python 3.14's development headers,
`readelf` (binutils), `ldconfig`, and the six X11 helpers and two xkbcommon
libraries listed below installed, because the build copies them in.

**Files**

- `desktop/main.py` — `QApplication`, the bundled backend (section 7) unless
  `FLEXWEEK_DESKTOP_ORIGIN` is set, and the native window
  (`desktop/native/window.py`). One copy runs per user data folder; launching
  again brings it forward. `--smoke-test` is described under "Releasing the
  Linux build".
- `desktop/build_linux.sh` — Nuitka onedir. Leaves out the WebEngine modules,
  keeps the Qt plugins listed at the top of this file, and drops
  `egldeviceintegrations` and `printsupport`.
- `desktop/finish_linux_bundle.sh` — trims Qt's `.qm` translations, copies
  `libxcb-cursor.so.0`, `libxcb-icccm.so.4`, `libxcb-image.so.0`,
  `libxcb-keysyms.so.1`, `libxcb-render-util.so.0` and `libxcb-util.so.1` into
  the bundle with their licences (Qt's X11 plugin needs them, and Ubuntu and Mint
  do not install them), and `libxkbcommon.so.0` and `libxkbcommon-x11.so.0`
  (Qt's X11 plugin needs both; the release workflow installs the Ubuntu 24.04
  packages, 1.6.0-1build1 when this was written, and its licence is the upstream
  LICENSE file of that release), then runs the check below.
- `desktop/check_bundle.py` — fails the bundle when a binary needs a glibc newer
  than 2.38, or a library that is neither inside it nor in `LINUX_SYSTEM_LIBS`,
  the libraries a desktop Linux already has. Two plugins Qt skips when their
  libraries are missing (the GTK file dialogs and GLib's network status) are
  exempt.
- `desktop/package_linux.sh` makes the tarball and `packaging/make-appimage.sh`
  the AppImage. `desktop/smoke_linux_containers.sh` starts the tarball in stock
  Ubuntu 24.04 and Debian 13 containers.

**What the bundle takes from the system.** The README's "Linux libraries" table,
for students, lists it. It was read on 2026-09-25 from a 0.14 bundle with
`readelf -d` on every file: each `NEEDED` library the bundle does not carry. That
is `libEGL.so.1` and `libGL.so.1`; `libfontconfig.so.1` and `libfreetype.so.6`; `libX11`,
`libX11-xcb` and `libxcb` with its `glx`, `randr`, `render`, `shape`, `shm`,
`sync`, `xfixes` and `xkb` parts; `libwayland-client`, `-cursor` and `-egl`;
`libglib-2.0`, `libgthread-2.0` and `libdbus-1`; `libgssapi_krb5` and
`libbrotlidec` for Qt's network module; `libpulse`, `libbz2`, `libdrm`, `libXext`
and `libXrandr` for sound; and glibc, `libstdc++` and `libgcc_s`. PySide6's own
ICU, FFmpeg, OpenSSL and zstd are inside.

**Where to build a release.** On Ubuntu 24.04, the release workflow's `linux`
job. A newer host fails the glibc check on purpose: this Fedora workstation's
Python needs glibc 2.42 (`GLIBC_ABI_GNU2_TLS`).

**Size.** A 0.14 bundle is 252 MB unpacked, and its largest file is the 48 MB
`FlexWeek` launcher. The AppImage of it is 92 MB.

---

## 7. Bundled server — scope change 2026-09-07

**This supersedes section 1's "Do not embed a second FastAPI process in v1" and
settles the last open question in section 5.** The owner asked for an executable
that does not depend on a server being up. Section 1's reasoning still holds for
a *second* process; what ships instead is the same FastAPI app running in a
background thread of the one desktop process.

How it works:

- `desktop/server.py` binds a loopback socket on an ephemeral port **before**
  the app is built, because the backend pins its CSRF origin check and
  `TrustedHostMiddleware` to one exact origin — the port has to be known first.
  uvicorn is then handed the already-bound socket, so there is no
  pick-a-port-and-hope race.
- uvicorn runs with `loop="asyncio"` and `http="h11"`: uvloop and httptools are
  optional native extras and there is no reason to depend on them surviving
  being frozen.
- The SQLite database lives under the user data directory, never inside the
  read-only application bundle.
- No web assets ship in the bundle. The web client was retired in September 2026
  and `backend/app.py` serves an API only.
- The window closing stops the server via `aboutToQuit`.

Setting `FLEXWEEK_DESKTOP_ORIGIN` (or `FLEXWEEK_ORIGIN`) still points the window
at a hosted deployment and skips the bundled server entirely. An invalid value
is an error rather than a silent fall back to local, so a typo in a hosted
deployment cannot quietly start serving a different, empty database.

Security posture is unchanged: same origin checks, same CSRF header, same
cookies. The listener is bound to `127.0.0.1`, so it is not reachable from the
network.

## 8. Desktop completion checks — 2026-09-07

The account flow is now exercised automatically by `desktop/tests/test_native.py`
and `desktop/tests/test_smoke.py` against a real local API, using temporary
databases and offscreen widgets. PySide6 is optional for the backend test
environment; these tests skip explicitly when desktop dependencies are absent.

Two wrapper defects were reproduced and fixed: new-window links retained hidden
pages after handoff, and requested downloads had no native handler. New windows
now use Qt's `newWindowRequested` signal without creating another page; only
HTTP(S) destinations are handed to the system browser. Draft downloads use a
native Save dialog and cancel when no destination is selected.

Qt API references:
- https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEnginePage.html#PySide6.QtWebEngineCore.QWebEnginePage.newWindowRequested
- https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEngineDownloadRequest.html

The Linux build now compiles in a unique staging directory, excludes application
test packages, and preserves the previous successful artifact under a dated
`.previous.*` path before publishing a new one. `FLEXWEEK_BUILD_OUTPUT` can select
a different destination and `FLEXWEEK_BUILD_JOBS` defaults to four compiler jobs.
Build intermediates remain available for diagnosis; existing build folders are
not deleted.

## 9. Windows build preparation — 2026-09-07

GLM-5.3 Flash drafted `desktop/build_windows.ps1` and made `patchelf` a Linux-only
requirement. The main agent reviewed the draft and tightened staging, compiler
selection, environment restoration and publication checks. The script uses Python 3.14, Nuitka and PySide6 to create a standalone
Windows directory with the backend and the native window included. It stages builds and
refuses to overwrite `dist/FlexWeek-Windows`.

From a Windows PowerShell prompt in the repository:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-desktop.txt
.\desktop\build_windows.ps1
.\dist\FlexWeek-Windows\FlexWeek.exe
```

A compatible Visual Studio C++ build toolchain is required. No Windows host or
PowerShell interpreter was available in this session, so neither a Windows
executable nor PowerShell execution has been verified. The remaining Windows
check is build → open → register → save → restart → sign out on a machine
without the development virtualenv.

The default self-contained desktop mode stores accounts locally. Hosted mode
(`FLEXWEEK_DESKTOP_ORIGIN`) points the desktop app at another deployment's
accounts and weeks. There is no automatic local-to-hosted synchronization, and
since 2026-09-19 no browser client on either side.

### Windows release build — CI, same method as Daily Scheduler (2026-09-09)

Nuitka cannot cross-compile: the Windows package is built on a GitHub Actions
`windows-latest` runner, mirroring Local-Schedule-Assistant's
`release-windows.yml`. `.github/workflows/release-windows.yml` fires when a
release is published (or by hand against an existing tag), installs both
requirements files into a fresh Python 3.14, runs `desktop/build_windows.ps1`
(MSVC is preinstalled on the runner), smoke-checks the freeze layout
(`FlexWeek.exe`), copies
`README.txt`, `LICENSE.txt` and `flexweek.png` into the folder, and uploads the
installers to the release (see "Windows installers" below). ICU (`icuuc.dll` / `icuin.dll`) is treated as a Windows 10 1809+
system library and is not copied out of System32. The paste-ready release
text is `docs/github-release.md`.

### Windows installers (0.9.2)

0.9.0 and 0.9.1 shipped a zip with a `FlexWeek.lnk` at the top. The workflow made
that shortcut with a relative path, and Windows stored it as
`C:\dist\zip-stage\FlexWeek\app\FlexWeek.exe` on the build machine, so the
shortcut opened nothing on anyone else's PC. The zip is gone; the release ships
two installers built from the same `dist\FlexWeek-Windows` folder:

- `FlexWeek-Windows-x64-Setup.exe` from `packaging/windows/flexweek.iss`
  (Inno Setup 7.1.0, downloaded from its GitHub release and checked against
  the SHA-256 listed there). It installs for the current account in
  `%LOCALAPPDATA%\Programs\FlexWeek` without an administrator, adds a Start
  menu shortcut (desktop shortcut optional) and an uninstaller. The setup
  dialog can still switch to every account.
- `FlexWeek-Windows-x64.msi` from `packaging/windows/flexweek.wxs` (WiX 6.0.2;
  v7 blocks every command until its EULA is accepted). It installs for every
  account in Program Files with an administrator, for school and IT tools.

Shortcuts use installer constants (`{app}`, `[INSTALLFOLDER]`) resolved on the
user's PC. Never change the Inno `AppId` or the MSI `UpgradeCode`; upgrades find
the installed copy by them. The version comes from the `vX.Y.Z` release tag.

Before attaching anything, the workflow silently installs each installer on the
runner, checks that the Start menu shortcut opens the installed `FlexWeek.exe`
from its folder, runs `--smoke-test` through that shortcut's target, then
uninstalls and checks the app is gone. Pull requests that touch packaging run
the same build and tests without uploading, and keep the installers as run
artifacts for seven days.

---

## 8. Releasing the Linux build

The built app is **not** committed. `dist/` is gitignored, and it has to stay
that way: the bundle is about 250 MB, so a plain `git add dist/` would grow
`.git` by that much, permanently, and every judge cloning the repo would pay for
it. (While it held Chromium, `libQt6WebEngineCore.so.6` alone was over GitHub's
100 MB per-file limit.)

Distribute it as a release asset instead. GitHub Releases allow 2 GB per file.

```bash
./desktop/build_linux.sh                       # -> dist/FlexWeek/
./desktop/package_linux.sh                  # -> dist/release/FlexWeek-Linux-x86_64.tar.gz
```

This machine's Fedora Python needs glibc 2.42 (`GLIBC_ABI_GNU2_TLS`). A
release Linux build has to be made on Ubuntu 24.04 (the GitHub Actions
`linux` job), not on this host. `desktop/check_bundle.py` fails the Fedora
bundle on purpose.

The archive holds one `FlexWeek/` folder with the app, `README.txt`,
`flexweek.png`, `flexweek.desktop`, `install-menu-entry.sh` and `LICENSE.txt`.
`finish_linux_bundle.sh` copies `libxcb-cursor` and the five other X11 helpers,
and the two xkbcommon libraries, into the bundle, drops unused Qt `.qm` files,
and fails the build if anything needs a newer glibc than 2.38 or a library a
desktop does not have (section 6). A tar.gz keeps the executable bit that a zip
would lose. Attach the tarball and its `.sha256` to a GitHub Release
using the body in `docs/github-release.md`. The README's "Download for Linux"
link expects this exact filename.

About 250 MB on disk (section 6). Users extract it and run
`FlexWeek/FlexWeek`, with no Python and no separate server.

Verify a release candidate by extracting it somewhere clean and starting it with
an empty profile, rather than trusting the tree it was built from:

```bash
tar -xzf FlexWeek-Linux-x86_64.tar.gz -C /tmp/check
XDG_DATA_HOME=/tmp/check-profile /tmp/check/FlexWeek/FlexWeek
```

Or `FlexWeek --smoke-test report.json`. It creates a throwaway account in a
temporary data folder (removed afterwards, never the real profile), walks the
first-week setup to "Add to my week and plan", and exits 0 only when the planned
week is on screen: the window grab must show at least 200 colors on an 8 px
grid. A dead or blank page is one flat color, which is how 0.9.0 failed for
testers after that button. With `FLEXWEEK_DESKTOP_ORIGIN` set it stops at the
Create account screen instead of making accounts on that server.
`desktop/smoke_linux_containers.sh` runs it inside stock Ubuntu 24.04 and
Debian 13 containers; the release workflow runs it on the Linux tarball, the raw
Linux onedir and the Windows build.

**Housekeeping.** `build_linux.sh` preserves each previous build as
`dist/FlexWeek.previous.<timestamp>` and never prunes them, so `dist/` grows by
about 250 MB per rebuild. Delete the ones you do not need.

## Reminders (Phase 5)

As of 0.15, reminders are on unless the student turns them off in
Settings > Alerts, and accounts from before 0.15 had them turned on once. A
reminder comes a set number of minutes before each block starts, and at once for
a block saved inside that time. It shows in the tray, for a moment under the top
bar, and on the status line. A block with its own Spotify link plays it when the
block starts, stopped and snoozed as an alarm is. `desktop/native/remind.py`
decides when; the window presents it.

## Window, tray and quitting (2026-09-10)

- Launching FlexWeek shows its window. If it is already running, the existing
  window comes forward instead (see the last point).
- When the desktop has a system tray, FlexWeek puts its logo there. Closing the
  window hides it to the tray, so reminders and alarms keep firing. The first
  close shows a tray message that says so.
- Click the tray icon, or choose **Show FlexWeek** from its menu, to bring the
  window back. Choose **Quit** from the tray menu to stop FlexWeek.
- Settings > Alerts > "Keep running when I close the window" turns this off;
  closing the window then quits.
- Without a tray, or when the tray icon cannot load, closing the window quits.
  FlexWeek never keeps running with no window and no tray icon.
- Launching FlexWeek again while it runs brings the existing window forward
  instead of starting a second copy on the same database. One copy runs per
  user data directory.

The tray icon is loaded from `desktop/assets/logo.png` next to the bundled backend.
Before this fix the path was taken from `desktop/main.py`. Nuitka places that file
at the bundle root, so the path pointed one directory above the bundle. Qt logged
`QSystemTrayIcon::setVisible: No Icon set`, the tray entry was invisible, and a
closed window left the process running with no visible way back.
