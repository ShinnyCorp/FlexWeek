from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Blocks one module by setting it to None in sys.modules, which makes its import raise, then runs
# the app's entry point the way `python -m desktop.main` does.
RUN_WITH_BLOCKED = """
import runpy, sys
sys.modules[{module!r}] = None
runpy.run_module("desktop.main", run_name="__main__")
"""


@pytest.mark.parametrize("module", ["PySide6", "flexweek_engine"])
def test_a_part_that_fails_to_import_gives_one_plain_message_not_a_traceback(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", RUN_WITH_BLOCKED.format(module=module)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 1, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "FlexWeek could not start because a part it needs did not load" in result.stderr
    assert module in result.stderr
