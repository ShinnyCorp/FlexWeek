//! The hidden desktop for the real-pointer rig.
//!
//! KWin provides Xwayland on a virtual screen locally. Xvfb and Openbox provide
//! the same X11 interface on Linux CI. The state file records the processes this
//! module started, so stop signals those PIDs only when the start time and
//! command name still match. Each checkout has its own state, logs and KWin
//! socket. The display number is the one the server allocates.

use std::collections::HashMap;
use std::fs::{self, File};
use std::io::{self, Read};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::os::unix::io::AsRawFd;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdout, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

const WIDTH: &str = "1400";
const HEIGHT: &str = "900";
const X11_SOCKETS: &str = "/tmp/.X11-unix";

/// A session bus with no service directories, so nothing is activated on demand.
const BUS_CONFIG: &str = r#"<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <keep_umask/>
  <listen>unix:tmpdir=/tmp</listen>
  <auth>EXTERNAL</auth>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
"#;

type Env = HashMap<String, String>;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Server {
    Kwin,
    Xvfb,
}

impl Server {
    fn parse(text: &str) -> Option<Self> {
        match text {
            "kwin" => Some(Self::Kwin),
            "xvfb" => Some(Self::Xvfb),
            _ => None,
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Kwin => "kwin",
            Self::Xvfb => "xvfb",
        }
    }

    /// `running` asks for the current set, which includes the private bus daemon.
    fn live_count(self) -> usize {
        match self {
            Self::Kwin => 2,
            Self::Xvfb => 3,
        }
    }

    /// State files from before the bus daemon was recorded are still stopped.
    fn readable(self, count: usize) -> bool {
        match self {
            Self::Kwin => count == 1 || count == 2,
            Self::Xvfb => count == 2 || count == 3,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct OwnedProcess {
    pid: i32,
    name: String,
    started: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct Session {
    server: Server,
    display: String,
    processes: Vec<OwnedProcess>,
    bus: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct SessionFile {
    server: String,
    display: String,
    processes: Vec<OwnedProcess>,
    #[serde(default)]
    bus: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Place {
    pub state: PathBuf,
    pub socket: String,
    pub runs_key: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Started {
    pub display: String,
    pub bus: String,
    pub runs_key: String,
}

enum PipePoll {
    Line(String),
    Pending,
}

/// Directory that holds one `session.json` per checkout. `FWTEST_RIG_STATE` moves
/// it for tests so one test process does not stop a session another process recorded.
pub(crate) fn state_root() -> PathBuf {
    match std::env::var_os("FWTEST_RIG_STATE") {
        Some(path) if !path.is_empty() => PathBuf::from(path),
        _ => PathBuf::from("/tmp/flexweek-rig"),
    }
}

pub fn place(checkout: &Path) -> Result<Place, String> {
    let resolved = fs::canonicalize(checkout)
        .map_err(|error| format!("cannot identify checkout {}: {error}", checkout.display()))?;
    let meta = fs::metadata(&resolved).map_err(|error| error.to_string())?;
    let key = format!("{:x}-{:x}", meta.dev(), meta.ino());
    Ok(Place {
        state: state_root().join(&key).join("session.json"),
        socket: format!("flexweek-rig-{key}"),
        runs_key: key,
    })
}

pub fn start(checkout: &Path, server: &str) -> Result<Started, String> {
    let located = place(checkout)?;
    let mut host = RealHost::new(located.clone());
    let started = start_on(&mut host, server)?;
    Ok(Started {
        display: started.display,
        bus: started.bus,
        runs_key: located.runs_key,
    })
}

pub fn stop(checkout: &Path) -> Result<(), String> {
    let located = place(checkout)?;
    stop_state(&located.state)
}

/// Stop the session recorded at `state`, whether or not a job file still names it.
pub fn stop_state(state: &Path) -> Result<(), String> {
    stop_at(state, Path::new("/proc"), &mut real_kill)
}

#[derive(Debug)]
struct StartedInner {
    display: String,
    bus: String,
}

/// Processes started so far. Drop stops them unless start finished.
struct Armed<'a> {
    host: &'a mut dyn Host,
    pids: Vec<i32>,
    armed: bool,
}

impl Drop for Armed<'_> {
    fn drop(&mut self) {
        if !self.armed {
            return;
        }
        for pid in self.pids.drain(..).rev() {
            self.host.terminate(pid);
        }
    }
}

fn remember(
    armed: &mut Armed<'_>,
    server: Server,
    display: &str,
    processes: &[OwnedProcess],
    bus: &str,
) -> Result<(), String> {
    armed.host.save(&Session {
        server,
        display: display.to_string(),
        processes: processes.to_vec(),
        bus: bus.to_string(),
    })
}

fn start_on(host: &mut dyn Host, server: &str) -> Result<StartedInner, String> {
    let server = if server == "auto" {
        if host.which("kwin_wayland") {
            "kwin"
        } else {
            "xvfb"
        }
    } else {
        server
    };
    let server = Server::parse(server).ok_or_else(|| format!("Unknown server '{server}'"))?;
    if let Some(current) = host.read_state()
        && host.running().is_some()
        && current.server == server
    {
        return Ok(StartedInner {
            display: current.display,
            bus: current.bus,
        });
    }
    if host.has_record() {
        host.stop()?;
    }
    let mut armed = Armed {
        host,
        pids: Vec::new(),
        armed: true,
    };
    let started = start_children(&mut armed, server);
    if started.is_ok() {
        armed.armed = false;
    }
    started
}

fn start_children(armed: &mut Armed<'_>, server: Server) -> Result<StartedInner, String> {
    let base = armed.host.base_env();
    let (bus_pid, address) = armed.host.start_bus(&base)?;
    armed.pids.push(bus_pid);
    let result = (|| {
        let daemon = armed.host.owned(bus_pid, "dbus-daemon")?;
        remember(armed, server, "", std::slice::from_ref(&daemon), &address)?;
        let mut env = base.clone();
        env.insert("DBUS_SESSION_BUS_ADDRESS".to_string(), address.clone());
        match server {
            Server::Kwin => start_kwin(armed, &env, &daemon, &address),
            Server::Xvfb => start_xvfb(armed, &env, &daemon, &address),
        }
    })();
    armed.host.close_stdout(bus_pid);
    result
}

fn start_kwin(
    armed: &mut Armed<'_>,
    env: &Env,
    daemon: &OwnedProcess,
    address: &str,
) -> Result<StartedInner, String> {
    let socket = armed.host.socket_name();
    let command = vec![
        "kwin_wayland".to_string(),
        "--virtual".to_string(),
        "--xwayland".to_string(),
        "--no-lockscreen".to_string(),
        "--no-global-shortcuts".to_string(),
        "--socket".to_string(),
        socket,
        "--width".to_string(),
        WIDTH.to_string(),
        "--height".to_string(),
        HEIGHT.to_string(),
    ];
    let pid = armed.host.launch(&command, "kwin.log", env, false)?;
    armed.pids.push(pid);
    let owned = armed.host.owned(pid, "kwin_wayland")?;
    remember(
        armed,
        Server::Kwin,
        "",
        &[daemon.clone(), owned.clone()],
        address,
    )?;
    let begun = Instant::now();
    while armed.host.before_deadline(begun, 20) {
        if armed.host.exited(pid) {
            return Err(format!(
                "KWin exited; see {}",
                armed.host.log_path("kwin.log")
            ));
        }
        if let Some(display) = armed.host.kwin_display_of(pid)
            && armed.host.connects(&display, env)?
        {
            remember(
                armed,
                Server::Kwin,
                &display,
                &[daemon.clone(), owned],
                address,
            )?;
            return Ok(StartedInner {
                display,
                bus: address.to_string(),
            });
        }
        armed.host.pause();
    }
    Err("The hidden session's Xwayland never came up".to_string())
}

fn start_xvfb(
    armed: &mut Armed<'_>,
    env: &Env,
    daemon: &OwnedProcess,
    address: &str,
) -> Result<StartedInner, String> {
    let command = vec![
        "Xvfb".to_string(),
        "-displayfd".to_string(),
        "1".to_string(),
        "-screen".to_string(),
        "0".to_string(),
        format!("{WIDTH}x{HEIGHT}x24"),
        "-nolisten".to_string(),
        "tcp".to_string(),
        "-ac".to_string(),
    ];
    let pid = armed.host.launch(&command, "xvfb.log", env, true)?;
    armed.pids.push(pid);
    let xvfb = armed.host.owned(pid, "Xvfb")?;
    remember(
        armed,
        Server::Xvfb,
        "",
        &[daemon.clone(), xvfb.clone()],
        address,
    )?;
    let display = display_from_pipe(armed.host, pid)?;
    wait_for_display(armed.host, &display, env, pid)?;
    let mut display_env = env.clone();
    display_env.insert("DISPLAY".to_string(), display.clone());
    let openbox =
        armed
            .host
            .launch(&["openbox".to_string()], "openbox.log", &display_env, false)?;
    armed.pids.push(openbox);
    let window = armed.host.owned(openbox, "openbox")?;
    remember(
        armed,
        Server::Xvfb,
        "",
        &[daemon.clone(), xvfb.clone(), window.clone()],
        address,
    )?;
    wait_for_openbox(armed.host, &display_env, openbox)?;
    remember(
        armed,
        Server::Xvfb,
        &display,
        &[daemon.clone(), xvfb, window],
        address,
    )?;
    Ok(StartedInner {
        display,
        bus: address.to_string(),
    })
}

fn display_from_pipe(host: &mut dyn Host, pid: i32) -> Result<String, String> {
    let begun = Instant::now();
    while host.before_deadline(begun, 20) {
        if host.exited(pid) {
            return Err(format!("Xvfb exited; see {}", host.log_path("xvfb.log")));
        }
        if let PipePoll::Line(number) = host.poll_stdout(pid, Duration::from_millis(200))? {
            if is_decimal(&number) {
                host.close_stdout(pid);
                return Ok(format!(":{number}"));
            }
            return Err(format!("Xvfb reported an invalid display: '{number}'"));
        }
    }
    Err("Xvfb did not choose a display".to_string())
}

fn wait_for_display(host: &mut dyn Host, display: &str, env: &Env, pid: i32) -> Result<(), String> {
    let begun = Instant::now();
    while host.before_deadline(begun, 20) {
        if host.exited(pid) {
            return Err(format!(
                "The hidden X server exited; see {} logs",
                host.state_dir()
            ));
        }
        if host.connects(display, env)? {
            return Ok(());
        }
        host.pause();
    }
    Err(format!(
        "The hidden X display {display} never accepted connections"
    ))
}

fn wait_for_openbox(host: &mut dyn Host, env: &Env, pid: i32) -> Result<(), String> {
    let begun = Instant::now();
    while host.before_deadline(begun, 10) {
        if host.exited(pid) {
            return Err(format!(
                "Openbox exited; see {}",
                host.log_path("openbox.log")
            ));
        }
        if host.openbox_ready(env)? {
            return Ok(());
        }
        host.pause();
    }
    Err("Openbox did not take control of the hidden display".to_string())
}

fn is_display(text: &str) -> bool {
    let Some(rest) = text.strip_prefix(':') else {
        return false;
    };
    is_decimal(rest)
}

fn is_decimal(text: &str) -> bool {
    !text.is_empty() && text.bytes().all(|byte| byte.is_ascii_digit())
}

fn filtered_env<I, K, V>(vars: I) -> Env
where
    I: IntoIterator<Item = (K, V)>,
    K: AsRef<str>,
    V: AsRef<str>,
{
    vars.into_iter()
        .filter(|(key, _)| {
            let key = key.as_ref();
            key != "QT_IM_MODULE" && key != "XMODIFIERS"
        })
        .map(|(key, value)| (key.as_ref().to_string(), value.as_ref().to_string()))
        .collect()
}

fn which(name: &str) -> bool {
    let Some(path) = std::env::var_os("PATH") else {
        return false;
    };
    std::env::split_paths(&path).any(|dir| {
        let candidate = dir.join(name);
        fs::metadata(&candidate)
            .is_ok_and(|meta| meta.is_file() && meta.permissions().mode() & 0o111 != 0)
    })
}

fn process_state(proc_root: &Path, pid: i32) -> Option<(String, u64)> {
    let text = fs::read_to_string(proc_root.join(pid.to_string()).join("stat")).ok()?;
    let (_, rest) = text.rsplit_once(") ")?;
    let mut fields = rest.split_whitespace();
    let state = fields.next()?.to_string();
    let started = fields.nth(18)?.parse().ok()?;
    Some((state, started))
}

fn alive(proc_root: &Path, process: &OwnedProcess) -> bool {
    let Some((state, started)) = process_state(proc_root, process.pid) else {
        return false;
    };
    if state == "Z" || started != process.started {
        return false;
    }
    fs::read_to_string(proc_root.join(process.pid.to_string()).join("comm"))
        .is_ok_and(|text| text.trim() == process.name)
}

fn owned(proc_root: &Path, pid: i32, name: &str) -> Result<OwnedProcess, String> {
    let Some((_, started)) = process_state(proc_root, pid) else {
        return Err(format!("{name} exited before the hidden display was ready"));
    };
    Ok(OwnedProcess {
        pid,
        name: name.to_string(),
        started,
    })
}

fn kwin_display(proc_root: &Path, pid: i32) -> Option<String> {
    let tasks = fs::read_dir(proc_root.join(pid.to_string()).join("task")).ok()?;
    for task in tasks.flatten() {
        let Ok(children) = fs::read_to_string(task.path().join("children")) else {
            continue;
        };
        for child in children.split_whitespace() {
            let Ok(cmdline) = fs::read(proc_root.join(child).join("cmdline")) else {
                continue;
            };
            let args: Vec<&[u8]> = cmdline.split(|byte| *byte == 0).collect();
            if args.len() < 2 {
                continue;
            }
            let program = Path::new(std::ffi::OsStr::from_bytes(args[0]));
            if program.file_name() != Some(std::ffi::OsStr::from_bytes(b"Xwayland")) {
                continue;
            }
            let Ok(display) = std::str::from_utf8(args[1]) else {
                continue;
            };
            if is_display(display) {
                return Some(display.to_string());
            }
        }
    }
    None
}

fn read_session(path: &Path) -> Option<Session> {
    let text = fs::read_to_string(path).ok()?;
    let file: SessionFile = serde_json::from_str(&text).ok()?;
    let server = Server::parse(&file.server)?;
    if !is_display(&file.display) || !server.readable(file.processes.len()) {
        return None;
    }
    Some(Session {
        server,
        display: file.display,
        processes: file.processes,
        bus: file.bus,
    })
}

fn save_session(path: &Path, session: &Session) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let file = SessionFile {
        server: session.server.as_str().to_string(),
        display: session.display.clone(),
        processes: session.processes.clone(),
        bus: session.bus.clone(),
    };
    let text = serde_json::to_string(&file).map_err(|error| error.to_string())?;
    let pending = path.with_extension("new");
    fs::write(&pending, text).map_err(|error| error.to_string())?;
    fs::rename(&pending, path).map_err(|error| error.to_string())?;
    Ok(())
}

fn session_running(session: &Session, proc_root: &Path, x11: &Path) -> Option<String> {
    if session.bus.is_empty() || session.processes.len() != session.server.live_count() {
        return None;
    }
    if session
        .processes
        .first()
        .map(|process| process.name.as_str())
        != Some("dbus-daemon")
    {
        return None;
    }
    if !session
        .processes
        .iter()
        .all(|process| alive(proc_root, process))
    {
        return None;
    }
    if session.server == Server::Kwin {
        let pid = session.processes.last()?.pid;
        if kwin_display(proc_root, pid).as_deref() != Some(session.display.as_str()) {
            return None;
        }
    }
    let number = session.display.strip_prefix(':')?;
    x11.join(format!("X{number}"))
        .exists()
        .then(|| session.display.clone())
}

fn read_recorded(path: &Path) -> Vec<OwnedProcess> {
    let Ok(text) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let Ok(file) = serde_json::from_str::<SessionFile>(&text) else {
        return Vec::new();
    };
    if Server::parse(&file.server).is_none() {
        return Vec::new();
    }
    file.processes
}

fn stop_at(
    state: &Path,
    proc_root: &Path,
    kill: &mut dyn FnMut(i32, i32) -> io::Result<()>,
) -> Result<(), String> {
    for process in read_recorded(state).iter().rev() {
        signal_until_dead(proc_root, process, kill)?;
        // fwtest is the parent. A stopped child stays a zombie until waited.
        crate::identity::reap_pids([process.pid]);
    }
    match fs::remove_file(state) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(format!("could not remove {}: {error}", state.display())),
    }
}

fn signal_until_dead(
    proc_root: &Path,
    process: &OwnedProcess,
    kill: &mut dyn FnMut(i32, i32) -> io::Result<()>,
) -> Result<(), String> {
    if !alive(proc_root, process) {
        return Ok(());
    }
    kill(process.pid, libc_signal::TERM).map_err(|error| error.to_string())?;
    let deadline = Instant::now() + Duration::from_secs(3);
    while alive(proc_root, process) && Instant::now() < deadline {
        thread::sleep(Duration::from_millis(100));
    }
    if alive(proc_root, process) {
        kill(process.pid, libc_signal::KILL).map_err(|error| error.to_string())?;
        let deadline = Instant::now() + Duration::from_secs(3);
        while alive(proc_root, process) && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(100));
        }
    }
    Ok(())
}

fn real_kill(pid: i32, signal: i32) -> io::Result<()> {
    let rc = unsafe { nix::libc::kill(pid, signal) };
    if rc == 0 {
        return Ok(());
    }
    let error = io::Error::last_os_error();
    if error.raw_os_error() == Some(nix::libc::ESRCH) {
        Ok(())
    } else {
        Err(error)
    }
}

/// Signal numbers without pulling the whole libc API into every call.
mod libc_signal {
    pub const TERM: i32 = 15;
    pub const KILL: i32 = 9;
}

trait Host {
    fn which(&self, name: &str) -> bool;
    fn read_state(&self) -> Option<Session>;
    fn has_record(&self) -> bool;
    fn save(&mut self, session: &Session) -> Result<(), String>;
    fn stop(&mut self) -> Result<(), String>;
    fn running(&mut self) -> Option<String>;
    fn base_env(&self) -> Env;
    fn socket_name(&self) -> String;
    fn log_path(&self, name: &str) -> String;
    fn state_dir(&self) -> String;
    fn start_bus(&mut self, env: &Env) -> Result<(i32, String), String>;
    fn owned(&self, pid: i32, name: &str) -> Result<OwnedProcess, String>;
    fn launch(
        &mut self,
        command: &[String],
        log_name: &str,
        env: &Env,
        pipe: bool,
    ) -> Result<i32, String>;
    fn exited(&mut self, pid: i32) -> bool;
    fn terminate(&mut self, pid: i32);
    fn kwin_display_of(&self, pid: i32) -> Option<String>;
    fn connects(&mut self, display: &str, env: &Env) -> Result<bool, String>;
    fn poll_stdout(&mut self, pid: i32, timeout: Duration) -> Result<PipePoll, String>;
    fn close_stdout(&mut self, pid: i32);
    fn openbox_ready(&mut self, env: &Env) -> Result<bool, String>;
    fn before_deadline(&mut self, started: Instant, seconds: u64) -> bool;
    fn pause(&self);
}

struct RealHost {
    place: Place,
    proc_root: PathBuf,
    x11: PathBuf,
    children: HashMap<i32, Child>,
    pipes: HashMap<i32, LinePipe>,
}

struct LinePipe {
    stdout: ChildStdout,
    pending: Vec<u8>,
}

impl RealHost {
    fn new(place: Place) -> Self {
        Self {
            place,
            proc_root: PathBuf::from("/proc"),
            x11: PathBuf::from(X11_SOCKETS),
            children: HashMap::new(),
            pipes: HashMap::new(),
        }
    }
}

impl Host for RealHost {
    fn which(&self, name: &str) -> bool {
        which(name)
    }

    fn read_state(&self) -> Option<Session> {
        read_session(&self.place.state)
    }

    fn has_record(&self) -> bool {
        self.place.state.is_file()
    }

    fn save(&mut self, session: &Session) -> Result<(), String> {
        save_session(&self.place.state, session)
    }

    fn stop(&mut self) -> Result<(), String> {
        stop_at(&self.place.state, &self.proc_root, &mut real_kill)
    }

    fn running(&mut self) -> Option<String> {
        let session = read_session(&self.place.state)?;
        session_running(&session, &self.proc_root, &self.x11)
    }

    fn base_env(&self) -> Env {
        filtered_env(std::env::vars())
    }

    fn socket_name(&self) -> String {
        self.place.socket.clone()
    }

    fn log_path(&self, name: &str) -> String {
        self.place
            .state
            .parent()
            .unwrap_or(Path::new("/tmp/flexweek-rig"))
            .join(name)
            .display()
            .to_string()
    }

    fn state_dir(&self) -> String {
        self.place
            .state
            .parent()
            .unwrap_or(Path::new("/tmp/flexweek-rig"))
            .display()
            .to_string()
    }

    fn start_bus(&mut self, env: &Env) -> Result<(i32, String), String> {
        let parent = self.state_dir();
        fs::create_dir_all(&parent).map_err(|error| error.to_string())?;
        let config = Path::new(&parent).join("bus.conf");
        fs::write(&config, BUS_CONFIG).map_err(|error| error.to_string())?;
        let pid = self.launch(
            &[
                "dbus-daemon".to_string(),
                format!("--config-file={}", config.display()),
                "--nofork".to_string(),
                "--nopidfile".to_string(),
                "--print-address=1".to_string(),
            ],
            "bus.log",
            env,
            true,
        )?;
        let address = finish_bus(self, pid)?;
        Ok((pid, address))
    }

    fn owned(&self, pid: i32, name: &str) -> Result<OwnedProcess, String> {
        owned(&self.proc_root, pid, name)
    }

    fn launch(
        &mut self,
        command: &[String],
        log_name: &str,
        env: &Env,
        pipe: bool,
    ) -> Result<i32, String> {
        if command.is_empty() {
            return Err("refusing to launch an empty command".to_string());
        }
        let parent = self.state_dir();
        fs::create_dir_all(&parent).map_err(|error| error.to_string())?;
        let log_path = Path::new(&parent).join(log_name);
        let log = File::create(&log_path).map_err(|error| error.to_string())?;
        let stderr = log.try_clone().map_err(|error| error.to_string())?;
        let stdout = if pipe {
            Stdio::piped()
        } else {
            Stdio::from(log.try_clone().map_err(|error| error.to_string())?)
        };
        let mut cmd = Command::new(&command[0]);
        cmd.args(&command[1..])
            .env_clear()
            .envs(env)
            .stderr(Stdio::from(stderr))
            .stdout(stdout);
        // SAFETY: setsid is async-signal-safe and runs in the child after fork,
        // before exec. It gives the hidden server its own session so stopping
        // the rig does not depend on process-group membership.
        unsafe {
            use std::os::unix::process::CommandExt;
            cmd.pre_exec(|| {
                nix::unistd::setsid().map_err(io::Error::from)?;
                Ok(())
            });
        }
        let mut child = cmd
            .spawn()
            .map_err(|error| format!("could not run {}: {error}", command[0]))?;
        let pid = child.id() as i32;
        if pipe {
            let stdout = child
                .stdout
                .take()
                .ok_or_else(|| format!("{} did not give a pipe", command[0]))?;
            let fd = stdout.as_raw_fd();
            // SAFETY: the fd belongs to this ChildStdout. O_NONBLOCK changes
            // only this pipe's read side.
            unsafe {
                let flags = nix::libc::fcntl(fd, nix::libc::F_GETFL);
                if flags >= 0 {
                    nix::libc::fcntl(fd, nix::libc::F_SETFL, flags | nix::libc::O_NONBLOCK);
                }
            }
            self.pipes.insert(
                pid,
                LinePipe {
                    stdout,
                    pending: Vec::new(),
                },
            );
        }
        self.children.insert(pid, child);
        Ok(pid)
    }

    fn exited(&mut self, pid: i32) -> bool {
        match self.children.get_mut(&pid) {
            Some(child) => child.try_wait().ok().flatten().is_some(),
            None => true,
        }
    }

    fn terminate(&mut self, pid: i32) {
        let Some(child) = self.children.get_mut(&pid) else {
            return;
        };
        if child.try_wait().ok().flatten().is_some() {
            return;
        }
        let _ = real_kill(pid, libc_signal::TERM);
        let deadline = Instant::now() + Duration::from_secs(3);
        while Instant::now() < deadline {
            if child.try_wait().ok().flatten().is_some() {
                return;
            }
            thread::sleep(Duration::from_millis(50));
        }
        let _ = real_kill(pid, libc_signal::KILL);
        let deadline = Instant::now() + Duration::from_secs(3);
        while Instant::now() < deadline {
            if child.try_wait().ok().flatten().is_some() {
                return;
            }
            thread::sleep(Duration::from_millis(50));
        }
    }

    fn kwin_display_of(&self, pid: i32) -> Option<String> {
        kwin_display(&self.proc_root, pid)
    }

    fn connects(&mut self, display: &str, env: &Env) -> Result<bool, String> {
        let mut child = Command::new("xdotool")
            .arg("getmouselocation")
            .env_clear()
            .envs(env)
            .env("DISPLAY", display)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|error| format!("xdotool: {error}"))?;
        let deadline = Instant::now() + Duration::from_secs(2);
        loop {
            if Instant::now() >= deadline {
                let _ = child.kill();
                let _ = child.wait();
                return Ok(false);
            }
            if let Some(status) = child.try_wait().map_err(|error| error.to_string())? {
                return Ok(status.success());
            }
            thread::sleep(Duration::from_millis(20));
        }
    }

    fn poll_stdout(&mut self, pid: i32, timeout: Duration) -> Result<PipePoll, String> {
        let Some(pipe) = self.pipes.get_mut(&pid) else {
            return Ok(PipePoll::Pending);
        };
        if let Some(line) = take_line(&mut pipe.pending) {
            return Ok(PipePoll::Line(line));
        }
        let fd = pipe.stdout.as_raw_fd();
        let millis = i32::try_from(timeout.as_millis()).unwrap_or(i32::MAX);
        let mut fds = [nix::libc::pollfd {
            fd,
            events: nix::libc::POLLIN,
            revents: 0,
        }];
        let rc = unsafe { nix::libc::poll(fds.as_mut_ptr(), 1, millis) };
        if rc < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                return Ok(PipePoll::Pending);
            }
            return Err(error.to_string());
        }
        if rc == 0 {
            return Ok(PipePoll::Pending);
        }
        let mut buf = [0u8; 256];
        loop {
            match pipe.stdout.read(&mut buf) {
                Ok(0) => {
                    let line = String::from_utf8_lossy(&pipe.pending).trim().to_string();
                    pipe.pending.clear();
                    return Ok(PipePoll::Line(line));
                }
                Ok(count) => {
                    pipe.pending.extend_from_slice(&buf[..count]);
                    if let Some(line) = take_line(&mut pipe.pending) {
                        return Ok(PipePoll::Line(line));
                    }
                }
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                    return Ok(PipePoll::Pending);
                }
                Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
                Err(error) => return Err(error.to_string()),
            }
        }
    }

    fn close_stdout(&mut self, pid: i32) {
        self.pipes.remove(&pid);
    }

    fn openbox_ready(&mut self, env: &Env) -> Result<bool, String> {
        let mut child = Command::new("xprop")
            .args(["-root", "_NET_SUPPORTING_WM_CHECK"])
            .env_clear()
            .envs(env)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|error| format!("xprop: {error}"))?;
        let deadline = Instant::now() + Duration::from_secs(2);
        loop {
            if Instant::now() >= deadline {
                let _ = child.kill();
                let _ = child.wait();
                return Err("xprop timed out".to_string());
            }
            if let Some(status) = child.try_wait().map_err(|error| error.to_string())? {
                if !status.success() {
                    return Ok(false);
                }
                let mut stdout = String::new();
                if let Some(mut pipe) = child.stdout.take() {
                    let _ = pipe.read_to_string(&mut stdout);
                }
                return Ok(stdout.contains("window id #"));
            }
            thread::sleep(Duration::from_millis(20));
        }
    }

    fn before_deadline(&mut self, started: Instant, seconds: u64) -> bool {
        started.elapsed() < Duration::from_secs(seconds)
    }

    fn pause(&self) {
        thread::sleep(Duration::from_millis(200));
    }
}

fn take_line(pending: &mut Vec<u8>) -> Option<String> {
    let split = pending.iter().position(|byte| *byte == b'\n')?;
    let line: Vec<u8> = pending.drain(..=split).collect();
    Some(String::from_utf8_lossy(&line).trim().to_string())
}

/// Stops `pid` on drop unless disarmed. A panic while reading the bus uses this.
struct StopPid<'a> {
    host: &'a mut dyn Host,
    pid: Option<i32>,
}

impl Drop for StopPid<'_> {
    fn drop(&mut self) {
        if let Some(pid) = self.pid.take() {
            self.host.terminate(pid);
        }
    }
}

fn read_bus_line(host: &mut dyn Host, pid: i32) -> Result<String, String> {
    let begun = Instant::now();
    while host.before_deadline(begun, 10) {
        match host.poll_stdout(pid, Duration::from_millis(200))? {
            PipePoll::Line(line) if !line.is_empty() && !host.exited(pid) => return Ok(line),
            PipePoll::Line(_) => break,
            PipePoll::Pending => {
                if host.exited(pid) {
                    break;
                }
            }
        }
    }
    Err("The hidden session's D-Bus never gave its address".to_string())
}

fn finish_bus(host: &mut dyn Host, pid: i32) -> Result<String, String> {
    let mut stop = StopPid {
        host,
        pid: Some(pid),
    };
    let line = read_bus_line(stop.host, pid)?;
    stop.pid = None;
    Ok(line)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static TEMP_SEQ: AtomicU64 = AtomicU64::new(0);

    fn temp_dir() -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "fwtest-hidden-{}-{}",
            std::process::id(),
            TEMP_SEQ.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&path).unwrap();
        path
    }

    fn stat_line(pid: i32, comm: &str, state: &str, started: u64) -> String {
        let mut tail = vec![state.to_string()];
        tail.extend(std::iter::repeat_n("0".to_string(), 18));
        tail.push(started.to_string());
        format!("{pid} ({comm}) {}", tail.join(" "))
    }

    fn write_proc(proc_root: &Path, pid: i32, comm: &str, state: &str, started: u64) {
        let dir = proc_root.join(pid.to_string());
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("stat"), stat_line(pid, comm, state, started)).unwrap();
        fs::write(dir.join("comm"), format!("{comm}\n")).unwrap();
    }

    struct Fake {
        kwin_on_path: bool,
        state: Option<Session>,
        running_display: Option<String>,
        stopped: bool,
        launches: Vec<(Vec<String>, String, Env)>,
        saved: Vec<Session>,
        bus_address: String,
        bus_pid: i32,
        next_pid: i32,
        kwin_display: Option<String>,
        pipe_line: Option<String>,
        connects_answers: Vec<bool>,
        connects_calls: usize,
        openbox_answers: Vec<bool>,
        openbox_calls: usize,
        exited: bool,
        force_timeout: bool,
        deadline_checks: u32,
        socket: String,
        caller_bus: String,
        terminated: Vec<i32>,
        poll_error: bool,
        withhold_polls: u32,
        panic_in_connect: bool,
    }

    impl Fake {
        fn new() -> Self {
            Self {
                kwin_on_path: false,
                state: None,
                running_display: None,
                stopped: false,
                launches: Vec::new(),
                saved: Vec::new(),
                bus_address: "unix:path=/tmp/private".to_string(),
                bus_pid: 42,
                next_pid: 100,
                kwin_display: Some(":71".to_string()),
                pipe_line: None,
                connects_answers: Vec::new(),
                connects_calls: 0,
                openbox_answers: Vec::new(),
                openbox_calls: 0,
                exited: false,
                force_timeout: false,
                deadline_checks: 0,
                socket: "flexweek-rig-test".to_string(),
                caller_bus: "unix:path=/tmp/caller".to_string(),
                terminated: Vec::new(),
                poll_error: false,
                withhold_polls: 0,
                panic_in_connect: false,
            }
        }
    }

    impl Host for Fake {
        fn which(&self, name: &str) -> bool {
            name == "kwin_wayland" && self.kwin_on_path
        }

        fn read_state(&self) -> Option<Session> {
            self.state.clone()
        }

        fn has_record(&self) -> bool {
            self.state.is_some()
        }

        fn save(&mut self, session: &Session) -> Result<(), String> {
            self.saved.push(session.clone());
            self.state = Some(session.clone());
            Ok(())
        }

        fn stop(&mut self) -> Result<(), String> {
            self.stopped = true;
            self.state = None;
            self.running_display = None;
            Ok(())
        }

        fn running(&mut self) -> Option<String> {
            self.running_display.clone()
        }

        fn base_env(&self) -> Env {
            let mut env = HashMap::new();
            env.insert(
                "DBUS_SESSION_BUS_ADDRESS".to_string(),
                self.caller_bus.clone(),
            );
            env.insert("HOME".to_string(), "/home/test".to_string());
            env
        }

        fn socket_name(&self) -> String {
            self.socket.clone()
        }

        fn log_path(&self, name: &str) -> String {
            format!("/tmp/flexweek-rig/test/{name}")
        }

        fn state_dir(&self) -> String {
            "/tmp/flexweek-rig/test".to_string()
        }

        fn start_bus(&mut self, _env: &Env) -> Result<(i32, String), String> {
            Ok((self.bus_pid, self.bus_address.clone()))
        }

        fn owned(&self, pid: i32, name: &str) -> Result<OwnedProcess, String> {
            Ok(OwnedProcess {
                pid,
                name: name.to_string(),
                started: 1,
            })
        }

        fn launch(
            &mut self,
            command: &[String],
            log_name: &str,
            env: &Env,
            _pipe: bool,
        ) -> Result<i32, String> {
            self.launches
                .push((command.to_vec(), log_name.to_string(), env.clone()));
            let pid = self.next_pid;
            self.next_pid += 1;
            Ok(pid)
        }

        fn exited(&mut self, _pid: i32) -> bool {
            self.exited
        }

        fn terminate(&mut self, pid: i32) {
            self.terminated.push(pid);
        }

        fn kwin_display_of(&self, _pid: i32) -> Option<String> {
            self.kwin_display.clone()
        }

        fn connects(&mut self, _display: &str, _env: &Env) -> Result<bool, String> {
            if self.panic_in_connect {
                panic!("start blew up");
            }
            let answer = self
                .connects_answers
                .get(self.connects_calls)
                .copied()
                .unwrap_or(true);
            self.connects_calls += 1;
            Ok(answer)
        }

        fn poll_stdout(&mut self, _pid: i32, _timeout: Duration) -> Result<PipePoll, String> {
            if self.poll_error {
                return Err("poll failed".to_string());
            }
            if self.withhold_polls > 0 {
                self.withhold_polls -= 1;
                return Ok(PipePoll::Pending);
            }
            if let Some(line) = self.pipe_line.take() {
                return Ok(PipePoll::Line(line));
            }
            Ok(PipePoll::Pending)
        }

        fn close_stdout(&mut self, _pid: i32) {}

        fn openbox_ready(&mut self, _env: &Env) -> Result<bool, String> {
            let answer = self
                .openbox_answers
                .get(self.openbox_calls)
                .copied()
                .unwrap_or(true);
            self.openbox_calls += 1;
            Ok(answer)
        }

        fn before_deadline(&mut self, _started: Instant, _seconds: u64) -> bool {
            if self.force_timeout {
                return false;
            }
            self.deadline_checks += 1;
            self.deadline_checks < 40
        }

        fn pause(&self) {}
    }

    #[test]
    fn each_checkout_has_its_own_state_and_socket() {
        let root = temp_dir();
        fs::create_dir_all(root.join("first")).unwrap();
        fs::create_dir_all(root.join("second")).unwrap();
        let first = place(&root.join("first")).unwrap();
        let second = place(&root.join("second")).unwrap();
        assert_ne!(first.state, second.state);
        assert_ne!(first.socket, second.socket);
        assert_ne!(first.state, PathBuf::from("/tmp/flexweek-rig/session.json"));
        assert_ne!(first.state.parent(), second.state.parent());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn kwin_display_comes_from_its_xwayland_child() {
        let proc_root = temp_dir();
        let task = proc_root.join("42").join("task").join("42");
        fs::create_dir_all(&task).unwrap();
        fs::write(task.join("children"), "77").unwrap();
        fs::create_dir_all(proc_root.join("77")).unwrap();
        fs::write(
            proc_root.join("77").join("cmdline"),
            b"/usr/bin/Xwayland\0:76\0",
        )
        .unwrap();
        fs::create_dir_all(proc_root.join("88")).unwrap();
        fs::write(
            proc_root.join("88").join("cmdline"),
            b"/usr/bin/Xwayland\0:75\0",
        )
        .unwrap();
        assert_eq!(kwin_display(&proc_root, 42).as_deref(), Some(":76"));
        let _ = fs::remove_dir_all(proc_root);
    }

    #[test]
    fn running_rejects_a_display_no_longer_owned_by_kwin() {
        let proc_root = temp_dir();
        let x11 = temp_dir();
        write_proc(&proc_root, 41, "dbus-daemon", "S", 1);
        write_proc(&proc_root, 42, "kwin_wayland", "S", 1);
        let task = proc_root.join("42").join("task").join("42");
        fs::create_dir_all(&task).unwrap();
        fs::write(task.join("children"), "77").unwrap();
        fs::create_dir_all(proc_root.join("77")).unwrap();
        fs::write(
            proc_root.join("77").join("cmdline"),
            b"/usr/bin/Xwayland\0:72\0",
        )
        .unwrap();
        File::create(x11.join("X71")).unwrap();
        let session = Session {
            server: Server::Kwin,
            display: ":71".to_string(),
            processes: vec![
                OwnedProcess {
                    pid: 41,
                    name: "dbus-daemon".to_string(),
                    started: 1,
                },
                OwnedProcess {
                    pid: 42,
                    name: "kwin_wayland".to_string(),
                    started: 1,
                },
            ],
            bus: "unix:path=/tmp/dbus-private".to_string(),
        };
        assert_eq!(session_running(&session, &proc_root, &x11), None);
        fs::write(
            proc_root.join("77").join("cmdline"),
            b"/usr/bin/Xwayland\0:71\0",
        )
        .unwrap();
        assert_eq!(
            session_running(&session, &proc_root, &x11).as_deref(),
            Some(":71")
        );
        let _ = fs::remove_dir_all(proc_root);
        let _ = fs::remove_dir_all(x11);
    }

    #[test]
    fn auto_uses_xvfb_when_kwin_is_unavailable() {
        let mut fake = Fake::new();
        fake.pipe_line = Some("73".to_string());
        fake.connects_answers = vec![false, true];
        fake.openbox_answers = vec![false, true];
        let started = start_on(&mut fake, "auto").unwrap();
        assert_eq!(started.display, ":73");
        assert!(fake.connects_calls >= 2, "{}", fake.connects_calls);
        assert!(fake.openbox_calls >= 2, "{}", fake.openbox_calls);
        assert!(
            fake.launches
                .iter()
                .any(|(command, _, _)| command[0] == "Xvfb"),
            "{:?}",
            fake.launches
                .iter()
                .map(|(command, _, _)| &command[0])
                .collect::<Vec<_>>()
        );
        assert!(
            fake.launches
                .iter()
                .all(|(command, _, _)| command[0] != "kwin_wayland")
        );
        assert!(
            fake.saved.len() >= 2,
            "state must be written before the display is ready"
        );
        assert!(
            fake.saved
                .iter()
                .any(|session| session.display.is_empty() && !session.processes.is_empty())
        );
        let saved = fake.saved.last().unwrap();
        assert_eq!(saved.server, Server::Xvfb);
        assert_eq!(
            saved
                .processes
                .iter()
                .map(|process| process.name.as_str())
                .collect::<Vec<_>>(),
            vec!["dbus-daemon", "Xvfb", "openbox"]
        );
    }

    #[test]
    fn xvfb_rejects_a_display_it_did_not_allocate() {
        let mut fake = Fake::new();
        fake.pipe_line = Some("nope".to_string());
        let error = start_on(&mut fake, "xvfb").unwrap_err();
        assert!(
            error.contains("Xvfb reported an invalid display: 'nope'"),
            "{error}"
        );
    }

    #[test]
    fn switching_servers_stops_the_owned_session() {
        let mut fake = Fake::new();
        fake.state = Some(Session {
            server: Server::Kwin,
            display: ":71".to_string(),
            processes: vec![OwnedProcess {
                pid: 12345,
                name: "kwin_wayland".to_string(),
                started: 1,
            }],
            bus: String::new(),
        });
        fake.running_display = Some(":71".to_string());
        fake.pipe_line = Some("72".to_string());
        let started = start_on(&mut fake, "xvfb").unwrap();
        assert_eq!(started.display, ":72");
        assert!(fake.stopped);
    }

    #[test]
    fn stop_terminates_all_recorded_processes() {
        let root = temp_dir();
        let mut children = Vec::new();
        for _ in 0..3 {
            children.push(Command::new("sleep").arg("30").spawn().unwrap());
        }
        let processes = children
            .iter()
            .map(|child| owned(Path::new("/proc"), child.id() as i32, "sleep").unwrap())
            .collect();
        let state = root.join("session.json");
        save_session(
            &state,
            &Session {
                server: Server::Xvfb,
                display: ":73".to_string(),
                processes,
                bus: "unix:path=/tmp/dbus-private".to_string(),
            },
        )
        .unwrap();
        let mut signals = Vec::new();
        let stopped = stop_at(&state, Path::new("/proc"), &mut |pid, signal| {
            signals.push(signal);
            real_kill(pid, signal)
        });
        stopped.unwrap();
        assert_eq!(signals, vec![libc_signal::TERM; 3]);
        for child in &children {
            assert!(
                crate::identity::read_identity(child.id() as i32)
                    .unwrap()
                    .is_none()
            );
        }
        assert!(!state.exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn kwin_uses_private_bus_instead_of_callers() {
        let mut fake = Fake::new();
        fake.kwin_on_path = true;
        let started = start_on(&mut fake, "kwin").unwrap();
        assert_eq!(started.display, ":71");
        assert_eq!(started.bus, "unix:path=/tmp/private");
        let (command, log_name, env) = &fake.launches[0];
        assert_eq!(log_name, "kwin.log");
        assert_eq!(
            env.get("DBUS_SESSION_BUS_ADDRESS").map(String::as_str),
            Some("unix:path=/tmp/private")
        );
        assert_ne!(
            env.get("DBUS_SESSION_BUS_ADDRESS").map(String::as_str),
            Some(fake.caller_bus.as_str())
        );
        assert_eq!(
            command,
            &[
                "kwin_wayland",
                "--virtual",
                "--xwayland",
                "--no-lockscreen",
                "--no-global-shortcuts",
                "--socket",
                "flexweek-rig-test",
                "--width",
                "1400",
                "--height",
                "900",
            ]
        );
        assert!(fake.saved.iter().any(|session| {
            session.display.is_empty()
                && session
                    .processes
                    .iter()
                    .any(|process| process.name == "dbus-daemon")
        }));
        let saved = fake.saved.last().unwrap();
        assert_eq!(saved.display, ":71");
        assert_eq!(saved.bus, "unix:path=/tmp/private");
        assert_eq!(
            saved
                .processes
                .iter()
                .map(|process| process.name.as_str())
                .collect::<Vec<_>>(),
            vec!["dbus-daemon", "kwin_wayland"]
        );
    }

    #[test]
    fn kwin_waits_until_the_display_accepts_connections() {
        let mut fake = Fake::new();
        fake.connects_answers = vec![false, true];
        let started = start_on(&mut fake, "kwin").unwrap();
        assert_eq!(started.display, ":71");
        assert!(fake.connects_calls >= 2, "{}", fake.connects_calls);
    }

    #[test]
    fn stop_signals_bus_after_both_servers() {
        let proc_root = temp_dir();
        let state = proc_root.join("session.json");
        for (pid, name) in [(41, "dbus-daemon"), (42, "Xvfb"), (43, "openbox")] {
            write_proc(&proc_root, pid, name, "S", 1);
        }
        save_session(
            &state,
            &Session {
                server: Server::Xvfb,
                display: ":73".to_string(),
                processes: vec![
                    OwnedProcess {
                        pid: 41,
                        name: "dbus-daemon".to_string(),
                        started: 1,
                    },
                    OwnedProcess {
                        pid: 42,
                        name: "Xvfb".to_string(),
                        started: 1,
                    },
                    OwnedProcess {
                        pid: 43,
                        name: "openbox".to_string(),
                        started: 1,
                    },
                ],
                bus: "unix:path=/tmp/private".to_string(),
            },
        )
        .unwrap();
        let mut signals = Vec::new();
        stop_at(&state, &proc_root, &mut |pid, signal| {
            signals.push((pid, signal));
            let stat = proc_root.join(pid.to_string()).join("stat");
            let text = fs::read_to_string(&stat).unwrap().replace(" S ", " Z ");
            fs::write(stat, text).unwrap();
            Ok(())
        })
        .unwrap();
        assert_eq!(
            signals.iter().map(|(pid, _)| *pid).collect::<Vec<_>>(),
            vec![43, 42, 41]
        );
        assert!(
            signals
                .iter()
                .all(|(_, signal)| *signal == libc_signal::TERM)
        );
        assert!(!state.exists());
        let _ = fs::remove_dir_all(proc_root);
    }

    #[test]
    fn an_error_after_the_bus_starts_stops_what_was_started() {
        let mut fake = Fake::new();
        fake.kwin_on_path = true;
        fake.force_timeout = true;
        let error = start_on(&mut fake, "kwin").unwrap_err();
        assert!(error.contains("Xwayland never came up"), "{error}");
        assert!(
            fake.terminated.contains(&fake.bus_pid),
            "{:?}",
            fake.terminated
        );
        assert!(fake.terminated.contains(&100), "{:?}", fake.terminated);
    }

    #[test]
    fn a_panic_during_start_stops_what_was_started() {
        let mut fake = Fake::new();
        fake.kwin_on_path = true;
        fake.panic_in_connect = true;
        let caught = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _ = start_on(&mut fake, "kwin");
        }));
        assert!(caught.is_err());
        assert!(
            fake.terminated.contains(&fake.bus_pid),
            "{:?}",
            fake.terminated
        );
        assert!(fake.terminated.contains(&100), "{:?}", fake.terminated);
    }

    #[test]
    fn a_bus_error_stops_the_daemon() {
        let mut timed_out = Fake::new();
        timed_out.force_timeout = true;
        let timed_out_pid = timed_out.bus_pid;
        let error = finish_bus(&mut timed_out, timed_out_pid).unwrap_err();
        assert!(error.contains("never gave its address"), "{error}");
        assert_eq!(timed_out.terminated, vec![42]);

        let mut died = Fake::new();
        died.exited = true;
        let died_pid = died.bus_pid;
        let error = finish_bus(&mut died, died_pid).unwrap_err();
        assert!(error.contains("never gave its address"), "{error}");
        assert_eq!(died.terminated, vec![42]);

        let mut broken = Fake::new();
        broken.poll_error = true;
        let broken_pid = broken.bus_pid;
        let error = finish_bus(&mut broken, broken_pid).unwrap_err();
        assert_eq!(error, "poll failed");
        assert_eq!(broken.terminated, vec![42]);
    }

    #[test]
    fn the_bus_address_waits_for_a_whole_line() {
        let mut pending = b"unix:path=/tmp/part".to_vec();
        assert!(take_line(&mut pending).is_none());
        pending.extend_from_slice(b"ial\n");
        assert_eq!(
            take_line(&mut pending).as_deref(),
            Some("unix:path=/tmp/partial")
        );

        let mut fake = Fake::new();
        fake.withhold_polls = 2;
        fake.pipe_line = Some("unix:path=/tmp/private".to_string());
        let line = finish_bus(&mut fake, 42).unwrap();
        assert_eq!(line, "unix:path=/tmp/private");
        assert!(fake.terminated.is_empty(), "{:?}", fake.terminated);
    }

    #[test]
    fn stop_reads_a_session_saved_before_the_display_is_ready() {
        let root = temp_dir();
        let mut child = Command::new("sleep").arg("30").spawn().unwrap();
        let pid = child.id() as i32;
        let owned = owned(Path::new("/proc"), pid, "sleep").unwrap();
        let state = root.join("session.json");
        save_session(
            &state,
            &Session {
                server: Server::Kwin,
                display: String::new(),
                processes: vec![owned],
                bus: "unix:path=/tmp/private".to_string(),
            },
        )
        .unwrap();
        assert!(read_session(&state).is_none());
        let seen = format!(
            "recorded {:?}; state {:?}; comm {:?}",
            read_recorded(&state),
            process_state(Path::new("/proc"), pid),
            fs::read_to_string(format!("/proc/{pid}/comm"))
        );
        stop_at(&state, Path::new("/proc"), &mut real_kill).unwrap();
        // Asked of the child itself, not of /proc: once stopped it may still be listed there for a
        // moment as a zombie until its parent, this test, collects it.
        let stopped = (0..50).any(|_| {
            let done = matches!(child.try_wait(), Ok(Some(_)) | Err(_));
            if !done {
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            done
        });
        if !stopped {
            let _ = child.kill();
            let _ = child.wait();
        }
        assert!(stopped, "pid {pid} still running 5 s after stop ({seen})");
        assert!(!state.exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn private_bus_has_no_activatable_services() {
        if !which("dbus-daemon") || !which("busctl") {
            panic!(
                "dbus-daemon and busctl must be on PATH to check the private bus has no activatable services"
            );
        }
        let root = temp_dir();
        let mut host = RealHost::new(Place {
            state: root.join("session.json"),
            socket: "flexweek-rig-test".to_string(),
            runs_key: "test".to_string(),
        });
        let env = filtered_env(std::env::vars());
        let (pid, address) = host.start_bus(&env).unwrap();
        struct Kill(i32);
        impl Drop for Kill {
            fn drop(&mut self) {
                unsafe {
                    nix::libc::kill(self.0, libc_signal::TERM);
                }
            }
        }
        let _kill = Kill(pid);
        let output = Command::new("busctl")
            .arg(format!("--address={address}"))
            .args([
                "call",
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "ListActivatableNames",
            ])
            .output()
            .unwrap();
        host.terminate(pid);
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        assert_eq!(
            String::from_utf8_lossy(&output.stdout).trim(),
            "as 1 \"org.freedesktop.DBus\""
        );
        assert!(!BUS_CONFIG.contains("standard_session_servicedirs"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn stop_does_not_signal_a_reused_pid() {
        let root = temp_dir();
        let mut child = Command::new("sleep").arg("30").spawn().unwrap();
        let mut recorded = owned(Path::new("/proc"), child.id() as i32, "sleep").unwrap();
        recorded.started = 0;
        let state = root.join("session.json");
        save_session(
            &state,
            &Session {
                server: Server::Kwin,
                display: ":74".to_string(),
                processes: vec![recorded],
                bus: String::new(),
            },
        )
        .unwrap();
        stop_at(&state, Path::new("/proc"), &mut real_kill).unwrap();
        assert!(child.try_wait().unwrap().is_none());
        let _ = child.kill();
        let _ = child.wait();
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn filtered_env_drops_input_method_variables() {
        let env = filtered_env([
            ("HOME", "/home/test"),
            ("QT_IM_MODULE", "ibus"),
            ("XMODIFIERS", "@im=ibus"),
            ("DBUS_SESSION_BUS_ADDRESS", "unix:path=/tmp/caller"),
        ]);
        assert_eq!(env.get("HOME").map(String::as_str), Some("/home/test"));
        assert_eq!(
            env.get("DBUS_SESSION_BUS_ADDRESS").map(String::as_str),
            Some("unix:path=/tmp/caller")
        );
        assert!(!env.contains_key("QT_IM_MODULE"));
        assert!(!env.contains_key("XMODIFIERS"));
    }

    #[test]
    fn read_state_keeps_old_process_counts_and_rejects_the_rest() {
        let root = temp_dir();
        let path = root.join("session.json");
        let write = |body: &str| fs::write(&path, body).unwrap();
        write(
            r#"{"server":"kwin","display":":71","processes":[{"pid":1,"name":"kwin_wayland","started":1}]}"#,
        );
        assert!(read_session(&path).is_some());
        write(
            r#"{"server":"kwin","display":":71","processes":[{"pid":1,"name":"dbus-daemon","started":1},{"pid":2,"name":"kwin_wayland","started":1}],"bus":"unix:path=/tmp/p"}"#,
        );
        assert!(read_session(&path).is_some());
        write(
            r#"{"server":"kwin","display":"71","processes":[{"pid":1,"name":"kwin_wayland","started":1}]}"#,
        );
        assert!(read_session(&path).is_none());
        write(
            r#"{"server":"weston","display":":71","processes":[{"pid":1,"name":"kwin_wayland","started":1}]}"#,
        );
        assert!(read_session(&path).is_none());
        write(
            r#"{"server":"xvfb","display":":73","processes":[{"pid":1,"name":"dbus-daemon","started":1}]}"#,
        );
        assert!(read_session(&path).is_none());
        write(
            r#"{"server":"xvfb","display":":73","processes":[{"pid":1,"name":"dbus-daemon","started":1},{"pid":2,"name":"Xvfb","started":1}]}"#,
        );
        assert!(read_session(&path).is_some());
        write(
            r#"{"server":"kwin","display":":71","processes":[{"pid":1,"name":"kwin_wayland","started":1,"extra":1}]}"#,
        );
        assert!(read_session(&path).is_none());
        let _ = fs::remove_dir_all(root);
    }
}
