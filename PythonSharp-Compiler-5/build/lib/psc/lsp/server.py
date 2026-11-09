from __future__ import annotations

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
)
from psc.semantics import (
    GlobalSymbolTable,
    MemberSymbol,
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
        td = stmt.type_ref.display_name() if stmt.type_ref else "var"
        locals_found.append((stmt.name, td, stmt.span, stmt.type_ref))
    elif isinstance(stmt, ForEachStmt):
        td = stmt.type_ref.display_name() if stmt.type_ref else "var"
        locals_found.append((stmt.item_name, td, stmt.span, stmt.type_ref))
    elif isinstance(stmt, UsingResourceStmt):
        td = stmt.type_ref.display_name() if stmt.type_ref else "var"
        locals_found.append((stmt.name, td, stmt.span, stmt.type_ref))
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
        stub_paths = find_stdlib_stubs(self.stdlib_dir)
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
        tok, _ = self._find_token_and_index(state, line, col)
        return tok

    def _find_token_and_index(self, state: DocumentState, line: int, col: int) -> tuple[Token | None, int]:
        if not state.tokens:
            return None, -1
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
                        matching = [l for l in all_locs if l[0] == name and l[2].start_line <= line]
                        if matching:
                            best = max(matching, key=lambda l: l[2].start_line)
                            return ("local variable", best[1], best[2], best[3])
                    # Property accessors
                    if hasattr(m, "accessors") and m.accessors:
                        for acc in m.accessors:
                            if acc.span.start_line <= line <= acc.span.end_line and acc.body:
                                acc_locs = _collect_scoped_locals(acc.body)
                                matching = [l for l in acc_locs if l[0] == name and l[2].start_line <= line]
                                if matching:
                                    best = max(matching, key=lambda l: l[2].start_line)
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
                    elif symtab:
                        receiver_type = symtab.lookup_type_in_context([prev2_tok.lexeme], tuple(state.unit.namespace), state.unit.imports)

            if receiver_type:
                if val in receiver_type.members_by_name:
                    mem = receiver_type.members_by_name[val][0]
                    return self._format_member_hover(receiver_type, mem)
                if receiver_type.ast_node:
                    for m in receiver_type.ast_node.members:
                        if getattr(m, "name", None) == val:
                            return self._format_ast_member_hover(receiver_type.name, receiver_type.unit.ps_filename, m)

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
                    elif symtab:
                        receiver_type = symtab.lookup_type_in_context([prev2_tok.lexeme], tuple(state.unit.namespace), state.unit.imports)

            if receiver_type:
                if val in receiver_type.members_by_name:
                    mem = receiver_type.members_by_name[val][0]
                    if is_type_def and mem.resolved_type and symtab:
                        tname = mem.resolved_type.qualified_name.split(".")[-1]
                        t_sym = symtab.lookup_type_in_context([tname], tuple(state.unit.namespace), state.unit.imports)
                        if t_sym:
                            return {"uri": path_to_uri(t_sym.unit.ps_filename), "range": span_to_range(t_sym.span)}
                    return {"uri": path_to_uri(receiver_type.unit.ps_filename), "range": span_to_range(mem.span)}

                if receiver_type.ast_node:
                    for m in receiver_type.ast_node.members:
                        if getattr(m, "name", None) == val:
                            return {"uri": path_to_uri(receiver_type.unit.ps_filename), "range": span_to_range(m.span)}

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
