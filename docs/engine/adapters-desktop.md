# Desktop adapters: what each wrapper function is (calendar, history, update, remind, reuse, weekmodel)

Classes: ADAPTER encodes, calls one engine function and decodes; LOGIC decided something in Python and moved into the engine (the row says where); STAYS cannot move (Qt, file, clock, environment, randomness, or a definition).

The other desktop modules are classified in the files of the parts that did them. `weekmodel` dataclass definitions (`Occurrence`, `Waiting`, `DayQueue`, `WeekModel`) STAY: they are dataclasses.

| Module | Function | Class | Reason |
|---|---|---|---|
| calendar | category_title | ADAPTER | encodes, makes one engine call, decodes |
| calendar | is_series | ADAPTER | encodes, makes one engine call, decodes |
| calendar | monday_of | ADAPTER | encodes, makes one engine call, decodes |
| calendar | date_for_day | ADAPTER | encodes, makes one engine call, decodes |
| calendar | sunday_due | ADAPTER | encodes, makes one engine call, decodes |
| calendar | local_stamp | STAYS | reads the clock (`datetime.now()`); the engine gets the minute as text |
| calendar | occupied_intervals | ADAPTER | list of pairs to list of tuples |
| calendar | create_click_range | ADAPTER | pair to tuple, or None |
| calendar | apply_block_times | ADAPTER | decodes, passing None through |
| calendar | split_occurrence | ADAPTER | decodes the blocks and passes the new id on |
| calendar | delete_occurrence | ADAPTER | encodes, makes one engine call, decodes |
| calendar | apply_block_edit | ADAPTER | encodes, makes one engine call, decodes |
| calendar | relocate_block | ADAPTER | decodes three answers, passing None through |
| calendar | first_plannable_day | STAYS | reads the clock (`date.today()`); the engine gets the date as text |
| calendar | due_day_in_week | LOGIC, moved | an empty deadline gave no day: now `grid::due_day_of` in the engine |
| calendar | days_through | ADAPTER | hands back the engine's list (was `[int(day) ...]`, a no-op) |
| calendar | month_for_view | ADAPTER | encodes, makes one engine call, decodes |
| calendar | shifted_month | ADAPTER | encodes, makes one engine call, decodes |
| calendar | month_anchor_date | ADAPTER | encodes, makes one engine call, decodes |
| calendar | due_soon_for | ADAPTER | encodes, makes one engine call, decodes |
| calendar | placement_on | ADAPTER | turns the engine's "not today" answer into the `NOT_TODAY` sentinel object, which only Python can hold; no rule of its own |
| calendar | agenda_for | ADAPTER | encodes, makes one engine call, decodes |
| calendar | next_action_for | ADAPTER | encodes, makes one engine call, decodes |
| calendar | is_setup_block | ADAPTER | encodes, makes one engine call, decodes |
| calendar | span_problem | ADAPTER | encodes, makes one engine call, decodes |
| calendar | span_clash | ADAPTER | encodes, makes one engine call, decodes |
| calendar | category_icon | ADAPTER | encodes, makes one engine call, decodes |
| history | same_value | ADAPTER | encodes both values as sorted-key JSON |
| history | capture_step | LOGIC, moved | sorted the changed ids: the engine sorts them (`history::capture_step`) |
| history | push_step | LOGIC, moved | the 50-step limit and the trimming of the caller's list: `history_push` in the binding, rule `history::over_limit` |
| history | join_step | LOGIC, moved | whether to fold into the newest step or push: `history::join_into`, applied to the caller's list by `history_join` |
| history | mark_stale | LOGIC, moved | which steps hold the week: `history::touches`, marked in place by `history_mark_stale` |
| remind | _members | ADAPTER | encodes, makes one engine call, decodes |
| remind | reminder_lead_min | ADAPTER | encodes, makes one engine call, decodes |
| remind | start_alert_due | ADAPTER | encodes, makes one engine call, decodes |
| remind | song_due | ADAPTER | encodes, makes one engine call, decodes |
| remind | reminder_key | ADAPTER | encodes, makes one engine call, decodes |
| remind | alarm_key | ADAPTER | encodes, makes one engine call, decodes |
| remind | clock_parts | ADAPTER | hands the engine `datetime.fromtimestamp` and `datetime` (the local zone is read through them); the seconds and milliseconds sums are `remind::seconds_of` and `millis_of` |
| remind | reminder_blocks | ADAPTER | encodes, makes one engine call, decodes |
| remind | due_reminders | ADAPTER | passes the fired container as it is (was `_members`) |
| remind | due_songs | ADAPTER | passes the played container as it is (was `_members`) |
| remind | todays_starts | ADAPTER | rows to tuples, still a generator |
| remind | due_alarms | ADAPTER | hands the engine `datetime.fromisoformat`, the container of fired keys as it is; the binding marks a real set |
| remind | snooze_until | ADAPTER | encodes, makes one engine call, decodes |
| reuse | restore_point_label | ADAPTER | encodes, makes one engine call, decodes |
| reuse | week_label | ADAPTER | encodes, makes one engine call, decodes |
| reuse | floor_slot | ADAPTER | encodes, makes one engine call, decodes |
| reuse | is_homework_session | ADAPTER | encodes, makes one engine call, decodes |
| reuse | session_days | ADAPTER | encodes, makes one engine call, decodes |
| reuse | is_planned | ADAPTER | encodes, makes one engine call, decodes |
| reuse | planning_days | ADAPTER | encodes, makes one engine call, decodes |
| reuse | apply_plan | ADAPTER | set of targets to a list |
| reuse | clear_stale_pins | ADAPTER | encodes, makes one engine call, decodes |
| reuse | held_in_place | ADAPTER | encodes, makes one engine call, decodes |
| reuse | plan_start | LOGIC, moved | hour and minute arithmetic and the half-minute rule: `planning::plan_start_at` |
| reuse | solve_request | LOGIC, moved | `only`, `not_before` and `everything` are read as given by `reuse_solve_request`; the set of targets is a list to set |
| reuse | due_point | ADAPTER | encodes, makes one engine call, decodes |
| reuse | settle_placements | LOGIC, moved | `keep` is read as given by `reuse_settle_placements` |
| reuse | occurrence_days | ADAPTER | encodes, makes one engine call, decodes |
| reuse | session_minutes | ADAPTER | encodes, makes one engine call, decodes |
| reuse | available_homework_minutes | ADAPTER | encodes, makes one engine call, decodes |
| reuse | copied_fixed_block | ADAPTER | encodes, makes one engine call, decodes |
| reuse | copied_homework_block | ADAPTER | encodes, makes one engine call, decodes |
| reuse | clipboard_item | ADAPTER | encodes, makes one engine call, decodes |
| reuse | clipboard_fingerprint | ADAPTER | encodes, makes one engine call, decodes |
| reuse | block_occurs_on_day | ADAPTER | encodes, makes one engine call, decodes |
| reuse | intervals_overlap | ADAPTER | encodes, makes one engine call, decodes |
| reuse | _own_place | ADAPTER | encodes, makes one engine call, decodes |
| reuse | row_conflict | LOGIC, moved | finding the row's own place by identity (`_own_place`) is in the binding |
| reuse | proposals_from_clipboard | ADAPTER | encodes, makes one engine call, decodes |
| reuse | merge_preview_rows | ADAPTER | encodes, makes one engine call, decodes |
| reuse | capacity_problem | ADAPTER | encodes, makes one engine call, decodes |
| reuse | preview_conflict_message | LOGIC, moved | same as `row_conflict` |
| reuse | routine_source_blocks | ADAPTER | encodes, makes one engine call, decodes |
| reuse | routine_template | ADAPTER | encodes, makes one engine call, decodes |
| reuse | routine_rows | ADAPTER | encodes, makes one engine call, decodes |
| reuse | unfinished_items | ADAPTER | encodes, makes one engine call, decodes |
| reuse | late_from_start | ADAPTER | encodes, makes one engine call, decodes |
| reuse | running_late_block | ADAPTER | encodes, makes one engine call, decodes |
| reuse | running_late_refusal | LOGIC, moved | the date is read from `now` by the binding |
| reuse | late_locked_line | ADAPTER | encodes, makes one engine call, decodes |
| reuse | late_id | ADAPTER | encodes, makes one engine call, decodes |
| reuse | copy_label | ADAPTER | encodes, makes one engine call, decodes |
| reuse | planner_title | LOGIC, moved | attribute defaults and the clock sum are in the binding and `remind::seconds_of_millis`; the engine gets `datetime.fromtimestamp` |
| update | install_kind | STAYS | reads `sys.platform`, the environment and `sys.executable`; the engine decides from the values |
| update | asset_name | LOGIC, moved | the unknown-kind `KeyError` is raised by `update_asset_name` |
| update | available | LOGIC, moved | a payload that is not a dict is no release: read by `update_available` |
| update | release_from_page | ADAPTER | encodes, makes one engine call, decodes |
| update | expected_digest | ADAPTER | encodes, makes one engine call, decodes |
| update | verified | ADAPTER | encodes, makes one engine call, decodes |
| update | sanitize_updates | LOGIC, moved | a value `json.dumps` cannot write is read as none given: `update_sanitize` |
| update | due_for_check | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | minute_of | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | set_clock_24h | LOGIC, moved | whether the clock changed: `week_set_clock` compares the object passed with the record the module keeps (`_clock` stays in Python because the tests restore it) |
| weekmodel | clock_text | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | hhmm_text | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | time_format | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | clock_label | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | short_clock | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | range_label | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | length_label | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | planned_line | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | due_label | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | moved_words | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | added_words | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | dated_words | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | Occurrence.minutes | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | Occurrence.live | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | Occurrence.slack_words | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | WeekModel._engine | LOGIC, moved | the handle cache and its tuple-only rule: `week_handle_of` |
| weekmodel | WeekModel.date_of | ADAPTER | tuple to `date` |
| weekmodel | WeekModel.on_day | ADAPTER | the engine answers with positions; they are turned into the held objects |
| weekmodel | WeekModel.load_min | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | WeekModel.open_work | ADAPTER | positions to held objects |
| weekmodel | WeekModel.due_today_unplaced | ADAPTER | positions to held objects |
| weekmodel | WeekModel.leftover_kind | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | WeekModel.leftover_words | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | WeekModel.leftover_parts | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | WeekModel.minutes_left_today | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | WeekModel.day_queue | ADAPTER | positions to held objects, then `DayQueue` |
| weekmodel | build_week | ADAPTER | dicts to `Occurrence` and `Waiting`, lists to tuples |
| remind | _members | LOGIC, moved | removed: the binding writes a set out (`members_of`) |
| reuse | _own_place | LOGIC, moved | removed: `own_place` in the binding |
