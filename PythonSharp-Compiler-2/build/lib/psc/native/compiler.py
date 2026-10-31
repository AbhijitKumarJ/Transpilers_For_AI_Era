from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from psc.semantics import GlobalSymbolTable


@dataclass(slots=True)
class NativeCompileResult:
    success: bool
    output_binary: Path | None = None
    error: str | None = None
    compiler_used: str | None = None


class NativeCompiler:
    """Orchestrates AOT C-extension compilation via mypyc or Cython for [NativeCompile] types."""

    def __init__(self, preferred_compiler: str = "mypyc") -> None:
        self.preferred_compiler = preferred_compiler

    @staticmethod
    def has_native_types(symtab: GlobalSymbolTable) -> bool:
        """Returns True if any type in the symbol table is decorated with [NativeCompile]."""
        for type_sym in symtab.types_by_id.values():
            if type_sym.is_native_compile:
                return True
            if type_sym.ast_node:
                for attr in type_sym.ast_node.attributes:
                    if attr.path and attr.path[-1] in ("NativeCompile", "NativeCompileAttribute"):
                        return True
        return False

    def compile_module(
        self,
        py_source_path: Path,
        out_dir: Path | None = None,
    ) -> NativeCompileResult:
        """
        Compiles a generated Python source file to a native C-extension (.so/.pyd).
        Attempts `mypyc` first, followed by `cythonize` if mypyc is not available.
        """
        py_source_path = py_source_path.resolve()
        target_dir = (out_dir or py_source_path.parent).resolve()

        # Check for mypyc CLI
        mypyc_bin = shutil.which("mypyc")
        if mypyc_bin:
            cmd = [
                mypyc_bin,
                "--ignore-missing-imports",
                str(py_source_path),
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(target_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode == 0:
                    # Look for generated .so or .pyd
                    binaries = list(target_dir.glob(f"{py_source_path.stem}.*so")) + list(
                        target_dir.glob(f"{py_source_path.stem}.*pyd")
                    )
                    out_bin = binaries[0] if binaries else None
                    return NativeCompileResult(
                        success=True,
                        output_binary=out_bin,
                        compiler_used="mypyc",
                    )
                return NativeCompileResult(
                    success=False,
                    error=proc.stderr or proc.stdout,
                    compiler_used="mypyc",
                )
            except Exception as e:
                return NativeCompileResult(
                    success=False,
                    error=str(e),
                    compiler_used="mypyc",
                )

        # Check for cythonize CLI
        cython_bin = shutil.which("cythonize")
        if cython_bin:
            cmd = [
                cython_bin,
                "-3",
                "-i",
                str(py_source_path),
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(target_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode == 0:
                    binaries = list(target_dir.glob(f"{py_source_path.stem}.*so")) + list(
                        target_dir.glob(f"{py_source_path.stem}.*pyd")
                    )
                    out_bin = binaries[0] if binaries else None
                    return NativeCompileResult(
                        success=True,
                        output_binary=out_bin,
                        compiler_used="cython",
                    )
                return NativeCompileResult(
                    success=False,
                    error=proc.stderr or proc.stdout,
                    compiler_used="cython",
                )
            except Exception as e:
                return NativeCompileResult(
                    success=False,
                    error=str(e),
                    compiler_used="cython",
                )

        return NativeCompileResult(
            success=False,
            error=(
                "Neither 'mypyc' nor 'cythonize' was found on PATH. "
                "To enable AOT native compilation for [NativeCompile], run: pip install mypy"
            ),
        )
