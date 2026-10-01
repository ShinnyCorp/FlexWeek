"""Guarantee 7: another thread waits no longer during a full-budget solve than it did in Python."""

from __future__ import annotations

import threading
import time

from backend import models as live_models
from backend import solver as live_solver
from backend.tests.engine_ref import models as ref_models
from backend.tests.engine_ref import solver as ref_solver

# School fills Monday; nine two-hour pieces cannot all fit, so the search spends the 150 ms budget.
WEEK = [
    {
        "id": "school",
        "title": "School",
        "kind": "locked",
        "days": [0, 1, 2, 3, 4],
        "start": "08:00",
        "duration_min": 420,
    }
] + [
    {
        "id": f"hw{i}",
        "title": f"H{i}",
        "kind": "flexible",
        "days": [0],
        "duration_min": 120,
        "priority": 1 + i % 3,
        "latest": "Monday 21:00",
    }
    for i in range(9)
]


def _longest_wait(module, models) -> float:
    gaps: list[float] = []
    stop = False

    def beat() -> None:
        last = time.perf_counter()
        while not stop:
            time.sleep(0.001)
            now = time.perf_counter()
            gaps.append((now - last) * 1000)
            last = now

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    time.sleep(0.05)
    gaps.clear()
    module.solve([models.TimeBlock(**block) for block in WEEK])
    time.sleep(0.02)
    stop = True
    thread.join()
    return max(gaps)


def test_another_thread_waits_no_longer_than_under_the_python_solver() -> None:
    python_waits = [_longest_wait(ref_solver, ref_models) for _ in range(3)]
    rust_waits = [_longest_wait(live_solver, live_models) for _ in range(3)]
    assert max(rust_waits) <= max(python_waits) + 2.0, (
        f"rust waited {max(rust_waits):.1f} ms; python waited {max(python_waits):.1f} ms"
    )
