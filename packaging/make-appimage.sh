#!/usr/bin/env bash
# Wrap the Nuitka onedir tree into a type-2 AppImage.
#
# Usage:
#   packaging/make-appimage.sh <onedir-dir> [output.AppImage]
#
# The onedir dir must contain the FlexWeek binary and its qt6.conf (both come
# from desktop/build_linux.sh). Public release AppImages are built in CI on
# ubuntu-24.04, so the glibc demand matches the onedir tarball from the same
# job — an AppImage built on a newer distro would demand that distro's glibc.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ONEDIR="${1:-}"
OUT="${2:-}"

if [[ -z "$ONEDIR" || ! -d "$ONEDIR" ]]; then
  echo "usage: $0 <onedir-dir> [output.AppImage]" >&2
  exit 2
fi
ONEDIR="$(cd "$ONEDIR" && pwd)"

if [[ ! -x "$ONEDIR/FlexWeek" ]]; then
  echo "error: no executable FlexWeek in $ONEDIR" >&2
  ls -la "$ONEDIR" >&2 || true
  exit 2
fi

if [[ -z "$OUT" ]]; then
  OUT="$(dirname "$ONEDIR")/FlexWeek-x86_64.AppImage"
fi
mkdir -p "$(dirname "$OUT")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/fw-appimage.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

APPDIR="$WORK/AppDir"
mkdir -p "$APPDIR/usr/bin" \
         "$APPDIR/usr/lib/FlexWeek" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy the whole onedir next to a stable path; AppRun launches from there so
# Nuitka's relative bundle layout keeps working.
cp -a "$ONEDIR"/. "$APPDIR/usr/lib/FlexWeek/"
chmod +x "$APPDIR/usr/lib/FlexWeek/FlexWeek"

# Thin launcher on PATH for the desktop Exec= line.
cat > "$APPDIR/usr/bin/FlexWeek" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/../lib/FlexWeek/FlexWeek" "$@"
EOF
chmod +x "$APPDIR/usr/bin/FlexWeek"

# AppRun: entry point when the AppImage is executed. The bundled qt6.conf
# next to the binary already points Qt at the bundle's own plugins, so no
# QT_PLUGIN_PATH override is needed or wanted here.
# AppRun also checks for libEGL before the app starts. Without it the dynamic
# loader fails with a message that does not say what to install.
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"

# ldconfig lives in /sbin or /usr/sbin on some systems, which a PATH may leave out.
export PATH="$PATH:/usr/sbin:/sbin"
have_library() {
  # The cache listing is read whole; stopping early would end the pipe with SIGPIPE.
  case "$(ldconfig -p 2>/dev/null)" in
    *[[:space:]]"$1 ("*) return 0 ;;
  esac
  local dir
  while IFS= read -r dir; do
    [[ -n "$dir" && -e "$dir/$1" ]] && return 0
  done < <(printf '%s\n' "${LD_LIBRARY_PATH:-}" | tr ':' '\n')
  return 1
}

if ! have_library libEGL.so.1; then
  echo 'FlexWeek cannot start: the system library libEGL.so.1 is not installed. See the "Linux libraries" section of the README for what to install.' >&2
  exit 1
fi

exec "$HERE/usr/lib/FlexWeek/FlexWeek" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# Desktop entry + icon (appimagetool wants these at AppDir root too).
cp "$ROOT/packaging/flexweek.desktop" "$APPDIR/flexweek.desktop"
cp "$ROOT/packaging/flexweek.desktop" "$APPDIR/usr/share/applications/flexweek.desktop"
cp "$ROOT/desktop/assets/logo.png" "$APPDIR/flexweek.png"
cp "$ROOT/desktop/assets/logo.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/flexweek.png"
# Symlink without extension — some appimagetool versions look for this.
ln -sf flexweek.png "$APPDIR/.DirIcon"

# Fetch appimagetool (pinned) if not already on PATH.
TOOL=""
if command -v appimagetool >/dev/null 2>&1; then
  TOOL="$(command -v appimagetool)"
else
  TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.0/appimagetool-x86_64.AppImage"
  TOOL="$WORK/appimagetool"
  echo "Downloading appimagetool 1.9.0…"
  curl -fsSL "$TOOL_URL" -o "$TOOL"
  chmod +x "$TOOL"
fi

# CI runners often lack FUSE; extract-and-run avoids mounting the tool itself.
export APPIMAGE_EXTRACT_AND_RUN=1
export ARCH=x86_64

echo "Building AppImage → $OUT"
"$TOOL" "$APPDIR" "$OUT"

chmod +x "$OUT"
ls -lh "$OUT"
# Name only, like the tarball's checksum, so `sha256sum -c` works next to the download.
(cd "$(dirname "$OUT")" && sha256sum "$(basename "$OUT")") | tee "${OUT}.sha256"
echo "Built: $OUT"
