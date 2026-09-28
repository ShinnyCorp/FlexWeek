//! Job records. The JSON shape is the contract's, parsed at the file boundary.

use std::fs::{self, File};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::identity::is_live_match;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProcRef {
    pub pid: i32,
    pub start_ticks: u64,
    #[serde(default)]
    pub comm: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct JobLimits {
    pub nice: i32,
    pub io: String,
    pub cpus: Vec<usize>,
    pub timeout: u64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct JobRecord {
    pub id: String,
    pub checkout: PathBuf,
    pub argv: Vec<String>,
    pub started: String,
    pub owner: ProcRef,
    pub processes: Vec<ProcRef>,
    pub limits: JobLimits,
    /// systemd user scope, when the job was started inside one.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub scope: Option<String>,
}

pub fn jobs_dir(root: &Path) -> PathBuf {
    root.join("jobs")
}

pub fn job_path(root: &Path, id: &str) -> Result<PathBuf, io::Error> {
    if !safe_id(id) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "job id must be a single path segment",
        ));
    }
    Ok(jobs_dir(root).join(format!("{id}.json")))
}

fn safe_id(id: &str) -> bool {
    !id.is_empty()
        && !id.starts_with('.')
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
}

pub fn save_job(root: &Path, job: &JobRecord) -> io::Result<()> {
    let path = job_path(root, &job.id)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("json.tmp");
    let mut file = File::create(&tmp)?;
    serde_json::to_writer_pretty(&mut file, job).map_err(io::Error::other)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    fs::rename(tmp, path)?;
    Ok(())
}

pub fn load_job_file(path: &Path) -> io::Result<JobRecord> {
    let text = fs::read_to_string(path)?;
    serde_json::from_str(&text).map_err(io::Error::other)
}

pub fn list_job_files(root: &Path) -> io::Result<Vec<PathBuf>> {
    let dir = jobs_dir(root);
    if !dir.exists() {
        return Ok(Vec::new());
    }
    let mut paths = Vec::new();
    for entry in fs::read_dir(&dir)? {
        let path = entry?.path();
        if path.extension().and_then(|ext| ext.to_str()) == Some("json") {
            paths.push(path);
        }
    }
    paths.sort();
    Ok(paths)
}

pub fn owner_is_live(job: &JobRecord) -> io::Result<bool> {
    is_live_match(job.owner.pid, job.owner.start_ticks)
}
