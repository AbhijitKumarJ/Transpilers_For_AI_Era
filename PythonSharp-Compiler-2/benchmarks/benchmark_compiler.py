from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from psc import compile_sources  # noqa: E402

STDLIB = ROOT / "stdlib" / "PythonSharp.Core.d.ps"


def generate_source(classes: int, methods_per_class: int) -> str:
    if classes < 1:
        raise ValueError("classes must be at least 1")
    if methods_per_class < 1:
        raise ValueError("methods_per_class must be at least 1")

    lines = ["namespace Bench;", "", "using PythonSharp.Core;", ""]
    for class_index in range(classes):
        lines.extend(
            [
                f"public class C{class_index}",
                "{",
                "    private readonly Dict<int, int> _values = new Dict<int, int>();",
                "",
                "    public int Total() { return _values.Values().Sum(); }",
            ]
        )
        for method_index in range(1, methods_per_class):
            lines.append(f"    public int M{method_index}(int value) => value + {method_index};")
        lines.extend(["}", ""])
    return "\n".join(lines)


def _cold_import_seconds(out_dir: Path) -> float:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(out_dir)
    code = "import time; started = time.perf_counter(); import bench; print(time.perf_counter() - started)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return float(result.stdout.strip())


def _run_once(*, source: str, measure_import: bool) -> dict[str, float | int | None]:
    with tempfile.TemporaryDirectory(prefix="psc-bench-") as tmp:
        out_dir = Path(tmp) / "dist"
        started = time.perf_counter()
        artifacts, diagnostics = compile_sources(
            sources={"Bench/Bench.ps": source},
            out_dir=out_dir,
            stdlib_source=STDLIB.read_text(encoding="utf-8"),
            assembly_name="Bench",
            emit_pyc=False,
        )
        compile_seconds = time.perf_counter() - started
        if diagnostics.has_errors():
            raise RuntimeError(diagnostics.format_all())

        cold_import_seconds = _cold_import_seconds(out_dir) if measure_import else None
        return {
            "compile_seconds": compile_seconds,
            "cold_import_seconds": cold_import_seconds,
            "emitted_modules": len(artifacts),
            "emitted_bytes": sum(len(artifact.py_source.encode("utf-8")) for artifact in artifacts),
            "emitted_lines": sum(artifact.py_source.count("\n") for artifact in artifacts),
        }


def run_benchmark(
    *,
    classes: int,
    methods_per_class: int,
    budget_seconds: float,
    measure_import: bool,
    runs: int,
) -> dict[str, object]:
    if runs < 1:
        raise ValueError("runs must be at least 1")

    source = generate_source(classes, methods_per_class)
    samples = [_run_once(source=source, measure_import=measure_import) for _ in range(runs)]
    compile_samples = [float(sample["compile_seconds"]) for sample in samples]
    import_samples = [
        float(sample["cold_import_seconds"]) for sample in samples if sample["cold_import_seconds"] is not None
    ]
    best_compile = min(compile_samples)
    return {
        "classes": classes,
        "methods_per_class": methods_per_class,
        "source_lines": source.count("\n") + 1,
        "runs": runs,
        "compile_seconds": round(best_compile, 3),
        "compile_seconds_median": round(statistics.median(compile_samples), 3),
        "compile_seconds_all": [round(value, 3) for value in compile_samples],
        "emitted_modules": samples[0]["emitted_modules"],
        "emitted_bytes": samples[0]["emitted_bytes"],
        "emitted_lines": samples[0]["emitted_lines"],
        "cold_import_seconds": round(statistics.median(import_samples), 3) if import_samples else None,
        "budget_seconds": budget_seconds,
        "within_budget": best_compile <= budget_seconds,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark the PythonSharp compiler on a generated project.")
    parser.add_argument("--classes", type=int, default=1000, help="Number of generated classes (default: 1000).")
    parser.add_argument(
        "--methods",
        type=int,
        default=21,
        help="Methods per generated class, including Total() (default: 21).",
    )
    parser.add_argument(
        "--budget-seconds",
        type=float,
        default=30.0,
        help="Fail if the best compile run exceeds this many seconds (default: 30.0).",
    )
    parser.add_argument("--runs", type=int, default=3, help="Number of compile runs; best time is the budget metric.")
    parser.add_argument("--no-import", action="store_true", help="Skip the cold-import measurement.")
    parser.add_argument("--json", action="store_true", help="Emit metrics as JSON.")
    args = parser.parse_args(argv)

    metrics = run_benchmark(
        classes=args.classes,
        methods_per_class=args.methods,
        budget_seconds=args.budget_seconds,
        measure_import=not args.no_import,
        runs=args.runs,
    )
    if args.json:
        print(json.dumps(metrics, indent=2, sort_keys=True))
    else:
        print("PythonSharp compiler benchmark")
        print(f"  classes: {metrics['classes']}")
        print(f"  methods per class: {metrics['methods_per_class']}")
        print(f"  source lines: {metrics['source_lines']}")
        print(f"  runs: {metrics['runs']}")
        print(f"  compile seconds (best): {metrics['compile_seconds']}")
        print(f"  compile seconds (median): {metrics['compile_seconds_median']}")
        print(f"  compile seconds (all): {metrics['compile_seconds_all']}")
        print(f"  emitted modules: {metrics['emitted_modules']}")
        print(f"  emitted bytes: {metrics['emitted_bytes']}")
        print(f"  emitted lines: {metrics['emitted_lines']}")
        print(f"  cold import seconds: {metrics['cold_import_seconds']}")
        print(f"  budget seconds: {metrics['budget_seconds']}")
        print(f"  within budget: {metrics['within_budget']}")

    return 0 if metrics["within_budget"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
