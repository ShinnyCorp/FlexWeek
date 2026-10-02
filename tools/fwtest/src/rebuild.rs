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
    pub command: Vec<String>,
}

pub fn resolve(
    checkout: &Path,
    cli: Option<&str>,
    no_rebuild: bool,
) -> Result<EngineBuild, String> {
    if no_rebuild || env_flag_off("FWTEST_ENGINE_REBUILD") {
        return Ok(EngineBuild {
            enabled: false,
            command: Vec::new(),
        });
    }
    let text = match cli {
        Some(text) => Some(text.to_string()),
        None => std::env::var("FWTEST_ENGINE_BUILD")
            .ok()
            .filter(|value| !value.is_empty()),
    };
    let Some(text) = text else {
        return Ok(EngineBuild {
            enabled: true,
            command: default_command(checkout),
        });
    };
    if text == "off" {
        return Ok(EngineBuild {
            enabled: false,
            command: Vec::new(),
        });
    }
    Ok(EngineBuild {
        enabled: true,
        command: split_command(&text)?,
    })
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
    ]
}

/// Case-specific features are added for the mutated build only.
/// The clean rebuild uses the command without them.
pub fn with_features(command: &[String], features: &[String]) -> Vec<String> {
    if features.is_empty() {
        return command.to_vec();
    }
    let mut command = command.to_vec();
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
}
