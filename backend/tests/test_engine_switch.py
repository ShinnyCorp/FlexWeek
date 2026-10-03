"""The engine's password hash, on fixed vectors."""

from __future__ import annotations

import hashlib

import flexweek_engine  # type: ignore[import-untyped]


def test_store_hash_vectors():
    assert flexweek_engine.digest("flexweek") == hashlib.sha256(b"flexweek").hexdigest()
    encoded = "scrypt$32768$8$3$00112233445566778899aabbccddeeff$acfa1ad8d5c639d068e6988715f03dd7b1acdb99c998707b1632762596fd2b16"
    assert flexweek_engine.password_hash("secret", "00112233445566778899aabbccddeeff") == encoded
    assert flexweek_engine.password_matches("secret", encoded) is True
    assert flexweek_engine.password_matches("other", encoded) is False
