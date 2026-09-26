"""Packaged builds compile the native window and must not follow Chromium."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINUX = (ROOT / "desktop/build_linux.sh").read_text(encoding="utf-8")
WINDOWS = (ROOT / "desktop/build_windows.ps1").read_text(encoding="utf-8")
FINISH = (ROOT / "desktop/finish_linux_bundle.sh").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/release-windows.yml").read_text(encoding="utf-8")

GONE = (
    "desktop/webengine.py",
    "desktop/sandbox.py",
    "desktop/tests/webengine_probe.py",
    "desktop/tests/test_webengine.py",
    "desktop/tests/test_sandbox.py",
)


def test_retired_chromium_shell_is_gone() -> None:
    for relative in GONE:
        assert not (ROOT / relative).exists(), relative


def test_nuitka_does_not_compile_chromium() -> None:
    assert "--include-package=desktop \\" not in LINUX
    assert "'--include-package=desktop'" not in WINDOWS
    for text in (LINUX, WINDOWS):
        assert "include-package=desktop.native" in text
        assert "desktop.webengine" not in text
        assert "PySide6.QtWebEngineCore" in text
        assert "noinclude-module" not in text


def test_linux_trim_survives_a_bundle_with_no_chromium_locales() -> None:
    assert '[[ -d "$BUNDLE/qtwebengine_locales" ]]' in FINISH


def test_release_jobs_fail_if_chromium_lands_in_the_package() -> None:
    assert "Native package must not ship WebEngine" in WORKFLOW
    assert WORKFLOW.count("Native package must not ship WebEngine") == 2
    assert "WebEngine core DLL missing" not in WORKFLOW


def test_both_builds_ship_the_plugin_that_makes_an_alarm_audible() -> None:
    """QtMultimedia reaches the sound card through a Qt plugin. Trim it and the app still starts, the
    alarm still shows its dialog, and it rings silently, which is the one thing an alarm must not do."""
    for text in (LINUX, WINDOWS):
        assert "include-qt-plugins=multimedia," in text


def test_the_windows_build_takes_its_icon_from_the_ico_with_every_size() -> None:
    """Nuitka's --windows-icon-from-ico was handed the PNG. The .ico carries each size Windows asks
    for, drawn at that size by scripts/brand.py."""
    import struct

    assert "--windows-icon-from-ico=$(Join-Path $Root 'desktop\\assets\\logo.ico')" in WINDOWS
    data = (ROOT / "desktop/assets/logo.ico").read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert (reserved, kind) == (0, 1)
    sides = [data[6 + 16 * index] or 256 for index in range(count)]
    assert sides == [256, 128, 64, 48, 32, 16]
    assert (ROOT / "desktop/assets/logo.png").read_bytes()[16:24] == struct.pack(">II", 512, 512)
