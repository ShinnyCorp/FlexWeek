//! `fwtest rig` runs the rig driver as one job, then stops the hidden session,
//! then stops anything still left. `FLEXWEEK_RIG_KEEP` is never passed through.

use std::path::Path;

use crate::contain;

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
    let hidden = checkout.join("scripts/rig/hidden_session.py");
    if !drive.is_file() || !hidden.is_file() {
        eprintln!("Missing {} or {}.", drive.display(), hidden.display());
        return 2;
    }
    let session = match contain::session() {
        Ok(session) => session,
        Err(code) => return code,
    };
    // SAFETY: this runs on the main thread before the job starts. The child must
    // not see the keep flag.
    unsafe {
        std::env::remove_var("FLEXWEEK_RIG_KEEP");
    }
    let mut drive_cmd = vec![
        python.to_string_lossy().into_owned(),
        drive.to_string_lossy().into_owned(),
    ];
    drive_cmd.extend(extra.iter().cloned());
    let drive_code = match session.run_in(&drive_cmd, None, &checkout) {
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
    let stop_code = match session.run_in(&stop_cmd, None, &checkout) {
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
