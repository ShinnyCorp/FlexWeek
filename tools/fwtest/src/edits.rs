//! A mutation's backup is on disk before the source file changes.
//! `fwtest clean` puts the backup back if the run that edited the file is gone.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::job;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct EditRecord {
    pub file: PathBuf,
    pub backup: PathBuf,
    pub case: String,
}

pub struct Guard {
    source: PathBuf,
    backup: PathBuf,
    record: PathBuf,
    armed: bool,
}

impl Guard {
    pub fn arm(root: &Path, source: &Path, case: &str) -> io::Result<Self> {
        let dir = root.join("edits");
        fs::create_dir_all(&dir)?;
        let key = file_key(source);
        let backup = dir.join(format!("{key}.backup"));
        let record_path = dir.join(format!("{key}.json"));
        fs::copy(source, &backup)?;
        let record = EditRecord {
            file: source.to_path_buf(),
            backup: backup.clone(),
            case: case.to_string(),
        };
        let tmp = record_path.with_extension("json.tmp");
        fs::write(
            &tmp,
            serde_json::to_vec_pretty(&record).map_err(io::Error::other)?,
        )?;
        fs::rename(&tmp, &record_path)?;
        Ok(Self {
            source: source.to_path_buf(),
            backup,
            record: record_path,
            armed: true,
        })
    }
}

impl Drop for Guard {
    fn drop(&mut self) {
        if !self.armed {
            return;
        }
        if fs::copy(&self.backup, &self.source).is_ok() {
            delete_bytecode(&self.source);
            let _ = fs::remove_file(&self.record);
            let _ = fs::remove_file(&self.backup);
        }
    }
}

pub fn delete_bytecode(source: &Path) {
    let Some(parent) = source.parent() else {
        return;
    };
    let Some(stem) = source.file_stem().and_then(|stem| stem.to_str()) else {
        return;
    };
    let cache = parent.join("__pycache__");
    let Ok(entries) = fs::read_dir(cache) else {
        return;
    };
    let prefix = format!("{stem}.");
    for entry in entries.flatten() {
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if name.starts_with(&prefix) && name.ends_with(".pyc") {
            let _ = fs::remove_file(entry.path());
        }
    }
}

/// Put back edits only when no job is still running. A live mutate owns its file.
pub fn restore_finished(root: &Path) -> io::Result<usize> {
    if live_job(root)? {
        return Ok(0);
    }
    let dir = root.join("edits");
    if !dir.exists() {
        return Ok(0);
    }
    let mut restored = 0;
    for entry in fs::read_dir(&dir)? {
        let path = entry?.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let text = fs::read_to_string(&path)?;
        let record: EditRecord = serde_json::from_str(&text).map_err(io::Error::other)?;
        fs::copy(&record.backup, &record.file)?;
        delete_bytecode(&record.file);
        fs::remove_file(&path)?;
        let _ = fs::remove_file(&record.backup);
        restored += 1;
    }
    Ok(restored)
}

fn live_job(root: &Path) -> io::Result<bool> {
    for path in job::list_job_files(root)? {
        let job = job::load_job_file(&path)?;
        if job::owner_is_live(&job)? {
            return Ok(true);
        }
    }
    Ok(false)
}

fn file_key(path: &Path) -> String {
    let mut hash = 0xcbf29ce484222325u64;
    for byte in path.to_string_lossy().as_bytes() {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("{hash:016x}")
}
