//! The rig command is tested with stand-in scripts. No real KWin is started.

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;

use fwtest::identity;
use fwtest::job::{self, JobLimits, JobRecord, ProcRef};

fn scratch() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "fwtest-rig-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(path.join("no-systemd")).unwrap();
    path
}

fn write_script(path: &Path, body: &str) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, body).unwrap();
    let mut perms = fs::metadata(path).unwrap().permissions();
    perms.set_mode(0o755);
    fs::set_permissions(path, perms).unwrap();
}

#[test]
fn rig_drops_keep_stops_the_hidden_session_and_leaves_no_child() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    let git = Command::new("git")
        .arg("init")
        .current_dir(&repo)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .unwrap();
    assert!(git.success());
    let log = home.join("rig.log");
    write_script(
        &repo.join("scripts/rig/drive.py"),
        &format!(
            r#"#!/bin/sh
printf 'keep=%s\n' "${{FLEXWEEK_RIG_KEEP-}}" >> "{log}"
printf 'args=%s\n' "$*" >> "{log}"
sleep 120 &
echo $! >> "{log}"
"#,
            log = log.display()
        ),
    );
    write_script(
        &repo.join("scripts/rig/hidden_session.py"),
        &format!(
            r#"#!/bin/sh
printf 'hidden-stop\n' >> "{log}"
"#,
            log = log.display()
        ),
    );
    let python = home.join("python");
    write_script(&python, "#!/bin/sh\nexec \"$@\"\n");
    let status = Command::new(env!("CARGO_BIN_EXE_fwtest"))
        .current_dir(&repo)
        .env("HOME", &home)
        .env("XDG_RUNTIME_DIR", home.join("no-systemd"))
        .env("DBUS_SESSION_BUS_ADDRESS", "")
        .env("FWTEST_QUEUE_POLL_SECS", "1")
        .env("FWTEST_QUEUE_WAIT_SECS", "8")
        .env("FWTEST_PYTHON", &python)
        .env("FLEXWEEK_RIG_KEEP", "1")
        .args(["rig", "--design", "classic", "--tab", "day"])
        .status()
        .unwrap();
    assert!(status.success(), "{status}");
    let text = fs::read_to_string(&log).unwrap();
    assert!(
        text.contains("keep=\n") || text.lines().any(|line| line == "keep="),
        "{text}"
    );
    assert!(!text.contains("keep=1"), "{text}");
    assert!(text.contains("hidden-stop"), "{text}");
    assert!(text.contains("--design"), "{text}");
    let pid = text
        .lines()
        .find_map(|line| line.parse::<i32>().ok())
        .expect(&text);
    assert!(
        identity::read_identity(pid).unwrap().is_none(),
        "child {pid} still running"
    );
    let _ = fs::remove_dir_all(home);
}

#[test]
fn rig_from_a_subdirectory_runs_at_the_checkout() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    let git = Command::new("git")
        .arg("init")
        .current_dir(&repo)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .unwrap();
    assert!(git.success());
    let log = home.join("rig.log");
    write_script(
        &repo.join("scripts/rig/drive.py"),
        &format!(
            r#"#!/bin/sh
printf 'cwd=%s\n' "$(pwd)" >> "{log}"
"#,
            log = log.display()
        ),
    );
    write_script(
        &repo.join("scripts/rig/hidden_session.py"),
        &format!(
            r#"#!/bin/sh
printf 'stop-cwd=%s\n' "$(pwd)" >> "{log}"
"#,
            log = log.display()
        ),
    );
    let python = home.join("python");
    write_script(&python, "#!/bin/sh\nexec \"$@\"\n");
    let nested = repo.join("nested");
    fs::create_dir_all(&nested).unwrap();
    let status = Command::new(env!("CARGO_BIN_EXE_fwtest"))
        .current_dir(&nested)
        .env("HOME", &home)
        .env("XDG_RUNTIME_DIR", home.join("no-systemd"))
        .env("DBUS_SESSION_BUS_ADDRESS", "")
        .env("FWTEST_QUEUE_POLL_SECS", "1")
        .env("FWTEST_QUEUE_WAIT_SECS", "8")
        .env("FWTEST_PYTHON", &python)
        .args(["rig", "--design", "classic"])
        .status()
        .unwrap();
    assert!(status.success(), "{status}");
    let text = fs::read_to_string(&log).unwrap();
    let cwd = format!("cwd={}", repo.display());
    let stop = format!("stop-cwd={}", repo.display());
    assert!(text.contains(&cwd), "{text}");
    assert!(text.contains(&stop), "{text}");
    assert!(
        !text.contains(&format!("cwd={}", nested.display())),
        "{text}"
    );
    let _ = fs::remove_dir_all(home);
}

fn rig_repo(home: &Path, hidden_body: &str) -> PathBuf {
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    let git = Command::new("git")
        .arg("init")
        .current_dir(&repo)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .unwrap();
    assert!(git.success());
    write_script(&repo.join("scripts/rig/drive.py"), "#!/bin/sh\nexit 0\n");
    write_script(&repo.join("scripts/rig/hidden_session.py"), hidden_body);
    write_script(&home.join("python"), "#!/bin/sh\nexec \"$@\"\n");
    repo
}

fn stale_record(home: &Path, id: &str, repo: &Path, argv: Vec<String>, owner: ProcRef) {
    let job = JobRecord {
        id: id.to_string(),
        checkout: repo.to_path_buf(),
        argv,
        started: "2026-09-29T06:15:00Z".to_string(),
        owner,
        processes: Vec::new(),
        limits: JobLimits {
            nice: 19,
            io: "idle".to_string(),
            cpus: vec![0],
            timeout: 0,
        },
        scope: None,
    };
    job::save_job(&home.join(".flexweek-ui-harness/fwtest"), &job).unwrap();
}

fn dead_owner() -> ProcRef {
    ProcRef {
        pid: 2_000_000_001,
        start_ticks: 1,
        comm: "fwtest".to_string(),
    }
}

fn rig_argv(home: &Path, repo: &Path) -> Vec<String> {
    vec![
        home.join("python").display().to_string(),
        repo.join("scripts/rig/drive.py").display().to_string(),
    ]
}

fn clean_command(home: &Path) -> Command {
    let mut command = Command::new(env!("CARGO_BIN_EXE_fwtest"));
    command
        .current_dir(home)
        .env("HOME", home)
        .env("XDG_RUNTIME_DIR", home.join("no-systemd"))
        .env("DBUS_SESSION_BUS_ADDRESS", "")
        .env("FWTEST_PYTHON", home.join("python"))
        .arg("clean");
    command
}

#[test]
fn clean_stops_the_hidden_session_of_a_stale_rig_job() {
    let home = scratch();
    let log = home.join("rig.log");
    let repo = rig_repo(
        &home,
        &format!(
            "#!/bin/sh\nprintf 'hidden %s cwd=%s\\n' \"$*\" \"$(pwd)\" >> \"{}\"\n",
            log.display()
        ),
    );
    stale_record(
        &home,
        "stale-rig",
        &repo,
        rig_argv(&home, &repo),
        dead_owner(),
    );
    let output = clean_command(&home).output().unwrap();
    assert!(output.status.success(), "{output:?}");
    let text = fs::read_to_string(&log).unwrap_or_default();
    assert_eq!(text, format!("hidden stop cwd={}\n", repo.display()));
    assert!(
        job::list_job_files(&home.join(".flexweek-ui-harness/fwtest"))
            .unwrap()
            .is_empty()
    );
    let _ = fs::remove_dir_all(home);
}

#[test]
fn clean_leaves_the_hidden_session_alone_for_other_stale_jobs() {
    let home = scratch();
    let log = home.join("rig.log");
    let repo = rig_repo(
        &home,
        &format!("#!/bin/sh\necho hidden >> \"{}\"\n", log.display()),
    );
    let argv = vec!["sleep".to_string(), "1".to_string()];
    stale_record(&home, "stale-sleep", &repo, argv, dead_owner());
    let output = clean_command(&home).output().unwrap();
    assert!(output.status.success(), "{output:?}");
    assert!(!log.exists());
    let _ = fs::remove_dir_all(home);
}

#[test]
fn clean_leaves_the_hidden_session_alone_while_a_rig_job_is_live_in_that_checkout() {
    let home = scratch();
    let log = home.join("rig.log");
    let repo = rig_repo(
        &home,
        &format!("#!/bin/sh\necho hidden >> \"{}\"\n", log.display()),
    );
    let mut owner = Command::new("sleep").arg("120").spawn().unwrap();
    let identity = identity::read_identity(owner.id() as i32).unwrap().unwrap();
    let live = ProcRef {
        pid: identity.pid,
        start_ticks: identity.start_ticks,
        comm: identity.comm,
    };
    stale_record(&home, "live-rig", &repo, rig_argv(&home, &repo), live);
    stale_record(
        &home,
        "stale-rig",
        &repo,
        rig_argv(&home, &repo),
        dead_owner(),
    );
    let output = clean_command(&home).output().unwrap();
    let _ = owner.kill();
    let _ = owner.wait();
    assert!(output.status.success(), "{output:?}");
    assert!(!log.exists());
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_failing_hidden_session_stop_is_logged_and_the_record_still_goes() {
    let home = scratch();
    let repo = rig_repo(&home, "#!/bin/sh\necho 'no session here' >&2\nexit 3\n");
    stale_record(
        &home,
        "stale-rig",
        &repo,
        rig_argv(&home, &repo),
        dead_owner(),
    );
    let output = clean_command(&home).output().unwrap();
    assert!(output.status.success(), "{output:?}");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("hidden_session.py stop"), "{stderr}");
    assert!(stderr.contains("no session here"), "{stderr}");
    assert!(
        job::list_job_files(&home.join(".flexweek-ui-harness/fwtest"))
            .unwrap()
            .is_empty()
    );
    let _ = fs::remove_dir_all(home);
}
