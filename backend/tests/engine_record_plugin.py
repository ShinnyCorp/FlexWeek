"""Pytest plugin: wrap live engine-backed functions and write the recorded-calls fixture."""

from __future__ import annotations

from backend.tests.engine_record import dump, wrap_live_modules


def pytest_configure() -> None:
    wrap_live_modules()


def pytest_sessionfinish() -> None:
    dump()
