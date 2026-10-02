# Engine adapters

A backend wrapper is one of three classes.

**ADAPTER.** The body only encodes arguments, calls one engine function, and decodes the result. Turning `None` into a default the original also used, a list into a tuple, or a dict into a dataclass or a pydantic model is still an adapter. So is re-checking a value with a pydantic model.

**LOGIC.** The body decides something a student could see, or computes a value, in Python: a comparison that picks a result, arithmetic on times, a sort, a loop that builds a result, string building, or a rule. That work lives in the engine. The Python left behind is an adapter.

**STAYS.** It cannot move, and only for one of these reasons: it reads the clock, the environment, a file, or randomness (the engine core is pure, so Python reads those and passes them in); it is a dataclass, a `Protocol`, or an exception; it is the pydantic validation the contract keeps in Python (`backend/models.py`, which this table does not list); or it is a method of the connection that only forwards to the Rust connection.

`limits`, `slots`, and `weeks` define no functions. They re-export engine names and constants. `storage.SESSION_SECONDS` stays in Python because `backend/app.py` imports it for the cookie lifetime. Adding that many seconds to the clock reading happens in `open_session`.

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
| comfort | snap_minutes | ADAPTER | One `snap_minutes_wide` call. Values that fit in 64 bits keep the old engine rounding; a wider int uses Python's formula in the engine. |
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

The desktop's eleven modules are classified in a later run.
