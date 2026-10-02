//! Scratch databases live under `target/store-tests`, same as the crate's own tests.
#![allow(dead_code)]

use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

pub fn scratch(name: &str) -> PathBuf {
    let folder = Path::new(env!("CARGO_MANIFEST_DIR")).join("../target/store-tests");
    std::fs::create_dir_all(&folder).unwrap();
    let path = folder.join(format!("{name}-{}.sqlite", std::process::id()));
    let _ = std::fs::remove_file(&path);
    path
}

/// `hashlib.sha256(f"{week_start}:{source_id}".encode()).hexdigest()[:32]`, not the engine helper.
pub fn assignment_id(week_start: &str, source_id: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(format!("{week_start}:{source_id}").as_bytes());
    let hex: String = hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    format!("a-{}", &hex[..32])
}
