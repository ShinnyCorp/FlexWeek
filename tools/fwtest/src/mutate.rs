//! Run mutation specs one case at a time. The source file is restored however the case ends.
//! A case whose file is under `engine/` rebuilds the engine module before its test. The spec
//! ends with one more rebuild from the restored tree, so the checkout's module is clean.

use std::cell::RefCell;
use std::collections::HashSet;
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
    /// Tests already run once without a mutation this run and seen green.
    passing: RefCell<HashSet<String>>,
}

pub fn run(
    specs: &[PathBuf],
    case_name: Option<&str>,
    python: Option<&Path>,
    engine_build: Option<&str>,
    no_engine_rebuild: bool,
    engine_only: bool,
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
    let mut build = match rebuild::resolve(&checkout, engine_build, no_engine_rebuild) {
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
    if build.match_installed_audit && specs_rebuild_engine(&files, case_name) {
        match_clean_rebuild_to_installed_module(&session, &python, &checkout, &mut build);
    }
    let job = Job {
        session: &session,
        checkout: &checkout,
        python: &python,
        root: &root,
        build: &build,
        passing: RefCell::new(HashSet::new()),
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
            if engine_only && !is_engine_source(&case.file) {
                continue;
            }
            saw_case = true;
            // A clean module before each case: the test is run unmutated first, and a case that
            // edits Rust leaves the mutated module installed until this.
            if let Some(code) = settle_or_stop(&job) {
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

/// Cases whose `test` names no test that exists. A renamed test would otherwise fail only in the
/// mutate job, after the wait for the test run.
pub fn test_misses(checkout: &Path) -> Result<Vec<String>, String> {
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
            if let Some(reason) = missing_test(checkout, &case.test) {
                misses.push(format!("{stem}: {} test {} {reason}", case.name, case.test));
            }
        }
    }
    Ok(misses)
}

/// Why the test named by a case cannot be found, or `None` when it exists.
fn missing_test(checkout: &Path, test: &str) -> Option<String> {
    match cargo_test(test) {
        Err(error) => Some(error),
        Ok(Some(cargo)) => {
            let target = format!("tests/{}.rs", cargo.target);
            let defined = integration_test_files(&checkout.join("engine"))
                .into_iter()
                .filter(|path| path.ends_with(&target))
                .any(|path| {
                    fs::read_to_string(path).is_ok_and(|body| defines_rust_fn(&body, &cargo.name))
                });
            (!defined).then(|| format!("is not a function in engine/**/{target}"))
        }
        Ok(None) => python_test_missing(checkout, test),
    }
}

/// `path::function`, with a `[param]` id and a class part (`Class::function`) ignored.
fn python_test_missing(checkout: &Path, test: &str) -> Option<String> {
    let bare = test.split_once('[').map_or(test, |(head, _)| head);
    let Some((file, rest)) = bare.split_once("::") else {
        return Some("has no ::function part".to_string());
    };
    let function = rest.rsplit("::").next().unwrap_or(rest);
    match fs::read_to_string(checkout.join(file)) {
        Err(_) => Some(format!("names {file}, which does not exist")),
        Ok(body) => (!defines_python_fn(&body, function))
            .then(|| format!("has no function {function} in {file}")),
    }
}

fn defines_python_fn(body: &str, name: &str) -> bool {
    body.lines().any(|line| {
        let line = line.trim_start();
        let line = line.strip_prefix("async ").unwrap_or(line);
        line.strip_prefix("def ")
            .and_then(|rest| rest.strip_prefix(name))
            .is_some_and(|rest| rest.starts_with('('))
    })
}

fn defines_rust_fn(body: &str, name: &str) -> bool {
    body.lines().any(|line| {
        let line = line.trim_start().trim_start_matches("pub ");
        line.strip_prefix("fn ")
            .and_then(|rest| rest.strip_prefix(name))
            .is_some_and(|rest| rest.starts_with('('))
    })
}

/// Every `.rs` file under `dir`, except build output in `target` directories.
fn integration_test_files(dir: &Path) -> Vec<PathBuf> {
    let mut found = Vec::new();
    let Ok(entries) = fs::read_dir(dir) else {
        return found;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            if entry.file_name() != "target" {
                found.extend(integration_test_files(&path));
            }
        } else if path.extension().and_then(|ext| ext.to_str()) == Some("rs") {
            found.push(path);
        }
    }
    found
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

struct CargoTest {
    package: String,
    target: String,
    name: String,
}

fn cargo_test(test: &str) -> Result<Option<CargoTest>, String> {
    let Some(rest) = test.strip_prefix("cargo:") else {
        return Ok(None);
    };
    let parts: Vec<&str> = rest.split(':').collect();
    if parts.len() != 3 || parts.iter().any(|part| part.is_empty()) {
        return Err(format!(
            "cargo test must be cargo:<package>:<target>:<name>, got {test}"
        ));
    }
    Ok(Some(CargoTest {
        package: parts[0].to_string(),
        target: parts[1].to_string(),
        name: parts[2].to_string(),
    }))
}

enum Baseline {
    Green,
    Red(String),
    Interrupted(u8),
}

fn pytest_command(job: &Job<'_>, test: &str) -> Vec<String> {
    vec![
        job.python.to_string_lossy().into_owned(),
        "-m".into(),
        "pytest".into(),
        test.to_string(),
        "-q".into(),
        "-x".into(),
        "-p".into(),
        "no:cacheprovider".into(),
    ]
}

fn cargo_command(cargo: &CargoTest) -> Vec<String> {
    vec![
        "cargo".to_string(),
        "test".to_string(),
        "-p".to_string(),
        cargo.package.clone(),
        "--test".to_string(),
        cargo.target.clone(),
        "--".to_string(),
        cargo.name.clone(),
        "--exact".to_string(),
    ]
}

/// The case's test, run once per run without any mutation. A test that is red on its own cannot
/// catch anything, so its case is `BASE`, not `RED`; without this a test that fails to import
/// would count every mutation as caught.
fn baseline(job: &Job<'_>, case: &Case, cargo: Option<&CargoTest>) -> Baseline {
    if job.passing.borrow().contains(&case.test) {
        return Baseline::Green;
    }
    let (command, cwd, timeout) = match cargo {
        Some(cargo) => (
            cargo_command(cargo),
            job.checkout.join("engine"),
            Some(rebuild::build_timeout()),
        ),
        None => (
            pytest_command(job, &case.test),
            job.checkout.to_path_buf(),
            None,
        ),
    };
    let ran = match job.session.run_logged_in(&command, timeout, &cwd) {
        Ok(ran) => ran,
        Err(error) => return Baseline::Red(format!("test did not run unmutated: {error}")),
    };
    if ran.code >= 128 {
        return Baseline::Interrupted(ran.code);
    }
    if ran.code != 0 {
        let line = match cargo {
            Some(_) => cargo_failure_line(&ran.log),
            None => failing_line(&ran.log),
        };
        return Baseline::Red(format!("test is red without the mutation: {line}"));
    }
    job.passing.borrow_mut().insert(case.test.clone());
    Baseline::Green
}

fn run_case(job: &Job<'_>, stem: &str, case: &Case) -> CaseEnd {
    if let Some(detail) = reject_expect(case) {
        return done("PATTERN", detail);
    }
    let cargo = match cargo_test(&case.test) {
        Ok(cargo) => cargo,
        Err(detail) => return done("PATTERN", detail),
    };
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
    match baseline(job, case, cargo.as_ref()) {
        Baseline::Green => {}
        Baseline::Red(detail) => return done("BASE", detail),
        Baseline::Interrupted(code) => return CaseEnd::Interrupted(code),
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
    if let Some(cargo) = cargo {
        return run_cargo(job, guard, case, &cargo);
    }
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
    let command = pytest_command(job, &case.test);
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

fn run_cargo(job: &Job<'_>, guard: Guard, case: &Case, cargo: &CargoTest) -> CaseEnd {
    let command = cargo_command(cargo);
    let engine = job.checkout.join("engine");
    let ran = match job
        .session
        .run_logged_in(&command, Some(rebuild::build_timeout()), &engine)
    {
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
    drop(guard);
    if ran.code == 0 {
        return done("GREEN", String::new());
    }
    if compile_failed(&ran.log) {
        let label = if case.expect == "build" {
            "RED"
        } else {
            "BUILD"
        };
        return done(label, build_failure_line(&ran.log));
    }
    done("RED", cargo_failure_line(&ran.log))
}

fn compile_failed(log: &Path) -> bool {
    fs::read_to_string(log)
        .map(|text| text.contains("could not compile"))
        .unwrap_or(false)
}

fn cargo_failure_line(log: &Path) -> String {
    let Ok(text) = fs::read_to_string(log) else {
        return String::new();
    };
    text.lines()
        .find(|line| {
            let trimmed = line.trim();
            trimmed.contains("assertion")
                || trimmed.contains("assert")
                || trimmed.contains("panicked")
        })
        .map(|line| line.trim().chars().take(110).collect())
        .unwrap_or_default()
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
    if let Err(error) = edits::mark_engine_rebuild(job.root, job.checkout, &job.build.clean_command)
    {
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

fn specs_rebuild_engine(files: &[PathBuf], case_name: Option<&str>) -> bool {
    for spec in files {
        let Ok(text) = fs::read_to_string(spec) else {
            continue;
        };
        let Ok(cases) = serde_json::from_str::<Vec<Case>>(&text) else {
            continue;
        };
        for case in cases {
            if case_name.is_some_and(|wanted| wanted != case.name) {
                continue;
            }
            if is_engine_source(&case.file) && cargo_test(&case.test).ok().flatten().is_none() {
                return true;
            }
        }
    }
    false
}

fn match_clean_rebuild_to_installed_module(
    session: &Session,
    python: &Path,
    checkout: &Path,
    build: &mut EngineBuild,
) {
    let command = vec![
        python.to_string_lossy().into_owned(),
        "-c".to_string(),
        rebuild::AUDIT_PROBE.to_string(),
    ];
    let audit = match session.run_logged_in(&command, Some(60), checkout) {
        Ok(ran) => {
            let output = fs::read_to_string(&ran.log).unwrap_or_default();
            rebuild::classify_audit_probe(ran.code, &output)
        }
        Err(error) => {
            eprintln!("could not read the installed engine module: {error}");
            rebuild::InstalledAudit::Unknown
        }
    };
    match audit {
        rebuild::InstalledAudit::Present => {
            eprintln!("installed engine module has the audit functions");
        }
        rebuild::InstalledAudit::Absent => {
            build.clean_command = rebuild::without_audit(&build.command);
            eprintln!(
                "installed engine module has no audit functions; the clean rebuild will match that"
            );
        }
        rebuild::InstalledAudit::Unknown => {
            eprintln!(
                "could not read the installed engine module; the clean rebuild keeps --features audit"
            );
        }
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

    #[test]
    fn a_cargo_test_name_has_three_fields() {
        let parsed = cargo_test(
            "cargo:flexweek-engine:test_solver:test_a_low_session_skips_midnight_when_the_morning_is_free",
        )
        .unwrap()
        .unwrap();
        assert_eq!(parsed.package, "flexweek-engine");
        assert_eq!(parsed.target, "test_solver");
        assert_eq!(
            parsed.name,
            "test_a_low_session_skips_midnight_when_the_morning_is_free"
        );
        assert!(
            cargo_test("backend/tests/test_solver.py::test_names")
                .unwrap()
                .is_none()
        );
        assert!(cargo_test("cargo:flexweek-engine:test_solver").is_err());
    }
}
