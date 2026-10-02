//! Mutation cases against the toy fixture. A killed run is restored by clean.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, Instant};

fn scratch() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "fwtest-mut-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(path.join("no-systemd")).unwrap();
    path
}

fn git_init(dir: &Path) {
    let status = Command::new("git")
        .arg("init")
        .current_dir(dir)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .unwrap();
    assert!(status.success());
}

fn project_python() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../.venv/bin/python")
}

fn copy_fixture(repo: &Path) {
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures");
    fs::create_dir_all(repo.join("toy")).unwrap();
    for name in [
        "toy/calc.py",
        "toy/test_calc.py",
        "toy/__init__.py",
        "mutations.json",
    ] {
        fs::copy(fixture.join(name), repo.join(name)).unwrap();
    }
}

fn fwtest(home: &Path, repo: &Path) -> Command {
    let mut command = Command::new(env!("CARGO_BIN_EXE_fwtest"));
    command
        .current_dir(repo)
        .env("HOME", home)
        .env("XDG_RUNTIME_DIR", home.join("no-systemd"))
        .env("DBUS_SESSION_BUS_ADDRESS", "")
        .env("FWTEST_QUEUE_POLL_SECS", "1")
        .env("FWTEST_QUEUE_WAIT_SECS", "8")
        .env("FWTEST_PYTHON", project_python());
    command
}

#[test]
fn the_toy_spec_reports_caught_survived_and_missing() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git_init(&repo);
    copy_fixture(&repo);
    let cache = repo.join("toy/__pycache__");
    fs::create_dir_all(&cache).unwrap();
    fs::write(cache.join("calc.cpython-314.pyc"), b"stale").unwrap();
    let output = fwtest(&home, &repo)
        .args(["mutate", "mutations.json"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(
        output.status.code(),
        Some(1),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    assert!(
        stdout.contains("RED") && stdout.contains("add subtracts"),
        "{stdout}"
    );
    assert!(
        stdout.contains("GREEN") && stdout.contains("a comment changes nothing"),
        "{stdout}"
    );
    assert!(
        stdout.contains("PATTERN") && stdout.contains("the pattern is not there"),
        "{stdout}"
    );
    assert!(stdout.contains("2 mutation(s) SURVIVED"), "{stdout}");
    let source = fs::read_to_string(repo.join("toy/calc.py")).unwrap();
    assert!(source.contains("a + b"), "{source}");
    assert!(!source.contains("a - b"), "{source}");
    assert!(!cache.join("calc.cpython-314.pyc").exists());
    let _ = fs::remove_dir_all(home);
}

#[test]
fn mutate_prints_one_line_per_case_and_keeps_pytest_output_in_the_job_log() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git_init(&repo);
    copy_fixture(&repo);
    let output = fwtest(&home, &repo)
        .args(["mutate", "mutations.json"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(
        output.status.code(),
        Some(1),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    let line = |label: &str, name: &str, why: &str| {
        format!("{label:5} {:10} {name:56} {why}", "mutations")
    };
    let expected = vec![
        line("RED", "add subtracts", "E       assert -1 == 5"),
        line("GREEN", "a comment changes nothing", ""),
        line(
            "PATTERN",
            "the pattern is not there",
            "pattern found 0 times in toy/calc.py",
        ),
        "2 mutation(s) SURVIVED".to_string(),
    ];
    assert_eq!(
        stdout.lines().collect::<Vec<_>>(),
        expected,
        "stderr:\n{stderr}"
    );
    let logs = home.join(".flexweek-ui-harness/fwtest/logs");
    let text: String = fs::read_dir(&logs)
        .unwrap()
        .map(|entry| fs::read_to_string(entry.unwrap().path()).unwrap())
        .collect();
    assert!(text.contains("1 failed"), "log:\n{text}");
    assert!(text.contains("1 passed"), "log:\n{text}");
    assert!(text.contains("assert -1 == 5"), "log:\n{text}");
    let _ = fs::remove_dir_all(home);
}

#[test]
fn one_caught_case_exits_clean() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git_init(&repo);
    copy_fixture(&repo);
    let output = fwtest(&home, &repo)
        .args(["mutate", "--case", "add subtracts", "mutations.json"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        output.status.success(),
        "{stdout}\n{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(stdout.contains("every mutation was caught"), "{stdout}");
    assert!(!stdout.contains("a comment changes nothing"), "{stdout}");
    let _ = fs::remove_dir_all(home);
}

#[test]
fn an_unknown_case_name_exits_2() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git_init(&repo);
    copy_fixture(&repo);
    let output = fwtest(&home, &repo)
        .args(["mutate", "--case", "no such case", "mutations.json"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(
        output.status.code(),
        Some(2),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    assert!(
        stderr.contains("no case named no such case"),
        "stderr:\n{stderr}\nstdout:\n{stdout}"
    );
    assert!(!stdout.contains("every mutation was caught"), "{stdout}");
    let _ = fs::remove_dir_all(home);
}

#[test]
fn mutate_from_a_subdirectory_runs_the_comment_case() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git_init(&repo);
    copy_fixture(&repo);
    let nested = repo.join("nested");
    fs::create_dir_all(&nested).unwrap();
    let output = fwtest(&home, &repo)
        .current_dir(&nested)
        .args([
            "mutate",
            "--case",
            "a comment changes nothing",
            repo.join("mutations.json").to_str().unwrap(),
        ])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(
        output.status.code(),
        Some(1),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    assert!(
        stdout.contains("GREEN") && stdout.contains("a comment changes nothing"),
        "from a subdirectory the comment case should run and survive:\n{stdout}\n{stderr}"
    );
    assert!(!stdout.contains("every mutation was caught"), "{stdout}");
    let _ = fs::remove_dir_all(home);
}

#[test]
fn clean_restores_a_file_left_by_a_killed_mutate() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git_init(&repo);
    fs::write(repo.join("calc.py"), "def add(a, b):\n    return a + b\n").unwrap();
    fs::write(
        repo.join("mutations.json"),
        r#"[{"name":"add subtracts","file":"calc.py","old":"a + b","new":"a - b","test":"calc.py"}]"#,
    )
    .unwrap();
    let python = home.join("python");
    // The first pytest run is the unmutated baseline and must pass; the second, on the mutated
    // file, hangs so the run can be killed mid-case.
    fs::write(
        &python,
        "#!/bin/sh\nif [ \"$2\" = pytest ]; then if [ -e \"$HOME/baseline-ran\" ]; then sleep 30; else touch \"$HOME/baseline-ran\"; exit 0; fi; fi\nexit 1\n",
    )
    .unwrap();
    let mut perms = fs::metadata(&python).unwrap().permissions();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        perms.set_mode(0o755);
    }
    fs::set_permissions(&python, perms).unwrap();
    let mut child = fwtest(&home, &repo)
        .env("FWTEST_PYTHON", &python)
        .args(["mutate", "mutations.json"])
        .spawn()
        .unwrap();
    let source = repo.join("calc.py");
    let started = Instant::now();
    loop {
        let text = fs::read_to_string(&source).unwrap_or_default();
        if text.contains("a - b") {
            break;
        }
        assert!(
            started.elapsed() < Duration::from_secs(8),
            "edit never appeared: {text}"
        );
        std::thread::sleep(Duration::from_millis(30));
    }
    let _ = Command::new("kill")
        .args(["-KILL", &child.id().to_string()])
        .status();
    let _ = child.wait();
    let mid = fs::read_to_string(&source).unwrap();
    assert!(mid.contains("a - b"), "kill restored early: {mid}");
    let cleaned = fwtest(&home, &repo).arg("clean").status().unwrap();
    assert!(cleaned.success(), "{cleaned}");
    let restored = fs::read_to_string(&source).unwrap();
    assert!(restored.contains("a + b"), "{restored}");
    assert!(!restored.contains("a - b"), "{restored}");
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_case_whose_test_is_red_before_any_mutation_is_base_and_edits_nothing() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git_init(&repo);
    copy_fixture(&repo);
    fs::write(
        repo.join("mutations.json"),
        r#"[{"name":"add subtracts","file":"toy/calc.py","old":"a + b","new":"a - b","test":"toy/test_calc.py::test_absent"}]"#,
    )
    .unwrap();
    let output = fwtest(&home, &repo)
        .args(["mutate", "mutations.json"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(
        output.status.code(),
        Some(1),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    assert!(
        stdout.contains("BASE") && stdout.contains("red without the mutation"),
        "{stdout}"
    );
    assert!(
        !stdout.contains("RED "),
        "a red test must not count as a catch: {stdout}"
    );
    let source = fs::read_to_string(repo.join("toy/calc.py")).unwrap();
    assert!(
        source.contains("a + b") && !source.contains("a - b"),
        "{source}"
    );
    let _ = fs::remove_dir_all(home);
}
