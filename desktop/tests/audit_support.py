"""Shared by the audit-0190 window tests: a server that stops answering, and its return."""

from __future__ import annotations

from desktop.native.client import _error
from desktop.native.window import NativeWindow


def refuse_all(window: NativeWindow, verb: str, path: str) -> list[dict]:
    """Every matching request fails the way a dropped connection does; returns what was sent."""
    real = window.session.client.request
    sent: list[dict] = []

    def request(method, target, payload, on_success, on_error):
        if method != verb or not target.startswith(path):
            return real(method, target, payload, on_success, on_error)
        sent.append(payload)
        on_error(_error(0))
        return None

    window.session.client.request = request  # type: ignore[method-assign]
    window._real_request = real  # type: ignore[attr-defined]
    return sent


def reconnect(window: NativeWindow) -> None:
    window.session.client.request = window._real_request  # type: ignore[attr-defined,method-assign]
