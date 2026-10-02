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
   that finds an edit left by a killed run restores it before it does anything else.
5. **Only its own processes are killed.** `fwtest` never matches processes by name or command line.
   It kills a PID only if the PID's start time matches the one it recorded.

## Commands

```text
fwtest gate [--backend-only] [--workers N]
fwtest mutate [SPEC.json ...] [--case NAME]
fwtest rig [--server kwin|xvfb|auto] [ARGS FOR scripts/rig/drive.py ...]
fwtest run [--timeout SECONDS] -- COMMAND [ARGS ...]
fwtest clean
```

- `gate` runs the checks `scripts/verify.py` runs, in the same order: ruff, mypy over `backend`,
  pytest, then `git diff --check` on the working tree, the index, and the committed range from the
  diff base. The diff base is `$VERIFY_BASE_SHA`, then `main`, then `origin/main`, then `HEAD^`,
  skipping any value of all zeroes. pytest gets `-n N` where N is `--workers`, or half the cores
  and at least 2. It prints `VERIFIED: Backend and desktop. Packaged binaries and other platforms
  need separate checks.` (or `VERIFIED: Backend.` with `--backend-only`) only when every step
  passed, as `verify.py` does. The per-step timeout is 480 seconds.
- `mutate` runs every spec in `scripts/mutations/`, or the specs named. `--case` runs one case by
  name. It prints one line per case (`RED`, `GREEN` or `PATTERN`, then the spec, the case name and
  the first failing assertion) and ends with `every mutation was caught` or `N mutation(s)
  SURVIVED`. It exits 1 if any case survived or any pattern was not found exactly once.
- `rig` starts this checkout's hidden session, then runs `scripts/rig/drive.py` as one job.
  `--server` is `kwin`, `xvfb`, or `auto` (the default: KWin when `kwin_wayland` is on `PATH`,
  otherwise Xvfb). That flag is not forwarded to the driver. The driver receives the display, the
  private D-Bus address, and the runs-folder key in its environment. `FLEXWEEK_RIG_KEEP` is removed
  before the driver starts, so the run always stops the session afterwards by the PIDs recorded in
  its state file, then stops anything the job itself left behind.
- `run` runs any command as a job, with the guarantees above. It exists for the picture tours and
  the one-off scripts that currently go through `run-alone.sh`.
- `clean` stops every process recorded by a job that is no longer running. For a stale rig job,
  with no live rig job in that checkout, it also stops the hidden session by the PIDs in its state
  file. It restores any source file left edited by a mutation run and removes the stale records. It
  is safe to run at any time and does nothing when there is nothing to clean. Every other command
  runs it first.

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

A mutation case stays exactly as `scripts/mutate.py` reads it today, so the existing specs work
unchanged:

```json
{"name": "…", "file": "path from the repo root", "old": "…", "new": "…", "test": "pytest node id"}
```

Running a case: check `old` occurs exactly once, save the edit record, write the edited file,
delete the file's cached bytecode (`__pycache__/<stem>.*.pyc`, because a same-length edit within a
second can reuse a stale `.pyc`), run `python -m pytest <test> -q -x -p no:cacheprovider` with
`PYTHONDONTWRITEBYTECODE=1` and `QT_QPA_PLATFORM=offscreen`, restore the file, delete its bytecode
again, delete the record. A case is caught when pytest exits non-zero.

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
