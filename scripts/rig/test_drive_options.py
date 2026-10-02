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


def test_drive_reads_the_session_fwtest_started(monkeypatch):
    monkeypatch.setenv("FLEXWEEK_RIG_DISPLAY", ":71")
    monkeypatch.setenv("FLEXWEEK_RIG_BUS", "unix:path=/private")
    monkeypatch.setenv("FLEXWEEK_RIG_RUNS_KEY", "abc-1")
    assert drive.session_from_fwtest() == (":71", "unix:path=/private", "abc-1")


def test_drive_without_a_session_says_to_use_fwtest(monkeypatch):
    monkeypatch.delenv("FLEXWEEK_RIG_DISPLAY", raising=False)
    monkeypatch.delenv("FLEXWEEK_RIG_BUS", raising=False)
    monkeypatch.delenv("FLEXWEEK_RIG_RUNS_KEY", raising=False)
    with pytest.raises(SystemExit) as refused:
        drive.session_from_fwtest()
    assert str(refused.value) == "Use fwtest rig."
