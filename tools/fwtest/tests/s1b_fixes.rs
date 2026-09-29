//! Review findings that the earlier contain/gate/mutate tests never reached.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

use fwtest::identity;
use fwtest::job;

fn scratch() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "fwtest-s1b-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(path.join("no-systemd")).unwrap();
    path
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

fn state_root(home: &Path) -> PathBuf {
    home.join(".flexweek-ui-harness/fwtest")
}

struct StopOnDrop {
    pid: i32,
    ticks: u64,
}

impl Drop for StopOnDrop {
    fn drop(&mut self) {
        let _ = identity::stop_if_ours(self.pid, self.ticks);
    }
}

fn guard_pidfile(path: &Path) -> Option<StopOnDrop> {
    let text = fs::read_to_string(path).ok()?;
    let pid: i32 = text.trim().parse().ok()?;
    let identity = identity::read_identity(pid).ok().flatten()?;
    Some(StopOnDrop {
        pid,
        ticks: identity.start_ticks,
    })
}

fn wait_child(child: &mut Child, limit: Duration) -> Option<std::process::ExitStatus> {
    let started = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(status)) => return Some(status),
            Ok(None) => {}
            Err(_) => return None,
        }
        if started.elapsed() >= limit {
            let pid = child.id();
            let _ = Command::new("kill")
                .args(["-TERM", &pid.to_string()])
                .status();
            std::thread::sleep(Duration::from_millis(200));
            match child.try_wait() {
                Ok(Some(status)) => return Some(status),
                _ => {
                    let _ = Command::new("kill")
                        .args(["-KILL", &pid.to_string()])
                        .status();
                    let _ = child.wait();
                    return None;
                }
            }
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}

fn daemon_script(pid1: &Path, pid2: &Path) -> String {
    format!(
        "(setsid sh -c 'sleep 3131 & echo $! > \"{p1}\"; sleep 3132 & echo $! > \"{p2}\"; wait' &); sleep 1",
        p1 = pid1.display(),
        p2 = pid2.display()
    )
}

#[test]
fn a_reparented_daemon_leaves_no_sleepers() {
    let home = scratch();
    let pid1 = home.join("sleep-3131.pid");
    let pid2 = home.join("sleep-3132.pid");
    let script = daemon_script(&pid1, &pid2);
    let mut child = fwtest(&home)
        .args(["run", "--", "sh", "-c", &script])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let status = wait_child(&mut child, Duration::from_secs(10));
    let _g1 = guard_pidfile(&pid1);
    let _g2 = guard_pidfile(&pid2);
    let status = status.expect("fwtest did not exit within 10 seconds");
    assert_eq!(status.code(), Some(0), "{status:?}");
    for path in [&pid1, &pid2] {
        let pid: i32 = fs::read_to_string(path)
            .unwrap_or_else(|_| panic!("{} missing", path.display()))
            .trim()
            .parse()
            .unwrap();
        assert!(
            identity::read_identity(pid).unwrap().is_none(),
            "{} pid {pid} still has a /proc entry",
            path.file_name().unwrap().to_string_lossy()
        );
    }
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_reparented_daemon_does_not_hang_fwtest() {
    let home = scratch();
    let pid1 = home.join("sleep-3131.pid");
    let pid2 = home.join("sleep-3132.pid");
    let script = daemon_script(&pid1, &pid2);
    let started = Instant::now();
    let mut child = fwtest(&home)
        .args(["run", "--", "sh", "-c", &script])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let status = wait_child(&mut child, Duration::from_secs(10));
    let _g1 = guard_pidfile(&pid1);
    let _g2 = guard_pidfile(&pid2);
    let elapsed = started.elapsed();
    assert!(status.is_some(), "fwtest still running after {:?}", elapsed);
    assert!(
        elapsed < Duration::from_secs(10),
        "fwtest took {elapsed:?} to finish"
    );
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_stable_job_does_not_rewrite_its_record_every_tick() {
    let home = scratch();
    let mut child = fwtest(&home)
        .args(["run", "--", "sleep", "2"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let jobs = state_root(&home).join("jobs");
    let started = Instant::now();
    let path = loop {
        assert!(
            started.elapsed() < Duration::from_secs(8),
            "job record never appeared"
        );
        let mut found = None;
        if let Ok(entries) = fs::read_dir(&jobs) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.extension().and_then(|ext| ext.to_str()) == Some("json")
                    && let Ok(job) = job::load_job_file(&path)
                    && !job.processes.is_empty()
                {
                    found = Some(path);
                    break;
                }
            }
        }
        if let Some(path) = found {
            break path;
        }
        std::thread::sleep(Duration::from_millis(30));
    };
    let first = fs::metadata(&path).unwrap().modified().unwrap();
    std::thread::sleep(Duration::from_millis(800));
    let second = fs::metadata(&path).unwrap().modified().unwrap();
    let _ = wait_child(&mut child, Duration::from_secs(8));
    assert_eq!(
        first, second,
        "job record mtime changed while the process set was stable"
    );
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_bad_record_is_set_aside_and_other_commands_still_run() {
    let home = scratch();
    let root = state_root(&home);
    let jobs = root.join("jobs");
    let edits = root.join("edits");
    fs::create_dir_all(&jobs).unwrap();
    fs::create_dir_all(&edits).unwrap();
    fs::write(jobs.join("broken.json"), "this is not a job\n").unwrap();
    fs::write(
        edits.join("missing.json"),
        r#"{"file":"/tmp/fwtest-missing-src","backup":"/tmp/fwtest-no-such-backup","case":"x"}
"#,
    )
    .unwrap();
    let clean = fwtest(&home).arg("clean").output().unwrap();
    let stderr = String::from_utf8_lossy(&clean.stderr);
    assert!(
        clean.status.success(),
        "clean should not fail on a bad record: {stderr}"
    );
    assert!(
        jobs.join("broken.json.bad").is_file(),
        "broken job was not set aside; stderr={stderr}"
    );
    assert!(!jobs.join("broken.json").exists());
    assert!(
        edits.join("missing.json").is_file(),
        "edit with a missing backup should be kept; stderr={stderr}"
    );
    assert!(
        stderr.to_lowercase().contains("missing") || stderr.contains("backup"),
        "missing backup should be reported: {stderr}"
    );
    let run = fwtest(&home).args(["run", "--", "true"]).output().unwrap();
    assert!(
        run.status.success(),
        "run after a bad record: {}",
        String::from_utf8_lossy(&run.stderr)
    );
    let _ = fs::remove_dir_all(home);
}
