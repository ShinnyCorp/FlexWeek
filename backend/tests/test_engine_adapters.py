"""Wrappers that are not listed as STAYS or LOGIC in docs/engine/adapters.md stay free of engine logic."""

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
DESKTOP_MODULES = (
    "calendar",
    "custom_look",
    "files",
    "focus",
    "history",
    "pomodoro",
    "remind",
    "reuse",
    "tokens",
    "update",
    "version",
    "weekmodel",
)
# look.py still paints. Only the four helpers that call the engine are wrappers.
LOOK_HELPERS = (
    "known_pack",
    "sanitize_custom",
    "sanitize_look",
    "effective_look",
)
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


def names_from_doc(*kinds: str) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for line in ADAPTERS.read_text().splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[2] not in kinds:
            continue
        found.setdefault(cells[0], set()).add(cells[1])
    return found


def _is_class(name: str) -> bool:
    return name.rsplit(".", 1)[-1][:1].isupper()


def is_stays(names: set[str], qual: str) -> bool:
    """A listed function, and functions nested inside it.

    A class listed as STAYS is the definition. Its methods are classified on their own rows, so the
    class name does not exempt them. Nested functions under a listed function still are.
    """
    parts = qual.split(".")
    for end in range(1, len(parts) + 1):
        prefix = ".".join(parts[:end])
        if prefix in names and not _is_class(prefix):
            return True
    return False


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


def is_type_test(node: ast.Call) -> bool:
    func = node.func
    return isinstance(func, ast.Name) and func.id in {"isinstance", "type"}


def is_truth_test(node: ast.expr) -> bool:
    """`if name` or `if obj.attr`: the value's own truth, not a comparison."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        node = node.operand
    return isinstance(node, (ast.Name, ast.Attribute))


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
        elif isinstance(item, ast.Call) and is_type_test(item):
            kind = "type test"
        elif isinstance(item, ast.BoolOp):
            kind = "default"
        elif isinstance(item, ast.IfExp):
            kind = "branch"
        elif isinstance(item, (ast.If, ast.While)) and is_truth_test(item.test):
            kind = "truth test"
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


# The stricter shapes (a type test, `x or default`, a conditional expression, a truth test) already
# sit in these wrappers. Each line names the shape. A new shape, or an older one (a loop, arithmetic,
# a comparison, a sort), is not listed and still fails.
ALLOWED_FOR_NOW = {
    ("assignments.prepare_solve", "branch"),  # a missing deadline stays None while decoding
    ("availability.resolve_work_windows", "branch"),  # None windows stay None on the way in
    ("solver._points", "branch"),  # a missing point stays None while encoding
    ("calendar.apply_block_times", "branch"),  # the engine's None answer stays None
    ("calendar.relocate_block", "branch"),  # None dest in, None answer out
    ("calendar.placement_on", "branch"),  # None trace in; the engine's flag becomes NOT_TODAY
    ("calendar.agenda_for", "branch"),  # None trace and day data stay None on the way in
    ("calendar.next_action_for", "branch"),  # None day data stays None on the way in
    ("calendar.span_problem", "type test"),  # the engine is told the due value's Python type
    ("custom_look._text_or_none", "branch"),  # text stays, anything else becomes None
    ("custom_look._text_or_none", "type test"),
    ("custom_look._name", "branch"),  # a non-text name is none for the engine
    ("custom_look._name", "type test"),
    ("custom_look.sanitize_saved", "branch"),  # a non-list file is an empty list
    ("custom_look.sanitize_saved", "type test"),
    ("custom_look.save_look", "branch"),  # a non-text name is an empty string
    ("custom_look.save_look", "type test"),
    ("custom_look.free_name", "branch"),  # a non-text name is an empty string
    ("custom_look.free_name", "type test"),
    ("custom_look.rename_look", "branch"),  # a non-text name is an empty string
    ("custom_look.rename_look", "type test"),
    ("focus.persist_payload", "branch"),  # the engine's None answer stays None
    ("focus.restore_state", "branch"),  # the engine's None answer stays None
    ("focus.credit_target", "branch"),  # the engine's None answer stays None
    ("history.capture_step", "branch"),  # the engine's None answer stays None
    ("reuse.apply_plan", "branch"),  # None targets and assignments stay None on the way in
    ("reuse.due_point", "branch"),  # the engine's None answer stays None
    ("reuse.block_occurs_on_day", "branch"),  # None placed blocks stay None on the way in
    ("reuse.row_conflict", "branch"),  # the engine's None answer stays None
    ("update.available", "branch"),  # the engine's None answer stays None
    ("update.release_from_page", "branch"),  # the engine's None answer stays None
    ("weekmodel.WeekModel._engine", "default"),  # either tuple missing skips the handle cache
    ("weekmodel.WeekModel._engine", "type test"),
    ("weekmodel.WeekModel.on_day", "default"),  # either tuple missing skips the day cache
    ("weekmodel.WeekModel.on_day", "type test"),
    ("weekmodel.WeekModel.load_min", "default"),  # either tuple missing skips the load cache
    ("weekmodel.WeekModel.load_min", "type test"),
    ("weekmodel.WeekModel.day_queue", "branch"),  # no current block stays None
    ("app.adopt_legacy_deadlines", "truth test"),  # the engine's "over the cap" becomes the 422
    ("app.require_own_assignments", "truth test"),  # the engine's "not owned" becomes the 422
    ("app.insert_restore_point", "default"),  # a missing keep-set is an empty list
}


def problem_key(problem: str) -> tuple[str, str]:
    name = problem.split(":", 1)[0]
    kind = problem.rsplit("(", 1)[-1].removesuffix(")")
    return name, kind


def test_wrappers_keep_no_engine_logic() -> None:
    # LOGIC is a leftover the table names (custom_look.readability). LOGIC, moved is not exempt.
    exempt = names_from_doc("STAYS", "LOGIC")
    problems: list[str] = []
    modules = [(name, ROOT / "backend" / f"{name}.py") for name in BACKEND_MODULES]
    modules += [(name, ROOT / "desktop" / "native" / f"{name}.py") for name in DESKTOP_MODULES]
    for name, path in modules:
        tree = ast.parse(path.read_text(), filename=str(path))
        for problem in functions_of(tree, exempt.get(name, set())):
            problems.append(f"{name}.{problem}")
    look_path = ROOT / "desktop" / "native" / "look.py"
    look_tree = ast.parse(look_path.read_text(), filename=str(look_path))
    assert isinstance(look_tree, ast.Module)
    listed = {
        node.name: node
        for node in look_tree.body
        if isinstance(node, ast.FunctionDef) and node.name in LOOK_HELPERS
    }
    missing = set(LOOK_HELPERS) - listed.keys()
    assert not missing, f"look.py no longer defines: {sorted(missing)}"
    for name in LOOK_HELPERS:
        for problem in logic_in(listed[name], name, set()):
            problems.append(f"look.{problem}")
    problems = [problem for problem in problems if problem_key(problem) not in ALLOWED_FOR_NOW]
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
    problems = [problem for problem in problems if problem_key(problem) not in ALLOWED_FOR_NOW]
    assert not problems, "\n".join(problems)
