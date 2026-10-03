"""Reminder and alarm due checks. No Qt, no notification delivery."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime

import flexweek_engine  # type: ignore[import-untyped]

# The engine runs these rules, so the numbers are read from it rather than written down again.
REMINDER_WINDOW_MIN = flexweek_engine.REMINDER_WINDOW_MIN
REMINDER_LEAD_DEFAULT_MIN = flexweek_engine.REMINDER_LEAD_DEFAULT_MIN
ALARM_SNOOZE_MIN = flexweek_engine.ALARM_SNOOZE_MIN
ALARM_SNOOZE_MS = flexweek_engine.ALARM_SNOOZE_MS
REMINDER_POLL_MS = 30_000


def reminder_lead_min(prefs: dict | None, default: int | None = None) -> int:
    """The saved lead, else `default`, else the engine's own default."""
    fallback = REMINDER_LEAD_DEFAULT_MIN if default is None else default
    return int(flexweek_engine.remind_lead_min(json.dumps(prefs), fallback))


def start_alert_due(start_min: int, now_min: int, lead: int) -> bool:
    """From the minute the lead begins to the start minute itself."""
    return bool(flexweek_engine.remind_start_alert_due(start_min, now_min, lead))


def song_due(start_min: int, now_min: int, lead: int) -> bool:
    """From the start minute until the reminder lead has passed."""
    return bool(flexweek_engine.remind_song_due(start_min, now_min, lead))


def reminder_key(week_start: str, block_id: str, day: int, start: str) -> str:
    return str(flexweek_engine.remind_key(week_start, block_id, day, start))


def alarm_key(iso_date: str, alarm: dict) -> str:
    return str(flexweek_engine.remind_alarm_key(iso_date, json.dumps(alarm)))


def clock_parts(now_ms: int) -> dict:
    return json.loads(flexweek_engine.remind_clock_parts(now_ms, datetime.fromtimestamp, datetime))


def reminder_blocks(blocks: list[dict], trace: dict | None) -> list[dict]:
    return json.loads(flexweek_engine.remind_blocks(json.dumps(blocks), json.dumps(trace)))


def due_reminders(
    *,
    blocks: list[dict],
    trace: dict | None,
    today_iso: str,
    now_min: int,
    lead_min: int,
    fired: set[str],
    default_link: str | None = None,
    sound_is_spotify: bool = False,
) -> list[dict]:
    return json.loads(
        flexweek_engine.remind_due(
            json.dumps(blocks),
            json.dumps(trace),
            today_iso,
            now_min,
            lead_min,
            fired,
            default_link,
            sound_is_spotify,
        )
    )


def due_songs(
    *,
    blocks: list[dict],
    trace: dict | None,
    today_iso: str,
    now_min: int,
    lead_min: int,
    played: set[str],
    default_link: str | None = None,
    sound_is_spotify: bool = False,
) -> list[dict]:
    """Blocks that are starting with a song to play, as alarms: the block's own Spotify link, else the
    Settings link when the chosen sound is Spotify."""
    return json.loads(
        flexweek_engine.remind_songs(
            json.dumps(blocks),
            json.dumps(trace),
            today_iso,
            now_min,
            lead_min,
            played,
            default_link,
            sound_is_spotify,
        )
    )


def todays_starts(
    blocks: list[dict], trace: dict | None, today_iso: str
) -> Iterator[tuple[dict, int, int, str]]:
    """Each block starting today: the block, its day, its start in minutes, and its reminder key."""
    rows = json.loads(flexweek_engine.remind_todays_starts(json.dumps(blocks), json.dumps(trace), today_iso))
    yield from map(tuple, rows)


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
    queued, remaining, last_ms = flexweek_engine.remind_due_alarms(
        json.dumps(alarms),
        today_iso,
        weekday,
        now_ms,
        last_check_ms,
        fired,
        json.dumps(snoozed),
        datetime.fromisoformat,
    )
    return json.loads(queued), json.loads(remaining), last_ms


def snooze_until(now_ms: int) -> int:
    return int(flexweek_engine.remind_snooze_until(now_ms))
