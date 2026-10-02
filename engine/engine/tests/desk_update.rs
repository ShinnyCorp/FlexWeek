//! Rust twin of the Qt-free, disk-free tests in `desktop/tests/test_update.py`.
//!
//! `test_the_version_here_is_the_one_the_changelog_announced` reads CHANGELOG.md and `version.py`'s
//! constant, so it stays Python. The two version-ordering tests call `version.py`'s own `parse` and
//! `is_newer`, which are not one of the eleven wrappers; their twins test the engine's copy of the
//! same rule in `update.rs`, which `available` uses.

mod common;

use common::desk::{object, with};
use flexweek_engine::desk::update::{
    LINUX_APPIMAGE, LINUX_TARBALL, WINDOWS_SETUP, available, due_for_check, expected_digest,
    install_kind, is_newer, parse_version, sanitize_updates, verified,
};
use serde_json::{Value, json};

// What `version.py` says; `available` takes the running version as an argument.
const VERSION: &str = "0.17.2";

fn asset(name: &str) -> Value {
    json!({"name": name, "browser_download_url": format!("https://example.invalid/{name}")})
}

fn release_of(tag: &str, names: &[String], fields: Value) -> Value {
    let base = json!({
        "tag_name": tag,
        "assets": names.iter().map(|name| asset(name)).collect::<Vec<_>>(),
        "body": "notes",
    });
    with(base, fields)
}

fn all_names() -> Vec<String> {
    vec![
        WINDOWS_SETUP.to_string(),
        format!("{WINDOWS_SETUP}.sha256"),
        LINUX_TARBALL.to_string(),
        format!("{LINUX_TARBALL}.sha256"),
    ]
}

fn release() -> Value {
    release_of("v9.9.9", &all_names(), json!({}))
}

#[test]
fn test_version_ordering_is_by_number_not_by_text() {
    // String comparison puts 0.9.0 above 0.13.0 and would offer a downgrade as an update.
    for (candidate, current, newer) in [
        ("0.14.0", "0.13.0", true),
        ("v0.14.0", "0.13.0", true),
        ("0.13.1", "0.13.0", true),
        ("1.0.0", "0.13.0", true),
        ("0.13.0", "0.13.0", false),
        ("0.12.9", "0.13.0", false),
        ("0.9.0", "0.13.0", false),
        ("0.2.0", "0.13.0", false),
    ] {
        assert_eq!(
            is_newer(candidate, current),
            newer,
            "{candidate} against {current}"
        );
    }
}

#[test]
fn test_a_tag_this_build_cannot_read_is_not_an_update() {
    for value in [
        "",
        "v",
        "1.2.3-rc1",
        "latest",
        "1.2.x",
        "2026-09-20",
        "1.2.3.4.5",
    ] {
        assert_eq!(parse_version(value), None, "{value:?}");
        assert!(!is_newer(value, "0.13.0"), "{value:?}");
    }
}

#[test]
fn test_a_newer_release_offers_the_file_for_this_install() {
    let found = available(&release(), "windows", VERSION).expect("an update");
    assert_eq!(found.version, "9.9.9");
    assert_eq!(found.asset, WINDOWS_SETUP);
    assert!(
        found.checksum_url.ends_with(".sha256"),
        "{}",
        found.checksum_url
    );
}

#[test]
fn test_an_appimage_is_offered_an_appimage() {
    let names = [
        LINUX_APPIMAGE.to_string(),
        format!("{LINUX_APPIMAGE}.sha256"),
    ];
    let release = release_of("v9.9.9", &names, json!({}));
    assert_eq!(
        available(&release, "appimage", VERSION)
            .expect("an update")
            .asset,
        LINUX_APPIMAGE
    );
    // ...and a tarball install is not offered that AppImage.
    assert_eq!(available(&release, "tarball", VERSION), None);
}

#[test]
fn test_the_running_version_is_not_an_update() {
    let running = release_of(&format!("v{VERSION}"), &all_names(), json!({}));
    assert_eq!(available(&running, "windows", VERSION), None);
}

#[test]
fn test_an_older_release_is_not_an_update() {
    let old = release_of("v0.0.1", &all_names(), json!({}));
    assert_eq!(available(&old, "windows", VERSION), None);
}

#[test]
fn test_drafts_and_prereleases_are_left_alone() {
    let draft = release_of("v9.9.9", &all_names(), json!({"draft": true}));
    let pre = release_of("v9.9.9", &all_names(), json!({"prerelease": true}));
    assert_eq!(available(&draft, "windows", VERSION), None);
    assert_eq!(available(&pre, "windows", VERSION), None);
}

#[test]
fn test_a_release_whose_build_failed_offers_nothing() {
    // A release can exist with no file for a platform if that job failed. Offering an update that
    // cannot be downloaded is worse than staying quiet.
    let names = [LINUX_TARBALL.to_string(), format!("{LINUX_TARBALL}.sha256")];
    assert_eq!(
        available(&release_of("v9.9.9", &names, json!({})), "windows", VERSION),
        None
    );
}

#[test]
fn test_an_asset_with_no_checksum_beside_it_is_refused() {
    let names = [WINDOWS_SETUP.to_string()];
    assert_eq!(
        available(&release_of("v9.9.9", &names, json!({})), "windows", VERSION),
        None
    );
}

#[test]
fn test_a_payload_that_is_not_a_release_is_not_an_update() {
    for payload in [
        Value::Null,
        json!(""),
        json!([]),
        json!({"assets": "no"}),
        json!({"tag_name": 5}),
    ] {
        assert_eq!(available(&payload, "windows", VERSION), None, "{payload}");
    }
}

#[test]
fn test_a_digest_is_taken_from_the_line_naming_this_file() {
    let digest = "a".repeat(64);
    let text = format!(
        "{}  OtherFile.exe\n{digest}  {WINDOWS_SETUP}\n",
        "b".repeat(64)
    );
    assert_eq!(expected_digest(&text, WINDOWS_SETUP), Some(digest));
    assert_eq!(expected_digest(&text, "Missing.exe"), None);
}

#[test]
fn test_a_binary_marked_checksum_line_still_reads() {
    let digest = "c".repeat(64);
    assert_eq!(
        expected_digest(&format!("{digest} *{LINUX_TARBALL}\n"), LINUX_TARBALL),
        Some(digest)
    );
}

#[test]
fn test_only_the_exact_bytes_pass() {
    let payload = b"a packaged FlexWeek";
    // hashlib.sha256(payload).hexdigest(), worked out once with Python.
    let digest = "49512409308a61965ab42f4ef27b15090ef3fd50003b26d858336a7a91d64531";
    assert!(verified(payload, Some(digest)));
    assert!(verified(payload, Some(&digest.to_uppercase())));
    assert!(!verified(b"a packaged FlexWeek!", Some(digest)));
    assert!(!verified(b"", Some(digest)));
}

#[test]
fn test_a_missing_or_unreadable_digest_never_passes() {
    // An unverified binary is the one thing that must not be run, so absence fails closed.
    for digest in [None, Some(""), Some("abc"), Some(&"z".repeat(64)[..])] {
        assert!(!verified(b"anything", digest), "{digest:?}");
    }
}

#[test]
fn test_how_this_copy_was_installed_decides_what_it_downloads() {
    assert_eq!(
        install_kind(Some("win32"), Some(""), Some(""), Some("")),
        "windows"
    );
    assert_eq!(
        install_kind(
            Some("linux"),
            Some("/x/FlexWeek-x86_64.AppImage"),
            Some("/tmp/.mount_fw"),
            Some("/tmp/.mount_fw/usr/bin/FlexWeek"),
        ),
        "appimage"
    );
    assert_eq!(
        install_kind(Some("linux"), Some(""), Some(""), Some("/opt/fw/FlexWeek")),
        "tarball"
    );
}

#[test]
fn test_another_application_s_appimage_is_not_mistaken_for_this_one() {
    // APPIMAGE is inherited by every child process. A FlexWeek started from a terminal running
    // inside some other AppImage sees that application's path, and an update would then overwrite a
    // different program. Found because the editor this was written in is itself an AppImage.
    assert_eq!(
        install_kind(
            Some("linux"),
            Some("/home/someone/AppImages/other-app.appimage"),
            Some("/tmp/.mount_other"),
            Some("/opt/flexweek/FlexWeek"),
        ),
        "tarball"
    );
}

#[test]
fn test_an_appimage_variable_with_no_mount_behind_it_is_ignored() {
    assert_eq!(
        install_kind(
            Some("linux"),
            Some("/x/FlexWeek.AppImage"),
            Some(""),
            Some("/opt/fw/FlexWeek")
        ),
        "tarball"
    );
}

fn settings(fields: Value) -> serde_json::Map<String, Value> {
    object(with(Value::Object(sanitize_updates(&Value::Null)), fields))
}

const DAY_MS: i64 = 24 * 3_600_000;

#[test]
fn test_a_fresh_install_checks_once_and_then_leaves_it_a_day() {
    let now = 1_700_000_000_000;
    assert!(due_for_check(&settings(json!({})), now));
    assert!(!due_for_check(&settings(json!({"last_ms": now})), now));
    assert!(!due_for_check(
        &settings(json!({"last_ms": now})),
        now + DAY_MS - 1
    ));
    assert!(due_for_check(
        &settings(json!({"last_ms": now})),
        now + DAY_MS
    ));
}

#[test]
fn test_turning_checks_off_stops_them() {
    assert!(!due_for_check(
        &settings(json!({"check": false})),
        1_700_000_000_000
    ));
}

#[test]
fn test_a_clock_that_went_backwards_does_not_stop_checking_forever() {
    // A last-checked stamp from the future would otherwise never come due again.
    let now = 1_700_000_000_000;
    assert!(due_for_check(
        &settings(json!({"last_ms": now + 10 * DAY_MS})),
        now
    ));
}

#[test]
fn test_the_settings_file_survives_nonsense() {
    assert_eq!(
        sanitize_updates(&Value::Null),
        object(json!({"check": true, "last_ms": 0, "skip": ""}))
    );
    assert_eq!(sanitize_updates(&json!("not a dict"))["check"], json!(true));
    assert_eq!(
        sanitize_updates(&json!({"check": "yes"}))["check"],
        json!(true)
    );
    assert_eq!(
        sanitize_updates(&json!({"check": false}))["check"],
        json!(false)
    );
    assert_eq!(
        sanitize_updates(&json!({"last_ms": -5}))["last_ms"],
        json!(0)
    );
    assert_eq!(
        sanitize_updates(&json!({"last_ms": "soon"}))["last_ms"],
        json!(0)
    );
    assert_eq!(
        sanitize_updates(&json!({"skip": "x".repeat(99)}))["skip"],
        json!("")
    );
    assert_eq!(
        sanitize_updates(&json!({"skip": "0.14.0"}))["skip"],
        json!("0.14.0")
    );
}
