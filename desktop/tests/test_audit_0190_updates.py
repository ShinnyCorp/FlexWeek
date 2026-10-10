"""Audit finding 11: a downloaded update does not stay on the disk once it has been used."""

from __future__ import annotations

import importlib.util
import os
import tarfile
import tempfile
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from desktop.native.updater import STALE_DOWNLOAD_S, apply_update, collect_stale_downloads


@pytest.fixture()
def temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "temp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


def a_download(temp: Path, name: str = "flexweek-update-abc123") -> Path:
    folder = temp / name
    folder.mkdir()
    package = folder / "FlexWeek.AppImage"
    package.write_bytes(b"new")
    return package


def test_an_appimage_update_that_took_leaves_no_download_behind(
    temp: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = tmp_path / "FlexWeek.AppImage"
    installed.write_bytes(b"old")
    monkeypatch.setenv("APPIMAGE", str(installed))
    package = a_download(temp)
    assert apply_update(str(package), "appimage") is None
    assert installed.read_bytes() == b"new"
    assert not package.parent.exists()


def test_an_update_that_could_not_be_put_in_place_leaves_no_download_behind(
    temp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APPIMAGE", raising=False)
    package = a_download(temp)
    assert apply_update(str(package), "appimage") is not None
    assert not package.parent.exists()


def test_a_tree_update_leaves_no_download_behind(
    temp: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "FlexWeek"
    root.mkdir()
    (root / "FlexWeek").write_text("old")
    build = tmp_path / "build" / "FlexWeek"
    build.mkdir(parents=True)
    (build / "FlexWeek").write_text("new")
    folder = temp / "flexweek-update-tree"
    folder.mkdir()
    archive = folder / "release.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(build, arcname="FlexWeek")
    monkeypatch.setattr("desktop.native.updater.bundle_root", lambda: root)
    assert apply_update(str(archive), "tree") is None
    assert (root / "FlexWeek").read_text() == "new"
    assert not folder.exists()


def test_a_file_the_updater_did_not_download_is_left_alone(
    temp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APPIMAGE", raising=False)
    package = a_download(temp, "mine")
    (package.parent / "notes.txt").write_text("keep")
    apply_update(str(package), "appimage")
    assert (package.parent / "notes.txt").exists()


def test_the_windows_installer_is_kept_while_it_runs(temp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtCore import QProcess

    monkeypatch.setattr(QProcess, "startDetached", staticmethod(lambda *_args: True))
    package = a_download(temp)
    assert apply_update(str(package), "windows") is None
    assert package.exists()


def test_downloads_left_by_an_earlier_run_are_collected_at_launch(temp: Path) -> None:
    old = a_download(temp, "flexweek-update-old").parent
    recent = a_download(temp, "flexweek-update-recent").parent
    other = temp / "something-else"
    other.mkdir()
    long_ago = time.time() - STALE_DOWNLOAD_S - 60
    os.utime(old, (long_ago, long_ago))
    os.utime(other, (long_ago, long_ago))
    collect_stale_downloads()
    assert not old.exists()
    assert recent.exists()
    assert other.exists()
