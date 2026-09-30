//! Contained jobs leave no detached grandchild, and they run at nice 19.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, Instant};

use fwtest::contain::half_cpus;
use fwtest::identity::{self, parse_stat};
use fwtest::job;

fn scratch() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "fwtest-run-{}-{}",
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
        .current_dir(home);
    command
}

fn state_root(home: &Path) -> PathBuf {
    home.join(".flexweek-ui-harness/fwtest")
}

fn wait_until_recorded(home: &Path, pidfile: &Path) -> (i32, u64) {
    let started = Instant::now();
    loop {
        assert!(
            started.elapsed() < Duration::from_secs(8),
            "detached process was not recorded"
        );
        if let Ok(text) = fs::read_to_string(pidfile)
            && let Ok(pid) = text.trim().parse::<i32>()
            && let Some(identity) = identity::read_identity(pid).unwrap()
        {
            for path in job::list_job_files(&state_root(home)).unwrap_or_default() {
                if let Ok(record) = job::load_job_file(&path)
                    && record.processes.iter().any(|process| {
                        process.pid == pid && process.start_ticks == identity.start_ticks
                    })
                {
                    return (pid, identity.start_ticks);
                }
            }
        }
        std::thread::sleep(Duration::from_millis(30));
    }
}

fn detach_script(pidfile: &Path, linger: &str) -> String {
    format!(
        "setsid sleep 120 >/dev/null 2>&1 & echo $! > '{}'; sleep {linger}",
        pidfile.display()
    )
}

#[test]
fn a_timeout_exits_124_and_the_command_is_gone() {
    let home = scratch();
    let output = fwtest(&home)
        .args(["run", "--timeout", "1", "--", "sleep", "30"])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(124), "{output:?}");
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_setsid_grandchild_is_gone_when_the_command_finishes() {
    let home = scratch();
    let pidfile = home.join("grand.pid");
    let script = detach_script(&pidfile, "0.4");
    let status = fwtest(&home)
        .args(["run", "--", "sh", "-c", &script])
        .status()
        .unwrap();
    assert_eq!(status.code(), Some(0), "run status {status:?}");
    let pid: i32 = fs::read_to_string(&pidfile)
        .unwrap()
        .trim()
        .parse()
        .unwrap();
    assert!(
        identity::read_identity(pid).unwrap().is_none(),
        "grandchild {pid} still has a /proc entry"
    );
    assert!(job::list_job_files(&state_root(&home)).unwrap().is_empty());
    let _ = fs::remove_dir_all(home);
}

#[test]
fn sigterm_stops_the_setsid_grandchild() {
    let home = scratch();
    let pidfile = home.join("grand.pid");
    let script = detach_script(&pidfile, "30");
    let mut child = fwtest(&home)
        .args(["run", "--", "sh", "-c", &script])
        .spawn()
        .unwrap();
    let (pid, ticks) = wait_until_recorded(&home, &pidfile);
    let _ = Command::new("kill")
        .args(["-TERM", &child.id().to_string()])
        .status();
    let status = child.wait().unwrap();
    assert_eq!(status.code(), Some(128 + 15), "{status:?}");
    assert!(!identity::is_live_match(pid, ticks).unwrap());
    let _ = fs::remove_dir_all(home);
}

#[test]
fn sigkill_then_clean_stops_the_setsid_grandchild() {
    let home = scratch();
    let pidfile = home.join("grand.pid");
    let script = detach_script(&pidfile, "30");
    let mut child = fwtest(&home)
        .args(["run", "--", "sh", "-c", &script])
        .spawn()
        .unwrap();
    let (pid, ticks) = wait_until_recorded(&home, &pidfile);
    let _ = Command::new("kill")
        .args(["-KILL", &child.id().to_string()])
        .status();
    let _ = child.wait();
    let cleaned = fwtest(&home).arg("clean").status().unwrap();
    assert!(cleaned.success(), "{cleaned:?}");
    assert!(!identity::is_live_match(pid, ticks).unwrap());
    let _ = fs::remove_dir_all(home);
}

#[test]
fn the_command_runs_at_nice_19_on_the_chosen_cpus() {
    let home = scratch();
    let output = fwtest(&home)
        .args([
            "run",
            "--",
            "sh",
            "-c",
            "cat /proc/self/stat; printf '\\n---\\n'; cat /proc/self/status",
        ])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let text = String::from_utf8_lossy(&output.stdout);
    let (stat, status) = text.split_once("\n---\n").expect(&text);
    let identity = parse_stat(stat).unwrap();
    assert_eq!(identity.nice, 19, "{stat}");
    let allowed = status
        .lines()
        .find_map(|line| line.strip_prefix("Cpus_allowed_list:"))
        .expect(status)
        .trim()
        .to_string();
    assert_eq!(allowed, cpu_list(&half_cpus()), "{status}");
    let _ = fs::remove_dir_all(home);
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
