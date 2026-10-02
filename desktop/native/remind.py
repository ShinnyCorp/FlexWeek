"""Reminder and alarm due checks. No Qt, no notification delivery."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime

import flexweek_engine  # type: ignore[import-untyped]

from backend.slots import hhmm_to_minutes
from desktop.native.calendar import date_for_day, monday_of
from desktop.native.reuse import occurrence_days

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
    return {
        "iso": moment.date().isoformat(),
        "day": moment.weekday(),
        "minute": moment.hour * 60 + moment.minute,
        "midnight_ms": int(midnight.timestamp() * 1000),
        "now_ms": now_ms,
    }


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
    week_start = monday_of(today_iso)
    for block in reminder_blocks(blocks, trace):
        start = block.get("start")
        if not start or block.get("completed"):
            continue
        for day in occurrence_days(block):
            if day in (block.get("missed_days") or []) or date_for_day(week_start, day) != today_iso:
                continue
            yield block, day, hhmm_to_minutes(start), reminder_key(week_start, block["id"], day, start)


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
    start_ms = now_ms - REMINDER_WINDOW_MIN * 60_000 if last_check_ms is None else last_check_ms
    queued: list[dict] = []
    remaining_snooze = dict(snoozed)
    for alarm in alarms:
        if not alarm.get("enabled") or weekday not in (alarm.get("days") or []):
            continue
        hour, minute = (int(part) for part in str(alarm["time"]).split(":"))
        due_at = datetime.fromisoformat(today_iso).replace(hour=hour, minute=minute, second=0, microsecond=0)
        due_ms = int(due_at.timestamp() * 1000)
        key = alarm_key(today_iso, alarm)
        if start_ms < due_ms <= now_ms and key not in fired:
            fired.add(key)
            queued.append(dict(alarm))
    for alarm_id, due_ms in list(remaining_snooze.items()):
        if not (start_ms < due_ms <= now_ms):
            continue
        remaining_snooze.pop(alarm_id)
        alarm = next((item for item in alarms if item.get("id") == alarm_id), None)
        if alarm and alarm.get("enabled"):
            queued.append(dict(alarm))
    return queued, remaining_snooze, now_ms


def snooze_until(now_ms: int) -> int:
    return int(flexweek_engine.remind_snooze_until(now_ms))
