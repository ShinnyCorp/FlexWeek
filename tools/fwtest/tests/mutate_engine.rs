//! Engine mutations rebuild a stand-in module. The stand-in reads the Rust
//! source and writes the Python the test imports, which is what maturin does
//! for the real engine.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, Instant};

fn scratch() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "fwtest-eng-{}-{}",
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

fn fwtest(home: &Path, repo: &Path) -> Command {
    let mut command = Command::new(env!("CARGO_BIN_EXE_fwtest"));
    command
        .current_dir(repo)
        .env("HOME", home)
        .env("XDG_RUNTIME_DIR", home.join("no-systemd"))
        .env("DBUS_SESSION_BUS_ADDRESS", "")
        .env("FWTEST_QUEUE_POLL_SECS", "1")
        .env("FWTEST_QUEUE_WAIT_SECS", "8")
        .env("FWTEST_ENGINE_BUILD_TIMEOUT", "20")
        .env("FWTEST_PYTHON", project_python());
    command
}

fn write_repo(repo: &Path, spec: &str) {
    fs::create_dir_all(repo.join("engine")).unwrap();
    fs::create_dir_all(repo.join("toy")).unwrap();
    fs::write(repo.join("engine/rule.rs"), "pub const N: i32 = 1;\n").unwrap();
    fs::write(repo.join("toy/__init__.py"), "").unwrap();
    fs::write(repo.join("toy/built.py"), "VALUE = 1\n").unwrap();
    fs::write(
        repo.join("toy/test_built.py"),
        "def test_value():\n    from toy.built import VALUE\n    assert VALUE == 1\n",
    )
    .unwrap();
    fs::write(
        repo.join("install_engine.py"),
        r#"import pathlib, re, sys
text = pathlib.Path("engine/rule.rs").read_text()
if "N: i32 = 9" in text:
    print("error: mutated const does not compile", file=sys.stderr)
    raise SystemExit(1)
value = re.search(r"N: i32 = \(?(\d+)\)?", text).group(1)
pathlib.Path("toy/built.py").write_text(f"VALUE = {value}\n")
"#,
    )
    .unwrap();
    fs::write(repo.join("mutations.json"), spec).unwrap();
}

fn engine_build_arg(repo: &Path) -> String {
    format!(
        "{} {}",
        project_python().display(),
        repo.join("install_engine.py").display()
    )
}

fn rule(repo: &Path) -> String {
    fs::read_to_string(repo.join("engine/rule.rs")).unwrap()
}

#[test]
fn an_engine_mutation_is_caught_only_after_the_rebuild() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git_init(&repo);
    write_repo(
        &repo,
        r#"[{"name":"n becomes two","file":"engine/rule.rs","old":"pub const N: i32 = 1;\n","new":"pub const N: i32 = 2;\n","test":"toy/test_built.py::test_value"}]"#,
    );
    let output = fwtest(&home, &repo)
        .args([
            "mutate",
            "--engine-build",
            &engine_build_arg(&repo),
            "mutations.json",
        ])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        output.status.success(),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    assert!(
        stdout.contains("RED") && stdout.contains("n becomes two"),
        "{stdout}"
    );
    assert!(stdout.contains("built in "), "{stdout}");
    assert!(stdout.contains("every mutation was caught"), "{stdout}");
    assert!(stderr.contains("rebuilt clean engine module"), "{stderr}");
    assert!(rule(&repo).contains("N: i32 = 1"), "{}", rule(&repo));
    assert_eq!(
        fs::read_to_string(repo.join("toy/built.py")).unwrap(),
        "VALUE = 1\n"
    );
    assert!(
        !home
            .join(".flexweek-ui-harness/fwtest/edits/engine-module.json")
            .exists()
    );
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_skipped_rebuild_leaves_the_engine_mutation_uncaught() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git_init(&repo);
    write_repo(
        &repo,
        r#"[{"name":"n becomes two","file":"engine/rule.rs","old":"pub const N: i32 = 1;\n","new":"pub const N: i32 = 2;\n","test":"toy/test_built.py::test_value"}]"#,
    );
    let output = fwtest(&home, &repo)
        .args(["mutate", "--no-engine-rebuild", "mutations.json"])
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
        stdout.contains("GREEN") && stdout.contains("rebuild skipped"),
        "{stdout}"
    );
    assert!(stdout.contains("1 mutation(s) SURVIVED"), "{stdout}");
    assert!(!stderr.contains("rebuilt clean engine module"), "{stderr}");
    assert!(rule(&repo).contains("N: i32 = 1"), "{}", rule(&repo));
    assert_eq!(
        fs::read_to_string(repo.join("toy/built.py")).unwrap(),
        "VALUE = 1\n"
    );
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_noop_engine_mutation_is_not_caught() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git_init(&repo);
    write_repo(
        &repo,
        r#"[{"name":"n wrapped","file":"engine/rule.rs","old":"pub const N: i32 = 1;\n","new":"pub const N: i32 = (1);\n","test":"toy/test_built.py::test_value"}]"#,
    );
    let output = fwtest(&home, &repo)
        .args([
            "mutate",
            "--engine-build",
            &engine_build_arg(&repo),
            "mutations.json",
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
        stdout.contains("GREEN") && stdout.contains("n wrapped"),
        "{stdout}"
    );
    assert!(stdout.contains("1 mutation(s) SURVIVED"), "{stdout}");
    assert_eq!(
        fs::read_to_string(repo.join("toy/built.py")).unwrap(),
        "VALUE = 1\n"
    );
    let _ = fs::remove_dir_all(home);
}

#[test]
fn a_failed_engine_build_is_not_caught_unless_the_case_expects_it() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git_init(&repo);
    write_repo(
        &repo,
        r#"[{"name":"n does not compile","file":"engine/rule.rs","old":"pub const N: i32 = 1;\n","new":"pub const N: i32 = 9;\n","test":"toy/test_built.py::test_value"}]"#,
    );
    let output = fwtest(&home, &repo)
        .args([
            "mutate",
            "--engine-build",
            &engine_build_arg(&repo),
            "mutations.json",
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
        stdout.contains("BUILD") && stdout.contains("did not build"),
        "{stdout}\n{stderr}"
    );
    assert!(!stdout.contains("RED"), "{stdout}");
    assert!(stdout.contains("1 mutation(s) SURVIVED"), "{stdout}");
    assert!(rule(&repo).contains("N: i32 = 1"), "{}", rule(&repo));
    assert!(stderr.contains("rebuilt clean engine module"), "{stderr}");

    write_repo(
        &repo,
        r#"[{"name":"n does not compile","file":"engine/rule.rs","old":"pub const N: i32 = 1;\n","new":"pub const N: i32 = 9;\n","test":"toy/test_built.py::test_value","expect":"build"}]"#,
    );
    let output = fwtest(&home, &repo)
        .args([
            "mutate",
            "--engine-build",
            &engine_build_arg(&repo),
            "mutations.json",
        ])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        output.status.success(),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    assert!(
        stdout.contains("RED") && stdout.contains("did not build"),
        "{stdout}"
    );
    assert!(stdout.contains("every mutation was caught"), "{stdout}");
    assert!(rule(&repo).contains("N: i32 = 1"), "{}", rule(&repo));
    let _ = fs::remove_dir_all(home);
}

#[test]
fn clean_restores_the_file_and_rebuilds_after_a_killed_engine_mutate() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git_init(&repo);
    write_repo(
        &repo,
        r#"[{"name":"n becomes two","file":"engine/rule.rs","old":"pub const N: i32 = 1;\n","new":"pub const N: i32 = 2;\n","test":"toy/test_built.py::test_value"}]"#,
    );
    let stamp = home.join("stamp");
    let script = repo.join("sleep_engine.py");
    fs::write(
        &script,
        r#"import os, pathlib, time
text = pathlib.Path("engine/rule.rs").read_text()
stamp = pathlib.Path(os.environ["ENGINE_STAMP"])
if "N: i32 = 2" in text:
    stamp.write_text("mutated\n")
    time.sleep(30)
else:
    stamp.write_text("clean\n")
"#,
    )
    .unwrap();
    let build = format!("{} {}", project_python().display(), script.display());
    let mut child = fwtest(&home, &repo)
        .env("ENGINE_STAMP", &stamp)
        .args(["mutate", "--engine-build", &build, "mutations.json"])
        .spawn()
        .unwrap();
    let started = Instant::now();
    loop {
        let text = fs::read_to_string(&stamp).unwrap_or_default();
        if text.contains("mutated") {
            break;
        }
        assert!(
            started.elapsed() < Duration::from_secs(8),
            "build never started: {text} source={}",
            rule(&repo)
        );
        std::thread::sleep(Duration::from_millis(30));
    }
    let mid = rule(&repo);
    assert!(mid.contains("N: i32 = 2"), "kill restored early: {mid}");
    let _ = Command::new("kill")
        .args(["-KILL", &child.id().to_string()])
        .status();
    let _ = child.wait();
    assert!(
        home.join(".flexweek-ui-harness/fwtest/edits/engine-module.json")
            .is_file(),
        "the module mark was not left for clean"
    );
    let cleaned = fwtest(&home, &repo)
        .env("ENGINE_STAMP", &stamp)
        .arg("clean")
        .output()
        .unwrap();
    let stderr = String::from_utf8_lossy(&cleaned.stderr);
    assert!(
        cleaned.status.success(),
        "stderr:\n{stderr}\n{}",
        String::from_utf8_lossy(&cleaned.stdout)
    );
    let restored = rule(&repo);
    assert!(restored.contains("N: i32 = 1"), "{restored}");
    assert!(!restored.contains("N: i32 = 2"), "{restored}");
    let stamp_text = fs::read_to_string(&stamp).unwrap_or_default();
    assert!(
        stamp_text.contains("clean"),
        "clean did not rebuild: {stamp_text}\n{stderr}"
    );
    assert!(
        !home
            .join(".flexweek-ui-harness/fwtest/edits/engine-module.json")
            .exists()
    );
    let _ = fs::remove_dir_all(home);
}

fn write_default_maturin(repo: &Path, module_source: &str) {
    write_repo(
        repo,
        r#"[{"name":"n becomes two","file":"engine/rule.rs","old":"pub const N: i32 = 1;\n","new":"pub const N: i32 = 2;\n","test":"toy/test_built.py::test_value"}]"#,
    );
    let bin = repo.join(".venv/bin");
    fs::create_dir_all(&bin).unwrap();
    let maturin = bin.join("maturin");
    fs::write(
        &maturin,
        r#"#!/usr/bin/env python3
import os, pathlib, re, sys
log = pathlib.Path(os.environ["BUILD_LOG"])
with log.open("a") as handle:
    handle.write(" ".join(sys.argv) + "\n")
text = pathlib.Path("engine/rule.rs").read_text()
value = re.search(r"N: i32 = \(?(\d+)\)?", text).group(1)
pathlib.Path("toy/built.py").write_text(f"VALUE = {value}\n")
"#,
    )
    .unwrap();
    let mut permissions = fs::metadata(&maturin).unwrap().permissions();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        permissions.set_mode(0o755);
    }
    fs::set_permissions(&maturin, permissions).unwrap();
    fs::create_dir_all(repo.join("fake")).unwrap();
    fs::write(repo.join("fake/flexweek_engine.py"), module_source).unwrap();
}

fn builds_with_default_command(module_source: &str) -> (String, String, String) {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    git_init(&repo);
    write_default_maturin(&repo, module_source);
    let log = home.join("builds.log");
    let output = fwtest(&home, &repo)
        .env("BUILD_LOG", &log)
        .env("PYTHONPATH", repo.join("fake"))
        .args(["mutate", "mutations.json"])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&output.stdout).into_owned();
    let stderr = String::from_utf8_lossy(&output.stderr).into_owned();
    assert!(
        output.status.success(),
        "stdout:\n{stdout}\nstderr:\n{stderr}"
    );
    let recorded = fs::read_to_string(&log).unwrap_or_default();
    let _ = fs::remove_dir_all(&home);
    (recorded, stdout, stderr)
}

#[test]
fn a_module_with_audit_is_rebuilt_with_audit() {
    let (recorded, stdout, stderr) =
        builds_with_default_command("def panic_probe():\n    return None\n");
    let lines: Vec<&str> = recorded.lines().collect();
    assert_eq!(lines.len(), 2, "{recorded}");
    assert!(lines[0].contains("--features audit"), "{recorded}");
    assert!(lines[1].contains("--features audit"), "{recorded}");
    assert!(stdout.contains("RED"), "{stdout}");
    assert!(
        stderr.contains("installed engine module has the audit functions"),
        "{stderr}"
    );
}

#[test]
fn a_module_without_audit_is_left_without_it() {
    let (recorded, _stdout, stderr) = builds_with_default_command("VALUE = 1\n");
    let lines: Vec<&str> = recorded.lines().collect();
    assert_eq!(lines.len(), 2, "{recorded}");
    assert!(lines[0].contains("--features audit"), "{recorded}");
    assert!(
        !lines[1].contains("audit"),
        "clean rebuild changed the feature set: {recorded}"
    );
    assert!(stderr.contains("has no audit functions"), "{stderr}");
}

#[test]
fn an_unreadable_module_keeps_the_audit_default() {
    let (recorded, _stdout, stderr) = builds_with_default_command("raise RuntimeError('unread')\n");
    let lines: Vec<&str> = recorded.lines().collect();
    assert_eq!(lines.len(), 2, "{recorded}");
    assert!(lines[0].contains("--features audit"), "{recorded}");
    assert!(lines[1].contains("--features audit"), "{recorded}");
    assert!(stderr.contains("could not read"), "{stderr}");
}
