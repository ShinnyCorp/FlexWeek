"""The rig's --option flag and where its runs are kept."""

from __future__ import annotations

from types import SimpleNamespace

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
    session = SimpleNamespace(STATE=tmp_path / "state" / "abc-1" / "session.json")
    folder = drive.default_runs_folder(session)
    assert folder == tmp_path / "abc-1"
    names = [f"20260929-10000{n}-{n}" for n in range(5)]
    for name in names:
        (folder / name).mkdir(parents=True)
    (folder / "notes").mkdir()
    drive.prune_runs(folder)
    assert sorted(item.name for item in folder.iterdir()) == [*names[2:], "notes"]
