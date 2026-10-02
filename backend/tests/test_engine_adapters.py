"""Wrappers that are not listed as STAYS in docs/engine/adapters.md stay free of engine logic."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_MODULES = (
    "assignments",
    "availability",
    "comfort",
    "day",
    "explain",
    "limits",
    "month",
    "recovery",
    "restore",
    "slots",
    "solver",
    "storage",
    "transfer",
    "weeks",
)
DESKTOP_MODULES: tuple[str, ...] = ()
APP_MODULES = ("app",)
# The helper functions of backend/app.py that hold no HTTP: route handlers and the functions that
# map an engine status onto an HTTP error are not listed and are not checked.
APP_HELPERS = (
    "adopt_legacy_deadlines",
    "encode_new_assignment",
    "rewrite_blocks",
    "normalize_stored_block",
    "rewrite_stored_blocks",
    "assignment_view",
    "require_own_assignments",
    "payload_digest",
    "insert_restore_point",
    "preferences_from_row",
    "validate_windows",
    "solve_availability",
)

ROOT = Path(__file__).resolve().parents[2]
ADAPTERS = ROOT / "docs" / "engine" / "adapters.md"


def stays_from_doc() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for line in ADAPTERS.read_text().splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[2] != "STAYS":
            continue
        found.setdefault(cells[0], set()).add(cells[1])
    return found


def is_stays(names: set[str], qual: str) -> bool:
    parts = qual.split(".")
    return any(".".join(parts[:end]) in names for end in range(1, len(parts) + 1))


def is_none_check(node: ast.Compare) -> bool:
    if len(node.ops) != 1 or len(node.comparators) != 1:
        return False
    if not isinstance(node.ops[0], (ast.Is, ast.IsNot)):
        return False
    other = node.comparators[0]
    return isinstance(other, ast.Constant) and other.value is None


def is_sort(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name) and func.id == "sorted":
        return True
    return isinstance(func, ast.Attribute) and func.attr == "sort"


def logic_in(node: ast.AST, qual: str, stays: set[str]) -> list[str]:
    problems: list[str] = []

    def walk(item: ast.AST) -> None:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nested = f"{qual}.{item.name}"
            if not is_stays(stays, nested):
                problems.extend(logic_in(item, nested, stays))
            return
        if isinstance(item, ast.Lambda):
            walk(item.body)
            return
        kind = None
        if isinstance(item, (ast.For, ast.While, ast.AsyncFor)):
            kind = "loop"
        elif isinstance(item, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)) and any(
            gen.ifs for gen in item.generators
        ):
            kind = "comprehension"
        elif isinstance(item, (ast.BinOp, ast.AugAssign)):
            kind = "arithmetic"
        elif isinstance(item, ast.Compare) and not is_none_check(item):
            kind = "comparison"
        elif isinstance(item, ast.Call) and is_sort(item):
            kind = "sort"
        if kind is not None:
            problems.append(
                f"{qual}: logic belongs in the engine: see docs/engine/adapters.md ({kind})"
            )
        for child in ast.iter_child_nodes(item):
            walk(child)

    body = node.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else [node]
    for stmt in body:
        walk(stmt)
    return problems


def functions_of(tree: ast.AST, stays: set[str]) -> list[str]:
    problems: list[str] = []

    def scan(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                scan(node.body, f"{prefix}{node.name}.")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}{node.name}"
                if not is_stays(stays, qual):
                    problems.extend(logic_in(node, qual, stays))

    if isinstance(tree, ast.Module):
        scan(tree.body, "")
    return problems


def test_wrappers_keep_no_engine_logic() -> None:
    stays = stays_from_doc()
    problems: list[str] = []
    modules = [(name, ROOT / "backend" / f"{name}.py") for name in BACKEND_MODULES]
    modules += [(name, ROOT / "desktop" / f"{name}.py") for name in DESKTOP_MODULES]
    for name, path in modules:
        tree = ast.parse(path.read_text(), filename=str(path))
        for problem in functions_of(tree, stays.get(name, set())):
            problems.append(f"{name}.{problem}")
    assert not problems, "\n".join(problems)


def test_app_helpers_keep_no_engine_logic() -> None:
    path = ROOT / "backend" / f"{APP_MODULES[0]}.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    assert isinstance(tree, ast.Module)
    listed = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in APP_HELPERS
    }
    missing = set(APP_HELPERS) - listed.keys()
    assert not missing, f"app.py no longer defines: {sorted(missing)}"
    problems: list[str] = []
    for name in APP_HELPERS:
        problems.extend(f"app.{problem}" for problem in logic_in(listed[name], name, set()))
    assert not problems, "\n".join(problems)
