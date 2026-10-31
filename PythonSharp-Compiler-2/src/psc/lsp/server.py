from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO
from urllib.parse import unquote, urlparse

from psc.cli import _find_default_stdlib_dir
from psc.diagnostics import DiagnosticEngine, SourceSpan
from psc.frontend import CompilationUnit, Lexer, Parser, Token, TokenKind
from psc.lsp.protocol import JsonRpcProtocol
from psc.project import (
    is_ps_project_file,
    is_ps_source_file,
    is_ps_stub_file,
    load_project,
)
from psc.semantics import GlobalSymbolTable, analyze_compilation_units
from psc.version import __version__

PSC_KEYWORDS = [
    "abstract", "as", "async", "await", "base", "bool", "break", "byte", "case", "catch",
    "char", "class", "const", "continue", "decimal", "default", "delegate", "do", "double",
    "else", "enum", "event", "explicit", "extern", "false", "finally", "fixed", "float",
    "for", "foreach", "goto", "if", "implicit", "in", "int", "interface", "internal",
    "is", "lock", "long", "namespace", "new", "null", "object", "operator", "out",
    "override", "params", "private", "protected", "public", "readonly", "record", "ref",
    "return", "sbyte", "sealed", "short", "sizeof", "stackalloc", "static", "string",
    "struct", "switch", "this", "throw", "true", "try", "typeof", "uint", "ulong",
    "unchecked", "unsafe", "ushort", "using", "virtual", "void", "volatile", "while", "yield",
]

CORE_TYPES = [
    "String", "Int32", "Int64", "Boolean", "Double", "Single", "Object", "Void",
    "List", "Dict", "HashSet", "IEnumerable", "IAsyncEnumerable", "IAsyncEnumerator",
    "IDisposable", "IAsyncDisposable", "Task", "Console", "Math", "Exception",
]


def uri_to_path(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path)).resolve()
    return Path(uri).resolve()


def path_to_uri(path: Path | str) -> str:
    p = Path(path).resolve()
    return p.as_uri()


def span_to_range(span: SourceSpan) -> dict[str, dict[str, int]]:
    return {
        "start": {"line": max(0, span.start_line - 1), "character": max(0, span.start_col - 1)},
        "end": {"line": max(0, span.end_line - 1), "character": max(0, span.end_col - 1)},
    }


@dataclass(slots=True)
class DocumentState:
    uri: str
    text: str
    unit: CompilationUnit | None = None
    tokens: list[Token] | None = None
    project_units: list[CompilationUnit] = field(default_factory=list)
    symtab: GlobalSymbolTable | None = None
    diagnostics: DiagnosticEngine | None = None


class LanguageServer:
    """Pure-Python Language Server Protocol (LSP) server for PythonSharp (.ps) files."""

    def __init__(self, in_stream: BinaryIO | None = None, out_stream: BinaryIO | None = None) -> None:
        self.in_stream = in_stream or sys.stdin.buffer
        self.out_stream = out_stream or sys.stdout.buffer
        self.documents: dict[str, DocumentState] = {}
        self.workspace_root: Path | None = None
        self.is_running = True
        self.notifications_log: list[dict[str, object]] = []

        self.stdlib_dir: Path | None = _find_default_stdlib_dir()
        self.stdlib_units: list[CompilationUnit] = []
        self._load_stdlib()

    def _load_stdlib(self) -> None:
        if not self.stdlib_dir or not self.stdlib_dir.exists():
            return
        diag = DiagnosticEngine()
        stub_paths = sorted(p for p in self.stdlib_dir.rglob("*") if p.is_file() and is_ps_stub_file(p))
        for idx, stub_file in enumerate(stub_paths):
            try:
                text = stub_file.read_text(encoding="utf-8")
                unit = Parser.from_source(
                    text,
                    file_id=-(idx + 1),
                    ps_filename=str(stub_file.resolve()),
                    diagnostics=diag,
                ).parse_compilation_unit()
                self.stdlib_units.append(unit)
            except Exception:
                pass

    def send_notification(self, method: str, params: object) -> None:
        notif = JsonRpcProtocol.make_notification(method, params)
        self.notifications_log.append(notif)
        if self.out_stream is not None:
            JsonRpcProtocol.write_message(self.out_stream, notif)

    def send_response(self, req_id: object, result: object) -> None:
        resp = JsonRpcProtocol.make_response(req_id, result)
        if self.out_stream is not None:
            JsonRpcProtocol.write_message(self.out_stream, resp)

    def _discover_project_files(self, target_path: Path) -> list[Path]:
        target_path = target_path.resolve()
        # 1. Walk up looking for a project file
        cur = target_path.parent if target_path.is_file() else target_path
        while cur != cur.parent:
            psprojs = [p for p in cur.glob("*") if is_ps_project_file(p)]
            if psprojs:
                try:
                    cfg = load_project(psprojs[0], stdlib_dir=self.stdlib_dir)
                    return [f.resolve() for f in cfg.source_files]
                except Exception:
                    pass
            cur = cur.parent

        # 2. Check sibling files and workspace root
        files: set[Path] = set()
        if target_path.parent.exists():
            for p in target_path.parent.glob("*"):
                if p.is_file() and is_ps_source_file(p):
                    files.add(p.resolve())

        if self.workspace_root and self.workspace_root.exists():
            try:
                for p in self.workspace_root.rglob("*"):
                    if not p.is_file():
                        continue
                    parts = p.parts
                    if any(ig in parts for ig in ("dist", ".venv", "venv", "__pycache__", ".git", "node_modules")):
                        continue
                    if is_ps_source_file(p):
                        files.add(p.resolve())
            except Exception:
                pass

        if target_path.is_file():
            files.add(target_path)
        return sorted(files)

    def analyze_document(self, uri: str, text: str) -> DocumentState:
        target_path = uri_to_path(uri)
        project_files = self._discover_project_files(target_path)

        diag = DiagnosticEngine()
        project_units: list[CompilationUnit] = []
        active_unit: CompilationUnit | None = None
        active_tokens: list[Token] | None = None

        for idx, file_path in enumerate(project_files):
            file_uri = path_to_uri(file_path)
            is_active = (file_uri == uri or file_path == target_path)

            if is_active:
                content = text
            elif file_uri in self.documents:
                content = self.documents[file_uri].text
            else:
                try:
                    content = file_path.read_text(encoding="utf-8")
                except Exception:
                    continue

            file_diag = DiagnosticEngine()
            tokens = Lexer(content, file_id=idx, ps_filename=str(file_path), diagnostics=file_diag).tokenize()
            unit = Parser.from_source(
                content, file_id=idx, ps_filename=str(file_path), diagnostics=file_diag
            ).parse_compilation_unit()
            project_units.append(unit)

            if is_active:
                active_unit = unit
                active_tokens = tokens
                for d in file_diag.diagnostics:
                    diag.diagnostics.append(d)

        # Fallback if active document wasn't in project_files
        if active_unit is None:
            active_tokens = Lexer(text, file_id=0, ps_filename=str(target_path), diagnostics=diag).tokenize()
            active_unit = Parser.from_source(
                text, file_id=0, ps_filename=str(target_path), diagnostics=diag
            ).parse_compilation_unit()
            project_units.append(active_unit)

        all_units = list(self.stdlib_units) + project_units
        symtab = GlobalSymbolTable(default_assembly_name="Workspace")
        if not diag.has_errors():
            analyze_compilation_units(all_units, symtab=symtab, diagnostics=diag, assembly_name="Workspace")

        state = DocumentState(
            uri=uri,
            text=text,
            unit=active_unit,
            tokens=active_tokens,
            project_units=all_units,
            symtab=symtab,
            diagnostics=diag,
        )
        self.documents[uri] = state

        # Publish diagnostics for the active document only
        lsp_diags: list[dict[str, object]] = []
        for d in diag.diagnostics:
            span = d.span
            if span.ps_filename not in (uri, str(target_path), str(target_path.resolve())):
                continue
            start_line = max(0, span.start_line - 1)
            start_col = max(0, span.start_col - 1)
            end_line = max(0, span.end_line - 1)
            end_col = max(0, span.end_col - 1)
            msg = d.message
            if d.hint:
                msg = f"{msg}\nHint: {d.hint}"
            lsp_diags.append({
                "range": {
                    "start": {"line": start_line, "character": start_col},
                    "end": {"line": end_line, "character": end_col},
                },
                "severity": 1,
                "code": d.code or "PSC",
                "source": "psc",
                "message": msg,
            })

        self.send_notification("textDocument/publishDiagnostics", {
            "uri": uri,
            "diagnostics": lsp_diags,
        })
        return state

    def handle_request(self, message: dict[str, object]) -> dict[str, object] | None:
        req_id = message.get("id")
        method = message.get("method")
        params = message.get("params", {})
        if not isinstance(params, dict):
            params = {}

        if method == "initialize":
            root_uri = params.get("rootUri")
            if root_uri and isinstance(root_uri, str):
                self.workspace_root = uri_to_path(root_uri)
            return JsonRpcProtocol.make_response(req_id, {
                "capabilities": {
                    "textDocumentSync": 1,
                    "hoverProvider": True,
                    "definitionProvider": True,
                    "typeDefinitionProvider": True,
                    "completionProvider": {
                        "triggerCharacters": [".", " "],
                        "resolveProvider": False,
                    },
                },
                "serverInfo": {
                    "name": "pythonsharp-lsp",
                    "version": __version__,
                },
            })

        if method == "shutdown":
            return JsonRpcProtocol.make_response(req_id, None)

        if method == "textDocument/hover":
            doc_uri = str(params.get("textDocument", {}).get("uri", ""))
            pos = params.get("position", {})
            line = int(pos.get("line", 0)) + 1
            character = int(pos.get("character", 0)) + 1
            hover_text = self._compute_hover(doc_uri, line, character)
            if hover_text:
                return JsonRpcProtocol.make_response(req_id, {
                    "contents": {
                        "kind": "markdown",
                        "value": hover_text,
                    }
                })
            return JsonRpcProtocol.make_response(req_id, None)

        if method in ("textDocument/definition", "textDocument/typeDefinition"):
            doc_uri = str(params.get("textDocument", {}).get("uri", ""))
            pos = params.get("position", {})
            line = int(pos.get("line", 0)) + 1
            character = int(pos.get("character", 0)) + 1
            is_type_def = (method == "textDocument/typeDefinition")
            loc = self._compute_definition(doc_uri, line, character, is_type_def=is_type_def)
            return JsonRpcProtocol.make_response(req_id, loc)

        if method == "textDocument/completion":
            items = []
            for kw in sorted(PSC_KEYWORDS):
                items.append({
                    "label": kw,
                    "kind": 14,
                    "detail": "keyword",
                })
            for ct in sorted(CORE_TYPES):
                items.append({
                    "label": ct,
                    "kind": 7,
                    "detail": f"PythonSharp.Core.{ct}",
                })
            return JsonRpcProtocol.make_response(req_id, {
                "isIncomplete": False,
                "items": items,
            })

        return JsonRpcProtocol.make_response(req_id, None)

    def handle_notification(self, message: dict[str, object]) -> None:
        method = message.get("method")
        params = message.get("params", {})
        if not isinstance(params, dict):
            params = {}

        if method == "initialized":
            return

        if method == "exit":
            self.is_running = False
            return

        if method == "textDocument/didOpen":
            td = params.get("textDocument", {})
            uri = str(td.get("uri", ""))
            text = str(td.get("text", ""))
            self.analyze_document(uri, text)
            return

        if method == "textDocument/didChange":
            td = params.get("textDocument", {})
            uri = str(td.get("uri", ""))
            changes = params.get("contentChanges", [])
            if changes and isinstance(changes, list) and isinstance(changes[0], dict):
                text = str(changes[0].get("text", ""))
                self.analyze_document(uri, text)
            return

        if method == "textDocument/didClose":
            td = params.get("textDocument", {})
            uri = str(td.get("uri", ""))
            self.documents.pop(uri, None)
            self.send_notification("textDocument/publishDiagnostics", {
                "uri": uri,
                "diagnostics": [],
            })
            return

    def _find_token_at(self, state: DocumentState, line: int, col: int) -> Token | None:
        if not state.tokens:
            return None
        for tok in state.tokens:
            if tok.span.start_line == line and tok.span.start_col <= col <= tok.span.end_col:
                return tok
        return None

    def _compute_hover(self, uri: str, line: int, col: int) -> str | None:
        state = self.documents.get(uri)
        if state is None or state.unit is None:
            return None

        # 1. Hover on import statement
        for imp in state.unit.imports:
            if imp.span.start_line <= line <= imp.span.end_line:
                ns_str = ".".join(imp.path)
                # Find declaring unit
                loc_desc = ""
                for u in state.project_units:
                    if u.namespace == imp.path:
                        loc_desc = f"\n\n*Declared in `{u.ps_filename}`*"
                        break
                return f"```csharp\nnamespace {ns_str}\n```{loc_desc}"

        tok = self._find_token_at(state, line, col)
        if tok is None:
            return None

        val = tok.lexeme
        if tok.kind in (TokenKind.CLASS, TokenKind.INTERFACE, TokenKind.RECORD, TokenKind.STRUCT):
            return f"**keyword** `{val}`"
        if tok.kind in (TokenKind.PUBLIC, TokenKind.PRIVATE, TokenKind.PROTECTED, TokenKind.INTERNAL):
            return f"**access modifier** `{val}`"

        # 2. Hover on namespace segment
        for u in state.project_units:
            if val in u.namespace:
                ns_str = ".".join(u.namespace)
                return f"```csharp\nnamespace {ns_str}\n```\n*Declared in `{u.ps_filename}`*"

        # 3. Hover on type (symtab)
        symtab = state.symtab
        if symtab and val in symtab.short_name_index:
            type_sym = symtab.short_name_index[val][0]
            decl = type_sym.ast_node
            k_name = type_sym.kind.name.lower()
            if type_sym.is_record and decl.primary_ctor_params:
                params_str = ", ".join(f"{p.type_ref.display_name()} {p.name}" for p in decl.primary_ctor_params)
                sig = f"public record {type_sym.name}({params_str})"
            else:
                tp_str = f"<{', '.join(type_sym.type_params)}>" if type_sym.type_params else ""
                sig = f"public {k_name} {type_sym.name}{tp_str}"
            loc = "PythonSharp Core Standard Library" if type_sym.is_ambient_stub else f"Declared in `{type_sym.unit.ps_filename}`"
            return f"```csharp\n{sig}\n```\n*{loc}*"

        # 4. Hover on members in symtab
        if symtab:
            for type_sym in symtab.types_by_id.values():
                if val in type_sym.members_by_name:
                    mem = type_sym.members_by_name[val][0]
                    kind_desc = mem.kind
                    type_str = mem.resolved_type.qualified_name if mem.resolved_type else ""
                    return f"```csharp\n({kind_desc}) {type_str} {type_sym.name}.{val}\n```\n*Declared in `{type_sym.unit.ps_filename}`*"

        if val in CORE_TYPES:
            return f"```csharp\nCore type {val}\n```\n*Mapped to Python runtime standard library*"

        return None

    def _compute_definition(
        self, uri: str, line: int, col: int, is_type_def: bool = False
    ) -> dict[str, object] | None:
        state = self.documents.get(uri)
        if state is None or state.unit is None:
            return None

        # 1. Navigation on import statements: `using PythonSharp.Core;`
        for imp in state.unit.imports:
            if imp.span.start_line <= line <= imp.span.end_line:
                for u in state.project_units:
                    if u.namespace == imp.path:
                        span = u.namespace_span or SourceSpan(
                            file_id=u.file_id,
                            ps_filename=u.ps_filename,
                            start_line=1,
                            start_col=1,
                            end_line=1,
                            end_col=len(".".join(imp.path)) + 12,
                        )
                        return {
                            "uri": path_to_uri(u.ps_filename),
                            "range": span_to_range(span),
                        }

        tok = self._find_token_at(state, line, col)
        if tok is None:
            return None

        val = tok.lexeme

        # 2. Namespace token navigation: e.g. `Core` in `namespace PythonSharp.Core;`
        for u in state.project_units:
            if val in u.namespace:
                span = u.namespace_span or SourceSpan(
                    file_id=u.file_id,
                    ps_filename=u.ps_filename,
                    start_line=1,
                    start_col=1,
                    end_line=1,
                    end_col=10,
                )
                return {
                    "uri": path_to_uri(u.ps_filename),
                    "range": span_to_range(span),
                }

        symtab = state.symtab
        if symtab is None:
            return None

        # 3. If Type Definition requested on variable / field / member
        if is_type_def:
            for type_sym in symtab.types_by_id.values():
                if val in type_sym.members_by_name:
                    mem = type_sym.members_by_name[val][0]
                    target_tname = mem.resolved_type.qualified_name.split(".")[-1] if mem.resolved_type else None
                    if target_tname and target_tname in symtab.short_name_index:
                        t_sym = symtab.short_name_index[target_tname][0]
                        return {
                            "uri": path_to_uri(t_sym.unit.ps_filename),
                            "range": span_to_range(t_sym.span),
                        }

        # 4. Type Name Navigation (cross-file & stdlib)
        if val in symtab.short_name_index:
            candidates = symtab.short_name_index[val]
            chosen = candidates[0]
            # Match current namespace or imports if ambiguous
            for c in candidates:
                if list(c.namespace) in [imp.path for imp in state.unit.imports] or list(c.namespace) == state.unit.namespace:
                    chosen = c
                    break
            return {
                "uri": path_to_uri(chosen.unit.ps_filename),
                "range": span_to_range(chosen.span),
            }

        # 5. Member / Parameter Navigation
        # Check current unit's types and primary constructor parameters
        for type_decl in state.unit.types:
            for member in type_decl.members:
                if getattr(member, "name", None) == val:
                    m_span = getattr(member, "span", None)
                    if m_span:
                        return {
                            "uri": path_to_uri(state.unit.ps_filename),
                            "range": span_to_range(m_span),
                        }
            for p in type_decl.primary_ctor_params:
                if p.name == val:
                    return {
                        "uri": path_to_uri(state.unit.ps_filename),
                        "range": span_to_range(p.span),
                    }

        # Check all registered members across symtab
        for type_sym in symtab.types_by_id.values():
            if val in type_sym.members_by_name:
                mem = type_sym.members_by_name[val][0]
                return {
                    "uri": path_to_uri(type_sym.unit.ps_filename),
                    "range": span_to_range(mem.span),
                }

        return None

    def serve(self) -> None:
        """Runs the main server loop, reading messages from `self.in_stream`."""
        while self.is_running:
            msg = JsonRpcProtocol.read_message(self.in_stream)
            if msg is None:
                break
            if "id" in msg:
                resp = self.handle_request(msg)
                if resp is not None and self.out_stream is not None:
                    JsonRpcProtocol.write_message(self.out_stream, resp)
            else:
                self.handle_notification(msg)
