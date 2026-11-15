#!/usr/bin/env python3
"""
Test runner for Ported 12_json_logger (python-json-logger in PythonSharp).
Builds the project with `psc` and validates structured JSON logging, renaming, extra fields, and exceptions.
"""
from __future__ import annotations

import io
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building JsonLogger via `psc build` ===")
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

    print("\n=== Step 2: Testing Ported JsonFormatter Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_json_logger import JsonFormatter
    except ImportError as e:
        print(f"Failed to import json_formatter: {e}", file=sys.stderr)
        return 1

    # 1. Basic Formatter output
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    formatter = JsonFormatter()
    handler.setFormatter(formatter)

    test_logger = logging.getLogger("micro_json_test")
    test_logger.setLevel(logging.DEBUG)
    test_logger.handlers = [handler]
    test_logger.propagate = False

    test_logger.info("Service initialized successfully")
    output_line = stream.getvalue().strip()
    data = json.loads(output_line)

    assert data["message"] == "Service initialized successfully"
    assert data["level"] == "INFO"
    assert data["logger"] == "micro_json_test"
    assert "timestamp" in data
    assert data["timestamp"].endswith("Z")
    print("[PASS] Standard record formatting and JSON parsing verified")

    # 2. Custom field renaming
    rename_stream = io.StringIO()
    rename_handler = logging.StreamHandler(rename_stream)
    rename_formatter = JsonFormatter(rename_fields={"timestamp": "@timestamp", "level": "severity", "message": "msg"})
    rename_handler.setFormatter(rename_formatter)

    rename_logger = logging.getLogger("rename_test")
    rename_logger.handlers = [rename_handler]
    rename_logger.propagate = False

    rename_logger.warning("Storage high watermark warning")
    rename_data = json.loads(rename_stream.getvalue().strip())

    assert "@timestamp" in rename_data
    assert rename_data["severity"] == "WARNING"
    assert rename_data["msg"] == "Storage high watermark warning"
    print("[PASS] Custom field renaming (@timestamp, severity, msg) verified")

    # 3. Extra custom attributes
    extra_stream = io.StringIO()
    extra_handler = logging.StreamHandler(extra_stream)
    extra_handler.setFormatter(JsonFormatter())

    extra_logger = logging.getLogger("extra_test")
    extra_logger.setLevel(logging.DEBUG)
    extra_logger.handlers = [extra_handler]
    extra_logger.propagate = False

    extra_logger.info("User checkout completed", extra={"user_id": 42091, "cart_total": 129.99, "is_vip": True})
    extra_data = json.loads(extra_stream.getvalue().strip())

    assert extra_data["user_id"] == 42091
    assert abs(extra_data["cart_total"] - 129.99) < 1e-4
    assert extra_data["is_vip"] is True
    print("[PASS] Extra payload dictionary merging (user_id, cart_total, is_vip) verified")

    # 4. Exception Traceback Serialization
    exc_stream = io.StringIO()
    exc_handler = logging.StreamHandler(exc_stream)
    exc_handler.setFormatter(JsonFormatter())

    exc_logger = logging.getLogger("exc_test")
    exc_logger.setLevel(logging.DEBUG)
    exc_logger.handlers = [exc_handler]
    exc_logger.propagate = False

    try:
        raise ValueError("Database connection timeout")
    except ValueError:
        exc_logger.error("Failed to execute database query", exc_info=True)

    exc_data = json.loads(exc_stream.getvalue().strip())
    assert exc_data["level"] == "ERROR"
    assert exc_data["message"] == "Failed to execute database query"
    assert "exception" in exc_data
    assert "ValueError: Database connection timeout" in exc_data["exception"]
    print("[PASS] Exception traceback serialization verified")

    print("\nAll json-logger verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
