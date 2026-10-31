use crate::diagnostics::SourceSpan;

/// Single bidirectional line mapping between an emitted `.rs` module line
/// and its originating `.rsharp` source file, line, and column.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SourceMapEntry {
    pub rs_file: String,
    pub rs_line: u32,
    pub rsharp_file: String,
    pub rsharp_line: u32,
    pub rsharp_col: u32,
}

/// Tracks bidirectional `.rs` <-> `.rsharp` source line mappings for a synthesized Rust module
/// and translates `rustc` fallback diagnostics back into original `.rsharp` coordinates.
#[derive(Clone, Debug, Default)]
pub struct RustSourceMap {
    pub rs_file: String,
    pub entries: Vec<SourceMapEntry>,
}

impl RustSourceMap {
    pub fn new(rs_file: impl Into<String>) -> Self {
        Self {
            rs_file: rs_file.into(),
            entries: Vec::new(),
        }
    }

    pub fn record(&mut self, rs_line: u32, span: &SourceSpan) {
        if span.filename.is_empty() || span.start_line == 0 {
            return;
        }
        self.entries.push(SourceMapEntry {
            rs_file: self.rs_file.clone(),
            rs_line,
            rsharp_file: span.filename.clone(),
            rsharp_line: span.start_line,
            rsharp_col: span.start_col,
        });
    }

    /// Resolves an emitted `.rs` line number back to the closest originating `.rsharp` location.
    pub fn lookup_rsharp_location(&self, rs_line: u32) -> Option<&SourceMapEntry> {
        self.entries
            .iter()
            .rev()
            .find(|e| e.rs_line <= rs_line)
            .or_else(|| self.entries.first())
    }

    /// Serializes the source map to a deterministic `.rsharp.map` text table.
    pub fn to_map_file_string(&self) -> String {
        let mut out = String::from("# RustSharp Bidirectional Source Map (.rsharp.map)\n");
        out.push_str("# rs_file:rs_line => rsharp_file:rsharp_line:rsharp_col\n");
        for entry in &self.entries {
            out.push_str(&format!(
                "{}:{} => {}:{}:{}\n",
                entry.rs_file,
                entry.rs_line,
                entry.rsharp_file,
                entry.rsharp_line,
                entry.rsharp_col
            ));
        }
        out
    }

    /// Rewrites `--> src/module.rs:line:col` spans in raw `rustc` output to point directly
    /// to the originating `.rsharp` file and line.
    pub fn translate_rustc_stderr(&self, stderr: &str) -> String {
        let mut translated = Vec::new();
        let needle = format!("--> {}:", self.rs_file);

        for line in stderr.lines() {
            let trimmed = line.trim_start();
            if let Some(rest) = trimmed.strip_prefix(&needle) {
                let mut parts = rest.split(':');
                if let Some(line_str) = parts.next() {
                    if let Ok(rs_line) = line_str.parse::<u32>() {
                        if let Some(mapped) = self.lookup_rsharp_location(rs_line) {
                            translated.push(format!(
                                "  --> {}:{}:{} (mapped from {}:{})",
                                mapped.rsharp_file,
                                mapped.rsharp_line,
                                mapped.rsharp_col,
                                self.rs_file,
                                rs_line
                            ));
                            continue;
                        }
                    }
                }
            }
            translated.push(line.to_string());
        }

        translated.join("\n")
    }
}
