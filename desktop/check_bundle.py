"""Check that a built desktop bundle runs on a fresh machine. No Qt imports.

    python -m desktop.check_bundle linux dist/FlexWeek --max-glibc 2.38
    python -m desktop.check_bundle windows dist/FlexWeek-Windows

A Linux bundle fails when any binary needs a newer glibc than the one the
release notes promise, or a library that is neither inside the bundle nor part
of a normal desktop install. A Windows bundle fails when a binary imports a DLL
that is neither inside the bundle nor part of Windows 10 1809 or later. Windows
system DLLs are checked for, never copied: Microsoft's own files are not ours
to redistribute. Either fails when a file in desktop/assets, the icon and the
fonts, is not in the bundle at the same place.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"

# Libraries every desktop Linux with a GUI session already has. The glibc and
# GCC runtime set, the X11 and Wayland client stack, GL/EGL from the graphics
# driver, fonts (FreeType pulls in Brotli), D-Bus, sound, NSS, Expat (WebEngine
# XML), and util-linux uuid.
LINUX_SYSTEM_LIBS = frozenset(
    {
        "ld-linux-x86-64.so.2",
        "libc.so.6",
        "libm.so.6",
        "libdl.so.2",
        "libpthread.so.0",
        "librt.so.1",
        "libresolv.so.2",
        "libutil.so.1",
        "libstdc++.so.6",
        "libgcc_s.so.1",
        "libz.so.1",
        "libGL.so.1",
        "libEGL.so.1",
        "libOpenGL.so.0",
        "libGLX.so.0",
        "libgbm.so.1",
        "libdrm.so.2",
        "libX11.so.6",
        "libX11-xcb.so.1",
        "libXext.so.6",
        "libXfixes.so.3",
        "libXrandr.so.2",
        "libXrender.so.1",
        "libXcomposite.so.1",
        "libXdamage.so.1",
        "libXtst.so.6",
        "libXi.so.6",
        "libxkbfile.so.1",
        "libxshmfence.so.1",
        "libxcb.so.1",
        "libxcb-glx.so.0",
        "libxcb-randr.so.0",
        "libxcb-render.so.0",
        "libxcb-shape.so.0",
        "libxcb-shm.so.0",
        "libxcb-sync.so.1",
        "libxcb-xfixes.so.0",
        "libxcb-xkb.so.1",
        "libxcb-xinerama.so.0",
        "libxcb-xinput.so.0",
        "libwayland-client.so.0",
        "libwayland-cursor.so.0",
        "libwayland-egl.so.1",
        "libfontconfig.so.1",
        "libfreetype.so.6",
        "libdbus-1.so.3",
        "libglib-2.0.so.0",
        "libgobject-2.0.so.0",
        "libgthread-2.0.so.0",
        "libasound.so.2",
        # QtMultimedia arrived with the alarm sounds and brought these two. libpulse is the peer of
        # libasound above: every desktop Linux runs PulseAudio or PipeWire's pulse shim. libbz2 comes
        # in under FFmpeg, and is base on every distribution that ships a desktop. If either is
        # somehow absent the QtMultimedia import fails, desktop/native/sound.py catches it, and the
        # alarm shows its dialog without a sound rather than the app failing to start.
        "libpulse.so.0",
        "libbz2.so.1",
        "libnss3.so",
        "libnssutil3.so",
        "libsmime3.so",
        "libnspr4.so",
        "libplc4.so",
        "libplds4.so",
        "libudev.so.1",
        "libgssapi_krb5.so.2",
        "libxcb-dri3.so.0",
        "libxcb-present.so.0",
        "libbrotlidec.so.1",
        "libbrotlicommon.so.1",
        "libexpat.so.1",
        "libuuid.so.1",
    }
)

# DLLs that are part of Windows 10 1809 and later. icuuc/icuin have been system
# DLLs since 1703, so Qt6Core's import of icuuc.dll is satisfied by Windows.
# avrt, dxva2, evr and the mf* trio arrived with QtMultimedia for the alarm sounds. All are Windows
# components in System32. Media Foundation (mf*) is absent on "N" editions until the Media Feature
# Pack is installed; there the media plugins fail to load, sound.py catches it, and the alarm shows
# its dialog without a sound. avrt, which is what QAudioSink itself needs, is present everywhere.
WINDOWS_SYSTEM_DLLS = frozenset(
    {
        "advapi32.dll",
        "authz.dll",
        "avrt.dll",
        "bcrypt.dll",
        "bcryptprimitives.dll",
        "bthprops.cpl",
        "cfgmgr32.dll",
        "comctl32.dll",
        "comdlg32.dll",
        "crypt32.dll",
        "d3d9.dll",
        "d3d11.dll",
        "d3d12.dll",
        "dbghelp.dll",
        "dcomp.dll",
        "dhcpcsvc.dll",
        "dnsapi.dll",
        "dwmapi.dll",
        "dwrite.dll",
        "dxgi.dll",
        "dxva2.dll",
        "evr.dll",
        "fontsub.dll",
        "gdi32.dll",
        "hid.dll",
        "icu.dll",
        "icuin.dll",
        "icuuc.dll",
        "imm32.dll",
        "iphlpapi.dll",
        "kernel32.dll",
        "mf.dll",
        "mfplat.dll",
        "mfreadwrite.dll",
        "mmdevapi.dll",
        "mpr.dll",
        "msimg32.dll",
        "ncrypt.dll",
        "netapi32.dll",
        "ntdll.dll",
        "ole32.dll",
        "oleacc.dll",
        "oleaut32.dll",
        "opengl32.dll",
        "pdh.dll",
        "powrprof.dll",
        "propsys.dll",
        "psapi.dll",
        "rpcrt4.dll",
        "secur32.dll",
        "setupapi.dll",
        "shcore.dll",
        "shell32.dll",
        "shlwapi.dll",
        "uiautomationcore.dll",
        "urlmon.dll",
        "user32.dll",
        "userenv.dll",
        "uxtheme.dll",
        "version.dll",
        "winhttp.dll",
        "winmm.dll",
        "winspool.drv",
        "winusb.dll",
        "wintrust.dll",
        "wldap32.dll",
        "ws2_32.dll",
        "wtsapi32.dll",
        "d2d1.dll",
        "windowscodecs.dll",
        "normaliz.dll",
        "credui.dll",
    }
)
WINDOWS_API_SET_PREFIXES = ("api-ms-win-", "ext-ms-win-")

# Qt loads these plugins only when their libraries exist and quietly skips them
# otherwise: GTK file dialogs outside GTK desktops, GLib network status.
OPTIONAL_LINUX_PLUGINS = frozenset(
    {
        "PySide6/qt-plugins/platformthemes/libqgtk3.so",
        "PySide6/qt-plugins/networkinformation/libqglib.so",
    }
)

NEEDED_LINE = re.compile(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]")
GLIBC_NAME = re.compile(r"\bName: (GLIBC_[A-Z0-9_.]+)")
NUMBERED_GLIBC = re.compile(r"GLIBC_(\d+)\.(\d+)(?:\.\d+)?")
# Marker versions that are not numbered but still need a minimum glibc. Distros
# built with newer toolchains add them, e.g. Fedora's Python needs GNU2_TLS.
GLIBC_ABI_MARKERS = {
    "GLIBC_ABI_DT_RELR": (2, 36),
    "GLIBC_ABI_GNU_TLS": (2, 42),
    "GLIBC_ABI_GNU2_TLS": (2, 42),
    "GLIBC_ABI_DT_X86_64_PLT": (2, 42),
}
UNKNOWN_GLIBC = (99, 99)


def version_tuple(text: str) -> tuple[int, int]:
    major, minor = text.split(".")
    return int(major), int(minor)


GlibcNeed = tuple[tuple[int, int], str]


def glibc_need(name: str) -> tuple[int, int] | None:
    """The glibc release a symbol version needs; unknown ABI markers never pass."""
    if name.startswith("GLIBC_ABI_"):
        return GLIBC_ABI_MARKERS.get(name, UNKNOWN_GLIBC)
    match = NUMBERED_GLIBC.fullmatch(name)
    return (int(match.group(1)), int(match.group(2))) if match else None


def parse_readelf(dynamic: str, versions: str) -> tuple[set[str], GlibcNeed | None]:
    """NEEDED sonames and the most demanding glibc symbol version, from `readelf -d` and `-V`."""
    needed = set(NEEDED_LINE.findall(dynamic))
    found = [(need, name) for name in GLIBC_NAME.findall(versions) if (need := glibc_need(name))]
    return needed, max(found) if found else None


def linux_problems(
    binaries: dict[str, tuple[set[str], GlibcNeed | None]],
    bundled: set[str],
    max_glibc: tuple[int, int],
) -> list[str]:
    problems = []
    for name, (needed, glibc) in sorted(binaries.items()):
        if glibc is not None and glibc[0] > max_glibc:
            (major, minor), symbol = glibc
            if glibc[0] == UNKNOWN_GLIBC:
                release = "a glibc this check does not know"
            else:
                release = f"glibc {major}.{minor}"
            problems.append(f"{name} needs {symbol} ({release})")
        if name in OPTIONAL_LINUX_PLUGINS:
            continue
        for soname in sorted(needed - bundled - LINUX_SYSTEM_LIBS):
            problems.append(f"{name} needs {soname}, which is neither bundled nor a desktop system library")
    return problems


def windows_problems(binaries: dict[str, list[str]], bundled: set[str]) -> list[str]:
    problems = []
    for name, imports in sorted(binaries.items()):
        for dll in sorted({item.lower() for item in imports}):
            if dll in bundled or dll in WINDOWS_SYSTEM_DLLS or dll.startswith(WINDOWS_API_SET_PREFIXES):
                continue
            problems.append(f"{name} imports {dll}, which is neither bundled nor part of Windows")
    return problems


def pe_imports(data: bytes) -> list[str]:
    """DLL names in a PE file's import table. Empty for anything that is not a PE image."""

    def u16(at: int) -> int:
        return int.from_bytes(data[at : at + 2], "little")

    def u32(at: int) -> int:
        return int.from_bytes(data[at : at + 4], "little")

    if data[:2] != b"MZ" or len(data) < 0x40:
        return []
    header = u32(0x3C)
    if data[header : header + 4] != b"PE\0\0":
        return []
    coff = header + 4
    section_count = u16(coff + 2)
    optional = coff + 20
    optional_size = u16(coff + 16)
    directories = optional + (112 if u16(optional) == 0x20B else 96)
    import_rva = u32(directories + 8)
    sections = optional + optional_size

    def file_offset(rva: int) -> int | None:
        for index in range(section_count):
            entry = sections + 40 * index
            virtual_size, virtual_address = u32(entry + 8), u32(entry + 12)
            raw_size, raw_pointer = u32(entry + 16), u32(entry + 20)
            if virtual_address <= rva < virtual_address + max(virtual_size, raw_size):
                return raw_pointer + rva - virtual_address
        return None

    names = []
    descriptor = file_offset(import_rva) if import_rva else None
    while descriptor is not None and data[descriptor : descriptor + 20] not in (b"", bytes(20)):
        name_at = file_offset(u32(descriptor + 12))
        if name_at is None:
            break
        names.append(data[name_at : data.index(b"\0", name_at)].decode("ascii"))
        descriptor += 20
    return names


def files(root: Path) -> Iterable[Path]:
    return (path for path in sorted(root.rglob("*")) if path.is_file() and not path.is_symlink())


def asset_problems(assets: Path, root: Path) -> list[str]:
    """Every file under `assets` must sit at desktop/assets in the bundle, where the app looks for it."""
    return [
        f"desktop/assets/{relative} is missing, so the app draws without it"
        for relative in (path.relative_to(assets).as_posix() for path in files(assets))
        if not (root / "desktop" / "assets" / relative).is_file()
    ]


def check_linux(root: Path, max_glibc: tuple[int, int]) -> list[str]:
    binaries = {}
    for path in files(root):
        with path.open("rb") as handle:
            if handle.read(4) != b"\x7fELF":
                continue
        dynamic, versions = (
            subprocess.run(["readelf", flag, "--wide", str(path)], capture_output=True, text=True).stdout
            for flag in ("-d", "-V")
        )
        binaries[str(path.relative_to(root))] = parse_readelf(dynamic, versions)
    bundled = {path.name for path in root.rglob("*")}
    return linux_problems(binaries, bundled, max_glibc) + asset_problems(ASSETS, root)


def check_windows(root: Path) -> list[str]:
    binaries = {
        str(path.relative_to(root)): pe_imports(path.read_bytes())
        for path in files(root)
        if path.suffix.lower() in {".dll", ".exe", ".pyd"}
    }
    bundled = {path.name.lower() for path in root.rglob("*")}
    return windows_problems(binaries, bundled) + asset_problems(ASSETS, root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("platform", choices=["linux", "windows"])
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--max-glibc", default="2.38", help="newest glibc the release notes promise")
    args = parser.parse_args(argv)
    if not args.bundle.is_dir():
        print(f"No bundle at {args.bundle}", file=sys.stderr)
        return 2
    if args.platform == "linux":
        problems = check_linux(args.bundle, version_tuple(args.max_glibc))
    else:
        problems = check_windows(args.bundle)
    for problem in problems:
        print(f"FAIL: {problem}")
    print(f"{len(problems)} problem(s) in {args.bundle}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
