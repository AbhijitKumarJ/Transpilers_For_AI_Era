#!/usr/bin/env python3
"""Verification harness for ported 02_slugify library."""

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).parent.resolve()
    print("=== Step 1: Building Slugify via `psc build` ===")
    cmd = ["psc", "build", str(proj_dir)] if shutil.which("psc") else [sys.executable, "-m", "psc.cli", "build", str(proj_dir)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout.strip())
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        return res.returncode

    print("\n=== Step 2: Testing Ported Slugifier Functionality ===")
    dist_dir = proj_dir / "dist"
    sys.path.insert(0, str(dist_dir))

    from slugify_util import Slugifier

    # Test 1: Standard URL slug
    s1 = Slugifier.slugify("Hello World!")
    assert s1 == "hello-world", f"Expected 'hello-world', got {repr(s1)}"
    print(f"[PASS] Slugifier.slugify('Hello World!') -> {repr(s1)}")

    # Test 2: Punctuation & symbols cleaning
    s2 = Slugifier.slugify("  Special @#$ Characters & More  ")
    assert s2 == "special-characters-more", f"Expected 'special-characters-more', got {repr(s2)}"
    print(f"[PASS] Slugifier.slugify('  Special @#$ Characters & More  ') -> {repr(s2)}")

    # Test 3: Custom separator and preserve case
    s3 = Slugifier.slugify("Custom_Separator_Test", "_", False)
    assert s3 == "Custom_Separator_Test", f"Expected 'Custom_Separator_Test', got {repr(s3)}"
    print(f"[PASS] Slugifier.slugify('Custom_Separator_Test', '_', False) -> {repr(s3)}")

    # Test 4: Technical titles
    s4 = Slugifier.slugify("C# to Python Transpiler 2026")
    assert s4 == "c-to-python-transpiler-2026", f"Expected 'c-to-python-transpiler-2026', got {repr(s4)}"
    print(f"[PASS] Slugifier.slugify('C# to Python Transpiler 2026') -> {repr(s4)}")

    # Test 5: Empty string
    s5 = Slugifier.slugify("")
    assert s5 == "", f"Expected '', got {repr(s5)}"
    print(f"[PASS] Slugifier.slugify('') -> {repr(s5)}")

    print("\nAll slugify verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

