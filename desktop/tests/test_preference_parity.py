"""Every account preference has to be reachable from the desktop app, or be named as web-only.

The browser shell was retired, so the native client is how most students meet FlexWeek. Ten of the
twenty-six preferences could only be set from the web app, including `start_at_login`, a desktop
feature the desktop app could not turn on.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib

import pytest

from backend.app import Preferences

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Settings the desktop app has nothing to do with. Each needs a reason, not just an entry.
WEB_ONLY = {
    "sidebar_collapsed": "the sidebar is a web layout; the desktop app has no sidebar",
    "sidebar_width_px": "as above",
}
# Set in their own dialog rather than in Settings.
ELSEWHERE = {
    "protected": "Availability",
    "day_cutoff": "Availability",
    "setup": "first-run setup writes it; Settings offers Run setup again",
}
# Written for you, not chosen. save_preferences derives the light or dark axis from the pack.
DERIVED = {"theme": "follows theme_pack, set in NativeSession.save_preferences"}


def native_source() -> str:
    return "\n".join(p.read_text() for p in pathlib.Path("desktop/native").rglob("*.py"))


def test_every_preference_is_reachable_from_the_desktop_app() -> None:
    source = native_source()
    unreachable = [
        field for field in Preferences.model_fields if field not in source and field not in WEB_ONLY
    ]
    assert unreachable == [], f"the desktop app cannot set: {unreachable}"


def test_the_settings_dialog_saves_what_it_shows() -> None:
    """A control the dialog builds but never writes back is worse than no control at all."""
    settings = pathlib.Path("desktop/native/settings.py").read_text()
    body = settings[settings.index("def updates(") :]
    saved = {field for field in Preferences.model_fields if f'"{field}"' in body}
    shown = {
        field
        for field in Preferences.model_fields
        if field not in WEB_ONLY and field not in ELSEWHERE and field not in DERIVED and field in settings
    }
    assert shown - saved == set(), f"shown in Settings but never saved: {sorted(shown - saved)}"


def test_a_derived_preference_really_is_derived() -> None:
    controller = pathlib.Path("desktop/native/controller.py").read_text()
    for field in DERIVED:
        assert f'body["{field}"]' in controller, f"{field} is not derived anywhere"


def test_every_web_only_preference_says_why() -> None:
    for field, reason in WEB_ONLY.items():
        assert field in Preferences.model_fields, f"{field} is no longer a preference"
        assert reason, field
