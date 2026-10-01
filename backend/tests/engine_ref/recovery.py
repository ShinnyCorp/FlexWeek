"""One-time recovery codes. No HTTP, no database."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

RECOVERY_CODE_COUNT = 8
RECOVERY_CODE_PATTERN = re.compile(r"^[0-9a-f]{4}(?:-[0-9a-f]{4}){3}$")


def normalize_recovery_code(value: str) -> str:
    return re.sub(r"[^0-9a-fA-F]", "", value).lower()


def hash_recovery_code(value: str) -> str:
    return hashlib.sha256(b"flexweek-recovery:" + normalize_recovery_code(value).encode()).hexdigest()


def format_recovery_code(raw_hex: str) -> str:
    return f"{raw_hex[:4]}-{raw_hex[4:8]}-{raw_hex[8:12]}-{raw_hex[12:]}"


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    while len(codes) < count:
        code = format_recovery_code(secrets.token_hex(8))
        digest = hash_recovery_code(code)
        if digest in seen:
            continue
        if not RECOVERY_CODE_PATTERN.fullmatch(code):
            continue
        seen.add(digest)
        codes.append(code)
    return codes


def recovery_code_matches(presented: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_recovery_code(presented), stored_hash)
