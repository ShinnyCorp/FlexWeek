"""Add and Edit homework, #37 as option B of the 0.18.3 mock-up: under Estimated time, "In one go" or
"Spread over days" as a choice of the homework, with a grey line saying what Plan will do with the values
as they stand now. It replaces the Spread button at the bottom of More details."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from desktop.native.widgets import HomeworkDialog
from desktop.tests.window_support import free, qapp  # noqa: F401

TODAY = "2026-09-14"
NOON = datetime(2026, 9, 14, 12, 0)


def host(*blocks: dict, selected_day: str = "") -> QWidget:
    parent = QWidget()
    parent.session = SimpleNamespace(  # type: ignore[attr-defined]
        now_ms=lambda: int(NOON.timestamp() * 1000),
        blocks=list(blocks),
        week_start=TODAY,
        selected_day=selected_day,
    )
    return parent


def essay(**more: object) -> dict:
    return {
        "id": "essay",
        "title": "History essay",
        "due": "2026-09-20",
        "estimate_min": 120,
        "category": "assignments",
        "revision": 0,
        **more,
    }


def waiting(day: int, start: str | None = None) -> dict:
    return {
        "id": f"s{day}",
        "title": "History essay",
        "kind": "flexible",
        "assignment_id": "essay",
        "duration_min": 60,
        "days": [day],
        **({"start": start} if start else {}),
    }


def opened(parent: QWidget, assignment: dict | None = None, **more: object) -> HomeworkDialog:
    dialog = HomeworkDialog(parent, assignment, TODAY, **more)
    dialog.show()
    QApplication.processEvents()
    return dialog


def spread(dialog: HomeworkDialog) -> None:
    dialog.spread_choice.setCurrentIndex(1)


def test_the_choice_is_shown_from_60_minutes_up_in_add_and_in_edit(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    for assignment in (None, essay()):
        dialog = opened(parent, assignment)
        assert dialog.spread_choice.isVisible()
        assert not dialog.spread_line.isVisible(), "the line says what Spread will do, not one go"
        spread(dialog)
        assert dialog.spread_line.isVisible()
        dialog.spread_choice.setCurrentIndex(0)
        assert [dialog.spread_choice.itemText(i) for i in range(2)] == ["In one go", "Spread over days"]
        assert dialog.spread_choice.currentData() == "one", "one go is today's behaviour"
        dialog.estimate.setValue(45)
        assert not dialog.spread_choice.isVisible() and not dialog.spread_line.isVisible()
        dialog.estimate.setValue(60)
        assert dialog.spread_choice.isVisible()
        free(dialog)
    free(parent)


def test_an_estimate_that_drops_below_60_means_one_go_again(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent, essay())
    dialog.title.setText("History essay")
    spread(dialog)
    dialog.estimate.setValue(45)
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert not dialog.spread_requested()
    free(dialog)
    free(parent)


def test_the_choice_is_called_sessions_and_the_old_button_is_gone(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent, essay())
    dialog.more_details.click()
    assert dialog.findChild(QPushButton, "spreadHomework") is None
    assert "Spread across days" not in [button.text() for button in dialog.findChildren(QPushButton)]
    labels = [label.text() for label in dialog.findChildren(QLabel) if label.objectName() == "fieldLabel"]
    assert "Sessions" in labels
    free(dialog)
    free(parent)


def test_the_grey_line_says_what_plan_will_do_before_the_due(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent, essay())
    spread(dialog)
    assert dialog.spread_line.text() == "2 × 60 min on different days before it is due Sun 20 Sep."
    free(dialog)
    free(parent)


def test_the_line_follows_the_values_not_yet_saved(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent, essay())
    spread(dialog)
    dialog.estimate.setValue(180)
    assert dialog.spread_line.text() == "3 × 60 min on different days before it is due Sun 20 Sep."
    dialog.estimate.setValue(90)
    assert dialog.spread_line.text() == "60 min and 30 min on different days before it is due Sun 20 Sep."
    dialog.due.date.setDate(QDate(2026, 9, 18))
    assert dialog.spread_line.text().endswith("before it is due Fri 18 Sep.")
    dialog.due.timed.setChecked(True)
    assert dialog.spread_line.text().endswith("before it is due Fri 18 Sep, 15:00.")
    free(dialog)
    free(parent)


def test_sessions_beyond_the_days_left_share_days_and_the_line_says_so(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent, essay(due="2026-09-15"), )
    spread(dialog)
    dialog.estimate.setValue(240)
    assert dialog.spread_line.text() == "4 × 60 min over 2 days before it is due Tue 15 Sep."
    dialog.due.date.setDate(QDate(2026, 9, 14))
    assert dialog.spread_line.text() == "4 × 60 min on the same day before it is due Mon 14 Sep."
    free(dialog)
    free(parent)


def test_edit_spreads_only_what_focus_has_not_already_covered(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent, essay(estimate_min=240, focus_minutes=60))
    spread(dialog)
    assert dialog.spread_line.text() == "3 × 60 min on different days before it is due Sun 20 Sep."
    dialog.estimate.setValue(300)
    assert dialog.spread_line.text() == "4 × 60 min on different days before it is due Sun 20 Sep."
    free(dialog)
    free(parent)


def test_a_time_picked_by_hand_is_one_time_so_the_choice_waits_for_flexweek_to_pick(
    qapp: QApplication,  # noqa: F811
) -> None:
    parent = host(waiting(3, "19:00") | {"pinned": True})
    dialog = opened(parent, essay())
    assert dialog.when.currentData() == "fixed", "placed by hand"
    assert not dialog.spread_choice.isVisible()
    dialog.when.setCurrentIndex(0)
    assert dialog.spread_choice.isVisible()
    spread(dialog)
    dialog.when.setCurrentIndex(1)
    assert not dialog.spread_choice.isVisible()
    assert dialog.spread_choice.currentData() == "one", "hidden means one go"
    free(dialog)
    free(parent)


def test_the_days_start_at_the_day_on_screen_when_it_is_ahead(qapp: QApplication) -> None:  # noqa: F811
    parent = host(selected_day="2026-09-19")
    dialog = opened(parent, essay(estimate_min=180))
    spread(dialog)
    # Sat 19 and Sun 20: three sessions, two days.
    assert dialog.spread_line.text() == "3 × 60 min over 2 days before it is due Sun 20 Sep."
    assert dialog.spread_plan() == {"session_min": 60, "from_date": "2026-09-19"}
    free(dialog)
    free(parent)


def test_saving_with_spread_hands_the_unsaved_values_and_the_plan_to_the_window(
    qapp: QApplication,  # noqa: F811
) -> None:
    parent = host()
    dialog = opened(parent)
    dialog.title.setText("Science project")
    dialog.estimate.setValue(180)
    dialog.due.date.setDate(QDate(2026, 9, 18))
    spread(dialog)
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert dialog.spread_requested()
    saved = dialog.assignment()
    assert (saved["title"], saved["estimate_min"], saved["due"]) == ("Science project", 180, "2026-09-18")
    assert dialog.spread_plan() == {"session_min": 60, "from_date": TODAY}
    free(dialog)
    free(parent)


def test_one_go_saves_as_it_always_did(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent)
    dialog.title.setText("Science project")
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert not dialog.spread_requested()
    free(dialog)
    free(parent)


def test_homework_that_already_has_several_times_shows_no_choice(qapp: QApplication) -> None:  # noqa: F811
    parent = host(waiting(1, "15:00"), waiting(2, "15:00"))
    dialog = opened(parent, essay())
    assert not dialog.spread_choice.isVisible() and not dialog.spread_line.isVisible()
    free(dialog)
    free(parent)


def tab_chain(dialog: HomeworkDialog, steps: int = 14) -> list[QWidget]:
    dialog.estimate.setFocus()
    seen = [dialog.focusWidget()]
    for _ in range(steps):
        dialog.focusNextChild()
        seen.append(dialog.focusWidget())
    return seen


def test_the_choice_comes_after_estimated_time_in_the_tab_order(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent, essay())
    chain = tab_chain(dialog)
    first_segment = dialog.spread_choice.buttons()[0]
    assert dialog.estimate in chain
    assert chain.index(dialog.estimate) < chain.index(first_segment) < chain.index(dialog.completed)
    # Back from Finished, the way the keyboard goes up: the choice is the stop before it.
    dialog.completed.setFocus()
    dialog.focusPreviousChild()
    assert dialog.focusWidget() in dialog.spread_choice.buttons()
    assert Qt.FocusPolicy.NoFocus not in {button.focusPolicy() for button in dialog.spread_choice.buttons()}
    free(dialog)
    free(parent)
