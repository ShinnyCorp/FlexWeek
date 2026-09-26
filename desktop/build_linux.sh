#!/usr/bin/env bash
# Build the FlexWeek Linux desktop shell (onedir standalone).
#
# Produces dist/FlexWeek/FlexWeek — runs without a Python install and without a
# separate server: the FastAPI backend is bundled and started in-process.
# The window is native Qt widgets; Chromium is not compiled
# in. --onefile is not used because Qt plugins ship as a folder (see DESKTOP.md).
#
# Nuitka is what pyside6-deploy shells out to. It is driven directly here
# because pyside6-deploy rewrites its own .spec with absolute paths on every
# run, which does not survive being committed to a repository.
#
# desktop/finish_linux_bundle.sh trims, vendors and checks the bundle before it
# is published. desktop/package_linux.sh turns it into the download.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV:-$ROOT/.venv}"
OUT="${FLEXWEEK_BUILD_OUTPUT:-$ROOT/dist/FlexWeek}"

# Nuitka looks for patchelf on PATH, not in site-packages.
export PATH="$VENV/bin:$PATH"
export PYTHONPATH="$ROOT"

command -v patchelf >/dev/null || { echo "patchelf not found; pip install -r requirements-desktop.txt" >&2; exit 1; }

mkdir -p "$ROOT/build"
STAGING="$(mktemp -d "$ROOT/build/linux.XXXXXX")"
trap 'echo "Build staging retained at $STAGING" >&2' ERR
# mypy and pydantic.mypy are type-checking tools; uvloop, httptools, watchfiles,
# websockets and yaml are uvicorn extras that desktop/server.py never enables;
# curses, readline and termios are terminal modules whose Fedora builds need a
# newer glibc than the release promises.
"$VENV/bin/python" -m nuitka "$ROOT/desktop/main.py" \
    --standalone \
    --follow-imports \
    --enable-plugin=pyside6 \
    --include-package=desktop.native \
    --include-package=backend \
    --include-data-dir="$ROOT/desktop/assets=desktop/assets" \
    --nofollow-import-to=desktop.tests,backend.tests \
    --nofollow-import-to=PySide6.QtWebEngineCore,PySide6.QtWebEngineWidgets,PySide6.QtWebEngineQuick \
    --nofollow-import-to=mypy,pydantic.mypy,uvloop,httptools,watchfiles,websockets,yaml \
    --nofollow-import-to=curses,readline,termios \
    --output-filename=FlexWeek \
    --output-dir="$STAGING" \
    --linux-icon="$ROOT/desktop/assets/logo.png" \
    --noinclude-dlls='*.cpp.o' \
    --noinclude-dlls='*.qsb' \
    --noinclude-dlls='libtinfo.so*' \
    --noinclude-dlls='libncursesw.so*' \
    --noinclude-dlls='libreadline.so*' \
    --include-qt-plugins=multimedia,networkinformation,platforminputcontexts,position,qmllint,qmltooling,vectorimageformats \
    --noinclude-qt-plugins=egldeviceintegrations,printsupport \
    --jobs="${FLEXWEEK_BUILD_JOBS:-4}"

BUNDLE="$STAGING/main.dist"
"$ROOT/desktop/finish_linux_bundle.sh" "$BUNDLE"

mkdir -p "$(dirname "$OUT")"
BACKUP=""
if [[ -e "$OUT" ]]; then
    BACKUP="$OUT.previous.$(date +%Y%m%d-%H%M%S)"
    [[ ! -e "$BACKUP" ]] || { echo "Backup already exists: $BACKUP" >&2; exit 1; }
    mv "$OUT" "$BACKUP"
fi
if ! mv "$BUNDLE" "$OUT"; then
    [[ -z "$BACKUP" ]] || mv "$BACKUP" "$OUT"
    exit 1
fi

echo "Built: $OUT/FlexWeek"
[[ -z "$BACKUP" ]] || echo "Previous build preserved: $BACKUP"
echo "Build intermediates retained: $STAGING"
du -sh "$OUT"
