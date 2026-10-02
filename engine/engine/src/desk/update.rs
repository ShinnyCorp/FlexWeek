//! Update checks from `desktop/native/update.py`.

use regex::Regex;
use std::sync::LazyLock;

use crate::error::{EngineError, EngineResult};

pub const RELEASES_URL: &str = "https://api.github.com/repos/j0nsh1n/FlexWeek/releases/latest";
pub const RELEASE_PAGE: &str = "https://github.com/j0nsh1n/FlexWeek/releases/latest";
pub const RELEASE_TAG_PAGE: &str = "https://github.com/j0nsh1n/FlexWeek/releases/tag/";
pub const RELEASE_DOWNLOAD: &str = "https://github.com/j0nsh1n/FlexWeek/releases/download/";
pub const CHECK_EVERY_HOURS: i64 = 24;

pub const WINDOWS_SETUP: &str = "FlexWeek-Windows-x64-Setup.exe";
pub const WINDOWS_MSI: &str = "FlexWeek-Windows-x64.msi";
pub const LINUX_TARBALL: &str = "FlexWeek-Linux-x86_64.tar.gz";
pub const LINUX_APPIMAGE: &str = "FlexWeek-x86_64.AppImage";

fn tag_pattern() -> &'static Regex {
    // Python `re.fullmatch`: the whole tag, not a version buried in `v9.9.9/../../evil`.
    static PATTERN: LazyLock<Regex> =
        LazyLock::new(|| Regex::new(r"\Av?[0-9]+(?:\.[0-9]+){1,3}\z").expect("tag pattern"));
    &PATTERN
}

pub fn parse_version(value: &str) -> Option<Vec<i64>> {
    let text = value.trim().strip_prefix('v').unwrap_or(value.trim());
    let parts: Vec<&str> = text.split('.').collect();
    if parts.is_empty()
        || parts.len() > 4
        || !parts.iter().all(|p| p.chars().all(|c| c.is_ascii_digit()))
    {
        return None;
    }
    parts.iter().map(|p| p.parse().ok()).collect()
}

pub fn is_newer(candidate: &str, current: &str) -> bool {
    let one = parse_version(candidate);
    let two = parse_version(current);
    let (Some(one), Some(two)) = (one, two) else {
        return false;
    };
    let width = one.len().max(two.len());
    let mut a = one;
    let mut b = two;
    while a.len() < width {
        a.push(0);
    }
    while b.len() < width {
        b.push(0);
    }
    a > b
}

pub fn install_kind(
    platform: Option<&str>,
    appimage: Option<&str>,
    appdir: Option<&str>,
    executable: Option<&str>,
) -> &'static str {
    let system = platform.unwrap_or("");
    if system.starts_with("win") {
        return "windows";
    }
    let image = appimage.unwrap_or("");
    let mount = appdir.unwrap_or("");
    let running = executable.unwrap_or("");
    if !image.is_empty()
        && !mount.is_empty()
        && !running.is_empty()
        && path_is_relative_to(running, mount)
    {
        return "appimage";
    }
    "tarball"
}

fn path_is_relative_to(path: &str, base: &str) -> bool {
    let path = std::path::Path::new(path);
    let base = std::path::Path::new(base);
    match (path.canonicalize(), base.canonicalize()) {
        (Ok(path), Ok(base)) => path.starts_with(base),
        // A path that is not on disk yet still counts. Python's Path.resolve
        // does not require the file to exist.
        _ => logical_path(path).starts_with(logical_path(base)),
    }
}

fn logical_path(path: &std::path::Path) -> std::path::PathBuf {
    let mut out = std::path::PathBuf::new();
    for part in path.components() {
        match part {
            std::path::Component::CurDir => {}
            std::path::Component::ParentDir => {
                out.pop();
            }
            other => out.push(other.as_os_str()),
        }
    }
    out
}

pub fn asset_name(kind: &str) -> Option<&'static str> {
    match kind {
        "windows" => Some(WINDOWS_SETUP),
        "appimage" => Some(LINUX_APPIMAGE),
        "tarball" => Some(LINUX_TARBALL),
        _ => None,
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Update {
    pub version: String,
    pub asset: String,
    pub url: String,
    pub checksum_url: String,
    pub notes: String,
}

pub fn available(
    release: &serde_json::Value,
    kind: &str,
    current: &str,
) -> EngineResult<Option<Update>> {
    use crate::desk::pyops::get;
    use crate::stored::truthy;
    if !matches!(release, serde_json::Value::Object(_)) {
        return Ok(None);
    }
    if truthy(get(release, "draft")?) || truthy(get(release, "prerelease")?) {
        return Ok(None);
    }
    let Some(tag) = get(release, "tag_name")?.and_then(|v| v.as_str()) else {
        return Ok(None);
    };
    if !is_newer(tag, current) {
        return Ok(None);
    }
    let Some(assets) = get(release, "assets")?.and_then(|v| v.as_array()) else {
        return Ok(None);
    };
    let wanted = asset_name(kind).ok_or_else(|| EngineError::key(kind))?;
    let mut by_name: Vec<(String, Option<serde_json::Value>)> = Vec::new();
    for item in assets {
        let serde_json::Value::Object(obj) = item else {
            continue;
        };
        let Some(name) = obj.get("name").and_then(|v| v.as_str()) else {
            continue;
        };
        let url = obj.get("browser_download_url").cloned();
        match by_name.iter_mut().find(|(known, _)| known == name) {
            Some(entry) => entry.1 = url,
            None => by_name.push((name.to_string(), url)),
        }
    }
    let found = |name: &str| -> Option<String> {
        by_name
            .iter()
            .find(|(known, _)| known == name)
            .and_then(|(_, url)| url.as_ref())
            .and_then(|url| url.as_str())
            .map(str::to_string)
    };
    let (Some(url), Some(checksum_url)) = (found(wanted), found(&format!("{wanted}.sha256")))
    else {
        return Ok(None);
    };
    let notes = get(release, "body")?
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    Ok(Some(Update {
        version: tag.strip_prefix('v').unwrap_or(tag).to_string(),
        asset: wanted.to_string(),
        url,
        checksum_url,
        notes,
    }))
}

pub fn due_for_check(settings: &serde_json::Value, now_ms: i64) -> EngineResult<bool> {
    use crate::desk::pyops::{get, or_default, to_int};
    use crate::stored::truthy;
    if let Some(check) = get(settings, "check")?
        && !truthy(Some(check))
    {
        return Ok(false);
    }
    let last = to_int(&or_default(get(settings, "last_ms")?, serde_json::json!(0)))?;
    let now = i128::from(now_ms);
    Ok(last > now || now - last >= i128::from(CHECK_EVERY_HOURS) * 3_600_000)
}

pub fn release_from_page(location: &str) -> Option<serde_json::Value> {
    if !location.starts_with(RELEASE_TAG_PAGE) {
        return None;
    }
    let tag = location.strip_prefix(RELEASE_TAG_PAGE)?;
    if !tag_pattern().is_match(tag) {
        return None;
    }
    let names = [WINDOWS_SETUP, WINDOWS_MSI, LINUX_TARBALL, LINUX_APPIMAGE];
    let mut assets = Vec::new();
    for base in names {
        for name in [base.to_string(), format!("{base}.sha256")] {
            assets.push(serde_json::json!({
                "name": name,
                "browser_download_url": format!("{RELEASE_DOWNLOAD}{tag}/{name}"),
            }));
        }
    }
    Some(serde_json::json!({
        "tag_name": tag,
        "assets": assets,
        "body": "",
    }))
}

pub fn expected_digest(checksum_text: &str, asset: &str) -> Option<String> {
    for line in checksum_text.lines() {
        let parts: Vec<&str> = line.split_whitespace().collect();
        if parts.len() != 2 || parts[0].len() != 64 {
            continue;
        }
        if parts[1].trim_start_matches('*') == asset {
            return Some(parts[0].to_lowercase());
        }
    }
    None
}

pub fn verified(payload: &[u8], digest: Option<&str>) -> bool {
    !digest.is_none_or(|text| text.is_empty() || text.chars().count() != 64)
        && digest.is_some_and(|text| sha256_hex(payload) == text.to_lowercase())
}

pub fn sha256_hex_for_migration(text: &str) -> String {
    sha256_hex(text.as_bytes())
}

fn sha256_hex(data: &[u8]) -> String {
    let hash = sha256::hash(data);
    hash.iter().map(|byte| format!("{byte:02x}")).collect()
}

pub fn sanitize_updates(raw: &serde_json::Value) -> serde_json::Map<String, serde_json::Value> {
    use crate::desk::pyops::is_int;
    use serde_json::{Value, json};
    let mut clean = serde_json::Map::new();
    clean.insert("check".into(), json!(true));
    clean.insert("last_ms".into(), json!(0));
    clean.insert("skip".into(), json!(""));
    let Value::Object(raw) = raw else {
        return clean;
    };
    if raw.get("check") == Some(&json!(false)) {
        clean.insert("check".into(), json!(false));
    }
    if let Some(last) = raw.get("last_ms")
        && is_int(last)
        && let Ok(found) = crate::desk::pyops::to_int(last)
        && (0..=4_102_444_800_000).contains(&found)
    {
        clean.insert("last_ms".into(), last.clone());
    }
    if let Some(Value::String(skip)) = raw.get("skip")
        && skip.chars().count() <= 32
    {
        clean.insert("skip".into(), json!(skip));
    }
    clean
}

mod sha256 {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];

    pub fn hash(data: &[u8]) -> [u8; 32] {
        let mut h = [
            0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
            0x5be0cd19,
        ];
        let bit_len = (data.len() as u64) * 8;
        let mut msg = data.to_vec();
        msg.push(0x80);
        while (msg.len() % 64) != 56 {
            msg.push(0);
        }
        msg.extend_from_slice(&bit_len.to_be_bytes());
        for chunk in msg.chunks(64) {
            let mut w = [0u32; 64];
            for (i, word) in chunk.chunks(4).enumerate().take(16) {
                w[i] = u32::from_be_bytes([word[0], word[1], word[2], word[3]]);
            }
            for i in 16..64 {
                let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
                let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
                w[i] = w[i - 16]
                    .wrapping_add(s0)
                    .wrapping_add(w[i - 7])
                    .wrapping_add(s1);
            }
            let (mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut hh): (
                u32,
                u32,
                u32,
                u32,
                u32,
                u32,
                u32,
                u32,
            ) = (h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7]);
            for i in 0..64 {
                let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
                let ch = (e & f) ^ ((!e) & g);
                let temp1 = hh
                    .wrapping_add(s1)
                    .wrapping_add(ch)
                    .wrapping_add(K[i])
                    .wrapping_add(w[i]);
                let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
                let maj = (a & b) ^ (a & c) ^ (b & c);
                let temp2 = s0.wrapping_add(maj);
                hh = g;
                g = f;
                f = e;
                e = d.wrapping_add(temp1);
                d = c;
                c = b;
                b = a;
                a = temp1.wrapping_add(temp2);
            }
            h[0] = h[0].wrapping_add(a);
            h[1] = h[1].wrapping_add(b);
            h[2] = h[2].wrapping_add(c);
            h[3] = h[3].wrapping_add(d);
            h[4] = h[4].wrapping_add(e);
            h[5] = h[5].wrapping_add(f);
            h[6] = h[6].wrapping_add(g);
            h[7] = h[7].wrapping_add(hh);
        }
        let mut out = [0u8; 32];
        for (i, word) in h.iter().enumerate() {
            out[i * 4..i * 4 + 4].copy_from_slice(&word.to_be_bytes());
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::{install_kind, is_newer, parse_version};

    #[test]
    fn parse_version_matches_desktop_tests() {
        for value in ["0.14.0", "v0.14.0", "1.2.3", "0.13.0.1"] {
            assert!(parse_version(value).is_some());
        }
        for value in [
            "",
            "v",
            "1.2.3-rc1",
            "latest",
            "1.2.x",
            "2026-09-20",
            "1.2.3.4.5",
        ] {
            assert!(parse_version(value).is_none());
        }
    }

    #[test]
    fn is_newer_orders_by_number_not_text() {
        assert!(is_newer("0.14.0", "0.13.0"));
        assert!(is_newer("v0.14.0", "0.13.0"));
        assert!(is_newer("0.13.1", "0.13.0"));
        assert!(is_newer("1.0.0", "0.13.0"));
        assert!(!is_newer("0.13.0", "0.13.0"));
        assert!(!is_newer("0.12.9", "0.13.0"));
        assert!(!is_newer("0.9.0", "0.13.0"));
        assert!(!is_newer("0.2.0", "0.13.0"));
        assert!(!is_newer("", "0.13.0"));
        assert!(!is_newer("1.2.3-rc1", "0.13.0"));
    }

    #[test]
    fn install_kind_ignores_the_process_environment() {
        let mount = std::env::temp_dir();
        let image = mount.join("flexweek-appimage-probe");
        let exe = mount.join("flexweek-probe-bin");
        std::fs::write(&image, b"x").unwrap();
        std::fs::write(&exe, b"x").unwrap();
        // set_var is unsafe in this toolchain because another thread can read the
        // environment at the same time. This test is that reader, on one thread.
        unsafe {
            std::env::set_var("APPIMAGE", &image);
            std::env::set_var("APPDIR", &mount);
        }
        let kind = install_kind(Some("linux"), None, None, Some(exe.to_str().unwrap()));
        unsafe {
            std::env::remove_var("APPIMAGE");
            std::env::remove_var("APPDIR");
        }
        let _ = std::fs::remove_file(&image);
        let _ = std::fs::remove_file(&exe);
        assert_eq!(kind, "tarball");
    }
}
