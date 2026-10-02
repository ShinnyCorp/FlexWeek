//! The rig command is tested with stand-in programs. No real KWin is started.
//!
//! The stand-ins are copies of one small binary. A shell script would show up
//! in `/proc` as `sh`, and stop would then refuse to signal it.

use std::ffi::OsStr;
use std::fs;
use std::ops::Deref;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

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

fn ppid() -> i32 {
    let text = fs::read_to_string("/proc/self/status").unwrap_or_default();
    for line in text.lines() {
        if let Some(rest) = line.strip_prefix("PPid:") {
            return rest.trim().parse().unwrap_or(1);
        }
    }
    1
}

fn process_dead(pid: i32) -> bool {
    let Ok(stat) = fs::read_to_string(format!("/proc/{pid}/stat")) else {
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
            if env::var("FWTEST_STANDIN_HOLD").ok().as_deref() == Some("1") {
                thread::sleep(Duration::from_secs(30));
            }
            let exe = env::current_exe().expect("current exe");
            let xwayland = exe.parent().expect("bin").join("Xwayland");
            let _child = process::Command::new(xwayland).arg(":71").spawn();
            sleep_until_signaled();
        }
        "Xwayland" => {
            // Once. Killing kwin reparents this process to init, which stays alive.
            let parent = ppid();
            while !process_dead(parent) {
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
    fn atexit(cb: extern "C" fn()) -> i32;
}

fn signal(pid: i32, sig: i32) {
    unsafe {
        kill(pid, sig);
    }
}

struct ScratchDir(PathBuf);

impl Drop for ScratchDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

impl Deref for ScratchDir {
    type Target = Path;

    fn deref(&self) -> &Path {
        &self.0
    }
}

impl AsRef<Path> for ScratchDir {
    fn as_ref(&self) -> &Path {
        &self.0
    }
}

impl AsRef<OsStr> for ScratchDir {
    fn as_ref(&self) -> &OsStr {
        self.0.as_os_str()
    }
}

fn scratch() -> ScratchDir {
    let path = std::env::temp_dir().join(format!(
        "fwtest-rig-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(path.join("no-systemd")).unwrap();
    ScratchDir(path)
}

/// Removes this checkout's state file when the test ends, including after a panic.
/// `place` names that file from the checkout's device and inode.
struct Sweep {
    state: PathBuf,
}

impl Sweep {
    fn new(repo: &Path) -> Self {
        Self {
            state: hidden::place(repo).unwrap().state,
        }
    }
}

impl Drop for Sweep {
    fn drop(&mut self) {
        if self.state.is_dir() {
            let _ = fs::remove_dir_all(&self.state);
        } else {
            let _ = fs::remove_file(&self.state);
        }
        if let Some(dir) = self.state.parent() {
            let _ = fs::remove_dir(dir);
        }
    }
}

/// One directory for every test in this process, so `fwtest clean` here does not
/// see a session another process recorded under `/tmp/flexweek-rig`.
fn rig_state() -> &'static Path {
    static DIR: OnceLock<PathBuf> = OnceLock::new();
    DIR.get_or_init(|| {
        let path = std::env::temp_dir().join(format!("fwtest-rig-state-{}", std::process::id()));
        fs::create_dir_all(&path).unwrap();
        unsafe {
            std::env::set_var("FWTEST_RIG_STATE", &path);
        }
        path
    })
}

fn rig_tests_lock() -> std::sync::MutexGuard<'static, ()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    let lock = LOCK.get_or_init(|| Mutex::new(()));
    lock.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
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

struct StandinPaths {
    root: PathBuf,
    bin: PathBuf,
}

static STANDIN: OnceLock<StandinPaths> = OnceLock::new();

fn is_standin_pid(pid: i32) -> bool {
    STANDIN
        .get()
        .is_some_and(|paths| exe_under(pid, &paths.root))
}

fn exe_under(pid: i32, root: &Path) -> bool {
    fs::read_link(format!("/proc/{pid}/exe"))
        .ok()
        .is_some_and(|exe| exe.starts_with(root))
}

fn signal_standins(root: &Path, sig: i32) {
    let Ok(entries) = fs::read_dir("/proc") else {
        return;
    };
    let me = std::process::id() as i32;
    for entry in entries.flatten() {
        let Ok(pid) = entry.file_name().to_string_lossy().parse::<i32>() else {
            continue;
        };
        if pid == me || pid <= 1 {
            continue;
        }
        if exe_under(pid, root) {
            signal(pid, sig);
        }
    }
}

extern "C" fn reap_standin_at_exit() {
    let Some(paths) = STANDIN.get() else {
        return;
    };
    signal_standins(&paths.root, 15);
    std::thread::sleep(Duration::from_millis(50));
    signal_standins(&paths.root, 9);
    let _ = fs::remove_dir_all(&paths.root);
}

fn standin_dir() -> &'static Path {
    &STANDIN
        .get_or_init(|| {
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
            // SAFETY: reap_standin_at_exit only signals processes whose executable
            // is inside this process's stand-in directory, then removes that directory.
            unsafe {
                atexit(reap_standin_at_exit);
            }
            StandinPaths { root, bin }
        })
        .bin
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
        let pids = logged_pids(&text);
        for pid in &pids {
            if is_standin_pid(*pid) {
                signal(*pid, 15);
            }
        }
        std::thread::sleep(Duration::from_millis(50));
        for pid in pids {
            if is_standin_pid(pid) {
                signal(pid, 9);
            }
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
    fwtest_command(home, cwd, true)
}

fn fwtest_command(home: &Path, cwd: &Path, isolate_systemd: bool) -> Command {
    rig_state();
    let mut command = Command::new(env!("CARGO_BIN_EXE_fwtest"));
    command
        .current_dir(cwd)
        .env("HOME", home)
        .env("FWTEST_QUEUE_POLL_SECS", "1")
        .env("FWTEST_QUEUE_WAIT_SECS", "60")
        .env("FWTEST_PYTHON", home.join("python"))
        .env(
            "PATH",
            prepend_standin(&std::env::var("PATH").unwrap_or_default()),
        );
    if isolate_systemd {
        command
            .env("XDG_RUNTIME_DIR", home.join("no-systemd"))
            .env("DBUS_SESSION_BUS_ADDRESS", CALLER_BUS);
    }
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
    let _guard = rig_tests_lock();
    rig_state();
    let caller_display = std::env::var("DISPLAY").unwrap_or_default();
    let home = scratch();
    let repo = home.join("repo");
    init_repo(&repo);
    let _sweep = Sweep::new(&repo);
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
printf 'live_display=%s\n' "${{DISPLAY-}}" >> "{log}"
printf 'caller_display=%s\n' "${{FLEXWEEK_CALLER_DISPLAY-}}" >> "{log}"
printf 'caller_bus=%s\n' "${{FLEXWEEK_CALLER_BUS-}}" >> "{log}"
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
    assert!(
        !text.lines().any(|line| line == format!("bus={CALLER_BUS}")),
        "{text}"
    );
    let runs = hidden::place(&repo).unwrap().runs_key;
    assert!(text.contains(&format!("runs={runs}\n")), "{text}");
    assert!(text.contains("--design"), "{text}");
    assert!(
        text.lines()
            .any(|line| line == format!("live_display={caller_display}")),
        "{text}"
    );
    assert!(
        text.lines()
            .any(|line| line == format!("caller_display={caller_display}")),
        "{text}"
    );
    assert!(
        text.lines()
            .any(|line| line == format!("caller_bus={CALLER_BUS}")),
        "{text}"
    );
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
    let _guard = rig_tests_lock();
    rig_state();
    let home = scratch();
    let repo = home.join("repo");
    init_repo(&repo);
    let _sweep = Sweep::new(&repo);
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

fn stale_record(
    home: &Path,
    id: &str,
    repo: &Path,
    argv: Vec<String>,
    owner: ProcRef,
    processes: Vec<ProcRef>,
) {
    let job = JobRecord {
        id: id.to_string(),
        checkout: repo.to_path_buf(),
        argv,
        started: "2026-09-29T06:15:00Z".to_string(),
        owner,
        processes,
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
    rig_state();
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
    rig_state();
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
    let _guard = rig_tests_lock();
    rig_state();
    let home = scratch();
    let repo = rig_repo(&home);
    let _sweep = Sweep::new(&repo);
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
        Vec::new(),
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
fn clean_stops_a_session_named_only_by_its_state_file() {
    let _guard = rig_tests_lock();
    rig_state();
    let home = scratch();
    let repo = rig_repo(&home);
    let _sweep = Sweep::new(&repo);
    let mut sleep = spawn_sleep();
    let child = sleep.0.as_ref().unwrap();
    let pid = child.id() as i32;
    let identity = identity::read_identity(pid).unwrap().unwrap();
    write_sleep_session(&repo, pid, identity.start_ticks);
    let output = clean_command(&home).output().unwrap();
    assert_ran(&output);
    assert!(
        sleep.0.as_mut().unwrap().try_wait().unwrap().is_some(),
        "sleep {pid} still running"
    );
    assert!(!hidden::place(&repo).unwrap().state.exists());
    let _ = fs::remove_dir_all(home);
}

#[test]
fn clean_stops_a_session_named_only_by_its_job_record() {
    let _guard = rig_tests_lock();
    rig_state();
    let home = scratch();
    let repo = rig_repo(&home);
    let _sweep = Sweep::new(&repo);
    let mut sleep = spawn_sleep();
    let child = sleep.0.as_ref().unwrap();
    let pid = child.id() as i32;
    let identity = identity::read_identity(pid).unwrap().unwrap();
    stale_record(
        &home,
        "stale-rig",
        &repo,
        rig_argv(&home, &repo),
        dead_owner(),
        vec![ProcRef {
            pid,
            start_ticks: identity.start_ticks,
            comm: identity.comm,
        }],
    );
    let state = hidden::place(&repo).unwrap().state;
    // place() names the state file from the checkout's device and inode. The
    // runner reuses that inode as soon as the previous test deletes its checkout,
    // so a state file that test left behind is found at this path.
    if state.is_dir() {
        fs::remove_dir_all(&state).unwrap();
    } else if state.exists() {
        fs::remove_file(&state).unwrap();
    }
    assert!(
        !state.exists(),
        "state file still present at {}",
        state.display()
    );
    let output = clean_command(&home).output().unwrap();
    assert_ran(&output);
    assert!(
        sleep.0.as_mut().unwrap().try_wait().unwrap().is_some(),
        "sleep {pid} still running"
    );
    let _ = fs::remove_dir_all(home);
}

#[test]
fn clean_leaves_the_hidden_session_alone_while_a_rig_job_is_live_in_that_checkout() {
    let _guard = rig_tests_lock();
    rig_state();
    let home = scratch();
    let repo = rig_repo(&home);
    let _sweep = Sweep::new(&repo);
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
    stale_record(
        &home,
        "live-rig",
        &repo,
        rig_argv(&home, &repo),
        live,
        Vec::new(),
    );
    stale_record(
        &home,
        "stale-rig",
        &repo,
        rig_argv(&home, &repo),
        dead_owner(),
        Vec::new(),
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
    let _guard = rig_tests_lock();
    rig_state();
    let home = scratch();
    let repo = rig_repo(&home);
    let _sweep = Sweep::new(&repo);
    let state = hidden::place(&repo).unwrap().state;
    fs::create_dir_all(&state).unwrap();
    stale_record(
        &home,
        "stale-rig",
        &repo,
        rig_argv(&home, &repo),
        dead_owner(),
        Vec::new(),
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

fn session_processes(path: &Path) -> Vec<(String, i32)> {
    let Ok(text) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let mut found = Vec::new();
    for part in text.split("\"pid\":").skip(1) {
        let Some((pid_text, rest)) = part.split_once(',') else {
            continue;
        };
        let Ok(pid) = pid_text.trim().parse::<i32>() else {
            continue;
        };
        let Some(after) = rest.split("\"name\":\"").nth(1) else {
            continue;
        };
        let Some(name) = after.split('"').next() else {
            continue;
        };
        found.push((name.to_string(), pid));
    }
    found
}

fn wait_for_names(path: &Path, names: &[&str]) -> Vec<(String, i32)> {
    let started = Instant::now();
    loop {
        let found = session_processes(path);
        let have: Vec<&str> = found.iter().map(|(name, _)| name.as_str()).collect();
        if names.iter().all(|name| have.contains(name)) {
            return found;
        }
        if started.elapsed() > Duration::from_secs(15) {
            panic!(
                "state file never recorded {names:?}: {found:?} in {}",
                path.display()
            );
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}

fn wait_for_job(root: &Path, names: &[&str]) -> fwtest::job::JobRecord {
    let started = Instant::now();
    loop {
        if let Ok(files) = job::list_job_files(root) {
            for path in files {
                if let Ok(job) = job::load_job_file(&path) {
                    let comms: Vec<&str> = job
                        .processes
                        .iter()
                        .map(|process| process.comm.as_str())
                        .collect();
                    if names.iter().all(|name| comms.contains(name)) {
                        return job;
                    }
                }
            }
        }
        if started.elapsed() > Duration::from_secs(15) {
            panic!("job record never listed {names:?}");
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}

fn wait_child(child: &mut Child) -> std::process::ExitStatus {
    let started = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(status)) => return status,
            Ok(None) if started.elapsed() > Duration::from_secs(20) => {
                let _ = child.kill();
                panic!("fwtest did not exit");
            }
            Ok(None) => std::thread::sleep(Duration::from_millis(50)),
            Err(error) => panic!("wait failed: {error}"),
        }
    }
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

#[test]
fn a_signal_during_startup_leaves_no_recorded_process_alive() {
    let _guard = rig_tests_lock();
    rig_state();
    let home = scratch();
    let repo = rig_repo(&home);
    let _sweep = Sweep::new(&repo);
    let standin_log = home.join("standin.log");
    let _stop = StopLogged {
        log: standin_log.clone(),
    };
    let mut child = fwtest(&home, &repo)
        .env("FWTEST_STANDIN_LOG", &standin_log)
        .env("FWTEST_STANDIN_HOLD", "1")
        .args(["rig", "--server", "kwin"])
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let state = hidden::place(&repo).unwrap().state;
    let recorded = wait_for_names(&state, &["dbus-daemon", "kwin_wayland"]);
    let job = wait_for_job(
        &home.join(".flexweek-ui-harness/fwtest"),
        &["dbus-daemon", "kwin_wayland"],
    );
    assert!(
        job.argv
            .iter()
            .any(|arg| arg.ends_with("scripts/rig/drive.py"))
    );
    let standin = fs::read_to_string(&standin_log).unwrap_or_default();
    assert!(
        !standin.contains("Xwayland"),
        "display was ready before the signal: {standin}"
    );
    signal(child.id() as i32, 15);
    let status = wait_child(&mut child);
    assert_eq!(status.code(), Some(143), "status={status:?}");
    for (_, pid) in &recorded {
        dead(*pid);
    }
    let _ = fs::remove_dir_all(home);
}

#[test]
fn session_processes_are_in_the_job_record_and_the_scope() {
    let _guard = rig_tests_lock();
    rig_state();
    let systemd = systemd_scope_works();
    let home = scratch();
    let repo = rig_repo(&home);
    let _sweep = Sweep::new(&repo);
    let standin_log = home.join("standin.log");
    let _stop = StopLogged {
        log: standin_log.clone(),
    };
    let mut child = fwtest_command(&home, &repo, false)
        .env("FWTEST_STANDIN_LOG", &standin_log)
        .env("FWTEST_STANDIN_HOLD", "1")
        .args(["rig", "--server", "kwin"])
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let state = hidden::place(&repo).unwrap().state;
    let recorded = wait_for_names(&state, &["dbus-daemon", "kwin_wayland"]);
    let job = wait_for_job(
        &home.join(".flexweek-ui-harness/fwtest"),
        &["dbus-daemon", "kwin_wayland"],
    );
    let dbus_pid = recorded
        .iter()
        .find(|(name, _)| name == "dbus-daemon")
        .unwrap()
        .1;
    let identity = identity::read_identity(dbus_pid).unwrap().unwrap();
    assert_eq!(identity.nice, 19, "session was not niced with the job");
    if systemd {
        let scope = job
            .scope
            .as_deref()
            .unwrap_or_else(|| panic!("session was not in a scope: {job:?}"));
        let cgroup = fs::read_to_string(format!("/proc/{dbus_pid}/cgroup")).unwrap();
        assert!(
            cgroup.contains(scope),
            "dbus-daemon was not in {scope}:\n{cgroup}"
        );
        let status = fs::read_to_string(format!("/proc/{dbus_pid}/status")).unwrap();
        let allowed = status
            .lines()
            .find_map(|line| line.strip_prefix("Cpus_allowed_list:"))
            .unwrap_or("")
            .trim();
        let cpus = fwtest::contain::half_cpus();
        let expected = if cpus.len() > 1 && cpus.windows(2).all(|pair| pair[1] == pair[0] + 1) {
            format!("{}-{}", cpus[0], cpus[cpus.len() - 1])
        } else {
            cpus.iter()
                .map(|cpu| cpu.to_string())
                .collect::<Vec<_>>()
                .join(",")
        };
        assert_eq!(allowed, expected, "{status}");
        assert_eq!(
            fwtest::contain::io_class(dbus_pid),
            3,
            "session did not inherit idle disk priority"
        );
    } else {
        assert!(job.scope.is_none());
    }
    let standin = fs::read_to_string(&standin_log).unwrap_or_default();
    assert!(standin.contains(&format!("bus={PRIVATE_BUS}")), "{standin}");
    signal(child.id() as i32, 15);
    let status = wait_child(&mut child);
    assert_eq!(status.code(), Some(143), "status={status:?}");
    for (_, pid) in &recorded {
        dead(*pid);
    }
    let _ = fs::remove_dir_all(home);
}

#[test]
fn rig_list_does_not_start_a_session() {
    let _guard = rig_tests_lock();
    rig_state();
    let home = scratch();
    let repo = home.join("repo");
    init_repo(&repo);
    let _sweep = Sweep::new(&repo);
    let log = home.join("drive.log");
    let standin_log = home.join("standin.log");
    let _stop = StopLogged {
        log: standin_log.clone(),
    };
    write_script(
        &repo.join("scripts/rig/drive.py"),
        &format!(
            "#!/bin/sh\nprintf '%s\\n' \"$*\" > \"{log}\"\n",
            log = log.display()
        ),
    );
    write_script(&home.join("python"), "#!/bin/sh\nexec \"$@\"\n");
    let output = fwtest(&home, &repo)
        .env("FWTEST_STANDIN_LOG", &standin_log)
        .args(["rig", "--list"])
        .output()
        .unwrap();
    assert_ran(&output);
    let text = fs::read_to_string(&log).unwrap();
    assert!(text.contains("--list"), "{text}");
    let standin = fs::read_to_string(&standin_log).unwrap_or_default();
    assert!(
        !standin.contains("dbus-daemon"),
        "list started a session: {standin}"
    );
    assert!(!hidden::place(&repo).unwrap().state.exists());
    let _ = fs::remove_dir_all(home);
}
