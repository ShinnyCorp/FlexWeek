"""Why a plan came out the way it did. The sentences live in the engine."""

from flexweek_engine import sentence as _sentence  # type: ignore[import-untyped]
from flexweek_engine import slack_sentence  # type: ignore[import-untyped]

from backend.models import ReasonCode, SlackStatus

REASON_COPY: dict[ReasonCode, str] = {
    code: _sentence(code)
    for code in (
        "LOCKED_OVERLAP",
        "DEADLINE_MISS",
        "DEADLINE_PASSED",
        "NO_SLOT_LEFT",
        "PRIORITY_PREEMPT",
        "ENERGY_MISMATCH",
        "SLEEP_GUARD",
        "WORK_WINDOW_MISS",
        "NO_STUDY_TIME_TODAY",
        "RESHUFFLE_AFTER_MISS",
    )
}


def sentence(code: ReasonCode) -> str:
    return REASON_COPY[code]


__all__ = ["REASON_COPY", "SlackStatus", "sentence", "slack_sentence"]
