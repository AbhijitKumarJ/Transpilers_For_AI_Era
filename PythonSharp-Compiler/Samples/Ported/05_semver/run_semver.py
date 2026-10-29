#!/usr/bin/env python3
"""
Test runner for Ported 05_semver (SemVer 2.0.0 Parser and Comparator in PythonSharp).
Builds the project with `psc` and validates SemVer 2.0.0 semantics.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building SemVer via `psc build` ===")
    psc_bin = shutil.which("psc")
    if psc_bin:
        cmd = [psc_bin, "build", str(proj_dir)]
    else:
        cmd = [sys.executable, "-m", "psc.cli", "build", str(proj_dir)]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Build failed:\n{res.stderr}\n{res.stdout}", file=sys.stderr)
        return 1
    print(res.stdout.strip())

    print("\n=== Step 2: Testing Ported SemVer Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from sem_ver_util import SemVer
    except ImportError as e:
        print(f"Failed to import sem_ver_util: {e}", file=sys.stderr)
        return 1

    # 1. Parsing tests
    v1 = SemVer.parse("1.2.3")
    assert v1.major == 1 and v1.minor == 2 and v1.patch == 3, f"Unexpected: {v1}"
    assert v1.prerelease == "" and v1.build == ""
    assert v1.formatted() == "1.2.3"
    print(f"[PASS] SemVer.parse('1.2.3') -> {v1.formatted()}")

    v2 = SemVer.parse("2.0.1-alpha.1")
    assert v2.major == 2 and v2.minor == 0 and v2.patch == 1
    assert v2.prerelease == "alpha.1" and v2.build == ""
    assert v2.formatted() == "2.0.1-alpha.1"
    print(f"[PASS] SemVer.parse('2.0.1-alpha.1') -> {v2.formatted()}")

    v3 = SemVer.parse("1.0.0-beta.2+exp.sha.5114f85")
    assert v3.major == 1 and v3.minor == 0 and v3.patch == 0
    assert v3.prerelease == "beta.2" and v3.build == "exp.sha.5114f85"
    assert v3.formatted() == "1.0.0-beta.2+exp.sha.5114f85"
    print(f"[PASS] SemVer.parse with prerelease and build metadata -> {v3.formatted()}")

    # 2. Error handling
    try:
        SemVer.parse("invalid-version")
        assert False, "Should have thrown ValueError"
    except ValueError:
        print("[PASS] SemVer.parse('invalid-version') correctly raised ValueError")

    # 3. Precedence and Comparison tests (SemVer 2.0.0 canonical ordering)
    # 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0
    precedence_chain = [
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0",
        "1.0.1",
        "1.1.0",
        "2.0.0",
    ]

    for i in range(len(precedence_chain) - 1):
        earlier = SemVer.parse(precedence_chain[i])
        later = SemVer.parse(precedence_chain[i + 1])
        assert earlier.compare_to(later) < 0, f"Expected {earlier.formatted()} < {later.formatted()}"
        assert later.compare_to(earlier) > 0, f"Expected {later.formatted()} > {earlier.formatted()}"
        assert earlier.is_less_than(later)
        assert later.is_greater_than(earlier)
        assert not earlier.is_equal_to(later)
    print(f"[PASS] Canonical SemVer 2.0.0 precedence chain verified across {len(precedence_chain)} versions")

    # 4. Build metadata ignored in precedence
    v_b1 = SemVer.parse("1.0.0+build.1")
    v_b2 = SemVer.parse("1.0.0+build.2")
    assert v_b1.compare_to(v_b2) == 0, "Build metadata should not affect comparison"
    assert v_b1.is_equal_to(v_b2)
    print("[PASS] Build metadata ignored in precedence (1.0.0+build.1 == 1.0.0+build.2)")

    # 5. Compatibility (Caret ^ rule)
    app_v = SemVer.parse("1.2.5")
    assert app_v.is_compatible_with(SemVer.parse("1.2.0"))
    assert not app_v.is_compatible_with(SemVer.parse("2.0.0"))
    assert not app_v.is_compatible_with(SemVer.parse("1.3.0"))

    zero_v = SemVer.parse("0.2.3")
    assert zero_v.is_compatible_with(SemVer.parse("0.2.1"))
    assert not zero_v.is_compatible_with(SemVer.parse("0.3.0"))
    print("[PASS] SemVer.is_compatible_with caret rules verified")

    print("\nAll semver verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
