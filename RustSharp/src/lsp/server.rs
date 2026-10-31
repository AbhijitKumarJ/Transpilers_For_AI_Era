//! Language Server Protocol (LSP) Server for RustSharp (`rsharpc lsp`).
//!
//! Provides in-memory document caching, project/workspace file discovery,
//! real-time diagnostic publication, type and borrow hover tooltips,
//! cross-file definition jumping, document symbols (outline), workspace symbols,
//! and contextual autocompletion.

use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use crate::analyze_workspace_with_preflight;
use crate::diagnostics::{Diagnostic, DiagnosticSeverity, SourceSpan};
use crate::frontend::ast::{
    BorrowMode, CompilationUnit, EffectSignature, FieldStorageMode, MemberDecl,
    PolymorphismStrategy, Stmt, TypeKind,
};
use crate::lsp::jsonrpc::{
    escape_json, extract_json_field, extract_json_string_field, JsonRpcMessage, JsonRpcTransport,
};
use crate::semantics::GlobalSymbolTable;

pub const EMBEDDED_STDLIB: &str = include_str!("../../stdlib/RustSharp.Core.d.rsharp");

/// In-memory analysis cache for currently open documents and discovered project files.
#[derive(Clone, Debug)]
pub struct AnalysisSnapshot {
    pub units: Vec<CompilationUnit>,
    pub symtab: GlobalSymbolTable,
    pub diagnostics: Vec<Diagnostic>,
}

/// The RustSharp Language Server.
pub struct LspServer {
    /// Workspace root URI / path (e.g. `file:///home/abhijit/...`)
    pub workspace_root: Option<String>,
    /// In-memory document storage: Document URI -> source text (authoritative latest text).
    pub documents: BTreeMap<String, String>,
    /// Discovered files on disk in the project/workspace: Document URI -> source text.
    pub disk_documents: BTreeMap<String, String>,
    /// Ambient standard library content (`RustSharp.Core.d.rsharp`).
    pub stdlib_source: String,
    /// Cached analysis snapshot from the most recent pass.
    pub snapshot: Option<AnalysisSnapshot>,
    /// Flag set when `shutdown` request is received.
    pub is_shutdown: bool,
}

impl Default for LspServer {
    fn default() -> Self {
        Self::new()
    }
}

impl LspServer {
    pub fn new() -> Self {
        Self {
            workspace_root: None,
            documents: BTreeMap::new(),
            disk_documents: BTreeMap::new(),
            stdlib_source: EMBEDDED_STDLIB.to_string(),
            snapshot: None,
            is_shutdown: false,
        }
    }

    /// Discovers all `*.rsharp` files inside `root_uri_or_path` and caches their content.
    pub fn discover_workspace_files(&mut self, root_uri_or_path: &str) {
        let root_str = root_uri_or_path
            .strip_prefix("file://")
            .unwrap_or(root_uri_or_path);
        let root_path = Path::new(root_str);
        // Protect against scanning root "/" or empty or non-existent path
        if root_str.is_empty() || root_path == Path::new("/") || !root_path.is_dir() {
            return;
        }

        let mut discovered = Vec::new();
        discover_rsharp_files(root_path, &mut discovered, 0);

        for path in discovered {
            if let Ok(content) = fs::read_to_string(&path) {
                let uri = format!("file://{}", path.to_string_lossy());
                self.disk_documents.insert(uri, content);
            }
        }
    }

    /// Dispatches a JSON-RPC message, returning zero or more response/notification messages.
    pub fn handle_message(&mut self, msg: &JsonRpcMessage) -> Vec<JsonRpcMessage> {
        let method = msg.method.as_deref().unwrap_or("");
        let id_str = msg.id.as_deref();

        match method {
            "initialize" => {
                if let (Some(id), Some(params)) = (id_str, &msg.params) {
                    vec![self.handle_initialize(id, params)]
                } else if let Some(id) = id_str {
                    vec![self.handle_initialize(id, "{}")]
                } else {
                    vec![]
                }
            }

            "initialized" => {
                // Client acknowledged initialization; no response needed.
                vec![]
            }

            "textDocument/didOpen" => {
                if let Some(params) = &msg.params {
                    self.handle_did_open(params)
                } else {
                    vec![]
                }
            }

            "textDocument/didChange" => {
                if let Some(params) = &msg.params {
                    self.handle_did_change(params)
                } else {
                    vec![]
                }
            }

            "textDocument/didClose" => {
                if let Some(params) = &msg.params {
                    if let Some(uri) = extract_json_string_field(params, "uri") {
                        self.documents.remove(&uri);
                    }
                }
                vec![]
            }

            "textDocument/hover" => {
                if let (Some(id), Some(params)) = (id_str, &msg.params) {
                    vec![self.handle_hover(id, params)]
                } else {
                    vec![]
                }
            }

            "textDocument/definition" => {
                if let (Some(id), Some(params)) = (id_str, &msg.params) {
                    vec![self.handle_definition(id, params)]
                } else {
                    vec![]
                }
            }

            "textDocument/completion" => {
                if let (Some(id), Some(params)) = (id_str, &msg.params) {
                    vec![self.handle_completion(id, params)]
                } else {
                    vec![]
                }
            }

            "textDocument/documentSymbol" => {
                if let (Some(id), Some(params)) = (id_str, &msg.params) {
                    vec![self.handle_document_symbol(id, params)]
                } else {
                    vec![]
                }
            }

            "workspace/symbol" => {
                if let (Some(id), Some(params)) = (id_str, &msg.params) {
                    vec![self.handle_workspace_symbol(id, params)]
                } else {
                    vec![]
                }
            }

            "shutdown" => {
                self.is_shutdown = true;
                if let Some(id) = id_str {
                    vec![JsonRpcMessage::new_response(id, "null")]
                } else {
                    vec![]
                }
            }

            "exit" => {
                vec![]
            }

            _ => {
                if let Some(id) = id_str {
                    vec![JsonRpcMessage::new_response(id, "null")]
                } else {
                    vec![]
                }
            }
        }
    }

    fn handle_initialize(&mut self, id: &str, params: &str) -> JsonRpcMessage {
        if let Some(root_uri) = extract_json_string_field(params, "rootUri") {
            self.workspace_root = Some(root_uri.clone());
            self.discover_workspace_files(&root_uri);
        } else if let Some(root_path) = extract_json_string_field(params, "rootPath") {
            let uri = format!("file://{}", root_path);
            self.workspace_root = Some(uri.clone());
            self.discover_workspace_files(&uri);
        }

        let result = r#"{
  "capabilities": {
    "textDocumentSync": 1,
    "hoverProvider": true,
    "definitionProvider": true,
    "completionProvider": {
      "triggerCharacters": [".", "::"]
    },
    "documentSymbolProvider": true,
    "workspaceSymbolProvider": true
  },
  "serverInfo": {
    "name": "rsharpc-lsp",
    "version": "0.1.0"
  }
}"#;
        JsonRpcMessage::new_response(id, result)
    }

    fn handle_did_open(&mut self, params: &str) -> Vec<JsonRpcMessage> {
        let uri = match extract_json_string_field(params, "uri") {
            Some(u) => u,
            None => return vec![],
        };
        let text = match extract_json_string_field(params, "text") {
            Some(t) => t,
            None => return vec![],
        };

        self.documents.insert(uri.clone(), text);

        // Discover enclosing project / sibling files if not already cached
        let filename = uri_to_filename(&uri);
        let file_path = Path::new(&filename);
        if let Some(proj_root) = find_project_root_for_file(file_path) {
            let proj_root_str = proj_root.to_string_lossy();
            self.discover_workspace_files(&proj_root_str);
        }

        self.reanalyze_and_publish_diagnostics(&uri)
    }

    fn handle_did_change(&mut self, params: &str) -> Vec<JsonRpcMessage> {
        let uri = match extract_json_string_field(params, "uri") {
            Some(u) => u,
            None => return vec![],
        };
        let text = match extract_json_string_field(params, "text") {
            Some(t) => t,
            None => return vec![],
        };

        self.documents.insert(uri.clone(), text);
        self.reanalyze_and_publish_diagnostics(&uri)
    }

    /// Runs Pass 1 to Pass 2.5 analysis over all open documents, discovered project files, and stdlib,
    /// updating `self.snapshot` and generating `textDocument/publishDiagnostics` messages.
    pub fn reanalyze_and_publish_diagnostics(&mut self, target_uri: &str) -> Vec<JsonRpcMessage> {
        let mut files: Vec<(&str, &str)> = Vec::new();

        // 1. Include ambient stdlib
        files.push(("stdlib/RustSharp.Core.d.rsharp", &self.stdlib_source));

        // 2. Include discovered disk documents not currently open in memory
        for (uri, content) in &self.disk_documents {
            if !self.documents.contains_key(uri) {
                files.push((uri.as_str(), content.as_str()));
            }
        }

        // 3. Include in-memory open documents (authoritative latest text)
        for (uri, content) in &self.documents {
            files.push((uri.as_str(), content.as_str()));
        }

        let (units, symtab, diag) = analyze_workspace_with_preflight(&files);
        let all_diags = diag.diagnostics.clone();
        self.snapshot = Some(AnalysisSnapshot {
            units,
            symtab,
            diagnostics: all_diags.clone(),
        });

        // Filter diagnostics relevant to the target uri
        let target_filename = uri_to_filename(target_uri);
        let mut doc_diags = Vec::new();
        for d in &all_diags {
            if d.span.filename == target_uri
                || d.span.filename == target_filename
                || target_uri.ends_with(&d.span.filename)
            {
                doc_diags.push(d);
            }
        }

        let lsp_diag_items: Vec<String> = doc_diags
            .into_iter()
            .map(|d| {
                let start_l = d.span.start_line.saturating_sub(1);
                let start_c = d.span.start_col.saturating_sub(1);
                let end_l = d.span.end_line.saturating_sub(1);
                let end_c = d.span.end_col.saturating_sub(1);
                let severity = match d.severity {
                    DiagnosticSeverity::Error => 1,
                    DiagnosticSeverity::Warning => 2,
                };
                format!(
                    r#"{{"range":{{"start":{{"line":{},"character":{}}},"end":{{"line":{},"character":{}}}}},"severity":{},"code":"{}","source":"rsharpc","message":"{}"}}"#,
                    start_l,
                    start_c,
                    end_l,
                    end_c,
                    severity,
                    d.code.as_str(),
                    escape_json(&d.message)
                )
            })
            .collect();

        let params_json = format!(
            r#"{{"uri":"{}","diagnostics":[{}]}}"#,
            target_uri,
            lsp_diag_items.join(",")
        );

        vec![JsonRpcMessage::new_notification(
            "textDocument/publishDiagnostics",
            &params_json,
        )]
    }

    fn handle_hover(&self, id: &str, params: &str) -> JsonRpcMessage {
        let uri = match extract_json_string_field(params, "uri") {
            Some(u) => u,
            None => return JsonRpcMessage::new_response(id, "null"),
        };
        let line: usize = match extract_json_field(params, "line").and_then(|s| s.parse().ok()) {
            Some(l) => l,
            None => return JsonRpcMessage::new_response(id, "null"),
        };
        let col: usize = match extract_json_field(params, "character").and_then(|s| s.parse().ok())
        {
            Some(c) => c,
            None => return JsonRpcMessage::new_response(id, "null"),
        };

        let content = match self
            .documents
            .get(&uri)
            .or_else(|| self.disk_documents.get(&uri))
        {
            Some(c) => c,
            None => return JsonRpcMessage::new_response(id, "null"),
        };

        let ident = match extract_identifier_at_pos(content, line, col) {
            Some(i) => i,
            None => return JsonRpcMessage::new_response(id, "null"),
        };

        if let Some(snapshot) = &self.snapshot {
            if let Some(hover_md) = build_hover_content(&ident, snapshot) {
                let result = format!(
                    r#"{{"contents":{{"kind":"markdown","value":"{}"}}}}"#,
                    escape_json(&hover_md)
                );
                return JsonRpcMessage::new_response(id, &result);
            }
        }

        // Fallback for standard LINQ operators
        if let Some(linq_md) = linq_operator_doc(&ident) {
            let result = format!(
                r#"{{"contents":{{"kind":"markdown","value":"{}"}}}}"#,
                escape_json(linq_md)
            );
            return JsonRpcMessage::new_response(id, &result);
        }

        JsonRpcMessage::new_response(id, "null")
    }

    fn handle_definition(&mut self, id: &str, params: &str) -> JsonRpcMessage {
        let uri = match extract_json_string_field(params, "uri") {
            Some(u) => u,
            None => return JsonRpcMessage::new_response(id, "null"),
        };
        let line: usize = match extract_json_field(params, "line").and_then(|s| s.parse().ok()) {
            Some(l) => l,
            None => return JsonRpcMessage::new_response(id, "null"),
        };
        let col: usize = match extract_json_field(params, "character").and_then(|s| s.parse().ok())
        {
            Some(c) => c,
            None => return JsonRpcMessage::new_response(id, "null"),
        };

        // Fallback: If document is not in memory or disk cache, read directly from filesystem
        if !self.documents.contains_key(&uri) && !self.disk_documents.contains_key(&uri) {
            let filename = uri_to_filename(&uri);
            if let Ok(content) = fs::read_to_string(&filename) {
                self.documents.insert(uri.clone(), content);
                self.reanalyze_and_publish_diagnostics(&uri);
            }
        }

        let content = match self
            .documents
            .get(&uri)
            .or_else(|| self.disk_documents.get(&uri))
        {
            Some(c) => c.clone(),
            None => return JsonRpcMessage::new_response(id, "null"),
        };

        let ident = match extract_identifier_at_pos(&content, line, col) {
            Some(i) => i,
            None => return JsonRpcMessage::new_response(id, "null"),
        };

        if self.snapshot.is_none() {
            self.reanalyze_and_publish_diagnostics(&uri);
        }

        if let Some(snapshot) = &self.snapshot {
            let spans = find_symbol_definitions(
                &ident,
                &uri,
                line,
                col,
                snapshot,
                self.workspace_root.as_deref(),
            );

            let format_range = |span: &SourceSpan| {
                let start_l = span.start_line.saturating_sub(1);
                let start_c = span.start_col.saturating_sub(1);
                let end_l = if span.start_line == span.end_line {
                    span.end_line.saturating_sub(1)
                } else {
                    start_l
                };
                let end_c = if span.start_line == span.end_line {
                    span.end_col.saturating_sub(1)
                } else {
                    start_c + ident.len() as u32
                };
                (start_l, start_c, end_l, end_c)
            };

            if spans.len() == 1 {
                let span = &spans[0];
                let target_uri = span_to_uri(span, self.workspace_root.as_deref());
                let (start_l, start_c, end_l, end_c) = format_range(span);

                let result = format!(
                    r#"{{"uri":"{}","range":{{"start":{{"line":{},"character":{}}},"end":{{"line":{},"character":{}}}}}}}"#,
                    target_uri, start_l, start_c, end_l, end_c
                );
                return JsonRpcMessage::new_response(id, &result);
            } else if spans.len() > 1 {
                let locs: Vec<String> = spans
                    .iter()
                    .map(|span| {
                        let target_uri = span_to_uri(span, self.workspace_root.as_deref());
                        let (start_l, start_c, end_l, end_c) = format_range(span);
                        format!(
                            r#"{{"uri":"{}","range":{{"start":{{"line":{},"character":{}}},"end":{{"line":{},"character":{}}}}}}}"#,
                            target_uri, start_l, start_c, end_l, end_c
                        )
                    })
                    .collect();
                let result = format!("[{}]", locs.join(","));
                return JsonRpcMessage::new_response(id, &result);
            }
        }

        JsonRpcMessage::new_response(id, "null")
    }

    fn handle_document_symbol(&self, id: &str, params: &str) -> JsonRpcMessage {
        let uri = match extract_json_string_field(params, "uri") {
            Some(u) => u,
            None => return JsonRpcMessage::new_response(id, "[]"),
        };

        let target_filename = uri_to_filename(&uri);
        let mut symbols = Vec::new();

        if let Some(snapshot) = &self.snapshot {
            for unit in &snapshot.units {
                if unit.filename == uri
                    || unit.filename == target_filename
                    || uri.ends_with(&unit.filename)
                {
                    for ty in &unit.types {
                        let ty_kind = match ty.kind {
                            TypeKind::Record { .. } | TypeKind::ValueStruct => 23,
                            TypeKind::Enum => 10,
                            TypeKind::Interface { .. } => 11,
                            _ => 5,
                        };

                        let mut children = Vec::new();
                        for member in &ty.members {
                            match member {
                                MemberDecl::Method(m) => {
                                    children.push(format_document_symbol(&m.name, 6, &m.span, &[]));
                                }
                                MemberDecl::Field(f) => {
                                    children.push(format_document_symbol(&f.name, 8, &f.span, &[]));
                                }
                                MemberDecl::Property(p) => {
                                    children.push(format_document_symbol(&p.name, 7, &p.span, &[]));
                                }
                                _ => {}
                            }
                        }
                        for variant in &ty.enum_variants {
                            children.push(format_document_symbol(
                                &variant.name,
                                22,
                                &variant.span,
                                &[],
                            ));
                        }

                        symbols.push(format_document_symbol(
                            &ty.name, ty_kind, &ty.span, &children,
                        ));
                    }
                }
            }
        }

        let result = format!("[{}]", symbols.join(","));
        JsonRpcMessage::new_response(id, &result)
    }

    fn handle_workspace_symbol(&self, id: &str, params: &str) -> JsonRpcMessage {
        let query = extract_json_string_field(params, "query")
            .unwrap_or_default()
            .to_lowercase();
        let mut symbols = Vec::new();

        if let Some(snapshot) = &self.snapshot {
            for unit in &snapshot.units {
                for ty in &unit.types {
                    if ty.name.to_lowercase().contains(&query) {
                        let kind = match ty.kind {
                            TypeKind::Record { .. } | TypeKind::ValueStruct => 23,
                            TypeKind::Enum => 10,
                            TypeKind::Interface { .. } => 11,
                            _ => 5,
                        };
                        let uri = span_to_uri(&ty.span, self.workspace_root.as_deref());
                        symbols.push(format_workspace_symbol(&ty.name, kind, &uri, &ty.span));
                    }
                    for member in &ty.members {
                        match member {
                            MemberDecl::Method(m) if m.name.to_lowercase().contains(&query) => {
                                let uri = span_to_uri(&m.span, self.workspace_root.as_deref());
                                symbols.push(format_workspace_symbol(
                                    &format!("{}.{}", ty.name, m.name),
                                    6,
                                    &uri,
                                    &m.span,
                                ));
                            }
                            MemberDecl::Field(f) if f.name.to_lowercase().contains(&query) => {
                                let uri = span_to_uri(&f.span, self.workspace_root.as_deref());
                                symbols.push(format_workspace_symbol(
                                    &format!("{}.{}", ty.name, f.name),
                                    8,
                                    &uri,
                                    &f.span,
                                ));
                            }
                            MemberDecl::Property(p) if p.name.to_lowercase().contains(&query) => {
                                let uri = span_to_uri(&p.span, self.workspace_root.as_deref());
                                symbols.push(format_workspace_symbol(
                                    &format!("{}.{}", ty.name, p.name),
                                    7,
                                    &uri,
                                    &p.span,
                                ));
                            }
                            _ => {}
                        }
                    }
                }
            }
        }

        let result = format!("[{}]", symbols.join(","));
        JsonRpcMessage::new_response(id, &result)
    }

    fn handle_completion(&self, id: &str, params: &str) -> JsonRpcMessage {
        let uri = match extract_json_string_field(params, "uri") {
            Some(u) => u,
            None => return JsonRpcMessage::new_response(id, "null"),
        };
        let line: usize = match extract_json_field(params, "line").and_then(|s| s.parse().ok()) {
            Some(l) => l,
            None => return JsonRpcMessage::new_response(id, "null"),
        };
        let col: usize = match extract_json_field(params, "character").and_then(|s| s.parse().ok())
        {
            Some(c) => c,
            None => return JsonRpcMessage::new_response(id, "null"),
        };

        let content = self
            .documents
            .get(&uri)
            .or_else(|| self.disk_documents.get(&uri))
            .map(|s| s.as_str())
            .unwrap_or("");
        let line_prefix = get_line_prefix(content, line, col);

        let mut items = Vec::new();

        if line_prefix.ends_with('.') {
            // Suggest LINQ operators and collection methods
            for (op, detail) in linq_completions() {
                items.push(format!(
                    r#"{{"label":"{}","kind":2,"detail":"{}"}}"#,
                    op, detail
                ));
            }
        } else {
            // Suggest keywords
            for kw in keywords() {
                items.push(format!(
                    r#"{{"label":"{}","kind":14,"detail":"RustSharp keyword"}}"#,
                    kw
                ));
            }
            // Suggest standard primitive types
            for ty in &[
                "Console",
                "Math",
                "List",
                "Dictionary",
                "HashSet",
                "Task",
                "String",
                "Int32",
                "Int64",
                "Boolean",
                "Double",
                "Environment",
            ] {
                items.push(format!(
                    r#"{{"label":"{}","kind":7,"detail":"Standard library type"}}"#,
                    ty
                ));
            }
            // Suggest discovered user types from snapshot
            if let Some(snapshot) = &self.snapshot {
                for unit in &snapshot.units {
                    for ty in &unit.types {
                        if !ty.name.is_empty() {
                            items.push(format!(
                                r#"{{"label":"{}","kind":7,"detail":"{}"}}"#,
                                ty.name,
                                format_type_archetype(ty.kind)
                            ));
                        }
                    }
                }
            }
        }

        let result = format!(r#"{{"isIncomplete":false,"items":[{}]}}"#, items.join(","));
        JsonRpcMessage::new_response(id, &result)
    }
}

/// Runs the standard I/O streaming loop for `rsharpc lsp`.
pub fn run_stdio_server() -> io::Result<()> {
    let stdin = io::stdin();
    let mut reader = io::BufReader::new(stdin.lock());
    let stdout = io::stdout();
    let mut writer = io::BufWriter::new(stdout.lock());

    let mut server = LspServer::new();

    while let Some(msg) = JsonRpcTransport::read_message(&mut reader)? {
        let responses = server.handle_message(&msg);
        for resp in responses {
            JsonRpcTransport::write_message(&mut writer, &resp)?;
        }
        if server.is_shutdown && msg.method.as_deref() == Some("exit") {
            break;
        }
    }

    Ok(())
}

fn uri_to_filename(uri: &str) -> String {
    if let Some(stripped) = uri.strip_prefix("file://") {
        stripped.to_string()
    } else {
        uri.to_string()
    }
}

fn span_to_uri(span: &SourceSpan, workspace_root: Option<&str>) -> String {
    if span.filename.starts_with("file://") {
        span.filename.clone()
    } else {
        let p = Path::new(&span.filename);
        if p.is_absolute() {
            format!("file://{}", p.to_string_lossy())
        } else if let Some(root) = workspace_root {
            let root_clean = root.strip_prefix("file://").unwrap_or(root);
            let joined = Path::new(root_clean).join(p);
            format!("file://{}", joined.to_string_lossy())
        } else if let Ok(cwd) = std::env::current_dir() {
            let joined = cwd.join(p);
            format!("file://{}", joined.to_string_lossy())
        } else {
            format!("file:///{}", span.filename.trim_start_matches('/'))
        }
    }
}

fn discover_rsharp_files(dir: &Path, files: &mut Vec<PathBuf>, depth: usize) {
    if depth > 8 {
        return;
    }
    if let Ok(entries) = fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
                if !name.starts_with('.')
                    && name != "target"
                    && name != "node_modules"
                    && name != "build"
                {
                    discover_rsharp_files(&path, files, depth + 1);
                }
            } else if path.extension().and_then(|e| e.to_str()) == Some("rsharp") {
                files.push(path);
            }
        }
    }
}

fn find_project_root_for_file(file_path: &Path) -> Option<PathBuf> {
    if !file_path.exists() {
        return None;
    }
    let mut curr = file_path.parent();
    while let Some(dir) = curr {
        if dir == Path::new("/") || dir.as_os_str().is_empty() {
            break;
        }
        if let Ok(entries) = fs::read_dir(dir) {
            for entry in entries.flatten() {
                if let Some(ext) = entry.path().extension() {
                    if ext == "rsproj" {
                        return Some(dir.to_path_buf());
                    }
                }
            }
        }
        if dir.join(".git").exists() || dir.join("Cargo.toml").exists() {
            return Some(dir.to_path_buf());
        }
        curr = dir.parent();
    }
    None
}

fn format_document_symbol(
    name: &str,
    kind: usize,
    span: &SourceSpan,
    children: &[String],
) -> String {
    let start_l = span.start_line.saturating_sub(1);
    let start_c = span.start_col.saturating_sub(1);
    let end_l = span.end_line.saturating_sub(1);
    let end_c = span.end_col.saturating_sub(1);
    let children_str = if children.is_empty() {
        String::new()
    } else {
        format!(r#","children":[{}]"#, children.join(","))
    };

    format!(
        r#"{{"name":"{}","kind":{},"range":{{"start":{{"line":{},"character":{}}},"end":{{"line":{},"character":{}}}}},"selectionRange":{{"start":{{"line":{},"character":{}}},"end":{{"line":{},"character":{}}}}}{}}}"#,
        escape_json(name),
        kind,
        start_l,
        start_c,
        end_l,
        end_c,
        start_l,
        start_c,
        end_l,
        end_c,
        children_str
    )
}

fn format_workspace_symbol(name: &str, kind: usize, uri: &str, span: &SourceSpan) -> String {
    let start_l = span.start_line.saturating_sub(1);
    let start_c = span.start_col.saturating_sub(1);
    let end_l = span.end_line.saturating_sub(1);
    let end_c = span.end_col.saturating_sub(1);

    format!(
        r#"{{"name":"{}","kind":{},"location":{{"uri":"{}","range":{{"start":{{"line":{},"character":{}}},"end":{{"line":{},"character":{}}}}}}}}}"#,
        escape_json(name),
        kind,
        uri,
        start_l,
        start_c,
        end_l,
        end_c
    )
}

fn extract_identifier_at_pos(content: &str, line_idx: usize, col_idx: usize) -> Option<String> {
    let line = content.lines().nth(line_idx)?;
    if line.is_empty() {
        return None;
    }

    let bytes = line.as_bytes();
    let pos = col_idx.min(bytes.len().saturating_sub(1));

    if !is_ident_char(bytes[pos]) {
        // Check character immediately before if cursor is at the end of word
        if pos > 0 && is_ident_char(bytes[pos - 1]) {
            return extract_ident_around(bytes, pos - 1);
        }
        return None;
    }

    extract_ident_around(bytes, pos)
}

fn is_ident_char(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

fn extract_ident_around(bytes: &[u8], pos: usize) -> Option<String> {
    let mut start = pos;
    while start > 0 && is_ident_char(bytes[start - 1]) {
        start -= 1;
    }
    let mut end = pos;
    while end < bytes.len() && is_ident_char(bytes[end]) {
        end += 1;
    }

    String::from_utf8(bytes[start..end].to_vec()).ok()
}

fn get_line_prefix(content: &str, line_idx: usize, col_idx: usize) -> String {
    if let Some(line) = content.lines().nth(line_idx) {
        let idx = col_idx.min(line.len());
        line[..idx].trim_end().to_string()
    } else {
        String::new()
    }
}

fn build_hover_content(ident: &str, snapshot: &AnalysisSnapshot) -> Option<String> {
    // 1. Search for matching MethodDecl
    for unit in &snapshot.units {
        for ty in &unit.types {
            for member in &ty.members {
                if let MemberDecl::Method(m) = member {
                    if m.name == ident {
                        let self_str = match m.inferred_self_borrow {
                            BorrowMode::MutBorrow => "&mut self",
                            BorrowMode::ReadBorrow => "&self",
                            BorrowMode::OwnedMove => "self",
                            BorrowMode::Unresolved => "self",
                            BorrowMode::CopyValue | BorrowMode::SharedArc => "&self",
                        };

                        let params_str: Vec<String> = m
                            .params
                            .iter()
                            .map(|p| {
                                let borrow_prefix = match p.inferred_borrow {
                                    BorrowMode::MutBorrow => "&mut ",
                                    BorrowMode::ReadBorrow => "&",
                                    _ => "",
                                };
                                format!("{}: {}{}", p.name, borrow_prefix, p.ty.short_name())
                            })
                            .collect();

                        let rust_fn = if m.is_static {
                            format!(
                                "pub fn {}({}) -> {}",
                                to_snake_case(&m.name),
                                params_str.join(", "),
                                m.return_type.short_name()
                            )
                        } else {
                            let mut full_params = vec![self_str.to_string()];
                            full_params.extend(params_str);
                            format!(
                                "pub fn {}({}) -> {}",
                                to_snake_case(&m.name),
                                full_params.join(", "),
                                m.return_type.short_name()
                            )
                        };

                        let mut md = format!(
                            "```rustsharp\n(method) {} {}.{}(...)\n```\n\n**Lowered Rust signature:**\n```rust\n{}\n```\n",
                            m.return_type.short_name(),
                            ty.name,
                            m.name,
                            rust_fn
                        );

                        if !m.is_static {
                            md.push_str(&format!(
                                "\n*Inferred receiver borrow:* `{}` (whole-program mutation analysis)",
                                self_str
                            ));
                        }

                        if let EffectSignature::Fallible { error_type } = &m.inferred_effect {
                            md.push_str(&format!(
                                "\n*Checked effect:* `throws {}` (lowered to `Result<T, {}>`)",
                                error_type.short_name(),
                                error_type.short_name()
                            ));
                        }

                        return Some(md);
                    }
                }
            }
        }
    }

    // 2. Search for matching TypeDecl
    for unit in &snapshot.units {
        for ty in &unit.types {
            if ty.name == ident {
                let archetype_desc = format_type_archetype(ty.kind);
                let poly_desc = match &ty.inferred_polymorphism {
                    PolymorphismStrategy::FlattenedSubStruct { .. } => {
                        "Concrete subclass: flattened `base` struct + Deref/DerefMut"
                    }
                    PolymorphismStrategy::ClosedWorldEnum { variants: _ } => {
                        "Closed-world hierarchy: lowered to Rust enum with exhaustive match"
                    }
                    PolymorphismStrategy::OpenTrait => {
                        "Extensible interface: native Rust pub trait"
                    }
                    _ => "Monomorphic struct",
                };

                let md = format!(
                    "```rustsharp\n{} {}\n```\n\n**Archetype:** {}\n\n**Polymorphism Strategy:** {}",
                    archetype_desc, ty.name, archetype_desc, poly_desc
                );
                return Some(md);
            }
        }
    }

    // 3. Search for matching FieldDecl
    for unit in &snapshot.units {
        for ty in &unit.types {
            for member in &ty.members {
                if let MemberDecl::Field(f) = member {
                    if f.name == ident {
                        let storage = match f.resolved_storage {
                            FieldStorageMode::Plain => "Direct unboxed value (`T`)",
                            FieldStorageMode::ArcShared => "Shared actor reference (`Arc<T>`)",
                            FieldStorageMode::RwLockShared => {
                                "Thread-safe mutable state (`Arc<RwLock<T>>`)"
                            }
                        };
                        let md = format!(
                            "```rustsharp\n(field) {} {}.{}\n```\n\n**Storage:** {}",
                            f.ty.short_name(),
                            ty.name,
                            f.name,
                            storage
                        );
                        return Some(md);
                    }
                }
            }
        }
    }

    // 4. Search for matching LocalVar in statements
    for unit in &snapshot.units {
        for ty in &unit.types {
            for member in &ty.members {
                if let MemberDecl::Method(m) = member {
                    if let Some(body) = &m.body {
                        for stmt in &body.stmts {
                            if let Stmt::LocalVar {
                                name,
                                explicit_type,
                                inferred_mut,
                                inferred_type,
                                ..
                            } = stmt
                            {
                                if name == ident {
                                    let ty_name = explicit_type
                                        .as_ref()
                                        .or(inferred_type.as_ref())
                                        .map(|t| t.short_name())
                                        .unwrap_or("var");
                                    let mut_desc = if *inferred_mut {
                                        "Inferred as `let mut` (mutation detected)"
                                    } else {
                                        "Inferred as `let` (immutable borrow/value)"
                                    };
                                    let md = format!(
                                        "```rustsharp\n(local variable) {} {}\n```\n\n*Inferred binding:* {}",
                                        ty_name, name, mut_desc
                                    );
                                    return Some(md);
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    None
}

fn find_symbol_definitions(
    ident: &str,
    current_uri: &str,
    line_0: usize,
    _col_0: usize,
    snapshot: &AnalysisSnapshot,
    _workspace_root: Option<&str>,
) -> Vec<SourceSpan> {
    let target_line = (line_0 + 1) as u32;
    let target_filename = uri_to_filename(current_uri);

    // 1. Check local variable or parameter in the enclosing method of the current file
    for unit in &snapshot.units {
        if unit.filename == current_uri
            || unit.filename == target_filename
            || current_uri.ends_with(&unit.filename)
        {
            for ty in &unit.types {
                if ty.span.start_line <= target_line && ty.span.end_line >= target_line {
                    for member in &ty.members {
                        if let MemberDecl::Method(m) = member {
                            if m.span.start_line <= target_line && m.span.end_line >= target_line {
                                // Check parameters
                                for p in &m.params {
                                    if p.name == ident {
                                        return vec![p.span.clone()];
                                    }
                                }
                                // Check local variables
                                if let Some(body) = &m.body {
                                    for stmt in &body.stmts {
                                        if let Stmt::LocalVar { name, span, .. } = stmt {
                                            if name == ident {
                                                return vec![span.clone()];
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // 2. Check members of the enclosing type
                    for member in &ty.members {
                        match member {
                            MemberDecl::Method(m) if m.name == ident => {
                                return vec![m.span.clone()]
                            }
                            MemberDecl::Field(f) if f.name == ident => return vec![f.span.clone()],
                            MemberDecl::Property(p) if p.name == ident => {
                                return vec![p.span.clone()]
                            }
                            _ => {}
                        }
                    }
                    for variant in &ty.enum_variants {
                        if variant.name == ident {
                            return vec![variant.span.clone()];
                        }
                    }
                }
            }
        }
    }

    // 3. Top-level Type check across all units (records, classes, structs, interfaces, enums)
    let mut type_spans = Vec::new();
    for unit in &snapshot.units {
        for ty in &unit.types {
            if ty.name == ident {
                type_spans.push(ty.span.clone());
            }
        }
    }
    if !type_spans.is_empty() {
        return type_spans;
    }

    // 4. Enum variants across all units
    let mut variant_spans = Vec::new();
    for unit in &snapshot.units {
        for ty in &unit.types {
            for variant in &ty.enum_variants {
                if variant.name == ident {
                    variant_spans.push(variant.span.clone());
                }
            }
        }
    }
    if !variant_spans.is_empty() {
        return variant_spans;
    }

    // 5. Members across all units
    let mut member_spans = Vec::new();
    for unit in &snapshot.units {
        for ty in &unit.types {
            for member in &ty.members {
                match member {
                    MemberDecl::Method(m) if m.name == ident => member_spans.push(m.span.clone()),
                    MemberDecl::Field(f) if f.name == ident => member_spans.push(f.span.clone()),
                    MemberDecl::Property(p) if p.name == ident => member_spans.push(p.span.clone()),
                    _ => {}
                }
            }
        }
    }
    if !member_spans.is_empty() {
        return member_spans;
    }

    // 6. Check co-located raw .rs files in the project directory
    let current_file = Path::new(&target_filename);
    if let Some(parent) = current_file.parent() {
        // 6a. Direct {ident}.rs sibling file (e.g. NativeCrypto.rs)
        let candidate_rs = parent.join(format!("{}.rs", ident));
        if candidate_rs.exists() {
            if let Ok(rs_src) = fs::read_to_string(&candidate_rs) {
                let rs_line = find_rust_ident_line(&rs_src, ident);
                return vec![SourceSpan::new(
                    0,
                    candidate_rs.to_string_lossy().to_string(),
                    rs_line,
                    1,
                    rs_line,
                    1 + ident.len() as u32,
                )];
            }
        }

        // 6b. Search all sibling .rs files for `fn {snake_case(ident)}` or `fn {ident}`
        if let Ok(entries) = fs::read_dir(parent) {
            let snake_ident = to_snake_case(ident);
            for entry in entries.flatten() {
                let p = entry.path();
                if p.extension().and_then(|e| e.to_str()) == Some("rs") {
                    if let Ok(rs_src) = fs::read_to_string(&p) {
                        if let Some(rs_line) = find_rust_method_line(&rs_src, ident, &snake_ident) {
                            return vec![SourceSpan::new(
                                0,
                                p.to_string_lossy().to_string(),
                                rs_line,
                                1,
                                rs_line,
                                1 + ident.len() as u32,
                            )];
                        }
                    }
                }
            }
        }
    }

    Vec::new()
}

fn find_rust_ident_line(src: &str, ident: &str) -> u32 {
    let struct_pat = format!("struct {}", ident);
    let impl_pat = format!("impl {}", ident);
    let enum_pat = format!("enum {}", ident);
    for (i, line) in src.lines().enumerate() {
        if line.contains(&struct_pat) || line.contains(&impl_pat) || line.contains(&enum_pat) {
            return (i + 1) as u32;
        }
    }
    1
}

fn find_rust_method_line(src: &str, ident: &str, snake_ident: &str) -> Option<u32> {
    let fn_pat1 = format!("fn {}", snake_ident);
    let fn_pat2 = format!("fn {}", ident);
    for (i, line) in src.lines().enumerate() {
        if line.contains(&fn_pat1) || line.contains(&fn_pat2) {
            return Some((i + 1) as u32);
        }
    }
    None
}

fn format_type_archetype(kind: TypeKind) -> &'static str {
    match kind {
        TypeKind::Record { is_struct: true } => "record struct",
        TypeKind::Record { is_struct: false } => "record class (linear DTO)",
        TypeKind::StandardClass => "standard class (unique owner)",
        TypeKind::ServiceClass => "service class (readonly Arc<T> actor)",
        TypeKind::SharedClass => "shared class (Arc<RwLock<T>> shared state)",
        TypeKind::PrimitiveClass { .. } => "primitive type",
        TypeKind::ValueStruct => "value struct",
        TypeKind::Interface {
            is_extensible: true,
        } => "extensible interface (pub trait)",
        TypeKind::Interface {
            is_extensible: false,
        } => "sealed interface",
        TypeKind::Enum => "enum",
    }
}

fn to_snake_case(s: &str) -> String {
    let mut out = String::new();
    for (i, c) in s.char_indices() {
        if c.is_uppercase() {
            if i > 0 {
                out.push('_');
            }
            out.push(c.to_ascii_lowercase());
        } else {
            out.push(c);
        }
    }
    out
}

fn linq_operator_doc(ident: &str) -> Option<&'static str> {
    match ident {
        "Select" => Some(
            "```rustsharp\nIEnumerable<U> Select<T, U>(Func<T, U> selector)\n```\n\n**LINQ Pipeline:** Lowers directly to Rust zero-cost iterator `.map(...)`.",
        ),
        "Where" => Some(
            "```rustsharp\nIEnumerable<T> Where<T>(Func<T, bool> predicate)\n```\n\n**LINQ Pipeline:** Lowers directly to Rust zero-cost iterator `.filter(...)`.",
        ),
        "OrderBy" => Some(
            "```rustsharp\nIOrderedEnumerable<T> OrderBy<T, K>(Func<T, K> keySelector)\n```\n\n**LINQ Pipeline:** Collects into buffer and sorts by key ascending.",
        ),
        "OrderByDescending" => Some(
            "```rustsharp\nIOrderedEnumerable<T> OrderByDescending<T, K>(Func<T, K> keySelector)\n```\n\n**LINQ Pipeline:** Collects into buffer and sorts by key descending.",
        ),
        "Distinct" => Some(
            "```rustsharp\nIEnumerable<T> Distinct<T>()\n```\n\n**LINQ Pipeline:** Filters duplicates via an inline `HashSet` tracking seen items.",
        ),
        "Reverse" => Some(
            "```rustsharp\nIEnumerable<T> Reverse<T>()\n```\n\n**LINQ Pipeline:** Lowers to Rust `.rev()` iterator adapter.",
        ),
        "WithIndex" => Some(
            "```rustsharp\nIEnumerable<(int Index, T Item)> WithIndex<T>()\n```\n\n**LINQ Pipeline:** Lowers to Rust zero-cost `.enumerate()`.",
        ),
        "ToList" => Some(
            "```rustsharp\nList<T> ToList<T>()\n```\n\n**LINQ Materialization:** Materializes iterator sequence into a heap-allocated `Vec<T>`.",
        ),
        "ToArray" => Some(
            "```rustsharp\nT[] ToArray<T>()\n```\n\n**LINQ Materialization:** Materializes iterator sequence into a boxed slice `Box<[T]>`.",
        ),
        "ToHashSet" => Some(
            "```rustsharp\nHashSet<T> ToHashSet<T>()\n```\n\n**LINQ Materialization:** Collects iterator sequence into a `std::collections::HashSet<T>`.",
        ),
        _ => None,
    }
}

fn linq_completions() -> &'static [(&'static str, &'static str)] {
    &[
        ("Select", "LINQ iterator projection (.map)"),
        ("Where", "LINQ iterator filter (.filter)"),
        ("OrderBy", "LINQ sort by key ascending"),
        ("OrderByDescending", "LINQ sort by key descending"),
        ("Distinct", "LINQ deduplicate elements"),
        ("Reverse", "LINQ reverse sequence (.rev)"),
        ("WithIndex", "LINQ enumerate with 0-indexed counter"),
        ("ToList", "Materialize into Vec<T>"),
        ("ToArray", "Materialize into Box<[T]>"),
        ("ToHashSet", "Materialize into HashSet<T>"),
        ("First", "Extract first item (panics if empty)"),
        ("FirstOrDefault", "Extract first item or Option::None"),
        ("Last", "Extract last item (panics if empty)"),
        ("LastOrDefault", "Extract last item or Option::None"),
        ("Count", "Count items in sequence"),
        ("Any", "Test if any item satisfies condition"),
        ("All", "Test if all items satisfy condition"),
        ("Sum", "Sum numeric items"),
        ("Min", "Minimum item"),
        ("Max", "Maximum item"),
        ("Aggregate", "Fold/reduce sequence"),
    ]
}

fn keywords() -> &'static [&'static str] {
    &[
        "class",
        "record",
        "struct",
        "interface",
        "enum",
        "fn",
        "async",
        "await",
        "using",
        "namespace",
        "public",
        "private",
        "internal",
        "throws",
        "return",
        "if",
        "else",
        "while",
        "for",
        "foreach",
        "in",
        "switch",
        "case",
        "default",
        "break",
        "continue",
        "let",
        "var",
        "new",
    ]
}
