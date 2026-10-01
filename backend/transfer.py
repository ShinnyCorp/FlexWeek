"""Account-transfer size checks. The engine measures the envelope. No HTTP, no database."""

from __future__ import annotations

import json

from flexweek_engine import (  # type: ignore[import-untyped]
    transfer_apply_bytes as _transfer_apply_bytes,
)
from flexweek_engine import (
    transfer_apply_envelope as _transfer_apply_envelope,
)
from flexweek_engine import (
    transfer_fits as _transfer_fits,
)

from backend.limits import MAX_BODY

TRANSFER_TOO_LARGE = "This account is larger than the 256 KiB transfer limit."


def transfer_apply_envelope(snapshot: dict) -> dict:
    return json.loads(_transfer_apply_envelope(json.dumps(snapshot)))


def transfer_apply_bytes(snapshot: dict) -> int:
    return _transfer_apply_bytes(json.dumps(snapshot))


def transfer_fits(snapshot: dict) -> bool:
    measured = _transfer_fits(json.dumps(snapshot))
    # The cap stays the same constant the routes already import.
    return measured and transfer_apply_bytes(snapshot) <= MAX_BODY
