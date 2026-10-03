"""Deciding whether to update, checked as data. No network, no Qt, no disk.

The bias throughout is that not updating is safe and updating wrongly is not, so every test that
asks "should this install?" is really asking whether the refusals hold.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from desktop.native.update import (
    LINUX_APPIMAGE,
    LINUX_TARBALL,
    WINDOWS_SETUP,
    available,
    expected_digest,
    install_kind,
    verified,
)
from desktop.native.version import VERSION, is_newer, parse


def asset(name: str) -> dict:
    return {"name": name, "browser_download_url": f"https://example.invalid/{name}"}


def release(tag: str = "v9.9.9", names: tuple[str, ...] | None = None, **fields: object) -> dict:
    if names is None:
        names = (WINDOWS_SETUP, WINDOWS_SETUP + ".sha256", LINUX_TARBALL, LINUX_TARBALL + ".sha256")
    return {"tag_name": tag, "assets": [asset(name) for name in names], "body": "notes", **fields}


def test_the_version_here_is_the_one_the_changelog_announced() -> None:
    """The installers take their version from the git tag. If this constant drifts from the
    changelog, a released build reports the wrong version and never sees itself as out of date."""
    changelog = (Path(__file__).parents[2] / "CHANGELOG.md").read_text(encoding="utf-8")
    # A version still being written is headed "- Unreleased" and is not announced yet.
    headings = re.findall(r"^## \[(\d+\.\d+\.\d+)\](?! - Unreleased)", changelog, flags=re.M)
    assert headings, "no released version in the changelog"
    assert headings[0] == VERSION, f"version.py says {VERSION}, changelog says {headings[0]}"


@pytest.mark.parametrize(
    ("candidate", "current", "newer"),
    [
        ("0.14.0", "0.13.0", True),
        ("v0.14.0", "0.13.0", True),
        ("0.13.1", "0.13.0", True),
        ("1.0.0", "0.13.0", True),
        ("0.13.0", "0.13.0", False),
        ("0.12.9", "0.13.0", False),
        ("0.9.0", "0.13.0", False),
        ("0.2.0", "0.13.0", False),
    ],
)
def test_version_ordering_is_by_number_not_by_text(candidate: str, current: str, newer: bool) -> None:
    """String comparison puts 0.9.0 above 0.13.0 and would offer a downgrade as an update."""
    assert is_newer(candidate, current) is newer


@pytest.mark.parametrize("value", ["", "v", "1.2.3-rc1", "latest", "1.2.x", "2026-09-20", "1.2.3.4.5"])
def test_a_tag_this_build_cannot_read_is_not_an_update(value: str) -> None:
    assert parse(value) is None
    assert is_newer(value, "0.13.0") is False


def test_a_newer_release_offers_the_file_for_this_install() -> None:
    found = available(release(), "windows")
    assert found is not None
    assert found["version"] == "9.9.9"
    assert found["asset"] == WINDOWS_SETUP
    assert found["checksum_url"].endswith(".sha256")


def test_an_appimage_is_offered_an_appimage() -> None:
    names = (LINUX_APPIMAGE, LINUX_APPIMAGE + ".sha256")
    assert available(release(names=names), "appimage")["asset"] == LINUX_APPIMAGE
    # ...and a tarball install is not offered that AppImage.
    assert available(release(names=names), "tarball") is None


def test_the_running_version_is_not_an_update() -> None:
    assert available(release(tag=f"v{VERSION}"), "windows") is None


def test_an_older_release_is_not_an_update() -> None:
    assert available(release(tag="v0.0.1"), "windows") is None


def test_drafts_and_prereleases_are_left_alone() -> None:
    assert available(release(draft=True), "windows") is None
    assert available(release(prerelease=True), "windows") is None


def test_a_release_whose_build_failed_offers_nothing() -> None:
    """A release can exist with no file for a platform if that job failed. Offering an update that
    cannot be downloaded is worse than staying quiet."""
    assert available(release(names=(LINUX_TARBALL, LINUX_TARBALL + ".sha256")), "windows") is None


def test_an_asset_with_no_checksum_beside_it_is_refused() -> None:
    assert available(release(names=(WINDOWS_SETUP,)), "windows") is None


@pytest.mark.parametrize("payload", [None, "", [], {"assets": "no"}, {"tag_name": 5}])
def test_a_payload_that_is_not_a_release_is_not_an_update(payload: object) -> None:
    assert available(payload, "windows") is None


def test_a_digest_is_taken_from_the_line_naming_this_file() -> None:
    digest = "a" * 64
    text = f"{'b' * 64}  OtherFile.exe\n{digest}  {WINDOWS_SETUP}\n"
    assert expected_digest(text, WINDOWS_SETUP) == digest
    assert expected_digest(text, "Missing.exe") is None


def test_a_binary_marked_checksum_line_still_reads() -> None:
    digest = "c" * 64
    assert expected_digest(f"{digest} *{LINUX_TARBALL}\n", LINUX_TARBALL) == digest


def test_only_the_exact_bytes_pass() -> None:
    payload = b"a packaged FlexWeek"
    digest = hashlib.sha256(payload).hexdigest()
    assert verified(payload, digest) is True
    assert verified(payload, digest.upper()) is True
    assert verified(payload + b"!", digest) is False
    assert verified(b"", digest) is False


@pytest.mark.parametrize("digest", [None, "", "abc", "z" * 64])
def test_a_missing_or_unreadable_digest_never_passes(digest: str | None) -> None:
    """An unverified binary is the one thing that must not be run, so absence fails closed."""
    assert verified(b"anything", digest) is False


def test_how_this_copy_was_installed_decides_what_it_downloads() -> None:
    assert install_kind("win32", appimage="", appdir="", executable="") == "windows"
    assert (
        install_kind(
            "linux",
            appimage="/x/FlexWeek-x86_64.AppImage",
            appdir="/tmp/.mount_fw",
            executable="/tmp/.mount_fw/usr/bin/FlexWeek",
        )
        == "appimage"
    )
    assert install_kind("linux", appimage="", appdir="", executable="/opt/fw/FlexWeek") == "tarball"


def test_another_application_s_appimage_is_not_mistaken_for_this_one() -> None:
    """APPIMAGE is inherited by every child process. A FlexWeek started from a terminal running
    inside some other AppImage sees that application's path, and an update would then overwrite a
    different program. Found because the editor this was written in is itself an AppImage."""
    assert (
        install_kind(
            "linux",
            appimage="/home/someone/AppImages/other-app.appimage",
            appdir="/tmp/.mount_other",
            executable="/opt/flexweek/FlexWeek",
        )
        == "tarball"
    )


def test_an_appimage_variable_with_no_mount_behind_it_is_ignored() -> None:
    assert (
        install_kind("linux", appimage="/x/FlexWeek.AppImage", appdir="", executable="/opt/fw/FlexWeek")
        == "tarball"
    )


def test_the_executable_path_is_resolved_before_it_is_compared_with_the_mount() -> None:
    """The original resolved both paths. `..` steps out of the mount, so this copy is not the image."""
    assert (
        install_kind(
            "linux",
            appimage="/x/FlexWeek.AppImage",
            appdir="/tmp/.mount_fw",
            executable="/tmp/.mount_fw/../elsewhere/FlexWeek",
        )
        == "tarball"
    )


def settings(**fields: object) -> dict:
    from desktop.native.update import sanitize_updates

    return {**sanitize_updates(None), **fields}


DAY_MS = 24 * 3_600_000


def test_a_fresh_install_checks_once_and_then_leaves_it_a_day() -> None:
    from desktop.native.update import due_for_check

    now = 1_700_000_000_000
    assert due_for_check(settings(), now) is True
    assert due_for_check(settings(last_ms=now), now) is False
    assert due_for_check(settings(last_ms=now), now + DAY_MS - 1) is False
    assert due_for_check(settings(last_ms=now), now + DAY_MS) is True


def test_turning_checks_off_stops_them() -> None:
    from desktop.native.update import due_for_check

    assert due_for_check(settings(check=False), 1_700_000_000_000) is False


def test_a_clock_that_went_backwards_does_not_stop_checking_forever() -> None:
    """A last-checked stamp from the future would otherwise never come due again."""
    from desktop.native.update import due_for_check

    now = 1_700_000_000_000
    assert due_for_check(settings(last_ms=now + 10 * DAY_MS), now) is True


def test_the_settings_file_survives_nonsense() -> None:
    from desktop.native.update import sanitize_updates

    assert sanitize_updates(None) == {"check": True, "last_ms": 0, "skip": ""}
    assert sanitize_updates("not a dict")["check"] is True
    assert sanitize_updates({"check": "yes"})["check"] is True
    assert sanitize_updates({"check": False})["check"] is False
    assert sanitize_updates({"last_ms": -5})["last_ms"] == 0
    assert sanitize_updates({"last_ms": "soon"})["last_ms"] == 0
    assert sanitize_updates({"skip": "x" * 99})["skip"] == ""
    assert sanitize_updates({"skip": "0.14.0"})["skip"] == "0.14.0"
