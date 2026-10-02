//! The rig command is tested with stand-in programs. No real KWin is started.
//!
//! The stand-ins are copies of one small binary. A shell script would show up
//! in `/proc` as `sh`, and stop would then refuse to signal it.

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::OnceLock;

use fwtest::hidden;
use fwtest::identity;
use fwtest::job::{self, JobLimits, JobRecord, ProcRef};

const STANDIN_SOURCE: &str = r#"
use std::env;
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::Path;
use std::process;
use std::thread;
use std::time::Duration;

fn program() -> String {
    env::args()
        .next()
        .as_deref()
        .map(Path::new)
        .and_then(Path::file_name)
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default()
}

fn note(program: &str) {
    let Ok(path) = env::var("FWTEST_STANDIN_LOG") else {
        return;
    };
    let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) else {
        return;
    };
    let bus = env::var("DBUS_SESSION_BUS_ADDRESS").unwrap_or_default();
    let _ = writeln!(file, "{program} pid={} bus={bus}", process::id());
}

fn parent_gone() -> bool {
    let text = fs::read_to_string("/proc/self/status").unwrap_or_default();
    let mut ppid = 1;
    for line in text.lines() {
        if let Some(rest) = line.strip_prefix("PPid:") {
            ppid = rest.trim().parse().unwrap_or(1);
            break;
        }
    }
    let Ok(stat) = fs::read_to_string(format!("/proc/{ppid}/stat")) else {
        return true;
    };
    match stat.rsplit_once(") ") {
        Some((_, rest)) => rest.starts_with('Z'),
        None => true,
    }
}

fn sleep_until_signaled() {
    loop {
        thread::sleep(Duration::from_secs(60));
    }
}

fn main() {
    let program = program();
    note(&program);
    match program.as_str() {
        "dbus-daemon" => {
            println!("unix:path=/fwtest-standin-bus");
            let _ = io::stdout().flush();
            sleep_until_signaled();
        }
        "kwin_wayland" => {
            let exe = env::current_exe().expect("current exe");
            let xwayland = exe.parent().expect("bin").join("Xwayland");
            let _child = process::Command::new(xwayland).arg(":71").spawn();
            sleep_until_signaled();
        }
        "Xwayland" => {
            while !parent_gone() {
                thread::sleep(Duration::from_millis(50));
            }
        }
        "Xvfb" => {
            println!("99");
            let _ = io::stdout().flush();
            sleep_until_signaled();
        }
        "openbox" => sleep_until_signaled(),
        "xdotool" => process::exit(0),
        "xprop" => {
            println!("window id # 0x1");
        }
        _ => process::exit(1),
    }
}
"#;

const CALLER_BUS: &str = "unix:path=/caller-session";
const PRIVATE_BUS: &str = "unix:path=/fwtest-standin-bus";

unsafe extern "C" {
    fn kill(pid: i32, sig: i32) -> i32;
}

fn signal(pid: i32, sig: i32) {
    unsafe {
        kill(pid, sig);
    }
}

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

fn standin_dir() -> &'static Path {
    static DIR: OnceLock<PathBuf> = OnceLock::new();
    DIR.get_or_init(|| {
        let root = std::env::temp_dir().join(format!("fwtest-standin-{}", std::process::id()));
        let bin = root.join("bin");
        fs::create_dir_all(&bin).unwrap();
        let source = root.join("standin.rs");
        fs::write(&source, STANDIN_SOURCE).unwrap();
        let compiled = root.join("standin");
        let output = Command::new("rustc")
            .args(["--edition", "2024", "-O", "-o"])
            .arg(&compiled)
            .arg(&source)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "rustc stand-in failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        for name in [
            "dbus-daemon",
            "kwin_wayland",
            "Xwayland",
            "xdotool",
            "Xvfb",
            "openbox",
            "xprop",
        ] {
            let dest = bin.join(name);
            fs::copy(&compiled, &dest).unwrap();
            let mut perms = fs::metadata(&dest).unwrap().permissions();
            perms.set_mode(0o755);
            fs::set_permissions(&dest, perms).unwrap();
        }
        bin
    })
}

fn prepend_standin(path: &str) -> String {
    format!("{}:{path}", standin_dir().display())
}

struct Reap(Option<Child>);

impl Drop for Reap {
    fn drop(&mut self) {
        if let Some(child) = self.0.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

struct StopLogged {
    log: PathBuf,
}

impl Drop for StopLogged {
    fn drop(&mut self) {
        let Ok(text) = fs::read_to_string(&self.log) else {
            return;
        };
        for pid in logged_pids(&text) {
            signal(pid, 15);
        }
    }
}

fn logged_pids(text: &str) -> Vec<i32> {
    text.lines()
        .filter_map(|line| {
            let rest = line.split_once("pid=")?.1;
            rest.split_whitespace().next()?.parse().ok()
        })
        .collect()
}

fn logged_pid(text: &str, name: &str) -> i32 {
    let prefix = format!("{name} pid=");
    text.lines()
        .find_map(|line| {
            let rest = line.strip_prefix(&prefix)?;
            rest.split_whitespace().next()?.parse().ok()
        })
        .unwrap_or_else(|| panic!("{name} missing in {text}"))
}

fn init_repo(repo: &Path) {
    fs::create_dir_all(repo).unwrap();
    let git = Command::new("git")
        .arg("init")
        .current_dir(repo)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .unwrap();
    assert!(git.success());
}

fn fwtest(home: &Path, cwd: &Path) -> Command {
    let mut command = Command::new(env!("CARGO_BIN_EXE_fwtest"));
    command
        .current_dir(cwd)
        .env("HOME", home)
        .env("XDG_RUNTIME_DIR", home.join("no-systemd"))
        .env("DBUS_SESSION_BUS_ADDRESS", CALLER_BUS)
        .env("FWTEST_QUEUE_POLL_SECS", "1")
        .env("FWTEST_QUEUE_WAIT_SECS", "60")
        .env("FWTEST_PYTHON", home.join("python"))
        .env(
            "PATH",
            prepend_standin(&std::env::var("PATH").unwrap_or_default()),
        );
    command
}

fn assert_ran(output: &std::process::Output) {
    assert!(
        output.status.success(),
        "status={:?}\nstdout={}\nstderr={}",
        output.status,
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}

fn dead(pid: i32) {
    let found = identity::read_identity(pid).unwrap();
    assert!(found.is_none(), "pid {pid} still running: {found:?}");
}

#[test]
fn rig_drops_keep_stops_the_hidden_session_and_leaves_no_child() {
    let home = scratch();
    let repo = home.join("repo");
    init_repo(&repo);
    let log = home.join("rig.log");
    let standin_log = home.join("standin.log");
    let _stop = StopLogged {
        log: standin_log.clone(),
    };
    write_script(
        &repo.join("scripts/rig/drive.py"),
        &format!(
            r#"#!/bin/sh
printf 'keep=%s\n' "${{FLEXWEEK_RIG_KEEP-}}" >> "{log}"
printf 'display=%s\n' "${{FLEXWEEK_RIG_DISPLAY-}}" >> "{log}"
printf 'bus=%s\n' "${{FLEXWEEK_RIG_BUS-}}" >> "{log}"
printf 'runs=%s\n' "${{FLEXWEEK_RIG_RUNS_KEY-}}" >> "{log}"
printf 'args=%s\n' "$*" >> "{log}"
sleep 120 &
echo $! >> "{log}"
"#,
            log = log.display()
        ),
    );
    write_script(&home.join("python"), "#!/bin/sh\nexec \"$@\"\n");
    let output = fwtest(&home, &repo)
        .env("FLEXWEEK_RIG_KEEP", "1")
        .env("FWTEST_STANDIN_LOG", &standin_log)
        .args(["rig", "--design", "classic", "--tab", "day"])
        .output()
        .unwrap();
    assert_ran(&output);
    let text = fs::read_to_string(&log).unwrap();
    assert!(
        text.contains("keep=\n") || text.lines().any(|line| line == "keep="),
        "{text}"
    );
    assert!(!text.contains("keep=1"), "{text}");
    assert!(text.contains("display=:71\n"), "{text}");
    assert!(text.contains(&format!("bus={PRIVATE_BUS}\n")), "{text}");
    assert!(!text.contains(CALLER_BUS), "{text}");
    let runs = hidden::place(&repo).unwrap().runs_key;
    assert!(text.contains(&format!("runs={runs}\n")), "{text}");
    assert!(text.contains("--design"), "{text}");
    let pid = text
        .lines()
        .find_map(|line| line.parse::<i32>().ok())
        .expect(&text);
    dead(pid);
    let standin = fs::read_to_string(&standin_log).unwrap();
    assert!(
        standin.contains("kwin_wayland pid=") && standin.contains(&format!("bus={PRIVATE_BUS}")),
        "{standin}"
    );
    assert!(
        !standin
            .lines()
            .any(|line| line.starts_with("kwin_wayland ") && line.contains(CALLER_BUS)),
        "{standin}"
    );
    dead(logged_pid(&standin, "dbus-daemon"));
    dead(logged_pid(&standin, "kwin_wayland"));
    let _ = fs::remove_dir_all(home);
}

#[test]
fn rig_from_a_subdirectory_runs_at_the_checkout() {
    let home = scratch();
    let repo = home.join("repo");
    init_repo(&repo);
    let log = home.join("rig.log");
    let standin_log = home.join("standin.log");
    let _stop = StopLogged {
        log: standin_log.clone(),
    };
    write_script(
        &repo.join("scripts/rig/drive.py"),
        &format!(
            r#"#!/bin/sh
printf 'cwd=%s\n' "$(pwd)" >> "{log}"
"#,
            log = log.display()
        ),
    );
    write_script(&home.join("python"), "#!/bin/sh\nexec \"$@\"\n");
    let nested = repo.join("nested");
    fs::create_dir_all(&nested).unwrap();
    let output = fwtest(&home, &nested)
        .env("FWTEST_STANDIN_LOG", &standin_log)
        .args(["rig", "--design", "classic"])
        .output()
        .unwrap();
    assert_ran(&output);
    let text = fs::read_to_string(&log).unwrap();
    assert!(
        text.contains(&format!("cwd={}\n", repo.display())),
        "{text}"
    );
    assert!(
        !text.contains(&format!("cwd={}", nested.display())),
        "{text}"
    );
    let standin = fs::read_to_string(&standin_log).unwrap();
    dead(logged_pid(&standin, "dbus-daemon"));
    dead(logged_pid(&standin, "kwin_wayland"));
    let _ = fs::remove_dir_all(home);
}

fn rig_repo(home: &Path) -> PathBuf {
    let repo = home.join("repo");
    init_repo(&repo);
    write_script(&repo.join("scripts/rig/drive.py"), "#!/bin/sh\nexit 0\n");
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

fn write_sleep_session(repo: &Path, pid: i32, started: u64) {
    let place = hidden::place(repo).unwrap();
    if let Some(parent) = place.state.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    let json = format!(
        r#"{{"server":"kwin","display":":71","processes":[{{"pid":{pid},"name":"sleep","started":{started}}}],"bus":"unix:path=/tmp/private"}}"#
    );
    fs::write(place.state, json).unwrap();
}

fn spawn_sleep() -> Reap {
    Reap(Some(Command::new("sleep").arg("120").spawn().unwrap()))
}

#[test]
fn clean_stops_the_hidden_session_of_a_stale_rig_job() {
    let home = scratch();
    let repo = rig_repo(&home);
    let mut sleep = spawn_sleep();
    let child = sleep.0.as_ref().unwrap();
    let pid = child.id() as i32;
    let identity = identity::read_identity(pid).unwrap().unwrap();
    assert_eq!(identity.comm, "sleep");
    write_sleep_session(&repo, pid, identity.start_ticks);
    stale_record(
        &home,
        "stale-rig",
        &repo,
        rig_argv(&home, &repo),
        dead_owner(),
    );
    let output = clean_command(&home).output().unwrap();
    assert_ran(&output);
    assert!(
        sleep.0.as_mut().unwrap().try_wait().unwrap().is_some(),
        "sleep {pid} still running"
    );
    assert!(!hidden::place(&repo).unwrap().state.exists());
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
    let repo = rig_repo(&home);
    let mut sleep = spawn_sleep();
    let child = sleep.0.as_ref().unwrap();
    let pid = child.id() as i32;
    let identity = identity::read_identity(pid).unwrap().unwrap();
    write_sleep_session(&repo, pid, identity.start_ticks);
    let argv = vec!["sleep".to_string(), "1".to_string()];
    stale_record(&home, "stale-sleep", &repo, argv, dead_owner());
    let output = clean_command(&home).output().unwrap();
    assert_ran(&output);
    assert!(
        sleep.0.as_mut().unwrap().try_wait().unwrap().is_none(),
        "sleep {pid} was stopped"
    );
    assert!(hidden::place(&repo).unwrap().state.exists());
    let _ = fs::remove_dir_all(home);
}

#[test]
fn clean_leaves_the_hidden_session_alone_while_a_rig_job_is_live_in_that_checkout() {
    let home = scratch();
    let repo = rig_repo(&home);
    let mut sleep = spawn_sleep();
    let child = sleep.0.as_ref().unwrap();
    let pid = child.id() as i32;
    let identity = identity::read_identity(pid).unwrap().unwrap();
    write_sleep_session(&repo, pid, identity.start_ticks);
    let mut owner = Command::new("sleep").arg("120").spawn().unwrap();
    let owner_identity = identity::read_identity(owner.id() as i32).unwrap().unwrap();
    let live = ProcRef {
        pid: owner_identity.pid,
        start_ticks: owner_identity.start_ticks,
        comm: owner_identity.comm,
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
    assert_ran(&output);
    assert!(
        sleep.0.as_mut().unwrap().try_wait().unwrap().is_none(),
        "sleep {pid} was stopped"
    );
    assert!(hidden::place(&repo).unwrap().state.exists());
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_failing_hidden_session_stop_is_logged_and_the_record_still_goes() {
    let home = scratch();
    let repo = rig_repo(&home);
    let state = hidden::place(&repo).unwrap().state;
    fs::create_dir_all(&state).unwrap();
    stale_record(
        &home,
        "stale-rig",
        &repo,
        rig_argv(&home, &repo),
        dead_owner(),
    );
    let output = clean_command(&home).output().unwrap();
    assert_ran(&output);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains(&format!("hidden session stop for {}", repo.display())),
        "{stderr}"
    );
    assert!(
        stderr.contains(&format!("could not remove {}", state.display())),
        "{stderr}"
    );
    assert!(stderr.contains("Is a directory (os error 21)"), "{stderr}");
    assert!(
        job::list_job_files(&home.join(".flexweek-ui-harness/fwtest"))
            .unwrap()
            .is_empty()
    );
    let _ = fs::remove_dir_all(&state);
    let _ = fs::remove_dir_all(home);
}
