//! `fwtest clean`: stop processes left by a job whose owner is gone, then drop that record.
//!
//! A second run with nothing stale is a no-op. A process whose PID matches a
//! record but whose start ticks do not is never signalled. A record stays if a
//! recorded process is still alive after SIGKILL, so the next clean retries it.

use std::io::{self, Write};
use std::path::Path;

use crate::ExitCode;
use crate::identity::{self, StopResult};
use crate::job::{self, JobRecord};
use crate::state;

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CleanReport {
    pub removed: usize,
    pub stopped: Vec<i32>,
    pub spared: Vec<i32>,
    pub survived: Vec<i32>,
}

pub fn clean(root: &Path) -> io::Result<CleanReport> {
    let mut report = CleanReport::default();
    for path in job::list_job_files(root)? {
        let job = match job::load_job_file(&path) {
            Ok(job) => job,
            Err(error) => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!("{}: {error}", path.display()),
                ));
            }
        };
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
        std::fs::remove_file(&path)?;
        report.removed += 1;
    }
    Ok(report)
}

pub fn run() -> ExitCode {
    let root = match state::harness_root() {
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

pub fn sample_job(
    id: &str,
    owner_pid: i32,
    owner_ticks: u64,
    processes: Vec<job::ProcRef>,
) -> JobRecord {
    JobRecord {
        id: id.to_string(),
        checkout: Path::new("/tmp/fwtest-checkout").to_path_buf(),
        argv: vec!["sleep".to_string(), "120".to_string()],
        started: "2026-09-28T06:15:00Z".to_string(),
        owner: job::ProcRef {
            pid: owner_pid,
            start_ticks: owner_ticks,
            comm: "fwtest".to_string(),
        },
        processes,
        limits: job::JobLimits {
            nice: 19,
            io: "idle".to_string(),
            cpus: vec![0, 1],
            timeout: 600,
        },
        scope: None,
    }
}
