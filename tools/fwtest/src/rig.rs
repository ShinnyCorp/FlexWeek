//! `fwtest rig` runs the rig driver inside one contained job. That job starts
//! the hidden session, so the session shares the job's scope and limits and
//! the stop handlers are already installed. The session is always stopped
//! afterwards. `FLEXWEEK_RIG_KEEP` is removed before the driver starts, and a
//! value there cannot keep the session.

use std::path::Path;

use crate::contain;
use crate::hidden;

pub fn run(extra: &[String], python: Option<&Path>) -> u8 {
    let checkout = match crate::state::git_toplevel() {
        Ok(path) => path,
        Err(message) => {
            eprintln!("{message}");
            return 2;
        }
    };
    let python = match crate::state::resolve_python(python, &checkout) {
        Ok(path) => path,
        Err(message) => {
            eprintln!("{message}");
            return 2;
        }
    };
    let drive = checkout.join("scripts/rig/drive.py");
    if !drive.is_file() {
        eprintln!("Missing {}.", drive.display());
        return 2;
    }
    let (server, drive_args) = match split_server(extra) {
        Ok(split) => split,
        Err(message) => {
            eprintln!("{message}");
            return 2;
        }
    };
    let session = match contain::session() {
        Ok(session) => session,
        Err(code) => return code,
    };
    // SAFETY: this thread clears the variable before any job starts, and the
    // process is single-threaded here. The driver must not see a keep request.
    unsafe {
        std::env::remove_var("FLEXWEEK_RIG_KEEP");
    }
    if lists_only(&drive_args) {
        let mut drive_cmd = vec![
            python.to_string_lossy().into_owned(),
            drive.to_string_lossy().into_owned(),
        ];
        drive_cmd.extend(drive_args);
        return match session.run_in(&drive_cmd, None, &checkout) {
            Ok(code) => code,
            Err(error) => {
                eprintln!("rig driver failed: {error}");
                1
            }
        };
    }
    let exe = match std::env::current_exe() {
        Ok(path) => path,
        Err(error) => {
            eprintln!("could not find fwtest: {error}");
            return 1;
        }
    };
    // The child starts the session inside the job. It must not take the lock
    // this process already holds.
    let mut drive_cmd = vec![
        exe.to_string_lossy().into_owned(),
        "--inside-rig".to_string(),
        "--server".to_string(),
        server,
        python.to_string_lossy().into_owned(),
        drive.to_string_lossy().into_owned(),
    ];
    drive_cmd.extend(drive_args);
    let drive_result = session.run_in(&drive_cmd, None, &checkout);
    let keep = std::env::var("FLEXWEEK_RIG_KEEP").ok();
    let stop_result = if stops_when(keep.as_deref()) {
        hidden::stop(&checkout)
    } else {
        Ok(())
    };
    let drive_code = match drive_result {
        Ok(code) => code,
        Err(error) => {
            eprintln!("rig driver failed: {error}");
            if let Err(message) = stop_result {
                eprintln!("hidden session stop failed: {message}");
            }
            return 1;
        }
    };
    if let Err(message) = stop_result {
        eprintln!("hidden session stop failed: {message}");
        if drive_code != 0 {
            return drive_code;
        }
        return 1;
    }
    drive_code
}

/// `--server` belongs to the hidden session. The rest is forwarded to drive.py.
fn split_server(args: &[String]) -> Result<(String, Vec<String>), String> {
    let mut server = "auto".to_string();
    let mut rest = Vec::new();
    let mut args = args.iter();
    while let Some(arg) = args.next() {
        if arg == "--server" {
            let Some(value) = args.next() else {
                return Err("fwtest rig --server needs kwin, xvfb, or auto".to_string());
            };
            server = value.clone();
        } else if let Some(value) = arg.strip_prefix("--server=") {
            if value.is_empty() {
                return Err("fwtest rig --server needs kwin, xvfb, or auto".to_string());
            }
            server = value.to_string();
        } else {
            rest.push(arg.clone());
        }
    }
    if !matches!(server.as_str(), "auto" | "kwin" | "xvfb") {
        return Err(format!("Unknown server '{server}'"));
    }
    Ok((server, rest))
}

/// `--list` only prints the scenario names. It does not need a hidden session.
fn lists_only(args: &[String]) -> bool {
    args.iter().any(|arg| arg == "--list")
}

/// A rig run always stops the hidden session. `fwtest rig` removes
/// `FLEXWEEK_RIG_KEEP` before the driver, and the value is ignored here so a
/// leftover cannot keep the session.
pub fn stops_when(_keep: Option<&str>) -> bool {
    true
}

/// Start the hidden session and replace this process with the rig driver.
///
/// The parent has already installed the stop handlers and placed this process
/// in the job. This process must not take the job lock.
pub fn inside(args: &[String]) -> i32 {
    let mut args = args.iter();
    if args.next().map(String::as_str) != Some("--server") {
        eprintln!("fwtest --inside-rig needs --server");
        return 2;
    }
    let Some(server) = args.next() else {
        eprintln!("fwtest rig --server needs kwin, xvfb, or auto");
        return 2;
    };
    if !matches!(server.as_str(), "auto" | "kwin" | "xvfb") {
        eprintln!("Unknown server '{server}'");
        return 2;
    }
    let (Some(python), Some(drive)) = (args.next(), args.next()) else {
        eprintln!("fwtest --inside-rig needs the rig driver");
        return 2;
    };
    let rest: Vec<&String> = args.collect();
    let checkout = match crate::state::git_toplevel() {
        Ok(path) => path,
        Err(message) => {
            eprintln!("{message}");
            return 2;
        }
    };
    unsafe {
        std::env::remove_var("FLEXWEEK_RIG_KEEP");
    }
    let started = match hidden::start(&checkout, server) {
        Ok(started) => started,
        Err(message) => {
            eprintln!("{message}");
            return 1;
        }
    };
    // SAFETY: this process is single-threaded here. exec replaces it, so the
    // variables live only in the driver.
    unsafe {
        std::env::set_var("FLEXWEEK_RIG_DISPLAY", &started.display);
        std::env::set_var("FLEXWEEK_RIG_BUS", &started.bus);
        std::env::set_var("FLEXWEEK_RIG_RUNS_KEY", &started.runs_key);
    }
    let mut command = std::process::Command::new(python);
    command.arg(drive);
    for arg in rest {
        command.arg(arg);
    }
    let error = std::os::unix::process::CommandExt::exec(&mut command);
    eprintln!("could not run the rig driver: {error}");
    if let Err(message) = hidden::stop(&checkout) {
        eprintln!("hidden session stop failed: {message}");
    }
    1
}

#[cfg(test)]
mod tests {
    use super::{split_server, stops_when};

    #[test]
    fn a_rig_run_always_stops_its_hidden_desktop() {
        assert!(stops_when(None));
        assert!(stops_when(Some("")));
        assert!(stops_when(Some("1")));
        assert_eq!(split_server(&[]).unwrap().0, "auto");
    }

    #[test]
    fn server_flag_is_not_forwarded_to_the_driver() {
        let (server, rest) = split_server(&[
            "--server".to_string(),
            "xvfb".to_string(),
            "--design".to_string(),
            "classic".to_string(),
        ])
        .unwrap();
        assert_eq!(server, "xvfb");
        assert_eq!(rest, ["--design", "classic"]);
        let error = split_server(&["--server".to_string(), "weston".to_string()]).unwrap_err();
        assert_eq!(error, "Unknown server 'weston'");
    }
}
