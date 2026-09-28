//! `fwtest rig` runs the rig driver as one job, then stops the hidden session,
//! then stops anything still left. `FLEXWEEK_RIG_KEEP` is never passed through.

use std::path::{Path, PathBuf};
use std::process::Command;

use crate::contain;

pub fn run(extra: &[String], python: Option<&Path>) -> u8 {
    let checkout = match git_toplevel() {
        Ok(path) => path,
        Err(message) => {
            eprintln!("{message}");
            return 2;
        }
    };
    let python = match resolve_python(python, &checkout) {
        Ok(path) => path,
        Err(message) => {
            eprintln!("{message}");
            return 2;
        }
    };
    let drive = checkout.join("scripts/rig/drive.py");
    let hidden = checkout.join("scripts/rig/hidden_session.py");
    if !drive.is_file() || !hidden.is_file() {
        eprintln!("Missing {} or {}.", drive.display(), hidden.display());
        return 2;
    }
    let session = match contain::session() {
        Ok(session) => session,
        Err(code) => return code,
    };
    // Safe: this runs before the job thread. The child must not see the keep flag.
    unsafe {
        std::env::remove_var("FLEXWEEK_RIG_KEEP");
    }
    let mut drive_cmd = vec![
        python.to_string_lossy().into_owned(),
        drive.to_string_lossy().into_owned(),
    ];
    drive_cmd.extend(extra.iter().cloned());
    let drive_code = match session.run(&drive_cmd, None) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("rig driver failed: {error}");
            return 1;
        }
    };
    let stop_cmd = vec![
        python.to_string_lossy().into_owned(),
        hidden.to_string_lossy().into_owned(),
        "stop".to_string(),
    ];
    let stop_code = match session.run(&stop_cmd, None) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("hidden session stop failed: {error}");
            return 1;
        }
    };
    if drive_code != 0 {
        return drive_code;
    }
    if stop_code != 0 {
        return stop_code;
    }
    0
}

fn git_toplevel() -> Result<PathBuf, String> {
    let output = Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .output()
        .map_err(|error| format!("git rev-parse failed: {error}"))?;
    if !output.status.success() {
        return Err("fwtest rig must be run inside a git checkout".to_string());
    }
    let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if path.is_empty() {
        return Err("fwtest rig must be run inside a git checkout".to_string());
    }
    Ok(PathBuf::from(path))
}

fn resolve_python(explicit: Option<&Path>, checkout: &Path) -> Result<PathBuf, String> {
    if let Some(path) = explicit {
        return Ok(path.to_path_buf());
    }
    if let Some(path) = std::env::var_os("FWTEST_PYTHON").filter(|value| !value.is_empty()) {
        return Ok(PathBuf::from(path));
    }
    let venv = checkout.join(".venv/bin/python");
    if venv.is_file() {
        return Ok(venv);
    }
    Err(format!(
        "No project Python. Pass --python, set FWTEST_PYTHON, or create {}.",
        venv.display()
    ))
}
