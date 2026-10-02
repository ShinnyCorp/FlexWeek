# Engine adapters

A backend wrapper is one of three classes.

**ADAPTER.** The body only encodes arguments, calls one engine function, and decodes the result. Turning `None` into a default the original also used, a list into a tuple, or a dict into a dataclass or a pydantic model is still an adapter. So is re-checking a value with a pydantic model.

**LOGIC.** The body decides something a student could see, or computes a value, in Python: a comparison that picks a result, arithmetic on times, a sort, a loop that builds a result, string building, or a rule. That work lives in the engine. The Python left behind is an adapter.

**STAYS.** It cannot move, and only for one of these reasons: it reads the clock, the environment, a file, or randomness (the engine core is pure, so Python reads those and passes them in); it is a dataclass, a `Protocol`, or an exception; it is the pydantic validation the contract keeps in Python (`backend/models.py`, which this table does not list); or it is a method of the connection that only forwards to the Rust connection.

`limits`, `slots`, and `weeks` define no functions. They re-export engine names and constants. `storage.SESSION_SECONDS` stays in Python because `backend/app.py` imports it for the cookie lifetime. Adding that many seconds to the clock reading happens in `open_session`.

The desktop tables use the same three classes. Those modules live in `desktop/native/`. `look.py` is paint; only its four engine helpers are in the table. `test_engine_adapters.py` reads every STAYS row and every row whose class is exactly LOGIC. A row marked `LOGIC, moved` is not exempt: the wrapper has to be clean.

## Backend

| Module | Function | Class | Reason |
| --- | --- | --- | --- |
| assignments | migrated_assignment_id | ADAPTER | Passes two strings to one engine call. |
| assignments | due_from_latest | ADAPTER | Passes the week, the latest instant, and the days to one engine call. |
| assignments | completed_at_for_block | ADAPTER | Encodes the block as JSON and calls the engine once. |
| assignments | due_placement_bound | ADAPTER | One engine call; `None` stays `None`, otherwise the pair becomes ints. |
| assignments | due_slack_point | ADAPTER | One engine call, returned as a pair of ints. |
| assignments | prepare_solve | ADAPTER | Encodes blocks and assignments, one call, then pydantic and tuples. |
| assignments | legacy_session | ADAPTER | One engine call, then a `TimeBlock` and the body dict. |
| assignments | rewrite_session | ADAPTER | One engine call, then `TimeBlock.model_validate`. |
| assignments | planned_minutes_by_id | ADAPTER | Encodes the weeks, one call, values become ints. |
| assignments | unplanned_minutes | ADAPTER | Three ints in, one engine call. |
| assignments | migrate_blocks | ADAPTER | Encodes the blocks, one call, two lists out. |
| availability | add_occupancy | ADAPTER | One engine call, written back over the occupancy list. |
| availability | occupancy_from_windows | ADAPTER | Encodes the windows, one call, list out. |
| availability | lateness_occupancy | ADAPTER | One engine call, list out. |
| availability | study_rank | ADAPTER | Encodes the windows, one call. |
| availability | resolve_work_windows | ADAPTER | `None` stays `None`; an empty list is the engine's to default. One call, then pydantic. |
| availability | session_inside_work_windows | ADAPTER | Encodes the windows, one call. |
| availability | merge_occupancy | ADAPTER | One engine call, list out. |
| availability | spread_sessions | ADAPTER | One engine call; the session text is decoded and the remainder is returned beside it. |
| comfort | snap_minutes | ADAPTER | One `snap_minutes_wide` call. Integers f64 holds exactly keep `plan::snap_minutes`; past 2^53 the engine uses Python's formula. |
| comfort | split_plan | ADAPTER | One engine call, JSON decoded. |
| comfort | preview_split | ADAPTER | One engine call, JSON decoded. |
| day | is_work_session | ADAPTER | Encodes the block, one call, `bool` of the result. |
| day | build_day | ADAPTER | Encodes rows and weeks, one call, then pydantic on sessions and locked blocks. |
| explain | sentence | ADAPTER | Looks up engine copy cached at import, so an unknown code stays a `KeyError`. |
| month | build_month | ADAPTER | Encodes rows and weeks, one call, JSON decoded. |
| recovery | generate_recovery_codes | STAYS | Reads `secrets` for each draw. The binding repeats that draw; the engine accepts or skips the bytes. |
| recovery | recovery_code_matches | ADAPTER | One engine call. ASCII comparison and the non-ASCII `TypeError` live in the engine. |
| restore | canonical | ADAPTER | Encodes the value, one call. |
| restore | state_token | ADAPTER | Encodes the snapshot, one call. |
| restore | diff_snapshots | ADAPTER | Encodes both snapshots, one call, JSON decoded. |
| restore | diff_transfer | ADAPTER | Encodes both snapshots, one call, JSON decoded. |
| solver | _clock | STAYS | Reads `time.perf_counter`. A budget test patches that clock. |
| solver | _clock.elapsed | STAYS | Nested in `_clock`. Turns later readings of the same clock into milliseconds. |
| solver | _points | ADAPTER | `None` stays `None`; otherwise each point becomes a pair or `None` and is encoded. |
| solver | _windows | ADAPTER | `None` stays `None`. An empty list is encoded so the engine can default it. |
| solver | _blocks | ADAPTER | Encodes each block with `model_dump`. |
| solver | solve | ADAPTER | Encodes the plan, passes the clock callable, one call, then `SolveTrace`. |
| solver | reschedule_after_miss | ADAPTER | Encodes the plan, passes the clock callable, one call, then `SolveTrace`. |
| solver | reschedule_running_late | ADAPTER | Encodes the plan, passes the clock callable, one call, then `SolveTrace`. |
| storage | digest | ADAPTER | One engine call. |
| storage | password_hash | STAYS | Reads `secrets` when the caller does not pass a salt. An empty salt counts as missing, as it did before. |
| storage | password_matches | ADAPTER | One engine call. A hash with no salt raises `IndexError` inside the engine. |
| storage | Row | STAYS | `Protocol`. |
| storage | Row.__getitem__ | STAYS | `Protocol` method. |
| storage | Row.__iter__ | STAYS | `Protocol` method. |
| storage | Row.keys | STAYS | `Protocol` method. |
| storage | Cursor | STAYS | `Protocol`. |
| storage | Cursor.lastrowid | STAYS | `Protocol` property. |
| storage | Cursor.fetchone | STAYS | `Protocol` method. |
| storage | Cursor.fetchall | STAYS | `Protocol` method. |
| storage | Cursor.__iter__ | STAYS | `Protocol` method. |
| storage | Connection | STAYS | `Protocol`. |
| storage | Connection.execute | STAYS | Forwards to the Rust connection. |
| storage | Connection.load_assignment_rows | STAYS | Forwards to the Rust connection. |
| storage | Connection.assignment_exists | STAYS | Forwards to the Rust connection. |
| storage | Connection.count_assignments | STAYS | Forwards to the Rust connection. |
| storage | Connection.insert_assignment | STAYS | Forwards to the Rust connection. |
| storage | Connection.save_assignment | STAYS | Forwards to the Rust connection. |
| storage | Connection.delete_assignment | STAYS | Forwards to the Rust connection. |
| storage | Connection.list_account_weeks | STAYS | Forwards to the Rust connection. |
| storage | Connection.save_week | STAYS | Forwards to the Rust connection. |
| storage | Connection.capture_account | STAYS | Forwards to the Rust connection. |
| storage | Connection.prune_restore_points | STAYS | Forwards to the Rust connection. |
| storage | Connection.prune_operations | STAYS | Forwards to the Rust connection. |
| storage | Connection.recall_operation | STAYS | Forwards to the Rust connection. |
| storage | Connection.remember_operation | STAYS | Forwards to the Rust connection. |
| storage | Connection.insert_restore_point | STAYS | Forwards to the Rust connection. |
| storage | Connection.replace_account | STAYS | Forwards to the Rust connection. |
| storage | Connection.replace_recovery_codes | STAYS | Forwards to the Rust connection. |
| storage | Connection.save_routine | STAYS | Forwards to the Rust connection. |
| storage | Connection.delete_routine | STAYS | Forwards to the Rust connection. |
| storage | Connection.list_routines | STAYS | Forwards to the Rust connection. |
| storage | Connection.replace_routines | STAYS | Forwards to the Rust connection. |
| storage | Connection.preference_row | STAYS | Forwards to the Rust connection. |
| storage | Connection.write_preferences | STAYS | Forwards to the Rust connection. |
| storage | Connection.insert_preferences | STAYS | Forwards to the Rust connection. |
| storage | Connection.delete_account | STAYS | Forwards to the Rust connection. |
| storage | Connection.create_session_row | STAYS | Forwards to the Rust connection. |
| storage | Connection.open_session | STAYS | Forwards to the Rust connection. The week-long expiry is applied there. |
| storage | Connection.begin_immediate | STAYS | Forwards to the Rust connection. |
| storage | Connection.begin | STAYS | Forwards to the Rust connection. |
| storage | Connection.enforce_foreign_keys | STAYS | Forwards to the Rust connection. |
| storage | Connection.session_user | STAYS | Forwards to the Rust connection. |
| storage | Connection.insert_user | STAYS | Forwards to the Rust connection. |
| storage | Connection.find_user | STAYS | Forwards to the Rust connection. |
| storage | Connection.password_hash_of | STAYS | Forwards to the Rust connection. |
| storage | Connection.delete_session | STAYS | Forwards to the Rust connection. |
| storage | Connection.recovery_hashes | STAYS | Forwards to the Rust connection. |
| storage | Connection.count_recovery_codes | STAYS | Forwards to the Rust connection. |
| storage | Connection.use_recovery_code | STAYS | Forwards to the Rust connection. |
| storage | Connection.rotate_password | STAYS | Forwards to the Rust connection. |
| storage | Connection.read_week | STAYS | Forwards to the Rust connection. |
| storage | Connection.week_blocks | STAYS | Forwards to the Rust connection. |
| storage | Connection.week_starts | STAYS | Forwards to the Rust connection. |
| storage | Connection.assignment_body | STAYS | Forwards to the Rust connection. |
| storage | Connection.assignment_bodies | STAYS | Forwards to the Rust connection. |
| storage | Connection.list_assignment_rows | STAYS | Forwards to the Rust connection. |
| storage | Connection.list_restore_points | STAYS | Forwards to the Rust connection. |
| storage | Connection.restore_point_body | STAYS | Forwards to the Rust connection. |
| storage | Connection.availability_json | STAYS | Forwards to the Rust connection. |
| storage | Connection.adopt_legacy_deadlines | STAYS | Forwards to the Rust connection. |
| storage | Connection.require_own_assignments | STAYS | Forwards to the Rust connection. |
| storage | Connection.create_restore_point | STAYS | Forwards to the Rust connection. |
| storage | connect | ADAPTER | Opens one engine connection and yields it. Foreign keys are already on. |
| storage | new_preferences | ADAPTER | One `insert_preferences` call at `PREFS_VERSION`. |
| storage | initialize | ADAPTER | One `store_initialize_today` call. The binding reads the clock. |
| storage | delete_account | ADAPTER | Forwards to the connection. |
| storage | create_session | STAYS | Reads `secrets` for the token and `time.time` for the timestamp. Expiry is `open_session`. |
| storage | throttle | STAYS | Reads `time.time` and passes that instant to one engine call. |
| transfer | transfer_apply_envelope | ADAPTER | Encodes the snapshot, one call, JSON decoded. |
| transfer | transfer_apply_bytes | ADAPTER | Encodes the snapshot, one call. |
| transfer | transfer_fits | ADAPTER | Encodes the snapshot, one call. The size cap is the engine's. |

## backend/app.py helpers

`backend/app.py` is the HTTP layer: routes, dependencies, status codes, the pydantic request and response models, and the mapping of an engine status onto an HTTP error stay in Python. The rows below are the helper functions whose decisions moved into the engine (`engine/store/src/rules.rs`); `test_app_helpers_keep_no_engine_logic` checks them with the same rule as the modules above. Route handlers are not checked.

| Module | Function | Class | Reason |
| --- | --- | --- | --- |
| app | adopt_legacy_deadlines | ADAPTER | One connection call. `adopt_legacy_deadlines` in the engine picks the blocks and enforces the cap. Python maps "over the cap" to the 422 and revalidates the blocks. |
| app | encode_new_assignment | ADAPTER | The pydantic check the engine calls for each new assignment, then the stored text. |
| app | rewrite_blocks | ADAPTER | One engine call; the engine picks which blocks take their assignment's fields. |
| app | normalize_stored_block | ADAPTER | The pydantic check the engine calls for each rewritten stored block. |
| app | rewrite_stored_blocks | ADAPTER | One engine call; the engine picks which stored blocks are rewritten. |
| app | assignment_view | ADAPTER | One engine call; the engine adds `planned_min` and `unplanned_min`. |
| app | require_own_assignments | ADAPTER | One connection call; the engine says whether the account holds every id. Python maps "no" to the 422. |
| app | payload_digest | ADAPTER | One engine call; the engine hashes the canonical text. |
| app | insert_restore_point | ADAPTER | One connection call. Python reads `secrets` and the clock and passes both in; the engine names the point, counts, snapshots, protects and prunes. |
| app | preferences_from_row | ADAPTER | One engine call fills every default; `Preferences` is the pydantic check. |
| app | validate_windows | ADAPTER | The pydantic check the engine calls for each window list. |
| app | solve_availability | ADAPTER | One engine call splits the stored text and builds the occupancy; Python revalidates the study and work windows. |
| app | naive_now | STAYS | Reads the clock. |

`upsert_assignment`, `delete_assignment`, `save_week_row`, `upsert_routine`, and `delete_routine` are not in the table and the test does not check them. Each makes one store call and turns the status it gets back into an HTTP error (409, 422, 404) by comparing it with a status word. The store decides the status; the comparison only picks the error. None of the five holds a rule beyond that mapping: the revision check, the cap, and the identical-body shortcut are all in the store.

## Desktop

The eleven desktop wrapper modules, plus `look.py`'s four engine helpers and `version.py`. Dataclass and exception definitions STAY when a row says so. A class row does not cover its methods; those have their own rows.

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
| custom_look | _name | ADAPTER | raw name to `look_name`; the binding decodes text and the core validates it; errors become `LookNameError` |
| custom_look | _find | ADAPTER | one call, `look_find` |
| custom_look | sanitize_saved | ADAPTER | raw value to `look_saved`; the binding decodes a list and the core sanitizes it |
| custom_look | save_look | ADAPTER | raw name to `look_save`; the binding decodes text and the core validates it; errors become `LookNameError` |
| custom_look | free_name | ADAPTER | raw name to `free_name`; the binding decodes text and the core validates it; errors become `LookNameError` |
| custom_look | rename_look | ADAPTER | raw new name to `rename_look`; the binding decodes text and the core validates it; errors become `LookNameError` |
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
| update | install_kind | STAYS | reads `sys.platform`, the environment and `sys.executable`, and resolves the executable and mount paths as the original did; the engine decides from the values |
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
| weekmodel | WeekModel.on_day | ADAPTER | `_ON_DAY_CACHE` holds per-day results for hashable tuple models; misses and unhashable models use engine positions to return the held objects |
| weekmodel | WeekModel.load_min | ADAPTER | `_LOAD_MIN_CACHE` holds per-day totals for hashable tuple models; misses and unhashable models call the engine |
| weekmodel | WeekModel.open_work | ADAPTER | positions to held objects |
| weekmodel | WeekModel.due_today_unplaced | ADAPTER | positions to held objects |
| weekmodel | WeekModel.leftover_kind | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | WeekModel.leftover_words | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | WeekModel.leftover_parts | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | WeekModel.minutes_left_today | ADAPTER | encodes, makes one engine call, decodes |
| weekmodel | WeekModel.day_queue | ADAPTER | positions to held objects, then `DayQueue` |
| weekmodel | build_week | ADAPTER | `_BUILD_WEEK_CACHE` reuses the last encoded inputs; misses call `week_build`, then turn dicts into `Occurrence` and `Waiting` and lists into tuples |

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
- update.install_kind, reads platform, environment and executable, and resolves paths
- weekmodel.Occurrence, dataclass definition
- weekmodel.Waiting, dataclass definition
- weekmodel.DayQueue, dataclass definition
- weekmodel.WeekModel, dataclass definition (methods are classified above)

## Known logic the guard allows for now

`test_engine_adapters.py` also flags a type test (`isinstance` or `type`), `x or default`, a conditional expression, and `if name` / `if not name`. These wrappers already hold one of those, so the guard names them and still fails on any new one. An older shape (a loop, arithmetic, a comparison, a sort) is not in this list.

| Wrapper | Shape | What it holds |
| --- | --- | --- |
| assignments.prepare_solve | branch | a missing deadline stays None while decoding |
| availability.resolve_work_windows | branch | None windows stay None on the way in |
| solver._points | branch | a missing point stays None while encoding |
| calendar.apply_block_times | branch | the engine's None answer stays None |
| calendar.relocate_block | branch | None dest in, None answer out |
| calendar.placement_on | branch | None trace in; the engine's flag becomes NOT_TODAY |
| calendar.agenda_for | branch | None trace and day data stay None on the way in |
| calendar.next_action_for | branch | None day data stays None on the way in |
| calendar.span_problem | type test | the engine is told the due value's Python type |
| custom_look._text_or_none | branch, type test | text stays, anything else becomes None |
| custom_look._name | branch, type test | a non-text name is none for the engine |
| custom_look.sanitize_saved | branch, type test | a non-list file is an empty list |
| custom_look.save_look | branch, type test | a non-text name is an empty string |
| custom_look.free_name | branch, type test | a non-text name is an empty string |
| custom_look.rename_look | branch, type test | a non-text name is an empty string |
| focus.persist_payload | branch | the engine's None answer stays None |
| focus.restore_state | branch | the engine's None answer stays None |
| focus.credit_target | branch | the engine's None answer stays None |
| history.capture_step | branch | the engine's None answer stays None |
| reuse.apply_plan | branch | None targets and assignments stay None on the way in |
| reuse.due_point | branch | the engine's None answer stays None |
| reuse.block_occurs_on_day | branch | None placed blocks stay None on the way in |
| reuse.row_conflict | branch | the engine's None answer stays None |
| update.available | branch | the engine's None answer stays None |
| update.release_from_page | branch | the engine's None answer stays None |
| weekmodel.WeekModel._engine | default, type test | either tuple missing skips the handle cache |
| weekmodel.WeekModel.on_day | default, type test | either tuple missing skips the day cache |
| weekmodel.WeekModel.load_min | default, type test | either tuple missing skips the load cache |
| weekmodel.WeekModel.day_queue | branch | no current block stays None |
| app.adopt_legacy_deadlines | truth test | the engine's "over the cap" becomes the 422 |
| app.require_own_assignments | truth test | the engine's "not owned" becomes the 422 |
| app.insert_restore_point | default | a missing keep-set is an empty list |
