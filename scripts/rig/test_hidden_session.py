"""Process ownership and server selection for the hidden real-pointer desktop."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.rig import hidden_session as hidden


class FakeProcess:
    pid = 42
    stdout = None

    def poll(self):
        return None


def _copy_into_checkout(root: Path):
    script = root / "scripts" / "rig" / "hidden_session.py"
    script.parent.mkdir(parents=True)
    shutil.copyfile(hidden.__file__, script)
    name = f"rig_checkout_{root.name}"
    spec = importlib.util.spec_from_file_location(name, script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_each_checkout_has_its_own_state_and_socket(tmp_path) -> None:
    first = _copy_into_checkout(tmp_path / "first")
    second = _copy_into_checkout(tmp_path / "second")
    assert first.STATE != second.STATE
    assert first.SOCKET != second.SOCKET
    assert Path("/tmp/flexweek-rig/session.json") != first.STATE
    assert first.STATE.parent != second.STATE.parent


def test_kwin_display_comes_from_its_xwayland_child(monkeypatch, tmp_path) -> None:
    proc = tmp_path / "proc"
    own_tasks = proc / "42" / "task" / "42"
    own_tasks.mkdir(parents=True)
    (own_tasks / "children").write_text("77")
    (proc / "77").mkdir()
    (proc / "77" / "cmdline").write_bytes(b"/usr/bin/Xwayland\0:76\0")
    (proc / "88").mkdir()
    (proc / "88" / "cmdline").write_bytes(b"/usr/bin/Xwayland\0:75\0")
    monkeypatch.setattr(hidden, "PROC", proc)
    assert hidden._kwin_display(42) == ":76"


def test_running_rejects_a_display_no_longer_owned_by_kwin(monkeypatch, tmp_path) -> None:
    session = hidden.Session("kwin", ":71", (
        hidden.OwnedProcess(41, "dbus-daemon", 1),
        hidden.OwnedProcess(42, "kwin_wayland", 1),
    ), "unix:path=/tmp/dbus-private")
    (tmp_path / "X71").touch()
    monkeypatch.setattr(hidden, "X11_SOCKETS", tmp_path)
    monkeypatch.setattr(hidden, "_read_state", lambda: session)
    monkeypatch.setattr(hidden, "_alive", lambda _process: True)
    monkeypatch.setattr(hidden, "_kwin_display", lambda _pid: ":72")
    assert hidden.running() is None


def test_auto_uses_xvfb_when_kwin_is_unavailable(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(hidden, "STATE", tmp_path / "session.json")
    monkeypatch.setattr(hidden.shutil, "which", lambda _name: None)
    monkeypatch.setattr(hidden, "_start_bus", lambda _env: (FakeProcess(), "unix:path=/tmp/dbus-private"))
    monkeypatch.setattr(hidden, "_owned", lambda pid, _name: hidden.OwnedProcess(pid, "dbus-daemon", 1))
    monkeypatch.setattr(hidden, "_start_xvfb", lambda _env, _daemon, _address: ":73")
    assert hidden.start() == ":73"


def test_switching_servers_stops_the_owned_session(monkeypatch) -> None:
    current = hidden.Session("kwin", ":71", (hidden.OwnedProcess(12345, "kwin_wayland", 1),))
    stopped = []
    monkeypatch.setattr(hidden, "_read_state", lambda: current)
    monkeypatch.setattr(hidden, "running", lambda: current.display)
    monkeypatch.setattr(hidden, "stop", lambda: stopped.append(True))
    monkeypatch.setattr(hidden, "_start_bus", lambda _env: (FakeProcess(), "unix:path=/tmp/dbus-private"))
    monkeypatch.setattr(hidden, "_owned", lambda pid, _name: hidden.OwnedProcess(pid, "dbus-daemon", 1))
    monkeypatch.setattr(hidden, "_start_xvfb", lambda _env, _daemon, _address: ":72")
    assert hidden.start("xvfb") == ":72"
    assert stopped == [True]


def test_stop_terminates_all_recorded_processes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(hidden, "STATE", tmp_path / "session.json")
    first = subprocess.Popen(["sleep", "30"])
    second = subprocess.Popen(["sleep", "30"])
    third = subprocess.Popen(["sleep", "30"])
    try:
        hidden._save(hidden.Session("xvfb", ":73", (
            hidden._owned(first.pid, "sleep"), hidden._owned(second.pid, "sleep"),
            hidden._owned(third.pid, "sleep"),
        ), "unix:path=/tmp/dbus-private"))
        hidden.stop()
        first.wait(timeout=3)
        second.wait(timeout=3)
        third.wait(timeout=3)
        assert first.returncode == second.returncode == third.returncode == -15
        assert not hidden.STATE.exists()
    finally:
        for process in (first, second, third):
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=3)


def test_kwin_uses_private_bus_instead_of_callers(monkeypatch, tmp_path) -> None:
    launched = []
    saved = []
    monkeypatch.setattr(hidden, "STATE", tmp_path / "session.json")
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/tmp/caller")
    monkeypatch.setattr(hidden, "_start_bus", lambda _env: (FakeProcess(), "unix:path=/tmp/private"))
    monkeypatch.setattr(hidden, "_owned", lambda pid, name: hidden.OwnedProcess(pid, name, 1))
    monkeypatch.setattr(
        hidden, "_launch",
        lambda command, name, env: launched.append((command, name, env)) or FakeProcess(),
    )
    monkeypatch.setattr(hidden, "_kwin_display", lambda _pid: ":71")
    monkeypatch.setattr(hidden, "_connects", lambda _display, _env: True)
    monkeypatch.setattr(hidden, "_save", saved.append)

    assert hidden.start("kwin") == ":71"
    assert launched[0][1] == "kwin.log"
    assert launched[0][2]["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/tmp/private"
    assert saved[0].bus == "unix:path=/tmp/private"
    assert [process.name for process in saved[0].processes] == ["dbus-daemon", "kwin_wayland"]


def test_stop_signals_bus_after_both_servers(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(hidden, "STATE", tmp_path / "session.json")
    processes = (
        hidden.OwnedProcess(41, "dbus-daemon", 1),
        hidden.OwnedProcess(42, "Xvfb", 1),
        hidden.OwnedProcess(43, "openbox", 1),
    )
    hidden._save(hidden.Session("xvfb", ":73", processes, "unix:path=/tmp/private"))
    alive = {process.pid for process in processes}
    signals = []
    monkeypatch.setattr(hidden, "_alive", lambda process: process.pid in alive)

    def signal_process(pid, sig):
        signals.append((pid, sig))
        alive.remove(pid)

    monkeypatch.setattr(hidden.os, "kill", signal_process)
    hidden.stop()
    assert [pid for pid, _signal in signals] == [43, 42, 41]
    assert not hidden.STATE.exists()


def test_private_bus_has_no_activatable_services(monkeypatch, tmp_path) -> None:
    if shutil.which("dbus-daemon") is None:
        pytest.skip("dbus-daemon is not installed")
    monkeypatch.setattr(hidden, "STATE", tmp_path / "session.json")
    daemon, address = hidden._start_bus(hidden._env())
    try:
        result = subprocess.run(
            ["busctl", f"--address={address}", "call", "org.freedesktop.DBus",
             "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListActivatableNames"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        assert result.stdout.strip() == 'as 1 "org.freedesktop.DBus"'
    finally:
        hidden._terminate(daemon)
        if daemon.stdout is not None:
            daemon.stdout.close()


def test_stop_does_not_signal_a_reused_pid(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(hidden, "STATE", tmp_path / "session.json")
    process = subprocess.Popen(["sleep", "30"])
    try:
        wrong_start = replace(hidden._owned(process.pid, "sleep"), started=0)
        hidden._save(hidden.Session("kwin", ":74", (wrong_start,)))
        hidden.stop()
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=3)


def test_a_rig_run_stops_its_hidden_desktop_unless_asked_to_keep_it(monkeypatch, tmp_path):
    """Kept up for the next run, a hidden KWin and its bus outlived a rig by two hours beside the
    student's own desktop, which froze under the load. The run stops what it started."""
    from scripts.rig import drive

    calls = []
    monkeypatch.setattr(hidden, "start", lambda server: calls.append(("start", server)) or ":99")
    monkeypatch.setattr(hidden, "stop", lambda: calls.append(("stop",)))
    monkeypatch.setattr(hidden, "bus", lambda: "unix:path=/nowhere")
    monkeypatch.setitem(sys.modules, "hidden_session", hidden)
    monkeypatch.setattr(drive.subprocess, "run", lambda *_a, **_k: subprocess.CompletedProcess([], 3))
    monkeypatch.delenv("FLEXWEEK_RIG_KEEP", raising=False)
    monkeypatch.setattr(sys, "argv", ["drive.py", "--out", str(tmp_path / "out")])
    assert drive.main() == 3
    assert calls == [("start", "auto"), ("stop",)]
    calls.clear()
    monkeypatch.setenv("FLEXWEEK_RIG_KEEP", "1")
    assert drive.main() == 3
    assert calls == [("start", "auto")], "kept for runs back to back"
