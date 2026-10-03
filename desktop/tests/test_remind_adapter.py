"""What the reminder wrapper still decides in Python: the local time zone it reads for an alarm's day.

The engine's reminder rules have Rust twins; this file keeps the one case that depends on the
interpreter's zone, which no Rust test can set."""

from __future__ import annotations

import os
import time
from datetime import datetime

from desktop.native.remind import clock_parts, due_alarms


def test_alarm_fires_at_seven_on_a_daylight_saving_day() -> None:
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "America/New_York"
    time.tzset()
    try:
        alarm = {"id": "wake", "name": "Wake", "time": "07:00", "days": [6], "enabled": True}

        def queued_at(iso: str) -> list[str]:
            moment = datetime.fromisoformat(iso).replace(hour=7, minute=0)
            now_ms = int(moment.timestamp() * 1000)
            clock = clock_parts(now_ms)
            queued, _, _ = due_alarms(
                alarms=[alarm],
                today_iso=iso,
                weekday=moment.weekday(),
                now_ms=now_ms,
                midnight_ms=clock["midnight_ms"],
                last_check_ms=now_ms - 60_000,
                fired=set(),
                snoozed={},
            )
            return [item["id"] for item in queued]

        # The spring-forward and fall-back Sundays, and an ordinary one.
        assert queued_at("2026-03-08") == ["wake"]
        assert queued_at("2026-11-01") == ["wake"]
        assert queued_at("2026-09-13") == ["wake"]
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()
