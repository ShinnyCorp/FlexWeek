//! One contained job: subreaper, process group, low priority, and a stop that
//! reaches grandchildren which called `setsid`.

use std::collections::{HashMap, HashSet};
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicI32, AtomicU32, Ordering};
use std::sync::mpsc::{self, RecvTimeoutError};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use nix::sys::signal::Signal;

use crate::clean;
use crate::identity::{self, ProcIdentity};
use crate::job::{self, JobLimits, JobRecord, ProcRef};
use crate::queue;
use crate::state;

static INTERRUPTED: AtomicI32 = AtomicI32::new(0);
static JOBS_STARTED: AtomicU32 = AtomicU32::new(0);

const POLL: Duration = Duration::from_millis(250);
const PUMP_GRACE: Duration = Duration::from_millis(400);
const STOP_SLICE: Duration = Duration::from_secs(3);
const KEEP_LOGS: usize = 20;

extern "C" fn on_stop_signal(signal: i32) {
    INTERRUPTED.store(signal, Ordering::SeqCst);
}

pub fn half_cpus() -> Vec<usize> {
    let mut allowed = Vec::new();
    // SAFETY: cpu_set_t is a POD bitmask. sched_getaffinity writes it; CPU_ISSET
    // only reads bits the kernel set. A failed call leaves allowed empty.
    unsafe {
        let mut set = std::mem::zeroed::<nix::libc::cpu_set_t>();
        if nix::libc::sched_getaffinity(0, std::mem::size_of::<nix::libc::cpu_set_t>(), &mut set)
            == 0
        {
            for cpu in 0..nix::libc::CPU_SETSIZE as usize {
                if nix::libc::CPU_ISSET(cpu, &set) {
                    allowed.push(cpu);
                }
            }
        }
    }
    if allowed.is_empty() {
        let count = std::thread::available_parallelism()
            .map(|n| n.get())
            .unwrap_or(1);
        allowed.extend(0..count);
    }
    let take = (allowed.len() / 2).max(1);
    allowed.into_iter().take(take).collect()
}

pub struct Session {
    root: PathBuf,
    _lock: queue::MachineLock,
}

/// A finished job: its exit code and the log holding its combined output.
pub struct Ran {
    pub code: u8,
    pub log: PathBuf,
}

impl Session {
    pub fn run(&self, argv: &[String], timeout_secs: Option<u64>) -> io::Result<u8> {
        supervise(&self.root, argv, timeout_secs, None, true).map(|ran| ran.code)
    }

    pub fn run_in(&self, argv: &[String], timeout_secs: Option<u64>, cwd: &Path) -> io::Result<u8> {
        supervise(&self.root, argv, timeout_secs, Some(cwd), true).map(|ran| ran.code)
    }

    /// Like `run_in`, but the output goes only to the job's log file.
    pub fn run_logged_in(
        &self,
        argv: &[String],
        timeout_secs: Option<u64>,
        cwd: &Path,
    ) -> io::Result<Ran> {
        supervise(&self.root, argv, timeout_secs, Some(cwd), false)
    }
}

pub fn session() -> Result<Session, u8> {
    let root = match state::harness_root() {
        Ok(root) => root,
        Err(message) => {
            eprintln!("{message}");
            return Err(2);
        }
    };
    let held = match queue::lock(&root) {
        Ok(held) => held,
        Err(error) => {
            eprintln!("could not take the job lock: {error}");
            return Err(1);
        }
    };
    if let Err(error) = queue::wait_for_other_suites() {
        if queue::is_wait_timeout(&error) {
            return Err(75);
        }
        eprintln!("could not see whether another suite is running: {error}");
        return Err(1);
    }
    match clean::clean(&root) {
        Ok(report) if report.survived.is_empty() => {}
        Ok(report) => {
            eprintln!(
                "still running: {}",
                report
                    .survived
                    .iter()
                    .map(|pid| pid.to_string())
                    .collect::<Vec<_>>()
                    .join(" ")
            );
            return Err(1);
        }
        Err(error) => {
            eprintln!("clean failed: {error}");
            return Err(1);
        }
    }
    Ok(Session { root, _lock: held })
}

pub fn execute(argv: &[String], timeout_secs: Option<u64>) -> u8 {
    if argv.is_empty() {
        eprintln!("fwtest run needs a command");
        return 2;
    }
    let session = match session() {
        Ok(session) => session,
        Err(code) => return code,
    };
    match session.run(argv, timeout_secs) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("run failed: {error}");
            1
        }
    }
}

fn supervise(
    root: &Path,
    argv: &[String],
    timeout_secs: Option<u64>,
    cwd: Option<&Path>,
    echo: bool,
) -> io::Result<Ran> {
    INTERRUPTED.store(0, Ordering::SeqCst);
    install_stop_signals()?;
    become_subreaper()?;
    let cpus = half_cpus();
    let before = children_of(std::process::id() as i32);
    let id = job_id(std::process::id());
    let scope_name = format!("fwtest-{id}.scope");
    let (mut child, scope) = spawn_job(argv, &cpus, &scope_name, cwd)?;
    let mut cgroup_procs = scope.as_deref().and_then(resolve_cgroup_procs);
    let owner = identity::read_identity(std::process::id() as i32)?
        .ok_or_else(|| io::Error::other("cannot read fwtest's own process identity"))?;
    let mut job = JobRecord {
        id: id.clone(),
        checkout: cwd
            .map(Path::to_path_buf)
            .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from("/"))),
        argv: argv.to_vec(),
        started: utc_now(),
        owner: ProcRef {
            pid: owner.pid,
            start_ticks: owner.start_ticks,
            comm: owner.comm,
        },
        processes: Vec::new(),
        limits: JobLimits {
            nice: 19,
            io: "idle".to_string(),
            cpus: cpus.clone(),
            timeout: timeout_secs.unwrap_or(0),
        },
        scope,
    };
    let (log, log_path) = open_log(root, &id)?;
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let log_out = log.try_clone()?;
    let log_err = log.try_clone()?;
    let echo_out: Box<dyn Write + Send> = if echo {
        Box::new(io::stdout())
    } else {
        Box::new(io::sink())
    };
    let echo_err: Box<dyn Write + Send> = if echo {
        Box::new(io::stderr())
    } else {
        Box::new(io::sink())
    };
    let pump_out = std::thread::spawn(move || {
        if let Some(pipe) = stdout {
            let _ = pump(pipe, echo_out, log_out);
        }
    });
    let pump_err = std::thread::spawn(move || {
        if let Some(pipe) = stderr {
            let _ = pump(pipe, echo_err, log_err);
        }
    });
    let started = Instant::now();
    let timeout = timeout_secs.map(Duration::from_secs);
    let child_pid = child.id() as i32;
    let exit_code = loop {
        refresh_processes(root, &mut job, &before, child_pid, &mut cgroup_procs)?;
        if let Some(signal) = taken_interrupt() {
            let survived = stop_job(&job, &before, cgroup_procs.as_deref())?;
            break if survived.is_empty() {
                128u8.saturating_add(signal as u8)
            } else {
                1
            };
        }
        if timeout.is_some_and(|limit| started.elapsed() >= limit) {
            let _ = stop_job(&job, &before, cgroup_procs.as_deref())?;
            eprintln!("timed out");
            break 124;
        }
        if let Some(status) = child.try_wait()? {
            refresh_processes(root, &mut job, &before, child_pid, &mut cgroup_procs)?;
            let _ = stop_job(&job, &before, cgroup_procs.as_deref())?;
            break status.code().unwrap_or(1) as u8;
        }
        std::thread::sleep(POLL);
    };
    drop(child);
    finish_pumps(pump_out, pump_err);
    let survived = leftover_pids(&before, cgroup_procs.as_deref());
    if survived.is_empty()
        && let Ok(path) = job::job_path(root, &job.id)
    {
        let _ = fs::remove_file(path);
    }
    Ok(Ran {
        code: exit_code,
        log: log_path,
    })
}

fn refresh_processes(
    root: &Path,
    job: &mut JobRecord,
    before: &HashSet<i32>,
    child_pid: i32,
    cgroup_procs: &mut Option<PathBuf>,
) -> io::Result<()> {
    if cgroup_procs.is_none()
        && let Some(scope) = job.scope.as_deref()
    {
        *cgroup_procs = resolve_cgroup_procs(scope);
    }
    let processes = snapshot(before, child_pid, cgroup_procs.as_deref());
    if proc_keys(&processes) != proc_keys(&job.processes) {
        job.processes = processes;
        job::save_job(root, job)?;
    }
    Ok(())
}

fn spawn_job(
    argv: &[String],
    cpus: &[usize],
    scope: &str,
    cwd: Option<&Path>,
) -> io::Result<(Child, Option<String>)> {
    if systemd_user_works() {
        match spawn_systemd(argv, scope, cpus, cwd) {
            Ok(child) => return Ok((child, Some(scope.to_string()))),
            Err(error) => eprintln!("systemd-run unavailable ({error}); containing without it"),
        }
    }
    Ok((spawn_direct(argv, cpus, cwd)?, None))
}

fn systemd_user_works() -> bool {
    Command::new("systemd-run")
        .args(["--user", "--scope", "--collect", "--quiet", "--", "true"])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn spawn_systemd(
    argv: &[String],
    scope: &str,
    cpus: &[usize],
    cwd: Option<&Path>,
) -> io::Result<Child> {
    let quota = format!("{}00%", cpus.len());
    let memory = format!("{}", half_ram_bytes());
    let cpus = cpus.to_vec();
    let mut command = Command::new("systemd-run");
    command
        .args([
            "--user",
            "--scope",
            "--collect",
            &format!("--unit={scope}"),
            "--quiet",
            &format!("--property=CPUQuota={quota}"),
            &format!("--property=MemoryMax={memory}"),
            "--",
        ])
        .args(argv)
        .stdin(Stdio::inherit())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(dir) = cwd {
        command.current_dir(dir);
    }
    // SAFETY: pre_exec runs in the child after fork and before exec. apply_limits
    // only issues async-signal-safe syscalls.
    unsafe {
        command.pre_exec(move || apply_limits(&cpus));
    }
    let child = command.spawn()?;
    // SAFETY: setpgid on a child we just spawned closes the race with the
    // child's own setpgid(0, 0) in apply_limits.
    unsafe {
        nix::libc::setpgid(child.id() as i32, child.id() as i32);
    }
    Ok(child)
}

fn spawn_direct(argv: &[String], cpus: &[usize], cwd: Option<&Path>) -> io::Result<Child> {
    let cpus = cpus.to_vec();
    let mut command = Command::new(&argv[0]);
    command
        .args(&argv[1..])
        .stdin(Stdio::inherit())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(dir) = cwd {
        command.current_dir(dir);
    }
    // SAFETY: pre_exec runs in the child after fork and before exec. apply_limits
    // only issues async-signal-safe syscalls.
    unsafe {
        command.pre_exec(move || apply_limits(&cpus));
    }
    let child = command.spawn()?;
    // SAFETY: setpgid on a child we just spawned closes the race with the
    // child's own setpgid(0, 0) in apply_limits.
    unsafe {
        nix::libc::setpgid(child.id() as i32, child.id() as i32);
    }
    Ok(child)
}

fn apply_limits(cpus: &[usize]) -> io::Result<()> {
    // SAFETY: called from pre_exec in the child. setpgid, setpriority, ioprio_set,
    // sched_setaffinity, prctl, getppid and raise are async-signal-safe. The
    // cpu_set_t is a local POD bitmask filled with CPU_SET before the affinity call.
    unsafe {
        if nix::libc::setpgid(0, 0) != 0 {
            return Err(io::Error::last_os_error());
        }
        if nix::libc::setpriority(nix::libc::PRIO_PROCESS, 0, 19) != 0 {
            return Err(io::Error::last_os_error());
        }
        // Idle I/O class is 3. The value is (class << 13) | level.
        let ioprio = 3 << 13;
        if nix::libc::syscall(nix::libc::SYS_ioprio_set, 1, 0, ioprio) != 0 {
            return Err(io::Error::last_os_error());
        }
        let mut set = std::mem::zeroed::<nix::libc::cpu_set_t>();
        for cpu in cpus {
            nix::libc::CPU_SET(*cpu, &mut set);
        }
        if nix::libc::sched_setaffinity(0, std::mem::size_of::<nix::libc::cpu_set_t>(), &set) != 0 {
            return Err(io::Error::last_os_error());
        }
        if nix::libc::prctl(nix::libc::PR_SET_PDEATHSIG, nix::libc::SIGTERM) != 0 {
            return Err(io::Error::last_os_error());
        }
        if nix::libc::getppid() == 1 {
            nix::libc::raise(nix::libc::SIGTERM);
        }
    }
    Ok(())
}

fn become_subreaper() -> io::Result<()> {
    // SAFETY: PR_SET_CHILD_SUBREAPER with arg 1 is a process-wide flag; no pointers.
    let rc = unsafe { nix::libc::prctl(nix::libc::PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) };
    if rc == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}

fn install_stop_signals() -> io::Result<()> {
    // SAFETY: the handler only stores into an AtomicI32. SA_SIGINFO is not set, so
    // the kernel calls this as a plain sighandler_t.
    unsafe {
        let mut action: nix::libc::sigaction = std::mem::zeroed();
        action.sa_sigaction = on_stop_signal as *const () as usize;
        nix::libc::sigemptyset(&mut action.sa_mask);
        for signal in [nix::libc::SIGINT, nix::libc::SIGTERM] {
            if nix::libc::sigaction(signal, &action, std::ptr::null_mut()) != 0 {
                return Err(io::Error::last_os_error());
            }
        }
    }
    Ok(())
}

fn taken_interrupt() -> Option<i32> {
    let signal = INTERRUPTED.load(Ordering::SeqCst);
    (signal > 0).then_some(signal)
}

struct ProcSnap {
    identities: HashMap<i32, ProcIdentity>,
    children: HashMap<i32, Vec<i32>>,
}

fn scan_proc() -> ProcSnap {
    let mut identities = HashMap::new();
    let mut children: HashMap<i32, Vec<i32>> = HashMap::new();
    let Ok(entries) = fs::read_dir("/proc") else {
        return ProcSnap {
            identities,
            children,
        };
    };
    for entry in entries.flatten() {
        let Ok(pid) = entry.file_name().to_string_lossy().parse::<i32>() else {
            continue;
        };
        let Ok(Some(identity)) = identity::read_identity(pid) else {
            continue;
        };
        children.entry(identity.ppid).or_default().push(pid);
        identities.insert(pid, identity);
    }
    ProcSnap {
        identities,
        children,
    }
}

fn children_of(pid: i32) -> HashSet<i32> {
    scan_proc()
        .children
        .get(&pid)
        .into_iter()
        .flatten()
        .copied()
        .collect()
}

fn collect_tree(pid: i32, into: &mut HashSet<i32>, snap: &ProcSnap) {
    let mut stack = vec![pid];
    while let Some(pid) = stack.pop() {
        if !into.insert(pid) {
            continue;
        }
        if let Some(children) = snap.children.get(&pid) {
            stack.extend(children);
        }
    }
}

fn snapshot(before: &HashSet<i32>, child_pid: i32, cgroup_procs: Option<&Path>) -> Vec<ProcRef> {
    let snap = scan_proc();
    let me = std::process::id() as i32;
    let mut pids = HashSet::new();
    collect_tree(child_pid, &mut pids, &snap);
    if let Some(identity) = snap.identities.get(&child_pid) {
        collect_group(identity.pgrp, me, before, &mut pids, &snap);
    }
    if let Some(children) = snap.children.get(&me) {
        for &pid in children {
            if !before.contains(&pid) {
                collect_tree(pid, &mut pids, &snap);
            }
        }
    }
    if let Some(path) = cgroup_procs {
        pids.extend(read_cgroup_procs(path));
    }
    pids.remove(&me);
    for pid in before {
        pids.remove(pid);
    }
    pids.into_iter()
        .filter_map(|pid| snap.identities.get(&pid).cloned())
        .map(proc_ref)
        .collect()
}

fn collect_group(
    pgrp: i32,
    me: i32,
    before: &HashSet<i32>,
    into: &mut HashSet<i32>,
    snap: &ProcSnap,
) {
    if pgrp <= 1 {
        return;
    }
    if snap
        .identities
        .get(&me)
        .is_some_and(|identity| identity.pgrp == pgrp)
    {
        return;
    }
    for (pid, identity) in &snap.identities {
        if identity.pgrp == pgrp && *pid != me && !before.contains(pid) {
            into.insert(*pid);
        }
    }
}

fn resolve_cgroup_procs(scope: &str) -> Option<PathBuf> {
    let output = Command::new("systemctl")
        .args(["--user", "show", "-p", "ControlGroup", "--value", scope])
        .output()
        .ok()?;
    let group = String::from_utf8_lossy(&output.stdout);
    let group = group.trim().trim_start_matches('/');
    if group.is_empty() {
        return None;
    }
    let path = Path::new("/sys/fs/cgroup").join(group).join("cgroup.procs");
    path.is_file().then_some(path)
}

fn read_cgroup_procs(path: &Path) -> Vec<i32> {
    fs::read_to_string(path)
        .unwrap_or_default()
        .split_whitespace()
        .filter_map(|token| token.parse().ok())
        .collect()
}

fn discover_remaining(
    before: &HashSet<i32>,
    cgroup_procs: Option<&Path>,
    targets: &mut HashMap<i32, u64>,
) {
    let snap = scan_proc();
    let me = std::process::id() as i32;
    let mut pids = HashSet::new();
    if let Some(children) = snap.children.get(&me) {
        for &pid in children {
            if !before.contains(&pid) {
                collect_tree(pid, &mut pids, &snap);
            }
        }
    }
    if let Some(path) = cgroup_procs {
        pids.extend(read_cgroup_procs(path));
    }
    pids.remove(&me);
    for pid in before {
        pids.remove(pid);
    }
    for pid in pids {
        if let Some(identity) = snap.identities.get(&pid) {
            targets.entry(pid).or_insert(identity.start_ticks);
        }
    }
}

fn stop_job(
    job: &JobRecord,
    before: &HashSet<i32>,
    cgroup_procs: Option<&Path>,
) -> io::Result<Vec<i32>> {
    if let Some(scope) = &job.scope {
        let _ = Command::new("systemctl")
            .args(["--user", "stop", scope])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    let mut targets: HashMap<i32, u64> = job
        .processes
        .iter()
        .map(|process| (process.pid, process.start_ticks))
        .collect();
    signal_until(
        &mut targets,
        before,
        cgroup_procs,
        Signal::SIGTERM,
        STOP_SLICE,
    )?;
    signal_until(
        &mut targets,
        before,
        cgroup_procs,
        Signal::SIGKILL,
        STOP_SLICE,
    )?;
    identity::reap_pids(targets.keys().copied());
    Ok(live_targets(&targets))
}

fn signal_until(
    targets: &mut HashMap<i32, u64>,
    before: &HashSet<i32>,
    cgroup_procs: Option<&Path>,
    signal: Signal,
    budget: Duration,
) -> io::Result<()> {
    let deadline = Instant::now() + budget;
    loop {
        discover_remaining(before, cgroup_procs, targets);
        let mut any = false;
        for (&pid, &ticks) in targets.iter() {
            if !ours_and_live(pid, ticks) {
                continue;
            }
            identity::send(pid, signal)?;
            any = true;
        }
        if !any || Instant::now() >= deadline {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}

fn ours_and_live(pid: i32, ticks: u64) -> bool {
    if pid <= 1 || pid as u32 == std::process::id() {
        return false;
    }
    identity::is_live_match(pid, ticks).unwrap_or(false)
}

fn live_targets(targets: &HashMap<i32, u64>) -> Vec<i32> {
    targets
        .iter()
        .filter(|(pid, ticks)| ours_and_live(**pid, **ticks))
        .map(|(pid, _)| *pid)
        .collect()
}

fn leftover_pids(before: &HashSet<i32>, cgroup_procs: Option<&Path>) -> Vec<i32> {
    let mut targets = HashMap::new();
    discover_remaining(before, cgroup_procs, &mut targets);
    for (&pid, &ticks) in &targets {
        if ours_and_live(pid, ticks) {
            let _ = identity::send(pid, Signal::SIGKILL);
        }
    }
    std::thread::sleep(Duration::from_millis(50));
    identity::reap_pids(targets.keys().copied());
    live_targets(&targets)
}

fn proc_keys(processes: &[ProcRef]) -> Vec<(i32, u64)> {
    let mut keys: Vec<_> = processes
        .iter()
        .map(|process| (process.pid, process.start_ticks))
        .collect();
    keys.sort_unstable();
    keys
}

fn proc_ref(identity: ProcIdentity) -> ProcRef {
    ProcRef {
        pid: identity.pid,
        start_ticks: identity.start_ticks,
        comm: identity.comm,
    }
}

fn finish_pumps(pump_out: std::thread::JoinHandle<()>, pump_err: std::thread::JoinHandle<()>) {
    let (tx, rx) = mpsc::channel();
    std::thread::spawn(move || {
        let _ = pump_out.join();
        let _ = pump_err.join();
        let _ = tx.send(());
    });
    let started = Instant::now();
    while started.elapsed() < PUMP_GRACE {
        if taken_interrupt().is_some() {
            return;
        }
        match rx.recv_timeout(Duration::from_millis(50)) {
            Ok(()) | Err(RecvTimeoutError::Disconnected) => return,
            Err(RecvTimeoutError::Timeout) => {}
        }
    }
}

fn open_log(root: &Path, id: &str) -> io::Result<(File, PathBuf)> {
    let dir = root.join("logs");
    fs::create_dir_all(&dir)?;
    let path = dir.join(format!("{id}.log"));
    let file = File::create(&path)?;
    prune_logs(&dir);
    Ok((file, path))
}

fn prune_logs(dir: &Path) {
    let Ok(entries) = fs::read_dir(dir) else {
        return;
    };
    let mut files: Vec<(SystemTime, PathBuf)> = Vec::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("log") {
            continue;
        }
        let modified = entry
            .metadata()
            .and_then(|meta| meta.modified())
            .unwrap_or(UNIX_EPOCH);
        files.push((modified, path));
    }
    files.sort_by_key(|left| std::cmp::Reverse(left.0));
    for (_, path) in files.into_iter().skip(KEEP_LOGS) {
        let _ = fs::remove_file(path);
    }
}

fn pump(mut pipe: impl Read, mut echo: impl Write, mut log: File) -> io::Result<()> {
    let mut buffer = [0u8; 8192];
    loop {
        let read = pipe.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        echo.write_all(&buffer[..read])?;
        log.write_all(&buffer[..read])?;
    }
    Ok(())
}

fn half_ram_bytes() -> u64 {
    let text = fs::read_to_string("/proc/meminfo").unwrap_or_default();
    for line in text.lines() {
        let Some(rest) = line.strip_prefix("MemTotal:") else {
            continue;
        };
        let kb: u64 = rest
            .split_whitespace()
            .next()
            .unwrap_or("0")
            .parse()
            .unwrap_or(0);
        return kb.saturating_mul(1024) / 2;
    }
    0
}

fn job_id(pid: u32) -> String {
    // Jobs in one process can start in the same second; each keeps its own log.
    let nth = JOBS_STARTED.fetch_add(1, Ordering::SeqCst);
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or(0);
    // SAFETY: gmtime_r writes the caller-provided tm; secs is a valid time_t.
    let tm = unsafe {
        let mut tm = std::mem::zeroed::<nix::libc::tm>();
        nix::libc::gmtime_r(&secs, &mut tm);
        tm
    };
    let id = format!(
        "{:04}{:02}{:02}-{:02}{:02}{:02}-{pid}",
        tm.tm_year + 1900,
        tm.tm_mon + 1,
        tm.tm_mday,
        tm.tm_hour,
        tm.tm_min,
        tm.tm_sec
    );
    if nth == 0 { id } else { format!("{id}-{nth}") }
}

fn utc_now() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or(0);
    // SAFETY: gmtime_r writes the caller-provided tm; secs is a valid time_t.
    let tm = unsafe {
        let mut tm = std::mem::zeroed::<nix::libc::tm>();
        nix::libc::gmtime_r(&secs, &mut tm);
        tm
    };
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        tm.tm_year + 1900,
        tm.tm_mon + 1,
        tm.tm_mday,
        tm.tm_hour,
        tm.tm_min,
        tm.tm_sec
    )
}
