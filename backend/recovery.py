"""One-time recovery codes. The engine formats and hashes them. No HTTP, no database."""

from __future__ import annotations

import re
import secrets

import flexweek_engine  # type: ignore[import-untyped]
from flexweek_engine import (  # type: ignore[import-untyped]
    format_recovery_code,
    hash_recovery_code,
    normalize_recovery_code,
)

RECOVERY_CODE_COUNT = 8
RECOVERY_CODE_PATTERN = re.compile(r"^[0-9a-f]{4}(?:-[0-9a-f]{4}){3}$")


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    return list(flexweek_engine.generate_recovery_codes(count, lambda: secrets.token_bytes(8)))


def recovery_code_matches(presented: str, stored_hash: str) -> bool:
    return flexweek_engine.recovery_code_matches(presented, stored_hash)


__all__ = [
    "RECOVERY_CODE_COUNT",
    "RECOVERY_CODE_PATTERN",
    "format_recovery_code",
    "generate_recovery_codes",
    "hash_recovery_code",
    "normalize_recovery_code",
    "recovery_code_matches",
]
