//! One contained job: subreaper, process group, low priority, and a stop that
//! reaches grandchildren which called `setsid`.

use std::collections::HashSet;
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicI32, Ordering};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use crate::clean;
use crate::identity::{self, ProcIdentity};
use crate::job::{self, JobLimits, JobRecord, ProcRef};
use crate::queue;
use crate::state;

static INTERRUPTED: AtomicI32 = AtomicI32::new(0);

extern "C" fn on_stop_signal(signal: i32) {
    INTERRUPTED.store(signal, Ordering::SeqCst);
}

pub fn half_cpus() -> Vec<usize> {
    let mut allowed = Vec::new();
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

pub fn execute(argv: &[String], timeout_secs: Option<u64>) -> u8 {
    let root = match state::harness_root() {
        Ok(root) => root,
        Err(message) => {
            eprintln!("{message}");
            return 2;
        }
    };
    if argv.is_empty() {
        eprintln!("fwtest run needs a command");
        return 2;
    }
    let _held = match queue::lock(&root) {
        Ok(held) => held,
        Err(error) => {
            eprintln!("could not take the job lock: {error}");
            return 1;
        }
    };
    if let Err(error) = queue::wait_for_other_suites() {
        if queue::is_wait_timeout(&error) {
            return 75;
        }
        eprintln!("could not see whether another suite is running: {error}");
        return 1;
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
            return 1;
        }
        Err(error) => {
            eprintln!("clean failed: {error}");
            return 1;
        }
    }
    match supervise(&root, argv, timeout_secs) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("run failed: {error}");
            1
        }
    }
}

fn supervise(root: &Path, argv: &[String], timeout_secs: Option<u64>) -> io::Result<u8> {
    INTERRUPTED.store(0, Ordering::SeqCst);
    install_stop_signals()?;
    become_subreaper()?;
    let cpus = half_cpus();
    let before = child_pids(std::process::id() as i32);
    let id = job_id(std::process::id());
    let scope = format!("fwtest-{id}.scope");
    let (mut child, scope) = spawn_job(argv, &cpus, &scope)?;
    let owner = identity::read_identity(std::process::id() as i32)?
        .ok_or_else(|| io::Error::other("cannot read fwtest's own process identity"))?;
    let mut job = JobRecord {
        id: id.clone(),
        checkout: std::env::current_dir().unwrap_or_else(|_| PathBuf::from("/")),
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
    let log = open_log(root, &id)?;
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let log_out = log.try_clone()?;
    let log_err = log.try_clone()?;
    let pump_out = std::thread::spawn(move || {
        if let Some(pipe) = stdout {
            let _ = pump(pipe, io::stdout(), log_out);
        }
    });
    let pump_err = std::thread::spawn(move || {
        if let Some(pipe) = stderr {
            let _ = pump(pipe, io::stderr(), log_err);
        }
    });
    let started = Instant::now();
    let timeout = timeout_secs.map(Duration::from_secs);
    let child_pid = child.id() as i32;
    let exit_code = loop {
        job.processes = snapshot(&before, child_pid, job.scope.as_deref());
        job::save_job(root, &job)?;
        if let Some(signal) = taken_interrupt() {
            let survived = stop_job(&job)?;
            break if survived.is_empty() {
                128u8.saturating_add(signal as u8)
            } else {
                1
            };
        }
        if timeout.is_some_and(|limit| started.elapsed() >= limit) {
            let _ = stop_job(&job)?;
            eprintln!("timed out");
            break 124;
        }
        if let Some(status) = child.try_wait()? {
            job.processes = snapshot(&before, child_pid, job.scope.as_deref());
            job::save_job(root, &job)?;
            let _ = stop_job(&job)?;
            break status.code().unwrap_or(1) as u8;
        }
        std::thread::sleep(Duration::from_millis(50));
    };
    drop(child);
    let _ = pump_out.join();
    let _ = pump_err.join();
    let survived: Vec<(i32, u64)> = job
        .processes
        .iter()
        .filter_map(|process| {
            identity::is_live_match(process.pid, process.start_ticks)
                .ok()
                .unwrap_or(false)
                .then_some((process.pid, process.start_ticks))
        })
        .collect();
    if survived.is_empty()
        && let Ok(path) = job::job_path(root, &job.id)
    {
        let _ = fs::remove_file(path);
    }
    Ok(exit_code)
}

fn spawn_job(argv: &[String], cpus: &[usize], scope: &str) -> io::Result<(Child, Option<String>)> {
    if systemd_user_works() {
        match spawn_systemd(argv, scope, cpus) {
            Ok(child) => return Ok((child, Some(scope.to_string()))),
            Err(error) => eprintln!("systemd-run unavailable ({error}); containing without it"),
        }
    }
    Ok((spawn_direct(argv, cpus)?, None))
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

fn spawn_systemd(argv: &[String], scope: &str, cpus: &[usize]) -> io::Result<Child> {
    let quota = format!("{}00%", cpus.len());
    let memory = format!("{}", half_ram_bytes());
    let affinity = cpu_list(cpus);
    let mut command = Command::new("systemd-run");
    command
        .args([
            "--user",
            "--scope",
            "--collect",
            &format!("--unit={scope}"),
            "--quiet",
            "--property=Nice=19",
            "--property=IOSchedulingClass=idle",
            &format!("--property=CPUQuota={quota}"),
            &format!("--property=MemoryMax={memory}"),
            &format!("--property=CPUAffinity={affinity}"),
            "--",
        ])
        .args(argv)
        .stdin(Stdio::inherit())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    command.spawn()
}

fn spawn_direct(argv: &[String], cpus: &[usize]) -> io::Result<Child> {
    let cpus = cpus.to_vec();
    let mut command = Command::new(&argv[0]);
    command
        .args(&argv[1..])
        .stdin(Stdio::inherit())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    unsafe {
        command.pre_exec(move || apply_limits(&cpus));
    }
    let child = command.spawn()?;
    unsafe {
        nix::libc::setpgid(child.id() as i32, child.id() as i32);
    }
    Ok(child)
}

fn apply_limits(cpus: &[usize]) -> io::Result<()> {
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
    let rc = unsafe { nix::libc::prctl(nix::libc::PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) };
    if rc == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}

fn install_stop_signals() -> io::Result<()> {
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

fn snapshot(before: &HashSet<i32>, child_pid: i32, scope: Option<&str>) -> Vec<ProcRef> {
    let mut pids = HashSet::new();
    if let Some(identity) = identity::read_identity(child_pid).ok().flatten() {
        collect_descendants(identity.pid, &mut pids);
        collect_group(identity.pgrp, &mut pids);
    }
    for pid in child_pids(std::process::id() as i32) {
        if !before.contains(&pid) {
            pids.insert(pid);
            collect_descendants(pid, &mut pids);
        }
    }
    if let Some(scope) = scope {
        pids.extend(scope_pids(scope));
    }
    pids.into_iter()
        .filter_map(|pid| identity::read_identity(pid).ok().flatten())
        .map(proc_ref)
        .collect()
}

fn collect_descendants(pid: i32, into: &mut HashSet<i32>) {
    if !into.insert(pid) {
        return;
    }
    for child in child_pids(pid) {
        collect_descendants(child, into);
    }
}

fn collect_group(pgrp: i32, into: &mut HashSet<i32>) {
    let Ok(entries) = fs::read_dir("/proc") else {
        return;
    };
    for entry in entries.flatten() {
        let Ok(pid) = entry.file_name().to_string_lossy().parse::<i32>() else {
            continue;
        };
        if let Some(identity) = identity::read_identity(pid).ok().flatten()
            && identity.pgrp == pgrp
        {
            into.insert(pid);
        }
    }
}

fn child_pids(pid: i32) -> HashSet<i32> {
    let mut found = HashSet::new();
    let task = PathBuf::from(format!("/proc/{pid}/task"));
    if let Ok(entries) = fs::read_dir(task) {
        for entry in entries.flatten() {
            let children = entry.path().join("children");
            if let Ok(text) = fs::read_to_string(children) {
                for token in text.split_whitespace() {
                    if let Ok(child) = token.parse() {
                        found.insert(child);
                    }
                }
            }
        }
    }
    if let Ok(entries) = fs::read_dir("/proc") {
        for entry in entries.flatten() {
            let Ok(candidate) = entry.file_name().to_string_lossy().parse::<i32>() else {
                continue;
            };
            if identity::read_identity(candidate)
                .ok()
                .flatten()
                .is_some_and(|identity| identity.ppid == pid)
            {
                found.insert(candidate);
            }
        }
    }
    found
}

fn scope_pids(scope: &str) -> Vec<i32> {
    let output = Command::new("systemctl")
        .args(["--user", "show", "-p", "ControlGroup", "--value", scope])
        .output();
    let Ok(output) = output else {
        return Vec::new();
    };
    let group = String::from_utf8_lossy(&output.stdout);
    let group = group.trim().trim_start_matches('/');
    if group.is_empty() {
        return Vec::new();
    }
    let path = Path::new("/sys/fs/cgroup").join(group).join("cgroup.procs");
    fs::read_to_string(path)
        .unwrap_or_default()
        .split_whitespace()
        .filter_map(|token| token.parse().ok())
        .collect()
}

fn stop_job(job: &JobRecord) -> io::Result<Vec<i32>> {
    if let Some(scope) = &job.scope {
        let _ = Command::new("systemctl")
            .args(["--user", "stop", scope])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    let targets: Vec<(i32, u64)> = job
        .processes
        .iter()
        .map(|process| (process.pid, process.start_ticks))
        .collect();
    identity::stop_all(&targets)
}

fn proc_ref(identity: ProcIdentity) -> ProcRef {
    ProcRef {
        pid: identity.pid,
        start_ticks: identity.start_ticks,
        comm: identity.comm,
    }
}

fn open_log(root: &Path, id: &str) -> io::Result<File> {
    let dir = root.join("logs");
    fs::create_dir_all(&dir)?;
    File::create(dir.join(format!("{id}.log")))
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

fn cpu_list(cpus: &[usize]) -> String {
    cpus.iter()
        .map(|cpu| cpu.to_string())
        .collect::<Vec<_>>()
        .join(",")
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
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or(0);
    let mut tm = unsafe { std::mem::zeroed::<nix::libc::tm>() };
    unsafe {
        nix::libc::gmtime_r(&secs, &mut tm);
    }
    format!(
        "{:04}{:02}{:02}-{:02}{:02}{:02}-{pid}",
        tm.tm_year + 1900,
        tm.tm_mon + 1,
        tm.tm_mday,
        tm.tm_hour,
        tm.tm_min,
        tm.tm_sec
    )
}

fn utc_now() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or(0);
    let mut tm = unsafe { std::mem::zeroed::<nix::libc::tm>() };
    unsafe {
        nix::libc::gmtime_r(&secs, &mut tm);
    }
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
