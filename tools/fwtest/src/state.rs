//! On-disk state lives in `~/.flexweek-ui-harness/fwtest/`, outside every checkout.

use std::path::{Path, PathBuf};
use std::process::Command;

pub fn harness_root() -> Result<PathBuf, String> {
    let home = std::env::var_os("HOME").filter(|value| !value.is_empty());
    let Some(home) = home else {
        return Err("HOME is not set, so fwtest has nowhere to keep job records".to_string());
    };
    Ok(PathBuf::from(home).join(".flexweek-ui-harness/fwtest"))
}

pub fn git_toplevel() -> Result<PathBuf, String> {
    let output = Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .output()
        .map_err(|error| format!("git rev-parse failed: {error}"))?;
    if !output.status.success() {
        return Err("fwtest must be run inside a git checkout".to_string());
    }
    let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if path.is_empty() {
        return Err("fwtest must be run inside a git checkout".to_string());
    }
    Ok(PathBuf::from(path))
}

pub fn resolve_python(explicit: Option<&Path>, checkout: &Path) -> Result<PathBuf, String> {
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
