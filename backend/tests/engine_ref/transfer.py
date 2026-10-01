"""Account-transfer size checks. No HTTP, no database."""

from __future__ import annotations

import json

from backend.tests.engine_ref.limits import MAX_BODY

TRANSFER_TOO_LARGE = "This account is larger than the 256 KiB transfer limit."
APPLY_TOKEN_PAD = "f" * 64
APPLY_OPERATION_PAD = "o" * 80


def transfer_apply_envelope(snapshot: dict) -> dict:
    return {
        "snapshot": snapshot,
        "state_token": APPLY_TOKEN_PAD,
        "operation_id": APPLY_OPERATION_PAD,
    }


def transfer_apply_bytes(snapshot: dict) -> int:
    return len(json.dumps(transfer_apply_envelope(snapshot), separators=(",", ":")).encode())


def transfer_fits(snapshot: dict) -> bool:
    return transfer_apply_bytes(snapshot) <= MAX_BODY
