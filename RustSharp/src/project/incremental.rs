//! Incremental Build Cache for RustSharp (`rsharpc`).
//!
//! Provides SHA-256 file fingerprinting, cache persistence, and sub-millisecond
//! skip-checks for unchanged modules.

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

/// Computes pure-Rust standard SHA-256 hash formatted as a 64-character lowercase hex string.
#[allow(clippy::needless_range_loop, clippy::chunks_exact_to_as_chunks)]
pub fn compute_sha256(data: &[u8]) -> String {
    let mut state = [
        0x6a09e667u32,
        0xbb67ae85u32,
        0x3c6ef372u32,
        0xa54ff53au32,
        0x510e527fu32,
        0x9b05688cu32,
        0x1f83d9abu32,
        0x5be0cd19u32,
    ];

    let bit_len = (data.len() as u64).wrapping_mul(8);
    let mut msg = data.to_vec();
    msg.push(0x80);
    while (msg.len() % 64) != 56 {
        msg.push(0x00);
    }
    msg.extend_from_slice(&bit_len.to_be_bytes());

    let k: [u32; 64] = [
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

    for chunk in msg.chunks_exact(64) {
        let mut w = [0u32; 64];
        for i in 0..16 {
            let offset = i * 4;
            w[i] = u32::from_be_bytes([
                chunk[offset],
                chunk[offset + 1],
                chunk[offset + 2],
                chunk[offset + 3],
            ]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16]
                .wrapping_add(s0)
                .wrapping_add(w[i - 7])
                .wrapping_add(s1);
        }

        let mut a = state[0];
        let mut b = state[1];
        let mut c = state[2];
        let mut d = state[3];
        let mut e = state[4];
        let mut f = state[5];
        let mut g = state[6];
        let mut h = state[7];

        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let temp1 = h
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(k[i])
                .wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let temp2 = s0.wrapping_add(maj);

            h = g;
            g = f;
            f = e;
            e = d.wrapping_add(temp1);
            d = c;
            c = b;
            b = a;
            a = temp1.wrapping_add(temp2);
        }

        state[0] = state[0].wrapping_add(a);
        state[1] = state[1].wrapping_add(b);
        state[2] = state[2].wrapping_add(c);
        state[3] = state[3].wrapping_add(d);
        state[4] = state[4].wrapping_add(e);
        state[5] = state[5].wrapping_add(f);
        state[6] = state[6].wrapping_add(g);
        state[7] = state[7].wrapping_add(h);
    }

    let mut hex = String::with_capacity(64);
    for val in state {
        hex.push_str(&format!("{:08x}", val));
    }
    hex
}

/// Represents the cached state of a project compilation.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct IncrementalBuildCache {
    /// Map of input relative path (e.g. `"Models/Order.rsharp"`) -> SHA-256 hash.
    pub file_hashes: BTreeMap<String, String>,
    /// Map of output relative path (e.g. `"src/models.rs"`) -> emitted Rust source code.
    pub emitted_modules: BTreeMap<String, String>,
    /// Synthesized Cargo.toml content.
    pub cargo_toml: String,
    /// Synthesized src/lib.rs content.
    pub lib_rs: String,
}

impl IncrementalBuildCache {
    /// Loads cached compilation state from a JSON cache file.
    pub fn load_from_disk(path: &Path) -> Option<Self> {
        let content = fs::read_to_string(path).ok()?;
        Self::deserialize_simple_json(&content)
    }

    /// Persists cached compilation state to disk.
    pub fn save_to_disk(&self, path: &Path) -> Result<(), String> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|e| format!("Failed to create cache dir: {}", e))?;
        }
        let serialized = self.serialize_simple_json();
        fs::write(path, serialized)
            .map_err(|e| format!("Failed to write cache file '{}': {}", path.display(), e))
    }

    /// Checks if all current input files match the cached SHA-256 hashes.
    pub fn is_up_to_date(&self, current_inputs: &[(&str, &str)]) -> bool {
        if self.file_hashes.len() != current_inputs.len() {
            return false;
        }

        for (path, content) in current_inputs {
            let current_hash = compute_sha256(content.as_bytes());
            if self.file_hashes.get(*path) != Some(&current_hash) {
                return false;
            }
        }

        true
    }

    /// Updates cache file hashes for a given set of input files.
    pub fn record_inputs(&mut self, inputs: &[(&str, &str)]) {
        self.file_hashes.clear();
        for (path, content) in inputs {
            let hash = compute_sha256(content.as_bytes());
            self.file_hashes.insert(path.to_string(), hash);
        }
    }

    fn serialize_simple_json(&self) -> String {
        let mut out = String::from("{\n");

        out.push_str("  \"file_hashes\": {\n");
        let hash_entries: Vec<String> = self
            .file_hashes
            .iter()
            .map(|(k, v)| format!("    \"{}\": \"{}\"", escape_json(k), escape_json(v)))
            .collect();
        out.push_str(&hash_entries.join(",\n"));
        out.push_str("\n  },\n");

        out.push_str("  \"emitted_modules\": {\n");
        let mod_entries: Vec<String> = self
            .emitted_modules
            .iter()
            .map(|(k, v)| format!("    \"{}\": \"{}\"", escape_json(k), escape_json(v)))
            .collect();
        out.push_str(&mod_entries.join(",\n"));
        out.push_str("\n  },\n");

        out.push_str(&format!(
            "  \"cargo_toml\": \"{}\",\n",
            escape_json(&self.cargo_toml)
        ));
        out.push_str(&format!(
            "  \"lib_rs\": \"{}\"\n",
            escape_json(&self.lib_rs)
        ));
        out.push_str("}\n");

        out
    }

    fn deserialize_simple_json(json: &str) -> Option<Self> {
        let mut cache = Self::default();

        if let Some(hashes_start) = json.find("\"file_hashes\":") {
            let rest = &json[hashes_start..];
            if let Some(open) = rest.find('{') {
                if let Some(close) = rest[open..].find('}') {
                    let block = &rest[open + 1..open + close];
                    for line in block.lines() {
                        if let Some((k, v)) = parse_json_key_value(line) {
                            cache.file_hashes.insert(k, v);
                        }
                    }
                }
            }
        }

        if let Some(mods_start) = json.find("\"emitted_modules\":") {
            let rest = &json[mods_start..];
            if let Some(open) = rest.find('{') {
                if let Some(close) = rest[open..].find('}') {
                    let block = &rest[open + 1..open + close];
                    for line in block.lines() {
                        if let Some((k, v)) = parse_json_key_value(line) {
                            cache.emitted_modules.insert(k, v);
                        }
                    }
                }
            }
        }

        if let Some(cargo_start) = json.find("\"cargo_toml\":") {
            let rest = &json[cargo_start..];
            if let Some((_, v)) = parse_json_key_value(rest.lines().next().unwrap_or("")) {
                cache.cargo_toml = v;
            }
        }

        if let Some(lib_start) = json.find("\"lib_rs\":") {
            let rest = &json[lib_start..];
            if let Some((_, v)) = parse_json_key_value(rest.lines().next().unwrap_or("")) {
                cache.lib_rs = v;
            }
        }

        Some(cache)
    }
}

fn escape_json(s: &str) -> String {
    s.replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
        .replace('\t', "\\t")
}

fn unescape_json(s: &str) -> String {
    s.replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace("\\\"", "\"")
        .replace("\\\\", "\\")
}

fn parse_json_key_value(line: &str) -> Option<(String, String)> {
    let trimmed = line.trim().trim_end_matches(',');
    let (k_part, v_part) = trimmed.split_once(':')?;
    let k = k_part.trim().trim_matches('"');
    let v = v_part.trim().trim_matches('"');
    if k.is_empty() {
        return None;
    }
    Some((unescape_json(k), unescape_json(v)))
}
