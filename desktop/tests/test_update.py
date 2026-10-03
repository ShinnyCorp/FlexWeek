"""The update rules that stay Python: the changelog's version and where this copy is installed.

The rest, including every refusal to install, is tested in engine/engine/tests/desk_update.rs.
"""

from __future__ import annotations

import re
from pathlib import Path

from desktop.native.update import install_kind
from desktop.native.version import VERSION


def test_the_version_here_is_the_one_the_changelog_announced() -> None:
    """The installers take their version from the git tag. If this constant drifts from the
    changelog, a released build reports the wrong version and never sees itself as out of date."""
    changelog = (Path(__file__).parents[2] / "CHANGELOG.md").read_text(encoding="utf-8")
    # A version still being written is headed "- Unreleased" and is not announced yet.
    headings = re.findall(r"^## \[(\d+\.\d+\.\d+)\](?! - Unreleased)", changelog, flags=re.M)
    assert headings, "no released version in the changelog"
    assert headings[0] == VERSION, f"version.py says {VERSION}, changelog says {headings[0]}"


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
