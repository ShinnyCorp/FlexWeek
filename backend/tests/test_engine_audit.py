"""Cases from the engine audit that have fixed expectations or use Python's own int() as the oracle."""

from __future__ import annotations

import flexweek_engine  # type: ignore[import-untyped]

from backend import availability as live_availability
from backend import day as live_day
from backend import models as live_models
from backend import month as live_month


def outcome(fn):
    try:
        return ("ok", fn())
    except Exception as exc:
        return (type(exc).__name__, str(exc))


def test_int_parser_matches_python_for_every_code_point():
    def check(chars: list[str]) -> None:
        got = flexweek_engine.int_chars("".join(chars))
        for ch, item in zip(chars, got, strict=True):
            want = outcome(lambda ch=ch: int(ch))
            if want[0] == "ok":
                want = ("ok", str(want[1]))
            assert item == want, (repr(ch), item, want)

    chunk: list[str] = []
    for code_point in range(0x110000):
        if 0xD800 <= code_point <= 0xDFFF:
            continue
        chunk.append(chr(code_point))
        if len(chunk) == 4096:
            check(chunk)
            chunk = []
    if chunk:
        check(chunk)


def test_int_parser_matches_python_on_longer_text():
    for text in ("1_2", "\x1c12", "  8", "'", "\x00", "+3", "1__2", "١٢", "\x1c"):
        got = flexweek_engine.int_text(text)
        want = outcome(lambda text=text: int(text))
        if want[0] == "ok":
            want = ("ok", str(want[1]))
        assert got == want, (repr(text), got, want)


def test_a_panic_becomes_runtime_error():
    try:
        flexweek_engine.panic_probe()
    except RuntimeError as exc:
        assert str(exc) == "probe"
    else:
        raise AssertionError("the panic did not become RuntimeError")


def test_a_window_start_in_other_digits_is_read_as_int_reads_it():
    # The pattern's `\d` takes "1٠" and int() reads it as 10, so the window runs 10:00 to 12:00.
    body = {"days": [0], "start": "1٠:00", "duration_min": 120}
    live = [live_models.StudyWindow(**body)]
    for start_min, rank in ((10 * 60, 1), (0, 2)):
        assert live_availability.study_rank(live, None, 0, start_min, 60) == rank


def test_an_empty_start_means_not_placed_yet_in_day_and_month():
    # WeekRequest only checks a start when it is truthy, so "" is stored for a session with no time.
    essay = {"id": "s1", "title": "Essay", "kind": "flexible", "days": [0], "duration_min": 60, "start": "", "assignment_id": "a1"}
    day = live_day.build_day("2026-09-07", "2026-09-07", [essay], [], [])
    assert day["next_action"] == {"kind": "add"}
    assert day["workload"]["available_min"] == 1440
    month = live_month.build_month("2026-09", [], [("2026-09-07", [essay])])
    assert month["unscheduled"] == {"session_count": 1, "minutes": 60}
