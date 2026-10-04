"""Account, week drafts and solver results for the native desktop window."""

from __future__ import annotations

import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from urllib.parse import quote
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Signal

from backend.models import Assignment, ProtectedWindow, StudyWindow, TimeBlock, WorkWindow
from backend.slots import DAY_END_MIN, DAY_START_MIN, hhmm_to_minutes, minutes_to_hhmm
from backend.weeks import current_week_start
from desktop.native.calendar import (
    DAY_FULL,
    SERIES_DRAG_MESSAGE,
    apply_block_edit,
    apply_block_times,
    date_for_day,
    days_through,
    delete_occurrence,
    due_day_in_week,
    first_plannable_day,
    is_series,
    is_setup_block,
    local_stamp,
    monday_of,
    month_anchor_date,
    month_for_view,
    relocate_block,
    shifted_month,
    span_problem,
)
from desktop.native.client import ApiError, NativeClient, auth_error
from desktop.native.files import (
    export_day_payload,
    export_week_payload,
    merge_imported_blocks,
    parse_import_payload,
    plan_imported_homework,
)
from desktop.native.focus import (
    DEFAULT_TIMERS,
    FOCUS_PHASE_LABEL,
    begin_state,
    break_phase,
    credit_target,
    focus_candidates,
    more_time_choices,
    now_and_next,
    now_next_line,
    pause_state,
    persist_payload,
    phase_duration_ms,
    remaining_ms,
    restore_state,
    set_phase,
)
from desktop.native.history import capture_step, join_step, mark_stale, push_step
from desktop.native.kept import KeptSession
from desktop.native.look import pack_axis, sanitize_look
from desktop.native.pomodoro import inflate_for_solve, split_solved
from desktop.native.remind import (
    clock_parts,
    due_alarms,
    due_reminders,
    due_songs,
    reminder_lead_min,
    snooze_until,
)
from desktop.native.reuse import (
    MAX_WEEK_BLOCKS,
    apply_plan,
    available_homework_minutes,
    block_occurs_on_day,
    capacity_problem,
    clear_stale_pins,
    clipboard_fingerprint,
    clipboard_item,
    copied_fixed_block,
    copied_homework_block,
    copy_label,
    due_point,
    is_planned,
    late_from_start,
    late_id,
    merge_preview_rows,
    plan_start,
    proposals_from_clipboard,
    restore_point_label,
    routine_rows,
    routine_source_blocks,
    routine_template,
    running_late_block,
    running_late_refusal,
    session_days,
    settle_placements,
    solve_request,
    unfinished_items,
    week_label,
)
from desktop.native.weekmodel import WeekModel, build_week, due_label, length_label, minute_of

WEEK_OVER = "This week is over, so nothing was planned. Plan this week or a later one."


def first_placed(trace: dict, targets: object) -> tuple[int, int] | None:
    """Where the first homework a plan gave a time is, by day and then minute."""
    spots = [
        (day, minute_of(item["start"]))
        for item in trace.get("placed") or []
        if item["id"] in targets and item.get("start")
        for day in (item.get("days") or [])[:1]
    ]
    return min(spots, default=None)


def plan_sentence(placed: int, waiting: int) -> str:
    """How much homework a plan placed, counting homework only."""
    said = f"Planned {placed} homework block{'s' if placed != 1 else ''}."
    if waiting:
        said += f" {waiting} still need{'s' if waiting == 1 else ''} a time."
    return said


PAST_DROP = "That's in the past."


def _assignment_write(item_id: str, item: dict | None, revision: int) -> dict:
    if item is None:
        return {"id": item_id, "assignment": None, "revision": revision}
    body = Assignment.model_validate(
        {key: value for key, value in item.items() if key in Assignment.model_fields}
    )
    dumped = body.model_dump(mode="json")
    dumped.pop("revision", None)
    return {"id": item_id, "assignment": dumped, "revision": revision}


def _week_write(week_start: str, blocks: list[dict], revision: int) -> dict:
    return {
        "week_start": week_start,
        "blocks": [TimeBlock.model_validate(block).model_dump(mode="json") for block in blocks],
        "revision": revision,
    }


def _revision_after_deletes(stored_blocks: list[dict], revision: int, deleted: set[str]) -> int:
    """The server takes a deleted homework's blocks out of every week before it writes the week sent
    with it, and each deleted homework that had blocks there moves that week up by one. A week written
    in the same save has to carry the revision it will have by then."""
    return revision + sum(
        1 for item_id in deleted if any(block.get("assignment_id") == item_id for block in stored_blocks)
    )


def _keep_step_revisions(step: dict, data: dict) -> None:
    stored = {week["week_start"]: week for week in data.get("weeks") or []}
    for entry in step.get("weeks") or []:
        week = stored.get(entry["week_start"])
        if week is not None:
            entry["revision"] = week["revision"]


# What the status line says when a save or a week load goes as expected. A reminder on the status line
# outranks these, so they are not allowed to replace it.
ROUTINE_STATUS = frozenset(
    ("Saving…", "Saved.", "Saving preferences…", "Saved preferences.", "Loading…", "This week.")
)


class NativeSession(QObject):
    account_changed = Signal(object)
    recovery_codes = Signal(list)
    week_changed = Signal()
    busy_changed = Signal(bool)
    status = Signal(str)
    # Each save's outcome, for words that must wait for it: (stored, what the status line says).
    save_finished = Signal(bool, str)
    plan_conflicts = Signal(list)
    planned = Signal(str)
    focus_changed = Signal()
    focus_replace_needed = Signal(str, str)
    alerts = Signal(list)
    alarm_due = Signal(object)

    def __init__(self, origin: str, parent: QObject | None = None, kept: KeptSession | None = None) -> None:
        super().__init__(parent)
        self.client = NativeClient(origin, self)
        self.client.expired.connect(self._on_expired)
        self.account: dict | None = None
        # Keep me signed in: where this database's kept session lives, and the choice on the sign-in
        # card at the last sign-in. A session resumed at launch was kept, so it stays kept.
        self.kept = kept
        self.keep_signed_in = True
        self.week_start = current_week_start()
        self.blocks: list[dict] = []
        self.revision = 0
        self.assignments: dict[str, dict] = {}
        self.dirty_assignments: set[str] = set()
        self.trace: dict | None = None
        self.dirty = False
        self.conflict = False
        self.pending_save: dict | None = None
        self._save_status: str | None = None
        self.busy = False
        self.message = ""
        self.planner_view = "week"
        self.selected_day = date.today().isoformat()
        self.day_data: dict | None = None
        self.selected_month: str | None = None
        self.month_data: dict | None = None
        # The type a drag on the hours makes, once one is picked under Add. Until then a block made by
        # dragging has none: it used to be School, and an hour of Club counted as school.
        self.armed_category: str | None = None
        self.selected_block_id: str | None = None
        self.selected_occurrence_day: int | None = None
        self._ticket = 0
        self._plan_ticket: int | None = None
        self._day_ticket = 0
        self._month_ticket = 0
        self._undo: list[dict] = []
        self._join_step = False
        # New homework to give a time once its save lands, when the student plans as they add.
        self._plan_after_save: set[str] = set()
        self._redo: list[dict] = []
        self._committed_blocks: list[dict] = []
        self._committed_assignments: dict[str, dict] = {}
        self._history_label = "editing the week"
        self._pending_step: dict | None = None
        self._plan_step: dict | None = None
        self._traveling: str | None = None
        self._travel_step: dict | None = None
        self.clipboard: dict | None = None
        self.routines: dict[str, dict] = {}
        self.saved_weeks: list[str] = []
        self.preferences: dict | None = None
        self.late_preview: dict | None = None
        self.spread_preview: dict | None = None
        self._seen_unfinished: set[str] = set()
        self._attempts: dict[str, str] = {}
        self._weeks_ticket = 0
        self._routines_ticket = 0
        self._prefs_ticket = 0
        self._assign_ticket = 0
        self._preview_attempt: str | None = None
        self._move_attempt: str | None = None
        self.focus: dict | None = None
        self._fresh_plan = False
        # The last plan's homework given a time and still without one: what its toast and its bar say.
        self.plan_counts: tuple[int, int] = (0, 0)
        # The day and minute of the first homework the last plan gave a time, to scroll to.
        self.plan_first: tuple[int, int] | None = None
        self.needs_time: dict[str, str] = {}
        # Registered in this sitting, so setup can open before the account's preferences arrive.
        self.new_account = False
        self.focus_store: dict[int, dict | None] = {}
        self.look: dict = sanitize_look(None)
        self.now_ms = lambda: int(time.time() * 1000)
        self._focus_busy = False
        self._pending_focus: dict | None = None
        self._record_history = True
        self.fired_reminders: set[str] = set()
        self.fired_alarms: set[str] = set()
        self.snoozed_alarms: dict[str, int] = {}
        self.last_alarm_check: int | None = None
        self.active_alarm: dict | None = None
        self.alarm_queue: list[dict] = []
        self.played_songs: set[str] = set()
        self._snoozed_songs: dict[str, dict] = {}
        self._focus_after_restore = False
        self.restore_points: list[dict] = []
        self.restore_preview: dict | None = None
        self.storage_info: dict | None = None
        self.transfer_preview: dict | None = None
        self.timer_presets: list[dict] = []
        self.reminder_limits: dict = {}
        self.recovery_remaining: int | None = None
        self.split_preview: dict | None = None
        self._drafts: dict[str, dict] = {}
        self._reminder_ticket = 0
        self._reminder_fetching: str | None = None
        self._reminder_week: str | None = None
        self._reminder_blocks: list[dict] = []
        self._reminder_trace: dict | None = None

    def _say(self, text: str) -> None:
        self.message = text
        self.status.emit(text)

    def _begin(self, planning: bool = False) -> int:
        self._ticket += 1
        self._plan_ticket = self._ticket if planning else None
        self.busy = True
        self.busy_changed.emit(True)
        return self._ticket

    @property
    def planning(self) -> bool:
        """A plan was asked for and its result is not back yet."""
        return self.busy and self._plan_ticket == self._ticket

    def _alive(self, ticket: int) -> bool:
        return ticket == self._ticket

    def _idle(self, ticket: int) -> bool:
        if not self._alive(ticket):
            return False
        self.busy = False
        self.busy_changed.emit(False)
        return True

    def _fail(self, ticket: int, error: ApiError) -> None:
        if self._idle(ticket):
            self._say(error.message)

    def _clear_local(self) -> None:
        if self.account is not None:
            self.focus_store.pop(self.account["id"], None)
        self.account = None
        self.week_start = current_week_start()
        self.blocks = []
        self.revision = 0
        self.assignments = {}
        self.dirty_assignments.clear()
        self.trace = None
        self.dirty = False
        self.conflict = False
        self.pending_save = None
        self.planner_view = "week"
        self.selected_day = date.today().isoformat()
        self.day_data = None
        self.selected_month = None
        self.month_data = None
        self.armed_category = None
        self.selected_block_id = None
        self.selected_occurrence_day = None
        self._day_ticket += 1
        self._month_ticket += 1
        self._undo.clear()
        self._redo.clear()
        self._committed_blocks = []
        self._committed_assignments = {}
        self._pending_step = None
        self._plan_step = None
        self._traveling = None
        self._travel_step = None
        self.clipboard = None
        self.routines = {}
        self.saved_weeks = []
        self.preferences = None
        self.new_account = False
        self.late_preview = None
        self.spread_preview = None
        self._seen_unfinished.clear()
        self._attempts.clear()
        self._preview_attempt = None
        self._history_label = "editing the week"
        self.needs_time = {}
        self._reset_focus(persist=False)
        self.fired_reminders.clear()
        self.fired_alarms.clear()
        self.snoozed_alarms.clear()
        self.last_alarm_check = None
        self.active_alarm = None
        self.alarm_queue.clear()
        self.played_songs.clear()
        self._snoozed_songs.clear()
        self._focus_after_restore = False
        self.restore_points = []
        self.restore_preview = None
        self.storage_info = None
        self.transfer_preview = None
        self.timer_presets = []
        self.reminder_limits = {}
        self.recovery_remaining = None
        self.split_preview = None
        self._drafts.clear()
        self._reminder_ticket += 1
        self._reminder_fetching = None
        self._reminder_week = None
        self._reminder_blocks = []
        self._reminder_trace = None

    def arm_category(self, category: str) -> None:
        self.armed_category = category

    def select_block(self, block_id: str | None, day: int | None) -> None:
        self.selected_block_id = block_id
        self.selected_occurrence_day = day

    def _ensure_selected_day(self) -> None:
        try:
            if monday_of(self.selected_day) == self.week_start:
                return
            weekday = date.fromisoformat(self.selected_day).weekday()
        except ValueError:
            self.selected_day = self.week_start
            return
        self.selected_day = date_for_day(self.week_start, weekday)

    def _held(self) -> bool:
        return bool(self.dirty or self.dirty_assignments or self.pending_save)

    def _week_snapshot(self) -> dict:
        return {
            "week_start": self.week_start,
            "blocks": deepcopy(self.blocks),
            "revision": self.revision,
            "assignments": deepcopy(self.assignments),
            "dirty_assignments": set(self.dirty_assignments),
            "trace": deepcopy(self.trace),
            "dirty": self.dirty,
            "conflict": self.conflict,
            "pending_save": deepcopy(self.pending_save),
            "undo": deepcopy(self._undo),
            "redo": deepcopy(self._redo),
            "committed_blocks": deepcopy(self._committed_blocks),
            "committed_assignments": deepcopy(self._committed_assignments),
            "pending_step": deepcopy(self._pending_step),
            "history_label": self._history_label,
            "selected_day": self.selected_day,
            "selected_block_id": self.selected_block_id,
            "selected_occurrence_day": self.selected_occurrence_day,
        }

    def _restore_week(self, snap: dict) -> None:
        self.week_start = snap["week_start"]
        self.blocks = deepcopy(snap["blocks"])
        self.revision = snap["revision"]
        self.assignments = deepcopy(snap["assignments"])
        self.dirty_assignments = set(snap["dirty_assignments"])
        self.trace = deepcopy(snap["trace"])
        self.dirty = snap["dirty"]
        self.conflict = snap["conflict"]
        self.pending_save = deepcopy(snap["pending_save"])
        self._undo = deepcopy(snap["undo"])
        self._redo = deepcopy(snap["redo"])
        self._committed_blocks = deepcopy(snap["committed_blocks"])
        self._committed_assignments = deepcopy(snap["committed_assignments"])
        self._pending_step = deepcopy(snap["pending_step"])
        self._history_label = snap["history_label"]
        self.selected_day = snap["selected_day"]
        self.selected_block_id = snap["selected_block_id"]
        self.selected_occurrence_day = snap["selected_occurrence_day"]

    def _refresh_view(self) -> None:
        if self.planner_view == "day":
            self._ensure_selected_day()
            self._fetch_day()
        elif self.planner_view == "month" and self.selected_month:
            self._fetch_month()

    def set_view(self, view: str) -> None:
        if view not in {"day", "week", "month"} or self.account is None:
            return
        if view == "month":
            self.open_month()
            return
        if self.planner_view == "month":
            self._leave_month(view)
            return
        self.planner_view = view
        self._refresh_view()
        self.week_changed.emit()

    def open_day(self, iso_day: str) -> None:
        if self.account is None:
            return
        try:
            date.fromisoformat(iso_day)
        except ValueError:
            return
        monday = monday_of(iso_day)
        self.selected_day = iso_day
        self.planner_view = "day"
        self.day_data = None
        if monday != self.week_start:
            self.load_week(monday)
            return
        self._fetch_day()
        self.week_changed.emit()

    def open_month(self, month: str | None = None) -> None:
        if self.account is None:
            return
        today = datetime.fromtimestamp(self.now_ms() / 1000).date().isoformat()
        anchor = self.selected_day if self.planner_view == "day" else (
            today if monday_of(today) == self.week_start else date_for_day(self.week_start, 3)
        )
        self.selected_day = anchor
        self.selected_month = month or month_for_view(anchor)
        self.planner_view = "month"
        self.month_data = None
        self._fetch_month()
        self.week_changed.emit()

    def shift_month(self, amount: int) -> None:
        if self.planner_view != "month" or not self.selected_month:
            return
        nxt = shifted_month(self.selected_month, amount)
        if nxt is None:
            return
        self.selected_month = nxt
        self.month_data = None
        self._fetch_month()
        self.week_changed.emit()

    def _leave_month(self, view: str) -> None:
        if not self.selected_month:
            self.planner_view = view
            self.week_changed.emit()
            return
        today = datetime.fromtimestamp(self.now_ms() / 1000).date().isoformat()
        anchor = self.selected_day if self.selected_day[:7] == self.selected_month else (
            month_anchor_date(self.selected_month, today)
        )
        monday = monday_of(anchor)
        self.selected_day = anchor
        self.planner_view = view
        if monday != self.week_start:
            self.load_week(monday)
            return
        self._refresh_view()
        self.week_changed.emit()

    def _fetch_day(self) -> None:
        if self.account is None or self.planner_view != "day":
            return
        asked = self.selected_day
        self._day_ticket += 1
        token = self._day_ticket

        def ok(data: dict) -> None:
            if token != self._day_ticket or self.planner_view != "day" or self.selected_day != asked:
                return
            self.day_data = data
            self.week_changed.emit()

        def err(_error: ApiError) -> None:
            if token != self._day_ticket:
                return
            self.week_changed.emit()

        self.client.request("GET", f"/api/day?date={asked}", None, ok, err)

    def _fetch_month(self) -> None:
        if self.account is None or self.planner_view != "month" or not self.selected_month:
            return
        asked = self.selected_month
        self._month_ticket += 1
        token = self._month_ticket

        def ok(data: dict) -> None:
            if token != self._month_ticket or self.planner_view != "month" or self.selected_month != asked:
                return
            self.month_data = data
            self.week_changed.emit()

        def err(error: ApiError) -> None:
            if token != self._month_ticket:
                return
            self._say(error.message)
            self.week_changed.emit()

        self.client.request("GET", f"/api/month?month={asked}", None, ok, err)

    def _keep_session(self) -> None:
        if self.kept is None:
            return
        self.kept.note_sign_in()
        token = self.client.session_token() if self.keep_signed_in else None
        if token:
            self.kept.keep(token)
        else:
            self.kept.forget()

    def _forget_session(self) -> None:
        if self.kept is not None:
            self.kept.forget()

    def resume(self) -> None:
        """Open the week with the session kept at the last sign-in, when there is one and it still
        works. One that the server has ended, by expiry or by signing out elsewhere, is forgotten."""
        token = self.kept.token() if self.kept is not None else None
        if token is None or self.account is not None or self.busy:
            return
        ticket = self._begin()
        self._say("Signing in…")
        self.client.adopt_session(token)

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            self.client.set_account(data)
            self.account = {"id": data["id"], "username": data["username"]}
            self.keep_signed_in = True
            self.account_changed.emit(self.account)
            self.load_week(self.week_start, discard=True)

        def failed(error: ApiError) -> None:
            if error.status == 401:
                self._forget_session()
            self.client.reset()
            self._fail(ticket, error)

        self.client.request("GET", "/api/auth/me", None, ok, failed)

    def _on_expired(self) -> None:
        self._forget_session()
        self._ticket += 1
        self.busy = False
        self.busy_changed.emit(False)
        self.client.reset()
        self._clear_local()
        self.account_changed.emit(None)
        self.week_changed.emit()
        self._say("Please sign in again, or check your username and password.")

    def register(self, username: str, password: str) -> None:
        ticket = self._begin()
        self._say("Creating account…")

        def ok(data: dict) -> None:
            if not self._alive(ticket):
                return
            self.client.set_account(data)
            self.account = {"id": data["id"], "username": data["username"]}
            self.new_account = True
            self.busy = False
            self.busy_changed.emit(False)
            self.account_changed.emit(self.account)
            self.recovery_codes.emit(list(data.get("recovery_codes") or []))
            self._say("Save these recovery codes before continuing.")

        self.client.request(
            "POST",
            "/api/auth/register",
            {"username": username, "password": password},
            ok,
            lambda error: self._fail(ticket, auth_error(error, creating=True)),
        )

    def login(self, username: str, password: str) -> None:
        ticket = self._begin()
        self._say("Signing in…")

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            self.client.set_account(data)
            self.account = {"id": data["id"], "username": data["username"]}
            self._keep_session()
            self.account_changed.emit(self.account)
            self.load_week(self.week_start, discard=True)

        self.client.request(
            "POST",
            "/api/auth/login",
            {"username": username, "password": password},
            ok,
            lambda error: self._fail(ticket, auth_error(error, creating=False)),
        )

    def finish_recovery(self) -> None:
        if self.account is None:
            return
        # Kept only now. Kept at registration, quitting before this page would open the week at the
        # next launch and the recovery codes would never be shown again.
        self._keep_session()
        self.load_week(current_week_start())

    def logout(self) -> None:
        # Forgotten first, so a sign-out that fails to reach the server still leaves nothing to resume.
        self._forget_session()
        account_id = None if self.account is None else self.account["id"]
        ticket = self._begin()
        self._say("Signing out…")

        def finish() -> None:
            if not self._alive(ticket):
                return
            if account_id is not None:
                self.focus_store.pop(account_id, None)
            self.client.reset()
            self._clear_local()
            self.busy = False
            self.busy_changed.emit(False)
            self.account_changed.emit(None)
            self.week_changed.emit()
            self.focus_changed.emit()
            self._say("Signed out.")

        if self.client.account is None:
            finish()
            return
        self.client.request("POST", "/api/auth/logout", None, lambda _data: finish(), lambda _error: finish())

    def load_week(
        self, week_start: str | None = None, *, discard: bool = False, said: str = "This week."
    ) -> None:
        """Load a week from the server. `said` is what the status line says once it is loaded."""
        if self.account is None:
            return
        if self.busy:
            return
        start = week_start or current_week_start()
        if discard:
            self._drafts.pop(start, None)
        elif start == self.week_start and self._held():
            return
        else:
            parked = self._drafts.get(start)
            if parked is not None and (
                parked["dirty"] or parked["dirty_assignments"] or parked["pending_save"]
            ):
                if start != self.week_start:
                    if self._held():
                        self._drafts[self.week_start] = self._week_snapshot()
                    self._restore_week(parked)
                    self._drafts.pop(start, None)
                    self._say("This week.")
                    self._refresh_view()
                    self.week_changed.emit()
                    self._restore_focus()
                    self._drop_missing_focus()
                return
        previous = self.week_start
        ticket = self._begin()
        self._say("Loading…")

        def week_ok(data: dict) -> None:
            if not self._alive(ticket) or self.client.account is None:
                return
            self._load_assignments(ticket, previous, data, said)

        def failed(error: ApiError) -> None:
            if not self._alive(ticket):
                return
            # The week on screen did not change, so Day view must not stay on a day outside it.
            if monday_of(self.selected_day) != self.week_start:
                self._ensure_selected_day()
                self._refresh_view()
            self._fail(ticket, error)
            self.week_changed.emit()

        self.client.request("GET", f"/api/week?week_start={start}", None, week_ok, failed)

    def _assignments_url(self, week_start: str) -> str:
        return f"/api/assignments?week_start={week_start}&include_completed=true"

    def _load_assignments(self, ticket: int, previous: str, week: dict, said: str = "This week.") -> None:
        loaded = week["week_start"]

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            if loaded != previous:
                if self._held():
                    self._drafts[previous] = self._week_snapshot()
                self._undo.clear()
                self._redo.clear()
            elif self.revision != week["revision"]:
                mark_stale(self._undo, loaded)
                mark_stale(self._redo, loaded)
            self._drafts.pop(loaded, None)
            self.blocks = list(week["blocks"])
            self.revision = week["revision"]
            self.week_start = loaded
            self.dirty = False
            self.conflict = False
            self.pending_save = None
            self._pending_step = None
            self.trace = None
            self.assignments = {item["id"]: item for item in data["assignments"]}
            self.dirty_assignments.clear()
            self._committed_blocks = deepcopy(self.blocks)
            self._committed_assignments = deepcopy(self.assignments)
            self._ensure_selected_day()
            self._say(said)
            self._refresh_view()
            self.week_changed.emit()
            self._restore_focus()
            self._drop_missing_focus()
            self._fetch_weeks()
            self._fetch_routines()
            self._fetch_preferences()
            self._fetch_restore_points()
            self._fetch_recovery_status()

        def failed(error: ApiError) -> None:
            if not self._alive(ticket):
                return
            if monday_of(self.selected_day) != self.week_start:
                self._ensure_selected_day()
                self._refresh_view()
            self._fail(ticket, error)
            self.week_changed.emit()

        self.client.request("GET", self._assignments_url(loaded), None, ok, failed)

    def reload(self) -> None:
        self.pending_save = None
        self.dirty = False
        self.conflict = False
        self.dirty_assignments.clear()
        self.load_week(self.week_start, discard=True, said="Reloaded this week.")

    def _touch(self, label: str | None = None, keep: set[str] | frozenset[str] = frozenset()) -> None:
        if label:
            self._history_label = label
        self.blocks, lost = settle_placements(self.blocks, self.assignments, self.week_start, keep)
        self.blocks = clear_stale_pins(self.blocks)
        for note in lost:
            self.needs_time[note["block_id"]] = note["message"]
        self._forget_settled_notes()
        self.dirty = True
        self.conflict = False
        self.pending_save = None
        self.trace = None
        self.week_changed.emit()
        if lost:
            self.plan_conflicts.emit(lost)

    def _forget_settled_notes(self) -> None:
        waiting = {
            block["id"]
            for block in self.blocks
            if block.get("kind") == "flexible" and not block.get("completed") and not block.get("start")
        }
        self.needs_time = {key: value for key, value in self.needs_time.items() if key in waiting}

    def plan_notes(self) -> dict | None:
        """The last plan's explanations, or after an edit the reason each session lost its time."""
        if self.trace is not None:
            return self.trace
        if not self.needs_time:
            return None
        return {
            "placed": [],
            "explanations": [{"block_id": key, "message": value} for key, value in self.needs_time.items()],
        }

    def add_block(self, block: dict, *, scope: str = "series", day: int | None = None) -> None:
        validated = TimeBlock.model_validate(block).model_dump(mode="json")
        self.blocks = apply_block_edit(self.blocks, validated, scope=scope, day=day)
        self._touch("editing " + validated["title"], keep={validated["id"]})

    def add_homework(self, assignment: dict, *, days: list[int] | None = None) -> None:
        payload = {key: value for key, value in assignment.items() if key in Assignment.model_fields}
        payload.setdefault("revision", 0)
        known = self.assignments.get(payload.get("id"))
        if known is not None:
            # A dialog that stayed open across a focus credit holds an older copy. As in the web
            # client's saveHomework, an edit never sets the revision or the focus counters.
            for key in ("revision", "focus_minutes", "focus_sessions"):
                payload[key] = known.get(key) or 0
        body = Assignment.model_validate(payload).model_dump(mode="json")
        sessions = [item for item in self.blocks if item.get("assignment_id") == body["id"]]
        # One session as long as the old estimate is the homework's only planned time, so it follows
        # the new estimate. Spread, pasted or partly planned sessions keep the lengths already chosen.
        whole = (
            len(sessions) == 1
            and known is not None
            and sessions[0]["duration_min"] == known.get("estimate_min")
        )
        blocks = []
        for item in self.blocks:
            if item.get("assignment_id") != body["id"]:
                blocks.append(item)
                continue
            session = deepcopy(item)
            session["title"] = body["title"]
            if whole:
                session["duration_min"] = body["estimate_min"]
            session["priority"] = body["priority"]
            session["energy"] = body["energy"]
            if body.get("category") is not None:
                session["category"] = body["category"]
            if days is not None and len(sessions) == 1 and not session.get("start"):
                session["days"] = days
            if "fixed_at" in assignment and not session.get("completed"):
                self._fix_session(session, assignment["fixed_at"])
            blocks.append(TimeBlock.model_validate(session).model_dump(mode="json"))
        if not sessions:
            session = {
                "id": str(uuid4()),
                "title": body["title"],
                "kind": "flexible",
                "duration_min": body["estimate_min"],
                "days": days if days is not None else session_days(self.week_start, body["due"]),
                "priority": body["priority"],
                "energy": body["energy"],
                "assignment_id": body["id"],
                "category": body.get("category"),
            }
            if assignment.get("fixed_at"):
                self._fix_session(session, assignment["fixed_at"])
            blocks.append(TimeBlock.model_validate(session).model_dump(mode="json"))
        finished = bool(body.get("completed"))
        label = "editing " + body["title"]
        if known is not None and finished != bool(known.get("completed")):
            label = ("finishing " if finished else "reopening ") + body["title"]
            for session in blocks:
                if session.get("assignment_id") != body["id"]:
                    continue
                session["completed"] = finished
                if finished and session.get("kind") == "flexible" and session.get("start"):
                    if len(session["days"]) == 1:
                        session["completed_day"] = session["days"][0]
                elif not finished:
                    session.pop("completed_day", None)
        self.assignments[body["id"]] = body
        self.dirty_assignments.add(body["id"])
        self.blocks = blocks
        edited = {session["id"] for session in blocks if session.get("assignment_id") == body["id"]}
        self._touch(label, keep=edited)

    def _fix_session(self, session: dict, fixed_at: dict | None) -> None:
        """Pin `session` at the day and start the student chose with "Do it at", or with None let
        FlexWeek move it again, as "Let FlexWeek pick a time" does."""
        if fixed_at is None:
            session.pop("pinned", None)
            return
        session.update(start=fixed_at["start"], days=[fixed_at["day"]], pinned=True)
        self.needs_time.pop(session["id"], None)

    def apply_times(self, block_id: str, start_min: int, end_min: int, day: int | None = None) -> bool:
        block = next((item for item in self.blocks if item["id"] == block_id), None)
        if block is None:
            return False
        if is_series(block):
            self._say(SERIES_DRAG_MESSAGE.format(title=block["title"], count=len(block["days"])))
            return False
        updated = apply_block_times(block, start_min, end_min, day)
        if updated is None:
            return False
        # Homework moved by hand is the student's own time, so no plan moves it again.
        homework = updated.get("assignment_id") and updated.get("kind") == "flexible"
        if homework and not updated.get("completed"):
            updated["pinned"] = True
        self.add_block(updated)
        return True

    def set_setup_blocks(self, blocks: list[dict]) -> None:
        """Replace the school and activities setup made with `blocks`, as one Undo step. Anything the
        student added another way stays where it is."""
        kept = [block for block in self.blocks if not is_setup_block(block)]
        made = [TimeBlock.model_validate(block).model_dump(mode="json") for block in blocks]
        self.blocks = kept + made
        self._touch("setting up your week")

    def plan_after_save(self, assignment_id: str) -> None:
        """Give this homework's sessions that need a time one once the save now under way lands."""
        waiting = {
            block["id"]
            for block in self.blocks
            if block.get("assignment_id") == assignment_id
            and not block.get("start")
            and not block.get("completed")
        }
        self._plan_after_save |= waiting

    def place_session(self, block_id: str, day: int, start_min: int) -> bool:
        """Give homework that needs a time the one the student chose, dragged or picked. It is pinned,
        so no plan moves it, and it is one Undo step."""
        block = next((item for item in self.blocks if item["id"] == block_id), None)
        if block is None or block.get("kind") != "flexible" or block.get("completed"):
            return False
        placed = {**block, "start": minutes_to_hhmm(start_min), "days": [day], "pinned": True}
        self.blocks = [placed if item["id"] == block_id else item for item in self.blocks]
        self.needs_time.pop(block_id, None)
        self._touch("placing " + block["title"], keep={block_id})
        return True

    def move_occurrence(
        self, block_id: str, from_day: int, to_day: int, start_min: int, end_min: int
    ) -> bool:
        """One day's copy of a block that repeats, moved on its own, as Daily Scheduler moves its
        separate copies. The other days keep the series; this day becomes a block of its own."""
        block = next((item for item in self.blocks if item["id"] == block_id), None)
        if block is None or not is_series(block) or from_day not in block["days"]:
            return False
        if end_min <= start_min or start_min < DAY_START_MIN or end_min > DAY_END_MIN:
            return False
        before = {item["id"] for item in self.blocks}
        moved = {**block, "start": minutes_to_hhmm(start_min), "duration_min": end_min - start_min}
        blocks = apply_block_edit(self.blocks, moved, scope="occurrence", day=from_day)
        made = next((item["id"] for item in blocks if item["id"] not in before), block_id)
        self.blocks = [{**item, "days": [to_day]} if item["id"] == made else item for item in blocks]
        self._touch("moving " + block["title"] + " on one day", keep={made})
        return True

    def span_drop_problem(
        self, block_id: str, day: int, start: int, end: int, from_day: int = -1
    ) -> str | None:
        """Why a block cannot land here, including a drop onto a different day already past."""
        try:
            target = date.fromisoformat(self.week_start) + timedelta(days=day)
        except ValueError:
            target = None
        now = datetime.fromtimestamp(self.now_ms() / 1000)
        if target is not None and target < now.date() and day != from_day:
            return PAST_DROP
        block = next((item for item in self.blocks if item["id"] == block_id), None)
        if block is None:
            return None
        due = due_point(
            (self.assignments.get(block.get("assignment_id") or "") or {}).get("due"),
            self.week_start,
        )
        return span_problem(self.blocks, block_id, day, start, end, due)

    def copy_last_week_fixed_rows(self) -> list[dict] | None:
        """Fixed times from the previous Monday, offered on a blank week."""
        if self.account is None:
            return None
        try:
            previous = monday_of((date.fromisoformat(self.week_start) - timedelta(days=7)).isoformat())
        except ValueError:
            return None
        source = self._week_local(previous)
        if source is None:
            return None
        blocks = [
            item
            for item in source.get("blocks") or []
            if item.get("kind") == "locked" and item.get("start") and not is_setup_block(item)
        ]
        if not blocks:
            return None
        rows = []
        for item in blocks:
            days = [int(day) for day in item.get("days") or []]
            if not days:
                continue
            copy = copied_fixed_block(item, days, str(uuid4()))
            rows.append(
                {
                    "week_start": self.week_start,
                    "day": days[0],
                    "fixed": True,
                    "block": copy,
                    "group_id": copy["id"],
                    "checked": True,
                    "invalid": "",
                }
            )
        return rows or None

    def date_problem(
        self,
        block_id: str,
        from_iso: str,
        to_iso: str,
        start: str | None = None,
        duration_min: int | None = None,
        assignment_id: str | None = None,
    ) -> str | None:
        """Why this block cannot go on `to_iso`, in the same words as a hours drag, or None."""
        try:
            to_week = monday_of(to_iso)
            from_week = monday_of(from_iso)
            from_day = date.fromisoformat(from_iso).weekday()
            to_day = date.fromisoformat(to_iso).weekday()
        except ValueError:
            return None
        if from_iso == to_iso:
            return None
        block = self._block_on_week(block_id, from_week)
        clock = start
        length = duration_min
        homework_id = assignment_id or ""
        if block is not None:
            if from_day not in (block.get("days") or []) or not block.get("start"):
                return None
            clock = block["start"]
            length = int(block["duration_min"])
            homework_id = block.get("assignment_id") or homework_id
        if not clock or length is None:
            return None
        try:
            start_min = hhmm_to_minutes(clock)
        except ValueError:
            return "That is outside the hours FlexWeek plans in, so it stayed where it was."
        assignment = self.assignments.get(homework_id) or self.assignments.get(block_id)
        due = due_point((assignment or {}).get("due"), to_week)
        return span_problem([], block_id, to_day, start_min, start_min + int(length), due)

    def move_to_date(self, block_id: str, from_iso: str, to_iso: str) -> bool:
        """Move a block to another calendar date. Same week keeps its time; another week is one save
        of both documents. A repeating block moves only the day it was dragged from. The open week
        does not change until the server accepts the write."""
        if self.account is None or self.conflict or self.busy or self.pending_save is not None:
            return False
        try:
            from_week = monday_of(from_iso)
            to_week = monday_of(to_iso)
        except ValueError:
            return False
        if from_iso == to_iso:
            return True
        problem = self.date_problem(block_id, from_iso, to_iso)
        if problem:
            self._say(problem)
            return False
        key = f"move-to-date|{self.account['id']}|{block_id}|{from_iso}|{to_iso}"
        operation_id = self._operation(key)
        source = self._week_local(from_week)
        dest = source if to_week == from_week else self._week_local(to_week)
        if source is not None and dest is not None:
            return self._commit_move_to_date(
                block_id, from_iso, to_iso, from_week, to_week, source, dest, operation_id, key
            )
        ticket = self._begin()
        needed = [week for week in dict.fromkeys((from_week, to_week)) if self._week_local(week) is None]
        fetched: dict[str, dict] = {}

        def fail(error: ApiError) -> None:
            if self._idle(ticket):
                self._say(error.message)
                self.save_finished.emit(False, self.message)

        def proceed() -> None:
            if not self._alive(ticket):
                return
            source_state = self._week_local(from_week) or fetched[from_week]
            dest_state = (
                source_state if to_week == from_week else (self._week_local(to_week) or fetched[to_week])
            )
            launched = self._commit_move_to_date(
                block_id,
                from_iso,
                to_iso,
                from_week,
                to_week,
                source_state,
                dest_state,
                operation_id,
                key,
                ticket=ticket,
            )
            if not launched and self._alive(ticket) and self.busy:
                self._idle(ticket)
                self.save_finished.emit(False, self.message)

        def fetch_next() -> None:
            if not needed:
                proceed()
                return
            week = needed.pop(0)

            def ok(data: dict) -> None:
                if not self._alive(ticket):
                    return
                fetched[week] = data
                fetch_next()

            self.client.request("GET", f"/api/week?week_start={week}", None, ok, fail)

        fetch_next()
        return True

    def _week_local(self, week_start: str) -> dict | None:
        if week_start == self.week_start:
            return {"blocks": self.blocks, "revision": self.revision}
        parked = self._drafts.get(week_start)
        if parked is not None and parked["dirty"]:
            return {"blocks": parked["blocks"], "revision": parked["revision"]}
        return None

    def unsaved_weeks(self) -> dict[str, WeekModel]:
        """Weeks other than the open one that the student changed and left without saving, as they
        have them now, by their Monday."""
        return {
            week_start: build_week(week_start, parked["blocks"], parked["assignments"], parked["trace"])
            for week_start, parked in self._drafts.items()
            if parked["dirty"]
        }

    def _block_on_week(self, block_id: str, week_start: str) -> dict | None:
        state = self._week_local(week_start)
        if state is None:
            return None
        return next((item for item in state["blocks"] if item["id"] == block_id), None)

    def _commit_move_to_date(
        self,
        block_id: str,
        from_iso: str,
        to_iso: str,
        from_week: str,
        to_week: str,
        source: dict,
        dest: dict,
        operation_id: str,
        attempt_key: str,
        ticket: int | None = None,
    ) -> bool:
        from_day = date.fromisoformat(from_iso).weekday()
        to_day = date.fromisoformat(to_iso).weekday()
        block = next((item for item in source["blocks"] if item["id"] == block_id), None)
        if block is None or from_day not in (block.get("days") or []) or not block.get("start"):
            self._say("That block is not on that date.")
            return False
        start = hhmm_to_minutes(block["start"])
        assignment = self.assignments.get(block.get("assignment_id") or "")
        due = due_point((assignment or {}).get("due"), to_week)
        problem = span_problem([], block_id, to_day, start, start + int(block["duration_min"]), due)
        if problem:
            self._say(problem)
            return False
        moved = relocate_block(
            source["blocks"],
            block_id,
            from_day,
            to_day,
            None if to_week == from_week else dest["blocks"],
        )
        if moved is None:
            self._say("That block is not on that date.")
            return False
        source_after, dest_after, _made = moved
        if dest_after is not None and len(dest_after) > MAX_WEEK_BLOCKS:
            self._say(capacity_problem(len(dest["blocks"]), 1, week_label(to_week)))
            return False
        writes = [_week_write(from_week, source_after, source["revision"])]
        step_weeks = [
            {
                "week_start": from_week,
                "before": deepcopy(source["blocks"]),
                "after": deepcopy(source_after),
            }
        ]
        if dest_after is not None:
            writes.append(_week_write(to_week, dest_after, dest["revision"]))
            step_weeks.append(
                {
                    "week_start": to_week,
                    "before": deepcopy(dest["blocks"]),
                    "after": deepcopy(dest_after),
                }
            )
        title = str(block.get("title") or "the block")
        self._pending_step = {
            "label": "moving " + title + " to another date",
            "weeks": step_weeks,
            "assignments": [],
            "stale": False,
        }
        self._history_label = self._pending_step["label"]
        self._move_attempt = attempt_key
        self.pending_save = {
            "weeks": writes,
            "assignments": [],
            "operation_id": operation_id,
            "stay": True,
        }
        self._post_pending(ticket)
        return True

    def delete_homework(self, assignment_id: str) -> bool:
        """Delete homework and every session of it, in every week. The server removes the sessions,
        weeks this window has not loaded included, and says which it removed, so Undo can put each
        back. One Undo step, whichever weeks it touched."""
        item = self.assignments.get(assignment_id)
        if item is None or self.account is None or self.conflict:
            return False
        if self.busy or self.dirty or self.pending_save is not None:
            self._say("Wait a moment: your last change is still saving. Then delete it.")
            return False
        title = str(item.get("title") or "the homework")
        before = deepcopy(self.blocks)
        after = [block for block in self.blocks if block.get("assignment_id") != assignment_id]
        key = f"delete-homework|{self.account['id']}|{assignment_id}|{int(item.get('revision') or 0)}"
        payload = {
            # This week goes as it will be once the sessions are gone. The server stores a week that
            # already reads that way without asking for its revision, which the delete moves on.
            "weeks": [_week_write(self.week_start, after, self.revision)],
            "assignments": [_assignment_write(assignment_id, None, int(item.get("revision") or 0))],
            "operation_id": self._operation(key),
        }
        ticket = self._begin()
        self._say("Deleting " + title + "…")

        def fail(error: ApiError) -> None:
            if self._idle(ticket):
                self._say("Not deleted. " + error.message)
                self.save_finished.emit(False, self.message)

        def ok(data: dict) -> None:
            if not self._alive(ticket):
                return
            results = data.get("assignments") or []
            result = next((entry for entry in results if entry["id"] == assignment_id), {})
            removed: dict[str, list[dict]] = result.get("removed_sessions") or {}
            revisions = {week["week_start"]: week["revision"] for week in result.get("changed_weeks") or []}
            weeks = data.get("weeks") or []
            current = next((week for week in weeks if week["week_start"] == self.week_start), None)
            if current is not None:
                self.blocks = list(current["blocks"])
                self.revision = current["revision"]
            self.assignments.pop(assignment_id, None)
            self.dirty_assignments.discard(assignment_id)
            self._committed_blocks = deepcopy(self.blocks)
            self._committed_assignments = deepcopy(self.assignments)
            for week_start, parked in self._drafts.items():
                if week_start in revisions:
                    kept = [b for b in parked["blocks"] if b.get("assignment_id") != assignment_id]
                    parked["blocks"] = kept
                    parked["revision"] = revisions[week_start]
            step = {
                "label": "deleting " + title,
                "weeks": [
                    {"week_start": self.week_start, "before": before, "after": deepcopy(self.blocks),
                     "revision": self.revision}
                ],
                "assignments": [{"id": assignment_id, "before": deepcopy(item), "after": None}],
                "stale": False,
            }
            others = [week for week in removed if week != self.week_start]

            def finish() -> None:
                if not self._idle(ticket):
                    return
                push_step(self._undo, step)
                self._redo.clear()
                self._attempts.pop(key, None)
                self._say("Deleted " + title + ".")
                self.save_finished.emit(True, self.message)
                self._refresh_view()
                self.week_changed.emit()
                self._fetch_weeks()
                self._refresh_assignments()

            def next_week() -> None:
                if not others:
                    finish()
                    return
                week_start = others.pop(0)

                def got(week: dict) -> None:
                    if not self._alive(ticket):
                        return
                    kept = list(week.get("blocks") or [])
                    step["weeks"].append(
                        {
                            "week_start": week_start,
                            "before": kept + deepcopy(removed[week_start]),
                            "after": kept,
                            "revision": week["revision"],
                        }
                    )
                    next_week()

                # A week that cannot be read is left out of the step: Undo still brings the homework
                # back, with its sessions in every week that could be read.
                path = f"/api/week?week_start={week_start}"
                self.client.request("GET", path, None, got, lambda _error: next_week())

            next_week()

        self.client.request("POST", "/api/changes", payload, ok, fail)
        return True

    def unpin_assignment(self, assignment_id: str) -> bool:
        """Let FlexWeek move this homework's sessions again."""
        changed = False
        blocks = []
        for block in self.blocks:
            if block.get("assignment_id") == assignment_id and block.get("pinned"):
                block = {key: value for key, value in block.items() if key != "pinned"}
                changed = True
            blocks.append(block)
        if not changed:
            return False
        self.blocks = blocks
        title = (self.assignments.get(assignment_id) or {}).get("title") or "homework"
        self._touch("letting FlexWeek move " + title)
        return True

    def delete_block(self, block_id: str, *, scope: str = "series", day: int | None = None) -> None:
        block = next((item for item in self.blocks if item["id"] == block_id), None)
        if block is None:
            return
        if block.get("assignment_id") or scope != "occurrence":
            self.blocks = [item for item in self.blocks if item["id"] != block_id]
        else:
            self.blocks = delete_occurrence(self.blocks, block_id, day)
        if self.selected_block_id == block_id:
            self.select_block(None, None)
        self._touch("deleting " + block["title"])

    def delete_selected(self) -> bool:
        if self.selected_block_id is None:
            return False
        block = next((item for item in self.blocks if item["id"] == self.selected_block_id), None)
        if block is None:
            return False
        scope = "occurrence" if is_series(block) else "series"
        self.delete_block(block["id"], scope=scope, day=self.selected_occurrence_day)
        return True

    def complete_homework(self, assignment_id: str, completed: bool = True) -> None:
        item = self.assignments.get(assignment_id)
        if item is None:
            return
        body = deepcopy(item)
        body["completed"] = completed
        body["completed_at"] = (body.get("completed_at") or local_stamp()) if completed else None
        self.add_homework(body)

    def last_step(self) -> dict | None:
        """The change Undo would take back now."""
        return self._undo[-1] if self._undo else None

    def can_undo(self) -> bool:
        self._drop_stale_history()
        return (
            bool(self._undo)
            and not self.busy
            and not self.conflict
            and not self.dirty
            and self.pending_save is None
        )

    def can_redo(self) -> bool:
        self._drop_stale_history()
        return (
            bool(self._redo)
            and not self.busy
            and not self.conflict
            and not self.dirty
            and self.pending_save is None
        )

    def _drop_stale_history(self) -> None:
        while self._undo and self._undo[-1].get("stale"):
            self._undo.pop()
        while self._redo and self._redo[-1].get("stale"):
            self._redo.pop()

    def _apply_side(self, step: dict, side: str) -> None:
        for week in step.get("weeks") or []:
            if week["week_start"] == self.week_start:
                self.blocks = deepcopy(week[side])
        for entry in step.get("assignments") or []:
            target = entry[side]
            if target is None:
                self.assignments.pop(entry["id"], None)
            else:
                live = self.assignments.get(entry["id"])
                restored = deepcopy(target)
                restored["revision"] = int((live or {}).get("revision") or 0)
                if live is not None:
                    restored["focus_minutes"] = live.get("focus_minutes") or 0
                    restored["focus_sessions"] = live.get("focus_sessions") or 0
                self.assignments[entry["id"]] = restored
            self.dirty_assignments.add(entry["id"])
        self._touch(step["label"])

    def undo(self) -> None:
        if not self.can_undo():
            if self._undo and self._undo[-1].get("stale"):
                self._say("That change cannot be undone. Reload and try again.")
            return
        step = self._undo.pop()
        if step.get("weeks") and not any(week["week_start"] == self.week_start for week in step["weeks"]):
            self._undo.append(step)
            self._say("Undo applies to the week where that change was saved.")
            return
        self._traveling = "undo"
        self._travel_step = step
        self._apply_side(step, "before")
        self.save()

    def redo(self) -> None:
        if not self.can_redo():
            if self._redo and self._redo[-1].get("stale"):
                self._say("That change cannot be redone. Reload and try again.")
            return
        step = self._redo.pop()
        if step.get("weeks") and not any(week["week_start"] == self.week_start for week in step["weeks"]):
            self._redo.append(step)
            self._say("Redo applies to the week where that change was saved.")
            return
        self._traveling = "redo"
        self._travel_step = step
        self._apply_side(step, "after")
        self.save()

    def _post_travel_weeks(
        self,
        extra: list[dict],
        assignments: list[dict],
        operation_id: str | None,
        snapshot_label: str | None,
    ) -> None:
        side = "before" if self._traveling == "undo" else "after"
        writes = [_week_write(self.week_start, self.blocks, self.revision)]
        for entry in extra:
            writes.append(_week_write(entry["week_start"], deepcopy(entry[side]), entry["revision"]))
        self.pending_save = {
            "weeks": writes,
            "assignments": assignments,
            "operation_id": operation_id or str(uuid4()),
            "stay": True,
        }
        if snapshot_label:
            self.pending_save["snapshot_label"] = snapshot_label
        self._post_pending()

    def save(
        self,
        snapshot_label: str | None = None,
        operation_id: str | None = None,
        record_history: bool = True,
        status: str | None = None,
        join: bool = False,
    ) -> None:
        if self.account is None or self.conflict:
            return
        if self.busy:
            return
        # This save's change joins the Undo step before it, as automatic planning does after an add.
        self._join_step = join
        if status is not None:
            self._save_status = status
        if self.pending_save is None:
            writes = []
            for item_id in sorted(self.dirty_assignments):
                item = self.assignments.get(item_id)
                source = item if item is not None else self._committed_assignments.get(item_id)
                revision = int((source or {}).get("revision") or 0)
                writes.append(_assignment_write(item_id, item, revision))
            extra = [
                week
                for week in (self._travel_step or {}).get("weeks") or []
                if week["week_start"] != self.week_start
            ]
            if extra:
                self._post_travel_weeks(extra, writes, operation_id, snapshot_label)
                return
            deleted = {entry["id"] for entry in writes if entry["assignment"] is None}
            revision = _revision_after_deletes(self._committed_blocks, self.revision, deleted)
            self.pending_save = {
                "weeks": [_week_write(self.week_start, self.blocks, revision)],
                "assignments": writes,
                "operation_id": operation_id or str(uuid4()),
            }
            if snapshot_label:
                self.pending_save["snapshot_label"] = snapshot_label
            if self._traveling is None and record_history:
                self._pending_step = capture_step(
                    self._history_label,
                    self.week_start,
                    self._committed_blocks,
                    self.blocks,
                    self._committed_assignments,
                    self.assignments,
                    set(self.dirty_assignments),
                )
        self._post_pending()

    def _post_pending(self, ticket: int | None = None) -> None:
        if self.pending_save is None:
            return
        if ticket is None:
            ticket = self._begin()
        held = self._save_status
        if held is None:
            self._say("Saving…")
        destination = None
        written = {week["week_start"] for week in self.pending_save.get("weeks") or []}
        stay = bool(self.pending_save.get("stay"))
        if self.week_start not in written and written and not stay:
            destination = next(iter(written))
        payload = {key: value for key, value in self.pending_save.items() if key != "stay"}

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            current = next(
                (week for week in data.get("weeks") or [] if week["week_start"] == self.week_start),
                None,
            )
            if current is not None:
                self.blocks = list(current["blocks"])
                self.revision = current["revision"]
                self.dirty = False
                self.conflict = False
            for result in data.get("assignments", []):
                self.dirty_assignments.discard(result["id"])
                if result.get("assignment"):
                    stored = dict(result["assignment"])
                    stored["revision"] = result["revision"]
                    self.assignments[result["id"]] = stored
                else:
                    self.assignments.pop(result["id"], None)
            planned = False
            if self._traveling == "undo" and self._travel_step is not None:
                _keep_step_revisions(self._travel_step, data)
                push_step(self._redo, self._travel_step)
                self._say("Undid " + self._travel_step["label"] + ".")
            elif self._traveling == "redo" and self._travel_step is not None:
                _keep_step_revisions(self._travel_step, data)
                push_step(self._undo, self._travel_step)
                self._say("Redid " + self._travel_step["label"] + ".")
            else:
                planned = self._pending_step is not None and self._pending_step is self._plan_step
                if self._pending_step is not None:
                    stored_weeks = {week["week_start"]: week for week in data.get("weeks") or []}
                    for entry in self._pending_step["weeks"]:
                        stored = stored_weeks.get(entry["week_start"])
                        if stored is not None:
                            entry["after"] = deepcopy(stored["blocks"])
                    _keep_step_revisions(self._pending_step, data)
                    for entry in self._pending_step["assignments"]:
                        stored = self.assignments.get(entry["id"])
                        entry["after"] = None if stored is None else deepcopy(stored)
                    if self._join_step:
                        join_step(self._undo, self._pending_step)
                    else:
                        push_step(self._undo, self._pending_step)
                    self._redo.clear()
                if planned:
                    # `planned` says it, with Undo.
                    self.message = held or "Saved."
                else:
                    self._say(held if held is not None else "Saved.")
            self._traveling = None
            self._travel_step = None
            self._pending_step = None
            self._plan_step = None
            self._join_step = False
            self.pending_save = None
            self._save_status = None
            planned_next, self._plan_after_save = self._plan_after_save, set()
            if planned_next:
                # Plan it for me as I add it: the new homework's time, joined to the add in one step.
                QTimer.singleShot(0, lambda: self.solve(only=planned_next, join=True))
            if current is not None:
                self._committed_blocks = deepcopy(self.blocks)
                self._committed_assignments = deepcopy(self.assignments)
            if self._preview_attempt:
                self._attempts.pop(self._preview_attempt, None)
                self._preview_attempt = None
            if self._move_attempt:
                self._attempts.pop(self._move_attempt, None)
                self._move_attempt = None
            for week_start in written:
                if week_start != self.week_start:
                    self._drafts.pop(week_start, None)
            self.save_finished.emit(True, self.message)
            if planned:
                self.planned.emit(self.message)
            if destination is not None:
                self.load_week(destination)
                return
            self._refresh_view()
            self.week_changed.emit()
            self._fetch_weeks()
            self._refresh_assignments()

        def err(error: ApiError) -> None:
            if not self._idle(ticket):
                return
            # A plan waiting on this save must not fire after some later, unrelated one.
            self._plan_after_save = set()
            self._join_step = False
            refused_travel = bool(self._traveling) and error.status == 409
            if self._traveling and self._travel_step is not None:
                if error.status != 409:
                    self.blocks = deepcopy(self._committed_blocks)
                    self.assignments = deepcopy(self._committed_assignments)
                    self.dirty_assignments.clear()
                    self.dirty = False
                    self.pending_save = None
                    self.conflict = False
                if self._traveling == "undo":
                    self._undo.append(self._travel_step)
                else:
                    self._redo.append(self._travel_step)
                self._traveling = None
                self._travel_step = None
            self.conflict = error.status == 409
            if error.status == 409 and self._preview_attempt:
                self._attempts.pop(self._preview_attempt, None)
                self._preview_attempt = None
            if error.status == 409 and self._move_attempt:
                self._attempts.pop(self._move_attempt, None)
                self._move_attempt = None
            self._save_status = None
            self._say("Not saved. " + error.message)
            self.save_finished.emit(False, self.message)
            self.week_changed.emit()
            if refused_travel:
                # The week on screen is the undone one, which the server never stored. Showing it
                # would leave Undo greyed over a week that is not the saved one.
                self.pending_save = None
                self.dirty = False
                self.conflict = False
                self.dirty_assignments.clear()
                self.load_week(
                    self.week_start,
                    discard=True,
                    said="Undo did not go through. Your week was reloaded as it is saved.",
                )

        self.client.request("POST", "/api/changes", deepcopy(payload), ok, err)

    def retry_save(self) -> None:
        if self.pending_save is not None and not self.conflict:
            self.save()

    def solve(self, *, everything: bool = False, only: set[str] | None = None, join: bool = False) -> None:
        """Plan my homework. Homework that already has a time keeps it.

        `everything` is Replan all my homework. `only` finds new times for named work. Nothing is
        placed before now.
        """
        if self.planning:
            return
        if self.pending_save is not None or self.conflict:
            self._say("Wait a moment: your last change is still saving. Then plan again.")
            return
        start = plan_start(self.week_start, datetime.fromtimestamp(self.now_ms() / 1000))
        if start is not None and start[0] > 6:
            self._say(WEEK_OVER)
            return
        payload, targets = solve_request(
            self.blocks, self.assignments, self.week_start, everything=everything, only=only, not_before=start
        )
        if not targets:
            self._say("All your homework already has a time.")
            return
        ticket = self._begin(planning=True)
        self._say("Planning…")

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            original_blocks = self.blocks
            before = self._dump_blocks()
            self.blocks = apply_plan(
                self.blocks, data, targets=targets, assignments=self.assignments, week_start=self.week_start
            )
            sources = {block["id"]: block for block in self.blocks}
            data = {
                **data,
                "placed": [
                    sources.get(item["id"], item)
                    if item.get("kind") == "locked" and item["id"] in sources
                    else item
                    for item in data.get("placed") or []
                ],
            }
            self.trace = data
            placed = sum(1 for item in data["placed"] if item["id"] in targets and item.get("start"))
            waiting = sum(1 for item in data.get("unplaced") or [] if item["id"] in targets)
            # Why each target still has no time is what this plan found, not what the edit that first
            # took its time said: kept, that sentence came back after the next edit and was wrong.
            reasons = {
                item["block_id"]: item["message"]
                for item in data.get("explanations") or []
                if item.get("reason") and item.get("message")
            }
            for block_id in targets:
                if sources.get(block_id, {}).get("start"):
                    self.needs_time.pop(block_id, None)
                elif block_id in reasons:
                    self.needs_time[block_id] = reasons[block_id]
            self._fresh_plan = True
            self.plan_counts = (placed, waiting)
            self.plan_first = first_placed(data, targets)
            split_note = self._apply_auto_split(data)
            changed = self._dump_blocks() != before
            if not changed:
                self.blocks = original_blocks
            if changed and not split_note:
                self._history_label = "planning the week"
            placed_note = plan_sentence(placed, waiting) + split_note
            if not changed and not self.dirty and not self.dirty_assignments:
                self._say(placed_note)
                self.week_changed.emit()
                return
            # Said once its save lands, by `planned`, with Undo. Said now as well, the toast showed it
            # without Undo and then rewrapped it (Grok Bot's 0.17.0 audit, T7).
            self.message = placed_note
            self.week_changed.emit()
            self.dirty = self.dirty or changed
            self.save(status=placed_note, join=join)
            self._plan_step = None if join or not changed else self._pending_step

        self.client.request(
            "POST",
            "/api/solve",
            {
                "blocks": inflate_for_solve(payload, self.preferences),
                "week_start": self.week_start,
            },
            ok,
            lambda error: self._fail(ticket, error),
        )

    def _apply_auto_split(self, trace: dict) -> str:
        """Turn each placed homework block into focus chunks and breaks, when the student asked for
        it. The solver was given room for the breaks before it ran, so the chunks fit where it put
        the block rather than landing on whatever came next."""
        split, count = split_solved(self.blocks, trace, self.preferences)
        if not count:
            return ""
        self.blocks = split
        self._history_label = "the focus split"
        self.dirty = True
        return f" Split {count} into focus chunks."

    def _operation(self, key: str) -> str:
        if key not in self._attempts:
            self._attempts[key] = str(uuid4())
        return self._attempts[key]

    def _dump_blocks(self, blocks: list[dict] | None = None) -> list[dict]:
        return [
            TimeBlock.model_validate(block).model_dump(mode="json")
            for block in (blocks if blocks is not None else self.blocks)
        ]

    def _fetch_weeks(self) -> None:
        if self.account is None:
            return
        self._weeks_ticket += 1
        token = self._weeks_ticket

        def ok(data: dict) -> None:
            if token != self._weeks_ticket or self.account is None:
                return
            self.saved_weeks = list(data.get("weeks") or [])
            self.week_changed.emit()

        self.client.request("GET", "/api/weeks", None, ok, lambda _error: None)

    def _fetch_routines(self) -> None:
        if self.account is None:
            return
        self._routines_ticket += 1
        token = self._routines_ticket

        def ok(data: dict) -> None:
            if token != self._routines_ticket or self.account is None:
                return
            self.routines = {item["id"]: item for item in data.get("routines") or []}
            self.week_changed.emit()

        self.client.request("GET", "/api/routines", None, ok, lambda _error: None)

    def _fetch_preferences(self) -> None:
        if self.account is None:
            return
        self._prefs_ticket += 1
        token = self._prefs_ticket

        def ok(data: dict) -> None:
            if token != self._prefs_ticket or self.account is None:
                return
            self.preferences = data
            self.week_changed.emit()
            self._fetch_timer_tools()

        self.client.request("GET", "/api/preferences", None, ok, lambda _error: None)

    def _refresh_assignments(self) -> None:
        if self.account is None:
            return
        asked = self.week_start
        self._assign_ticket += 1
        token = self._assign_ticket

        def ok(data: dict) -> None:
            if token != self._assign_ticket or self.account is None or self.week_start != asked:
                return
            for item in data.get("assignments") or []:
                if item["id"] in self.dirty_assignments:
                    local = self.assignments.get(item["id"])
                    if local is not None:
                        local["unplanned_min"] = item.get("unplanned_min")
                        local["planned_min"] = item.get("planned_min")
                    continue
                self.assignments[item["id"]] = item
            self.week_changed.emit()

        self.client.request(
            "GET",
            self._assignments_url(asked),
            None,
            ok,
            lambda _error: None,
        )

    def consume_plan_review(self) -> dict | None:
        """The solver's trace, once, for the review panel. Reading a week again must not reopen it."""
        if not self._fresh_plan:
            return None
        self._fresh_plan = False
        return self.trace

    def remaining_for(self, assignment_id: str) -> int:
        return available_homework_minutes(
            self.assignments.get(assignment_id),
            self.blocks,
            self._committed_blocks,
        )

    def paste_destination(self, today: date | None = None) -> tuple[int, str | None] | None:
        if self.selected_block_id and self.selected_occurrence_day is not None:
            source = next((item for item in self.blocks if item["id"] == self.selected_block_id), None)
            if source is not None:
                placed = source if source.get("start") else None
                if placed is None and self.trace:
                    placed = next(
                        (
                            item
                            for item in (self.trace.get("placed") or [])
                            if item["id"] == self.selected_block_id
                            and self.selected_occurrence_day in (item.get("days") or [])
                        ),
                        None,
                    )
                start = placed["start"] if placed and placed.get("start") else None
                return (self.selected_occurrence_day, start if isinstance(start, str) else None)
        if self.planner_view == "day" and monday_of(self.selected_day) == self.week_start:
            day = (date.fromisoformat(self.selected_day) - date.fromisoformat(self.week_start)).days
            return (day, None)
        today = today or date.today()
        if monday_of(today.isoformat()) == self.week_start:
            return (today.weekday(), None)
        return None

    def copy_block(self, block_id: str, day: int | None, scope: str = "auto", *, say: bool = True) -> bool:
        if self.account is None:
            return False
        source = next((item for item in self.blocks if item["id"] == block_id), None)
        if source is None:
            return False
        source_day = day if day is not None else (source.get("days") or [0])[0]
        copy_scope = scope if scope != "auto" else ("occurrence" if is_series(source) else "block")
        label = copy_label(source, source_day, copy_scope)
        items = [clipboard_item(source, source_day, copy_scope, str(uuid4()))]
        self.clipboard = {
            "kind": "block",
            "label": label,
            "items": items,
            "fingerprint": clipboard_fingerprint(items),
        }
        if say:
            self._say(label + " copied. Choose a destination and paste.")
        self.week_changed.emit()
        return True

    def copy_selected(self, scope: str = "auto") -> bool:
        if not self.selected_block_id:
            self._say("Select a block before copying it.")
            return False
        return self.copy_block(self.selected_block_id, self.selected_occurrence_day, scope)

    def copy_day(self, day: int | None = None) -> bool:
        if self.account is None:
            return False
        destination = (day, None) if day is not None else self.paste_destination()
        if destination is None:
            self._say("Select a block or open Day view before copying a day from this week.")
            return False
        chosen = destination[0]
        placed = list((self.trace or {}).get("placed") or [])
        items = []
        for block in self.blocks:
            if not block_occurs_on_day(block, chosen, placed):
                continue
            if block.get("assignment_id") and block.get("completed"):
                continue
            items.append(clipboard_item(block, chosen, "occurrence", str(uuid4())))
        if not items:
            self._say(DAY_FULL[chosen] + " has nothing to copy.")
            return False
        noun = " item" if len(items) == 1 else " items"
        label = f"{DAY_FULL[chosen]} · {len(items)}{noun}"
        self.clipboard = {
            "kind": "day",
            "label": label,
            "items": items,
            "fingerprint": clipboard_fingerprint(items),
        }
        self._say(label + " copied. Choose a destination and paste.")
        self.week_changed.emit()
        return True

    def paste_proposals(
        self,
        target_day: int | None = None,
        target_start: str | None = None,
        *,
        today: date | None = None,
    ) -> list[dict] | None:
        if self.account is None or self.clipboard is None:
            if self.clipboard is None:
                self._say("Copy a block or day before pasting.")
            return None
        destination = (target_day, target_start) if target_day is not None else self.paste_destination(today)
        if destination is None:
            self._say("Select a block or open Day view before pasting into this week.")
            return None
        available = {item_id: self.remaining_for(item_id) for item_id in self.assignments}
        return proposals_from_clipboard(
            self.clipboard["items"],
            kind=self.clipboard["kind"],
            week_start=self.week_start,
            target_day=destination[0],
            target_start=destination[1],
            assignments=self.assignments,
            available=available,
        )

    def duplicate_selected(self, scope: str = "auto") -> list[dict] | None:
        source_id = self.selected_block_id
        day = self.selected_occurrence_day
        if source_id is None:
            self._say("Select a block before duplicating it.")
            return None
        prior = deepcopy(self.clipboard)
        # Nothing is left copied, so nothing says so.
        if not self.copy_block(source_id, day, scope, say=False):
            return None
        rows = self.paste_proposals(day if day is not None else 0, None)
        self.clipboard = prior
        self.week_changed.emit()
        return rows

    def confirm_preview(
        self,
        rows: list[dict],
        *,
        label: str,
        snapshot_label: str | None = None,
        operation_id: str | None = None,
        attempt_key: str | None = None,
        existing: list[dict] | None = None,
        destination: str | None = None,
        said: str | None = None,
    ) -> bool:
        """Add the checked rows. `said` is what the status line says once they are saved."""
        if self.account is None or self.conflict:
            return False
        checked = [row for row in rows if row.get("checked")]
        if not checked:
            self._say("Select at least one item before saving.")
            return False
        if any(row.get("invalid") for row in checked):
            self._say("Uncheck what cannot be added before saving.")
            return False
        op_id = operation_id or (self._operation(attempt_key) if attempt_key else str(uuid4()))
        groups = merge_preview_rows(rows, op_id)
        if not groups:
            self._say("There is nothing available to add.")
            return False
        by_week: dict[str, list[dict]] = {}
        for group in groups:
            by_week.setdefault(group["week_start"], []).append(group["block"])
        if attempt_key:
            self._preview_attempt = attempt_key
        if list(by_week) == [self.week_start]:
            added = by_week[self.week_start]
            problem = capacity_problem(len(self.blocks), len(added), week_label(self.week_start))
            if problem:
                self._say(problem)
                return False
            self.blocks = list(self.blocks) + added
            self._touch(label)
            self.save(snapshot_label=snapshot_label, operation_id=op_id, status=said)
            return True
        self._commit_groups(
            by_week,
            label=label,
            snapshot_label=snapshot_label,
            operation_id=op_id,
            said=said,
        )
        return True

    def _commit_groups(
        self,
        by_week: dict[str, list[dict]],
        *,
        label: str,
        snapshot_label: str | None,
        operation_id: str,
        said: str | None = None,
    ) -> None:
        needed = [week for week in by_week if week != self.week_start]
        ticket = self._begin()
        fetched: dict[str, dict] = {}

        def fail(error: ApiError) -> None:
            self._fail(ticket, error)

        def proceed() -> None:
            if not self._alive(ticket):
                return
            writes = []
            current_after = None
            for week, added in by_week.items():
                if week == self.week_start:
                    blocks = list(self.blocks) + added
                    revision = self.revision
                    current_after = blocks
                else:
                    data = fetched[week]
                    blocks = list(data["blocks"]) + added
                    revision = data["revision"]
                if len(blocks) > MAX_WEEK_BLOCKS:
                    if self._idle(ticket):
                        self._say(capacity_problem(len(blocks) - len(added), len(added), week_label(week)))
                    return
                writes.append(_week_write(week, blocks, revision))
            if current_after is not None:
                self.blocks = current_after
                self._history_label = label
                self.dirty = True
                self.conflict = False
                self._pending_step = capture_step(
                    label,
                    self.week_start,
                    self._committed_blocks,
                    self.blocks,
                    self._committed_assignments,
                    self.assignments,
                    set(),
                )
            payload: dict = {"weeks": writes, "assignments": [], "operation_id": operation_id}
            if snapshot_label:
                payload["snapshot_label"] = snapshot_label
            self.pending_save = payload
            if said is not None:
                self._save_status = said
            self._post_pending(ticket)

        def fetch_next() -> None:
            if not needed:
                proceed()
                return
            week = needed.pop()

            def ok(data: dict) -> None:
                if not self._alive(ticket):
                    return
                fetched[week] = data
                fetch_next()

            self.client.request("GET", f"/api/week?week_start={week}", None, ok, fail)

        fetch_next()

    def save_routine(self, name: str, block_ids: list[str] | None = None) -> bool:
        if self.account is None:
            return False
        sources = routine_source_blocks(self.blocks)
        if block_ids is not None:
            allowed = set(block_ids)
            sources = [block for block in sources if block["id"] in allowed]
        title = name.strip()
        if not title or not sources:
            self._say("Name the routine and select at least one fixed commitment.")
            return False
        templates = [routine_template(block, str(uuid4())) for block in sources]
        fingerprint = clipboard_fingerprint(
            [{"block": block, "source_day": 0, "scope": "block"} for block in sources]
        )
        key = f"create-routine|{self.account['id']}|{title}|{fingerprint}"
        routine_id = "r-" + self._operation(key)
        ticket = self._begin()
        self._say("Saving routine…")
        body = {"id": routine_id, "name": title, "blocks": templates, "revision": 0}

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            saved = data.get("routine") or data
            self.routines[saved["id"]] = saved
            self._attempts.pop(key, None)
            self._say("Saved " + saved["name"] + ".")
            self.week_changed.emit()

        self.client.request(
            "PUT",
            f"/api/routines/{quote(routine_id, safe='')}",
            body,
            ok,
            lambda error: self._fail(ticket, error),
        )
        return True

    def delete_routine(self, routine_id: str) -> None:
        routine = self.routines.get(routine_id)
        if self.account is None or routine is None:
            return
        key = f"delete-routine|{self.account['id']}|{routine_id}|{routine['revision']}"
        operation_id = self._operation(key)
        ticket = self._begin()
        path = (
            f"/api/routines/{quote(routine_id, safe='')}?revision={int(routine['revision'])}"
            f"&operation_id={quote(operation_id, safe='')}"
        )

        def ok(_data: dict) -> None:
            if not self._idle(ticket):
                return
            self.routines.pop(routine_id, None)
            self._attempts.pop(key, None)
            self._say("Deleted " + routine["name"] + ".")
            self.week_changed.emit()

        self.client.request("DELETE", path, None, ok, lambda error: self._fail(ticket, error))

    def apply_routine_rows(self, routine_id: str, week_start: str, days: list[int]) -> list[dict] | None:
        routine = self.routines.get(routine_id)
        if routine is None or not days:
            self._say("Choose at least one weekday to copy.")
            return None
        return routine_rows(routine, week_start, days)

    def apply_routine(
        self,
        routine_id: str,
        week_start: str,
        days: list[int],
        rows: list[dict] | None = None,
        existing: list[dict] | None = None,
    ) -> bool:
        routine = self.routines.get(routine_id)
        if self.account is None or routine is None:
            return False
        proposals = rows if rows is not None else self.apply_routine_rows(routine_id, week_start, days)
        if not proposals:
            self._say("There is nothing available to add.")
            return False
        key = (
            f"routine|{self.account['id']}|{routine_id}|{routine['revision']}|"
            f"{week_start}|{','.join(str(day) for day in days)}"
        )
        return self.confirm_preview(
            proposals,
            label="the " + routine["name"] + " routine",
            snapshot_label=restore_point_label("Before applying " + routine["name"] + " to " + week_start),
            operation_id=self._operation(key),
            attempt_key=key,
            existing=existing,
            destination=week_start,
        )

    def unfinished(self) -> list[dict]:
        return unfinished_items(
            self.assignments,
            self.saved_weeks,
            self.week_start,
            self.blocks,
            self._committed_blocks,
        )

    def consume_unfinished(self) -> list[dict]:
        items = self.unfinished()
        if not items or self.week_start in self._seen_unfinished:
            return []
        self._seen_unfinished.add(self.week_start)
        return items

    def plan_unfinished(self, assignment_id: str) -> list[dict] | None:
        item = self.assignments.get(assignment_id)
        minutes = self.remaining_for(assignment_id)
        if item is None or minutes < 15:
            self._say("That homework is already fully planned.")
            return None
        due_day = due_day_in_week(item.get("due"), self.week_start)
        days = days_through(due_day, first_plannable_day(self.week_start))
        block = copied_homework_block(item, days[0] if days else 0, minutes, str(uuid4()))
        block["days"] = days or [0]
        return [
            {
                "week_start": self.week_start,
                "day": block["days"][0],
                "fixed": False,
                "block": block,
                "group_id": block["id"],
                "checked": True,
                "invalid": "",
                "original_duration": minutes,
            }
        ]

    def recover_missed(self, block_id: str, day: int) -> None:
        block = next((item for item in self.blocks if item["id"] == block_id), None)
        if block is None or block.get("kind") != "locked" or day not in (block.get("days") or []):
            return
        if day in (block.get("missed_days") or []):
            self.save()
            return
        ticket = self._begin()
        self._say("Replanning after the miss…")

        def run(previous: list[dict]) -> None:
            payload = {
                "week_start": self.week_start,
                "blocks": self._dump_blocks(),
                "recover": {
                    "missed_block_id": block_id,
                    "missed_day": day,
                    "previous_placed": previous,
                },
            }

            def ok(trace: dict) -> None:
                if not self._idle(ticket):
                    return
                target = next((item for item in self.blocks if item["id"] == block_id), None)
                if target is None:
                    return
                missed = sorted(set(target.get("missed_days") or []) | {day})
                target["missed_days"] = missed
                self.blocks = apply_plan(
                    self.blocks, trace, assignments=self.assignments, week_start=self.week_start
                )
                self._touch("the replan")
                self.trace = trace
                self.save()

            self.client.request(
                "POST",
                "/api/solve",
                payload,
                ok,
                lambda error: self._fail(ticket, error),
            )

        if self.trace and self.trace.get("placed"):
            run(self._dump_blocks(self.trace["placed"]))
            return
        if any(is_planned(block) for block in self.blocks):
            run(self._dump_blocks(self.scheduled_blocks()))
            return

        def base_ok(trace: dict) -> None:
            if not self._alive(ticket):
                return
            run(self._dump_blocks(trace.get("placed") or []))

        self.client.request(
            "POST",
            "/api/solve",
            {"week_start": self.week_start, "blocks": self._dump_blocks()},
            base_ok,
            lambda error: self._fail(ticket, error),
        )

    def preview_running_late(self, minutes: int, now: datetime | None = None) -> None:
        moment = now or datetime.now()
        refusal = running_late_refusal(
            week_start=self.week_start,
            now=moment,
            dirty=self.dirty,
            conflict=self.conflict,
            block_count=len(self.blocks),
        )
        if refusal:
            self._say(refusal)
            return
        if minutes not in (15, 30, 60):
            self._say("Choose 15, 30 or 60 minutes.")
            return
        from_start = late_from_start(moment.hour * 60 + moment.minute)
        day = moment.weekday()
        ticket = self._begin()
        self._say("Replanning…")

        def run(previous: list[dict]) -> None:
            payload = {
                "week_start": self.week_start,
                "blocks": self._dump_blocks(),
                "running_late": {
                    "day": day,
                    "minutes": minutes,
                    "from_start": from_start,
                    "previous_placed": previous,
                },
            }

            def ok(trace: dict) -> None:
                if not self._idle(ticket):
                    return
                operation_id = str(uuid4())
                self.late_preview = {
                    "trace": trace,
                    "operation_id": operation_id,
                    "week_start": self.week_start,
                    "block": running_late_block(day, from_start, minutes, late_id(operation_id)),
                    "stale": False,
                }
                moved = len(trace.get("moves") or [])
                unplaced = len(trace.get("unplaced") or [])
                self._say(f"{moved} tasks move · {unplaced} tasks no longer fit")
                self.week_changed.emit()

            self.client.request(
                "POST",
                "/api/solve",
                payload,
                ok,
                lambda error: self._fail(ticket, error),
            )

        if self.trace and self.trace.get("placed"):
            run(self._dump_blocks(self.trace["placed"]))
            return
        if any(is_planned(block) for block in self.blocks):
            run(self._dump_blocks(self.scheduled_blocks()))
            return

        def base_ok(trace: dict) -> None:
            if not self._alive(ticket):
                return
            run(self._dump_blocks(trace.get("placed") or []))

        self.client.request(
            "POST",
            "/api/solve",
            {"week_start": self.week_start, "blocks": self._dump_blocks()},
            base_ok,
            lambda error: self._fail(ticket, error),
        )

    def accept_running_late(self) -> bool:
        preview = self.late_preview
        if preview is None or preview.get("stale") or preview.get("week_start") != self.week_start:
            return False
        if len(self.blocks) >= MAX_WEEK_BLOCKS:
            self._say("This week already has 100 blocks. Remove one before recording a late start.")
            return False
        self.blocks = apply_plan(
            [*self.blocks, preview["block"]],
            preview["trace"],
            assignments=self.assignments,
            week_start=self.week_start,
        )
        self._touch("running late")
        self.trace = preview["trace"]
        self.save(operation_id=preview["operation_id"])
        self.late_preview = None
        return True

    def preview_spread(self, assignment_id: str, session_min: int, from_date: str) -> None:
        item = self.assignments.get(assignment_id)
        if item is None or item.get("completed"):
            return
        ticket = self._begin()
        self._say("Working out sessions…")

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            sessions = data.get("sessions") or []
            remaining = int(data.get("remaining_min") or 0)
            if not sessions:
                if remaining:
                    self._say(
                        f"{length_label(remaining)} remains, but it does not fit the 15-minute planning grid."
                    )
                else:
                    self._say("All of this homework is already focused or planned.")
                self.spread_preview = None
                return
            rows = []
            total = 0
            for index, session in enumerate(sessions):
                duration = int(session["duration_min"])
                total += duration
                group_id = f"spread-{uuid4()}-{index:x}"
                block = copied_homework_block(item, session["days"][0], duration, group_id)
                rows.append(
                    {
                        "week_start": session["week_start"],
                        "day": session["days"][0],
                        "fixed": False,
                        "block": block,
                        "group_id": group_id,
                        "checked": True,
                        "invalid": "",
                    }
                )
            # Time, not a count of sessions, and the deadline as a student says it: this read
            # "3 sessions · 180 minutes ready to add before 2026-09-27T23:59."
            summary = f"{length_label(total)} ready to add before {due_label(item['due'], self.week_start)}."
            if remaining:
                summary += (
                    f" {length_label(remaining)} cannot fit the 15-minute grid and has not been "
                    "dropped from the homework total."
                )
            self.spread_preview = {
                "assignment_id": assignment_id,
                "rows": rows,
                "summary": summary,
                "from_date": from_date,
                "session_min": session_min,
            }
            self._say(summary)
            self.week_changed.emit()

        self.client.request(
            "POST",
            f"/api/assignments/{quote(assignment_id, safe='')}/spread",
            {"session_min": session_min, "from_date": from_date},
            ok,
            lambda error: self._fail(ticket, error),
        )

    def confirm_spread(self) -> bool:
        preview = self.spread_preview
        if preview is None or self.account is None:
            return False
        item = self.assignments.get(preview["assignment_id"])
        title = item["title"] if item else "homework"
        key = (
            f"spread|{self.account['id']}|{preview['assignment_id']}|"
            f"{preview['from_date']}|{preview['session_min']}"
        )
        ok = self.confirm_preview(
            preview["rows"],
            label="spreading " + title,
            operation_id=self._operation(key),
            attempt_key=key,
        )
        if ok:
            self.spread_preview = None
        return ok

    def save_availability(
        self,
        protected: list[dict],
        study_windows: list[dict],
        day_cutoff: str | None,
        work_windows: list[dict] | None = None,
    ) -> bool:
        if self.account is None or self.preferences is None:
            return False
        try:
            for window in protected:
                ProtectedWindow.model_validate(window)
            for window in study_windows:
                StudyWindow.model_validate(window)
            if work_windows is not None:
                for window in work_windows:
                    WorkWindow.model_validate(window)
        except ValueError as error:
            self._say(str(error))
            return False
        body = dict(self.preferences)
        body["protected"] = protected
        body["study_windows"] = study_windows
        body["day_cutoff"] = day_cutoff or None
        if work_windows is not None:
            body["work_windows"] = work_windows
        ticket = self._begin()
        self._say("Saving availability…")

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            self.preferences = data
            self._say("Saved availability.")
            self.week_changed.emit()

        self.client.request(
            "PUT",
            "/api/preferences",
            body,
            ok,
            lambda error: self._fail(ticket, error),
        )
        return True

    def _clock(self) -> dict:
        return clock_parts(self.now_ms())

    def scheduled_blocks(self) -> list[dict]:
        if not self.trace:
            return [
                block
                for block in self.blocks
                if block.get("kind") == "locked" or (block.get("kind") == "flexible" and block.get("start"))
            ]
        sources = {block["id"]: block for block in self.blocks}
        merged = []
        for placed in self.trace.get("placed") or []:
            source = sources.get(placed["id"])
            if source is None:
                merged.append(placed)
                continue
            item = dict(source)
            item["days"] = list(placed.get("days") or source.get("days") or [])
            item["start"] = placed.get("start")
            merged.append(item)
        return merged

    def now_next_text(self) -> str:
        clock = self._clock()
        week = monday_of(clock["iso"])
        if week != self.week_start:
            return ""
        return now_next_line(
            now_and_next(self.scheduled_blocks(), clock["day"], clock["minute"]),
            clock["minute"],
        )

    def focus_tasks(self) -> list[dict]:
        return focus_candidates(self.blocks, self.assignments, self.trace)

    def _drop_missing_focus(self) -> None:
        state = self.focus
        announce = self._focus_after_restore
        self._focus_after_restore = False
        if state is None or not state.get("blockId") or state.get("weekStart") != self.week_start:
            return
        exists = any(
            item["id"] == state["blockId"]
            and (not state.get("assignmentId") or item.get("assignment_id") == state["assignmentId"])
            for item in self.blocks
        )
        if exists:
            return
        self._reset_focus()
        if announce:
            self._say(
                "Schedule restored. The previous focus timer was stopped because "
                "its session no longer exists."
            )

    def _persist_focus(self) -> None:
        if self.account is None:
            return
        payload = persist_payload(self.focus)
        if payload is None:
            self.focus_store.pop(self.account["id"], None)
        else:
            self.focus_store[self.account["id"]] = payload

    def _reset_focus(self, persist: bool = True) -> None:
        self.focus = None
        self._focus_busy = False
        self._pending_focus = None
        if persist:
            self._persist_focus()
        self.focus_changed.emit()

    def _restore_focus(self) -> None:
        if self.account is None or self.focus is not None:
            return
        saved = self.focus_store.get(self.account["id"])
        state = restore_state(saved, assignments=self.assignments, blocks=self.blocks, now_ms=self.now_ms())
        if state is None:
            self.focus_store.pop(self.account["id"], None)
            return
        expired = state.pop("expired", False)
        self.focus = state
        self._persist_focus()
        self.focus_changed.emit()
        if expired and state["phase"] == "work":
            self.advance_focus(completed=True)
        elif expired:
            self.focus = set_phase(state, "work", self.preferences, self.now_ms())
            self.focus["running"] = False
            self.focus["remainingMs"] = remaining_ms(self.focus, self.now_ms())
            self._say("The break ended while FlexWeek was closed. Press Resume to focus again.")
            self._persist_focus()
            self.focus_changed.emit()

    def start_quick_focus(self, *, replace: bool = False) -> bool:
        return self.start_focus(None, None, replace=replace, quick=True)

    def start_focus(
        self,
        block_id: str | None,
        day: int | None = None,
        *,
        replace: bool = False,
        quick: bool = False,
    ) -> bool:
        if self.account is None or self.busy or self._focus_busy:
            return False
        if quick:
            target = {
                "weekStart": self.week_start,
                "blockId": None,
                "assignmentId": None,
                "day": None,
                "start": None,
                "title": "Quick focus",
            }
        else:
            block = next((item for item in self.blocks if item["id"] == block_id), None)
            if block is None or block.get("completed") or block.get("pomodoro_role") == "break":
                self._say("Place an unfinished work block before starting focus.")
                return False
            placed = block if block.get("start") else None
            if placed is None and self.trace:
                placed = next(
                    (
                        item
                        for item in (self.trace.get("placed") or [])
                        if item["id"] == block_id and (day is None or day in (item.get("days") or []))
                    ),
                    None,
                )
            if placed is None or not placed.get("start"):
                self._say("Place an unfinished work block before starting focus.")
                return False
            target = {
                "weekStart": self.week_start,
                "blockId": block_id,
                "assignmentId": block.get("assignment_id"),
                "day": (placed.get("days") or [day])[0],
                "start": placed["start"],
                "title": block["title"],
            }
        if self.focus is not None and not replace:
            self._pending_focus = {**target, "quick": quick, "block_id": block_id, "day": day}
            self.focus_replace_needed.emit(self.focus["title"], target["title"])
            return False
        self.focus = begin_state(target, self.preferences, self.now_ms())
        self._pending_focus = None
        self._persist_focus()
        self.focus_changed.emit()
        return True

    def confirm_replace_focus(self) -> bool:
        pending = self._pending_focus
        if pending is None:
            return False
        return self.start_focus(
            pending.get("block_id"),
            pending.get("day"),
            replace=True,
            quick=bool(pending.get("quick")),
        )

    def toggle_focus_pause(self) -> None:
        if self.focus is None or self._focus_busy or self.busy or self.focus.get("phase") == "ended":
            return
        self.focus = pause_state(self.focus, self.now_ms())
        self._persist_focus()
        self.focus_changed.emit()

    def reset_focus(self) -> None:
        self._reset_focus()

    def focus_elapsed_min(self) -> int:
        """Whole minutes of the work session running or paused on this week, which are credited to
        the homework only when it ends."""
        state = self.focus
        if state is None or state.get("phase") != "work" or state.get("weekStart") != self.week_start:
            return 0
        spent = phase_duration_ms("work", self.preferences) - remaining_ms(state, self.now_ms())
        return max(0, spent) // 60_000

    def tick_focus(self) -> None:
        if self.focus is None or not self.focus.get("running"):
            return
        if int(self.focus.get("endsAt") or 0) <= self.now_ms():
            self.focus["running"] = False
            self.focus["remainingMs"] = 0
            self.advance_focus(completed=True)
            return
        self.focus_changed.emit()

    def advance_focus(self, completed: bool) -> None:
        if self.focus is None or self._focus_busy or self.focus.get("phase") == "ended":
            return
        self._focus_busy = True
        try:
            if self.focus["phase"] == "work":
                if completed:
                    self.credit_focus_session()
                if self.focus is None:
                    return
                self.focus["cycles"] = int(self.focus.get("cycles") or 0) + (1 if completed else 0)
                assignment_id = self.focus.get("assignmentId")
                if completed and assignment_id and assignment_id in self.assignments:
                    self.focus["phase"] = "ended"
                    self.focus["running"] = False
                    self.focus["remainingMs"] = 0
                    self._persist_focus()
                    self.focus_changed.emit()
                    self.alerts.emit(
                        [
                            {
                                "title": "Focus session finished",
                                "body": self.focus["title"],
                                "kind": "focus",
                                "tone": "soft",
                            }
                        ]
                    )
                    return
                self.focus = self._enter_phase(
                    self.focus, break_phase(int(self.focus.get("cycles") or 0), self.preferences)
                )
            else:
                self.focus = self._enter_phase(self.focus, "work")
            self._persist_focus()
            self.focus_changed.emit()
        finally:
            self._focus_busy = False

    def _enter_phase(self, state: dict, phase: str) -> dict:
        """Move to a phase and announce it, which is what the web's setFocusPhase does. The tone is
        the web's: bright going into work, soft going into a break."""
        moved = set_phase(state, phase, self.preferences, self.now_ms())
        self.alerts.emit(
            [
                {
                    "title": FOCUS_PHASE_LABEL.get(phase, "Focus"),
                    "body": moved.get("title") or "",
                    "kind": "focus",
                    "tone": "bright" if phase == "work" else "soft",
                }
            ]
        )
        return moved

    def credit_focus_session(self) -> None:
        state = self.focus
        if state is None or not state.get("blockId"):
            return
        work_min = int((self.preferences or DEFAULT_TIMERS).get("timer_work_min") or 30)
        if state.get("assignmentId"):
            assignment = self.assignments.get(state["assignmentId"])
            updated = credit_target(state, assignment, None, work_min)
            if updated is None:
                self._say(
                    "This homework did not load, so the focus time was not counted. "
                    "Reload the week and try again."
                )
                return
            self.assignments[updated["id"]] = updated
            self.dirty_assignments.add(updated["id"])
        else:
            if state.get("weekStart") != self.week_start:
                return
            block = next((item for item in self.blocks if item["id"] == state["blockId"]), None)
            updated = credit_target(state, None, block, work_min)
            if updated is None:
                return
            self.blocks = [updated if item["id"] == updated["id"] else item for item in self.blocks]
        self.dirty = True
        self.pending_save = None
        self.save(record_history=False)

    def finish_focused_homework(self) -> bool:
        state = self.focus
        if state is None or state.get("phase") != "ended" or self.busy or self._focus_busy:
            return False
        assignment_id = state.get("assignmentId")
        if not assignment_id or assignment_id not in self.assignments:
            return False
        if state.get("weekStart") != self.week_start:
            self.load_week(state["weekStart"])
            return False
        block = next((item for item in self.blocks if item["id"] == state.get("blockId")), None)
        if block is not None and block.get("kind") == "flexible":
            if (
                state.get("start")
                and isinstance(state.get("day"), int)
                and state["day"] in (block.get("days") or [])
            ):
                block["start"] = state["start"]
                # A finished day is only valid on a finished block, and finishing the homework below
                # checks every session it has before marking any of them.
                block["completed"] = True
                block["completed_day"] = state["day"]
            elif not isinstance(block.get("completed_day"), int):
                block["start"] = None
        self.complete_homework(assignment_id, True)
        self._reset_focus()
        self.save()
        return True

    def add_focus_time(self, minutes: int) -> bool:
        state = self.focus
        if state is None or state.get("phase") != "ended" or self.busy or self._focus_busy:
            return False
        assignment = self.assignments.get(state.get("assignmentId"))
        if assignment is None or minutes not in more_time_choices(int(assignment.get("estimate_min") or 0)):
            self._say("Choose how much more time it needs.")
            return False
        assignment["estimate_min"] = int(assignment["estimate_min"]) + minutes
        self.dirty_assignments.add(assignment["id"])
        self.focus = self._enter_phase(state, break_phase(int(state.get("cycles") or 0), self.preferences))
        self._history_label = "adding time to " + assignment["title"]
        self.dirty = True
        self.pending_save = None
        self._persist_focus()
        self.focus_changed.emit()
        self.save()
        return True

    def take_focus_break(self) -> bool:
        state = self.focus
        if state is None or state.get("phase") != "ended" or self._focus_busy:
            return False
        self.focus = self._enter_phase(state, break_phase(int(state.get("cycles") or 0), self.preferences))
        self._persist_focus()
        self.focus_changed.emit()
        return True

    def _today_reminder_source(self, today_monday: str) -> tuple[list[dict], dict | None] | None:
        if self.week_start == today_monday:
            return self.blocks, self.trace
        parked = self._drafts.get(today_monday)
        if parked is not None:
            return parked["blocks"], parked.get("trace")
        if self._reminder_week == today_monday:
            return self._reminder_blocks, self._reminder_trace
        return None

    def _due_block_alerts(
        self, blocks: list[dict], trace: dict | None, clock: dict, prefs: dict
    ) -> tuple[list[dict], list[dict]]:
        """Today's reminders, and the songs of blocks that are starting."""
        notices: list[dict] = []
        lead = reminder_lead_min(prefs)
        # A bad saved link is left out here, as it is when the alarm rings.
        default_link = self.spotify_url(prefs.get("default_spotify_url") or "") or None
        sound_is_spotify = prefs.get("alarm_tone") == "spotify"
        due = due_reminders(
            blocks=blocks,
            trace=trace,
            today_iso=clock["iso"],
            now_min=clock["minute"],
            lead_min=lead,
            fired=self.fired_reminders,
            default_link=default_link,
            sound_is_spotify=sound_is_spotify,
        )
        for item in due:
            self.fired_reminders.add(item["key"])
            notices.append({"title": item["title"], "body": item["body"], "kind": "reminder"})
        songs = due_songs(
            blocks=blocks,
            trace=trace,
            today_iso=clock["iso"],
            now_min=clock["minute"],
            lead_min=lead,
            played=self.played_songs,
            default_link=default_link,
            sound_is_spotify=sound_is_spotify,
        )
        self.played_songs.update(song["id"] for song in songs)
        return notices, songs

    def _request_today_reminders(self, today_monday: str) -> None:
        if self._reminder_fetching == today_monday:
            return
        self._reminder_fetching = today_monday
        self._reminder_ticket += 1
        token = self._reminder_ticket

        def ok(data: dict) -> None:
            if token != self._reminder_ticket or self.account is None:
                return
            self._reminder_fetching = None
            if self.week_start == today_monday or today_monday in self._drafts:
                self._emit_cached_today_reminders(today_monday)
                return
            self._reminder_week = data.get("week_start") or today_monday
            self._reminder_blocks = list(data.get("blocks") or [])
            self._reminder_trace = None
            self._emit_cached_today_reminders(today_monday)

        def failed(_error: ApiError) -> None:
            if token != self._reminder_ticket:
                return
            self._reminder_fetching = None

        self.client.request("GET", f"/api/week?week_start={today_monday}", None, ok, failed)

    def _emit_cached_today_reminders(self, today_monday: str) -> None:
        prefs = self.preferences or {}
        if not prefs.get("reminders_enabled"):
            return
        clock = self._clock()
        if monday_of(clock["iso"]) != today_monday:
            return
        source = self._today_reminder_source(today_monday)
        if source is None:
            return
        notices, songs = self._due_block_alerts(source[0], source[1], clock, prefs)
        if notices:
            self.alerts.emit(notices)
        for song in songs:
            self._enqueue_alarm(song)

    def check_alerts(self) -> None:
        if self.account is None:
            return
        clock = self._clock()
        notices: list[dict] = []
        songs: list[dict] = []
        prefs = self.preferences or {}
        if prefs.get("reminders_enabled"):
            today_monday = monday_of(clock["iso"])
            source = self._today_reminder_source(today_monday)
            if source is None:
                self._request_today_reminders(today_monday)
            else:
                notices, songs = self._due_block_alerts(source[0], source[1], clock, prefs)
        queued, self.snoozed_alarms, self.last_alarm_check = due_alarms(
            alarms=[*(prefs.get("alarms") or []), *self._snoozed_songs.values()],
            today_iso=clock["iso"],
            weekday=clock["day"],
            now_ms=clock["now_ms"],
            midnight_ms=clock["midnight_ms"],
            last_check_ms=self.last_alarm_check,
            fired=self.fired_alarms,
            snoozed=self.snoozed_alarms,
        )
        if notices:
            self.alerts.emit(notices)
        for alarm in (*songs, *queued):
            self._enqueue_alarm(alarm)

    def _enqueue_alarm(self, alarm: dict) -> None:
        alarm_id = alarm.get("id")
        if self.active_alarm is not None and self.active_alarm.get("id") == alarm_id:
            return
        if any(item.get("id") == alarm_id for item in self.alarm_queue):
            return
        if self.active_alarm is None:
            self.active_alarm = alarm
            self.alarm_due.emit(alarm)
            return
        self.alarm_queue.append(alarm)

    def finish_alarm(self, snooze: bool = False) -> None:
        alarm = self.active_alarm
        self.active_alarm = None
        if snooze and alarm is not None:
            self.snoozed_alarms[alarm["id"]] = snooze_until(self.now_ms())
        if alarm is not None and alarm.get("block"):
            # A block's song is in no list of alarms, so the snooze has to keep it to ring it again.
            if snooze:
                self._snoozed_songs[alarm["id"]] = alarm
            else:
                self._snoozed_songs.pop(alarm["id"], None)
        nxt = self.alarm_queue.pop(0) if self.alarm_queue else None
        self.active_alarm = nxt
        self.alarm_due.emit(nxt)

    def spotify_url(self, value: str | None = None) -> str:
        from backend.models import valid_spotify_url

        raw = value
        if raw is None:
            block = next((item for item in self.blocks if item["id"] == self.selected_block_id), None)
            raw = (block or {}).get("spotify_url") or (self.preferences or {}).get("default_spotify_url")
        try:
            return valid_spotify_url(raw) or ""
        except ValueError:
            return ""

    def save_preferences(self, updates: dict) -> bool:
        if self.account is None or self.preferences is None:
            return False
        body = dict(self.preferences)
        body.update(updates)
        if "theme_pack" in body:
            body["theme"] = pack_axis(body.get("theme_pack") or "system")
        ticket = self._begin()
        self._say("Saving preferences…")

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            self.preferences = data
            self._say("Saved preferences.")
            self.week_changed.emit()

        self.client.request("PUT", "/api/preferences", body, ok, lambda error: self._fail(ticket, error))
        return True

    def preview_timer_split(self, duration_min: int) -> None:
        if self.account is None or self.preferences is None:
            return
        ticket = self._begin()

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            self.split_preview = data
            self.week_changed.emit()

        self.client.request(
            "POST",
            "/api/timer-split-preview",
            {
                "duration_min": duration_min,
                "timer_work_min": self.preferences.get("timer_work_min"),
                "timer_break_min": self.preferences.get("timer_break_min"),
                "timer_long_break_min": self.preferences.get("timer_long_break_min"),
                "timer_long_break_every": self.preferences.get("timer_long_break_every"),
            },
            ok,
            lambda error: self._fail(ticket, error),
        )

    def _fetch_timer_tools(self) -> None:
        if self.account is None:
            return

        def presets(data: dict) -> None:
            self.timer_presets = list(data.get("presets") or [])

        def limits(data: dict) -> None:
            self.reminder_limits = dict(data)
            self.week_changed.emit()

        self.client.request("GET", "/api/timer-presets", None, presets, lambda _error: None)
        self.client.request("GET", "/api/reminder-limits", None, limits, lambda _error: None)

    def _fetch_recovery_status(self) -> None:
        if self.account is None:
            return

        def ok(data: dict) -> None:
            self.recovery_remaining = int(data.get("remaining") or 0)
            self.week_changed.emit()

        def storage(data: dict) -> None:
            self.storage_info = data

        self.client.request("GET", "/api/auth/recovery-status", None, ok, lambda _error: None)
        self.client.request("GET", "/api/storage-info", None, storage, lambda _error: None)

    def recover(self, username: str, code: str, password: str) -> None:
        ticket = self._begin()
        self._say("Recovering account…")

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            self.client.set_account(data)
            self.account = {"id": data["id"], "username": data["username"]}
            self._keep_session()
            self.account_changed.emit(self.account)
            self.load_week(self.week_start, discard=True)

        self.client.request(
            "POST",
            "/api/auth/recover",
            {"username": username, "code": code, "password": password},
            ok,
            lambda error: self._fail(ticket, error),
        )

    def change_password(self, current_password: str, new_password: str) -> None:
        ticket = self._begin()
        self._say("Changing password…")

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            if data.get("id"):
                self.client.set_account(data)
                self.account = {"id": data["id"], "username": data["username"]}
                # The new password came with a new session, and the kept one no longer works.
                self._keep_session()
            self._say("Password replaced.")
            self.week_changed.emit()

        self.client.request(
            "POST",
            "/api/auth/password",
            {"current_password": current_password, "new_password": new_password},
            ok,
            lambda error: self._fail(ticket, error),
        )

    def replace_recovery_codes(self, password: str) -> None:
        ticket = self._begin()
        self._say("Replacing recovery codes…")

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            codes = list(data.get("recovery_codes") or [])
            self.recovery_remaining = int(data.get("remaining") or len(codes))
            self.recovery_codes.emit(codes)
            self._say("Save these replacement recovery codes.")

        self.client.request(
            "POST",
            "/api/auth/recovery-codes",
            {"password": password},
            ok,
            lambda error: self._fail(ticket, error),
        )

    def delete_account(self, password: str) -> None:
        ticket = self._begin()
        self._say("Deleting account…")

        def ok(_data: dict) -> None:
            if not self._alive(ticket):
                return
            self._forget_session()
            self.client.reset()
            self._clear_local()
            self.busy = False
            self.busy_changed.emit(False)
            self.account_changed.emit(None)
            self.week_changed.emit()
            self._say("Account deleted.")

        self.client.request(
            "DELETE",
            "/api/auth/account",
            {"password": password},
            ok,
            lambda error: self._fail(ticket, error),
        )

    def _fetch_restore_points(self) -> None:
        if self.account is None:
            return

        def ok(data: dict) -> None:
            self.restore_points = list(data.get("restore_points") or data.get("points") or [])
            self.week_changed.emit()

        self.client.request("GET", "/api/restore-points", None, ok, lambda _error: None)

    def create_restore_point(self, label: str) -> None:
        if self.account is None or not label.strip():
            self._say("Give the restore point a name.")
            return
        key = f"create-restore|{self.account['id']}|{label.strip()}"
        ticket = self._begin()
        self._say("Saving restore point…")

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            point = data.get("restore_point") or data
            self.restore_points = [point] + [
                item for item in self.restore_points if item.get("id") != point.get("id")
            ]
            self.restore_points = self.restore_points[:20]
            self._say("Saved restore point " + point.get("label", label) + ".")
            self.week_changed.emit()

        self.client.request(
            "POST",
            "/api/restore-points",
            {"label": label.strip(), "operation_id": self._operation(key)},
            ok,
            lambda error: self._fail(ticket, error),
        )

    def preview_restore_point(self, point_id: str, on_preview=None) -> None:
        if self.account is None:
            return
        ticket = self._begin()

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            self.restore_preview = data
            self.week_changed.emit()
            if on_preview is not None:
                on_preview()

        def err(error: ApiError) -> None:
            if self._alive(ticket):
                self.restore_preview = None
            self._fail(ticket, error)

        self.client.request(
            "GET",
            f"/api/restore-points/{quote(point_id, safe='')}/preview",
            None,
            ok,
            err,
        )

    def apply_restore_point(self, point_id: str) -> None:
        preview = self.restore_preview
        if self.account is None or preview is None or preview.get("id") != point_id:
            self._say("Preview the restore point first.")
            return
        key = f"restore|{self.account['id']}|{point_id}"
        ticket = self._begin()
        self._say("Restoring…")

        def ok(_data: dict) -> None:
            if not self._idle(ticket):
                return
            self.restore_preview = None
            self._undo.clear()
            self._redo.clear()
            self._focus_after_restore = True
            self._say("Restored.")
            self.load_week(self.week_start, said="Restored.")
            self._fetch_restore_points()

        def err(error: ApiError) -> None:
            if self._alive(ticket) and error.status == 409:
                self.restore_preview = None
            self._fail(ticket, error)

        self.client.request(
            "POST",
            f"/api/restore-points/{quote(point_id, safe='')}/restore",
            {"state_token": preview["state_token"], "operation_id": self._operation(key)},
            ok,
            err,
        )

    def export_account(self, password: str, on_snapshot) -> None:
        if self.account is None or self.dirty or self.dirty_assignments:
            self._say("Save, retry or download your unsaved changes before transferring account data.")
            return
        ticket = self._begin()

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            on_snapshot(data)
            self._say("Account file ready. Keep it private.")

        self.client.request(
            "POST",
            "/api/account-export",
            {"password": password},
            ok,
            lambda error: self._fail(ticket, error),
        )

    def preview_account_import(self, snapshot: dict, on_preview=None) -> None:
        if self.account is None or self.dirty or self.dirty_assignments:
            self._say("Save, retry or download your unsaved changes before transferring account data.")
            return
        ticket = self._begin()

        def ok(data: dict) -> None:
            if not self._idle(ticket):
                return
            self.transfer_preview = {"snapshot": snapshot, **data}
            self.week_changed.emit()
            if on_preview is not None:
                on_preview()

        def err(error: ApiError) -> None:
            if self._alive(ticket):
                self.transfer_preview = None
            self._fail(ticket, error)

        self.client.request(
            "POST",
            "/api/account-import/preview",
            {"snapshot": snapshot},
            ok,
            err,
        )

    def apply_account_import(self) -> None:
        preview = self.transfer_preview
        if self.account is None or preview is None:
            return
        if self.dirty or self.dirty_assignments:
            self._say("Save, retry or download your unsaved changes before transferring account data.")
            return
        key = f"import|{self.account['id']}|{preview.get('state_token')}"
        ticket = self._begin()

        def ok(_data: dict) -> None:
            if not self._idle(ticket):
                return
            self.transfer_preview = None
            self._undo.clear()
            self._redo.clear()
            self._say("Imported account data.")
            self.load_week(self.week_start, discard=True)
            self._fetch_restore_points()

        def err(error: ApiError) -> None:
            if self._alive(ticket) and error.status == 409:
                self.transfer_preview = None
            self._fail(ticket, error)

        self.client.request(
            "POST",
            "/api/account-import",
            {
                "snapshot": preview["snapshot"],
                "state_token": preview["state_token"],
                "operation_id": self._operation(key),
            },
            ok,
            err,
        )

    def week_file(self) -> dict:
        return export_week_payload(self.week_start, self.blocks, self.assignments)

    def day_file(self, day: int) -> dict:
        return export_day_payload(self.week_start, day, self.blocks, self.assignments)

    def import_week_file(self, raw: str, *, replace: bool | None = None) -> bool:
        parsed = parse_import_payload(raw)
        if parsed.get("error"):
            self._say(parsed["error"])
            return False
        target = parsed.get("week_start") or self.week_start
        if target != self.week_start:
            self._say(
                "This file is for "
                + week_label(target)
                + ". Open that week and import without changing other weeks?"
            )
            return False
        plan = plan_imported_homework(
            parsed.get("assignments") or [], parsed.get("blocks") or [], self.week_start, self.assignments
        )
        mode = "merge" if parsed.get("format") == "flexweek-day" else "replace"
        if replace is False:
            mode = "merge"
        if replace is True:
            mode = "replace"
        if mode == "replace" and self.blocks and replace is not True:
            self._say(
                "Replace blocks in "
                + week_label(self.week_start)
                + " with the import? Other weeks stay untouched."
            )
            return False
        try:
            merged = merge_imported_blocks(self.blocks, plan["blocks"], mode, parsed.get("day"))
        except ValueError as error:
            self._say(str(error) + " Nothing was imported.")
            return False
        if len(merged) > MAX_WEEK_BLOCKS:
            self._say(
                week_label(self.week_start)
                + " would exceed 100 blocks. Uncheck an item or remove a block first."
            )
            return False
        for item in plan["create"]:
            self.assignments[item["id"]] = item
            self.dirty_assignments.add(item["id"])
        self.blocks = merged
        self._touch("the import")
        self.save()
        return True
