"""Fetching a newer FlexWeek and putting it in place.

The deciding is in update.py, which is pure; this is the part that touches the network, the disk and
the running process, so it is written to fail safe at every step. A check that cannot reach GitHub
says nothing. A download that does not match its published checksum is deleted. An install directory
that cannot be written is reported rather than half-written. The app the student already has keeps
working in every one of those cases.

Nothing installs without the student pressing the button. The only thing that happens on its own is
the check, at most once a day, and that can be turned off.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from desktop.native.update import (
    RELEASE_PAGE,
    RELEASES_URL,
    Update,
    available,
    expected_digest,
    install_kind,
    release_from_page,
    verified,
)

USER_AGENT = b"FlexWeek-Updater"
DOWNLOAD_FOLDER_PREFIX = "flexweek-update-"
# On Windows the installer keeps running from its download after FlexWeek quits, so a download is only
# collected at the next launch once it is this old.
STALE_DOWNLOAD_S = 3600
DOWNLOAD_LIMIT = 400 * 1024 * 1024
# A check that hears nothing gives up rather than showing "Checking for updates…" for good. A download
# is only stopped when no data arrives for this long, so a slow connection still finishes.
CHECK_TIMEOUT_MS = 15_000
DOWNLOAD_STALL_MS = 30_000
CHECK_FAILED = "FlexWeek could not check for updates right now. Try again later, or open the release page."
DOWNLOAD_STOPPED = "The download stopped before it finished. Try again, or open the release page."


class Updater(QObject):
    """One check, then one download, then one hand-off. Never two at once."""

    found = Signal(object)
    none_found = Signal()
    # The check could not be completed. Said only when the student asked for it.
    unreachable = Signal(str)
    progress = Signal(int, int)
    failed = Signal(str)
    ready = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._busy = False
        self.kind = install_kind()

    @property
    def busy(self) -> bool:
        return self._busy

    def check(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._get(RELEASES_URL, self._on_release, fallback=self._check_page)

    def download(self, update: Update) -> None:
        if self._busy:
            return
        self._busy = True
        self._get(
            update["checksum_url"],
            lambda text: self._on_checksum(update, text),
        )

    def _request(self, url: str, timeout_ms: int, *, follow: bool = True) -> QNetworkRequest:
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", USER_AGENT)
        request.setTransferTimeout(timeout_ms)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy
            if follow
            else QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
        )
        return request

    def _get(self, url: str, then: object, binary: bool = False, fallback: object = None) -> None:
        timeout = CHECK_TIMEOUT_MS if fallback is not None else DOWNLOAD_STALL_MS
        reply = self._manager.get(self._request(url, timeout))
        if binary:
            reply.downloadProgress.connect(lambda got, total: self.progress.emit(got, max(total, 0)))
        reply.finished.connect(lambda: self._finish(reply, then, binary, fallback))

    def _finish(self, reply: QNetworkReply, then: object, binary: bool, fallback: object = None) -> None:
        data = bytes(reply.readAll().data())
        error = reply.error()
        reply.deleteLater()
        if error != QNetworkReply.NetworkError.NoError:
            # The API refuses unsigned checks past 60 an hour per address (403), which a shared school
            # or phone network reaches; the release page is asked instead. A download that fails is
            # reported: stopping quietly left the update dialog waiting for good.
            if callable(fallback):
                fallback()
            else:
                self._give_up(DOWNLOAD_STOPPED)
            return
        if len(data) > DOWNLOAD_LIMIT:
            self._give_up("That download was larger than any FlexWeek release.")
            return
        then(data if binary else data.decode("utf-8", "replace"))  # type: ignore[operator]

    def _stop(self) -> None:
        self._busy = False

    def _check_page(self) -> None:
        reply = self._manager.get(self._request(RELEASE_PAGE, CHECK_TIMEOUT_MS, follow=False))
        reply.finished.connect(lambda: self._on_page(reply))

    def _on_page(self, reply: QNetworkReply) -> None:
        target = reply.attribute(QNetworkRequest.Attribute.RedirectionTargetAttribute)
        reply.deleteLater()
        release = release_from_page(target.toString() if isinstance(target, QUrl) else "")
        if release is None:
            self._busy = False
            self.unreachable.emit(CHECK_FAILED)
            return
        self._decide(release)

    def _give_up(self, why: str) -> None:
        self._busy = False
        self.failed.emit(why)

    def _on_release(self, text: str) -> None:
        try:
            payload = json.loads(text)
        except ValueError:
            self._check_page()
            return
        self._decide(payload)

    def _decide(self, payload: object) -> None:
        update = available(payload, self.kind)
        self._busy = False
        if update is None:
            self.none_found.emit()
            return
        self.found.emit(update)

    def _on_checksum(self, update: Update, text: str) -> None:
        digest = expected_digest(text, update["asset"])
        if digest is None:
            self._give_up("That release did not publish a checksum, so it was not downloaded.")
            return
        self._get(update["url"], lambda data: self._on_payload(update, digest, data), binary=True)

    def _on_payload(self, update: Update, digest: str, data: bytes) -> None:
        if not verified(data, digest):
            # Wrong bytes: a truncated download, a proxy, or something worse. Keep what works.
            self._give_up("The download did not match its checksum, so it was discarded.")
            return
        folder = Path(tempfile.mkdtemp(prefix=DOWNLOAD_FOLDER_PREFIX))
        target = folder / update["asset"]
        try:
            target.write_bytes(data)
            target.chmod(target.stat().st_mode | stat.S_IXUSR)
        except OSError:
            shutil.rmtree(folder, ignore_errors=True)
            self._give_up("The download could not be saved.")
            return
        self._busy = False
        self.ready.emit(str(target))


def bundle_root() -> Path:
    """The directory that would be replaced by a tarball update."""
    return Path(sys.executable).resolve().parent


def writable(path: Path) -> bool:
    return os.access(path, os.W_OK)


def _own_download_folder(downloaded: Path) -> Path | None:
    """The folder the updater made for this download, or None for a file it did not put there."""
    folder = downloaded.parent
    ours = folder.name.startswith(DOWNLOAD_FOLDER_PREFIX) and folder.parent == Path(tempfile.gettempdir())
    return folder if ours and not folder.is_symlink() else None


def collect_stale_downloads() -> None:
    """Remove downloads an earlier run left behind, at launch, when none of this run's is under way."""
    root = Path(tempfile.gettempdir())
    cutoff = time.time() - STALE_DOWNLOAD_S
    try:
        found = [item for item in root.iterdir() if item.name.startswith(DOWNLOAD_FOLDER_PREFIX)]
    except OSError:
        return
    for folder in found:
        try:
            if folder.is_dir() and not folder.is_symlink() and folder.stat().st_mtime < cutoff:
                shutil.rmtree(folder, ignore_errors=True)
        except OSError:
            continue


def apply_update(downloaded: str, kind: str | None = None) -> str | None:
    """Put the downloaded release in place. Returns None on success, or why it could not.

    The caller restarts the app afterwards; on Windows the installer does its own thing and the app
    simply quits.
    """
    how = install_kind() if kind is None else kind
    source = Path(downloaded)
    if how == "windows":
        # The installer is still running from its download, which is collected at the next launch.
        from PySide6.QtCore import QProcess

        # Inno Setup upgrades an existing install in place; /SILENT keeps it to a progress window.
        started = QProcess.startDetached(str(source), ["/SILENT", "/NOCANCEL"])
        return None if started else "The installer would not start."
    try:
        if how == "appimage":
            current = os.environ.get("APPIMAGE")
            if not current:
                return "This copy does not know where its AppImage is."
            return _swap_file(source, Path(current))
        return _swap_tree(source)
    finally:
        folder = _own_download_folder(source)
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)


def _swap_file(source: Path, target: Path) -> str | None:
    if not writable(target.parent):
        return f"{target.parent} cannot be written, so the update was not applied."
    try:
        beside = target.with_suffix(target.suffix + ".new")
        shutil.copy2(source, beside)
        beside.chmod(beside.stat().st_mode | stat.S_IXUSR)
        # Atomic on one filesystem: the file is either the old one or the new one, never half.
        os.replace(beside, target)
    except OSError as error:
        return f"The update could not be put in place: {error}"
    return None


def _swap_tree(source: Path) -> str | None:
    """Unpack a tarball over the running bundle by building the new one beside it and swapping.

    Writing into the live directory would leave a half-updated app if anything failed part way.
    """
    root = bundle_root()
    if not writable(root.parent):
        return f"{root.parent} cannot be written, so the update was not applied."
    staging = root.parent / (root.name + ".update")
    previous = root.parent / (root.name + ".old")
    try:
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        with tarfile.open(source) as archive:
            _safe_extract(archive, staging)
        unpacked = next((child for child in staging.iterdir() if child.is_dir()), staging)
        shutil.rmtree(previous, ignore_errors=True)
        os.replace(root, previous)
        os.replace(unpacked, root)
    except (OSError, tarfile.TarError) as error:
        shutil.rmtree(staging, ignore_errors=True)
        if not root.exists() and previous.exists():
            os.replace(previous, root)
        return f"The update could not be put in place: {error}"
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(previous, ignore_errors=True)
    return None


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    """Refuse a member that would write outside the destination. A release is trusted, but a
    verified checksum proves the bytes came from GitHub, not that the archive is sane."""
    root = destination.resolve()
    for member in archive.getmembers():
        target = (root / member.name).resolve()
        if not target.is_relative_to(root):
            raise tarfile.TarError(f"{member.name} would be written outside the folder")
        if member.issym() or member.islnk():
            link = (target.parent / member.linkname).resolve()
            if not link.is_relative_to(root):
                raise tarfile.TarError(f"{member.name} links outside the folder")
    archive.extractall(destination, filter="tar")
