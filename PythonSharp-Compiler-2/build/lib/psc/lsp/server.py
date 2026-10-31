from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import BinaryIO

from psc.diagnostics import DiagnosticEngine
from psc.frontend import CompilationUnit, Lexer, Parser, Token, TokenKind
from psc.lsp.protocol import JsonRpcProtocol
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


@dataclass(slots=True)
class DocumentState:
    uri: str
    text: str
    unit: CompilationUnit | None = None
    tokens: list[Token] | None = None
    symtab: GlobalSymbolTable | None = None
    diagnostics: DiagnosticEngine | None = None


class LanguageServer:
    """Pure-Python Language Server Protocol (LSP) server for PythonSharp (.ps) files."""

    def __init__(self, in_stream: BinaryIO | None = None, out_stream: BinaryIO | None = None) -> None:
        self.in_stream = in_stream or sys.stdin.buffer
        self.out_stream = out_stream or sys.stdout.buffer
        self.documents: dict[str, DocumentState] = {}
        self.is_running = True
        self.notifications_log: list[dict[str, object]] = []

    def send_notification(self, method: str, params: object) -> None:
        notif = JsonRpcProtocol.make_notification(method, params)
        self.notifications_log.append(notif)
        if self.out_stream is not None:
            JsonRpcProtocol.write_message(self.out_stream, notif)

    def send_response(self, req_id: object, result: object) -> None:
        resp = JsonRpcProtocol.make_response(req_id, result)
        if self.out_stream is not None:
            JsonRpcProtocol.write_message(self.out_stream, resp)

    def analyze_document(self, uri: str, text: str) -> DocumentState:
        diag = DiagnosticEngine()
        tokens = Lexer(text, ps_filename=uri, diagnostics=diag).tokenize()
        unit = Parser.from_source(text, file_id=0, ps_filename=uri, diagnostics=diag).parse_compilation_unit()

        symtab = GlobalSymbolTable(default_assembly_name="Workspace")
        if not diag.has_errors():
            analyze_compilation_units([unit], symtab=symtab, diagnostics=diag, assembly_name="Workspace")

        state = DocumentState(
            uri=uri,
            text=text,
            unit=unit,
            tokens=tokens,
            symtab=symtab,
            diagnostics=diag,
        )
        self.documents[uri] = state

        # Publish diagnostics
        lsp_diags: list[dict[str, object]] = []
        for d in diag.diagnostics:
            span = d.span
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
                "severity": 1,  # Error
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
            return JsonRpcProtocol.make_response(req_id, {
                "capabilities": {
                    "textDocumentSync": 1,  # Full sync
                    "hoverProvider": True,
                    "definitionProvider": True,
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

        if method == "textDocument/definition":
            doc_uri = str(params.get("textDocument", {}).get("uri", ""))
            pos = params.get("position", {})
            line = int(pos.get("line", 0)) + 1
            character = int(pos.get("character", 0)) + 1
            loc = self._compute_definition(doc_uri, line, character)
            return JsonRpcProtocol.make_response(req_id, loc)

        if method == "textDocument/completion":
            items = []
            for kw in sorted(PSC_KEYWORDS):
                items.append({
                    "label": kw,
                    "kind": 14,  # Keyword
                    "detail": "keyword",
                })
            for ct in sorted(CORE_TYPES):
                items.append({
                    "label": ct,
                    "kind": 7,  # Class / Interface
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
        if state is None:
            return None
        tok = self._find_token_at(state, line, col)
        if tok is None:
            return None

        val = tok.lexeme
        if tok.kind in (TokenKind.CLASS, TokenKind.INTERFACE, TokenKind.RECORD, TokenKind.STRUCT):
            return f"**keyword** `{val}`"
        if tok.kind in (TokenKind.PUBLIC, TokenKind.PRIVATE, TokenKind.PROTECTED, TokenKind.INTERNAL):
            return f"**access modifier** `{val}`"

        # Check declared types in compilation unit
        if state.unit:
            for type_decl in state.unit.types:
                if type_decl.name == val:
                    kind_name = type_decl.kind.name.lower()
                    return f"```csharp\n{kind_name} {type_decl.name}\n```\n*Declared in {uri}*"
                for member in type_decl.members:
                    if getattr(member, "name", None) == val:
                        return f"```csharp\nmember {type_decl.name}.{val}\n```"

        if val in CORE_TYPES:
            return f"```csharp\nCore type {val}\n```\n*Mapped to Python runtime standard library*"

        return None

    def _compute_definition(self, uri: str, line: int, col: int) -> dict[str, object] | None:
        state = self.documents.get(uri)
        if state is None or state.unit is None:
            return None
        tok = self._find_token_at(state, line, col)
        if tok is None:
            return None

        val = tok.lexeme
        for type_decl in state.unit.types:
            if type_decl.name == val:
                span = type_decl.span
                return {
                    "uri": uri,
                    "range": {
                        "start": {"line": max(0, span.start_line - 1), "character": max(0, span.start_col - 1)},
                        "end": {"line": max(0, span.end_line - 1), "character": max(0, span.end_col - 1)},
                    },
                }
            for member in type_decl.members:
                if getattr(member, "name", None) == val:
                    span = getattr(member, "span", None)
                    if span:
                        return {
                            "uri": uri,
                            "range": {
                                "start": {"line": max(0, span.start_line - 1), "character": max(0, span.start_col - 1)},
                                "end": {"line": max(0, span.end_line - 1), "character": max(0, span.end_col - 1)},
                            },
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
