"""Deciding whether a newer FlexWeek exists, and which file to fetch for this install.

Nothing here touches the network, Qt or the disk. It takes the GitHub releases payload as plain
data and answers three questions: is there a newer release, which asset belongs to the way this copy
was installed, and does what arrived match the checksum published beside it. The fetching and the
installing live in updater.py, where they can be kept best-effort.

Updating is never silent. A download that is wrong, truncated or unverifiable is discarded, and the
student is told where the release page is instead. Replacing a working app with a broken one is a
worse outcome than not updating at all.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import TypedDict

import flexweek_engine  # type: ignore[import-untyped]

from desktop.native.version import VERSION

RELEASES_URL = "https://api.github.com/repos/j0nsh1n/FlexWeek/releases/latest"
RELEASE_PAGE = "https://github.com/j0nsh1n/FlexWeek/releases/latest"
RELEASE_TAG_PAGE = "https://github.com/j0nsh1n/FlexWeek/releases/tag/"
RELEASE_DOWNLOAD = "https://github.com/j0nsh1n/FlexWeek/releases/download/"
CHECK_EVERY_HOURS = 24

WINDOWS_SETUP = "FlexWeek-Windows-x64-Setup.exe"
WINDOWS_MSI = "FlexWeek-Windows-x64.msi"
LINUX_TARBALL = "FlexWeek-Linux-x86_64.tar.gz"
LINUX_APPIMAGE = "FlexWeek-x86_64.AppImage"


class Update(TypedDict):
    version: str
    asset: str
    url: str
    checksum_url: str
    notes: str


def install_kind(
    platform: str | None = None,
    appimage: str | None = None,
    appdir: str | None = None,
    executable: str | None = None,
) -> str:
    """How this copy was installed, which decides what an update looks like.

    The process environment and the file system are read here, not in the engine. `APPIMAGE` alone
    is not enough: a FlexWeek started inside some other AppImage inherits that path. The engine then
    checks whether this executable, with links followed, is running from inside the mounted image.
    """
    system = sys.platform if platform is None else platform
    image = os.environ.get("APPIMAGE", "") if appimage is None else appimage
    mount = os.environ.get("APPDIR", "") if appdir is None else appdir
    running = (sys.executable if executable is None else executable) or ""
    if not system.startswith("win") and image and mount and running:
        try:
            running = str(Path(running).resolve())
            mount = str(Path(mount).resolve())
        except OSError, ValueError:
            return "tarball"
    return str(flexweek_engine.update_install_kind(system, image or "", mount or "", running))


def asset_name(kind: str) -> str:
    return str(flexweek_engine.update_asset_name(kind))


def available(release: object, kind: str, current: str = VERSION) -> Update | None:
    """The update in this release for this kind of install, or None.

    None covers every uninteresting case: a malformed payload, a draft, a tag this build cannot
    read, a release no newer than what is running, and a release that has no file for this platform
    because its build failed.
    """
    raw = flexweek_engine.update_available(release, kind, current)
    return None if raw is None else json.loads(raw)


def release_from_page(location: str) -> dict | None:
    """The newest release as the API would describe it, from where the release page redirects.

    GitHub's API answers 60 unsigned requests an hour per address, and a school or a phone carrier
    puts many students behind one address, so the check could be refused with the app still asking.
    The release page is not counted that way and redirects to the newest release's tag, which is
    never a draft or a pre-release. File names are fixed, so their addresses follow from the tag.
    There are no notes, and a file a failed build never uploaded is found out by downloading it.
    """
    raw = flexweek_engine.update_release_from_page(location)
    return None if raw is None else json.loads(raw)


def expected_digest(checksum_text: str, asset: str) -> str | None:
    """The digest for this asset out of a sha256sum file.

    The published files name one asset each, but the format allows several lines, so the one naming
    this asset is the one that counts rather than simply the first.
    """
    return flexweek_engine.update_expected_digest(checksum_text, asset)


def verified(payload: bytes, digest: str | None) -> bool:
    """Whether the bytes are what the release says they are. An absent or unreadable digest is a
    failure, not a pass: an unverified binary is exactly what must not be run."""
    return bool(flexweek_engine.update_verified(payload, digest))


def sanitize_updates(raw: object) -> dict:
    """The device's update settings, whatever the file on disk says.

    Device-only, in the look file, rather than a preference on the account: whether this computer
    checks for updates is a property of this computer, and an account field would need the owner's
    approval to add.
    """
    return json.loads(flexweek_engine.update_sanitize(raw))


def due_for_check(settings: dict, now_ms: int) -> bool:
    """Once a day at most, and never when the student turned it off. A clock that has gone backwards
    is treated as due rather than never: the alternative is an app that stops checking forever."""
    return bool(flexweek_engine.update_due(json.dumps(settings), now_ms))
