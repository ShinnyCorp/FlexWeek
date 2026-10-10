# fwtest: the test harness

`fwtest` is one Rust command that runs FlexWeek's checks: the gate, the mutation checks and the
real-pointer rig. It replaces `scripts/verify.py`, `scripts/mutate.py` and the local
`run-alone.sh` queue. The 2,000-odd pytest tests stay in Python. `fwtest` only decides what runs,
when, with how much of the machine, and makes sure everything it started has stopped when it ends.

It exists because on 2026-09-28 the Python tooling froze the developer's displays. Gate runs back to
back used every core at full priority, and a rig's hidden KWin outlived its run by two hours. The
GPU driver stopped flipping frames under the load, and only a suspend brought the screens back.

This file is the contract. The implementation is built and reviewed against it.

## Guarantees

1. **Nothing outlives a job.** Every process a job starts, including grandchildren that detach or
   daemonize (KWin, Xwayland, dbus-daemon, a pytest worker), is stopped when the job ends. That
   holds whether the job ends normally, times out, gets Ctrl+C, or `fwtest` itself receives SIGTERM.
   If `fwtest` receives SIGKILL, the next `fwtest` run cleans up what it left.
2. **The desktop keeps priority.** A job runs at the lowest CPU priority (nice 19), with idle-only
   disk priority, pinned to at most half the machine's cores. Where a systemd user session exists,
   the job also runs in a transient scope with CPU and memory ceilings.
3. **One job at a time on the machine.** Jobs queue on one lock shared by every checkout, because
   the suites share Qt's test-mode files in `~/.qttest`. A job also waits for other agents' suites
   started outside `fwtest`, for up to 30 minutes.
4. **Source files are always restored.** A mutation's edit is undone however the run ends. A run
   that finds an edit left by a killed run restores it before it does anything else. A file under
   `engine/` also leaves a mark. The next clean rebuilds the installed engine module from the
   restored tree, so a killed run does not leave a mutated module either.
5. **Only its own processes are killed.** `fwtest` never matches processes by name or command line.
   It kills a PID only if the PID's start time matches the one it recorded.

## Commands

```text
fwtest gate [--backend-only] [--workers N]
fwtest mutate [SPEC.json ...] [--case NAME] [--engine-build COMMAND] [--no-engine-rebuild]
fwtest rig [--server kwin|xvfb|auto] [ARGS FOR scripts/rig/drive.py ...]
fwtest run [--timeout SECONDS] -- COMMAND [ARGS ...]
fwtest clean
```

- `gate` runs the checks `scripts/verify.py` runs, in the same order: ruff, mypy over `backend`,
  pytest, then `git diff --check` on the working tree, the index, and the committed range from the
  diff base. The diff base is `$VERIFY_BASE_SHA`, then `main`, then `origin/main`, then `HEAD^`,
  skipping any value of all zeroes. Before the Python behavior step, the gate checks every case in
  `scripts/mutations/` that its `old` text occurs exactly once and that its `test` exists (a Python
  `path::function`, or a Rust `cargo:` test in an `engine/**/tests/` file). A miss fails the gate
  before any tests run. pytest gets `-n N` where N is `--workers`, or half the cores
  and at least 2. It prints `VERIFIED: Backend and desktop. Packaged binaries and other platforms
  need separate checks.` (or `VERIFIED: Backend.` with `--backend-only`) only when every step
  passed, as `verify.py` does. The per-step timeout is 900 seconds.
- `mutate` runs every spec in `scripts/mutations/`, or the specs named. `--case` runs one case by
  name. It prints one line per case (`RED`, `GREEN`, `BASE`, `PATTERN`, or `BUILD`, then the spec, the
  case name, and a short detail) and ends with `every mutation was caught` or `N mutation(s)
  SURVIVED`. `RED` is caught. `GREEN`, `BASE`, `PATTERN`, and `BUILD` each count as not caught. `BASE`
  means the case's test was red before any mutation (each test is run once unmutated per run, after
  a clean engine rebuild when a case left a mutated module installed), so the case proves nothing. It exits 1
  if any case was not caught. A file under `engine/` is rebuilt before its test. See
  [Mutating a file under engine/](#mutating-a-file-under-engine).
- `rig` runs `scripts/rig/drive.py` as one contained job. The job starts this checkout's hidden
  session after the stop handlers are installed, so the session is in the job's record and in the
  same scope and limits as the driver. The state file is written as each session process starts.
  `--server` is `kwin`, `xvfb`, or `auto` (the default: KWin when `kwin_wayland` is on `PATH`,
  otherwise Xvfb). That flag is not forwarded to the driver. The driver receives the display, the
  private D-Bus address, and the runs-folder key in its environment. The driver refuses that display
  or that bus when it is the one `fwtest rig` was started with. A display the session itself
  allocated is allowed, including `:0`. `FLEXWEEK_RIG_KEEP` is removed
  before the driver starts, and the run always stops the session afterwards by the PIDs recorded in
  its state file. `fwtest rig --list` does not start a session.
- `run` runs any command as a job, with the guarantees above. It exists for the picture tours and
  the one-off scripts that currently go through `run-alone.sh`.
- `clean` stops every process recorded by a job that is no longer running. It also stops a hidden
  session whenever a job record or a state file names it, including when the job record is already
  gone and only the state file under `/tmp/flexweek-rig/` remains. That is how you stop a stranded
  session by hand. A live rig job in that checkout is left alone. It restores any source file left
  edited by a mutation run and removes the stale records. When `edits/engine-module.json` is
  present and no live job holds the checkout, it then runs the command stored in that mark and
  deletes the mark only after the rebuild succeeds. A failed rebuild leaves the mark, so the next
  clean tries again. It is safe to run at any time and does nothing when there is nothing to
  clean. Every other command runs it first.

Every command that runs Python uses `--python PATH` if given, then `$FWTEST_PYTHON`, then
`<checkout>/.venv/bin/python`, where `<checkout>` is the git top level of the working directory. A
git worktree has no `.venv` of its own, so give it a symlink to the main checkout's. If none of
these exists, `fwtest` says so and exits 2 rather than falling back to the system Python.

Exit codes: 0 when everything passed; 1 when a check failed or a mutation survived; 124 when a job
timed out; 75 when another suite outside `fwtest` held the machine for 30 minutes; 2 for a usage
error.

## Data

Everything `fwtest` keeps between runs lives in `~/.flexweek-ui-harness/fwtest/`, outside every
checkout.

```text
lock                   the machine-wide lock (flock)
jobs/<job id>.json     one record per running job
edits/<file hash>.json one record per source file a mutation is editing
edits/engine-module.json  the command that rebuilds a clean engine module
logs/<job id>.log      the job's combined output
```

A job record:

```json
{
  "id": "20260928-061500-4242",
  "checkout": "/home/jonathans/FlexWeek",
  "argv": [".venv/bin/python", "-m", "pytest", "-q", "-n", "8"],
  "started": "2026-09-28T06:15:00Z",
  "owner": {"pid": 4242, "start_ticks": 912345},
  "processes": [{"pid": 4250, "start_ticks": 912360, "comm": "python"}],
  "limits": {"nice": 19, "io": "idle", "cpus": [0, 1, 2, 3, 4, 5, 6, 7], "timeout": 600}
}
```

`start_ticks` is field 22 of `/proc/<pid>/stat`. A process is "ours" only while its PID and start
ticks both match. `processes` is refreshed as the job runs. A job is stale when its owner PID no
longer matches its start ticks.

A mutation edit record:

```json
{"file": "desktop/native/look.py", "backup": "<absolute path of the copy>", "case": "look/…"}
```

The backup is written, and the record saved, before the edit is made. The source is restored from
the backup and the record deleted after the case's test finishes, whatever the outcome.
`restore_finished` skips `engine-module.json`. That file is not an edit record.

```json
{
  "checkout": "/path/to/checkout",
  "command": [".venv/bin/maturin", "develop", "--release", "--manifest-path", "engine/py/Cargo.toml", "--features", "audit"]
}
```

The mark is written before a mutated engine build and removed only after a clean rebuild succeeds.

A mutation case stays as `scripts/mutate.py` reads it, with two optional fields:

```json
{
  "name": "…",
  "file": "path from the repo root",
  "old": "…",
  "new": "…",
  "test": "pytest node id",
  "expect": "",
  "features": []
}
```

`expect` is omitted, or `""`, when the catch is a failing pytest. `"build"` means a failed engine
rebuild is the catch. Any other value is `PATTERN` and the file is not edited. `"build"` on a file
outside `engine/` is also `PATTERN`. `features` lists cargo features added only to the mutated
build, for example `["audit"]`. The clean rebuild does not pass them.

Running a case: check `old` occurs exactly once, save the edit record, write the edited file,
delete the file's cached bytecode (`__pycache__/<stem>.*.pyc`, because a same-length edit within a
second can reuse a stale `.pyc`), run `python -m pytest <test> -q -x -p no:cacheprovider` with
`PYTHONDONTWRITEBYTECODE=1` and `QT_QPA_PLATFORM=offscreen`, restore the file, delete its bytecode
again, delete the record. A case is caught when pytest exits non-zero.

A case may name a Rust test instead of a pytest node id:

```text
cargo:<package>:<test target>:<test name>
```

For example
`cargo:flexweek-engine:test_solver:test_a_low_session_skips_midnight_when_the_morning_is_free`.
`fwtest` runs this in `<checkout>/engine`:

```text
cargo test -p <package> --test <target> -- <test name> --exact
```

Cargo compiles the mutated source, so this case does not rebuild the Python module.
The source file is still restored when the case ends. A compile failure is `BUILD`
and is not caught, unless the case sets `"expect": "build"`. A failing assertion is
`RED`. A `cargo:` value that is not those three fields is `PATTERN`, and the file
is not edited.

## Mutating a file under engine/

A case whose `file` has `engine` as its first path component edits Rust that the installed
`flexweek_engine` module was built from. Pytest imports that module, so the edit is invisible
until the module is rebuilt. `engines/` is not an engine path.

For each such case `fwtest`:

1. Saves the edit record and writes the mutation, the same way it does for Python.
2. Writes `edits/engine-module.json` with the base install command, before the build.
3. Runs that command with the checkout as its working directory. The case's `features` join
   the command's `--features` list. The default command is
   `<checkout>/.venv/bin/maturin develop --release --manifest-path engine/py/Cargo.toml --features audit`.
   Before the first mutated build, `fwtest` asks the checkout's Python whether
   `flexweek_engine` has `panic_probe`. When it does not, the command stored for the clean
   rebuild omits `--features audit`, so the checkout is left as it was found. When the import
   cannot be read, the clean rebuild keeps `--features audit`. A command given with
   `--engine-build` or `FWTEST_ENGINE_BUILD` is used as given and is not probed.
4. Runs the case's pytest, unless `test` is a `cargo:` name. That case skips this
   rebuild and the one in step 3. A pytest case that built prints `built in Ns` on its line.
5. Restores the source from the saved copy.
6. At the end of the spec, runs the clean command again and deletes the mark. The same clean
   rebuild runs before a later case whose file is not under `engine/` when the mark is still
   there. Stderr prints `rebuilt clean engine module in Ns`. The mutated build still passes
   `--features audit` when the default command is in use.

A build that fails is `BUILD`. The detail starts with `did not build`. The case is not caught.
When the case sets `"expect": "build"`, that same failure is `RED` and the detail still starts
with `did not build`. A failure to write the mark is `GREEN`, the same as a failure to write the
backup.

`--engine-build COMMAND` replaces the install command. `FWTEST_ENGINE_BUILD` does the same when
the flag is absent. The value `off`, the flag `--no-engine-rebuild`, or `FWTEST_ENGINE_REBUILD`
set to `0`, `off`, or `false` skips the rebuild. The source is still edited and restored, and
pytest runs against the module already installed, so the case is not caught. The command is a
shell-style string: words split on spaces, with single quotes, double quotes, and backslash
escapes. `FWTEST_ENGINE_BUILD_TIMEOUT` is the build limit in seconds. The default is 1200.

An interrupt is a child exit code of 128 or higher, including Ctrl+C. The run stops. The edit
record's drop restores the source. If `fwtest` itself is killed, the record stays and the next
`fwtest clean` (or the clean at the start of the next command) restores the file and runs the
marked rebuild. A failed clean rebuild leaves the mark.

Each engine case pays one release build of the mutated tree. A clean release build runs before
the next case whose file is not under `engine/`, and again at the end of the spec when the mark
is still set. Incremental builds reuse `engine/target`. Measured on 2026-10-02 in this checkout,
with that directory already warm: a mutated build took 4.4s to 7.5s, and a clean rebuild took
4.4s to 7.2s. A cold `engine/target` is slower than these times. The gate's audit tests call
`panic_probe`, `int_text`, and `int_chars`, which the default build exports.

## How a job is contained

- `fwtest` marks itself a child subreaper (`prctl(PR_SET_CHILD_SUBREAPER)`), so every descendant
  that detaches is re-parented to `fwtest` and stays findable.
- The command starts in a new process group with the limits applied before `exec`: nice 19,
  `ioprio_set` idle class, `sched_setaffinity` to the job's CPUs, and `PR_SET_PDEATHSIG` SIGTERM so
  the direct child hears if `fwtest` dies.
- With a systemd user session (`systemd-run --user` succeeds), the command runs inside
  `systemd-run --user --scope --collect -p CPUQuota=<half the cores>00% -p MemoryMax=<half of RAM>`.
  Stopping the scope stops everything in it. Without one, as on CI, the process group and the
  subreaper do the same work.
- To stop a job: SIGTERM every process in its tree (walked through `/proc/<pid>/task/*/children`),
  wait up to 3 seconds, SIGKILL whatever is left, wait up to 3 more seconds, and report any PID
  that survived.
- The picture tours and the rig need a display. `fwtest` passes the environment through unchanged
  apart from what the rig sets for itself; it never opens a window on the developer's display.

## What changes for the people who use it

- The developer runs `fwtest gate` where they ran `scripts/verify.py`, and keeps using the machine
  while it runs.
- Agents run every suite through `fwtest`. `run-alone.sh`, `scripts/verify.py` and
  `scripts/mutate.py` are deleted once `fwtest` reaches parity (below), with every caller moved in
  the same change: README, `agents.md`, CI and the workflow notes.
- CI installs a Rust toolchain and runs `fwtest gate --backend-only` and `fwtest rig --server xvfb
  …` where it ran the Python scripts.

## Parity

`fwtest` replaces the Python scripts only when, on the same commit:

- `fwtest gate` and `scripts/verify.py` pass and fail on the same steps, checked on a commit that
  passes and on one with a deliberately failing test;
- `fwtest mutate scripts/mutations/look.json` and `scripts/mutate.py` report the same case names
  as caught, survived and not found;
- a rig run leaves no `kwin_wayland --virtual`, Xwayland or rig `dbus-daemon` behind, including when
  `fwtest` is sent SIGTERM mid-run and when it is sent SIGKILL and `fwtest clean` runs after it;
- the desktop's load average during a gate run stays under half the core count.

## Not in scope

Windows. The harness is Linux tooling; the Windows release workflow does not use it. Running
mutation cases in parallel, which needs a copy of the checkout per worker, comes later if the
sequential run proves too slow.
