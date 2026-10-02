//! `fwtest clean`: stop processes left by a job whose owner is gone, then drop that record.
//!
//! A second run with nothing stale is a no-op. A process whose PID matches a
//! record but whose start ticks do not is never signalled. A record stays if a
//! recorded process is still alive after SIGKILL, so the next clean retries it.

use std::collections::HashSet;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use crate::ExitCode;
use crate::hidden;
use crate::identity::{self, StopResult};
use crate::job::{self, JobRecord};

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CleanReport {
    pub removed: usize,
    pub stopped: Vec<i32>,
    pub spared: Vec<i32>,
    pub survived: Vec<i32>,
}

pub fn clean(root: &Path) -> io::Result<CleanReport> {
    let mut report = CleanReport::default();
    // Stale jobs are removed below. Restore edits first only when nothing live
    // still owns a file; `restore_finished` checks that itself.
    crate::edits::restore_finished(root)?;
    let mut jobs = Vec::new();
    for path in job::list_job_files(root)? {
        if let Some(job) = job::load_or_set_aside(&path)? {
            jobs.push((path, job));
        }
    }
    let mut live_rig_checkouts = HashSet::new();
    for (_, job) in &jobs {
        if ran_rig_driver(job) && job::owner_is_live(job)? {
            live_rig_checkouts.insert(job.checkout.clone());
        }
    }
    for (path, job) in jobs {
        if job::owner_is_live(&job)? {
            continue;
        }
        if let Some(scope) = &job.scope {
            let _ = std::process::Command::new("systemctl")
                .args(["--user", "stop", scope])
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .status();
        }
        let mut survived = false;
        for process in &job.processes {
            match identity::stop_if_ours(process.pid, process.start_ticks)? {
                StopResult::Stopped => report.stopped.push(process.pid),
                StopResult::NotOurs => report.spared.push(process.pid),
                StopResult::Survived => {
                    survived = true;
                    report.survived.push(process.pid);
                }
                StopResult::Gone => {}
            }
        }
        if survived {
            continue;
        }
        if ran_rig_driver(&job) && !live_rig_checkouts.contains(&job.checkout) {
            stop_hidden_session(&job.checkout);
        }
        std::fs::remove_file(&path)?;
        report.removed += 1;
    }
    stop_state_files(&live_rig_checkouts);
    Ok(report)
}

/// A state file is enough. A live rig in that checkout is left alone.
fn stop_state_files(live_rig_checkouts: &HashSet<PathBuf>) {
    let mut protected = HashSet::new();
    for checkout in live_rig_checkouts {
        if let Ok(place) = hidden::place(checkout) {
            protected.insert(place.state);
        }
    }
    let Ok(entries) = std::fs::read_dir(hidden::state_root()) else {
        return;
    };
    for entry in entries.flatten() {
        let state = entry.path().join("session.json");
        if !state.is_file() || protected.contains(&state) {
            continue;
        }
        if let Err(message) = hidden::stop_state(&state) {
            eprintln!("hidden session stop for {}: {message}", state.display());
        }
    }
}

fn ran_rig_driver(job: &JobRecord) -> bool {
    job.argv
        .iter()
        .any(|arg| Path::new(arg).ends_with("scripts/rig/drive.py"))
}

/// A SIGKILLed rig leaves its `session.json` behind. Stop signals the recorded PIDs.
fn stop_hidden_session(checkout: &Path) {
    if let Err(message) = hidden::stop(checkout) {
        eprintln!("hidden session stop for {}: {message}", checkout.display());
    }
}

pub fn run() -> ExitCode {
    let root = match crate::state::harness_root() {
        Ok(root) => root,
        Err(message) => {
            eprintln!("{message}");
            return ExitCode::USAGE;
        }
    };
    match clean(&root) {
        Ok(report) if report.survived.is_empty() => {
            if !report.stopped.is_empty() {
                println!(
                    "stopped {}",
                    report
                        .stopped
                        .iter()
                        .map(|pid| pid.to_string())
                        .collect::<Vec<_>>()
                        .join(" ")
                );
            }
            ExitCode::OK
        }
        Ok(report) => {
            let _ = writeln!(
                std::io::stderr(),
                "still running: {}",
                report
                    .survived
                    .iter()
                    .map(|pid| pid.to_string())
                    .collect::<Vec<_>>()
                    .join(" ")
            );
            ExitCode::CHECK_FAILED
        }
        Err(error) => {
            eprintln!("clean failed: {error}");
            ExitCode::CHECK_FAILED
        }
    }
}
