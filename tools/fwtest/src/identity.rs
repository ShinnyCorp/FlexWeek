//! Process identity from `/proc/<pid>/stat`.
//!
//! `comm` is the only field that can contain spaces or parentheses. It sits
//! between the first `(` and the last `)`, and `starttime` is field 22 of the
//! whole record (the 20th token after that closing parenthesis).

use std::fs;
use std::io;
use std::time::Duration;

use nix::sys::signal::{Signal, kill};
use nix::unistd::Pid;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProcIdentity {
    pub pid: i32,
    pub comm: String,
    pub state: char,
    pub start_ticks: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StatParseError;

pub fn parse_stat(text: &str) -> Result<ProcIdentity, StatParseError> {
    let text = text.trim();
    let open = text.find('(').ok_or(StatParseError)?;
    let close = text.rfind(')').ok_or(StatParseError)?;
    if close < open {
        return Err(StatParseError);
    }
    let pid: i32 = text[..open].trim().parse().map_err(|_| StatParseError)?;
    if pid <= 0 {
        return Err(StatParseError);
    }
    let comm = text[open + 1..close].to_string();
    let rest: Vec<&str> = text[close + 1..].split_whitespace().collect();
    // state is the first token after comm. starttime is field 22, so index 19.
    let state = rest
        .first()
        .and_then(|token| token.chars().next())
        .ok_or(StatParseError)?;
    let start_ticks = rest
        .get(19)
        .ok_or(StatParseError)?
        .parse()
        .map_err(|_| StatParseError)?;
    Ok(ProcIdentity {
        pid,
        comm,
        state,
        start_ticks,
    })
}

pub fn read_identity(pid: i32) -> io::Result<Option<ProcIdentity>> {
    if pid <= 0 {
        return Ok(None);
    }
    match fs::read_to_string(format!("/proc/{pid}/stat")) {
        Ok(text) => match parse_stat(&text) {
            Ok(identity) if identity.pid == pid => Ok(Some(identity)),
            _ => Ok(None),
        },
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error),
    }
}

/// True only while this PID is still the same live process.
pub fn is_live_match(pid: i32, start_ticks: u64) -> io::Result<bool> {
    Ok(matches!(
        read_identity(pid)?,
        Some(found) if found.start_ticks == start_ticks && is_running_state(found.state)
    ))
}

fn is_running_state(state: char) -> bool {
    !matches!(state, 'Z' | 'X' | 'x')
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StopResult {
    Gone,
    NotOurs,
    Stopped,
    Survived,
}

/// Signal `pid` only when its start ticks still match. A reused PID is left alone.
pub fn stop_if_ours(pid: i32, start_ticks: u64) -> io::Result<StopResult> {
    if pid <= 1 || pid as u32 == std::process::id() {
        return Ok(StopResult::NotOurs);
    }
    if !is_live_match(pid, start_ticks)? {
        return Ok(if read_identity(pid)?.is_some() {
            StopResult::NotOurs
        } else {
            StopResult::Gone
        });
    }
    signal(pid, Signal::SIGTERM)?;
    if wait_until_gone(pid, start_ticks, Duration::from_secs(3))? {
        return Ok(StopResult::Stopped);
    }
    if is_live_match(pid, start_ticks)? {
        signal(pid, Signal::SIGKILL)?;
    }
    if wait_until_gone(pid, start_ticks, Duration::from_secs(3))? {
        Ok(StopResult::Stopped)
    } else if is_live_match(pid, start_ticks)? {
        Ok(StopResult::Survived)
    } else {
        Ok(StopResult::Stopped)
    }
}

fn signal(pid: i32, signal: Signal) -> io::Result<()> {
    match kill(Pid::from_raw(pid), signal) {
        Ok(()) => Ok(()),
        Err(nix::errno::Errno::ESRCH) => Ok(()),
        Err(error) => Err(io::Error::other(error)),
    }
}

fn wait_until_gone(pid: i32, start_ticks: u64, budget: Duration) -> io::Result<bool> {
    let started = std::time::Instant::now();
    loop {
        if !is_live_match(pid, start_ticks)? {
            return Ok(true);
        }
        if started.elapsed() >= budget {
            return Ok(false);
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}

#[cfg(test)]
mod tests {
    use super::parse_stat;

    #[test]
    fn comm_with_spaces_and_parentheses_does_not_shift_start_ticks() {
        let stat = "432 (worker (a) b) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 424242 20";
        let parsed = parse_stat(stat).unwrap();
        assert_eq!(parsed.pid, 432);
        assert_eq!(parsed.comm, "worker (a) b");
        assert_eq!(parsed.state, 'S');
        assert_eq!(parsed.start_ticks, 424242);
    }

    #[test]
    fn a_real_stat_line_parses_and_rereads_the_same_ticks() {
        let text = std::fs::read_to_string("/proc/self/stat").unwrap();
        let parsed = parse_stat(&text).unwrap();
        assert_eq!(parsed.pid, std::process::id() as i32);
        assert!(parsed.start_ticks > 0);
        let again = super::read_identity(parsed.pid).unwrap().unwrap();
        assert_eq!(again.start_ticks, parsed.start_ticks);
    }
}
