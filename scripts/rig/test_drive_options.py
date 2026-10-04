"""The rig's --option flag and where its runs are kept."""

from __future__ import annotations

import pytest

from scripts.rig import drive


def test_option_is_checked_against_the_designs_own_options():
    assert drive.parse_options("bento", ["hero=today", "corners=square"]) == {
        "hero": "today",
        "corners": "square",
    }
    assert drive.parse_options("bento", []) == {}


@pytest.mark.parametrize(
    ("design", "pair", "says"),
    [
        ("bento", "size=big", "hero: week, today"),
        ("bento", "hero=tomorrow", "week, today"),
        ("bento", "hero", "not key=value"),
        ("classic", "hero=today", "options: none"),
        (None, "hero=today", "needs --design"),
    ],
)
def test_bad_option_names_what_is_valid(design, pair, says):
    with pytest.raises(SystemExit) as refused:
        drive.parse_options(design, [pair])
    assert says in str(refused.value)


def test_runs_go_where_the_environment_says_and_only_the_newest_three_stay(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEXWEEK_RIG_RUNS", str(tmp_path))
    folder = drive.default_runs_folder("abc-1")
    assert folder == tmp_path / "abc-1"
    names = [f"20260929-10000{n}-{n}" for n in range(5)]
    for name in names:
        (folder / name).mkdir(parents=True)
    (folder / "notes").mkdir()
    drive.prune_runs(folder)
    assert sorted(item.name for item in folder.iterdir()) == [*names[2:], "notes"]


def _session(monkeypatch, display, bus="unix:path=/private"):
    monkeypatch.setenv("FLEXWEEK_RIG_DISPLAY", display)
    monkeypatch.setenv("FLEXWEEK_RIG_BUS", bus)
    monkeypatch.setenv("FLEXWEEK_RIG_RUNS_KEY", "abc-1")


def _clear_caller(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    monkeypatch.delenv("FLEXWEEK_CALLER_DISPLAY", raising=False)
    monkeypatch.delenv("FLEXWEEK_CALLER_BUS", raising=False)


def test_drive_reads_the_session_fwtest_started(monkeypatch):
    _session(monkeypatch, ":71")
    _clear_caller(monkeypatch)
    assert drive.session_from_fwtest() == (":71", "unix:path=/private", "abc-1")


def test_drive_without_a_session_says_to_use_fwtest(monkeypatch):
    monkeypatch.delenv("FLEXWEEK_RIG_DISPLAY", raising=False)
    monkeypatch.delenv("FLEXWEEK_RIG_BUS", raising=False)
    monkeypatch.delenv("FLEXWEEK_RIG_RUNS_KEY", raising=False)
    with pytest.raises(SystemExit) as refused:
        drive.session_from_fwtest()
    assert str(refused.value) == "Use fwtest rig."


def test_drive_accepts_display_zero_when_the_caller_has_none(monkeypatch):
    _session(monkeypatch, ":0")
    _clear_caller(monkeypatch)
    assert drive.session_from_fwtest() == (":0", "unix:path=/private", "abc-1")


def test_drive_accepts_display_zero_allocated_for_the_session(monkeypatch):
    _session(monkeypatch, ":0")
    _clear_caller(monkeypatch)
    monkeypatch.setenv("DISPLAY", ":1")
    assert drive.session_from_fwtest() == (":0", "unix:path=/private", "abc-1")


def test_drive_refuses_display_zero_when_it_is_the_caller_display(monkeypatch):
    _session(monkeypatch, ":0")
    _clear_caller(monkeypatch)
    monkeypatch.setenv("DISPLAY", ":0")
    with pytest.raises(SystemExit) as refused:
        drive.session_from_fwtest()
    assert str(refused.value) == "Refusing display :0, which is this process's own DISPLAY."


def test_drive_keeps_an_empty_caller_display_when_the_live_one_changes(monkeypatch):
    _session(monkeypatch, ":0")
    _clear_caller(monkeypatch)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("FLEXWEEK_CALLER_DISPLAY", "")
    assert drive.session_from_fwtest() == (":0", "unix:path=/private", "abc-1")


def test_drive_refuses_the_frozen_caller_display(monkeypatch):
    _session(monkeypatch, ":0")
    _clear_caller(monkeypatch)
    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.setenv("FLEXWEEK_CALLER_DISPLAY", ":0")
    with pytest.raises(SystemExit) as refused:
        drive.session_from_fwtest()
    assert str(refused.value) == "Refusing display :0, which is this process's own DISPLAY."


def test_drive_refuses_the_caller_display(monkeypatch):
    _session(monkeypatch, ":1")
    _clear_caller(monkeypatch)
    monkeypatch.setenv("DISPLAY", ":1")
    with pytest.raises(SystemExit) as refused:
        drive.session_from_fwtest()
    assert str(refused.value) == "Refusing display :1, which is this process's own DISPLAY."


def test_drive_refuses_the_caller_bus(monkeypatch):
    _session(monkeypatch, ":71", "unix:path=/caller")
    _clear_caller(monkeypatch)
    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/caller")
    with pytest.raises(SystemExit) as refused:
        drive.session_from_fwtest()
    assert str(refused.value) == "Refusing the caller's own D-Bus session bus."


def test_drive_keeps_an_empty_caller_bus_when_the_live_one_changes(monkeypatch):
    _session(monkeypatch, ":71")
    _clear_caller(monkeypatch)
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/private")
    monkeypatch.setenv("FLEXWEEK_CALLER_BUS", "")
    assert drive.session_from_fwtest() == (":71", "unix:path=/private", "abc-1")


def test_a_run_that_stops_before_the_last_scenario_is_a_failure():
    plan = [
        ("timeline", "week", "week-move-day"),
        ("timeline", "week", "week-resize-top"),
        ("timeline", "week", "week-create"),
    ]
    results = [
        {"design": "timeline", "tab": "week", "scenario": "week-move-day", "result": "PASS"},
        {"design": "timeline", "tab": "week", "scenario": "week-resize-top", "result": "PASS"},
    ]
    line, code, payload = drive.report_run(plan, results, finished=False, stopped_in="week-create")
    assert code == 1
    assert "passed" not in line.lower()
    assert "STOPPED" in line and "week-create" in line
    skipped = [item for item in payload if item["result"] == "SKIPPED"]
    assert skipped == [{"design": "timeline", "tab": "week", "scenario": "week-create", "result": "SKIPPED"}]


def test_a_python_error_from_the_app_is_a_failure():
    plan = [("timeline", "week", "week-beside")]
    results = [{"design": "timeline", "tab": "week", "scenario": "week-beside", "result": "PASS"}]
    line, code, payload = drive.report_run(
        plan, results, finished=True, python_error="KeyError: 'block_edge'", stopped_in="week-beside"
    )
    assert code == 1
    assert "passed" not in line.lower()
    assert "STOPPED" in line and "week-beside" in line
    assert "KeyError" in line
    assert payload == results


def test_a_finished_run_where_every_scenario_passed_still_says_passed():
    plan = [("bento", "week", "week-move-day")]
    results = [{"design": "bento", "tab": "week", "scenario": "week-move-day", "result": "PASS"}]
    line, code, payload = drive.report_run(plan, results, finished=True)
    assert code == 0
    assert line == "1/1 passed."
    assert payload == results
