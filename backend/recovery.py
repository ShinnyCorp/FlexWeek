"""One-time recovery codes. The engine formats and hashes them. No HTTP, no database."""

from __future__ import annotations

import hmac
import re
import secrets

from flexweek_engine import (  # type: ignore[import-untyped]
    format_recovery_code,
    hash_recovery_code,
    normalize_recovery_code,
)

RECOVERY_CODE_COUNT = 8
RECOVERY_CODE_PATTERN = re.compile(r"^[0-9a-f]{4}(?:-[0-9a-f]{4}){3}$")


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    while len(codes) < count:
        code = format_recovery_code(secrets.token_hex(8))
        digest = hash_recovery_code(code)
        if digest in seen or not RECOVERY_CODE_PATTERN.fullmatch(code):
            continue
        seen.add(digest)
        codes.append(code)
    return codes


def recovery_code_matches(presented: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_recovery_code(presented), stored_hash)


__all__ = [
    "RECOVERY_CODE_COUNT",
    "RECOVERY_CODE_PATTERN",
    "format_recovery_code",
    "generate_recovery_codes",
    "hash_recovery_code",
    "normalize_recovery_code",
    "recovery_code_matches",
]
