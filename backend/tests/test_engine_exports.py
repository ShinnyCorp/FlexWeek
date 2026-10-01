"""Every name the engine module exports must go through the export registry."""

from __future__ import annotations

import flexweek_engine  # type: ignore[import-untyped]


def _exported_functions() -> set[str]:
    names: set[str] = set()
    for name in dir(flexweek_engine):
        if name.startswith("_"):
            continue
        value = getattr(flexweek_engine, name)
        if callable(value):
            names.add(name)
    return names


def test_every_exported_function_is_in_the_guard_registry() -> None:
    registered = set(flexweek_engine.guarded_names())
    missing = sorted(_exported_functions() - registered)
    assert missing == [], f"exported without the export registry: {missing}"
