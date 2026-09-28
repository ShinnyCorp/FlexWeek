//! Run mutation specs one case at a time. The source file is restored however the case ends.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use serde::Deserialize;

use crate::contain::{self, Session};
use crate::edits::{self, Guard};

#[derive(Debug, Deserialize)]
struct Case {
    name: String,
    file: String,
    old: String,
    new: String,
    test: String,
}

pub fn run(specs: &[PathBuf], case_name: Option<&str>, python: Option<&Path>) -> u8 {
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
    let session = match contain::session() {
        Ok(session) => session,
        Err(code) => return code,
    };
    let files = match spec_files(&checkout, specs) {
        Ok(files) => files,
        Err(message) => {
            eprintln!("{message}");
            return 1;
        }
    };
    // Safe: this runs before any job thread, and the vars are only read by children.
    unsafe {
        std::env::set_var("PYTHONDONTWRITEBYTECODE", "1");
        std::env::set_var("QT_QPA_PLATFORM", "offscreen");
    }
    let mut missed = 0u32;
    for spec in files {
        let stem = spec
            .file_stem()
            .and_then(|stem| stem.to_str())
            .unwrap_or("spec")
            .to_string();
        let text = match fs::read_to_string(&spec) {
            Ok(text) => text,
            Err(error) => {
                eprintln!("FAILED: {}: {error}", spec.display());
                return 1;
            }
        };
        let cases: Vec<Case> = match serde_json::from_str(&text) {
            Ok(cases) => cases,
            Err(error) => {
                eprintln!("FAILED: {}: {error}", spec.display());
                return 1;
            }
        };
        for case in cases {
            if case_name.is_some_and(|wanted| wanted != case.name) {
                continue;
            }
            let outcome = run_case(&session, &checkout, &python, &stem, &case);
            println!(
                "{:7} {:10} {:56} {}",
                outcome.label, stem, case.name, outcome.detail
            );
            if outcome.label != "RED" {
                missed += 1;
            }
        }
    }
    if missed == 0 {
        println!("every mutation was caught");
        0
    } else {
        println!("{missed} mutation(s) SURVIVED");
        1
    }
}

struct Outcome {
    label: &'static str,
    detail: String,
}

fn run_case(session: &Session, checkout: &Path, python: &Path, stem: &str, case: &Case) -> Outcome {
    let source = checkout.join(&case.file);
    let text = match fs::read_to_string(&source) {
        Ok(text) => text,
        Err(error) => {
            return Outcome {
                label: "PATTERN",
                detail: format!("could not read {}: {error}", case.file),
            };
        }
    };
    let found = text.matches(&case.old).count();
    if found != 1 {
        return Outcome {
            label: "PATTERN",
            detail: format!("pattern found {found} times in {}", case.file),
        };
    }
    let state = match crate::state::harness_root() {
        Ok(path) => path,
        Err(error) => {
            return Outcome {
                label: "GREEN",
                detail: error,
            };
        }
    };
    let guard = match Guard::arm(&state, &source, &format!("{stem}/{}", case.name)) {
        Ok(guard) => guard,
        Err(error) => {
            return Outcome {
                label: "GREEN",
                detail: format!("could not save a backup: {error}"),
            };
        }
    };
    let edited = text.replacen(&case.old, &case.new, 1);
    if fs::write(&source, &edited).is_err() {
        return Outcome {
            label: "GREEN",
            detail: format!("could not edit {}", case.file),
        };
    }
    edits::delete_bytecode(&source);
    let command = vec![
        python.to_string_lossy().into_owned(),
        "-m".into(),
        "pytest".into(),
        case.test.clone(),
        "-q".into(),
        "-x".into(),
        "-p".into(),
        "no:cacheprovider".into(),
    ];
    let code = match session.run(&command, None) {
        Ok(code) => code,
        Err(error) => {
            drop(guard);
            return Outcome {
                label: "GREEN",
                detail: error.to_string(),
            };
        }
    };
    let detail = if code == 0 {
        String::new()
    } else {
        failing_line()
    };
    drop(guard);
    if code == 0 {
        Outcome {
            label: "GREEN",
            detail,
        }
    } else {
        Outcome {
            label: "RED",
            detail,
        }
    }
}

fn failing_line() -> String {
    let Ok(root) = crate::state::harness_root() else {
        return String::new();
    };
    let Ok(entries) = fs::read_dir(root.join("logs")) else {
        return String::new();
    };
    let mut newest: Option<(std::time::SystemTime, PathBuf)> = None;
    for entry in entries.flatten() {
        let Ok(modified) = entry.metadata().and_then(|meta| meta.modified()) else {
            continue;
        };
        let replace = match &newest {
            None => true,
            Some((time, _)) => modified >= *time,
        };
        if replace {
            newest = Some((modified, entry.path()));
        }
    }
    let Some((_, path)) = newest else {
        return String::new();
    };
    let Ok(text) = fs::read_to_string(path) else {
        return String::new();
    };
    text.lines()
        .find(|line| line.starts_with("E "))
        .map(|line| {
            let line = line.trim();
            if line.len() > 110 {
                line[..110].to_string()
            } else {
                line.to_string()
            }
        })
        .unwrap_or_default()
}

fn spec_files(checkout: &Path, specs: &[PathBuf]) -> Result<Vec<PathBuf>, String> {
    if !specs.is_empty() {
        return Ok(specs.to_vec());
    }
    let dir = checkout.join("scripts/mutations");
    let mut files = Vec::new();
    let entries = fs::read_dir(&dir).map_err(|error| format!("{}: {error}", dir.display()))?;
    for entry in entries {
        let path = entry.map_err(|error| error.to_string())?.path();
        if path.extension().and_then(|ext| ext.to_str()) == Some("json") {
            files.push(path);
        }
    }
    files.sort();
    if files.is_empty() {
        return Err(format!("no mutation specs in {}", dir.display()));
    }
    Ok(files)
}

fn git_toplevel() -> Result<PathBuf, String> {
    let output = Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .output()
        .map_err(|error| format!("git rev-parse failed: {error}"))?;
    if !output.status.success() {
        return Err("fwtest mutate must be run inside a git checkout".to_string());
    }
    let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if path.is_empty() {
        return Err("fwtest mutate must be run inside a git checkout".to_string());
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
