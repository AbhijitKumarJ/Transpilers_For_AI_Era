from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Sequence

from psc.build_cache import BuildCacheManager
from psc.codegen import ArtifactEmitter, EmittedArtifact, NamespacePackagePlanner, PythonAstBuilder
from psc.diagnostics import DiagnosticEngine
from psc.frontend import CompilationUnit, Parser
from psc.native import NativeCompiler
from psc.project import PsProjectConfig, load_project
from psc.semantics import GlobalSymbolTable, analyze_compilation_units
from psc.semantics.symbols import pascal_to_snake


def _find_default_stdlib_dir() -> Path | None:
    """Locates `stdlib/PythonSharp.Core.d.ps` relative to the package or working directory."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "stdlib",
        Path(sys.prefix) / "share" / "pythonsharp",
        Path.cwd() / "stdlib",
    ]
    for cand in candidates:
        if cand.exists() and any(cand.glob("*.d.ps")):
            return cand
    return None


def _discover_inputs(target: Path, out_dir: Path | None) -> PsProjectConfig:
    stdlib_dir = _find_default_stdlib_dir()
    target = target.resolve()

    if target.is_file() and target.suffix == ".psproj":
        cfg = load_project(target, stdlib_dir=stdlib_dir)
        if out_dir is not None:
            cfg.out_dir = out_dir.resolve()
        return cfg

    if target.is_file() and target.suffix == ".ps":
        stubs = sorted(stdlib_dir.rglob("*.d.ps")) if stdlib_dir else []
        return PsProjectConfig(
            project_name=target.stem,
            root_dir=target.parent,
            out_dir=(out_dir or (target.parent / "dist")).resolve(),
            source_files=[target],
            stub_files=stubs,
        )

    # Directory target: look for a `.psproj` first, or scan all `.ps` files
    psproj_files = list(target.glob("*.psproj"))
    if psproj_files:
        cfg = load_project(psproj_files[0], stdlib_dir=stdlib_dir)
        if out_dir is not None:
            cfg.out_dir = out_dir.resolve()
        return cfg

    stubs = sorted(stdlib_dir.rglob("*.d.ps")) if stdlib_dir else []
    for local_stub in sorted(target.rglob("*.d.ps")):
        if local_stub not in stubs:
            stubs.append(local_stub)
    sources = sorted(p for p in target.rglob("*.ps") if not p.name.endswith(".d.ps"))
    return PsProjectConfig(
        project_name=target.name,
        root_dir=target,
        out_dir=(out_dir or (target / "dist")).resolve(),
        source_files=sources,
        stub_files=stubs,
    )


def parse_and_analyze_config(
    config: PsProjectConfig,
) -> tuple[list[CompilationUnit], GlobalSymbolTable, DiagnosticEngine]:
    diag = DiagnosticEngine()
    units: list[CompilationUnit] = []

    for idx, file_path in enumerate(config.all_input_files()):
        try:
            rel_name = str(file_path.relative_to(config.root_dir))
        except ValueError:
            rel_name = file_path.name
        source_text = file_path.read_text(encoding="utf-8")
        unit = Parser.from_source(
            source_text,
            file_id=idx,
            ps_filename=rel_name,
            diagnostics=diag,
        ).parse_compilation_unit()
        units.append(unit)

    symtab = GlobalSymbolTable(default_assembly_name=config.project_name)
    if not diag.has_errors():
        analyze_compilation_units(
            units,
            symtab=symtab,
            diagnostics=diag,
            assembly_name=config.project_name,
        )

    return units, symtab, diag


def build_parser() -> argparse.ArgumentParser:
    from psc.version import LANGUAGE_VERSION, __version__

    parser = argparse.ArgumentParser(
        prog="psc",
        description="PythonSharp (psc) - Multi-Pass Static C#-to-Python 3.11+ Transpiler",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"psc {__version__} (language {LANGUAGE_VERSION})",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    check_p = subparsers.add_parser("check", help="Run Pass 1 & Pass 2 verification without emitting files")
    check_p.add_argument(
        "target", type=Path, nargs="?", default=Path("."), help="Path to .psproj, directory, or .ps file"
    )

    build_p = subparsers.add_parser("build", help="Compile .ps project into Python packages and line-pinned .pyc files")
    build_p.add_argument(
        "target", type=Path, nargs="?", default=Path("."), help="Path to .psproj, directory, or .ps file"
    )
    build_p.add_argument("-o", "--out-dir", type=Path, default=None, help="Output directory (default: dist/)")
    build_p.add_argument("--no-pyc", action="store_true", help="Disable PEP 552 .pyc bytecode emission")
    build_p.add_argument("-f", "--force", action="store_true", help="Force rebuild, ignoring compilation cache")
    build_p.add_argument("--no-cache", action="store_true", help="Disable build caching")
    build_p.add_argument(
        "--native", action="store_true", help="Compile [NativeCompile] types to C-extensions via mypyc/Cython"
    )

    watch_p = subparsers.add_parser("watch", help="Watch project files and rebuild incrementally on change")
    watch_p.add_argument(
        "target", type=Path, nargs="?", default=Path("."), help="Path to .psproj, directory, or .ps file"
    )
    watch_p.add_argument("-o", "--out-dir", type=Path, default=None, help="Output directory (default: dist/)")
    watch_p.add_argument("--no-pyc", action="store_true", help="Disable PEP 552 .pyc bytecode emission")
    watch_p.add_argument("--poll-interval", type=float, default=0.5, help="Polling interval in seconds (default: 0.5)")

    subparsers.add_parser("lsp", help="Run Language Server Protocol (LSP) server over stdio")

    dump_p = subparsers.add_parser("dump-ast", help="Print lowered Python 3.11+ source code to stdout")
    dump_p.add_argument(
        "target", type=Path, nargs="?", default=Path("."), help="Path to .psproj, directory, or .ps file"
    )

    run_p = subparsers.add_parser("run", help="Compile and execute a PythonSharp entrypoint (`Class.Method` or `Main`)")
    run_p.add_argument(
        "target", type=Path, nargs="?", default=Path("."), help="Path to .psproj, directory, or .ps file"
    )
    run_p.add_argument("-e", "--entry", type=str, default=None, help="Entrypoint e.g. 'Program.Main'")

    bindgen_p = subparsers.add_parser("bindgen", help="Generate .d.ps ambient stubs from Python .pyi type stubs")
    bindgen_p.add_argument("target", type=Path, help="Path to .pyi file or directory of .pyi stubs")
    bindgen_p.add_argument(
        "-o", "--out-dir", type=Path, default=Path(".ps-stubs"), help="Output directory (default: .ps-stubs/)"
    )
    bindgen_p.add_argument(
        "--root-namespace", type=str, default="Extern", help="Root namespace prefix (default: Extern)"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "lsp":
        from psc.lsp import LanguageServer

        server = LanguageServer()
        server.serve()
        return 0

    if args.command == "watch":
        from psc.watcher import ProjectWatcher

        out_dir = getattr(args, "out_dir", None)
        config = _discover_inputs(args.target, out_dir=out_dir)
        if getattr(args, "no_pyc", False):
            config.emit_pyc = False
        print(f"Starting psc watch on '{config.root_dir}'...")
        watcher = ProjectWatcher(config, poll_interval_sec=args.poll_interval)
        try:
            watcher.watch()
        except KeyboardInterrupt:
            print("\nWatch stopped.")
        return 0

    if args.command == "bindgen":
        from psc.bindgen import generate_bindings

        target = args.target.resolve()
        if not target.exists():
            print(f"ERROR: Target path '{args.target}' does not exist.", file=sys.stderr)
            return 1
        generated = generate_bindings(
            target,
            out_dir=args.out_dir.resolve(),
            root_namespace=args.root_namespace,
        )
        print(f"Bindgen succeeded: generated {len(generated)} .d.ps file(s) into '{args.out_dir}'.")
        return 0

    out_dir = getattr(args, "out_dir", None)
    config = _discover_inputs(args.target, out_dir=out_dir)

    if not config.source_files:
        print(f"ERROR: No .ps source files found in '{args.target}'.", file=sys.stderr)
        return 1

    emit_pyc = not getattr(args, "no_pyc", False) and config.emit_pyc
    use_cache = not getattr(args, "no_cache", False) and not getattr(args, "force", False)
    cache_mgr = BuildCacheManager()

    if use_cache and args.command == "build" and cache_mgr.is_up_to_date(config, emit_pyc=emit_pyc):
        print(f"Build is up to date: outputs in '{config.out_dir}' are fresh.")
        return 0

    _, symtab, diag = parse_and_analyze_config(config)
    if diag.has_errors():
        print(diag.format_all(), file=sys.stderr)
        return 1

    if args.command == "check":
        print(f"Check succeeded: {len(config.source_files)} .ps file(s) verified with 0 errors.")
        return 0

    if args.command == "dump-ast":
        planner = NamespacePackagePlanner(symtab)
        builder = PythonAstBuilder(symtab)
        import ast

        for rel_path, planned in sorted(planner.plan_modules().items()):
            mod_ast = builder.build_module(planned)
            print(f"# === Module: {rel_path} (pinned to {planned.primary_ps_filename}) ===")
            print(ast.unparse(mod_ast))
            print()
        return 0

    emitter = ArtifactEmitter(symtab)
    artifacts = emitter.emit_all(config.out_dir, emit_pyc=emit_pyc)

    if args.command == "build":
        if not getattr(args, "no_cache", False):
            cache_mgr.save_cache(config, artifacts, emit_pyc=emit_pyc)

        if getattr(args, "native", False) or NativeCompiler.has_native_types(symtab):
            native_compiler = NativeCompiler()
            for art in artifacts:
                res = native_compiler.compile_module(art.py_path, out_dir=config.out_dir)
                if res.success:
                    print(f"Native compilation ({res.compiler_used}) succeeded: {res.output_binary}")
                elif getattr(args, "native", False):
                    print(f"WARNING: Native compilation failed for '{art.py_path.name}': {res.error}", file=sys.stderr)

        print(f"Build succeeded: emitted {len(artifacts)} module(s) to '{config.out_dir}'.")
        return 0

    if args.command == "run":
        return _execute_artifacts(config.out_dir, artifacts, args.entry)

    return 0


def _execute_artifacts(
    out_dir: Path,
    artifacts: list[EmittedArtifact],
    entry_spec: str | None,
) -> int:
    sys.path.insert(0, str(out_dir))
    executed = False

    try:
        for art in artifacts:
            ns_globals: dict[str, object] = {"__name__": "__main__"}
            exec(art.code_object, ns_globals)

            if entry_spec:
                parts = entry_spec.split(".")
                cls_name = parts[0]
                method_name = pascal_to_snake(parts[1]) if len(parts) > 1 else "main"
                if cls_name in ns_globals:
                    cls_obj = ns_globals[cls_name]
                    fn = getattr(cls_obj, method_name, None)
                    if callable(fn):
                        fn()
                        executed = True
                        break
            else:
                # Auto-detect any class with a static `main()` method
                for val in ns_globals.values():
                    if isinstance(val, type) and hasattr(val, "main") and callable(getattr(val, "main")):
                        val.main()
                        executed = True
                        break
            if executed:
                break
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        if str(out_dir) in sys.path:
            sys.path.remove(str(out_dir))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
