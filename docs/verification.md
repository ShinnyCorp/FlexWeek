# Verification

Run the source checks from the repository root through `fwtest`, the Rust
test harness in `tools/fwtest` (contract in [tooling/fwtest.md](tooling/fwtest.md)).
Build it with `cargo build --release` in `tools/fwtest`, then:

```bash
tools/fwtest/target/release/fwtest gate
```

It uses the existing Python 3.14 environment at `.venv/bin/python`, or the
interpreter named by `--python` or `FWTEST_PYTHON`. The command runs Ruff, mypy,
all pytest cases, and working, staged and committed-range diff whitespace
checks, at low priority and one suite at a time on the machine. A failed
command, timeout, missing desktop dependency, empty test suite or skipped test
makes it fail. It installs nothing and does not build or publish a binary. Qt
cases use temporary databases and offscreen native widgets.

For environments without the desktop dependencies:

```bash
tools/fwtest/target/release/fwtest gate --backend-only
```

This runs the backend checks and explicitly reports desktop as unverified.
`.github/workflows/verify.yml` runs this variant on pushes and pull requests
using Python 3.14, after building `fwtest` and running its `cargo fmt --check`,
`cargo clippy -- -D warnings` and `cargo test`. The workflow has read-only
repository permissions. Its hosted execution is unverified until the branch is
pushed.
`.github/workflows/codeql.yml` scans Python; it does not replace this gate. The
generic kit CI that ran pyright is not used.

The other `fwtest` commands:

- `fwtest mutate [SPEC ...]` breaks one rule at a time from the specs in
  `scripts/mutations/` (all of them when none is named) and prints `RED`,
  `GREEN` or `PATTERN` per case. It exits 1 if any break survived or a pattern
  was not found exactly once.
- `fwtest rig ...` runs `scripts/rig/drive.py` with the same arguments, then
  stops the hidden session.
- `fwtest run -- CMD` runs any other suite, picture tour or script with the same
  limits and cleanup.
- `fwtest clean` stops processes and restores source files that a killed run
  left behind. Every other command runs it first.

## Coverage map

| Behavior | Automated evidence | Useful next-feature cases |
| --- | --- | --- |
| Accounts, expiry, ownership, CSRF, revision conflicts and retries | `backend/tests/test_accounts.py`, `test_account_edges.py`, `test_week_api.py` | Another account, expired session, stale response and failed save |
| Dated weeks and migration | `backend/tests/test_weeks.py`, `test_migration.py`, `test_week_api.py` | Monday validation, year/DST boundaries, repeat migration, unsaved week navigation |
| Solver placement, priorities and explanations | `backend/tests/test_solver.py`, `test_completed.py`, `test_solver_invariants.py` | Contested capacity with unequal domains, completed work, deadline/earliest bounds, timeout partial results |
| Missed occurrences and recovery | Solver tests; `desktop/tests/test_calendar.py`, `test_history.py` | One day of a series, cross-day movement, completed work, restore/save/reload |
| Grid gestures and event wiring | `desktop/tests/test_calendar.py` | Snap boundaries, cancel, a second pointer, move/resize, double-click, context menu and persisted reload |
| Imports, exports, drafts, categories and completion | `backend/tests/test_phase5.py` | Invalid input, repeat import, maximum merged size, unusual/maximum Unicode IDs, multi-day flexible tasks, completed placement round trip and exported draft reimport |
| Reminder preferences and session cleanup | `backend/tests/test_phase5.py`; `desktop/tests/test_remind.py` | Lead window, solved flexible work, completed/missed filtering, account transition and alert cleanup |
| Stage 6 recovery, identity and account transfer | `backend/tests/test_stage6_api.py`, `test_recovery.py`; `desktop/tests/test_files.py` | One-time code handling, wrong-password session preservation, local/hosted identity, malformed files, named removals, stale previews, replace/reload and deletion |
| Stage 7 month navigation | `backend/tests/test_month_api.py`, `test_weeks.py`, `test_day_api.py`; `desktop/tests/test_calendar.py` | Deadlines, completed work, project indicators, overdue work, empty/error states, stale month/account replies, year and 2000/2099 boundaries, responsive date targets and date-to-Day handoff |
| Stage 3 clipboard, routines, unfinished work and restore points | `backend/tests/test_routines_api.py`, `test_restore_api.py`; `desktop/tests/test_reuse.py`, `test_history.py` | Collision previews, a remaining-time cap shared across a batch, the 100-block limit, operation ids on retry and after 409, stale restore tokens, reload, a second account and a 390px dark-theme carry-forward |
| Desktop origin, local server and native window | `desktop/tests/test_origin.py`, `test_server.py`, `test_native.py`, `test_files.py` | Loopback origin, offline draft download, native Save/Open |
| Native Qt widgets | `desktop/tests/test_native.py`, `test_calendar.py`, `test_history.py`, `test_reuse.py`, `test_focus.py`, `test_look.py`, `test_remind.py`, `test_files.py`, `test_smoke.py`, `test_server.py` native-mode case | Packaging smoke on a real desktop |
| A painted week after setup | Native `--smoke-test` in `desktop/tests/test_smoke.py` | Window grab after a saved week; hosted origin that cannot load |

The generated solver cases use 20 fixed seeds and independent integer-minute
arithmetic. They check purity, candidate days, grid/deadline bounds, occupied
slots, completed work and explanations. They are not an exhaustive proof of
search optimality or a performance benchmark.

Native widget tests drive the Qt window against the real API and reload from
SQLite. Synthetic
pointer events test event wiring but do not prove hardware pointer capture,
touch scrolling or OS notification delivery.

## Adding coverage with a feature

1. Identify the behavior in the map and write a case with a concrete input and
   independently determined output. A fixture captured from current output
   cannot establish that the output is correct.
2. Cover the successful action and its relevant failure boundary. Examples
   include a cancelled gesture, rejected import, failed save, account change or
   exhausted scheduling window.
3. For event-driven UI behavior, extend a native widget case. The integration
   result can include a save and reload so the check covers persistence as well
   as the displayed draft.
   For multi-request actions, also prove retry idempotency: preserve the
   operation key and payload across a failed or ambiguous attempt, then start a
   new operation only after success or an explicit user change.
4. Demonstrate the test failing for the intended defect before fixing it, or
   temporarily remove the behavior in an isolated copy. Inspect the assertion
   mismatch; a missing dependency or syntax exception proves nothing about the
   behavior.
5. Run the full command above. The test glob and pytest discovery pick up new
   tests automatically. Update this map when a new feature needs a new testing
   layer, and record remaining limitations with the handoff.

## Release checks outside the source gate

The full source gate is not a release certification. A packaged Linux build
needs the same create/save/reload and recovery paths exercised through the
packaged executable in a fresh profile. `DESKTOP.md` describes the build and
artifact checks. Windows execution, Safari/iPhone, physical touch, keyboard
accessibility, notification permission/sound and visual contrast remain separate
checks. Native widget tests cover close-to-tray in a source checkout, but the tray icon path
is only proven in the packaged build, because that bug never occurred in a source checkout.

No hosted security audit or production configuration check runs here. Existing
account tests prove their particular isolation/CSRF/revision cases, not the
safety of every deployment.

## Stage 3 evidence

`desktop/tests/test_reuse.py` covers fixed-block collision previews, occurrence and series scope,
day-copy exclusions, homework identity and a remaining-time cap shared across a
batch, keyboard shortcuts that stay off in form fields and behind open dialogs,
routine weekday selection and long routine names, restore-token refresh, the
week kept after a restore, Clear week rollback, and operation ids that repeat
after an unknown response but not after a 409.

Native widget tests in `test_reuse.py` and `test_history.py` drive the same
APIs from the Qt window: copy through a collision preview, routines, unfinished
homework, and restore points. Backend isolation, limits and transactions are in
`test_routines_api.py` and `test_restore_api.py`.

## Findings from the September 8–9 pass

The regression cases reproduced and now protect against:

- Cancelled pointer gestures creating or changing blocks.
- In-page and browser notifications surviving sign-out, solved flexible tasks
  receiving no reminders, and an identical reminder being suppressed in the next account.
- Legacy imports accepting invalid starts or scheduling bounds; day merges
  exceeding the 100-block limit; invalid day envelopes; valid IDs such as
  `__proto__` being rejected, and maximum-length/Unicode IDs drifting from the API.
- A file read crossing an account change and replacing the next account's week.
- A delayed preference response changing the next account's theme.
- Unimportable downloaded drafts.
- Completing a solved task discarding either its spent slot or its original
  candidate days. The persisted completed day now round-trips independently;
  native completion tests cover save/reload/solve.
- A day import duplicating a multi-day flexible assignment, and text/day export
  disagreeing with the placement visible after Solve.
- A second account login discarding the first account's suspended draft.
- Viewing another week silencing reminders for today's loaded week.
- Saving unchanged occurrence fields unnecessarily splitting a recurring block.
- Lower-priority reading beating exam preparation because its placement domain
  was smaller, followed by optional skip branches exhausting the solver budget
  on a feasible energy-sensitive week.

The source findings and platform limitations remaining after review are recorded
in `context.md`. Test totals come from the command output, not a fixed expected
count in this document. The solver timeout test uses a controlled clock to
confirm that budget expiry retains a partial placement and explains unplaced
work; the existing packed-week test checks real elapsed time.
