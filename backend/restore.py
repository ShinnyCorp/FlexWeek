"""Restore-point snapshots. The engine compares them. No HTTP, no database."""

from __future__ import annotations

import json

from flexweek_engine import (  # type: ignore[import-untyped]
    canonical as _canonical,
)
from flexweek_engine import (
    diff_snapshots as _diff_snapshots,
)
from flexweek_engine import (
    diff_transfer as _diff_transfer,
)
from flexweek_engine import (
    state_token as _state_token,
)


def canonical(value: object) -> str:
    return _canonical(json.dumps(value))


def state_token(snapshot: dict) -> str:
    return _state_token(json.dumps(snapshot))


def diff_snapshots(current: dict, stored: dict) -> dict:
    return json.loads(_diff_snapshots(json.dumps(current), json.dumps(stored)))


def diff_transfer(current: dict, incoming: dict) -> dict:
    return json.loads(_diff_transfer(json.dumps(current), json.dumps(incoming)))
