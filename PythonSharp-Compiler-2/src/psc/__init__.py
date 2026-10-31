from __future__ import annotations

from pathlib import Path

from psc.build_cache import BuildCacheManager
from psc.codegen import (
    ArtifactEmitter,
    EmittedArtifact,
    NamespacePackagePlanner,
    PythonAstBuilder,
)
from psc.diagnostics import Diagnostic, DiagnosticEngine, SourceSpan
from psc.frontend import CompilationUnit, Lexer, Parser, Token, TokenKind
from psc.lsp import LanguageServer
from psc.native import NativeCompiler
from psc.project import PsProjectConfig, load_project
from psc.semantics import GlobalSymbolTable, analyze_compilation_units
from psc.version import LANGUAGE_VERSION, __version__
from psc.watcher import ProjectWatcher


def compile_sources(
    sources: dict[str, str],
    out_dir: Path,
    stdlib_source: str | None = None,
    assembly_name: str = "App",
    emit_pyc: bool = True,
) -> tuple[list[EmittedArtifact], DiagnosticEngine]:
    """
    High-level in-memory & disk compilation API for PythonSharp (`psc`):
      1. Parses optional `stdlib_source` (`PythonSharp.Core.d.ps`) and a mapping of
         `{ps_filename: ps_source_code}`.
      2. Runs Pass 1 (GlobalSymbolTable & SymbolCollector) and Pass 2 (SlotAndHierarchyAnalyzer,
         AccessChecker, PrimitiveResolver, OverloadResolver, LinqComprehensionFuser).
      3. Runs Pass 3 (NamespacePackagePlanner, PythonAstBuilder, ArtifactEmitter) to emit
         `.py` packages and line-pinned `.pyc` bytecode into `out_dir`.
    """
    diag = DiagnosticEngine()
    units: list[CompilationUnit] = []
    file_id = 0

    if stdlib_source is not None:
        units.append(
            Parser.from_source(
                stdlib_source,
                file_id=file_id,
                ps_filename="PythonSharp.Core.d.ps",
                diagnostics=diag,
            ).parse_compilation_unit()
        )
        file_id += 1

    for ps_filename, code in sources.items():
        units.append(
            Parser.from_source(
                code,
                file_id=file_id,
                ps_filename=ps_filename,
                diagnostics=diag,
            ).parse_compilation_unit()
        )
        file_id += 1

    if diag.has_errors():
        return [], diag

    symtab = GlobalSymbolTable(default_assembly_name=assembly_name)
    analyze_compilation_units(units, symtab=symtab, diagnostics=diag, assembly_name=assembly_name)
    if diag.has_errors():
        return [], diag

    emitter = ArtifactEmitter(symtab)
    artifacts = emitter.emit_all(out_dir=out_dir, emit_pyc=emit_pyc)
    return artifacts, diag


__all__ = [
    "ArtifactEmitter",
    "EmittedArtifact",
    "NamespacePackagePlanner",
    "PythonAstBuilder",
    "Diagnostic",
    "DiagnosticEngine",
    "SourceSpan",
    "CompilationUnit",
    "Lexer",
    "Parser",
    "Token",
    "TokenKind",
    "PsProjectConfig",
    "load_project",
    "GlobalSymbolTable",
    "analyze_compilation_units",
    "compile_sources",
    "BuildCacheManager",
    "ProjectWatcher",
    "LanguageServer",
    "NativeCompiler",
    "LANGUAGE_VERSION",
    "__version__",
]
