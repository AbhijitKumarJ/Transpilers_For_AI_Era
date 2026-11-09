#!/usr/bin/env python3
"""Verification harness for ported 03_isprime library."""

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).parent.resolve()
    print("=== Step 1: Building IsPrime via `psc build` ===")
    cmd = ["psc", "build", str(proj_dir)] if shutil.which("psc") else [sys.executable, "-m", "psc.cli", "build", str(proj_dir)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout.strip())
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        return res.returncode

    print("\n=== Step 2: Testing Ported PrimeMath Functionality ===")
    dist_dir = proj_dir / "dist"
    sys.path.insert(0, str(dist_dir))

    from math_util import PrimeMath

    # Test 1: Primality tests
    primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 97, 999983]
    for p in primes:
        assert PrimeMath.is_prime(p) is True, f"Expected {p} to be prime"
    print(f"[PASS] PrimeMath.is_prime on {len(primes)} primes")

    # Test 2: Composite numbers
    composites = [0, 1, -5, 4, 6, 8, 9, 15, 21, 25, 27, 100, 1000]
    for c in composites:
        assert PrimeMath.is_prime(c) is False, f"Expected {c} to be composite"
    print(f"[PASS] PrimeMath.is_prime on {len(composites)} composites")

    # Test 3: Next prime
    assert PrimeMath.next_prime(17) == 19
    assert PrimeMath.next_prime(20) == 23
    print("[PASS] PrimeMath.next_prime(17) -> 19, next_prime(20) -> 23")

    # Test 4: Primes up to limit
    up_to_30 = PrimeMath.primes_up_to(30)
    assert up_to_30 == [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
    print(f"[PASS] PrimeMath.primes_up_to(30) -> {up_to_30}")

    # Test 5: Prime factorization
    f84 = PrimeMath.prime_factors(84)
    assert f84 == [2, 2, 3, 7], f"Expected [2, 2, 3, 7], got {f84}"
    f360 = PrimeMath.prime_factors(360)
    assert f360 == [2, 2, 2, 3, 3, 5], f"Expected [2, 2, 2, 3, 3, 5], got {f360}"
    print(f"[PASS] PrimeMath.prime_factors(84) -> {f84}, prime_factors(360) -> {f360}")

    print("\nAll isprime verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
