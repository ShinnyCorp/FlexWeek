//! `fwtest rig` starts the hidden session, runs the rig driver as one job, then
//! stops that session by the PIDs it recorded. `FLEXWEEK_RIG_KEEP` is removed
//! before the driver starts, so a rig run always stops the session.

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
    // SAFETY: the main thread sets the driver's environment before the job
    // starts, and clears it again before stop. Nothing else reads these names.
    unsafe {
        std::env::remove_var("FLEXWEEK_RIG_KEEP");
    }
    let started = match hidden::start(&checkout, &server) {
        Ok(started) => started,
        Err(message) => {
            eprintln!("{message}");
            return 1;
        }
    };
    unsafe {
        std::env::set_var("FLEXWEEK_RIG_DISPLAY", &started.display);
        std::env::set_var("FLEXWEEK_RIG_BUS", &started.bus);
        std::env::set_var("FLEXWEEK_RIG_RUNS_KEY", &started.runs_key);
    }
    let mut drive_cmd = vec![
        python.to_string_lossy().into_owned(),
        drive.to_string_lossy().into_owned(),
    ];
    drive_cmd.extend(drive_args);
    let drive_result = session.run_in(&drive_cmd, None, &checkout);
    unsafe {
        std::env::remove_var("FLEXWEEK_RIG_DISPLAY");
        std::env::remove_var("FLEXWEEK_RIG_BUS");
        std::env::remove_var("FLEXWEEK_RIG_RUNS_KEY");
    }
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

/// Empty or absent `FLEXWEEK_RIG_KEEP` stops the session. Any other value keeps it.
pub fn stops_when(keep: Option<&str>) -> bool {
    match keep {
        None | Some("") => true,
        Some(_) => false,
    }
}

#[cfg(test)]
mod tests {
    use super::{split_server, stops_when};

    #[test]
    fn a_rig_run_stops_its_hidden_desktop_unless_asked_to_keep_it() {
        let steps = |keep| {
            let mut steps = vec!["start:auto"];
            if stops_when(keep) {
                steps.push("stop");
            }
            steps
        };
        assert_eq!(steps(None), ["start:auto", "stop"]);
        assert_eq!(steps(Some("")), ["start:auto", "stop"]);
        assert_eq!(steps(Some("1")), ["start:auto"]);
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
