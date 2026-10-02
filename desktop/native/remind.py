"""Reminder and alarm due checks. No Qt, no notification delivery."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime

import flexweek_engine  # type: ignore[import-untyped]

REMINDER_WINDOW_MIN = 2
REMINDER_POLL_MS = 30_000
ALARM_SNOOZE_MIN = 5
ALARM_SNOOZE_MS = ALARM_SNOOZE_MIN * 60_000


def reminder_lead_min(prefs: dict | None, default: int = 5) -> int:
    return int(flexweek_engine.remind_lead_min(None if prefs is None else json.dumps(prefs), default))


def start_alert_due(start_min: int, now_min: int, lead: int) -> bool:
    """From the minute the lead begins to the start minute itself."""
    return bool(flexweek_engine.remind_start_alert_due(start_min, now_min, lead))


def song_due(start_min: int, now_min: int) -> bool:
    return bool(flexweek_engine.remind_song_due(start_min, now_min))


def reminder_key(week_start: str, block_id: str, day: int, start: str) -> str:
    return str(flexweek_engine.remind_key(week_start, block_id, day, start))


def alarm_key(iso_date: str, alarm: dict) -> str:
    return str(flexweek_engine.remind_alarm_key(iso_date, json.dumps(alarm)))


def clock_parts(now_ms: int) -> dict:
    moment = datetime.fromtimestamp(now_ms / 1000.0)
    midnight = datetime(moment.year, moment.month, moment.day)
    return json.loads(
        flexweek_engine.remind_clock_parts(
            now_ms,
            moment.year,
            moment.month,
            moment.day,
            moment.hour,
            moment.minute,
            int(midnight.timestamp() * 1000),
        )
    )


def reminder_blocks(blocks: list[dict], trace: dict | None) -> list[dict]:
    return json.loads(
        flexweek_engine.remind_blocks(json.dumps(blocks), None if trace is None else json.dumps(trace))
    )


def due_reminders(
    *,
    blocks: list[dict],
    trace: dict | None,
    today_iso: str,
    now_min: int,
    lead_min: int,
    fired: set[str],
) -> list[dict]:
    return json.loads(
        flexweek_engine.remind_due(
            json.dumps(blocks),
            None if trace is None else json.dumps(trace),
            today_iso,
            now_min,
            lead_min,
            json.dumps(sorted(fired)),
        )
    )


def due_songs(
    *, blocks: list[dict], trace: dict | None, today_iso: str, now_min: int, played: set[str]
) -> list[dict]:
    """Blocks with a Spotify link that are starting, as alarms."""
    return json.loads(
        flexweek_engine.remind_songs(
            json.dumps(blocks),
            None if trace is None else json.dumps(trace),
            today_iso,
            now_min,
            json.dumps(sorted(played)),
        )
    )


def todays_starts(
    blocks: list[dict], trace: dict | None, today_iso: str
) -> Iterator[tuple[dict, int, int, str]]:
    """Each block starting today: the block, its day, its start in minutes, and its reminder key."""
    rows = json.loads(
        flexweek_engine.remind_todays_starts(
            json.dumps(blocks), None if trace is None else json.dumps(trace), today_iso
        )
    )
    yield from (tuple(row) for row in rows)


def due_alarms(
    *,
    alarms: list[dict],
    today_iso: str,
    weekday: int,
    now_ms: int,
    midnight_ms: int,
    last_check_ms: int | None,
    fired: set[str],
    snoozed: dict[str, int],
) -> tuple[list[dict], dict[str, int], int]:
    def due_ms_of(hour: int, minute: int) -> int:
        due_at = datetime.fromisoformat(today_iso).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return int(due_at.timestamp() * 1000)

    queued, remaining, last_ms = flexweek_engine.remind_due_alarms(
        json.dumps(alarms), today_iso, weekday, now_ms, last_check_ms, fired, json.dumps(snoozed), due_ms_of
    )
    return json.loads(queued), json.loads(remaining), last_ms


def snooze_until(now_ms: int) -> int:
    return int(flexweek_engine.remind_snooze_until(now_ms))
