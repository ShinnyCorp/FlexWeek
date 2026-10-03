from backend.tests.engine_ref.models import ReasonCode, SlackStatus

REASON_COPY: dict[ReasonCode, str] = {
    # Each says what really stopped the solver (backend/solver.py `_reason_for`), in the student's words.
    # "That time is already taken" named no time, and "Kept out of the sleep window" read as if the
    # homework had been placed.
    "LOCKED_OVERLAP": "Your fixed plans and finished work leave no gap long enough for it before it is due.",
    "DEADLINE_MISS": "There is not enough time left before it is due, even with nothing else planned.",
    "NO_SLOT_LEFT": "Your plans and other homework already fill every gap long enough for it.",
    "PRIORITY_PREEMPT": "Work with a higher priority used the free time before it is due.",
    "ENERGY_MISMATCH": "Planned outside its preferred time of day.",
    "SLEEP_GUARD": "It does not fit in the day on the days left for it.",
    "WORK_WINDOW_MISS": "That does not fit in the times you set aside for work.",
    "RESHUFFLE_AFTER_MISS": "Moved because you missed a day, so the rest of the week still fits.",
}


def sentence(code: ReasonCode) -> str:
    return REASON_COPY[code]


def _amount(minutes: int) -> str:
    """The app's lengths: "45 min", "2 h", "2 h 15 min"."""
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{rest} min"
    return f"{hours} h" if not rest else f"{hours} h {rest} min"


def slack_sentence(slack_min: int, status: SlackStatus) -> str:
    """Shown after the homework's name, as "Chem lab report: Finishes only 29 min before it is due."
    It used to open with the status and a colon of its own, so the line had two."""
    if slack_min == 0:
        return "Finishes right when it is due."
    only = "only " if status == "danger" else ""
    return f"Finishes {only}{_amount(slack_min)} before it is due."
