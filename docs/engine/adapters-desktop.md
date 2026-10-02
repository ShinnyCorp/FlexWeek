# Desktop adapters: what each wrapper function is

Classes: ADAPTER encodes, calls one engine function and decodes; LOGIC decided something in Python and moved into the engine (the row says where), or still decides in Python (see below); STAYS cannot move (Qt, file, clock, environment, randomness, or a definition).

The eleven desktop wrapper modules under `desktop/native/`, plus `look.py`'s four engine-backed helpers and `version.py`. Dataclass and exception definitions STAY when named in a row.

## Logic still in Python

| Module | Function | Why it stays |
|---|---|---|
| custom_look | readability | The filter, labels and block checks moved to the engine; a loop still asks `look.py` for each category's `resolved_palette`, `category_paint` and `block_paint`, which are not in the engine yet. |

## calendar

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

## custom_look

| Module | Function | Class | Reason |
|---|---|---|---|
| custom_look | LookNameError | STAYS | exception definition; raised from the engine's `LookNameProblem` |
| custom_look | _text_or_none | ADAPTER | turns a value that is not text into none, as the engine takes a pack and an accent |
| custom_look | base_of | ADAPTER | one call, `look_base_of` |
| custom_look | start_custom | ADAPTER | one call, `look_start` |
| custom_look | wear | ADAPTER | one call, `look_wear` |
| custom_look | reset_look | ADAPTER | one call, `look_reset` |
| custom_look | _name | ADAPTER | one call, `look_name`; the engine's error becomes `LookNameError` |
| custom_look | _find | ADAPTER | one call, `look_find` |
| custom_look | sanitize_saved | ADAPTER | one call, `look_saved` |
| custom_look | save_look | ADAPTER | one call, `look_save`; the engine's error becomes `LookNameError` |
| custom_look | free_name | ADAPTER | one call, `free_name`; the engine's error becomes `LookNameError` |
| custom_look | rename_look | ADAPTER | one call, `rename_look`; the engine's error becomes `LookNameError` |
| custom_look | duplicate_look | ADAPTER | one call, `duplicate_look`; the engine's error becomes `LookNameError` |
| custom_look | delete_look | ADAPTER | one call, `delete_look`; the engine's error becomes `LookNameError` |
| custom_look | export_look | ADAPTER | one call, `look_export` |
| custom_look | Imported | STAYS | dataclass |
| custom_look | import_look | STAYS | reads the file's text with Python's own JSON reader (NaN, Infinity, huge integers and lone surrogates are Python-only) and passes the value on; its size guard keeps a file the engine refuses from being parsed |
| custom_look | Problem | STAYS | dataclass |
| custom_look | readability | LOGIC | engine does filter and labels; Python loop for palette and block paint (see Logic still in Python) |
| custom_look | apply_fix | ADAPTER | one call, `look_apply_fix`; the engine reads the problem's own fields |

## files

| Module | Function | Class | Reason |
|---|---|---|---|
| files | assignment_body | ADAPTER | one engine call, then the pydantic model; no branch or loop |
| files | exportable_block | ADAPTER | one engine call, then the pydantic model; no branch or loop |
| files | _block_models | STAYS | runs the pydantic `TimeBlock` over a list; the model exists only in Python |
| files | _bodies | STAYS | runs the pydantic homework model over the ids the engine named, then raises the failure the engine stopped at; the model exists only in Python |
| files | _exported_blocks | ADAPTER | one engine call, the model, then raise the engine's failure (`is not None`) |
| files | _export_payload | ADAPTER | engine call, model calls, engine call; nothing decided |
| files | referenced_assignments | ADAPTER | one engine call, then the model over its ids |
| files | export_week_payload | LOGIC, moved | which blocks, the payload and its key order are the engine's |
| files | export_day_payload | LOGIC, moved | the day filter, day copies, date and payload are the engine's |
| files | _read_import | STAYS | reads the file's text with Python's own `json`, which accepts NaN and lone surrogates the engine's reader refuses; the empty test uses Python's `str.strip` |
| files | _checked_import | STAYS | runs both pydantic models and turns their exception into text; the model exists only in Python |
| files | _read_list | ADAPTER | json.loads and wire.restore |
| files | parse_import_payload | LOGIC, moved | the refusals, the version and day rules and the rest of the checks are the engine's |
| files | occurrence_import_id | ADAPTER | one engine call |
| files | plan_imported_homework | ADAPTER | one engine call |
| files | merge_imported_blocks | ADAPTER | one engine call |

## focus

| Module | Function | Class | Reason |
|---|---|---|---|
| focus | phase_duration_ms | ADAPTER | one engine call; int() on the result |
| focus | format_countdown | ADAPTER | one engine call |
| focus | remaining_ms | ADAPTER | one engine call; int() on the result |
| focus | focus_now | ADAPTER | one engine call |
| focus | more_time_choices | ADAPTER | one engine call; list copied as it comes from the engine |
| focus | persist_payload | ADAPTER | one engine call; None passes through |
| focus | restore_state | ADAPTER | one engine call; None passes through |
| focus | begin_state | ADAPTER | one engine call |
| focus | pause_state | ADAPTER | one engine call |
| focus | set_phase | ADAPTER | one engine call |
| focus | break_phase | ADAPTER | one engine call |
| focus | credit_target | ADAPTER | one engine call; None passes through |
| focus | focus_candidates | ADAPTER | one engine call |
| focus | now_and_next | ADAPTER | one engine call |
| focus | now_next_line | ADAPTER | one engine call |

## history

| Module | Function | Class | Reason |
|---|---|---|---|
| history | same_value | ADAPTER | encodes both values as sorted-key JSON |
| history | capture_step | LOGIC, moved | sorted the changed ids: the engine sorts them (`history::capture_step`) |
| history | push_step | LOGIC, moved | the 50-step limit and the trimming of the caller's list: `history_push` in the binding, rule `history::over_limit` |
| history | join_step | LOGIC, moved | whether to fold into the newest step or push: `history::join_into`, applied to the caller's list by `history_join` |
| history | mark_stale | LOGIC, moved | which steps hold the week: `history::touches`, marked in place by `history_mark_stale` |

## look

| Module | Function | Class | Reason |
|---|---|---|---|
| look | known_pack | ADAPTER | one call, `look_known_pack`, on the caller's own object |
| look | sanitize_custom | ADAPTER | one call, `look_sanitize_custom`; the pair comes back as one JSON list |
| look | sanitize_look | ADAPTER | one call, `look_sanitize_look` |
| look | effective_look | ADAPTER | one call, `look_effective_look`; the engine's `effective_look` is the port (nearest-knob and font rules) |

## pomodoro

| Module | Function | Class | Reason |
|---|---|---|---|
| pomodoro | _prefs | ADAPTER | json.dumps of the preferences; calls no engine function itself |
| pomodoro | timers | ADAPTER | one engine call; list to tuple of ints |
| pomodoro | plan_for | ADAPTER | one engine call |
| pomodoro | child_title | ADAPTER | one engine call |
| pomodoro | split_children | ADAPTER | one engine call |
| pomodoro | splittable | ADAPTER | one engine call |
| pomodoro | inflate_for_solve | ADAPTER | one engine call |
| pomodoro | split_solved | ADAPTER | one engine call; pair to tuple |

## remind

| Module | Function | Class | Reason |
|---|---|---|---|
| remind | reminder_lead_min | ADAPTER | encodes, makes one engine call, decodes |
| remind | start_alert_due | ADAPTER | encodes, makes one engine call, decodes |
| remind | song_due | ADAPTER | encodes, makes one engine call, decodes |
| remind | reminder_key | ADAPTER | encodes, makes one engine call, decodes |
| remind | alarm_key | ADAPTER | encodes, makes one engine call, decodes |
| remind | clock_parts | ADAPTER | hands the engine `datetime.fromtimestamp` and `datetime` (the local zone is read through them); the seconds and milliseconds sums are `remind::seconds_of` and `millis_of` |
| remind | reminder_blocks | ADAPTER | encodes, makes one engine call, decodes |
| remind | due_reminders | ADAPTER | passes the fired container as it is |
| remind | due_songs | ADAPTER | passes the played container as it is |
| remind | todays_starts | ADAPTER | rows to tuples, still a generator |
| remind | due_alarms | ADAPTER | hands the engine `datetime.fromisoformat`, the container of fired keys as it is; the binding marks a real set |
| remind | snooze_until | ADAPTER | encodes, makes one engine call, decodes |

## reuse

| Module | Function | Class | Reason |
|---|---|---|---|
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
| reuse | row_conflict | LOGIC, moved | finding the row's own place by identity is in the binding |
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

## tokens

| Module | Function | Class | Reason |
|---|---|---|---|
| tokens | Shadow | STAYS | dataclass |
| tokens | type_pt | ADAPTER | one call, `tokens_type_pt` |
| tokens | text_knob | ADAPTER | one call, `tokens_text_knob` |
| tokens | linear_rgb | ADAPTER | one call; the list becomes a tuple |
| tokens | hex_from_linear | ADAPTER | one call |
| tokens | oklab_from_linear | ADAPTER | one call; the list becomes a tuple |
| tokens | linear_from_oklab | ADAPTER | one call; the list becomes a tuple |
| tokens | oklab | ADAPTER | one call; the list becomes a tuple |
| tokens | oklch | ADAPTER | one call |
| tokens | _channels | ADAPTER | one call; the list becomes a tuple |
| tokens | mix | ADAPTER | one call |
| tokens | luminance | ADAPTER | one call |
| tokens | contrast | ADAPTER | one call |
| tokens | oklch_of | ADAPTER | one call; the list becomes a tuple |
| tokens | fit_lightness | ADAPTER | one call; the grounds are written with `plain` |
| tokens | mix_oklab | ADAPTER | one call |
| tokens | family_colours | ADAPTER | one call; each list in the result becomes a tuple |

## update

| Module | Function | Class | Reason |
|---|---|---|---|
| update | install_kind | STAYS | reads `sys.platform`, the environment and `sys.executable`; the engine decides from the values |
| update | asset_name | LOGIC, moved | the unknown-kind `KeyError` is raised by `update_asset_name` |
| update | available | LOGIC, moved | a payload that is not a dict is no release: read by `update_available` |
| update | release_from_page | ADAPTER | encodes, makes one engine call, decodes |
| update | expected_digest | ADAPTER | encodes, makes one engine call, decodes |
| update | verified | ADAPTER | encodes, makes one engine call, decodes |
| update | sanitize_updates | LOGIC, moved | a value `json.dumps` cannot write is read as none given: `update_sanitize` |
| update | due_for_check | ADAPTER | encodes, makes one engine call, decodes |

## version

| Module | Function | Class | Reason |
|---|---|---|---|
| version | parse | ADAPTER | one call, `update_parse_version`; tuple from the engine's list |
| version | is_newer | ADAPTER | one call, `update_is_newer` |

## weekmodel

| Module | Function | Class | Reason |
|---|---|---|---|
| weekmodel | Occurrence | STAYS | dataclass definition |
| weekmodel | Waiting | STAYS | dataclass definition |
| weekmodel | DayQueue | STAYS | dataclass definition |
| weekmodel | WeekModel | STAYS | dataclass definition; methods below are adapters or moved logic |
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

## STAYS

- calendar.local_stamp, reads the clock (`datetime.now()`)
- calendar.first_plannable_day, reads the clock (`date.today()`)
- custom_look.LookNameError, exception definition
- custom_look.Imported, dataclass
- custom_look.import_look, Python JSON reader and file size guard before the engine
- custom_look.Problem, dataclass
- files._block_models, pydantic `TimeBlock` model exists only in Python
- files._bodies, pydantic homework model exists only in Python
- files._read_import, Python `json` reader for NaN and lone surrogates
- files._checked_import, pydantic validation and exception text
- tokens.Shadow, dataclass
- update.install_kind, reads platform, environment and executable
- weekmodel.Occurrence, dataclass definition
- weekmodel.Waiting, dataclass definition
- weekmodel.DayQueue, dataclass definition
- weekmodel.WeekModel, dataclass definition (methods are classified above)
