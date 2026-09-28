//! The rig command is tested with stand-in scripts. No real KWin is started.

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;

use fwtest::identity;

fn scratch() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "fwtest-rig-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(path.join("no-systemd")).unwrap();
    path
}

fn write_script(path: &Path, body: &str) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, body).unwrap();
    let mut perms = fs::metadata(path).unwrap().permissions();
    perms.set_mode(0o755);
    fs::set_permissions(path, perms).unwrap();
}

#[test]
fn rig_drops_keep_stops_the_hidden_session_and_leaves_no_child() {
    let home = scratch();
    let repo = home.join("repo");
    fs::create_dir_all(&repo).unwrap();
    let git = Command::new("git")
        .arg("init")
        .current_dir(&repo)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .unwrap();
    assert!(git.success());
    let log = home.join("rig.log");
    write_script(
        &repo.join("scripts/rig/drive.py"),
        &format!(
            r#"#!/bin/sh
printf 'keep=%s\n' "${{FLEXWEEK_RIG_KEEP-}}" >> "{log}"
printf 'args=%s\n' "$*" >> "{log}"
sleep 120 &
echo $! >> "{log}"
"#,
            log = log.display()
        ),
    );
    write_script(
        &repo.join("scripts/rig/hidden_session.py"),
        &format!(
            r#"#!/bin/sh
printf 'hidden-stop\n' >> "{log}"
"#,
            log = log.display()
        ),
    );
    let python = home.join("python");
    write_script(&python, "#!/bin/sh\nexec \"$@\"\n");
    let status = Command::new(env!("CARGO_BIN_EXE_fwtest"))
        .current_dir(&repo)
        .env("HOME", &home)
        .env("XDG_RUNTIME_DIR", home.join("no-systemd"))
        .env("DBUS_SESSION_BUS_ADDRESS", "")
        .env("FWTEST_QUEUE_POLL_SECS", "1")
        .env("FWTEST_QUEUE_WAIT_SECS", "8")
        .env("FWTEST_PYTHON", &python)
        .env("FLEXWEEK_RIG_KEEP", "1")
        .args(["rig", "--design", "classic", "--tab", "day"])
        .status()
        .unwrap();
    assert!(status.success(), "{status}");
    let text = fs::read_to_string(&log).unwrap();
    assert!(
        text.contains("keep=\n") || text.lines().any(|line| line == "keep="),
        "{text}"
    );
    assert!(!text.contains("keep=1"), "{text}");
    assert!(text.contains("hidden-stop"), "{text}");
    assert!(text.contains("--design"), "{text}");
    let pid = text
        .lines()
        .find_map(|line| line.parse::<i32>().ok())
        .expect(&text);
    assert!(
        identity::read_identity(pid).unwrap().is_none(),
        "child {pid} still running"
    );
    let _ = fs::remove_dir_all(home);
}
