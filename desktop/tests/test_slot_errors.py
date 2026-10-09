"""An error inside a Qt slot fails the test that caused it (0.18.5).

Qt prints it through sys.excepthook and carries on, so a test stayed green over the plan bar's layout
error for weeks. conftest.py records the calls and fails the test; a marker that names the reason
lets one test off.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

pytest_plugins = ["pytester"]

RAISES = """
import pytest
from PySide6.QtCore import QObject, Signal


class Source(QObject):
    fired = Signal()


def raise_in_a_slot():
    source = Source()
    source.fired.connect(lambda: 1 / 0)
    source.fired.emit()
"""


def run_with_the_hook(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, test: str
) -> pytest.RunResult:
    """A session of its own: in this one, the hook of the test running would be handed the error."""
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parents[2]))
    pytester.makeconftest(Path(__file__).with_name("conftest.py").read_text())
    pytester.makepyfile(RAISES + test)
    return pytester.runpytest_subprocess("-p", "no:cacheprovider")


def test_an_error_in_a_slot_fails_the_test(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_with_the_hook(pytester, monkeypatch, "\ndef test_it():\n    raise_in_a_slot()\n")
    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(["*an error was raised inside a Qt slot*", "*ZeroDivisionError*"])


def test_a_marker_with_a_reason_lets_the_test_off(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    reason = '"the slot divides by zero"'
    test = f"\n@pytest.mark.slot_errors_allowed({reason})\ndef test_it():\n    raise_in_a_slot()\n"
    run_with_the_hook(pytester, monkeypatch, test).assert_outcomes(passed=1)


def test_a_marker_without_a_reason_is_refused(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    test = "\n@pytest.mark.slot_errors_allowed\ndef test_it():\n    raise_in_a_slot()\n"
    run_with_the_hook(pytester, monkeypatch, test).assert_outcomes(errors=1)
