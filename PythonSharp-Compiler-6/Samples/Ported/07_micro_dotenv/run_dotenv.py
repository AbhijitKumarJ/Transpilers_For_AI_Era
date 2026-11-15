#!/usr/bin/env python3
"""
Test runner for Ported 07_micro_dotenv (Python-dotenv reader in PythonSharp).
Builds the project with `psc` and validates .env parsing, quote unescaping, and environment loading.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building MicroDotEnv via `psc build` ===")
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

    print("\n=== Step 2: Testing Ported DotEnv Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_dot_env import DotEnv
    except ImportError as e:
        print(f"Failed to import micro_dot_env: {e}", file=sys.stderr)
        return 1

    # 1. In-memory .env content parsing
    sample_env = """
    # Server Configuration
    HOST=127.0.0.1
    PORT=8080 # Default HTTP port
    export APP_ENV=production

    # Quoted values
    DB_NAME="my_app_production"
    MULTILINE="Line 1\\nLine 2\\tTabbed"
    RAW_PATH='C:\\Windows\\System32'

    # Empty value
    SECRET_KEY=
    """

    parsed = DotEnv.parse(sample_env)
    assert parsed["HOST"] == "127.0.0.1", f"Got: {parsed['HOST']}"
    assert parsed["PORT"] == "8080", f"Got: {parsed['PORT']}"
    assert parsed["APP_ENV"] == "production", f"Got: {parsed['APP_ENV']}"
    assert parsed["DB_NAME"] == "my_app_production", f"Got: {parsed['DB_NAME']}"
    assert parsed["MULTILINE"] == "Line 1\nLine 2\tTabbed", f"Got: {repr(parsed['MULTILINE'])}"
    assert parsed["RAW_PATH"] == "C:\\Windows\\System32", f"Got: {parsed['RAW_PATH']}"
    assert parsed["SECRET_KEY"] == "", f"Got: {parsed['SECRET_KEY']}"
    print(f"[PASS] DotEnv.parse successfully extracted {len(parsed)} keys with quotes and comments handled")

    # 2. File Loading & os.environ integration
    with tempfile.TemporaryDirectory() as tmp_dir:
        env_file = Path(tmp_dir) / ".env.test"
        env_file.write_text(
            "TEST_PORT_7_VAR=pythonsharp_rocks\n"
            "TEST_PORT_7_OVERRIDE=original\n",
            encoding="utf-8",
        )

        # Ensure environment is clean before test
        os.environ.pop("TEST_PORT_7_VAR", None)
        os.environ["TEST_PORT_7_OVERRIDE"] = "preset"

        loaded = DotEnv.load(str(env_file), override_existing=False)
        assert len(loaded) == 2
        assert os.environ.get("TEST_PORT_7_VAR") == "pythonsharp_rocks"
        assert os.environ.get("TEST_PORT_7_OVERRIDE") == "preset"
        print("[PASS] DotEnv.load correctly set default environment variables without overriding")

        # Now test with override_existing=True
        DotEnv.load(str(env_file), override_existing=True)
        assert os.environ.get("TEST_PORT_7_OVERRIDE") == "original"
        print("[PASS] DotEnv.load with override_existing=True updated existing variables")

    # 3. Missing file handling
    missing_dict = DotEnv.load("/non/existent/path/.env")
    assert missing_dict == {}
    print("[PASS] DotEnv.load on missing file safely returned empty dictionary")

    print("\nAll micro_dotenv verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
