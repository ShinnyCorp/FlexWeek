"""Record arguments the existing backend tests pass to engine-backed functions."""

from __future__ import annotations

import importlib
import inspect
import json
from collections.abc import Callable
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Any

REPLACED = (
    "assignments",
    "availability",
    "comfort",
    "day",
    "explain",
    "month",
    "recovery",
    "restore",
    "slots",
    "solver",
    "storage",
    "transfer",
    "weeks",
)

SKIP_NAMES = {
    "connect",
    "create_session",
    "delete_account",
    "new_preferences",
}

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "engine_recorded_calls.json"

_records: dict[str, dict[str, Any]] = {}
_skipped: list[dict[str, Any]] = []


def fixture_path() -> Path:
    return FIXTURE


def _is_function(value: Any) -> bool:
    """Engine re-exports are builtin callables, not Python functions."""
    return callable(value) and not inspect.isclass(value) and not inspect.ismodule(value)


def encode(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, bytes):
        return {"__type__": "bytes", "hex": value.hex()}
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, Path):
        return {"__type__": "path", "value": str(value)}
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return {
            "__type__": "model",
            "class": type(value).__name__,
            "value": encode(value.model_dump()),
        }
    if isinstance(value, dict):
        return {str(key): encode(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [encode(item) for item in value]
    raise TypeError(type(value).__name__)


def decode(value: Any, models: Any) -> Any:
    if isinstance(value, dict) and "__type__" in value:
        kind = value["__type__"]
        if kind == "date":
            return date.fromisoformat(value["value"])
        if kind == "datetime":
            return datetime.fromisoformat(value["value"])
        if kind == "path":
            return Path(value["value"])
        if kind == "bytes":
            return bytes.fromhex(value["hex"])
        if kind == "model":
            cls = getattr(models, value["class"])
            return cls(**decode(value["value"], models))
        raise ValueError(kind)
    if isinstance(value, dict):
        return {key: decode(item, models) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item, models) for item in value]
    return value


def wrap_live_modules() -> None:
    for name in REPLACED:
        live = importlib.import_module(f"backend.{name}")
        ref = importlib.import_module(f"backend.tests.engine_ref.{name}")
        for func_name, func in inspect.getmembers(live):
            if func_name.startswith("_") or func_name in SKIP_NAMES:
                continue
            if not _is_function(func) or not _is_function(getattr(ref, func_name, None)):
                continue
            setattr(live, func_name, _recorder(name, func_name, func))


def dump() -> None:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "calls": sorted(_records.values(), key=lambda item: (item["module"], item["name"], item["key"])),
        "skipped": _skipped,
    }
    FIXTURE.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")


def _recorder(module: str, name: str, func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            encoded_args = [encode(item) for item in args]
            encoded_kwargs = {key: encode(item) for key, item in kwargs.items()}
        except TypeError as error:
            _skipped.append(
                {
                    "module": module,
                    "name": name,
                    "reason": str(error),
                }
            )
            return func(*args, **kwargs)
        key = json.dumps({"args": encoded_args, "kwargs": encoded_kwargs}, sort_keys=True, default=str)
        _records[f"{module}.{name}:{key}"] = {
            "key": key,
            "module": module,
            "name": name,
            "args": encoded_args,
            "kwargs": encoded_kwargs,
        }
        return func(*args, **kwargs)

    return wrapped
