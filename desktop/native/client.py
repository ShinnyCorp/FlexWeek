"""Asynchronous access to the desktop's private Python API."""

from __future__ import annotations

import contextlib
import ipaddress
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from PySide6.QtCore import QByteArray, QObject, QThread, QTimer, QUrl, Signal
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkCookie,
    QNetworkCookieJar,
    QNetworkProxy,
    QNetworkReply,
    QNetworkRequest,
)

REQUEST_TIMEOUT_MS = 30_000
SESSION_COOKIE = b"flexweek_session"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
PASSWORD_LENGTH_HINT = "Password: use 12–128 characters."
USERNAME_HINT = "Username: 3–32 letters, numbers or underscores."
USERNAME_ERROR = "Use 3 to 32 letters, numbers or underscores, with no spaces."
# Sign-in and sign-up say which thing is wrong wherever FlexWeek can tell. The server answers a wrong
# password and an unknown username alike on purpose; the sign-in card's link says why.
SIGN_IN_WRONG = "Wrong username or password. Try again, or choose Forgot password."
SIGN_IN_WHY_LINK = "Why doesn't it say which?"
SIGN_IN_WHY = "FlexWeek doesn't say which, so no one can find out who has an account."
SIGN_IN_NO_USERNAME = "Type your username."
SIGN_IN_NO_PASSWORD = "Type your password."
SIGN_IN_BAD_USERNAME = (
    "No FlexWeek username looks like that. Usernames are 3–32 letters, numbers or underscores."
)
SIGN_IN_SHORT_PASSWORD = "That isn't your password. FlexWeek passwords have at least 12 characters."
SIGN_UP_NO_USERNAME = "Choose a username."
SIGN_UP_NO_PASSWORD = "Choose a password with at least 12 characters."
SIGN_UP_SHORT_PASSWORD = "Add {n} more characters. Passwords need at least 12."
SIGN_UP_LONG_PASSWORD = "Use 128 characters or fewer."
USERNAME_TAKEN = "That username is taken. Try another."
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApiError:
    status: int
    message: str


class _CookieJar(QNetworkCookieJar):
    def snapshot(self) -> list[QNetworkCookie]:
        return self.allCookies()


def _local_origin(origin: str) -> str:
    try:
        parsed = urlsplit(origin)
        address = ipaddress.ip_address(parsed.hostname or "")
        host = f"[{address}]" if address.version == 6 else str(address)
        canonical = f"http://{host}:{parsed.port}"
        if (
            not address.is_loopback
            or parsed.port is None
            or parsed.port == 0
            or parsed.username is not None
            or parsed.password is not None
            or origin != canonical
        ):
            raise ValueError
    except ValueError:
        raise ValueError("The desktop API needs a canonical HTTP loopback origin with a port.") from None
    return canonical


def _api_path(path: str) -> None:
    parsed = urlsplit(path)
    decoded = unquote(parsed.path)
    if (
        not path.startswith("/api/")
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or "#" in path
        or "\\" in decoded
        or "//" in decoded
        or any(part in {".", ".."} for part in decoded.split("/"))
        or any(ord(char) < 33 or ord(char) == 127 for char in path)
        or not decoded.startswith("/api/")
    ):
        raise ValueError("Only relative /api/ requests are allowed.")


def _field_error(detail: object, names: tuple[str, ...], message: str) -> str | None:
    items = detail if isinstance(detail, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        loc = [str(part).lower() for part in (item.get("loc") or [])]
        if any(name in loc for name in names):
            return message
    return None


def _password_error(detail: object) -> str | None:
    return _field_error(detail, ("password", "new_password", "current_password"), PASSWORD_LENGTH_HINT)


def _username_error(detail: object) -> str | None:
    return _field_error(detail, ("username",), USERNAME_ERROR)


def _error(status: int, detail: object = None) -> ApiError:
    if status == 401 and detail == "Incorrect password":
        return ApiError(status, "Incorrect password. Try again.")
    if status == 401 and detail == "Incorrect username or password":
        return ApiError(status, SIGN_IN_WRONG)
    if status == 409 and detail == "Username unavailable":
        return ApiError(status, USERNAME_TAKEN)
    if status == 401 and detail == "Incorrect username or recovery code":
        return ApiError(status, "Wrong username or recovery code. Each code works once; try another one.")
    if status == 422:
        named = _password_error(detail) or _username_error(detail)
        if named:
            return ApiError(status, named)
    messages = {
        0: "Could not reach FlexWeek. Your changes may not have been saved. Try again.",
        401: "Please sign in again, or check your username and password.",
        403: "This request was refused. Restart FlexWeek and try again.",
        404: "This item is no longer available. Reload and try again.",
        409: "The saved data changed or that name is already in use. Reload and try again.",
        413: "This request is too large. Reduce its size and try again.",
        422: "Check the required fields, dates, times and lengths, then try again.",
        429: "Too many attempts. Wait five minutes before trying again.",
        503: "Storage is unavailable. Keep your changes and try again shortly.",
    }
    return ApiError(status, messages.get(status, "FlexWeek could not complete this request. Try again."))


def _username_ok(name: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_]{3,32}", name) is not None


def sign_in_problem(name: str, password: str) -> str:
    """What is wrong before asking the server, which could only say "check the required fields"."""
    if not name:
        return SIGN_IN_NO_USERNAME
    if not password:
        return SIGN_IN_NO_PASSWORD
    if not _username_ok(name):
        return SIGN_IN_BAD_USERNAME
    if len(password) < 12:
        return SIGN_IN_SHORT_PASSWORD
    return ""


def sign_up_problem(name: str, password: str) -> str:
    if not name:
        return SIGN_UP_NO_USERNAME
    if not _username_ok(name):
        return USERNAME_ERROR
    if not password:
        return SIGN_UP_NO_PASSWORD
    if len(password) > 128:
        return SIGN_UP_LONG_PASSWORD
    if len(password) < 12:
        return SIGN_UP_SHORT_PASSWORD.format(n=12 - len(password))
    return ""


def auth_error(error: ApiError, *, creating: bool) -> ApiError:
    """The words for a sign-in or sign-up that failed on the way. The general ones speak of changes
    that may not have been saved, which a sign-in never has."""
    then = "create your account" if creating else "sign in"
    if error.status == 0:
        return ApiError(0, f"FlexWeek can't reach its server. Close FlexWeek, open it again, then {then}.")
    if error.status == 503:
        return ApiError(503, f"FlexWeek can't open its saved data right now. Wait a minute, then {then}.")
    return error


class NativeClient(QObject):
    expired = Signal()

    def __init__(self, origin: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.origin = _local_origin(origin)
        self.account: dict | None = None
        self.epoch = 0
        self._replies: dict[QNetworkAccessManager, set[QNetworkReply]] = {}
        self._manager = self._new_manager([])

    def _check_thread(self) -> None:
        if QThread.currentThread() != self.thread():
            raise RuntimeError("The native API client must be used on its Qt thread.")

    def _new_manager(self, cookies: list[QNetworkCookie]) -> QNetworkAccessManager:
        manager = QNetworkAccessManager(self)
        manager.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        jar = _CookieJar(manager)
        jar.setAllCookies(cookies)
        manager.setCookieJar(jar)
        self._replies[manager] = set()
        return manager

    def _rotate(self, cookies: list[QNetworkCookie]) -> None:
        previous = self._manager
        self.epoch += 1
        self._manager = self._new_manager(cookies)
        # Abort can emit finished synchronously. Install the new epoch and jar first.
        for reply in tuple(self._replies[previous]):
            reply.abort()
        self._retire(previous)

    def _retire(self, manager: QNetworkAccessManager) -> None:
        if manager != self._manager and not self._replies.get(manager):
            self._replies.pop(manager, None)
            manager.deleteLater()

    def set_account(self, identity: dict) -> None:
        self._check_thread()
        if (
            type(identity.get("id")) is not int
            or identity["id"] <= 0
            or not isinstance(identity.get("username"), str)
            or not identity["username"]
        ):
            raise ValueError("An account needs a valid id and username.")
        jar = self._manager.cookieJar()
        assert isinstance(jar, _CookieJar)
        self.account = {"id": identity["id"], "username": identity["username"]}
        self._rotate(jar.snapshot())

    def reset(self) -> None:
        self._check_thread()
        self.account = None
        self._rotate([])

    def session_token(self) -> str | None:
        jar = self._manager.cookieJar()
        for cookie in jar.cookiesForUrl(QUrl(self.origin + "/")):
            if bytes(cookie.name().data()) == SESSION_COOKIE:
                return bytes(cookie.value().data()).decode("ascii", "replace") or None
        return None

    def adopt_session(self, token: str) -> None:
        """A session kept from an earlier launch. That launch's server was on another port, so the
        cookie is set again for this origin; the next request says whether it still works."""
        self._check_thread()
        self.account = None
        self._rotate([])
        jar = self._manager.cookieJar()
        cookie = QNetworkCookie(SESSION_COOKIE, token.encode("ascii"))
        jar.setCookiesFromUrl([cookie], QUrl(self.origin + "/"))

    @staticmethod
    def _notify_error(callback: Callable[[ApiError], None], error: ApiError) -> None:
        try:
            callback(error)
        except Exception:
            logger.error("A native request error handler failed.")

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None,
        on_success: Callable[[dict], None],
        on_error: Callable[[ApiError], None],
    ) -> QNetworkReply:
        self._check_thread()
        _api_path(path)
        method = method.upper()
        if method not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
            raise ValueError("Unsupported API request method.")
        if payload is not None and not isinstance(payload, dict):
            raise ValueError("API request bodies must be JSON objects.")
        encoded = json.dumps(payload, allow_nan=False).encode() if payload is not None else b""
        data = QByteArray(encoded)
        request = QNetworkRequest(QUrl(self.origin + path))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
        )
        request.setRawHeader(b"Accept", b"application/json")
        request.setRawHeader(b"Content-Type", b"application/json")
        request.setRawHeader(b"Origin", self.origin.encode("ascii"))
        request.setRawHeader(b"X-FlexWeek-Request", b"1")
        account_id = self.account["id"] if self.account is not None else None
        if account_id is not None:
            request.setRawHeader(b"X-FlexWeek-Account", str(account_id).encode("ascii"))
        epoch, manager = self.epoch, self._manager
        reply = manager.sendCustomRequest(request, method.encode("ascii"), data)
        self._replies[manager].add(reply)
        timer = QTimer(reply)
        timer.setSingleShot(True)
        timer.timeout.connect(reply.abort)
        timer.start(REQUEST_TIMEOUT_MS)

        def finished() -> None:
            timer.stop()
            self._replies[manager].discard(reply)
            try:
                if epoch != self.epoch:
                    return
                status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
                body = bytes(reply.readAll())
                result: object = None
                if len(body) <= MAX_RESPONSE_BYTES:
                    with contextlib.suppress(ValueError, UnicodeDecodeError):
                        result = json.loads(body) if body else {}
                detail = result.get("detail") if isinstance(result, dict) else None
                if not 200 <= status < 300 or reply.error() != QNetworkReply.NetworkError.NoError:
                    self._notify_error(on_error, _error(status, detail))
                    expired = (
                        status == 401
                        and account_id is not None
                        and detail
                        not in {
                            "Incorrect password",
                            "Incorrect username or password",
                            "Incorrect username or recovery code",
                        }
                        and epoch == self.epoch
                    )
                    if expired:
                        self.expired.emit()
                    return
                if not isinstance(result, dict) or (not body and status != 204):
                    self._notify_error(
                        on_error, ApiError(status, "FlexWeek returned an unreadable response.")
                    )
                    return
                try:
                    on_success(result)
                except Exception:
                    logger.error("A native request result handler failed.")
                    self._notify_error(
                        on_error, ApiError(status, "FlexWeek could not display this response.")
                    )
            finally:
                reply.deleteLater()
                self._retire(manager)

        reply.finished.connect(finished)
        return reply
