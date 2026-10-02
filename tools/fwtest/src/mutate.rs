//! Run mutation specs one case at a time. The source file is restored however the case ends.
//! A case whose file is under `engine/` rebuilds the engine module before its test. The spec
//! ends with one more rebuild from the restored tree, so the checkout's module is clean.

use std::fs;
use std::path::{Path, PathBuf};
use std::time::Instant;

use serde::Deserialize;

use crate::contain::{self, Session};
use crate::edits::{self, Guard};
use crate::rebuild::{self, EngineBuild};

#[derive(Debug, Deserialize)]
struct Case {
    name: String,
    file: String,
    old: String,
    new: String,
    test: String,
    /// `"build"` means a failed engine rebuild is the catch. Anything else is refused.
    #[serde(default)]
    expect: String,
    /// Extra cargo features for the mutated build only, for example `["audit"]`.
    #[serde(default)]
    features: Vec<String>,
}

struct Job<'a> {
    session: &'a Session,
    checkout: &'a Path,
    python: &'a Path,
    root: &'a Path,
    build: &'a EngineBuild,
}

pub fn run(
    specs: &[PathBuf],
    case_name: Option<&str>,
    python: Option<&Path>,
    engine_build: Option<&str>,
    no_engine_rebuild: bool,
) -> u8 {
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
    let build = match rebuild::resolve(&checkout, engine_build, no_engine_rebuild) {
        Ok(build) => build,
        Err(message) => {
            eprintln!("{message}");
            return 2;
        }
    };
    let session = match contain::session() {
        Ok(session) => session,
        Err(code) => return code,
    };
    let root = match crate::state::harness_root() {
        Ok(path) => path,
        Err(message) => {
            eprintln!("{message}");
            return 2;
        }
    };
    let files = match spec_files(&checkout, specs) {
        Ok(files) => files,
        Err(message) => {
            eprintln!("{message}");
            return 1;
        }
    };
    // SAFETY: this runs on the main thread before any job thread starts. Children inherit the vars.
    unsafe {
        std::env::set_var("PYTHONDONTWRITEBYTECODE", "1");
        std::env::set_var("QT_QPA_PLATFORM", "offscreen");
    }
    let job = Job {
        session: &session,
        checkout: &checkout,
        python: &python,
        root: &root,
        build: &build,
    };
    let mut missed = 0u32;
    let mut saw_case = false;
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
                return finish(&job, 1);
            }
        };
        let cases: Vec<Case> = match serde_json::from_str(&text) {
            Ok(cases) => cases,
            Err(error) => {
                eprintln!("FAILED: {}: {error}", spec.display());
                return finish(&job, 1);
            }
        };
        for case in cases {
            if case_name.is_some_and(|wanted| wanted != case.name) {
                continue;
            }
            saw_case = true;
            if !is_engine_source(&case.file)
                && let Some(code) = settle_or_stop(&job)
            {
                return code;
            }
            match run_case(&job, &stem, &case) {
                CaseEnd::Interrupted(code) => return stop_for(&job, code),
                CaseEnd::Done(outcome) => {
                    println!(
                        "{:5} {:10} {:56} {}",
                        outcome.label, stem, case.name, outcome.detail
                    );
                    if outcome.label != "RED" {
                        missed += 1;
                    }
                }
            }
        }
        if let Some(code) = settle_or_stop(&job) {
            return code;
        }
    }
    if let Some(name) = case_name
        && !saw_case
    {
        eprintln!("no case named {name}");
        return 2;
    }
    if missed == 0 {
        println!("every mutation was caught");
        0
    } else {
        println!("{missed} mutation(s) SURVIVED");
        1
    }
}

/// Cases whose `old` text does not occur exactly once. Empty when the specs are whole.
pub fn pattern_misses(checkout: &Path) -> Result<Vec<String>, String> {
    let mut misses = Vec::new();
    for spec in spec_files(checkout, &[])? {
        let text =
            fs::read_to_string(&spec).map_err(|error| format!("{}: {error}", spec.display()))?;
        let cases: Vec<Case> =
            serde_json::from_str(&text).map_err(|error| format!("{}: {error}", spec.display()))?;
        let stem = spec
            .file_stem()
            .and_then(|stem| stem.to_str())
            .unwrap_or("spec");
        for case in cases {
            let source = checkout.join(&case.file);
            let body = fs::read_to_string(&source).unwrap_or_default();
            let found = if source.is_file() {
                body.matches(&case.old).count()
            } else {
                0
            };
            if found != 1 {
                misses.push(format!(
                    "{stem}: {} pattern found {found} times in {}",
                    case.name, case.file
                ));
            }
        }
    }
    Ok(misses)
}

fn finish(job: &Job<'_>, code: u8) -> u8 {
    if let Some(stop) = settle_or_stop(job) {
        return stop;
    }
    code
}

fn settle_or_stop(job: &Job<'_>) -> Option<u8> {
    match settle(job) {
        Settle::Done => None,
        Settle::Interrupted(code) => {
            eprintln!("interrupted during engine rebuild");
            Some(code)
        }
        Settle::Failed(message) => {
            eprintln!("{message}");
            Some(1)
        }
    }
}

fn stop_for(job: &Job<'_>, code: u8) -> u8 {
    eprintln!("interrupted");
    match settle(job) {
        Settle::Failed(message) => eprintln!("{message}"),
        Settle::Interrupted(again) => eprintln!("interrupted during engine rebuild ({again})"),
        Settle::Done => {}
    }
    code
}

enum Settle {
    Done,
    Interrupted(u8),
    Failed(String),
}

fn settle(job: &Job<'_>) -> Settle {
    let mark = match edits::engine_rebuild(job.root) {
        Ok(Some(mark)) => mark,
        Ok(None) => return Settle::Done,
        Err(error) => return Settle::Failed(error.to_string()),
    };
    let started = Instant::now();
    let ran = match job.session.run_logged_in(
        &mark.command,
        Some(rebuild::build_timeout()),
        &mark.checkout,
    ) {
        Ok(ran) => ran,
        Err(error) => return Settle::Failed(format!("did not build: {error}")),
    };
    if ran.code >= 128 {
        return Settle::Interrupted(ran.code);
    }
    if ran.code != 0 {
        return Settle::Failed(format!(
            "clean engine rebuild failed ({})",
            build_failure_line(&ran.log)
        ));
    }
    if let Err(error) = edits::clear_engine_rebuild(job.root) {
        return Settle::Failed(error.to_string());
    }
    eprintln!(
        "rebuilt clean engine module in {:.1}s",
        started.elapsed().as_secs_f64()
    );
    Settle::Done
}

struct Outcome {
    label: &'static str,
    detail: String,
}

enum CaseEnd {
    Done(Outcome),
    Interrupted(u8),
}

fn run_case(job: &Job<'_>, stem: &str, case: &Case) -> CaseEnd {
    if let Some(detail) = reject_expect(case) {
        return done("PATTERN", detail);
    }
    let source = job.checkout.join(&case.file);
    let text = match fs::read_to_string(&source) {
        Ok(text) => text,
        Err(error) => {
            return done("PATTERN", format!("could not read {}: {error}", case.file));
        }
    };
    let found = text.matches(&case.old).count();
    if found != 1 {
        return done(
            "PATTERN",
            format!("pattern found {found} times in {}", case.file),
        );
    }
    let guard = match Guard::arm(job.root, &source, &format!("{stem}/{}", case.name)) {
        Ok(guard) => guard,
        Err(error) => {
            return done("GREEN", format!("could not save a backup: {error}"));
        }
    };
    let edited = text.replacen(&case.old, &case.new, 1);
    if fs::write(&source, &edited).is_err() {
        return done("GREEN", format!("could not edit {}", case.file));
    }
    edits::delete_bytecode(&source);
    let note = if is_engine_source(&case.file) {
        if job.build.enabled {
            match rebuild_mutated(job, case) {
                Rebuild::Interrupted(code) => return CaseEnd::Interrupted(code),
                Rebuild::Blocked(detail) => {
                    drop(guard);
                    return done("GREEN", detail);
                }
                Rebuild::Failed(detail) => {
                    drop(guard);
                    let label = if case.expect == "build" {
                        "RED"
                    } else {
                        "BUILD"
                    };
                    return done(label, detail);
                }
                Rebuild::Built(seconds) => format!("built in {seconds:.1}s"),
            }
        } else {
            "rebuild skipped".to_string()
        }
    } else {
        String::new()
    };
    let command = vec![
        job.python.to_string_lossy().into_owned(),
        "-m".into(),
        "pytest".into(),
        case.test.clone(),
        "-q".into(),
        "-x".into(),
        "-p".into(),
        "no:cacheprovider".into(),
    ];
    let ran = match job.session.run_logged_in(&command, None, job.checkout) {
        Ok(ran) => ran,
        Err(error) => {
            drop(guard);
            return done("GREEN", error.to_string());
        }
    };
    if ran.code >= 128 {
        drop(guard);
        return CaseEnd::Interrupted(ran.code);
    }
    let failing = if ran.code == 0 {
        String::new()
    } else {
        failing_line(&ran.log)
    };
    drop(guard);
    let detail = join_detail(&failing, &note);
    if ran.code == 0 {
        done("GREEN", detail)
    } else {
        done("RED", detail)
    }
}

fn reject_expect(case: &Case) -> Option<String> {
    if case.expect.is_empty() {
        return None;
    }
    if case.expect != "build" {
        return Some(format!("unknown expect {}", case.expect));
    }
    if !is_engine_source(&case.file) {
        return Some("expect build is only for a file under engine/".to_string());
    }
    None
}

enum Rebuild {
    Built(f64),
    Failed(String),
    Blocked(String),
    Interrupted(u8),
}

fn rebuild_mutated(job: &Job<'_>, case: &Case) -> Rebuild {
    if let Err(error) = edits::mark_engine_rebuild(job.root, job.checkout, &job.build.command) {
        return Rebuild::Blocked(format!("could not record the engine rebuild: {error}"));
    }
    let command = rebuild::with_features(&job.build.command, &case.features);
    let started = Instant::now();
    let ran =
        match job
            .session
            .run_logged_in(&command, Some(rebuild::build_timeout()), job.checkout)
        {
            Ok(ran) => ran,
            Err(error) => return Rebuild::Failed(format!("did not build: {error}")),
        };
    if ran.code >= 128 {
        return Rebuild::Interrupted(ran.code);
    }
    if ran.code != 0 {
        return Rebuild::Failed(build_failure_line(&ran.log));
    }
    Rebuild::Built(started.elapsed().as_secs_f64())
}

fn done(label: &'static str, detail: String) -> CaseEnd {
    CaseEnd::Done(Outcome { label, detail })
}

fn join_detail(failing: &str, note: &str) -> String {
    match (failing.is_empty(), note.is_empty()) {
        (true, true) => String::new(),
        (false, true) => failing.to_string(),
        (true, false) => note.to_string(),
        (false, false) => format!("{failing} {note}"),
    }
}

fn is_engine_source(file: &str) -> bool {
    Path::new(file)
        .components()
        .next()
        .is_some_and(|component| component.as_os_str() == "engine")
}

fn failing_line(log: &Path) -> String {
    let Ok(text) = fs::read_to_string(log) else {
        return String::new();
    };
    text.lines()
        .find(|line| line.starts_with("E "))
        .map(|line| line.trim().chars().take(110).collect())
        .unwrap_or_default()
}

fn build_failure_line(log: &Path) -> String {
    let Ok(text) = fs::read_to_string(log) else {
        return "did not build".to_string();
    };
    let line = text.lines().rev().find(|line| {
        let lower = line.to_ascii_lowercase();
        !line.trim().is_empty() && (lower.contains("error") || lower.contains("failed"))
    });
    match line {
        Some(line) => {
            let clipped: String = line.trim().chars().take(90).collect();
            format!("did not build: {clipped}")
        }
        None => "did not build".to_string(),
    }
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn engine_paths_are_the_engine_tree_only() {
        assert!(is_engine_source("engine/engine/src/solver.rs"));
        assert!(is_engine_source("engine/py/src/lib.rs"));
        assert!(!is_engine_source("desktop/native/look.py"));
        assert!(!is_engine_source("backend/solver.py"));
        assert!(!is_engine_source("engines/nope.rs"));
    }
}
