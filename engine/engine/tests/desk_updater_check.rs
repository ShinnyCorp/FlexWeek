//! Rust twin of the two engine-only tests in `desktop/tests/test_updater_check.py`.
//!
//! The rest of that file runs the `Updater` against a local server and a Qt event loop and stays
//! Python.

use flexweek_engine::desk::update::{available, release_from_page};

const TAG_PAGE: &str = "https://github.com/j0nsh1n/FlexWeek/releases/tag/v9.9.9";
const DOWNLOADS: &str = "https://github.com/j0nsh1n/FlexWeek/releases/download/v9.9.9/";

#[test]
fn test_the_release_page_s_redirect_names_the_newest_release() {
    let release = release_from_page(TAG_PAGE).expect("a release");
    let update = available(&release, "appimage", "0.14.0").expect("an update");
    assert_eq!(update.version, "9.9.9");
    assert_eq!(update.url, format!("{DOWNLOADS}FlexWeek-x86_64.AppImage"));
    assert_eq!(
        update.checksum_url,
        format!("{DOWNLOADS}FlexWeek-x86_64.AppImage.sha256")
    );
    assert_eq!(update.notes, "");
}

#[test]
fn test_a_redirect_anywhere_else_is_not_a_release() {
    for location in [
        "",
        "https://github.com/j0nsh1n/FlexWeek/releases",
        "https://github.com/someone-else/FlexWeek/releases/tag/v9.9.9",
        "https://github.com/j0nsh1n/FlexWeek/releases/tag/v9.9.9/../../evil",
        "https://github.com/j0nsh1n/FlexWeek/releases/tag/latest",
        "http://github.com/j0nsh1n/FlexWeek/releases/tag/v9.9.9",
    ] {
        assert_eq!(release_from_page(location), None, "{location:?}");
    }
}
