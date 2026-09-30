//! systemd-run --user --scope path. Skipped when that command does not work.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

use fwtest::contain::half_cpus;
use fwtest::identity::{self, parse_stat};

fn scratch() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "fwtest-sysd-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&path).unwrap();
    path
}

fn systemd_scope_works() -> bool {
    Command::new("systemd-run")
        .args(["--user", "--scope", "--collect", "--quiet", "--", "true"])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn skip_without_systemd() -> bool {
    if systemd_scope_works() {
        false
    } else {
        eprintln!("skipping systemd path: systemd-run --user --scope -- true failed");
        true
    }
}

fn fwtest(home: &Path) -> Command {
    let mut command = Command::new(env!("CARGO_BIN_EXE_fwtest"));
    command
        .env("HOME", home)
        .env("FWTEST_QUEUE_POLL_SECS", "1")
        .env("FWTEST_QUEUE_WAIT_SECS", "8")
        .current_dir(home);
    command
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

fn cpu_list(cpus: &[usize]) -> String {
    if cpus.len() > 1 && cpus.windows(2).all(|pair| pair[1] == pair[0] + 1) {
        format!("{}-{}", cpus[0], cpus[cpus.len() - 1])
    } else {
        cpus.iter()
            .map(|cpu| cpu.to_string())
            .collect::<Vec<_>>()
            .join(",")
    }
}

#[test]
fn systemd_run_echoes_the_command() {
    if skip_without_systemd() {
        return;
    }
    let home = scratch();
    let output = fwtest(&home)
        .args(["run", "--", "echo", "job-ran"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        output.status.success(),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    assert!(
        stdout.contains("job-ran"),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    assert!(
        !stderr.contains("Unknown assignment"),
        "systemd-run rejected a property:\n{stderr}"
    );
    let _ = fs::remove_dir_all(home);
}

#[test]
fn systemd_job_is_niced_grouped_and_in_a_scope() {
    if skip_without_systemd() {
        return;
    }
    let home = scratch();
    let output = fwtest(&home)
        .args([
            "run",
            "--",
            "sh",
            "-c",
            "cat /proc/self/stat; printf '\\n---\\n'; cat /proc/self/status; printf '\\n---\\n'; cat /proc/self/cgroup; printf '\\n---\\n'; cat /proc/$PPID/stat",
        ])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        output.status.success(),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    let mut parts = stdout.split("\n---\n");
    let stat = parts.next().expect(&stdout);
    let status = parts.next().expect(&stdout);
    let cgroup = parts.next().expect(&stdout);
    let parent = parts.next().expect(&stdout);
    let identity = parse_stat(stat).unwrap();
    let parent_id = parse_stat(parent).unwrap();
    assert_eq!(identity.nice, 19, "{stat}");
    let allowed = status
        .lines()
        .find_map(|line| line.strip_prefix("Cpus_allowed_list:"))
        .expect(status)
        .trim()
        .to_string();
    assert_eq!(allowed, cpu_list(&half_cpus()), "{status}");
    assert_ne!(
        identity.pgrp, parent_id.pgrp,
        "job shared fwtest's process group; job={stat} fwtest={parent}"
    );
    assert!(
        cgroup.contains(".scope") && cgroup.contains("fwtest-"),
        "job was not in an fwtest scope:\n{cgroup}"
    );
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_pipeline_around_fwtest_stays_alive() {
    if skip_without_systemd() {
        return;
    }
    let home = scratch();
    let script = format!(
        "'{bin}' run -- true | cat; echo alive",
        bin = env!("CARGO_BIN_EXE_fwtest")
    );
    let output = Command::new("sh")
        .arg("-c")
        .arg(&script)
        .env("HOME", &home)
        .env("FWTEST_QUEUE_POLL_SECS", "1")
        .env("FWTEST_QUEUE_WAIT_SECS", "8")
        .current_dir(&home)
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        output.status.success(),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    assert!(
        stdout.lines().any(|line| line.trim() == "alive"),
        "pipeline did not print alive:\n{stdout}\n{stderr}"
    );
    let _ = fs::remove_dir_all(home);
}

#[test]
fn systemd_reparented_daemon_is_gone_within_ten_seconds() {
    if skip_without_systemd() {
        return;
    }
    let home = scratch();
    let pid1 = home.join("sleep-3131.pid");
    let pid2 = home.join("sleep-3132.pid");
    let script = format!(
        "(setsid sh -c 'sleep 3131 & echo $! > \"{p1}\"; sleep 3132 & echo $! > \"{p2}\"; wait' &); sleep 1",
        p1 = pid1.display(),
        p2 = pid2.display()
    );
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
    let status = status.expect("fwtest did not exit within 10 seconds");
    assert_eq!(status.code(), Some(0), "elapsed {elapsed:?}");
    assert!(elapsed < Duration::from_secs(10), "took {elapsed:?}");
    for path in [&pid1, &pid2] {
        let pid: i32 = fs::read_to_string(path)
            .unwrap_or_else(|_| panic!("{} missing", path.display()))
            .trim()
            .parse()
            .unwrap();
        assert!(
            identity::read_identity(pid).unwrap().is_none(),
            "{} pid {pid} still running",
            path.display()
        );
    }
    let _ = fs::remove_dir_all(home);
}
