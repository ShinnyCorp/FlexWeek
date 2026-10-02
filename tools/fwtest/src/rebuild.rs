//! Install the Rust engine into the checkout's virtualenv.
//!
//! The mutate run rebuilds inside a contained job. `fwtest clean`, and the
//! clean that opens every command, rebuild a module a killed run left behind
//! with [`run_marked`].

use std::io::{self, Error};
use std::path::Path;
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use crate::edits::EngineRebuild;

pub const DEFAULT_TIMEOUT_SECS: u64 = 1200;

pub struct EngineBuild {
    pub enabled: bool,
    /// Base command for a mutated build. The default includes `--features audit`.
    pub command: Vec<String>,
    /// Command stored for the clean rebuild. It matches `command` unless a probe
    /// of the installed module finds that the audit functions are absent.
    pub clean_command: Vec<String>,
    /// True only for the default command. A caller-supplied command is used as given.
    pub match_installed_audit: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum InstalledAudit {
    Present,
    Absent,
    Unknown,
}

pub const AUDIT_PROBE: &str = "\
import flexweek_engine
print('yes' if hasattr(flexweek_engine, 'panic_probe') else 'no')
";

pub fn resolve(
    checkout: &Path,
    cli: Option<&str>,
    no_rebuild: bool,
) -> Result<EngineBuild, String> {
    if no_rebuild || env_flag_off("FWTEST_ENGINE_REBUILD") {
        return Ok(disabled_build());
    }
    let text = match cli {
        Some(text) => Some(text.to_string()),
        None => std::env::var("FWTEST_ENGINE_BUILD")
            .ok()
            .filter(|value| !value.is_empty()),
    };
    let Some(text) = text else {
        return Ok(default_build(checkout));
    };
    if text == "off" {
        return Ok(disabled_build());
    }
    Ok(fixed_build(split_command(&text)?))
}

fn disabled_build() -> EngineBuild {
    EngineBuild {
        enabled: false,
        command: Vec::new(),
        clean_command: Vec::new(),
        match_installed_audit: false,
    }
}

fn fixed_build(command: Vec<String>) -> EngineBuild {
    EngineBuild {
        enabled: true,
        clean_command: command.clone(),
        command,
        match_installed_audit: false,
    }
}

fn default_build(checkout: &Path) -> EngineBuild {
    let command = default_command(checkout);
    EngineBuild {
        enabled: true,
        clean_command: command.clone(),
        command,
        match_installed_audit: true,
    }
}

pub fn default_command(checkout: &Path) -> Vec<String> {
    vec![
        checkout
            .join(".venv/bin/maturin")
            .to_string_lossy()
            .into_owned(),
        "develop".to_string(),
        "--release".to_string(),
        "--manifest-path".to_string(),
        "engine/py/Cargo.toml".to_string(),
        "--features".to_string(),
        "audit".to_string(),
    ]
}

/// Drop `audit` from every `--features` value. Other features stay.
pub fn without_audit(command: &[String]) -> Vec<String> {
    let mut out = Vec::new();
    let mut index = 0;
    while index < command.len() {
        if command[index] == "--features" && index + 1 < command.len() {
            let names: Vec<&str> = command[index + 1]
                .split(',')
                .filter(|name| !name.is_empty() && *name != "audit")
                .collect();
            if !names.is_empty() {
                out.push("--features".to_string());
                out.push(names.join(","));
            }
            index += 2;
            continue;
        }
        out.push(command[index].clone());
        index += 1;
    }
    out
}

/// The last exact `yes` or `no` line wins. Any other output, or a non-zero
/// exit, means the probe could not be read.
pub fn classify_audit_probe(code: u8, output: &str) -> InstalledAudit {
    if code != 0 {
        return InstalledAudit::Unknown;
    }
    let mut found = InstalledAudit::Unknown;
    for line in output.lines() {
        match line.trim() {
            "yes" => found = InstalledAudit::Present,
            "no" => found = InstalledAudit::Absent,
            _ => {}
        }
    }
    found
}

/// Case-specific features are added for the mutated build only.
/// They join an existing `--features` list, so the default `audit` stays.
/// The clean rebuild uses the command without the case's extra features.
pub fn with_features(command: &[String], features: &[String]) -> Vec<String> {
    if features.is_empty() {
        return command.to_vec();
    }
    let mut command = command.to_vec();
    if let Some(slot) = command.iter().position(|arg| arg == "--features")
        && slot + 1 < command.len()
    {
        let mut names: Vec<String> = command[slot + 1]
            .split(',')
            .filter(|name| !name.is_empty())
            .map(str::to_string)
            .collect();
        for feature in features {
            if !names.iter().any(|name| name == feature) {
                names.push(feature.clone());
            }
        }
        command[slot + 1] = names.join(",");
        return command;
    }
    command.push("--features".to_string());
    command.push(features.join(","));
    command
}

pub fn build_timeout() -> u64 {
    std::env::var("FWTEST_ENGINE_BUILD_TIMEOUT")
        .ok()
        .and_then(|value| value.parse().ok())
        .filter(|value| *value > 0)
        .unwrap_or(DEFAULT_TIMEOUT_SECS)
}

pub fn run_marked(mark: &EngineRebuild) -> io::Result<()> {
    if mark.command.is_empty() {
        return Err(Error::other("engine rebuild command is empty"));
    }
    let mut command = Command::new("nice");
    command.arg("-n").arg("19");
    command.args(&mark.command);
    command
        .current_dir(&mark.checkout)
        .env("FLEXWEEK_SILENT", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());
    let mut child = command.spawn()?;
    let started = Instant::now();
    let limit = Duration::from_secs(build_timeout());
    loop {
        if let Some(status) = child.try_wait()? {
            if status.success() {
                return Ok(());
            }
            return Err(Error::other(format!(
                "engine rebuild failed with {}",
                status.code().unwrap_or(-1)
            )));
        }
        if started.elapsed() >= limit {
            let _ = child.kill();
            let _ = child.wait();
            return Err(Error::other("engine rebuild timed out"));
        }
        thread::sleep(Duration::from_millis(200));
    }
}

fn env_flag_off(name: &str) -> bool {
    matches!(
        std::env::var(name).ok().as_deref(),
        Some("0" | "off" | "false")
    )
}

pub fn split_command(text: &str) -> Result<Vec<String>, String> {
    let mut words = Vec::new();
    let mut current = String::new();
    let mut chars = text.chars().peekable();
    let mut in_single = false;
    let mut in_double = false;
    while let Some(ch) = chars.next() {
        match ch {
            '\'' if !in_double => in_single = !in_single,
            '"' if !in_single => in_double = !in_double,
            '\\' if !in_single => {
                if let Some(next) = chars.next() {
                    current.push(next);
                }
            }
            c if c.is_whitespace() && !in_single && !in_double => {
                if !current.is_empty() {
                    words.push(std::mem::take(&mut current));
                }
            }
            c => current.push(c),
        }
    }
    if in_single || in_double {
        return Err("unclosed quote in engine build command".to_string());
    }
    if !current.is_empty() {
        words.push(current);
    }
    if words.is_empty() {
        return Err("engine build command is empty".to_string());
    }
    Ok(words)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quotes_and_spaces_split_into_words() {
        let words =
            split_command(r#"maturin develop --manifest-path "engine/py/Cargo.toml""#).unwrap();
        assert_eq!(
            words,
            vec![
                "maturin",
                "develop",
                "--manifest-path",
                "engine/py/Cargo.toml"
            ]
        );
    }

    #[test]
    fn an_unclosed_quote_is_rejected() {
        assert!(split_command("maturin \"develop").is_err());
    }

    #[test]
    fn the_default_build_asks_for_audit() {
        let command = default_command(Path::new("/work"));
        assert_eq!(
            command[command.len() - 2..],
            ["--features".to_string(), "audit".to_string()]
        );
    }

    #[test]
    fn without_audit_drops_only_that_feature() {
        let command = vec![
            "maturin".to_string(),
            "--features".to_string(),
            "audit,extra".to_string(),
        ];
        assert_eq!(
            without_audit(&command),
            vec![
                "maturin".to_string(),
                "--features".to_string(),
                "extra".to_string()
            ]
        );
        assert_eq!(
            without_audit(&["maturin".into(), "--features".into(), "audit".into()]),
            vec!["maturin".to_string()]
        );
    }

    #[test]
    fn a_probe_that_cannot_be_read_is_unknown() {
        assert_eq!(classify_audit_probe(0, "yes\n"), InstalledAudit::Present);
        assert_eq!(classify_audit_probe(0, "no\n"), InstalledAudit::Absent);
        assert_eq!(classify_audit_probe(1, "yes\n"), InstalledAudit::Unknown);
        assert_eq!(
            classify_audit_probe(0, "warning\n"),
            InstalledAudit::Unknown
        );
    }
}
