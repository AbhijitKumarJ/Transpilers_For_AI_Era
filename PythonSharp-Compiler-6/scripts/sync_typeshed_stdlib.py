#!/usr/bin/env python3
"""
PythonSharp Typeshed Stdlib Synchronizer (Layer 2 Long-Tail Stubs).
Generates clean ambient .d.ps stubs from upstream Typeshed using ps-bindgen.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    import typeshed_client
except ImportError:
    print("ERROR: 'typeshed_client' is required for synchronizing stdlib stubs.", file=sys.stderr)
    print("Install it with: uv pip install typeshed-client", file=sys.stderr)
    sys.exit(1)

from psc.bindgen import generate_bindings


# Modules managed by Layer 0 (Core) or Layer 1 (Curated High-Value Domains)
# These MUST NEVER be overwritten by raw Typeshed output.
PROTECTED_MODULES: set[str] = {
    "builtins",
    "math",
    "sys",
    "os",
    "json",
    "re",
    "pathlib",
    "time",
    "datetime",
    "logging",
    "subprocess",
    "contextlib",
    "hashlib",
    "uuid",
    "shutil",
    # AI / Math curated domains
    "numpy",
    "scipy",
    "pandas",
    "matplotlib",
    "seaborn",
    "sklearn",
    "torch",
    "sympy",
    "qiskit",
    "polars",
    "xgboost",
    "lightgbm",
    "optuna",
    "transformers",
    "faiss",
    "onnxruntime",
}


def sync_stdlib_stubs(
    out_dir: Path,
    selected_modules: list[str] | None = None,
    dry_run: bool = False,
) -> int:
    ctx = typeshed_client.get_search_context()
    all_stubs = list(typeshed_client.get_all_stub_files(ctx))

    out_dir.mkdir(parents=True, exist_ok=True)
    synced_count = 0
    skipped_count = 0
    processed_modules: set[str] = set()

    print(f"Discovered {len(all_stubs)} total stub entries from typeshed.")
    print(f"Output directory: {out_dir}")

    # Standard library stubs are located under typeshed_client/typeshed/stdlib
    for mod_name, pyi_path in all_stubs:
        p_str = str(pyi_path)
        if "/stdlib/" not in p_str and "\\stdlib\\" not in p_str:
            continue

        parts = list(pyi_path.parts)
        try:
            idx = parts.index("stdlib")
            rel_parts = list(parts[idx + 1 :])
            rel_parts[-1] = pyi_path.stem
            if rel_parts[-1] == "__init__":
                rel_parts.pop()
            clean_mod = ".".join(rel_parts)
        except ValueError:
            clean_mod = mod_name
            for prefix in (
                "typeshed_client.typeshed.stdlib.",
                "typeshed_client.typeshed.",
                "mypy.typeshed.stdlib.",
                "mypy.typeshed.",
            ):
                if clean_mod.startswith(prefix):
                    clean_mod = clean_mod[len(prefix) :]
                    break

        top_mod = clean_mod.split(".")[0]
        if top_mod.startswith("_") or top_mod in PROTECTED_MODULES:
            skipped_count += 1
            continue

        if selected_modules and not any(clean_mod == m or clean_mod.startswith(f"{m}.") for m in selected_modules):
            continue

        if clean_mod in processed_modules:
            continue
        processed_modules.add(clean_mod)

        if dry_run:
            print(f"[DRY-RUN] Would sync {clean_mod} -> {pyi_path}")
            synced_count += 1
            continue

        try:
            generated = generate_bindings(
                pyi_path,
                out_dir=out_dir,
                root_namespace="Extern",
                module_name=clean_mod,
                triple_surface=False,
            )
            synced_count += len(generated)
        except Exception as e:
            print(f"WARNING: Failed to generate bindings for {clean_mod} ({pyi_path}): {e}", file=sys.stderr)

    print("\n--- Synchronization Summary ---")
    print(f"Synced .d.ps stubs: {synced_count}")
    print(f"Protected / private (skipped): {skipped_count}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize Python stdlib typeshed stubs to PythonSharp .d.ps stubs")
    parser.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "stdlib" / "03_typeshed_replica",
        help="Target directory (default: stdlib/03_typeshed_replica/)",
    )
    parser.add_argument(
        "-m",
        "--modules",
        nargs="+",
        default=None,
        help="Specific modules to sync (e.g. urllib sqlite3 csv asyncio)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate synchronization without writing files",
    )
    args = parser.parse_args()
    return sync_stdlib_stubs(
        args.out_dir,
        selected_modules=args.modules,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
