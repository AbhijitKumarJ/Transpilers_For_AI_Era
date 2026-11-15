from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import unquote, urlparse

from psc.cli import _find_default_stdlib_dir
from psc.diagnostics import DiagnosticEngine, SourceSpan
from psc.frontend import (
    CatchClause,
    CompilationUnit,
    FieldDecl,
    ForEachStmt,
    ForStmt,
    Lexer,
    LocalVarStmt,
    MethodDecl,
    Parser,
    PropertyDecl,
    Stmt,
    Token,
    TokenKind,
    TypeKind,
    TypeRef,
    UsingResourceStmt,
)
from psc.lsp.protocol import JsonRpcProtocol
from psc.project import (
    find_stdlib_stubs,
    is_ps_project_file,
    is_ps_source_file,
    is_ps_stub_file,
    load_project,
    load_ps_config,
)
from psc.semantics import (
    AccessChecker,
    GlobalSymbolTable,
    LinqComprehensionFuser,
    MemberSymbol,
    OverloadResolver,
    PrimitiveResolver,
    SlotAndHierarchyAnalyzer,
    SymbolCollector,
    TypeChecker,
    TypeSymbol,
    analyze_compilation_units,
)
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
    "Bytes", "Complex",
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


def _format_surface_ladder(surface_level: int, canonical_api: str | None) -> str:
    descriptions = {
        1: "Surface 1 (Raw ABI — Python-native snake_case)",
        2: "Surface 2 (Idiomatic C# Bridge — PascalCase)",
        3: "Surface 3 (Enterprise C# Architecture)",
    }
    desc = descriptions.get(surface_level) if surface_level > 0 else None
    if not desc and not canonical_api:
        return ""
    lines = ["\n\n---"]
    if desc:
        lines.append(f"**Surface Tier:** `{desc}`")
    if canonical_api:
        lines.append(f"**Canonical Target:** `{canonical_api}`")
    return "\n".join(lines)


def _format_type_kind(kind: TypeKind) -> str:
    kind_names = {
        TypeKind.CLASS: "class",
        TypeKind.PRIMITIVE_CLASS: "primitive class",
        TypeKind.STRUCT: "struct",
        TypeKind.PRIMITIVE_STRUCT: "primitive struct",
        TypeKind.INTERFACE: "interface",
        TypeKind.PRIMITIVE_INTERFACE: "primitive interface",
        TypeKind.RECORD: "record",
        TypeKind.ENUM: "enum",
    }
    return kind_names.get(kind, kind.name.lower().replace("_", " "))


def _collect_scoped_locals(stmt: Stmt | Any) -> list[tuple[str, str, SourceSpan, TypeRef | None]]:
    locals_found: list[tuple[str, str, SourceSpan, TypeRef | None]] = []
    if isinstance(stmt, LocalVarStmt):
        tr = stmt.type_ref
        if tr is None and stmt.initializer is not None:
            if hasattr(stmt.initializer, "data") and isinstance(stmt.initializer.data, dict) and "type_ref" in stmt.initializer.data:
                tr = stmt.initializer.data["type_ref"]
            elif hasattr(stmt.initializer, "resolved_type") and stmt.initializer.resolved_type:
                rt_str = str(stmt.initializer.resolved_type)
                if rt_str and rt_str != "var":
                    tr = TypeRef(span=stmt.span, path=[rt_str])
        td = tr.display_name() if tr else (str(getattr(stmt.initializer, "resolved_type", None) or "var") if stmt.initializer else "var")
        locals_found.append((stmt.name, td, stmt.span, tr))
    elif isinstance(stmt, ForEachStmt):
        td = stmt.type_ref.display_name() if stmt.type_ref else "var"
        locals_found.append((stmt.item_name, td, stmt.span, stmt.type_ref))
    elif isinstance(stmt, ForStmt):
        if stmt.initializer and isinstance(stmt.initializer, LocalVarStmt):
            tr = stmt.initializer.type_ref
            if tr is None and stmt.initializer.initializer is not None:
                if hasattr(stmt.initializer.initializer, "data") and isinstance(stmt.initializer.initializer.data, dict) and "type_ref" in stmt.initializer.initializer.data:
                    tr = stmt.initializer.initializer.data["type_ref"]
                elif hasattr(stmt.initializer.initializer, "resolved_type") and stmt.initializer.initializer.resolved_type:
                    rt_str = str(stmt.initializer.initializer.resolved_type)
                    if rt_str and rt_str != "var":
                        tr = TypeRef(span=stmt.initializer.span, path=[rt_str])
            td = tr.display_name() if tr else (str(getattr(stmt.initializer.initializer, "resolved_type", None) or "var") if stmt.initializer.initializer else "var")
            locals_found.append((stmt.initializer.name, td, stmt.initializer.span, tr))
    elif isinstance(stmt, UsingResourceStmt):
        tr = stmt.type_ref
        if tr is None and stmt.initializer is not None:
            if hasattr(stmt.initializer, "data") and isinstance(stmt.initializer.data, dict) and "type_ref" in stmt.initializer.data:
                tr = stmt.initializer.data["type_ref"]
            elif hasattr(stmt.initializer, "resolved_type") and stmt.initializer.resolved_type:
                rt_str = str(stmt.initializer.resolved_type)
                if rt_str and rt_str != "var":
                    tr = TypeRef(span=stmt.span, path=[rt_str])
        td = tr.display_name() if tr else (str(getattr(stmt.initializer, "resolved_type", None) or "var") if stmt.initializer else "var")
        locals_found.append((stmt.name, td, stmt.span, tr))
    elif isinstance(stmt, CatchClause):
        if stmt.bind_name:
            td = stmt.exception_type.display_name() if stmt.exception_type else "Exception"
            locals_found.append((stmt.bind_name, td, stmt.span, stmt.exception_type))

    # Recurse children
    for attr in ("body", "then_branch", "else_branch", "try_block", "finally_block"):
        sub = getattr(stmt, attr, None)
        if sub is not None:
            locals_found.extend(_collect_scoped_locals(sub))
    if hasattr(stmt, "catches") and stmt.catches:
        for c in stmt.catches:
            locals_found.extend(_collect_scoped_locals(c))
    if hasattr(stmt, "statements") and stmt.statements:
        for s in stmt.statements:
            locals_found.extend(_collect_scoped_locals(s))
    if hasattr(stmt, "sections") and stmt.sections:
        for sec in stmt.sections:
            if hasattr(sec, "statements"):
                for s in sec.statements:
                    locals_found.extend(_collect_scoped_locals(s))
    return locals_found


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

    def __init__(
        self,
        in_stream: BinaryIO | None = None,
        out_stream: BinaryIO | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        self.in_stream = in_stream or sys.stdin.buffer
        self.out_stream = out_stream or sys.stdout.buffer
        self.documents: dict[str, DocumentState] = {}
        self.workspace_root: Path | None = workspace_root.resolve() if workspace_root else None
        self.is_running = True
        self.notifications_log: list[dict[str, object]] = []

        self.stdlib_dir: Path | None = _find_default_stdlib_dir()
        self.stdlib_units: list[CompilationUnit] = []
        self._load_stdlib()

        # Performance caches for instantaneous LSP responsiveness
        self._stub_cache: dict[Path, tuple[float, CompilationUnit]] = {}
        self._source_cache: dict[Path, tuple[float, CompilationUnit, list[Token]]] = {}
        self._base_stub_symtab: GlobalSymbolTable | None = None
        self._base_stub_files: set[Path] = set()
        self._base_stub_units: list[CompilationUnit] = []
        self._project_discovery_cache: dict[Path, tuple[float, list[Path], list[Path]]] = {}

    def _load_stdlib(self) -> None:
        if not self.stdlib_dir or not self.stdlib_dir.exists():
            return
        diag = DiagnosticEngine()
        cfg = load_ps_config(self.workspace_root)
        stub_paths = find_stdlib_stubs(self.stdlib_dir, config=cfg)
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

    def _discover_project_files(self, target_path: Path) -> tuple[list[Path], list[Path]]:
        target_path = target_path.resolve()
        # 1. Walk up looking for a project file
        cur = target_path.parent if target_path.is_file() else target_path
        while cur != cur.parent:
            psprojs = [p for p in cur.glob("*") if is_ps_project_file(p)]
            if psprojs:
                psproj = psprojs[0]
                try:
                    mtime = psproj.stat().st_mtime
                    if psproj in self._project_discovery_cache and self._project_discovery_cache[psproj][0] == mtime:
                        return self._project_discovery_cache[psproj][1], self._project_discovery_cache[psproj][2]

                    cfg = load_project(psproj, stdlib_dir=self.stdlib_dir)
                    sources: set[Path] = {f.resolve() for f in cfg.source_files}
                    stubs: set[Path] = {f.resolve() for f in cfg.stub_files}
                    if cfg.project_references:
                        from psc.cli import resolve_project_dependencies

                        deps = resolve_project_dependencies(cfg, stdlib_dir=self.stdlib_dir)
                        for dep in deps:
                            dep_dps = [d.resolve() for d in dep.out_dir.rglob("*.d.ps")] if dep.out_dir.exists() else []
                            if dep_dps:
                                stubs.update(dep_dps)
                            else:
                                for sf in dep.source_files:
                                    sources.add(sf.resolve())
                    res_sources = sorted(sources)
                    res_stubs = sorted(stubs)
                    self._project_discovery_cache[psproj] = (mtime, res_sources, res_stubs)
                    return res_sources, res_stubs
                except Exception:
                    pass
            cur = cur.parent

        # 2. Check sibling files and workspace root
        sources: set[Path] = set()
        stubs: set[Path] = set()
        if target_path.parent.exists():
            for p in target_path.parent.glob("*"):
                if p.is_file():
                    if is_ps_source_file(p):
                        sources.add(p.resolve())
                    elif is_ps_stub_file(p):
                        stubs.add(p.resolve())

        for sdir in [target_path.parent / ".ps-stubs", target_path.parent / "typings"]:
            if sdir.is_dir():
                for p in sdir.rglob("*"):
                    if p.is_file() and is_ps_stub_file(p):
                        stubs.add(p.resolve())

        if self.workspace_root and self.workspace_root.exists():
            try:
                import os
                ignored = {
                    "dist", ".venv", "venv", "__pycache__", ".git", "node_modules",
                    ".ps-stubs", "typings", ".pytest_cache", "build"
                }
                for root, dirs, files in os.walk(self.workspace_root):
                    dirs[:] = [d for d in dirs if d not in ignored and not d.startswith(".")]
                    for f in files:
                        p = Path(root) / f
                        if is_ps_source_file(p):
                            sources.add(p.resolve())
                        elif is_ps_stub_file(p):
                            stubs.add(p.resolve())
            except Exception:
                pass

        if target_path.is_file():
            if is_ps_stub_file(target_path):
                stubs.add(target_path)
            else:
                sources.add(target_path)

        for d_uri in self.documents:
            d_path = uri_to_path(d_uri)
            if is_ps_stub_file(d_path):
                stubs.add(d_path)
            elif is_ps_source_file(d_path):
                sources.add(d_path)
        return sorted(sources), sorted(stubs)

    def analyze_document(self, uri: str, text: str) -> DocumentState:
        target_path = uri_to_path(uri)
        project_files, stub_files = self._discover_project_files(target_path)

        # Dynamic on-demand stubs from referenced namespaces in active text
        ref_ns: set[str] = set()
        ns_regex = re.compile(r"\b(?:using|extern\s+using)\s+([A-Za-z0-9_.]+)\s*;")
        for m in ns_regex.finditer(text):
            ref_ns.add(m.group(1).strip())
        if self.stdlib_dir and ref_ns:
            ps_cfg = load_ps_config(target_path.parent)
            on_demand = find_stdlib_stubs(self.stdlib_dir, referenced_namespaces=ref_ns, config=ps_cfg)
            for s in on_demand:
                s_res = s.resolve()
                if s_res not in stub_files:
                    stub_files.append(s_res)

        stub_files_set = set(stub_files)
        already_loaded = {
            Path(u.ps_filename).resolve() for u in self.stdlib_units if u.ps_filename
        }

        # Check or build base stub symbol table
        if self._base_stub_symtab is None or stub_files_set != self._base_stub_files:
            stub_units: list[CompilationUnit] = []
            for idx, stub_file in enumerate(stub_files):
                if stub_file in already_loaded:
                    continue
                try:
                    s_uri = path_to_uri(stub_file)
                    if s_uri in self.documents:
                        s_text = self.documents[s_uri].text
                        s_mtime = float(hash(s_text))
                    else:
                        s_text = stub_file.read_text(encoding="utf-8")
                        s_mtime = stub_file.stat().st_mtime

                    if stub_file in self._stub_cache and self._stub_cache[stub_file][0] == s_mtime:
                        s_unit = self._stub_cache[stub_file][1]
                    else:
                        s_unit = Parser.from_source(
                            s_text,
                            file_id=-(len(self.stdlib_units) + idx + 1),
                            ps_filename=str(stub_file),
                        ).parse_compilation_unit()
                        s_unit.is_ambient_stub = True
                        self._stub_cache[stub_file] = (s_mtime, s_unit)
                    stub_units.append(s_unit)
                except Exception:
                    pass

            base_symtab = GlobalSymbolTable(default_assembly_name="Workspace")
            base_diag = DiagnosticEngine()
            SymbolCollector(base_symtab, base_diag).collect_all(
                list(self.stdlib_units) + stub_units, assembly_name="Workspace"
            )
            try:
                SlotAndHierarchyAnalyzer(base_symtab, base_diag).analyze_all(stub_units)
                PrimitiveResolver(base_symtab, base_diag).resolve_all(stub_units)
            except Exception:
                pass

            self._base_stub_symtab = base_symtab
            self._base_stub_files = stub_files_set
            self._base_stub_units = stub_units

        # Fast clone of base stub symbols (4ms)
        symtab = self._base_stub_symtab.clone()

        diag = DiagnosticEngine()
        project_units: list[CompilationUnit] = []
        active_unit: CompilationUnit | None = None
        active_tokens: list[Token] | None = None

        for idx, file_path in enumerate(project_files):
            file_uri = path_to_uri(file_path)
            is_active = (file_uri == uri or file_path == target_path)

            if is_active:
                file_diag = DiagnosticEngine()
                tokens = Lexer(text, file_id=idx, ps_filename=str(file_path), diagnostics=file_diag).tokenize()
                unit = Parser.from_source(
                    text, file_id=idx, ps_filename=str(file_path), diagnostics=file_diag
                ).parse_compilation_unit()
                project_units.append(unit)
                active_unit = unit
                active_tokens = tokens
                for d in file_diag.diagnostics:
                    diag.diagnostics.append(d)
            elif file_uri in self.documents:
                doc_text = self.documents[file_uri].text
                file_diag = DiagnosticEngine()
                tokens = Lexer(doc_text, file_id=idx, ps_filename=str(file_path), diagnostics=file_diag).tokenize()
                unit = Parser.from_source(
                    doc_text, file_id=idx, ps_filename=str(file_path), diagnostics=file_diag
                ).parse_compilation_unit()
                project_units.append(unit)
            else:
                try:
                    mtime = file_path.stat().st_mtime
                    if file_path in self._source_cache and self._source_cache[file_path][0] == mtime:
                        _, unit, tokens = self._source_cache[file_path]
                    else:
                        content = file_path.read_text(encoding="utf-8")
                        file_diag = DiagnosticEngine()
                        tokens = Lexer(content, file_id=idx, ps_filename=str(file_path), diagnostics=file_diag).tokenize()
                        unit = Parser.from_source(
                            content, file_id=idx, ps_filename=str(file_path), diagnostics=file_diag
                        ).parse_compilation_unit()
                        self._source_cache[file_path] = (mtime, unit, tokens)
                    project_units.append(unit)
                except Exception:
                    continue

        # Fallback if active document wasn't in project_files
        if active_unit is None:
            active_tokens = Lexer(text, file_id=0, ps_filename=str(target_path), diagnostics=diag).tokenize()
            active_unit = Parser.from_source(
                text, file_id=0, ps_filename=str(target_path), diagnostics=diag
            ).parse_compilation_unit()
            project_units.append(active_unit)

        sem_diag = DiagnosticEngine()
        # Always run SymbolCollector first across project units to populate symtab completely
        SymbolCollector(symtab, sem_diag).collect_all(project_units, assembly_name="Workspace")

        try:
            SlotAndHierarchyAnalyzer(symtab, sem_diag).analyze_all(project_units)
            PrimitiveResolver(symtab, sem_diag).resolve_all(project_units)
        except Exception:
            pass

        try:
            AccessChecker(symtab, sem_diag).check_all(project_units)
            OverloadResolver(symtab, sem_diag).resolve_all(project_units)
            LinqComprehensionFuser(symtab).fuse_all(project_units)
            TypeChecker(symtab, sem_diag).verify_all(project_units)
        except Exception:
            pass

        if not diag.has_errors():
            for d in sem_diag.diagnostics:
                diag.diagnostics.append(d)

        all_units = list(self.stdlib_units) + self._base_stub_units + project_units

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
            matches_file = False
            if span.ps_filename in (uri, str(target_path), str(target_path.resolve())):
                matches_file = True
            else:
                try:
                    if Path(span.ps_filename).resolve() == target_path.resolve():
                        matches_file = True
                except Exception:
                    pass
            if not matches_file:
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
                    "documentFormattingProvider": True,
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

        if method == "textDocument/formatting":
            doc_uri = str(params.get("textDocument", {}).get("uri", ""))
            options = params.get("options", {})
            tab_size = int(options.get("tabSize", 4))
            insert_spaces = bool(options.get("insertSpaces", True))
            state = self.documents.get(doc_uri)
            if state and state.text:
                from psc.formatter import format_code

                formatted = format_code(state.text, tab_size=tab_size, insert_spaces=insert_spaces)
                if formatted != state.text:
                    lines = state.text.split("\n")
                    last_line = max(0, len(lines) - 1)
                    last_col = len(lines[last_line]) if lines else 0
                    return JsonRpcProtocol.make_response(req_id, [
                        {
                            "range": {
                                "start": {"line": 0, "character": 0},
                                "end": {"line": last_line, "character": last_col},
                            },
                            "newText": formatted,
                        }
                    ])
            return JsonRpcProtocol.make_response(req_id, [])

        if method == "textDocument/completion":
            doc_uri = str(params.get("textDocument", {}).get("uri", ""))
            pos = params.get("position", {})
            line = int(pos.get("line", 0))
            character = int(pos.get("character", 0))
            items = self._compute_completion(doc_uri, line, character)
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
        tok, _ = self._find_token_and_index(state, line, col)
        return tok

    def _find_token_and_index(self, state: DocumentState, line: int, col: int) -> tuple[Token | None, int]:
        if not state.tokens:
            return None, -1
        # Prefer token where col is strictly inside [start_col, end_col) to avoid boundary overlap
        for idx, tok in enumerate(state.tokens):
            if tok.span.start_line == line and tok.span.start_col <= col < tok.span.end_col:
                return tok, idx
        for idx, tok in enumerate(state.tokens):
            if tok.span.start_line == line and tok.span.start_col <= col <= tok.span.end_col:
                return tok, idx
        return None, -1

    def _resolve_local_symbol(
        self, unit: CompilationUnit, line: int, name: str
    ) -> tuple[str, str, SourceSpan, TypeRef | None] | None:
        """Finds a parameter or local variable in the active scope enclosing `line`."""
        for t in unit.types:
            if not (t.span.start_line <= line <= t.span.end_line):
                continue
            for m in t.members:
                if hasattr(m, "span") and m.span.start_line <= line <= m.span.end_line:
                    # 1. Method / Constructor parameters
                    if hasattr(m, "params"):
                        for p in m.params:
                            if p.name == name:
                                return ("parameter", p.type_ref.display_name(), p.span, p.type_ref)
                    # 2. Local variables in method body
                    body = getattr(m, "body", None)
                    if body is not None:
                        all_locs = _collect_scoped_locals(body)
                        matching = [loc for loc in all_locs if loc[0] == name and loc[2].start_line <= line]
                        if matching:
                            best = max(matching, key=lambda loc: loc[2].start_line)
                            return ("local variable", best[1], best[2], best[3])
                    # Property accessors
                    if hasattr(m, "accessors") and m.accessors:
                        for acc in m.accessors:
                            if acc.span.start_line <= line <= acc.span.end_line and acc.body:
                                acc_locs = _collect_scoped_locals(acc.body)
                                matching = [loc for loc in acc_locs if loc[0] == name and loc[2].start_line <= line]
                                if matching:
                                    best = max(matching, key=lambda loc: loc[2].start_line)
                                    return ("local variable", best[1], best[2], best[3])

            # 3. Primary constructor parameters (for records)
            if hasattr(t, "primary_ctor_params") and t.primary_ctor_params:
                for p in t.primary_ctor_params:
                    if p.name == name:
                        return ("parameter", p.type_ref.display_name(), p.span, p.type_ref)
        return None

    def _choose_best_type_candidate(
        self, candidates: list[TypeSymbol], unit: CompilationUnit
    ) -> TypeSymbol:
        # 1. Exact namespace match
        for c in candidates:
            if tuple(c.namespace) == tuple(unit.namespace):
                return c
        # 2. Match imported namespaces
        import_paths = [tuple(imp.path) for imp in unit.imports]
        for c in candidates:
            if tuple(c.namespace) in import_paths:
                return c
        # 3. Non-ambient (user code) before ambient stub
        for c in candidates:
            if not c.is_ambient_stub:
                return c
        # 4. Fallback
        return candidates[0]

    def _format_type_hover(self, type_sym: TypeSymbol) -> str:
        decl = type_sym.ast_node
        k_name = _format_type_kind(type_sym.kind)
        if type_sym.is_record and decl.primary_ctor_params:
            params_str = ", ".join(f"{p.type_ref.display_name()} {p.name}" for p in decl.primary_ctor_params)
            sig = f"public record {type_sym.name}({params_str})"
        else:
            tp_str = f"<{', '.join(type_sym.type_params)}>" if type_sym.type_params else ""
            sig = f"public {k_name} {type_sym.name}{tp_str}"
        loc = "PythonSharp Core Standard Library" if type_sym.is_ambient_stub else f"Declared in `{type_sym.unit.ps_filename}`"
        ladder = _format_surface_ladder(type_sym.surface_level, type_sym.canonical_api)
        return f"```csharp\n{sig}\n```\n*{loc}*{ladder}"

    def _format_member_hover(self, type_sym: TypeSymbol, mem: MemberSymbol) -> str:
        kind_desc = mem.kind
        if hasattr(mem, "ast_node") and hasattr(mem.ast_node, "type_ref") and mem.ast_node.type_ref:
            type_str = mem.ast_node.type_ref.display_name()
        elif mem.resolved_type:
            base = mem.resolved_type.qualified_name.split(".")[-1]
            if mem.resolved_type.type_args:
                args_str = ", ".join(a.qualified_name.split(".")[-1] for a in mem.resolved_type.type_args)
                type_str = f"{base}<{args_str}>"
            else:
                type_str = base
        else:
            type_str = ""

        eff_surface = mem.surface_level or type_sym.surface_level
        eff_canonical = mem.canonical_api or type_sym.canonical_api
        ladder = _format_surface_ladder(eff_surface, eff_canonical)

        if hasattr(mem, "ast_node") and isinstance(mem.ast_node, MethodDecl) and mem.ast_node.params:
            params_str = ", ".join(f"{p.type_ref.display_name()} {p.name}" for p in mem.ast_node.params)
            sig = f"({kind_desc}) {type_str} {type_sym.name}.{mem.name}({params_str})"
        else:
            sig = f"({kind_desc}) {type_str} {type_sym.name}.{mem.name}"

        loc = "PythonSharp Core Standard Library" if type_sym.is_ambient_stub else f"Declared in `{type_sym.unit.ps_filename}`"
        return f"```csharp\n{sig}\n```\n*{loc}*{ladder}"

    def _format_ast_member_hover(self, type_name: str, ps_filename: str, member: Any) -> str:
        if isinstance(member, MethodDecl):
            params_str = ", ".join(f"{p.type_ref.display_name()} {p.name}" for p in member.params)
            if member.is_constructor:
                sig = f"public {type_name}({params_str})"
            else:
                ret = member.return_type.display_name() if member.return_type else "void"
                tp_str = f"<{', '.join(member.type_params)}>" if member.type_params else ""
                sig = f"(method) {ret} {type_name}.{member.name}{tp_str}({params_str})"
        elif isinstance(member, PropertyDecl):
            ret = member.type_ref.display_name() if member.type_ref else "var"
            sig = f"(property) {ret} {type_name}.{member.name}"
        elif isinstance(member, FieldDecl):
            ret = member.type_ref.display_name() if member.type_ref else "var"
            sig = f"(field) {ret} {type_name}.{member.name}"
        else:
            sig = f"{type_name}.{getattr(member, 'name', '')}"
        return f"```csharp\n{sig}\n```\n*Declared in `{ps_filename}`*"

    def _compute_hover(self, uri: str, line: int, col: int) -> str | None:
        state = self.documents.get(uri)
        if state is None or state.unit is None:
            return None

        # 1. Hover on import statement
        for imp in state.unit.imports:
            if imp.span.start_line <= line <= imp.span.end_line:
                ns_str = ".".join(imp.path)
                loc_desc = ""
                for u in state.project_units:
                    if u.namespace == imp.path:
                        loc_desc = f"\n\n*Declared in `{u.ps_filename}`*"
                        break
                return f"```csharp\nnamespace {ns_str}\n```{loc_desc}"

        tok, tok_idx = self._find_token_and_index(state, line, col)
        if tok is None:
            return None

        val = tok.lexeme
        if tok.kind in (TokenKind.CLASS, TokenKind.INTERFACE, TokenKind.RECORD, TokenKind.STRUCT):
            return f"**keyword** `{val}`"
        if tok.kind in (TokenKind.PUBLIC, TokenKind.PRIVATE, TokenKind.PROTECTED, TokenKind.INTERNAL):
            return f"**access modifier** `{val}`"

        prev_tok = state.tokens[tok_idx - 1] if tok_idx > 0 else None
        prev2_tok = state.tokens[tok_idx - 2] if tok_idx > 1 else None

        # Hover on 'this'
        if val == "this":
            enc_t = next((t for t in state.unit.types if t.span.start_line <= line <= t.span.end_line), None)
            if enc_t:
                return f"```csharp\nthis: {enc_t.name}\n```\n*Declared in `{state.unit.ps_filename}`*"

        symtab = state.symtab

        # 2. Check if local variable or parameter
        local_sym = self._resolve_local_symbol(state.unit, line, val)
        if local_sym is not None:
            kind_label, type_disp, _, _ = local_sym
            return f"```csharp\n({kind_label}) {type_disp} {val}\n```"

        # 3. Member access: e.g. `receiver.val`
        if prev_tok and prev_tok.kind == TokenKind.DOT:
            receiver_type: TypeSymbol | None = None
            if prev2_tok:
                if prev2_tok.lexeme == "this":
                    enc_t = next((t for t in state.unit.types if t.span.start_line <= line <= t.span.end_line), None)
                    if enc_t and symtab:
                        receiver_type = symtab.lookup_type_in_context([enc_t.name], tuple(state.unit.namespace), state.unit.imports)
                elif prev2_tok.kind == TokenKind.IDENT:
                    rec_loc = self._resolve_local_symbol(state.unit, line, prev2_tok.lexeme)
                    if rec_loc and rec_loc[3] and symtab:
                        receiver_type = symtab.lookup_type_in_context(rec_loc[3].path, tuple(state.unit.namespace), state.unit.imports)
                        if not receiver_type and rec_loc[3].path[-1] in symtab.short_name_index:
                            receiver_type = symtab.short_name_index[rec_loc[3].path[-1]][0]
                    elif rec_loc and rec_loc[1] and symtab:
                        if rec_loc[1] in symtab.short_name_index:
                            receiver_type = symtab.short_name_index[rec_loc[1]][0]
                        else:
                            for sn, t_list in symtab.short_name_index.items():
                                if sn.lower() == rec_loc[1].lower():
                                    receiver_type = t_list[0]
                                    break
                    elif symtab:
                        receiver_type = symtab.lookup_type_in_context([prev2_tok.lexeme], tuple(state.unit.namespace), state.unit.imports)
                        if not receiver_type and prev2_tok.lexeme in symtab.short_name_index:
                            receiver_type = symtab.short_name_index[prev2_tok.lexeme][0]

            if receiver_type:
                visited_types: set[int] = set()
                type_queue = [receiver_type]
                while type_queue:
                    curr_type = type_queue.pop(0)
                    if curr_type.id.value in visited_types:
                        continue
                    visited_types.add(curr_type.id.value)
                    for base in curr_type.base_type_symbols:
                        if base.id.value not in visited_types:
                            type_queue.append(base)

                    if val in curr_type.members_by_name:
                        mem = curr_type.members_by_name[val][0]
                        return self._format_member_hover(curr_type, mem)
                    if curr_type.ast_node:
                        for m in curr_type.ast_node.members:
                            if getattr(m, "name", None) == val:
                                return self._format_ast_member_hover(curr_type.name, curr_type.unit.ps_filename, m)

            # Fallback across current unit
            for t_decl in state.unit.types:
                for m in t_decl.members:
                    if getattr(m, "name", None) == val:
                        return self._format_ast_member_hover(t_decl.name, state.unit.ps_filename, m)

            if symtab:
                for ts in symtab.types_by_id.values():
                    if val in ts.members_by_name:
                        mem = ts.members_by_name[val][0]
                        return self._format_member_hover(ts, mem)

        # 4. Type lookup in context
        if symtab:
            type_sym = symtab.lookup_type_in_context([val], tuple(state.unit.namespace), state.unit.imports)
            if type_sym is None and val in symtab.short_name_index:
                type_sym = self._choose_best_type_candidate(symtab.short_name_index[val], state.unit)
            if type_sym is not None:
                return self._format_type_hover(type_sym)

        # 5. Member on enclosing type (bare invocation without this.)
        enc_type = next((t for t in state.unit.types if t.span.start_line <= line <= t.span.end_line), None)
        if enc_type:
            for m in enc_type.members:
                if getattr(m, "name", None) == val:
                    return self._format_ast_member_hover(enc_type.name, state.unit.ps_filename, m)

        # 6. Fallback type search via short_name_index
        if symtab and val in symtab.short_name_index:
            candidates = symtab.short_name_index[val]
            chosen = self._choose_best_type_candidate(candidates, state.unit)
            return self._format_type_hover(chosen)

        # 7. Fallback member search across symtab
        if symtab:
            for type_sym in symtab.types_by_id.values():
                if val in type_sym.members_by_name:
                    mem = type_sym.members_by_name[val][0]
                    return self._format_member_hover(type_sym, mem)

        # 8. Namespace segment hover
        for u in state.project_units:
            if val in u.namespace:
                ns_str = ".".join(u.namespace)
                return f"```csharp\nnamespace {ns_str}\n```\n*Declared in `{u.ps_filename}`*"

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

        tok, tok_idx = self._find_token_and_index(state, line, col)
        if tok is None:
            return None

        val = tok.lexeme
        symtab = state.symtab

        # 2. Namespace declaration navigation: cursor is inside `namespace Foo.Bar;`
        if state.unit.namespace_span and state.unit.namespace_span.start_line <= line <= state.unit.namespace_span.end_line:
            for u in state.project_units:
                if val in u.namespace and u != state.unit:
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

        # 3. Check local variable or parameter
        local_sym = self._resolve_local_symbol(state.unit, line, val)
        if local_sym is not None:
            if is_type_def:
                type_ref = local_sym[3]
                if type_ref and symtab:
                    t_sym = symtab.lookup_type_in_context(type_ref.path, tuple(state.unit.namespace), state.unit.imports)
                    if t_sym:
                        return {
                            "uri": path_to_uri(t_sym.unit.ps_filename),
                            "range": span_to_range(t_sym.span),
                        }
            else:
                return {
                    "uri": path_to_uri(state.unit.ps_filename),
                    "range": span_to_range(local_sym[2]),
                }

        prev_tok = state.tokens[tok_idx - 1] if tok_idx > 0 else None
        prev2_tok = state.tokens[tok_idx - 2] if tok_idx > 1 else None

        # 4. Member access navigation: e.g. `receiver.val`
        if prev_tok and prev_tok.kind == TokenKind.DOT:
            receiver_type: TypeSymbol | None = None
            if prev2_tok:
                if prev2_tok.lexeme == "this":
                    enc_t = next((t for t in state.unit.types if t.span.start_line <= line <= t.span.end_line), None)
                    if enc_t and symtab:
                        receiver_type = symtab.lookup_type_in_context([enc_t.name], tuple(state.unit.namespace), state.unit.imports)
                elif prev2_tok.kind == TokenKind.IDENT:
                    rec_loc = self._resolve_local_symbol(state.unit, line, prev2_tok.lexeme)
                    if rec_loc and rec_loc[3] and symtab:
                        receiver_type = symtab.lookup_type_in_context(rec_loc[3].path, tuple(state.unit.namespace), state.unit.imports)
                        if not receiver_type and rec_loc[3].path[-1] in symtab.short_name_index:
                            receiver_type = symtab.short_name_index[rec_loc[3].path[-1]][0]
                    elif rec_loc and rec_loc[1] and symtab:
                        if rec_loc[1] in symtab.short_name_index:
                            receiver_type = symtab.short_name_index[rec_loc[1]][0]
                        else:
                            for sn, t_list in symtab.short_name_index.items():
                                if sn.lower() == rec_loc[1].lower():
                                    receiver_type = t_list[0]
                                    break
                    elif symtab:
                        receiver_type = symtab.lookup_type_in_context([prev2_tok.lexeme], tuple(state.unit.namespace), state.unit.imports)
                        if not receiver_type and prev2_tok.lexeme in symtab.short_name_index:
                            receiver_type = symtab.short_name_index[prev2_tok.lexeme][0]

            if receiver_type:
                visited_types: set[int] = set()
                type_queue = [receiver_type]
                while type_queue:
                    curr_type = type_queue.pop(0)
                    if curr_type.id.value in visited_types:
                        continue
                    visited_types.add(curr_type.id.value)
                    for base in curr_type.base_type_symbols:
                        if base.id.value not in visited_types:
                            type_queue.append(base)

                    if val in curr_type.members_by_name:
                        mem = curr_type.members_by_name[val][0]
                        if is_type_def and mem.resolved_type and symtab:
                            tname = mem.resolved_type.qualified_name.split(".")[-1]
                            t_sym = symtab.lookup_type_in_context([tname], tuple(state.unit.namespace), state.unit.imports)
                            if t_sym:
                                return {"uri": path_to_uri(t_sym.unit.ps_filename), "range": span_to_range(t_sym.span)}
                        return {"uri": path_to_uri(curr_type.unit.ps_filename), "range": span_to_range(mem.span)}

                    if curr_type.ast_node:
                        for m in curr_type.ast_node.members:
                            if getattr(m, "name", None) == val:
                                return {"uri": path_to_uri(curr_type.unit.ps_filename), "range": span_to_range(m.span)}
                return None

            # Fallback across current unit
            for t_decl in state.unit.types:
                for m in t_decl.members:
                    if getattr(m, "name", None) == val:
                        return {"uri": path_to_uri(state.unit.ps_filename), "range": span_to_range(m.span)}

            if symtab:
                for ts in symtab.types_by_id.values():
                    if val in ts.members_by_name:
                        mem = ts.members_by_name[val][0]
                        return {"uri": path_to_uri(ts.unit.ps_filename), "range": span_to_range(mem.span)}

        # 5. Type Name Navigation (using context)
        if symtab:
            type_sym = symtab.lookup_type_in_context([val], tuple(state.unit.namespace), state.unit.imports)
            if type_sym is None and val in symtab.short_name_index:
                type_sym = self._choose_best_type_candidate(symtab.short_name_index[val], state.unit)
            if type_sym is not None:
                return {
                    "uri": path_to_uri(type_sym.unit.ps_filename),
                    "range": span_to_range(type_sym.span),
                }

        # 6. Member Navigation on enclosing type
        enc_type = next((t for t in state.unit.types if t.span.start_line <= line <= t.span.end_line), None)
        if enc_type:
            for m in enc_type.members:
                if getattr(m, "name", None) == val:
                    if is_type_def and hasattr(m, "type_ref") and m.type_ref and symtab:
                        t_sym = symtab.lookup_type_in_context(m.type_ref.path, tuple(state.unit.namespace), state.unit.imports)
                        if t_sym:
                            return {"uri": path_to_uri(t_sym.unit.ps_filename), "range": span_to_range(t_sym.span)}
                    return {
                        "uri": path_to_uri(state.unit.ps_filename),
                        "range": span_to_range(m.span),
                    }

        # 7. Fallback type search via short_name_index
        if symtab and val in symtab.short_name_index:
            candidates = symtab.short_name_index[val]
            chosen = self._choose_best_type_candidate(candidates, state.unit)
            return {
                "uri": path_to_uri(chosen.unit.ps_filename),
                "range": span_to_range(chosen.span),
            }

        # 8. Check all registered members across symtab
        if symtab:
            for type_sym in symtab.types_by_id.values():
                if val in type_sym.members_by_name:
                    mem = type_sym.members_by_name[val][0]
                    return {
                        "uri": path_to_uri(type_sym.unit.ps_filename),
                        "range": span_to_range(mem.span),
                    }

        # 9. Fallback namespace token search (last resort)
        for u in state.project_units:
            if val in u.namespace and u != state.unit:
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

        return None

    def _default_completions(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for kw in sorted(PSC_KEYWORDS):
            items.append({"label": kw, "kind": 14, "detail": "keyword"})
        for ct in sorted(CORE_TYPES):
            items.append({"label": ct, "kind": 7, "detail": f"PythonSharp.Core.{ct}"})
        return items

    def _resolve_target_type(self, state: DocumentState, target_name: str) -> TypeSymbol | None:
        if not state.symtab:
            return None

        current_ns = tuple(state.unit.namespace) if state.unit and state.unit.namespace else ()
        imports = state.unit.imports if state.unit else []

        # 1. Lookup in context by name
        type_sym = state.symtab.lookup_type_in_context([target_name], current_ns, imports)
        if type_sym:
            return type_sym

        # 2. Check short_name_index for global/stdlib types (e.g., PyMath, Math, Console)
        if target_name in state.symtab.short_name_index:
            return self._choose_best_type_candidate(state.symtab.short_name_index[target_name], state.unit) if state.unit else state.symtab.short_name_index[target_name][0]

        # 3. Check parameters and local variables in the unit
        if state.unit:
            for t_decl in state.unit.types:
                for m in t_decl.members:
                    if isinstance(m, MethodDecl):
                        for p in m.params:
                            if p.name == target_name and p.type_ref and p.type_ref.path:
                                t = state.symtab.lookup_type_in_context(p.type_ref.path, current_ns, imports)
                                if not t and p.type_ref.path[-1] in state.symtab.short_name_index:
                                    t = state.symtab.short_name_index[p.type_ref.path[-1]][0]
                                if t:
                                    return t
                        if m.body:
                            for l_name, l_td, _span, l_tr in _collect_scoped_locals(m.body):
                                if l_name == target_name:
                                    if l_tr and l_tr.path:
                                        t = state.symtab.lookup_type_in_context(l_tr.path, current_ns, imports)
                                        if not t and l_tr.path[-1] in state.symtab.short_name_index:
                                            t = state.symtab.short_name_index[l_tr.path[-1]][0]
                                        if t:
                                            return t
                                    if l_td in state.symtab.short_name_index:
                                        return state.symtab.short_name_index[l_td][0]
                                    for sn, t_list in state.symtab.short_name_index.items():
                                        if sn.lower() == l_td.lower():
                                            return t_list[0]

        return None

    def _top_level_completions(self, state: DocumentState | None) -> list[dict[str, Any]]:
        items = self._default_completions()
        seen = {it["label"] for it in items}

        if state and state.symtab:
            for ns in state.symtab.namespaces:
                if ns:
                    root_ns = ns[0]
                    if root_ns not in seen:
                        seen.add(root_ns)
                        items.append({
                            "label": root_ns,
                            "kind": 9,
                            "detail": f"namespace {root_ns}",
                        })

            current_ns = tuple(state.unit.namespace) if state.unit and state.unit.namespace else ()
            if current_ns:
                for ns in state.symtab.namespaces:
                    if len(ns) > len(current_ns) and ns[:len(current_ns)] == current_ns:
                        sub = ns[len(current_ns)]
                        if sub not in seen:
                            seen.add(sub)
                            items.append({
                                "label": sub,
                                "kind": 9,
                                "detail": f"namespace {'.'.join(ns[:len(current_ns) + 1])}",
                            })

            if "Extern" not in seen and self.stdlib_dir and (self.stdlib_dir / "03_typeshed_replica").is_dir():
                seen.add("Extern")
                items.append({
                    "label": "Extern",
                    "kind": 9,
                    "detail": "namespace Extern",
                })

            for short_name, t_list in state.symtab.short_name_index.items():
                if short_name not in seen:
                    seen.add(short_name)
                    t_sym = t_list[0]
                    kind = 8 if t_sym.is_interface else (13 if t_sym.is_enum else (22 if t_sym.is_struct else 7))
                    items.append({
                        "label": short_name,
                        "kind": kind,
                        "detail": f"{t_sym.kind.name.lower()} {t_sym.qualified_name}",
                    })

        return items

    def _compute_completion(self, uri: str, line: int, character: int) -> list[dict[str, Any]]:
        state = self.documents.get(uri)
        if not state:
            return self._default_completions()

        lines = state.text.splitlines()
        current_line = lines[line][:character] if 0 <= line < len(lines) else ""

        # Check for member dot-access: `target.` or `target.prefix` (supports dotted chains like `A.B.`)
        match = re.search(r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)?$", current_line)
        if match and state.symtab:
            target_chain = match.group(1)
            member_prefix = match.group(2) or ""

            # 1. Check if target_chain is an absolute or relative namespace
            chain_tuple = tuple(target_chain.split("."))

            resolved_ns_tuple: tuple[str, ...] | None = None
            if chain_tuple in state.symtab.namespaces or any(len(ns) > len(chain_tuple) and ns[:len(chain_tuple)] == chain_tuple for ns in state.symtab.namespaces):
                resolved_ns_tuple = chain_tuple
            else:
                current_ns = tuple(state.unit.namespace) if state.unit and state.unit.namespace else ()
                for i in range(len(current_ns), 0, -1):
                    cand = current_ns[:i] + chain_tuple
                    if cand in state.symtab.namespaces or any(len(ns) > len(cand) and ns[:len(cand)] == cand for ns in state.symtab.namespaces):
                        resolved_ns_tuple = cand
                        break
                if not resolved_ns_tuple and state.unit:
                    for imp in state.unit.imports:
                        cand = tuple(imp.path) + chain_tuple
                        if cand in state.symtab.namespaces or any(len(ns) > len(cand) and ns[:len(cand)] == cand for ns in state.symtab.namespaces):
                            resolved_ns_tuple = cand
                            break

            is_known_ns = resolved_ns_tuple is not None and resolved_ns_tuple in state.symtab.namespaces
            has_sub_ns = resolved_ns_tuple is not None and any(len(ns) > len(resolved_ns_tuple) and ns[:len(resolved_ns_tuple)] == resolved_ns_tuple for ns in state.symtab.namespaces)
            is_extern_prefix = chain_tuple[0] == "Extern" and self.stdlib_dir is not None

            if is_known_ns or has_sub_ns or is_extern_prefix:
                ns_tuple_to_use = resolved_ns_tuple if resolved_ns_tuple is not None else chain_tuple
                ns_items: list[dict[str, Any]] = []
                for t in state.symtab.namespaces.get(ns_tuple_to_use, []):
                    if member_prefix and not t.name.lower().startswith(member_prefix.lower()):
                        continue
                    kind = 8 if t.is_interface else (13 if t.is_enum else (22 if t.is_struct else 7))
                    ns_items.append({
                        "label": t.name,
                        "kind": kind,
                        "detail": f"{t.kind.name.lower()} {t.qualified_name}",
                    })

                sub_seen: set[str] = set()
                for ns in state.symtab.namespaces:
                    if len(ns) > len(ns_tuple_to_use) and ns[:len(ns_tuple_to_use)] == ns_tuple_to_use:
                        sub = ns[len(ns_tuple_to_use)]
                        if sub not in sub_seen:
                            sub_seen.add(sub)
                            if not member_prefix or sub.lower().startswith(member_prefix.lower()):
                                ns_items.append({
                                    "label": sub,
                                    "kind": 9,
                                    "detail": f"namespace {'.'.join(ns[:len(ns_tuple_to_use) + 1])}",
                                })

                # Dynamically discover modules in 03_typeshed_replica for Extern
                if is_extern_prefix and self.stdlib_dir:
                    typeshed_dir = self.stdlib_dir / "03_typeshed_replica"
                    if not typeshed_dir.exists():
                        typeshed_dir = self.stdlib_dir / "03_extended"
                    if typeshed_dir.is_dir():
                        if len(chain_tuple) == 1:
                            for child in typeshed_dir.iterdir():
                                c_name = child.name.replace(".d.ps", "")
                                if c_name.startswith("_"):
                                    continue
                                pascal_name = "".join(part.capitalize() for part in c_name.split("_"))
                                if pascal_name not in sub_seen:
                                    sub_seen.add(pascal_name)
                                    if not member_prefix or pascal_name.lower().startswith(member_prefix.lower()):
                                        ns_items.append({
                                            "label": pascal_name,
                                            "kind": 9,
                                            "detail": f"namespace Extern.{pascal_name}",
                                        })
                        elif len(chain_tuple) == 2:
                            top_sub = chain_tuple[1].lower()
                            sub_dir = typeshed_dir / top_sub
                            if sub_dir.is_dir():
                                for child in sub_dir.glob("*.d.ps"):
                                    c_name = child.stem.replace(".d", "")
                                    if c_name.startswith("_") or c_name == top_sub:
                                        continue
                                    pascal_name = "".join(part.capitalize() for part in c_name.split("_"))
                                    if pascal_name not in sub_seen:
                                        sub_seen.add(pascal_name)
                                        if not member_prefix or pascal_name.lower().startswith(member_prefix.lower()):
                                            ns_items.append({
                                                "label": pascal_name,
                                                "kind": 9,
                                                "detail": f"namespace Extern.{chain_tuple[1]}.{pascal_name}",
                                            })

                if ns_items:
                    ns_items.sort(key=lambda x: x["label"])
                    return ns_items

            # 2. Check if target_chain is a qualified or local type symbol or variable
            target_type = state.symtab.types_by_qname.get(target_chain)
            if not target_type:
                target_type = self._resolve_target_type(state, target_chain)
            if target_type:
                items: list[dict[str, Any]] = []
                seen_members: set[str] = set()
                visited_types: set[int] = set()
                type_queue = [target_type]
                while type_queue:
                    curr_type = type_queue.pop(0)
                    if curr_type.id.value in visited_types:
                        continue
                    visited_types.add(curr_type.id.value)
                    for base in curr_type.base_type_symbols:
                        if base.id.value not in visited_types:
                            type_queue.append(base)

                    for m_name, m_list in curr_type.members_by_name.items():
                        if member_prefix and not m_name.lower().startswith(member_prefix.lower()):
                            continue
                        if m_name in seen_members:
                            continue
                        seen_members.add(m_name)
                        mem = m_list[0]
                        kind = 2 if mem.kind == "method" else (10 if mem.kind == "property" else 5)
                        detail = f"{curr_type.name}.{m_name}"
                        if mem.kind == "method":
                            params_list = getattr(mem.ast_node, "params", [])
                            params_str = ", ".join(
                                f"{p.type_ref.display_name() if p.type_ref else 'var'} {p.name}" for p in params_list
                            )
                            ret_str = mem.resolved_type.py_annotation if mem.resolved_type else "void"
                            detail = f"{ret_str} {curr_type.name}.{m_name}({params_str})"
                        elif mem.kind in ("property", "field"):
                            ret_str = mem.resolved_type.py_annotation if mem.resolved_type else "var"
                            detail = f"{ret_str} {curr_type.name}.{m_name}"
                        items.append({
                            "label": m_name,
                            "kind": kind,
                            "detail": detail,
                        })
                items.sort(key=lambda x: x["label"])
                return items

        return self._top_level_completions(state)

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
