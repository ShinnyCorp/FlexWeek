"""Start-up migration: the Rust store against the original Python store, on the same stored rows."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from collections.abc import Callable
from contextlib import suppress
from itertools import count
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from backend import storage as live
from backend.tests.engine_ref import models as ref_models
from backend.tests.engine_ref import storage as ref
from backend.tests.test_engine_parity import block_dict, title

N = int(os.environ.get("AUDIT_EXAMPLES", "200"))
MONDAYS = ["2026-09-07", "2026-09-14", "2026-08-31"]

OLD_WEEKS = """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL
    );
    CREATE TABLE weeks (
        user_id INTEGER PRIMARY KEY REFERENCES users(id),
        blocks TEXT NOT NULL DEFAULT '[]',
        revision INTEGER NOT NULL DEFAULT 0
    );
"""


@st.composite
def old_block(draw: Any, ident: str) -> dict:
    body = draw(block_dict(ident=ident))
    # A body the model rejects stays as drawn: old rows were not all valid.
    with suppress(ValidationError):
        body = ref_models.TimeBlock.model_validate(body).model_dump()
    body.pop("assignment_id", None)
    odd = draw(st.integers(0, 9))
    if odd == 0:
        body["start"] = ""
    elif odd == 1:
        body["title"] = ""
    elif odd == 2:
        body["priority"] = None
    elif odd == 3:
        body["duration_min"] = float(body["duration_min"])
    elif odd == 4:
        body["pomodoro_parent_id"] = ""
    elif odd == 5:
        body["assignment_id"] = ""
    elif odd == 6:
        body["title"] = draw(title)
    return body


@st.composite
def old_weeks(draw: Any) -> list[tuple[int, str, list[dict]]]:
    weeks = []
    for user in draw(st.lists(st.integers(1, 2), min_size=1, max_size=2, unique=True)):
        for monday in draw(st.lists(st.sampled_from(MONDAYS), min_size=1, max_size=2, unique=True)):
            size = draw(st.integers(0, 5))
            weeks.append((user, monday, [draw(old_block(f"b{i}")) for i in range(size)]))
    return weeks


def dump(path: Path) -> dict:
    """Every table as stored, text included, and the schema."""
    db = sqlite3.connect(path)
    out: dict = {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        out[name] = [list(row) for row in db.execute(f"SELECT * FROM {name} ORDER BY 1, 2")]
    out["schema"] = [row[0] for row in db.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name")]
    db.close()
    return out


def outcome(call: Callable[[], object]) -> str:
    try:
        call()
        return "ok"
    except BaseException as error:
        return f"{type(error).__module__}.{type(error).__name__}: {error}"


def seeded(folder: Path, weeks: list[tuple[int, str, Any]]) -> tuple[Path, Path]:
    """Two copies of one database whose weeks hold `weeks`; a str is stored as it is, anything else as JSON."""
    seed, rust, python = folder / "seed.db", folder / "rust.db", folder / "py.db"
    for path in (seed, rust, python):
        path.unlink(missing_ok=True)
    ref.initialize(seed)
    db = sqlite3.connect(seed)
    for user in (1, 2):
        db.execute("INSERT INTO users(id, username, password_hash) VALUES (?, ?, 'x')", (user, f"u{user}"))
    for user, monday, blocks in weeks:
        text = blocks if isinstance(blocks, str) else json.dumps(blocks)
        db.execute("INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?, ?, ?, 3)", (user, monday, text))
    db.commit()
    db.close()
    shutil.copy(seed, rust)
    shutil.copy(seed, python)
    return rust, python


def assert_same_start(rust: Path, python: Path, label: str) -> None:
    got, want = outcome(lambda: live.initialize(rust)), outcome(lambda: ref.initialize(python))
    assert got == want, f"start-up differs\n {label}\n rust: {got}\n python: {want}"
    left, right = dump(rust), dump(python)
    for table in right:
        assert left.get(table) == right[table], (
            f"{table} differs\n {label}\n rust:   {json.dumps(left.get(table))[:1200]}\n python: {json.dumps(right[table])[:1200]}"
        )
    if want == "ok":
        # Each store opens the other's file, and a second start changes nothing.
        assert outcome(lambda: ref.initialize(rust)) == "ok"
        assert outcome(lambda: live.initialize(python)) == "ok"
        assert dump(rust) == left and dump(python) == right, "a second start by the other store changed rows"


RUNS = count()


@settings(max_examples=N, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
@given(weeks=old_weeks())
def test_leftover_blocks_migrate_to_the_same_rows(tmp_path_factory: pytest.TempPathFactory, weeks: list) -> None:
    folder = tmp_path_factory.mktemp(f"run{next(RUNS)}")
    rust, python = seeded(folder, weeks)
    assert_same_start(rust, python, f"weeks: {json.dumps(weeks)[:1500]}")
    shutil.rmtree(folder)


BASE = {"id": "b0", "title": "Essay", "kind": "flexible", "duration_min": 45, "days": [0], "priority": 2, "energy": "high", "start": "10:00", "completed": True}
CHUNK = {"id": "c0", "title": "Read", "kind": "locked", "duration_min": 25, "days": [1], "start": "16:00", "pomodoro_parent_id": "grp", "pomodoro_role": "work", "pomodoro_index": 1}


def without(block: dict, key: str) -> dict:
    return {k: v for k, v in block.items() if k != key}


ODD_ROWS: dict[str, Any] = {
    "plain flexible block": [BASE],
    "plain pomodoro group": [CHUNK],
    'start is ""': [{**BASE, "start": ""}],
    'title is ""': [{**BASE, "title": ""}],
    "title missing": [without(BASE, "title")],
    "priority and energy null": [{**BASE, "priority": None, "energy": None}],
    "duration 45.0 (float)": [{**BASE, "duration_min": 45.0}],
    'duration "45" (text)': [{**BASE, "duration_min": "45"}],
    "duration missing": [without(BASE, "duration_min")],
    "id is a number": [{**BASE, "id": 7}, {**BASE, "id": 8}],
    "id missing": [without(BASE, "id")],
    'assignment_id is ""': [{**BASE, "assignment_id": ""}],
    'pomodoro_parent_id is ""': [{**CHUNK, "pomodoro_parent_id": ""}],
    "pomodoro_parent_id is a number": [{**CHUNK, "pomodoro_parent_id": 5}],
    "days missing": [without(BASE, "days")],
    "completed_day far out of range": [{**BASE, "completed_day": 10**9}],
    "non-ASCII title": [{**BASE, "title": "Schöol 📖"}],
    "key with a quote": [{**BASE, 'odd"key': 1}],
    "focus_minutes null": [{**BASE, "focus_minutes": None}],
    'latest is "Friday 9pm"': [{**BASE, "completed": False, "latest": "Friday 9pm"}],
    "blocks is not a list": {"oops": 1},
    "blocks text is not JSON": "not json",
}


@pytest.mark.parametrize("label", list(ODD_ROWS))
def test_odd_stored_rows_migrate_as_the_python_store_did(tmp_path: Path, label: str) -> None:
    rust, python = seeded(tmp_path, [(1, "2026-09-07", ODD_ROWS[label])])
    assert_same_start(rust, python, label)


def test_the_single_week_table_migrates_the_same(tmp_path: Path) -> None:
    rust, python = tmp_path / "old-rust.db", tmp_path / "old-py.db"
    blocks = json.dumps([
        {"id": "hw", "title": "Essay", "kind": "flexible", "duration_min": 45, "days": [0, 2], "latest": "Friday 21:00"},
        {"id": "p1", "title": "Read", "kind": "locked", "duration_min": 25, "days": [1], "start": "16:00", "pomodoro_parent_id": "grp", "pomodoro_role": "work", "pomodoro_index": 1, "completed": True},
        {"id": "p2", "title": "Read", "kind": "locked", "duration_min": 5, "days": [1], "start": "16:25", "pomodoro_parent_id": "grp", "pomodoro_role": "break", "pomodoro_index": 1},
        {"id": "school", "title": "Schöol", "kind": "locked", "duration_min": 390, "days": [0, 1, 2, 3, 4], "start": "08:00"},
    ])
    for path in (rust, python):
        db = sqlite3.connect(path)
        db.executescript(OLD_WEEKS)
        db.execute("INSERT INTO users VALUES (1, 'legacy', 'scrypt$x')")
        db.execute("INSERT INTO weeks(user_id, blocks, revision) VALUES (1, ?, 4)", (blocks,))
        db.commit()
        db.close()
    # Both stamp the week with today's Monday.
    assert_same_start(rust, python, "the single-week table")
