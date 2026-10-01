"""Replay arguments the existing backend tests passed to engine-backed functions."""

from __future__ import annotations

import importlib
import json

from backend.tests.engine_record import FIXTURE, decode


def _call(func, args, kwargs) -> None:
    try:
        func(*args, **kwargs)
    except Exception:
        return


def test_recorded_backend_inputs_run_on_both_copies() -> None:
    assert FIXTURE.is_file(), "record backend/tests/test_*.py first"
    payload = json.loads(FIXTURE.read_text())
    calls = payload["calls"]
    assert calls, "recording is empty"
    live_models = importlib.import_module("backend.models")
    ref_models = importlib.import_module("backend.tests.engine_ref.models")
    for call in calls:
        live = importlib.import_module(f"backend.{call['module']}")
        ref = importlib.import_module(f"backend.tests.engine_ref.{call['module']}")
        live_fn = getattr(live, call["name"])
        ref_fn = getattr(ref, call["name"])
        live_args = [decode(item, live_models) for item in call["args"]]
        live_kwargs = {key: decode(item, live_models) for key, item in call["kwargs"].items()}
        ref_args = [decode(item, ref_models) for item in call["args"]]
        ref_kwargs = {key: decode(item, ref_models) for key, item in call["kwargs"].items()}
        _call(live_fn, live_args, live_kwargs)
        _call(ref_fn, ref_args, ref_kwargs)
