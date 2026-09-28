//! What a student of the harness can observe: clean stops only a stale job's own processes.

use std::process::Command;
use std::time::Duration;

use fwtest::clean::{self, sample_job};
use fwtest::identity::{self, StopResult};
use fwtest::job::{self, ProcRef};

fn scratch_root() -> std::path::PathBuf {
    let path = std::env::temp_dir().join(format!(
        "fwtest-clean-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&path).unwrap();
    path
}

fn sleep_for(seconds: &str) -> std::process::Child {
    Command::new("sleep").arg(seconds).spawn().unwrap()
}

fn proc_ref(child: &std::process::Child) -> ProcRef {
    let pid = child.id() as i32;
    let identity = identity::read_identity(pid)
        .unwrap()
        .expect("sleep is alive");
    ProcRef {
        pid,
        start_ticks: identity.start_ticks,
        comm: identity.comm,
    }
}

#[test]
fn clean_does_nothing_when_there_are_no_records() {
    let root = scratch_root();
    let first = clean::clean(&root).unwrap();
    let second = clean::clean(&root).unwrap();
    assert_eq!(first.removed, 0);
    assert_eq!(second, first);
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn clean_stops_a_process_left_by_a_dead_owner_and_a_second_run_is_empty() {
    let root = scratch_root();
    let mut child = sleep_for("120");
    let recorded = proc_ref(&child);
    let job = sample_job("stale-owner", 2_000_000_001, 1, vec![recorded.clone()]);
    job::save_job(&root, &job).unwrap();

    let report = clean::clean(&root).unwrap();
    assert!(report.stopped.contains(&recorded.pid), "{report:?}");
    assert!(report.survived.is_empty());
    assert_eq!(report.removed, 1);
    assert!(job::list_job_files(&root).unwrap().is_empty());
    assert!(!identity::is_live_match(recorded.pid, recorded.start_ticks).unwrap());

    let again = clean::clean(&root).unwrap();
    assert_eq!(again.removed, 0);
    let _ = child.wait();
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn a_live_owner_keeps_its_process_and_its_record() {
    let root = scratch_root();
    let mut owner = sleep_for("120");
    let mut worker = sleep_for("120");
    let owner_ref = proc_ref(&owner);
    let worker_ref = proc_ref(&worker);
    let job = sample_job(
        "live-owner",
        owner_ref.pid,
        owner_ref.start_ticks,
        vec![worker_ref.clone()],
    );
    job::save_job(&root, &job).unwrap();

    let report = clean::clean(&root).unwrap();
    assert!(report.stopped.is_empty(), "{report:?}");
    assert_eq!(report.removed, 0);
    assert!(identity::is_live_match(worker_ref.pid, worker_ref.start_ticks).unwrap());
    assert_eq!(job::list_job_files(&root).unwrap().len(), 1);

    let _ = owner.kill();
    let _ = worker.kill();
    let _ = owner.wait();
    let _ = worker.wait();
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn mismatched_start_ticks_are_not_signalled() {
    let mut child = sleep_for("120");
    let recorded = proc_ref(&child);
    let wrong = recorded.start_ticks.wrapping_add(1);
    let result = identity::stop_if_ours(recorded.pid, wrong).unwrap();
    assert_eq!(result, StopResult::NotOurs);
    assert!(identity::is_live_match(recorded.pid, recorded.start_ticks).unwrap());
    std::thread::sleep(Duration::from_millis(100));
    assert!(identity::is_live_match(recorded.pid, recorded.start_ticks).unwrap());
    let _ = child.kill();
    let _ = child.wait();
}

#[test]
fn clean_cli_on_an_empty_home_exits_0() {
    let home = scratch_root();
    let output = Command::new(env!("CARGO_BIN_EXE_fwtest"))
        .arg("clean")
        .env("HOME", &home)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(output.stdout.is_empty());
    let _ = std::fs::remove_dir_all(home);
}
