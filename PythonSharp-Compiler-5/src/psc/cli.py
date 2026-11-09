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
from psc.project import (
    PsProjectConfig,
    add_project_reference,
    find_stdlib_stubs,
    is_ps_project_file,
    is_ps_source_file,
    is_ps_stub_file,
    load_project,
    resolve_project_dependencies,
)
from psc.semantics import GlobalSymbolTable, analyze_compilation_units
from psc.semantics.symbols import pascal_to_snake


def _find_default_stdlib_dir() -> Path | None:
    """Locates stdlib relative to the package, virtualenv, or working directory."""
    candidates = [
        Path(__file__).resolve().parent / "stdlib",
        Path(__file__).resolve().parent.parent.parent / "stdlib",
        Path(sys.prefix) / "share" / "pythonsharp",
        Path.cwd() / "stdlib",
    ]
    for cand in candidates:
        if cand.exists() and (
            any(is_ps_stub_file(p) for p in cand.glob("*"))
            or (cand / "00_core").is_dir()
        ):
            return cand
    return None


def _discover_inputs(target: Path, out_dir: Path | None) -> PsProjectConfig:
    stdlib_dir = _find_default_stdlib_dir()
    target = target.resolve()

    if target.is_file() and is_ps_project_file(target):
        cfg = load_project(target, stdlib_dir=stdlib_dir)
        if out_dir is not None:
            cfg.out_dir = out_dir.resolve()
        return cfg

    if target.is_file() and is_ps_source_file(target):
        stubs = find_stdlib_stubs(stdlib_dir)
        return PsProjectConfig(
            project_name=target.stem,
            root_dir=target.parent,
            out_dir=(out_dir or (target.parent / "dist")).resolve(),
            source_files=[target],
            stub_files=stubs,
        )

    # Directory target: look for a project file first, or scan all source files
    psproj_files = [p for p in target.glob("*") if is_ps_project_file(p)]
    if psproj_files:
        cfg = load_project(psproj_files[0], stdlib_dir=stdlib_dir)
        if out_dir is not None:
            cfg.out_dir = out_dir.resolve()
        return cfg

    stubs = find_stdlib_stubs(stdlib_dir)
    for local_stub in sorted(target.rglob("*")):
        if local_stub.is_file() and is_ps_stub_file(local_stub) and local_stub not in stubs:
            stubs.append(local_stub)
    sources = sorted(p for p in target.rglob("*") if p.is_file() and is_ps_source_file(p))
    return PsProjectConfig(
        project_name=target.name,
        root_dir=target,
        out_dir=(out_dir or (target / "dist")).resolve(),
        source_files=sources,
        stub_files=stubs,
    )


def parse_and_analyze_config(
    config: PsProjectConfig,
    target_surface: int | None = None,
    dependency_configs: list[PsProjectConfig] | None = None,
) -> tuple[list[CompilationUnit], GlobalSymbolTable, DiagnosticEngine]:
    diag = DiagnosticEngine()
    units: list[CompilationUnit] = []
    config_units: list[CompilationUnit] = []

    file_id = 0
    # 1. Parse ambient and stdlib stubs
    for stub_path in config.stub_files:
        try:
            rel_name = str(stub_path.relative_to(config.root_dir))
        except ValueError:
            rel_name = stub_path.name
        source_text = stub_path.read_text(encoding="utf-8")
        unit = Parser.from_source(
            source_text,
            file_id=file_id,
            ps_filename=rel_name,
            diagnostics=diag,
        ).parse_compilation_unit()
        unit.assembly_name = "PythonSharp.Core"
        units.append(unit)
        file_id += 1

    # 2. Parse referenced dependency project sources for cross-assembly type resolution
    if dependency_configs:
        for dep in dependency_configs:
            for dep_file in dep.source_files:
                try:
                    rel_name = str(dep_file.relative_to(dep.root_dir))
                except ValueError:
                    rel_name = dep_file.name
                source_text = dep_file.read_text(encoding="utf-8")
                unit = Parser.from_source(
                    source_text,
                    file_id=file_id,
                    ps_filename=rel_name,
                    diagnostics=diag,
                ).parse_compilation_unit()
                unit.assembly_name = dep.project_name
                units.append(unit)
                file_id += 1

    # 3. Parse target project sources
    for file_path in config.source_files:
        try:
            rel_name = str(file_path.relative_to(config.root_dir))
        except ValueError:
            rel_name = file_path.name
        source_text = file_path.read_text(encoding="utf-8")
        unit = Parser.from_source(
            source_text,
            file_id=file_id,
            ps_filename=rel_name,
            diagnostics=diag,
        ).parse_compilation_unit()
        unit.assembly_name = config.project_name
        units.append(unit)
        config_units.append(unit)
        file_id += 1

    symtab = GlobalSymbolTable(default_assembly_name=config.project_name)
    if not diag.has_errors():
        analyze_compilation_units(
            units,
            symtab=symtab,
            diagnostics=diag,
            assembly_name=config.project_name,
            target_surface=target_surface,
        )

    return config_units, symtab, diag


def compile_single_project(
    config: PsProjectConfig,
    emit_pyc: bool = True,
    target_surface: int | None = None,
    dependency_configs: list[PsProjectConfig] | None = None,
) -> tuple[list[EmittedArtifact], DiagnosticEngine]:
    config_units, symtab, diag = parse_and_analyze_config(
        config, target_surface=target_surface, dependency_configs=dependency_configs
    )
    for d in diag.diagnostics:
        if d.severity == "WARNING":
            print(str(d), file=sys.stderr)
    if diag.has_errors():
        return [], diag

    emitter = ArtifactEmitter(symtab, target_units=config_units)
    artifacts = emitter.emit_all(config.out_dir, emit_pyc=emit_pyc)
    return artifacts, diag


def _copy_dependency_artifacts(src_dir: Path, dst_dir: Path) -> None:
    """Copies compiled Python modules and packages from dependency out_dir to target out_dir."""
    import shutil

    if not src_dir.exists():
        return
    dst_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        if item.name in ("psc-manifest.json", ".psc-cache.json", ".psc-cache"):
            continue
        dest_item = dst_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest_item, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest_item)


def clean_project(config: PsProjectConfig) -> int:
    """Removes compiled artifacts, bytecode, and compilation cache from out_dir."""
    cache_mgr = BuildCacheManager()
    cache_mgr.clear_cache(config)
    if config.out_dir.exists():
        import shutil

        for item in list(config.out_dir.iterdir()):
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        print(f"Clean succeeded: removed outputs in '{config.out_dir}'.")
    else:
        print(f"Clean: directory '{config.out_dir}' does not exist (nothing to clean).")
    return 0


def create_project(name: str, target_dir: Path) -> int:
    """Creates a new starter PythonSharp project with .psproj, ProjMain.ps, TestUtil.ps, and run_main.py."""
    clean_name = Path(name).name
    if not clean_name.isidentifier():
        print(f"ERROR: '{clean_name}' is not a valid project name / identifier.", file=sys.stderr)
        return 1

    target_dir = target_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Project file: <name>.psproj
    psproj_file = target_dir / f"{clean_name}.psproj"
    if not psproj_file.exists():
        psproj_content = f"""<Project Sdk="PythonSharp.Sdk/0.1.0">
  <PropertyGroup>
    <AssemblyName>{clean_name}</AssemblyName>
    <TargetFramework>py3.11</TargetFramework>
  </PropertyGroup>
</Project>
"""
        psproj_file.write_text(psproj_content, encoding="utf-8")

    # 2. Entrypoint source file: ProjMain.ps
    proj_main_file = target_dir / "ProjMain.ps"
    if not proj_main_file.exists():
        proj_main_content = f"""namespace {clean_name};

using PythonSharp.Core;

public class ProjMain
{{
    public static void Main(string[] args)
    {{
        Console.WriteLine("{clean_name} - Starting");
        TestUtil.Log("Initialized successfully with PythonSharp!");
        Console.WriteLine("{clean_name} - Completed");
    }}
}}
"""
        proj_main_file.write_text(proj_main_content, encoding="utf-8")

    # 3. Helper utility source file: TestUtil.ps
    test_util_file = target_dir / "TestUtil.ps"
    if not test_util_file.exists():
        test_util_content = f"""namespace {clean_name};

using PythonSharp.Core;

public class TestUtil
{{
    public static void Log(string message)
    {{
        Console.WriteLine($"[{clean_name}.TestUtil] {{message}}");
    }}
}}
"""
        test_util_file.write_text(test_util_content, encoding="utf-8")

    # 4. Python runner harness: run_main.py
    run_main_file = target_dir / "run_main.py"
    if not run_main_file.exists():
        module_name = pascal_to_snake(clean_name)
        run_main_content = f"""#!/usr/bin/env python3
\"\"\"Starter entrypoint runner for {clean_name}.\"\"\"

import sys
from pathlib import Path


def main(args: list[str]) -> int:
    proj_dir = Path(__file__).parent.resolve()
    dist_dir = proj_dir / "dist"
    sys.path.insert(0, str(dist_dir))

    from {module_name} import ProjMain

    ProjMain.main(args)
    return 0


if __name__ == "__main__":
    sys.exit(main(args=sys.argv[1:]))
"""
        run_main_file.write_text(run_main_content, encoding="utf-8")

    print(f"Created new PythonSharp project '{clean_name}' in '{target_dir}':")
    print(f"  + {psproj_file.name}")
    print(f"  + {proj_main_file.name}")
    print(f"  + {test_util_file.name}")
    print(f"  + {run_main_file.name}")
    print("\nNext steps:")
    try:
        rel = target_dir.relative_to(Path.cwd())
        print(f"  cd {rel}")
    except ValueError:
        print(f"  cd {target_dir}")
    print("  psc build")
    print("  python run_main.py")
    return 0


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
    check_p.add_argument(
        "--target-surface",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Enforce enterprise surface level (1=Raw, 2=Bridge, 3=Enterprise). Emits PS005 warnings.",
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
    build_p.add_argument(
        "--target-surface",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Enforce enterprise surface level (1=Raw, 2=Bridge, 3=Enterprise). Emits PS005 warnings.",
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
    bindgen_p.add_argument(
        "--triple-surface",
        action="store_true",
        help="Generate 4-file Triple Surface bundle (primitives, raw surface 1, csharp bridge surface 2, enterprise surface 3)",
    )

    clean_p = subparsers.add_parser(
        "clean", help="Delete compiled artifacts and build cache from the output directory"
    )
    clean_p.add_argument(
        "target", type=Path, nargs="?", default=Path("."), help="Path to .psproj, directory, or .ps file"
    )
    clean_p.add_argument("-o", "--out-dir", type=Path, default=None, help="Output directory (default: dist/)")

    rebuild_p = subparsers.add_parser("rebuild", help="Clean output directory and rebuild project from scratch")
    rebuild_p.add_argument(
        "target", type=Path, nargs="?", default=Path("."), help="Path to .psproj, directory, or .ps file"
    )
    rebuild_p.add_argument("-o", "--out-dir", type=Path, default=None, help="Output directory (default: dist/)")
    rebuild_p.add_argument("--no-pyc", action="store_true", help="Disable PEP 552 .pyc bytecode emission")
    rebuild_p.add_argument(
        "--native", action="store_true", help="Compile [NativeCompile] types to C-extensions via mypyc/Cython"
    )
    rebuild_p.add_argument(
        "--target-surface",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Enforce enterprise surface level (1=Raw, 2=Bridge, 3=Enterprise). Emits PS005 warnings.",
    )

    create_p = subparsers.add_parser(
        "create",
        aliases=["new"],
        help="Create a new PythonSharp starter project with .psproj, ProjMain.ps, TestUtil.ps, and run_main.py",
    )
    create_p.add_argument("name", type=str, nargs="?", default=None, help="Project name (e.g. 'PS3' or 'MyApp')")
    create_p.add_argument("-n", "--name", dest="proj_name", type=str, default=None, help="Project name")
    create_p.add_argument(
        "-o", "--out-dir", type=Path, default=None, help="Directory to create project in (default: ./{name})"
    )

    add_p = subparsers.add_parser("add", help="Add a reference or package to the project")
    add_sub = add_p.add_subparsers(dest="add_command", required=False)
    ref_p = add_sub.add_parser("reference", help="Add a project reference to the project")
    ref_p.add_argument("reference", type=Path, help="Path to referenced .psproj or project directory")
    ref_p.add_argument("-p", "--project", type=Path, default=Path("."), help="Target project to update (default: .)")

    add_ref_p = subparsers.add_parser("add-reference", help="Add a project reference to the project")
    add_ref_p.add_argument("reference", type=Path, help="Path to referenced .psproj or project directory")
    add_ref_p.add_argument("-p", "--project", type=Path, default=Path("."), help="Target project to update (default: .)")

    format_p = subparsers.add_parser("format", help="Format PythonSharp (.ps) source files")
    format_p.add_argument("path", type=Path, nargs="?", default=Path("."), help="File or directory to format (default: .)")
    format_p.add_argument("--check", action="store_true", help="Check formatting without modifying files")
    format_p.add_argument("--tab-size", type=int, default=4, help="Number of spaces per indentation level (default: 4)")
    format_p.add_argument("--indent-tabs", action="store_true", help="Indent with tabs instead of spaces")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    if args.command in ("create", "new"):
        name = getattr(args, "proj_name", None) or getattr(args, "name", None)
        if not name:
            print("ERROR: Project name is required. Usage: psc create <name>", file=sys.stderr)
            return 1
        out_dir = getattr(args, "out_dir", None) or (Path.cwd() / name)
        return create_project(name, out_dir)

    if args.command in ("add", "add-reference"):
        if args.command == "add" and getattr(args, "add_command", None) != "reference":
            print("ERROR: Unknown add command. Usage: 'psc add reference <path>'", file=sys.stderr)
            return 1
        ref_path = args.reference
        target_path = getattr(args, "project", Path("."))
        try:
            updated_proj = add_project_reference(target_path, ref_path)
            print(f"Reference '{ref_path}' added to project '{updated_proj}'.")
            return 0
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    if args.command == "clean":
        out_dir = getattr(args, "out_dir", None)
        config = _discover_inputs(args.target, out_dir=out_dir)
        return clean_project(config)

    if args.command == "rebuild":
        out_dir = getattr(args, "out_dir", None)
        config = _discover_inputs(args.target, out_dir=out_dir)
        clean_project(config)

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
            triple_surface=getattr(args, "triple_surface", False),
        )
        print(f"Bindgen succeeded: generated {len(generated)} .d.ps file(s) into '{args.out_dir}'.")
        return 0

    if args.command == "format":
        from psc.formatter import format_code

        target_path = Path(args.path or ".").resolve()
        tab_size = getattr(args, "tab_size", 4)
        insert_spaces = not getattr(args, "indent_tabs", False)
        check_only = getattr(args, "check", False)

        ps_files: list[Path] = []
        if target_path.is_file():
            ps_files = [target_path]
        elif target_path.is_dir():
            ps_files = sorted(
                p
                for p in target_path.rglob("*.ps")
                if not any(x in p.parts for x in ("dist", ".venv", "venv", ".git", "__pycache__"))
            )

        unformatted_count = 0
        for f in ps_files:
            try:
                original = f.read_text(encoding="utf-8")
                formatted = format_code(original, tab_size=tab_size, insert_spaces=insert_spaces)
                if formatted != original:
                    unformatted_count += 1
                    if not check_only:
                        f.write_text(formatted, encoding="utf-8")
                        print(f"Formatted {f.relative_to(target_path.parent if target_path.is_file() else target_path)}")
                    else:
                        print(f"Would reformat {f.relative_to(target_path.parent if target_path.is_file() else target_path)}", file=sys.stderr)
            except Exception as e:
                print(f"ERROR: Failed to format '{f}': {e}", file=sys.stderr)

        if check_only and unformatted_count > 0:
            print(f"{unformatted_count} file(s) would be reformatted.", file=sys.stderr)
            return 1
        print(f"Format complete: {len(ps_files)} file(s) processed ({unformatted_count} formatted).")
        return 0

    out_dir = getattr(args, "out_dir", None)
    config = _discover_inputs(args.target, out_dir=out_dir)

    if not config.source_files:
        print(f"ERROR: No .ps source files found in '{args.target}'.", file=sys.stderr)
        return 1

    stdlib_dir = _find_default_stdlib_dir()
    deps: list[PsProjectConfig] = []
    if config.project_references:
        try:
            deps = resolve_project_dependencies(config, stdlib_dir=stdlib_dir)
        except Exception as e:
            print(f"ERROR: Failed to resolve project dependencies: {e}", file=sys.stderr)
            return 1

    emit_pyc = not getattr(args, "no_pyc", False) and config.emit_pyc
    use_cache = (
        not getattr(args, "no_cache", False)
        and not getattr(args, "force", False)
        and args.command != "rebuild"
    )
    cache_mgr = BuildCacheManager()
    target_surface = getattr(args, "target_surface", None)

    any_dep_rebuilt = False
    if args.command in ("build", "rebuild", "run"):
        for idx, dep in enumerate(deps):
            dep_deps = deps[:idx]
            dep_use_cache = use_cache and args.command != "rebuild"
            if dep_use_cache and cache_mgr.is_up_to_date(dep, emit_pyc=emit_pyc):
                print(f"Dependency '{dep.project_name}' is up to date: outputs in '{dep.out_dir}' are fresh.")
            else:
                print(f"Compiling dependency '{dep.project_name}'...")
                dep_artifacts, dep_diag = compile_single_project(
                    dep,
                    emit_pyc=emit_pyc,
                    target_surface=target_surface,
                    dependency_configs=dep_deps,
                )
                if dep_diag.has_errors():
                    print(dep_diag.format_all(), file=sys.stderr)
                    return 1
                if not getattr(args, "no_cache", False):
                    cache_mgr.save_cache(dep, dep_artifacts, emit_pyc=emit_pyc)
                print(f"Dependency '{dep.project_name}' built successfully ({len(dep_artifacts)} module(s)).")
                any_dep_rebuilt = True

            # Copy dependency outputs into config.out_dir
            _copy_dependency_artifacts(dep.out_dir, config.out_dir)

    if (
        not any_dep_rebuilt
        and use_cache
        and args.command == "build"
        and cache_mgr.is_up_to_date(config, emit_pyc=emit_pyc)
    ):
        print(f"Build is up to date: outputs in '{config.out_dir}' are fresh.")
        return 0

    config_units, symtab, diag = parse_and_analyze_config(
        config, target_surface=target_surface, dependency_configs=deps
    )
    for d in diag.diagnostics:
        if d.severity == "WARNING":
            print(str(d), file=sys.stderr)
    if diag.has_errors():
        print(diag.format_all(), file=sys.stderr)
        return 1

    if args.command == "check":
        print(f"Check succeeded: {len(config.source_files)} .ps file(s) verified with 0 errors.")
        return 0

    if args.command == "dump-ast":
        planner = NamespacePackagePlanner(symtab, target_units=config_units)
        builder = PythonAstBuilder(symtab)
        import ast

        for rel_path, planned in sorted(planner.plan_modules().items()):
            mod_ast = builder.build_module(planned)
            print(f"# === Module: {rel_path} (pinned to {planned.primary_ps_filename}) ===")
            print(ast.unparse(mod_ast))
            print()
        return 0

    emitter = ArtifactEmitter(symtab, target_units=config_units)
    artifacts = emitter.emit_all(config.out_dir, emit_pyc=emit_pyc)

    if args.command in ("build", "rebuild"):
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

        verb = "Rebuild" if args.command == "rebuild" else "Build"
        print(f"{verb} succeeded: emitted {len(artifacts)} module(s) to '{config.out_dir}'.")
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
