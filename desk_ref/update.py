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

import hashlib
import os
import re
import sys
from pathlib import Path
from typing import TypedDict

from desktop.native.version import VERSION, is_newer

RELEASES_URL = "https://api.github.com/repos/j0nsh1n/FlexWeek/releases/latest"
RELEASE_PAGE = "https://github.com/j0nsh1n/FlexWeek/releases/latest"
RELEASE_TAG_PAGE = "https://github.com/j0nsh1n/FlexWeek/releases/tag/"
RELEASE_DOWNLOAD = "https://github.com/j0nsh1n/FlexWeek/releases/download/"
_TAG = re.compile(r"v?[0-9]+(\.[0-9]+){1,3}")
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

    `APPIMAGE` alone is not enough to go on. It is inherited by every child process, so a FlexWeek
    started from a terminal inside some other AppImage sees that other application's path and would
    offer to overwrite it. The AppImage runtime sets `APPDIR` to the mounted image as well, so the
    question asked here is whether this executable is running from inside that image.
    """
    system = sys.platform if platform is None else platform
    if system.startswith("win"):
        return "windows"
    image = os.environ.get("APPIMAGE", "") if appimage is None else appimage
    mount = os.environ.get("APPDIR", "") if appdir is None else appdir
    running = (sys.executable if executable is None else executable) or ""
    if image and mount and running:
        try:
            if Path(running).resolve().is_relative_to(Path(mount).resolve()):
                return "appimage"
        except OSError, ValueError:
            return "tarball"
    return "tarball"


def asset_name(kind: str) -> str:
    return {
        "windows": WINDOWS_SETUP,
        "appimage": LINUX_APPIMAGE,
        "tarball": LINUX_TARBALL,
    }[kind]


def available(release: object, kind: str, current: str = VERSION) -> Update | None:
    """The update in this release for this kind of install, or None.

    None covers every uninteresting case: a malformed payload, a draft, a tag this build cannot
    read, a release no newer than what is running, and a release that has no file for this platform
    because its build failed.
    """
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        return None
    tag = release.get("tag_name")
    if not isinstance(tag, str) or not is_newer(tag, current):
        return None
    assets = release.get("assets")
    if not isinstance(assets, list):
        return None
    wanted = asset_name(kind)
    by_name = {
        item.get("name"): item.get("browser_download_url")
        for item in assets
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    url, checksum_url = by_name.get(wanted), by_name.get(wanted + ".sha256")
    if not isinstance(url, str) or not isinstance(checksum_url, str):
        return None
    body = release.get("body")
    return Update(
        version=tag.removeprefix("v"),
        asset=wanted,
        url=url,
        checksum_url=checksum_url,
        notes=body if isinstance(body, str) else "",
    )


def release_from_page(location: str) -> dict | None:
    """The newest release as the API would describe it, from where the release page redirects.

    GitHub's API answers 60 unsigned requests an hour per address, and a school or a phone carrier
    puts many students behind one address, so the check could be refused with the app still asking.
    The release page is not counted that way and redirects to the newest release's tag, which is
    never a draft or a pre-release. File names are fixed, so their addresses follow from the tag.
    There are no notes, and a file a failed build never uploaded is found out by downloading it.
    """
    if not location.startswith(RELEASE_TAG_PAGE):
        return None
    tag = location.removeprefix(RELEASE_TAG_PAGE)
    if not _TAG.fullmatch(tag):
        return None
    names = (WINDOWS_SETUP, WINDOWS_MSI, LINUX_TARBALL, LINUX_APPIMAGE)
    assets = [
        {"name": name, "browser_download_url": f"{RELEASE_DOWNLOAD}{tag}/{name}"}
        for base in names
        for name in (base, base + ".sha256")
    ]
    return {"tag_name": tag, "assets": assets, "body": ""}


def expected_digest(checksum_text: str, asset: str) -> str | None:
    """The digest for this asset out of a sha256sum file.

    The published files name one asset each, but the format allows several lines, so the one naming
    this asset is the one that counts rather than simply the first.
    """
    for line in checksum_text.splitlines():
        parts = line.split()
        if len(parts) != 2 or len(parts[0]) != 64:
            continue
        if parts[1].lstrip("*") == asset:
            return parts[0].lower()
    return None


def verified(payload: bytes, digest: str | None) -> bool:
    """Whether the bytes are what the release says they are. An absent or unreadable digest is a
    failure, not a pass: an unverified binary is exactly what must not be run."""
    if not digest or len(digest) != 64:
        return False
    return hashlib.sha256(payload).hexdigest() == digest.lower()


def sanitize_updates(raw: object) -> dict:
    """The device's update settings, whatever the file on disk says.

    Device-only, in the look file, rather than a preference on the account: whether this computer
    checks for updates is a property of this computer, and an account field would need the owner's
    approval to add.
    """
    clean = {"check": True, "last_ms": 0, "skip": ""}
    if not isinstance(raw, dict):
        return clean
    if raw.get("check") is False:
        clean["check"] = False
    last = raw.get("last_ms")
    if isinstance(last, int) and 0 <= last <= 4_102_444_800_000:
        clean["last_ms"] = last
    skip = raw.get("skip")
    if isinstance(skip, str) and len(skip) <= 32:
        clean["skip"] = skip
    return clean


def due_for_check(settings: dict, now_ms: int) -> bool:
    """Once a day at most, and never when the student turned it off. A clock that has gone backwards
    is treated as due rather than never: the alternative is an app that stops checking forever."""
    if not settings.get("check", True):
        return False
    last = int(settings.get("last_ms") or 0)
    return last > now_ms or now_ms - last >= CHECK_EVERY_HOURS * 3_600_000
