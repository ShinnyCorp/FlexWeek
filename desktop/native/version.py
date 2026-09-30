"""What version of FlexWeek this is.

An app that cannot say what it is cannot tell whether a release is newer than
itself, so this is the one place the number lives in the source. The installers
take their version from the git tag at release time; a test keeps this constant
and the newest CHANGELOG heading in step, so the two cannot drift.
"""

from __future__ import annotations

VERSION = "0.17.1"


def parse(value: str) -> tuple[int, ...] | None:
    """A release number as numbers, or None when it is not one.

    Tolerates a leading v, because GitHub tags carry one and release names do not.
    Anything with a suffix (1.2.3-rc1) is refused rather than guessed at: ordering
    pre-releases correctly is a problem this app does not need to have.
    """
    text = value.strip().removeprefix("v")
    parts = text.split(".")
    if not 1 <= len(parts) <= 4 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def is_newer(candidate: str, current: str = VERSION) -> bool:
    """Whether candidate is a release later than current. False if either is unreadable,
    so a tag this build cannot parse never triggers an update."""
    one, two = parse(candidate), parse(current)
    if one is None or two is None:
        return False
    width = max(len(one), len(two))
    return one + (0,) * (width - len(one)) > two + (0,) * (width - len(two))
