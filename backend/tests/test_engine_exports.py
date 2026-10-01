"""Every name the engine module exports must go through the export registry."""

from __future__ import annotations

import inspect

import flexweek_engine  # type: ignore[import-untyped]


def _exported_functions() -> set[str]:
    names: set[str] = set()
    for name in dir(flexweek_engine):
        value = getattr(flexweek_engine, name)
        if name.startswith("_") or inspect.isclass(value):
            continue
        if callable(value):
            names.add(name)
    return names


def test_every_exported_function_went_through_export() -> None:
    registered = set(flexweek_engine.guarded_names())
    missing = sorted(_exported_functions() - registered)
    assert missing == [], f"exported without the export registry: {missing}"


def test_every_pyfunction_body_calls_guard() -> None:
    """export! records the name. This checks the body actually calls guard."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "engine" / "py" / "src"
    missing: list[str] = []
    for path in sorted(root.glob("*.rs")):
        for name, body in _pyfunctions(path.read_text()):
            if "guard(" not in body:
                missing.append(f"{path.name} {name}")
    assert missing == [], f"pyfunction without guard: {missing}"


def _pyfunctions(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for part in text.split("#[pyfunction]")[1:]:
        marker = part.find("fn ")
        if marker < 0:
            continue
        name_start = marker + 3
        name_end = name_start
        while name_end < len(part) and (part[name_end].isalnum() or part[name_end] == "_"):
            name_end += 1
        name = part[name_start:name_end]
        brace = part.find("{", name_end)
        if brace < 0:
            continue
        depth = 0
        for index in range(brace, len(part)):
            if part[index] == "{":
                depth += 1
            elif part[index] == "}":
                depth -= 1
                if depth == 0:
                    found.append((name, part[brace : index + 1]))
                    break
    return found
