//! One job at a time. The lock is shared by every checkout. Suites started
//! outside fwtest are waited for, never stopped.

use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::fd::AsRawFd;
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;
use std::time::{Duration, Instant};

use crate::identity;

pub struct MachineLock {
    file: File,
}

pub fn lock(root: &Path) -> io::Result<MachineLock> {
    fs::create_dir_all(root)?;
    let file = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .custom_flags(nix::libc::O_CLOEXEC)
        .open(root.join("lock"))?;
    // SAFETY: `file` stays in MachineLock for the lock's lifetime, so the fd remains valid.
    let rc = unsafe { nix::libc::flock(file.as_raw_fd(), nix::libc::LOCK_EX) };
    if rc != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(MachineLock { file })
}

pub fn wait_for_other_suites() -> io::Result<()> {
    let poll = env_secs("FWTEST_QUEUE_POLL_SECS", 10);
    let limit = env_secs("FWTEST_QUEUE_WAIT_SECS", 30 * 60);
    let started = Instant::now();
    let mut announced = false;
    while other_suite_running()? {
        if started.elapsed() >= Duration::from_secs(limit) {
            let unit = if limit == 1 { "second" } else { "seconds" };
            eprintln!("Another suite has kept the machine for {limit} {unit}. Not starting.");
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "another suite held the machine",
            ));
        }
        if !announced {
            eprintln!("Waiting for another suite to finish.");
            announced = true;
        }
        std::thread::sleep(Duration::from_secs(poll.max(1)));
    }
    Ok(())
}

pub fn is_wait_timeout(error: &io::Error) -> bool {
    error.kind() == io::ErrorKind::TimedOut
}

fn env_secs(name: &str, default: u64) -> u64 {
    std::env::var(name)
        .ok()
        .and_then(|value| value.parse().ok())
        .filter(|value| *value > 0)
        .unwrap_or(default)
}

fn other_suite_running() -> io::Result<bool> {
    let entries = match fs::read_dir("/proc") {
        Ok(entries) => entries,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(false),
        Err(error) => return Err(error),
    };
    let self_pid = std::process::id() as i32;
    for entry in entries {
        let Ok(name) = entry else { continue };
        let Ok(pid) = name.file_name().to_string_lossy().parse::<i32>() else {
            continue;
        };
        if pid == self_pid {
            continue;
        }
        if suite_command(pid) {
            return Ok(true);
        }
    }
    Ok(false)
}

fn suite_command(pid: i32) -> bool {
    let Ok(comm) = fs::read_to_string(format!("/proc/{pid}/comm")) else {
        return false;
    };
    if !comm.trim().starts_with("python") {
        return false;
    }
    let Ok(raw) = fs::read(format!("/proc/{pid}/cmdline")) else {
        return false;
    };
    let text = String::from_utf8_lossy(&raw);
    let needles = ["pytest", "verify.py", "drive.py", "mutate.py"];
    needles.iter().any(|needle| text.contains(needle)) && !ours(pid)
}

fn ours(pid: i32) -> bool {
    identity::read_identity(pid)
        .ok()
        .flatten()
        .is_some_and(|identity| identity.ppid == std::process::id() as i32)
}

impl Drop for MachineLock {
    fn drop(&mut self) {
        // SAFETY: the fd is still open; unlocking at drop matches the LOCK_EX taken in `lock`.
        unsafe {
            nix::libc::flock(self.file.as_raw_fd(), nix::libc::LOCK_UN);
        }
    }
}
