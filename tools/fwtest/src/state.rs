//! On-disk state lives in `~/.flexweek-ui-harness/fwtest/`, outside every checkout.

use std::path::PathBuf;

pub fn harness_root() -> Result<PathBuf, String> {
    let home = std::env::var_os("HOME").filter(|value| !value.is_empty());
    let Some(home) = home else {
        return Err("HOME is not set, so fwtest has nowhere to keep job records".to_string());
    };
    Ok(PathBuf::from(home).join(".flexweek-ui-harness/fwtest"))
}
