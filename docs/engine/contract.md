# The FlexWeek engine in Rust

FlexWeek's planning logic and its storage move into one Rust library, the engine. The desktop app
keeps its PySide6 interface and its FastAPI server, and calls the engine through a Python module.
A phone app, when there is one, calls the same engine, so the week is planned and stored the same
way on both.

Jonathan approved this on 2026-09-29, as one part of a larger decision: the tooling (fwtest) and the
engine move to Rust now, and the interface stays in Python until the phone app is decided. The
reason is not speed. Measured on 2026-09-28, the planner takes 2 to 55 ms for real weeks, against a
150 ms budget. The reasons are one core for two apps, checks at compile time, and no garbage
collector freeing objects on the server's thread.

This file is the contract. The engine is built and reviewed against it.

## What moves

| Python today | Lines | Moves to | Slice |
|---|---|---|---|
| `backend/slots.py`, `backend/weeks.py` | 240 | `engine::time` | E1 |
| `backend/models.py` (the data, not the HTTP validation) | 660 | `engine::model` | E2 |
| `assignments.py`, `availability.py`, `comfort.py`, `day.py`, `month.py`, `explain.py` | 942 | `engine::plan`, `engine::day` | E2 |
| `restore.py`, `transfer.py`, `limits.py`, `recovery.py` | 162 | `engine::restore`, `engine::recovery` | E2 |
| `backend/solver.py` | 486 | `engine::solver` | E3 |
| `backend/storage.py` | 320 | `store` (SQLite) | E4 |
| `desktop/native/weekmodel.py` | 351 | `engine::week` | E6, later |

What stays in Python: `backend/app.py` (the FastAPI routes), the pydantic model classes in
`backend/models.py` as the checking layer at the HTTP edge and for `desktop/` (the engine's structs
are the data behind them, converted with `model_dump()` and `model_validate()` at the boundary),
everything in `desktop/` apart from its import lines, and every test. The HTTP API does not change.

## Guarantees

1. **Nothing a student can see changes.** For every input, a ported function returns what the
   Python one returned. The HTTP API, its errors, and every word on screen stay the same, character
   for character: sentences the engine builds (explanations, labels, error messages) are compared
   exactly in the differential tests, numbers included, since Rust formats floats and durations
   differently from Python's `str()` unless told to.
2. **Every database keeps working.** The engine opens the same SQLite file, with the same schema and
   migrations. Every stored hash still verifies: passwords are
   `scrypt$32768$8$3$<salt>$<key>` (N 32768, r 8, p 3, 32-byte key, a 16-byte salt as hex), stored
   sign-in tokens are the SHA-256 hex of the token, recovery codes are SHA-256 of
   `flexweek-recovery:` plus the normalised code. A new sign-in token is URL-safe base64 of 32 random
   bytes without padding, as `secrets.token_urlsafe(32)` makes it. Test vectors come from the
   Python functions, and a database written by the Python store is read by the Rust one and the
   other way round. Migrations have one owner at a time: the Python store until E4 lands, the
   Rust store from then on; the other side never migrates.
3. **The app works after every slice.** A slice lands behind the Python function it replaces: the
   Python name stays, its body calls the engine, and the existing tests run unchanged. No slice
   leaves two live implementations of one function in the shipped app.
4. **The core is pure.** `engine` has no file, network, clock or randomness of its own. What it
   needs is passed in: the time now, the solver's deadline, and randomness for recovery codes and
   sign-in tokens. Only `store` touches the disk, and only the Python module touches Python.
5. **Parity is proven, not assumed.** Before a Python body is replaced, a differential test runs the
   Python and Rust versions on generated inputs (Hypothesis) and on every fixture the backend tests
   use, and requires equal outputs. Order is deterministic wherever it can show in a result: the
   engine iterates in the order Python does (insertion order for what Python keeps in a dict,
   stable sorts with the same keys), using `Vec` and `BTreeMap` or an explicit order, never a hash
   map's. The solver keeps Python's search order and is compared only on weeks that both versions
   finish in under half the 150 ms budget, since a week near the budget may run out of time on one
   side and not the other; a plan returned on running out of time is not compared.
6. **Errors keep their types.** Where Python callers catch `ValueError`, `LookupError` or a named
   error, the engine raises the same type with the same message.
7. **The solver lets other threads run.** A solve releases Python's interpreter lock while it
   searches, so the window stays responsive during a plan.

## Shape

```text
engine/                    a Cargo workspace at the repository root
  engine/                  crate `flexweek-engine`: the pure core, no I/O
  store/                   crate `flexweek-store`: SQLite through rusqlite, schema and migrations
  py/                      crate `flexweek-py`: the Python module `flexweek_engine` (PyO3, built by maturin)
```

Data crosses into Python as plain values: dicts, lists, strings and numbers in the shapes the
pydantic models already dump (`model_dump()`), so `app.py` and `desktop/` keep their types. The
engine's own types are Rust structs with serde, named as the Python models are.

## Building and checking

- `cargo fmt --check`, `cargo clippy --workspace -- -D warnings`, `cargo test --workspace` in
  `engine/`. These join spec.md's Validation list in slice E1, with Jonathan's approval as the
  fwtest checks were.
- `maturin develop --release` builds `flexweek_engine` into the checkout's `.venv`. The gate runs
  as today, with the differential tests added to `backend/tests/`.
- The PyInstaller builds ship the compiled module from E1 on, since from E1 the app calls it:
  `test_native_packaging` checks it is in the Linux and Windows bundles, and CI installs a Rust
  toolchain and builds the module on both, as the fwtest contract already requires for Linux.
- Pinned versions: the Rust toolchain in `rust-toolchain.toml`, crates in `Cargo.lock`, and
  maturin in `requirements-dev.txt`.

## Slices

Each slice is one branch, reviewed and merged before the next starts, and ends with the gate green,
the new differential tests green, and the Rust checks passing.

- **E1, the frame and time.** The workspace, the Python module, `slots` and `weeks` ported, the
  differential test harness, and CI building and bundling the module on Linux and Windows. The
  Python `slots` and `weeks` call the engine.
- **E2, the model and the day's logic.** The data types, then `assignments`, `availability`,
  `comfort`, `day`, `month`, `explain`, `limits`, `restore`, `transfer` and `recovery`, in that
  order, each with its differential tests.
- **E3, the planner.** `solve`, `reschedule_after_miss` and `reschedule_running_late`, with the
  interpreter lock released during the search.
- **E4, storage.** `store` with the same schema, migrations, hashes, sessions and throttling. The
  backend API tests run against it unchanged, and the two stores read each other's files.
- **E5, the switch.** The Python bodies that now only call the engine are removed, and their
  callers in `backend/app.py` and `desktop/` import from `flexweek_engine` directly; only import
  lines change in `desktop/`. The pydantic classes stay in `backend/models.py`.
- **E6, later.** `desktop/native/weekmodel.py`, when the phone app needs the same week model.

## Not in scope

The interface, the FastAPI server and the tests stay in Python. The full move to a Rust interface
waits for the phone app. The engine does not add features: anything new goes in after E5, once
there is one implementation to change.
