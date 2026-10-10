from __future__ import annotations

import os
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_package_linux_ships_readme_icon_and_checksum(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    launcher = bundle / "FlexWeek"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    output = tmp_path / "release"
    env = {**os.environ, "FLEXWEEK_WEB_URL": "https://example.test/flexweek"}
    subprocess.run(
        ["bash", str(ROOT / "desktop/package_linux.sh"), str(bundle), str(output)],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    archive = output / "FlexWeek-Linux-x86_64.tar.gz"
    checksum = output / "FlexWeek-Linux-x86_64.tar.gz.sha256"
    assert archive.is_file()
    assert checksum.read_text(encoding="utf-8").split()[1] == "FlexWeek-Linux-x86_64.tar.gz"
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        assert "FlexWeek/FlexWeek" in names
        assert "FlexWeek/README.txt" in names
        assert "FlexWeek/flexweek.png" in names
        assert "FlexWeek/flexweek.desktop" in names
        assert "FlexWeek/install-menu-entry.sh" in names
        assert "FlexWeek/LICENSE.txt" in names
        readme = tar.extractfile("FlexWeek/README.txt")
        assert readme is not None
        text = readme.read().decode("utf-8")
        member = tar.getmember("FlexWeek/FlexWeek")
    assert "https://example.test/flexweek" in text
    assert "@WEB_VERSION@" not in text
    assert member.mode & 0o111


def test_appimage_checksum_names_only_the_file(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "FlexWeek").write_text("#!/bin/sh\n", encoding="utf-8")
    (bundle / "FlexWeek").chmod(0o755)
    # Stands in for appimagetool, which make-appimage.sh uses from PATH before downloading it.
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "appimagetool").write_text('#!/bin/sh\nprintf "appimage" > "$2"\n', encoding="utf-8")
    (tools / "appimagetool").chmod(0o755)
    output = tmp_path / "deep" / "release" / "FlexWeek-x86_64.AppImage"
    env = {**os.environ, "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}"}
    subprocess.run(
        ["bash", str(ROOT / "packaging/make-appimage.sh"), str(bundle), str(output)],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    checksum = output.with_name("FlexWeek-x86_64.AppImage.sha256")
    assert checksum.read_text(encoding="utf-8").split()[1] == "FlexWeek-x86_64.AppImage"
    assert "/" not in checksum.read_text(encoding="utf-8")
    subprocess.run(["sha256sum", "-c", checksum.name], cwd=output.parent, check=True, capture_output=True)


def _build_appdir(tmp_path: Path) -> Path:
    # A fake appimagetool that keeps the AppDir beside the output, so the test can run its AppRun.
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "FlexWeek").write_text('#!/bin/sh\ntouch "$(dirname "$0")/ran"\n', encoding="utf-8")
    (bundle / "FlexWeek").chmod(0o755)
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "appimagetool").write_text(
        '#!/bin/sh\ncp -a "$1" "$2.appdir" && printf "appimage" > "$2"\n', encoding="utf-8"
    )
    (tools / "appimagetool").chmod(0o755)
    output = tmp_path / "release" / "FlexWeek-x86_64.AppImage"
    env = {**os.environ, "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}"}
    subprocess.run(
        ["bash", str(ROOT / "packaging/make-appimage.sh"), str(bundle), str(output)],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return output.with_name("FlexWeek-x86_64.AppImage.appdir")


def _run_apprun(appdir: Path, ldconfig_output: str, library_path: str) -> subprocess.CompletedProcess[str]:
    # A fake ldconfig stands in for the system library cache, so a test can say libEGL is absent.
    fakes = appdir.parent / "fake-bin"
    fakes.mkdir(exist_ok=True)
    (fakes / "ldconfig").write_text(f"#!/bin/sh\nprintf '%s' '{ldconfig_output}'\n", encoding="utf-8")
    (fakes / "ldconfig").chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fakes}{os.pathsep}{os.environ['PATH']}",
        "LD_LIBRARY_PATH": library_path,
    }
    return subprocess.run([str(appdir / "AppRun")], env=env, capture_output=True, text=True)


def test_apprun_stops_with_one_message_when_libegl_is_missing(tmp_path: Path) -> None:
    appdir = _build_appdir(tmp_path)
    result = _run_apprun(appdir, ldconfig_output="", library_path="")
    assert result.returncode != 0
    assert "libEGL.so.1" in result.stderr
    assert "Linux libraries" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (appdir / "usr/lib/FlexWeek/ran").exists()


def test_apprun_starts_the_app_when_the_system_cache_has_libegl(tmp_path: Path) -> None:
    appdir = _build_appdir(tmp_path)
    result = _run_apprun(appdir, "\tlibEGL.so.1 (libc6,x86-64) => /lib64/libEGL.so.1\n", "")
    assert result.returncode == 0, result.stderr
    assert (appdir / "usr/lib/FlexWeek/ran").exists()


def test_apprun_accepts_libegl_found_on_library_path(tmp_path: Path) -> None:
    appdir = _build_appdir(tmp_path)
    libs = tmp_path / "libs"
    libs.mkdir()
    (libs / "libEGL.so.1").write_text("", encoding="utf-8")
    result = _run_apprun(appdir, ldconfig_output="", library_path=str(libs))
    assert result.returncode == 0, result.stderr
    assert (appdir / "usr/lib/FlexWeek/ran").exists()
