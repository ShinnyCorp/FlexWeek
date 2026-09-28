//! Jobs queue on one lock, and a suite fwtest did not start is waited for, not stopped.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, Instant};

fn scratch() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "fwtest-queue-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(path.join("no-systemd")).unwrap();
    path
}

fn wait_until_listed(pid: u32) {
    let started = Instant::now();
    loop {
        let listed = fs::read(format!("/proc/{pid}/cmdline"))
            .map(|raw| String::from_utf8_lossy(&raw).contains("pytest"))
            .unwrap_or(false);
        if listed {
            return;
        }
        assert!(
            started.elapsed() < Duration::from_secs(2),
            "sleeper {pid} never appeared in /proc"
        );
        std::thread::sleep(Duration::from_millis(20));
    }
}

fn fwtest(home: &Path) -> Command {
    let mut command = Command::new(env!("CARGO_BIN_EXE_fwtest"));
    command
        .env("HOME", home)
        .env("XDG_RUNTIME_DIR", home.join("no-systemd"))
        .env("DBUS_SESSION_BUS_ADDRESS", "")
        .env("FWTEST_QUEUE_POLL_SECS", "1")
        .env("FWTEST_QUEUE_WAIT_SECS", "8")
        .current_dir(home);
    command
}

#[test]
fn a_second_run_waits_until_the_lock_is_free() {
    let home = scratch();
    let root = home.join(".flexweek-ui-harness/fwtest");
    let held = fwtest::queue::lock(&root).unwrap();
    let err_path = home.join("stderr.txt");
    let err_file = fs::File::create(&err_path).unwrap();
    let mut child = fwtest(&home)
        .args(["run", "--", "true"])
        .stderr(std::process::Stdio::from(err_file))
        .spawn()
        .unwrap();
    std::thread::sleep(Duration::from_millis(800));
    let early = child.try_wait().unwrap();
    let err = fs::read_to_string(&err_path).unwrap_or_default();
    assert!(
        early.is_none(),
        "run did not wait for the lock: {early:?} {err}"
    );
    assert!(
        !err.contains("Waiting for another suite"),
        "passed the lock and waited for a suite instead: {err}"
    );
    drop(held);
    let _ = child.kill();
    let _ = child.wait();
    let _ = fs::remove_dir_all(home);
}

#[test]
fn an_outside_suite_is_waited_for_and_left_running() {
    let home = scratch();
    let mut suite = Command::new("python3")
        .args(["-c", "import time; time.sleep(2)", "pytest"])
        .spawn()
        .unwrap();
    wait_until_listed(suite.id());
    let started = Instant::now();
    let status = fwtest(&home)
        .env("FWTEST_QUEUE_WAIT_SECS", "3")
        .args(["run", "--", "true"])
        .status()
        .unwrap();
    assert!(started.elapsed() >= Duration::from_secs(1), "did not wait");
    match suite.try_wait().unwrap() {
        Some(finished) => assert!(
            finished.success(),
            "outside suite was stopped: {finished:?}"
        ),
        None => {
            assert_eq!(status.code(), Some(75), "{status:?}");
            let _ = suite.kill();
            let _ = suite.wait();
        }
    }
    let _ = fs::remove_dir_all(home);
}

#[test]
fn waiting_too_long_exits_75_and_does_not_stop_the_other_suite() {
    let home = scratch();
    let mut suite = Command::new("python3")
        .args(["-c", "import time; time.sleep(30)", "pytest"])
        .spawn()
        .unwrap();
    wait_until_listed(suite.id());
    let status = fwtest(&home)
        .env("FWTEST_QUEUE_WAIT_SECS", "1")
        .args(["run", "--", "true"])
        .status()
        .unwrap();
    assert_eq!(status.code(), Some(75), "{status:?}");
    assert!(
        suite.try_wait().unwrap().is_none(),
        "outside suite was stopped"
    );
    let _ = suite.kill();
    let _ = suite.wait();
    let _ = fs::remove_dir_all(home);
}
