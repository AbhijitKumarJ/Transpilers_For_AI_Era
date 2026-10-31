//! File Watcher for `rsharpc watch`.
//!
//! Continuously polls `.rsharp`, `.d.rsharp`, `.rsproj`, and co-located `.rs` files
//! in a workspace, triggering instant incremental compilation upon changes.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::thread::sleep;
use std::time::{Duration, SystemTime};

use crate::compile_rsproj;
use crate::project::load_rsproj;

pub struct WorkspaceWatcher {
    rsproj_path: PathBuf,
    stdlib_dir: Option<PathBuf>,
    last_mod_times: BTreeMap<PathBuf, SystemTime>,
}

impl WorkspaceWatcher {
    pub fn new(rsproj_path: &Path, stdlib_dir: Option<&Path>) -> Self {
        Self {
            rsproj_path: rsproj_path.to_path_buf(),
            stdlib_dir: stdlib_dir.map(|p| p.to_path_buf()),
            last_mod_times: BTreeMap::new(),
        }
    }

    /// Runs one poll cycle. Returns `true` if changes were detected and recompilation ran.
    pub fn poll_once(&mut self, write_to_disk: bool) -> Result<bool, String> {
        let config = load_rsproj(&self.rsproj_path, self.stdlib_dir.as_deref())?;
        let mut inputs = config.all_rsharp_inputs();
        inputs.extend(config.colocated_rs_files.iter().cloned());
        inputs.push(self.rsproj_path.clone());

        let mut changed = false;
        let mut current_times = BTreeMap::new();

        for file in &inputs {
            if let Ok(metadata) = file.metadata() {
                if let Ok(mtime) = metadata.modified() {
                    current_times.insert(file.clone(), mtime);
                    if let Some(&prev) = self.last_mod_times.get(file) {
                        if mtime > prev {
                            changed = true;
                        }
                    } else if !self.last_mod_times.is_empty() {
                        changed = true;
                    }
                }
            }
        }

        if self.last_mod_times.is_empty() {
            // First run
            self.last_mod_times = current_times;
            self.recompile(write_to_disk)?;
            return Ok(true);
        }

        if changed {
            self.last_mod_times = current_times;
            self.recompile(write_to_disk)?;
            return Ok(true);
        }

        Ok(false)
    }

    fn recompile(&self, write_to_disk: bool) -> Result<(), String> {
        match compile_rsproj(&self.rsproj_path, self.stdlib_dir.as_deref(), write_to_disk) {
            Ok((cfg, synth, _diag)) => {
                println!(
                    "[{}] rsharpc: Recompiled '{}' ({} Rust modules generated).",
                    chrono_like_time(),
                    cfg.name,
                    synth.emitted_modules.len()
                );
                Ok(())
            }
            Err(e) => {
                eprintln!("[{}] rsharpc compilation error:\n{}", chrono_like_time(), e);
                Ok(())
            }
        }
    }

    /// Enters a continuous polling loop, checking for changes every 250 milliseconds.
    pub fn watch_loop(&mut self, write_to_disk: bool) -> ! {
        println!(
            "[{}] rsharpc watch: Monitoring '{}' for changes (Ctrl+C to stop)...",
            chrono_like_time(),
            self.rsproj_path.display()
        );

        let _ = self.poll_once(write_to_disk);

        loop {
            sleep(Duration::from_millis(250));
            let _ = self.poll_once(write_to_disk);
        }
    }
}

fn chrono_like_time() -> String {
    let now = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let sec = now % 60;
    let min = (now / 60) % 60;
    let hour = (now / 3600) % 24;
    format!("{:02}:{:02}:{:02}", hour, min, sec)
}
