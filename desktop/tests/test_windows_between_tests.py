"""What one test leaves on screen for the next, run in a pytest of its own so the order is known."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

ROOT = Path(__file__).resolve().parents[2]

TESTS = '''
import pytest
from PySide6.QtWidgets import QApplication, QWidget

APP = QApplication.instance() or QApplication(["flexweek-windows-between-tests"])
# Held here as a view's own signals hold it, so the window outlives the test that showed it.
KEPT = []


@pytest.fixture(scope="module")
def board():
    shown = QWidget()
    shown.setObjectName("board")
    shown.show()
    yield shown
    shown.hide()


def showing():
    return sorted(window.objectName() for window in QApplication.topLevelWidgets() if window.isVisible())


def test_a_view_shown_on_its_own_is_left_showing(board):
    view = QWidget()
    view.setObjectName("stray")
    view.resize(1366, 760)
    view.show()
    KEPT.append(view)
    assert showing() == ["board", "stray"]


def test_the_next_test_finds_only_what_its_module_opened(board):
    assert showing() == ["board"]
'''


def test_a_window_one_test_leaves_showing_is_gone_before_the_next(tmp_path: Path) -> None:
    """Views left showing lay over later tests' windows, and a drag dropped on one of them instead."""
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_left.py").write_text(TESTS)
    env = {name: value for name, value in os.environ.items() if not name.startswith("PYTEST_")}
    env.update(PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen", FLEXWEEK_SILENT="1")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "desktop.tests.conftest",
         "-c", str(tmp_path / "pytest.ini"), str(tmp_path / "test_left.py")],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
    assert "2 passed" in result.stdout


def test_where_one_test_leaves_the_pointer_does_not_take_hover_from_the_next() -> None:
    """Clay's arrow test leaves the pointer over its view, which lives on hidden; the sign-in test's move
    onto Forgot password after it showed no hover. Run in that order, in one pytest of its own."""
    env = {name: value for name, value in os.environ.items() if not name.startswith("PYTEST_")}
    env.update(QT_QPA_PLATFORM="offscreen", FLEXWEEK_SILENT="1")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist",
         "desktop/tests/test_layout_clay.py::test_a_block_held_on_an_arrow_slides_the_row_to_the_next_day",
         "desktop/tests/test_sign_in_card.py::test_a_link_in_reach_keeps_the_accent_darker_and_underlined"
         "[pointer-forgotPassword]"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
    assert "2 passed" in result.stdout
