"""Reminder and alarm due checks. No Qt, no notification delivery."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from backend.tests.engine_ref.calendar import DAYS, date_for_day, monday_of
from backend.tests.engine_ref.reuse import occurrence_days
from backend.tests.engine_ref.weekmodel import hhmm_text

from backend.tests.engine_ref.slots import hhmm_to_minutes

REMINDER_WINDOW_MIN = 2
REMINDER_POLL_MS = 30_000
ALARM_SNOOZE_MIN = 5
ALARM_SNOOZE_MS = ALARM_SNOOZE_MIN * 60_000


def reminder_lead_min(prefs: dict | None, default: int = 5) -> int:
    if not prefs or prefs.get("reminder_lead_min") is None:
        return default
    return int(prefs["reminder_lead_min"])


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


def start_alert_due(start_min: int, now_min: int, lead: int) -> bool:
    """From the minute the lead begins to the start minute itself. A block saved after its lead
    began, or found when the app opens, is still reminded of before it starts, and the start minute
    is in because the poll may first look during it."""
    start = int(start_min)
    return start - max(0, int(lead)) <= int(now_min) <= start


def song_due(start_min: int, now_min: int) -> bool:
    return int(start_min) <= int(now_min) <= int(start_min) + REMINDER_WINDOW_MIN


def reminder_key(week_start: str, block_id: str, day: int, start: str) -> str:
    return "|".join((week_start, block_id, str(day), start))


def alarm_key(iso_date: str, alarm: dict) -> str:
    return "|".join((iso_date, str(alarm.get("id") or ""), str(alarm.get("time") or "")))


def reminder_blocks(blocks: list[dict], trace: dict | None) -> list[dict]:
    sources = {item["id"]: item for item in blocks}
    if not trace:
        return list(blocks)
    locked = [item for item in blocks if item.get("kind") == "locked"]
    placed = []
    for item in trace.get("placed") or []:
        if item.get("kind") != "flexible":
            continue
        source = sources.get(item["id"])
        if source is None:
            placed.append(item)
            continue
        placed.append(
            {
                **item,
                "completed": source.get("completed"),
                "missed_days": list(source.get("missed_days") or []),
                "title": source.get("title") or item.get("title"),
            }
        )
    return locked + placed


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


def due_reminders(
    *,
    blocks: list[dict],
    trace: dict | None,
    today_iso: str,
    now_min: int,
    lead_min: int,
    fired: set[str],
) -> list[dict]:
    due = []
    for block, day, start_min, key in todays_starts(blocks, trace, today_iso):
        if key in fired or not start_alert_due(start_min, now_min, lead_min):
            continue
        started = now_min >= start_min
        if started and block.get("spotify_url"):
            # Its song is its notice at the start, so it gets one, not two.
            continue
        due.append(
            {
                "key": key,
                "title": f"{block['title']} {'starts now' if started else 'starts soon'}",
                "body": f"{hhmm_text(block['start'])} · {DAYS[day]}",
            }
        )
    return due


def due_songs(
    *, blocks: list[dict], trace: dict | None, today_iso: str, now_min: int, played: set[str]
) -> list[dict]:
    """Blocks with a Spotify link that are starting, as alarms: the song plays until it is dismissed
    or snoozed. An alarm with no days never rings on its own, only when it is snoozed."""
    due = []
    for block, _day, start_min, key in todays_starts(blocks, trace, today_iso):
        link = block.get("spotify_url")
        if not link or key in played or not song_due(start_min, now_min):
            continue
        due.append(
            {
                "id": key,
                "name": block["title"],
                "time": block["start"],
                "days": [],
                "enabled": True,
                "sound": "spotify",
                "spotify_url": link,
                "block": True,
            }
        )
    return due


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
    return now_ms + ALARM_SNOOZE_MS
