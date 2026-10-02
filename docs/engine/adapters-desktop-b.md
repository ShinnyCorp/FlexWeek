# Desktop adapters, part B: focus, pomodoro, files

Every function of the three modules, as ADAPTER (encodes, makes one engine call, decodes), LOGIC
(moved into the engine in this slice) or STAYS (cannot move). The coordinator joins this table to the
desktop heading of `adapters.md`.

| module | function | class | reason |
|---|---|---|---|
| focus | phase_duration_ms | ADAPTER | one engine call; int() on the result |
| focus | format_countdown | ADAPTER | one engine call |
| focus | remaining_ms | ADAPTER | one engine call; int() on the result |
| focus | focus_now | ADAPTER | one engine call |
| focus | more_time_choices | ADAPTER | one engine call; was a rebuilt list (LOGIC by shape), now copied as it comes |
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
| pomodoro | _prefs | ADAPTER | json.dumps of the preferences; calls no engine function itself |
| pomodoro | timers | ADAPTER | one engine call; list to tuple of ints |
| pomodoro | plan_for | ADAPTER | one engine call |
| pomodoro | child_title | ADAPTER | one engine call |
| pomodoro | split_children | ADAPTER | one engine call |
| pomodoro | splittable | ADAPTER | one engine call |
| pomodoro | inflate_for_solve | ADAPTER | one engine call |
| pomodoro | split_solved | ADAPTER | one engine call; pair to tuple |
| files | assignment_body | ADAPTER | one engine call, then the pydantic model; no branch or loop |
| files | exportable_block | ADAPTER | one engine call, then the pydantic model; no branch or loop |
| files | _block_models | STAYS | runs the pydantic `TimeBlock` over a list; the model exists only in Python |
| files | _bodies | STAYS | runs the pydantic homework model over the ids the engine named, then raises the failure the engine stopped at; the model exists only in Python |
| files | _exported_blocks | ADAPTER | one engine call, the model, then raise the engine's failure (`is not None`) |
| files | _export_payload | ADAPTER | engine call, model calls, engine call; nothing decided |
| files | referenced_assignments | ADAPTER | one engine call, then the model over its ids |
| files | export_week_payload | LOGIC | moved: which blocks, the payload and its key order are the engine's |
| files | export_day_payload | LOGIC | moved: the day filter, day copies, date and payload are the engine's |
| files | _read_import | STAYS | reads the file's text with Python's own `json`, which accepts NaN and lone surrogates the engine's reader refuses; the empty test uses Python's `str.strip` |
| files | _checked_import | STAYS | runs both pydantic models and turns their exception into text; the model exists only in Python |
| files | _read_list | ADAPTER | json.loads and wire.restore |
| files | parse_import_payload | LOGIC | moved: the refusals, the version and day rules and the rest of the checks are the engine's |
| files | occurrence_import_id | ADAPTER | one engine call |
| files | plan_imported_homework | ADAPTER | one engine call |
| files | merge_imported_blocks | ADAPTER | one engine call |

## What `backend/tests/test_engine_adapters.py` will need for these modules

STAYS (a loop, `try` or a comparison other than `is None` that the rule would flag):
`files._block_models`, `files._bodies`, `files._read_import`, `files._checked_import`.

Why the pydantic ones are STAYS and not another reason: the engine cannot call a Python model, so the
model has to run between two engine calls. Each of these four holds a comprehension, a `try` or a
`strip` around that call. `_exported_blocks` and `parse_import_payload` hold only `is not None` and
calls, so the rule should pass them. If the rule flags `_exported_blocks` for its `raise`, it is the
same shape as `_bodies` and belongs on the list too.
