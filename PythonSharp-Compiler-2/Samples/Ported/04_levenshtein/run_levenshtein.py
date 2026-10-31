#!/usr/bin/env python3
"""Verification harness for ported 04_levenshtein library."""

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).parent.resolve()
    print("=== Step 1: Building Levenshtein via `psc build` ===")
    cmd = ["psc", "build", str(proj_dir)] if shutil.which("psc") else [sys.executable, "-m", "psc.cli", "build", str(proj_dir)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout.strip())
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        return res.returncode

    print("\n=== Step 2: Testing Ported Levenshtein Functionality ===")
    dist_dir = proj_dir / "dist"
    sys.path.insert(0, str(dist_dir))

    from distance_util import Levenshtein

    # Test 1: Classic kitten -> sitting edit distance
    d1 = Levenshtein.distance("kitten", "sitting")
    assert d1 == 3, f"Expected 3, got {d1}"
    print(f"[PASS] Levenshtein.distance('kitten', 'sitting') -> {d1}")

    # Test 2: flaw -> lawn
    d2 = Levenshtein.distance("flaw", "lawn")
    assert d2 == 2, f"Expected 2, got {d2}"
    print(f"[PASS] Levenshtein.distance('flaw', 'lawn') -> {d2}")

    # Test 3: Identical strings
    d3 = Levenshtein.distance("pythonsharp", "pythonsharp")
    assert d3 == 0, f"Expected 0, got {d3}"
    print(f"[PASS] Levenshtein.distance('pythonsharp', 'pythonsharp') -> {d3}")

    # Test 4: Empty strings
    assert Levenshtein.distance("", "hello") == 5
    assert Levenshtein.distance("world", "") == 5
    print("[PASS] Levenshtein empty string boundary checks")

    # Test 5: Ratio calculation
    r1 = Levenshtein.ratio("kitten", "sitting")
    expected_r1 = 1.0 - (6.0 / 13.0)
    assert abs(r1 - expected_r1) < 1e-6, f"Expected ~{expected_r1}, got {r1}"
    print(f"[PASS] Levenshtein.ratio('kitten', 'sitting') -> {r1:.4f}")

    r2 = Levenshtein.ratio("identical", "identical")
    assert r2 == 1.0, f"Expected 1.0, got {r2}"
    print(f"[PASS] Levenshtein.ratio('identical', 'identical') -> {r2}")

    print("\nAll levenshtein verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

