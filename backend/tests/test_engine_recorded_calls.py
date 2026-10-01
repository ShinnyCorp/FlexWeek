"""Replay arguments the existing backend tests passed to engine-backed functions."""

from __future__ import annotations

import importlib
import json
import time
from types import SimpleNamespace
from typing import Any

from backend.tests.engine_record import FIXTURE, decode

# initialize and throttle open the database at the path that was recorded. Replaying them
# writes under another run's temp directory. Part C's own tests cover those two.
# password_hash and generate_recovery_codes draw a fresh salt or code on each call, so the
# two copies cannot match.
SOLVER = {"solve", "reschedule_after_miss", "reschedule_running_late"}
SKIP = {
    ("storage", "initialize"),
    ("storage", "throttle"),
    ("storage", "password_hash"),
    ("recovery", "generate_recovery_codes"),
}


def _plain(value):
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump())
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items() if key != "solve_ms"}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


def _outcome(func, args, kwargs) -> tuple[str, object]:
    try:
        return ("ok", _plain(func(*args, **kwargs)))
    except Exception as error:
        return (type(error).__name__, str(error))


def _restore_deadline_tuples(kwargs: dict) -> None:
    """JSON stores tuples as lists. The original compares them as tuples and raises TypeError on a list."""
    for name in ("deadlines", "slack_deadlines"):
        raw = kwargs.get(name)
        if isinstance(raw, dict):
            kwargs[name] = {key: None if value is None else tuple(value) for key, value in raw.items()}


def test_recorded_backend_inputs_run_on_both_copies() -> None:
    assert FIXTURE.is_file(), "record backend/tests/test_*.py first"
    payload = json.loads(FIXTURE.read_text())
    calls = payload["calls"]
    assert calls, "recording is empty"
    modules = {call["module"] for call in calls}
    missing = sorted({"slots", "weeks", "explain"} - modules)
    assert missing == [], f"recording has no calls for {missing}"
    live_models = importlib.import_module("backend.models")
    ref_models = importlib.import_module("backend.tests.engine_ref.models")
    for call in calls:
        key = (call["module"], call["name"])
        if key in SKIP:
            continue
        kwargs = dict(call["kwargs"])
        _restore_deadline_tuples(kwargs)
        live: Any = importlib.import_module(f"backend.{call['module']}")
        ref: Any = importlib.import_module(f"backend.tests.engine_ref.{call['module']}")
        live_args = [decode(item, live_models) for item in call["args"]]
        live_kwargs = {name: decode(item, live_models) for name, item in kwargs.items()}
        ref_args = [decode(item, ref_models) for item in call["args"]]
        ref_kwargs = {name: decode(item, ref_models) for name, item in kwargs.items()}
        live_fn = getattr(live, call["name"])
        ref_fn = getattr(ref, call["name"])
        if call["name"] in SOLVER:
            # The search stops at 150 ms of wall time. Under a loaded gate the
            # Python copy can hit that and stop while the engine finishes.
            # Patch the name each module calls, not only the shared time module:
            # another test replaces backend.solver.time for the rest of the worker.
            frozen = time.perf_counter()

            def hold(instant: float = frozen) -> float:
                return instant

            fake = SimpleNamespace(perf_counter=hold)
            live_time = live.time
            ref_time = ref.time
            live.time = fake
            ref.time = fake
            try:
                live_out = _outcome(live_fn, live_args, live_kwargs)
                ref_out = _outcome(ref_fn, ref_args, ref_kwargs)
            finally:
                live.time = live_time
                ref.time = ref_time
        else:
            live_out = _outcome(live_fn, live_args, live_kwargs)
            ref_out = _outcome(ref_fn, ref_args, ref_kwargs)
        assert live_out == ref_out, f"{call['module']}.{call['name']}: {live_out} != {ref_out}"
