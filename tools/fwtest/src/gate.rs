//! `fwtest gate` runs the same checks as `scripts/verify.py`, in the same order.
//!
//! The success line is the one `verify.py` prints, including the backend-only
//! wording. Each step is one contained command. The per-step limit is 2400
//! seconds unless `FWTEST_STEP_TIMEOUT_SECS` is set (tests use a few seconds).

use std::path::Path;
use std::process::Command;

use crate::contain::{self, half_cpus};

const VERIFIED_TAIL: &str = "Packaged binaries and other platforms need separate checks.";

pub fn verified_line(backend_only: bool) -> String {
    let scope = if backend_only {
        "Backend only; desktop NOT VERIFIED"
    } else {
        "Backend and desktop"
    };
    format!("\nVERIFIED: {scope}. {VERIFIED_TAIL}")
}

pub fn default_workers() -> u32 {
    (half_cpus().len() as u32).max(2)
}

pub fn step_timeout_secs() -> u64 {
    std::env::var("FWTEST_STEP_TIMEOUT_SECS")
        .ok()
        .and_then(|value| value.parse().ok())
        .filter(|value| *value > 0)
        .unwrap_or(2400)
}

pub fn run(backend_only: bool, workers: Option<u32>, python: Option<&Path>) -> u8 {
    let workers = workers.unwrap_or_else(default_workers);
    if workers == 0 {
        eprintln!("--workers must be at least 1");
        return 2;
    }
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
    let session = match contain::session() {
        Ok(session) => session,
        Err(code) => return code,
    };
    if !python_is_314(&python) {
        eprintln!("Verification needs the project's Python 3.14 interpreter.");
        return 1;
    }
    if !backend_only && !pyside_present(&python) {
        eprintln!(
            "Full verification needs requirements-desktop.txt. --backend-only omits desktop explicitly."
        );
        return 1;
    }
    let base = match diff_base(&checkout) {
        Ok(base) => base,
        Err(message) => {
            eprintln!("FAILED: {message}");
            return 1;
        }
    };
    let report_dir = std::env::temp_dir().join(format!(
        "fwtest-gate-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|duration| duration.as_nanos())
            .unwrap_or(0)
    ));
    if let Err(error) = std::fs::create_dir_all(&report_dir) {
        eprintln!("FAILED: could not create the pytest report directory: {error}");
        return 1;
    }
    let junit = report_dir.join("pytest.xml");
    let timeout = step_timeout_secs();
    for (name, command) in steps(&python, workers, backend_only, &junit, &base) {
        if name == "Python behavior"
            && let Err(message) = mutation_patterns(&checkout)
        {
            eprintln!("FAILED: Mutation patterns:\n{message}");
            let _ = std::fs::remove_dir_all(&report_dir);
            return 1;
        }
        println!("\n{name}");
        let _ = std::io::Write::flush(&mut std::io::stdout());
        let code = match session.run_in(&command, Some(timeout), &checkout) {
            Ok(code) => code,
            Err(error) => {
                eprintln!("FAILED: {name}: {error}");
                let _ = std::fs::remove_dir_all(&report_dir);
                return 1;
            }
        };
        if code == 124 {
            eprintln!("FAILED: {name}: timed out");
            let _ = std::fs::remove_dir_all(&report_dir);
            return 1;
        }
        if code != 0 {
            eprintln!("FAILED: {name} (exit {code})");
            let _ = std::fs::remove_dir_all(&report_dir);
            return 1;
        }
    }
    match junit_totals(&junit) {
        Ok((count, skipped)) if count > 0 && skipped == 0 => {}
        Ok((count, skipped)) => {
            eprintln!("FAILED: Python suite ran {count} tests with {skipped} skipped.");
            let _ = std::fs::remove_dir_all(&report_dir);
            return 1;
        }
        Err(error) => {
            eprintln!("FAILED: Python suite ran 0 tests with 0 skipped.");
            eprintln!("FAILED: could not read the pytest report: {error}");
            let _ = std::fs::remove_dir_all(&report_dir);
            return 1;
        }
    }
    let _ = std::fs::remove_dir_all(&report_dir);
    println!("{}", verified_line(backend_only));
    0
}

/// Every mutation case's old text still occurs once in its source file, and its test still exists.
/// Edits near a case break the first, and a rename breaks the second; finding either out in the long
/// test step, or in a later mutation run, wastes the wait. A checkout with no `scripts/mutations`
/// has nothing to check.
fn mutation_patterns(checkout: &Path) -> Result<(), String> {
    println!("\nMutation patterns");
    if !checkout.join("scripts/mutations").is_dir() {
        println!("no scripts/mutations here; nothing to check");
        return Ok(());
    }
    let mut misses = crate::mutate::pattern_misses(checkout)?;
    misses.extend(crate::mutate::test_misses(checkout)?);
    if misses.is_empty() {
        return Ok(());
    }
    Err(misses.join("\n"))
}

pub fn steps(
    python: &Path,
    workers: u32,
    backend_only: bool,
    junit: &Path,
    base: &str,
) -> Vec<(String, Vec<String>)> {
    let python = python.to_string_lossy().into_owned();
    let mut pytest = vec![
        python.clone(),
        "-m".to_string(),
        "pytest".to_string(),
        "-q".to_string(),
        "-n".to_string(),
        workers.to_string(),
        format!("--junitxml={}", junit.display()),
    ];
    if backend_only {
        pytest.push("backend/tests".to_string());
    }
    vec![
        (
            "Python lint".to_string(),
            vec![
                python.clone(),
                "-m".to_string(),
                "ruff".to_string(),
                "check".to_string(),
                ".".to_string(),
            ],
        ),
        (
            "Backend types".to_string(),
            vec![
                python.clone(),
                "-m".to_string(),
                "mypy".to_string(),
                "backend".to_string(),
            ],
        ),
        ("Python behavior".to_string(), pytest),
        (
            "Working diff whitespace".to_string(),
            vec!["git".to_string(), "diff".to_string(), "--check".to_string()],
        ),
        (
            "Staged diff whitespace".to_string(),
            vec![
                "git".to_string(),
                "diff".to_string(),
                "--cached".to_string(),
                "--check".to_string(),
            ],
        ),
        (
            "Committed range whitespace".to_string(),
            vec![
                "git".to_string(),
                "diff".to_string(),
                "--check".to_string(),
                format!("{base}...HEAD"),
            ],
        ),
    ]
}

fn python_is_314(python: &Path) -> bool {
    let output = Command::new(python)
        .args([
            "-c",
            "import sys; print(sys.version_info[0], sys.version_info[1])",
        ])
        .output();
    let Ok(output) = output else {
        return false;
    };
    let text = String::from_utf8_lossy(&output.stdout);
    output.status.success() && text.split_whitespace().eq(["3", "14"])
}

fn pyside_present(python: &Path) -> bool {
    Command::new(python)
        .args([
            "-c",
            "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PySide6') else 1)",
        ])
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn diff_base(checkout: &Path) -> Result<String, String> {
    let from_env = std::env::var("VERIFY_BASE_SHA").ok();
    for candidate in [
        from_env,
        Some("main".to_string()),
        Some("origin/main".to_string()),
        Some("HEAD^".to_string()),
    ]
    .into_iter()
    .flatten()
    {
        if candidate.is_empty() || candidate.chars().all(|c| c == '0') {
            continue;
        }
        let ok = Command::new("git")
            .args(["rev-parse", "--verify", &candidate])
            .current_dir(checkout)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map(|status| status.success())
            .unwrap_or(false);
        if ok {
            return Ok(candidate);
        }
    }
    Err("Could not find a base revision for committed diff checks.".to_string())
}

fn junit_totals(path: &Path) -> std::io::Result<(u64, u64)> {
    let text = std::fs::read_to_string(path)?;
    let mut tests = 0u64;
    let mut skipped = 0u64;
    let mut rest = text.as_str();
    while let Some(start) = rest.find("<testsuite ") {
        rest = &rest[start + 1..];
        let end = rest.find('>').unwrap_or(rest.len());
        let tag = &rest[..end];
        tests += attr(tag, "tests");
        skipped += attr(tag, "skipped");
    }
    Ok((tests, skipped))
}

fn attr(tag: &str, name: &str) -> u64 {
    let key = format!("{name}=\"");
    let Some(start) = tag.find(&key) else {
        return 0;
    };
    let value = &tag[start + key.len()..];
    let end = value.find('"').unwrap_or(value.len());
    value[..end].parse().unwrap_or(0)
}
