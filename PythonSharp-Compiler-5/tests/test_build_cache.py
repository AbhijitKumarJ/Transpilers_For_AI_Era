from __future__ import annotations

from pathlib import Path

from psc.build_cache import BuildCacheManager
from psc.codegen import ArtifactEmitter
from psc.diagnostics import DiagnosticEngine
from psc.frontend import Parser
from psc.project import PsProjectConfig
from psc.semantics import GlobalSymbolTable, analyze_compilation_units


def test_build_cache_lifecycle(tmp_path: Path) -> None:
    src_file = tmp_path / "App.ps"
    src_file.write_text("namespace Demo; public class Greeter { public string Greet() => \"hi\"; }", encoding="utf-8")
    out_dir = tmp_path / "dist"

    config = PsProjectConfig(
        project_name="Demo",
        root_dir=tmp_path,
        out_dir=out_dir,
        source_files=[src_file],
    )

    manager = BuildCacheManager()
    # Initial state: no cache exists
    assert not manager.is_up_to_date(config)

    # Compile and emit artifacts
    diag = DiagnosticEngine()
    unit = Parser.from_source(src_file.read_text(), file_id=0, ps_filename="App.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable(default_assembly_name="Demo")
    analyze_compilation_units([unit], symtab=symtab, diagnostics=diag, assembly_name="Demo")
    emitter = ArtifactEmitter(symtab)
    artifacts = emitter.emit_all(out_dir=out_dir, emit_pyc=False)

    # Save cache
    manager.save_cache(config, artifacts, emit_pyc=False)

    # Now cache should report up to date
    assert manager.is_up_to_date(config, emit_pyc=False)

    # Changing source content invalidates cache
    src_file.write_text("namespace Demo; public class Greeter { public string Greet() => \"hello world\"; }", encoding="utf-8")
    assert not manager.is_up_to_date(config, emit_pyc=False)


def test_build_cache_output_removal(tmp_path: Path) -> None:
    src_file = tmp_path / "App.ps"
    src_file.write_text("namespace Demo; public class Item {}", encoding="utf-8")
    out_dir = tmp_path / "dist"

    config = PsProjectConfig(
        project_name="Demo",
        root_dir=tmp_path,
        out_dir=out_dir,
        source_files=[src_file],
    )

    manager = BuildCacheManager()
    diag = DiagnosticEngine()
    unit = Parser.from_source(src_file.read_text(), file_id=0, ps_filename="App.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable(default_assembly_name="Demo")
    analyze_compilation_units([unit], symtab=symtab, diagnostics=diag, assembly_name="Demo")
    emitter = ArtifactEmitter(symtab)
    artifacts = emitter.emit_all(out_dir=out_dir, emit_pyc=False)

    manager.save_cache(config, artifacts, emit_pyc=False)
    assert manager.is_up_to_date(config, emit_pyc=False)

    # Removing an output file invalidates cache
    out_file = artifacts[0].py_path
    assert out_file.exists()
    out_file.unlink()
    assert not manager.is_up_to_date(config, emit_pyc=False)
