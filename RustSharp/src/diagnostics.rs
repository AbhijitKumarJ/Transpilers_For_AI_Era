use std::fmt;

/// Tracks exact 1-indexed line and column positions in the original `.rsharp` or `.d.rsharp` file.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct SourceSpan {
    pub file_id: usize,
    pub filename: String,
    pub start_line: u32,
    pub start_col: u32,
    pub end_line: u32,
    pub end_col: u32,
}

impl SourceSpan {
    pub fn new(
        file_id: usize,
        filename: impl Into<String>,
        start_line: u32,
        start_col: u32,
        end_line: u32,
        end_col: u32,
    ) -> Self {
        Self {
            file_id,
            filename: filename.into(),
            start_line,
            start_col,
            end_line,
            end_col,
        }
    }

    pub fn merge(&self, other: &SourceSpan) -> SourceSpan {
        SourceSpan {
            file_id: self.file_id,
            filename: self.filename.clone(),
            start_line: self.start_line,
            start_col: self.start_col,
            end_line: other.end_line,
            end_col: other.end_col,
        }
    }

    pub fn format_location(&self) -> String {
        format!("{}:{}:{}", self.filename, self.start_line, self.start_col)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DiagnosticSeverity {
    Error,
    Warning,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DiagnosticCode {
    SyntaxError,
    UnresolvedSymbol,
    AccessViolation,
    /// RSHARP001: Attempted field mutation inside a `service class` outside the constructor.
    RSharp001ServiceMutation,
    /// RSHARP002: Mutating a collection while iterating over it in a `foreach` loop.
    RSharp002CollectionAliasing,
    /// RSHARP003: Use-after-move of a non-Clone / linear `IDisposable` resource.
    RSharp003UseAfterMove,
}

impl DiagnosticCode {
    pub fn as_str(&self) -> &'static str {
        match self {
            DiagnosticCode::SyntaxError => "RSHARP000",
            DiagnosticCode::RSharp001ServiceMutation => "RSHARP001",
            DiagnosticCode::RSharp002CollectionAliasing => "RSHARP002",
            DiagnosticCode::RSharp003UseAfterMove => "RSHARP003",
            DiagnosticCode::AccessViolation => "RSHARP004",
            DiagnosticCode::UnresolvedSymbol => "RSHARP005",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Diagnostic {
    pub code: DiagnosticCode,
    pub severity: DiagnosticSeverity,
    pub message: String,
    pub span: SourceSpan,
    pub quick_fix: Option<String>,
}

impl fmt::Display for Diagnostic {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let sev = match self.severity {
            DiagnosticSeverity::Error => "ERROR",
            DiagnosticSeverity::Warning => "WARNING",
        };
        write!(
            f,
            "{} [{}] at {}: {}",
            sev,
            self.code.as_str(),
            self.span.format_location(),
            self.message
        )?;
        if let Some(fix) = &self.quick_fix {
            write!(f, " (Quick-fix: {})", fix)?;
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Default)]
pub struct DiagnosticEngine {
    pub diagnostics: Vec<Diagnostic>,
}

impl DiagnosticEngine {
    pub fn new() -> Self {
        Self {
            diagnostics: Vec::new(),
        }
    }

    pub fn report_syntax_error(&mut self, span: SourceSpan, message: impl Into<String>) {
        self.diagnostics.push(Diagnostic {
            code: DiagnosticCode::SyntaxError,
            severity: DiagnosticSeverity::Error,
            message: message.into(),
            span,
            quick_fix: None,
        });
    }

    pub fn report_unresolved_symbol(&mut self, span: SourceSpan, symbol_name: &str) {
        self.diagnostics.push(Diagnostic {
            code: DiagnosticCode::UnresolvedSymbol,
            severity: DiagnosticSeverity::Error,
            message: format!("Unresolved symbol or type '{}'.", symbol_name),
            span,
            quick_fix: None,
        });
    }

    pub fn report_access_violation(
        &mut self,
        span: SourceSpan,
        member_name: &str,
        access_mod: &str,
        owner_type: &str,
    ) {
        self.diagnostics.push(Diagnostic {
            code: DiagnosticCode::AccessViolation,
            severity: DiagnosticSeverity::Error,
            message: format!(
                "Member '{}.{}' is '{}' and cannot be accessed from this context.",
                owner_type, member_name, access_mod
            ),
            span,
            quick_fix: None,
        });
    }

    pub fn report_rsharp001(&mut self, span: SourceSpan, service_name: &str, field_name: &str) {
        self.diagnostics.push(Diagnostic {
            code: DiagnosticCode::RSharp001ServiceMutation,
            severity: DiagnosticSeverity::Error,
            message: format!(
                "Cannot mutate field '{}' inside service class '{}'. Service classes are immutable after construction.",
                field_name, service_name
            ),
            span,
            quick_fix: Some(
                "Wrap mutable state in a 'shared class' or pass state via method parameters."
                    .to_string(),
            ),
        });
    }

    pub fn report_rsharp002(&mut self, span: SourceSpan, collection_name: &str) {
        self.diagnostics.push(Diagnostic {
            code: DiagnosticCode::RSharp002CollectionAliasing,
            severity: DiagnosticSeverity::Error,
            message: format!(
                "Cannot mutate collection '{}' while iterating over it in a 'foreach' loop.",
                collection_name
            ),
            span,
            quick_fix: Some(format!(
                "Iterate over a snapshot with '{}.ToList()' or collect mutations separately.",
                collection_name
            )),
        });
    }

    pub fn report_rsharp003(&mut self, span: SourceSpan, var_name: &str, moved_at: &SourceSpan) {
        self.diagnostics.push(Diagnostic {
            code: DiagnosticCode::RSharp003UseAfterMove,
            severity: DiagnosticSeverity::Error,
            message: format!(
                "Linear resource '{}' was already consumed at {}:{} and cannot be used again.",
                var_name, moved_at.start_line, moved_at.start_col
            ),
            span,
            quick_fix: Some(
                "Pass the resource by read/mutable borrow instead of a '[Moves]' parameter, or clone if supported."
                    .to_string(),
            ),
        });
    }

    pub fn has_errors(&self) -> bool {
        self.diagnostics
            .iter()
            .any(|d| d.severity == DiagnosticSeverity::Error)
    }

    pub fn format_all(&self) -> String {
        self.diagnostics
            .iter()
            .map(|d| d.to_string())
            .collect::<Vec<_>>()
            .join("\n")
    }
}
