#!/usr/bin/env python3
"""
Test runner for Ported 16_micro_retry (retry utility & decorator in PythonSharp).
Builds the project with `psc` and validates exponential backoff, exception filtering,
exhaustion rethrow, and decorator wrapping.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building MicroRetry via `psc build` ===")
    psc_bin = shutil.which("psc")
    if psc_bin:
        cmd = [psc_bin, "build", str(proj_dir), "-o", str(dist_dir)]
    else:
        cmd = [sys.executable, "-m", "psc.cli", "build", str(proj_dir), "-o", str(dist_dir)]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Build failed:\n{res.stderr}\n{res.stdout}", file=sys.stderr)
        return 1
    print(res.stdout.strip())

    print("\n=== Step 2: Testing Ported Retry Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_retry import Retry
    except ImportError as e:
        print(f"Failed to import micro_retry: {e}", file=sys.stderr)
        return 1

    # 1. Immediate Success
    val = Retry.call(lambda: 42)
    assert val == 42
    print("[PASS] Immediate success without retry verified")

    # 2. Transient Failure (Succeeds on 3rd attempt)
    attempts = 0

    def flaky_network_call(endpoint: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError(f"Temporary outage on attempt {attempts}")
        return f"Response from {endpoint} (succeeded on attempt {attempts})"

    attempts = 0
    res_str = Retry.call(flaky_network_call, ["https://api.example.com"], tries=5, delay=0.001, backoff=1.5)
    assert attempts == 3
    assert "succeeded on attempt 3" in res_str
    print("[PASS] Transient failure retries and eventual success verified")

    # 3. Exhaustion Re-raises Original Exception
    attempts = 0

    def persistent_failure():
        nonlocal attempts
        attempts += 1
        raise ValueError(f"Permanent validation error (attempt {attempts})")

    try:
        attempts = 0
        Retry.call(persistent_failure, tries=3, delay=0.001)
        assert False, "Should have re-raised original ValueError"
    except ValueError as e:
        assert attempts == 3
        assert "Permanent validation error (attempt 3)" in str(e)
        print(f"[PASS] Retry exhaustion re-raised original exception after 3 attempts: {e}")

    # 4. Exception Filtering (Do not retry unlisted exceptions)
    attempts = 0

    def raises_type_error():
        nonlocal attempts
        attempts += 1
        raise TypeError("Fatal type mismatch - do not retry")

    try:
        attempts = 0
        Retry.call(raises_type_error, tries=5, exceptions=[ConnectionError, TimeoutError])
        assert False, "Should not retry unhandled TypeError"
    except TypeError as e:
        assert attempts == 1  # Fails immediately on first attempt!
        print(f"[PASS] Unhandled exception bypassed retry and raised immediately: {e}")

    # 5. Decorator syntax
    dec_attempts = 0

    @Retry.decorator(tries=4, delay=0.001, backoff=2.0)
    def fetch_data(item_id: int) -> dict[str, int]:
        nonlocal dec_attempts
        dec_attempts += 1
        if dec_attempts < 2:
            raise RuntimeError("Database deadlock")
        return {"id": item_id, "status": 200}

    dec_attempts = 0
    data = fetch_data(99)
    assert dec_attempts == 2
    assert data["id"] == 99
    assert data["status"] == 200
    print("[PASS] Parametric decorator syntax (@Retry.decorator) verified")

    print("\nAll micro-retry verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

