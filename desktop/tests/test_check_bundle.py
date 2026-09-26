from __future__ import annotations

import struct
from pathlib import Path

from desktop.check_bundle import asset_problems, linux_problems, parse_readelf, pe_imports, windows_problems

READELF_DYNAMIC = """
Dynamic section at offset 0x1d8 contains 30 entries:
  Tag        Type                         Name/Value
 0x0000000000000001 (NEEDED)             Shared library: [libQt6Core.so.6]
 0x0000000000000001 (NEEDED)             Shared library: [libxcb-cursor.so.0]
 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
 0x000000000000001d (RUNPATH)            Library runpath: [$ORIGIN]
"""
READELF_VERSIONS = """
Version needs section '.gnu.version_r' contains 2 entries:
 Addr: 0x0000000000002f40  Offset: 0x002f40  Link: 7 (.dynstr)
  000000: Version: 1  File: libc.so.6  Cnt: 3
  0x0010:   Name: GLIBC_2.14  Flags: none  Version: 4
  0x0020:   Name: GLIBC_2.38  Flags: none  Version: 3
  0x0030:   Name: GLIBC_2.2.5  Flags: none  Version: 2
  0x0038:   Name: GLIBC_ABI_DT_RELR  Flags: none  Version: 6
  000000: Version: 1  File: libstdc++.so.6  Cnt: 1
  0x0040:   Name: GLIBCXX_3.4.32  Flags: none  Version: 5
"""


def test_readelf_output_gives_sonames_and_the_newest_glibc() -> None:
    needed, glibc = parse_readelf(READELF_DYNAMIC, READELF_VERSIONS)
    assert needed == {"libQt6Core.so.6", "libxcb-cursor.so.0", "libc.so.6"}
    assert glibc == ((2, 38), "GLIBC_2.38")


def test_fedora_python_tls_marker_counts_as_glibc_2_42() -> None:
    versions = (
        "  0x0010:   Name: GLIBC_2.34  Flags: none\n  0x0020:   Name: GLIBC_ABI_GNU2_TLS  Flags: none\n"
    )
    assert parse_readelf("", versions)[1] == ((2, 42), "GLIBC_ABI_GNU2_TLS")
    unknown = parse_readelf("", "  0x0010:   Name: GLIBC_ABI_SOMETHING_NEW  Flags: none\n")[1]
    assert linux_problems({"libpython3.14.so.1.0": (set(), unknown)}, set(), (2, 38)) == [
        "libpython3.14.so.1.0 needs GLIBC_ABI_SOMETHING_NEW (a glibc this check does not know)",
    ]


def test_a_binary_without_glibc_versions_reports_none() -> None:
    assert parse_readelf("", "") == (set(), None)


def test_linux_bundle_fails_on_a_newer_glibc_and_an_unbundled_xcb_helper() -> None:
    binaries = {
        "libQt6XcbQpa.so.6": (
            {"libxcb-cursor.so.0", "libxcb.so.1", "libQt6Core.so.6"},
            ((2, 34), "GLIBC_2.34"),
        ),
        "libtinfo.so.6": ({"libc.so.6"}, ((2, 42), "GLIBC_2.42")),
        "libQt6Core.so.6": ({"libc.so.6"}, ((2, 34), "GLIBC_2.34")),
    }
    problems = linux_problems(binaries, {"libQt6Core.so.6", "libQt6XcbQpa.so.6", "libtinfo.so.6"}, (2, 38))
    assert problems == [
        "libQt6XcbQpa.so.6 needs libxcb-cursor.so.0, which is neither bundled nor a desktop system library",
        "libtinfo.so.6 needs GLIBC_2.42 (glibc 2.42)",
    ]


def test_vendoring_the_helper_and_optional_plugins_pass() -> None:
    binaries = {
        "libQt6XcbQpa.so.6": ({"libxcb-cursor.so.0", "libxcb.so.1"}, ((2, 34), "GLIBC_2.34")),
        "PySide6/qt-plugins/platformthemes/libqgtk3.so": ({"libgtk-3.so.0"}, ((2, 36), "GLIBC_ABI_DT_RELR")),
        "libQt6WebEngineCore.so.6": ({"libexpat.so.1", "libuuid.so.1", "libc.so.6"}, ((2, 34), "GLIBC_2.34")),
    }
    assert linux_problems(binaries, {"libxcb-cursor.so.0", "libQt6XcbQpa.so.6"}, (2, 38)) == []


def test_windows_bundle_needs_the_vc_runtime_but_not_system_icu() -> None:
    imports = ["KERNEL32.dll", "icuuc.dll", "MSVCP140.dll", "api-ms-win-crt-heap-l1-1-0.dll"]
    binaries = {"Qt6Core.dll": imports}
    assert windows_problems(binaries, {"qt6core.dll"}) == [
        "Qt6Core.dll imports msvcp140.dll, which is neither bundled nor part of Windows",
    ]
    assert windows_problems(binaries, {"qt6core.dll", "msvcp140.dll"}) == []


def test_windows_qt_and_pydantic_use_system_dlls() -> None:
    binaries = {
        "PySide6/qt-plugins/platforms/qwindows.dll": ["USER32.dll", "uiautomationcore.dll"],
        "PySide6/qt-plugins/platforms/qdirect2d.dll": ["uiautomationcore.dll"],
        "pydantic_core/_pydantic_core.pyd": ["KERNEL32.dll", "bcryptprimitives.dll"],
    }
    assert windows_problems(binaries, set()) == []


def minimal_pe(dll_names: list[str]) -> bytes:
    """A PE32+ image with one .idata section holding an import table."""
    section_rva, section_raw = 0x1000, 0x200
    descriptors = bytearray()
    strings = bytearray()
    strings_at = section_rva + 20 * (len(dll_names) + 1)
    for name in dll_names:
        descriptors += struct.pack("<IIIII", 0, 0, 0, strings_at + len(strings), 0)
        strings += name.encode("ascii") + b"\0"
    section = bytes(descriptors) + bytes(20) + bytes(strings)
    optional_size = 240
    header = bytearray(0x40)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 0x3C, 0x40)
    coff = b"PE\0\0" + struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, optional_size, 0x22)
    optional = bytearray(optional_size)
    struct.pack_into("<H", optional, 0, 0x20B)
    struct.pack_into("<II", optional, 112 + 8, section_rva, len(section))
    table = struct.pack(
        "<8sIIIIIIHHI", b".idata", len(section), section_rva, len(section), section_raw, 0, 0, 0, 0, 0
    )
    image = bytes(header) + coff + bytes(optional) + table
    return image + bytes(section_raw - len(image)) + section


def test_pe_import_table_is_read_from_the_file_bytes() -> None:
    assert pe_imports(minimal_pe(["KERNEL32.dll", "icuuc.dll", "Qt6Core.dll"])) == [
        "KERNEL32.dll",
        "icuuc.dll",
        "Qt6Core.dll",
    ]


def test_non_pe_files_have_no_imports() -> None:
    assert pe_imports(b"\x7fELF" + bytes(100)) == []
    assert pe_imports(b"") == []


def test_a_bundle_without_an_asset_fails_and_names_it(tmp_path: Path) -> None:
    assets = tmp_path / "source"
    (assets / "fonts").mkdir(parents=True)
    (assets / "logo.png").write_bytes(b"png")
    (assets / "fonts" / "Inter-Bold.ttf").write_bytes(b"ttf")
    bundle = tmp_path / "bundle"
    (bundle / "desktop" / "assets").mkdir(parents=True)
    (bundle / "desktop" / "assets" / "logo.png").write_bytes(b"png")
    assert asset_problems(assets, bundle) == [
        "desktop/assets/fonts/Inter-Bold.ttf is missing, so the app draws without it"
    ]
    (bundle / "desktop" / "assets" / "fonts").mkdir()
    (bundle / "desktop" / "assets" / "fonts" / "Inter-Bold.ttf").write_bytes(b"ttf")
    assert asset_problems(assets, bundle) == []
