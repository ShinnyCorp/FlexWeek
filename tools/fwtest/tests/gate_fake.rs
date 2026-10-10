//! `fwtest gate` on a fake checkout. The real FlexWeek suite is not run.

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;

use fwtest::gate::{default_workers, verified_line};

fn scratch() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "fwtest-gate-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(path.join("no-systemd")).unwrap();
    path
}

fn git(dir: &Path, args: &[&str]) {
    let status = Command::new("git")
        .args(args)
        .current_dir(dir)
        .env("GIT_AUTHOR_NAME", "fwtest")
        .env("GIT_AUTHOR_EMAIL", "fwtest@example.com")
        .env("GIT_COMMITTER_NAME", "fwtest")
        .env("GIT_COMMITTER_EMAIL", "fwtest@example.com")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .unwrap();
    assert!(status.success(), "git {args:?} -> {status}");
}

fn fake_checkout(home: &Path) -> (PathBuf, PathBuf) {
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git(&repo, &["init"]);
    fs::write(repo.join("README"), "hello\n").unwrap();
    git(&repo, &["add", "README"]);
    git(&repo, &["commit", "-m", "init"]);
    let python = home.join("python");
    fs::write(
        &python,
        r#"#!/bin/sh
printf '%s\n' "$*" >> "$FWTEST_FAKE_LOG"
printf 'cwd=%s\n' "$(pwd)" >> "$FWTEST_FAKE_LOG"
if [ "$1" = "-c" ]; then
  printf '%s\n' "3 14"
  exit 0
fi
if [ "$2" = "ruff" ] && [ "${FWTEST_FAKE_FAIL_RUFF:-}" = 1 ]; then
  exit 3
fi
if [ "$2" = "ruff" ] && [ "${FWTEST_FAKE_SLEEP_RUFF:-}" = 1 ]; then
  sleep 30
fi
if [ "$2" = "pytest" ]; then
  xml=""
  for arg in "$@"; do
    case "$arg" in
      --junitxml=*) xml="${arg#--junitxml=}" ;;
    esac
  done
  tests="${FWTEST_FAKE_TESTS:-1}"
  skipped="${FWTEST_FAKE_SKIPPED:-0}"
  printf '<testsuite tests="%s" skipped="%s"></testsuite>\n' "$tests" "$skipped" > "$xml"
fi
exit 0
"#,
    )
    .unwrap();
    let mut perms = fs::metadata(&python).unwrap().permissions();
    perms.set_mode(0o755);
    fs::set_permissions(&python, perms).unwrap();
    (repo, python)
}

fn fwtest(home: &Path, repo: &Path, python: &Path) -> Command {
    let base = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(repo)
        .output()
        .unwrap();
    assert!(base.status.success());
    let sha = String::from_utf8(base.stdout).unwrap();
    let mut command = Command::new(env!("CARGO_BIN_EXE_fwtest"));
    command
        .current_dir(repo)
        .env("HOME", home)
        .env("XDG_RUNTIME_DIR", home.join("no-systemd"))
        .env("DBUS_SESSION_BUS_ADDRESS", "")
        .env("FWTEST_QUEUE_POLL_SECS", "1")
        .env("FWTEST_QUEUE_WAIT_SECS", "8")
        .env("FWTEST_FAKE_LOG", home.join("calls.log"))
        .env("VERIFY_BASE_SHA", sha.trim())
        .env("FWTEST_PYTHON", python);
    command
}

#[test]
fn gate_on_a_fake_project_runs_verify_steps_and_prints_its_line() {
    let home = scratch();
    let (repo, python) = fake_checkout(&home);
    let output = fwtest(&home, &repo, &python)
        .args(["gate", "--backend-only", "--workers", "2"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        output.status.success(),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    let positions: Vec<_> = [
        "Python lint",
        "Backend types",
        "Python behavior",
        "Working diff whitespace",
        "Staged diff whitespace",
        "Committed range whitespace",
    ]
    .into_iter()
    .map(|name| stdout.find(name).unwrap_or(usize::MAX))
    .collect();
    assert!(
        positions.windows(2).all(|pair| pair[0] < pair[1]),
        "steps out of order:\n{stdout}"
    );
    assert!(stdout.contains(
        "VERIFIED: Backend only; desktop NOT VERIFIED. Packaged binaries and other platforms need separate checks."
    ));
    assert!(stdout.contains(&verified_line(true)));
    let log = fs::read_to_string(home.join("calls.log")).unwrap();
    let pytest = log
        .lines()
        .find(|line| line.contains("pytest"))
        .expect(&log);
    assert!(pytest.contains("-n 2"), "{pytest}");
    assert!(pytest.contains("backend/tests"), "{pytest}");
    let _ = fs::remove_dir_all(home);
}

#[test]
fn gate_uses_half_the_cores_and_at_least_two_workers() {
    let home = scratch();
    let (repo, python) = fake_checkout(&home);
    let output = fwtest(&home, &repo, &python)
        .args(["gate", "--backend-only"])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let log = fs::read_to_string(home.join("calls.log")).unwrap();
    let pytest = log.lines().find(|line| line.contains("pytest")).unwrap();
    let needle = format!("-n {}", default_workers());
    assert!(pytest.contains(&needle), "{pytest} wanted {needle}");
    assert!(default_workers() >= 2);
    assert_eq!(fwtest::gate::step_timeout_secs(), 2400);
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_failing_step_exits_1_and_does_not_print_verified() {
    let home = scratch();
    let (repo, python) = fake_checkout(&home);
    let output = fwtest(&home, &repo, &python)
        .env("FWTEST_FAKE_FAIL_RUFF", "1")
        .args(["gate", "--backend-only", "--workers", "2"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(output.status.code(), Some(1), "{stderr}");
    assert!(stderr.contains("FAILED: Python lint (exit 3)"), "{stderr}");
    assert!(!stdout.contains("VERIFIED:"));
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_step_that_overruns_the_limit_fails_the_gate() {
    let home = scratch();
    let (repo, python) = fake_checkout(&home);
    let output = fwtest(&home, &repo, &python)
        .env("FWTEST_STEP_TIMEOUT_SECS", "1")
        .env("FWTEST_FAKE_SLEEP_RUFF", "1")
        .args(["gate", "--backend-only", "--workers", "2"])
        .output()
        .unwrap();
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(output.status.code(), Some(1), "{stderr}");
    assert!(
        stderr.contains("FAILED: Python lint: timed out"),
        "{stderr}"
    );
    let _ = fs::remove_dir_all(home);
}

#[test]
fn skipped_pytest_results_are_not_success() {
    let home = scratch();
    let (repo, python) = fake_checkout(&home);
    let output = fwtest(&home, &repo, &python)
        .env("FWTEST_FAKE_SKIPPED", "1")
        .args(["gate", "--backend-only", "--workers", "2"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(output.status.code(), Some(1), "{stderr}");
    assert!(
        stderr.contains("FAILED: Python suite ran 1 tests with 1 skipped."),
        "{stderr}"
    );
    assert!(!stdout.contains("VERIFIED:"));
    let _ = fs::remove_dir_all(home);
}

#[test]
fn gate_from_a_subdirectory_still_runs_at_the_checkout() {
    let home = scratch();
    let (repo, python) = fake_checkout(&home);
    let nested = repo.join("nested");
    fs::create_dir_all(&nested).unwrap();
    let output = fwtest(&home, &repo, &python)
        .current_dir(&nested)
        .args(["gate", "--backend-only", "--workers", "2"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        output.status.success(),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    let log = fs::read_to_string(home.join("calls.log")).unwrap();
    let wanted = format!("cwd={}", repo.display());
    let nested_cwd = format!("cwd={}", nested.display());
    let mut job_cwds = Vec::new();
    let mut lines = log.lines();
    while let Some(line) = lines.next() {
        if line.contains(" ruff ") || line.contains(" mypy ") || line.contains(" pytest ") {
            if let Some(cwd) = lines.next() {
                job_cwds.push(cwd.to_string());
            }
        }
    }
    assert!(
        !job_cwds.is_empty() && job_cwds.iter().all(|cwd| cwd == &wanted),
        "gate jobs did not all run at the checkout:\n{log}"
    );
    assert!(
        !job_cwds.iter().any(|cwd| cwd == &nested_cwd),
        "a gate job still ran in the subdirectory:\n{log}"
    );
    let _ = fs::remove_dir_all(home);
}

fn add_mutation_spec(repo: &Path, old: &str) {
    let dir = repo.join("scripts/mutations");
    fs::create_dir_all(&dir).unwrap();
    fs::write(
        dir.join("greeting.json"),
        format!(
            r#"[{{"name": "greeting is cut", "file": "README", "old": "{old}", "new": "bye", "test": "test_greeting.py::test_greeting"}}]"#
        ),
    )
    .unwrap();
    fs::write(
        repo.join("test_greeting.py"),
        "def test_greeting():\n    pass\n",
    )
    .unwrap();
}

#[test]
fn a_mutation_case_that_no_longer_matches_fails_the_gate_before_the_tests() {
    let home = scratch();
    let (repo, python) = fake_checkout(&home);
    add_mutation_spec(&repo, "goodbye");
    let output = fwtest(&home, &repo, &python)
        .args(["gate", "--backend-only", "--workers", "2"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(output.status.code(), Some(1), "{stderr}");
    assert!(
        stderr.contains("greeting: greeting is cut pattern found 0 times in README"),
        "{stderr}"
    );
    assert!(!stdout.contains("VERIFIED:"));
    let log = fs::read_to_string(home.join("calls.log")).unwrap();
    assert!(
        !log.lines().any(|line| line.contains("pytest")),
        "the tests ran after a stale pattern:\n{log}"
    );
    let _ = fs::remove_dir_all(home);
}

#[test]
fn mutation_cases_that_match_once_let_the_gate_go_on() {
    let home = scratch();
    let (repo, python) = fake_checkout(&home);
    add_mutation_spec(&repo, "hello");
    let output = fwtest(&home, &repo, &python)
        .args(["gate", "--backend-only", "--workers", "2"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        output.status.success(),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    assert!(stdout.contains("Mutation patterns"), "{stdout}");
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_mutation_case_whose_test_was_renamed_fails_the_gate_before_the_tests() {
    let home = scratch();
    let (repo, python) = fake_checkout(&home);
    add_mutation_spec(&repo, "hello");
    fs::write(
        repo.join("test_greeting.py"),
        "def test_salutation():\n    pass\n",
    )
    .unwrap();
    let output = fwtest(&home, &repo, &python)
        .args(["gate", "--backend-only", "--workers", "2"])
        .output()
        .unwrap();
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(output.status.code(), Some(1), "{stderr}");
    assert!(
        stderr.contains("greeting: greeting is cut test test_greeting.py::test_greeting has no function test_greeting in test_greeting.py"),
        "{stderr}"
    );
    let log = fs::read_to_string(home.join("calls.log")).unwrap();
    assert!(
        !log.lines().any(|line| line.contains("pytest")),
        "the tests ran after a renamed test:\n{log}"
    );
    let _ = fs::remove_dir_all(home);
}
