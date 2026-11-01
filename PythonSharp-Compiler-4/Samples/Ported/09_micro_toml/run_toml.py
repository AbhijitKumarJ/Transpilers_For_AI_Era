#!/usr/bin/env python3
"""
Test runner for Ported 09_micro_toml (pytoml/toml parser & serializer in PythonSharp).
Builds the project with `psc` and validates TOML parsing, types, tables, arrays, and dumps.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building MicroToml via `psc build` ===")
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

    print("\n=== Step 2: Testing Ported Toml Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_toml import Toml
    except ImportError as e:
        print(f"Failed to import micro_toml: {e}", file=sys.stderr)
        return 1

    # 1. Basic Key-Value Parsing
    toml_text = """
    # Global Config
    title = "PythonSharp TOML Test"
    version = 1
    ratio = 0.95
    enabled = true
    disabled = false
    raw_str = 'C:\\path\\to\\file'
    escaped_str = "line1\\nline2\\ttab\\\"quote"
    comment_in_str = "this # is not a comment"
    """
    data = Toml.parse(toml_text)
    assert data["title"] == "PythonSharp TOML Test", f"Unexpected title: {data['title']}"
    assert data["version"] == 1, f"Unexpected version: {data['version']}"
    assert abs(data["ratio"] - 0.95) < 1e-6, f"Unexpected ratio: {data['ratio']}"
    assert data["enabled"] is True
    assert data["disabled"] is False
    assert data["raw_str"] == r"C:\path\to\file"
    assert data["escaped_str"] == 'line1\nline2\ttab"quote'
    assert data["comment_in_str"] == "this # is not a comment"
    print("[PASS] Basic primitives (string, literal string, int, float, bool, escapes) verified")

    # 2. Arrays & Inline Tables
    toml_arrays = """
    primes = [2, 3, 5, 7, 11]
    tags = ["alpha", "beta", "gamma"]
    nested = [[1, 2], [3, 4]]
    point = { x = 10, y = 20, label = "origin" }
    """
    arr_data = Toml.parse(toml_arrays)
    assert arr_data["primes"] == [2, 3, 5, 7, 11]
    assert arr_data["tags"] == ["alpha", "beta", "gamma"]
    assert arr_data["nested"] == [[1, 2], [3, 4]]
    assert arr_data["point"]["x"] == 10
    assert arr_data["point"]["y"] == 20
    assert arr_data["point"]["label"] == "origin"
    print("[PASS] Arrays, nested arrays, and inline tables verified")

    # 3. Dotted Keys
    toml_dotted = """
    server.host = "127.0.0.1"
    server.port = 8080
    server.options.tls = true
    """
    dotted_data = Toml.parse(toml_dotted)
    assert dotted_data["server"]["host"] == "127.0.0.1"
    assert dotted_data["server"]["port"] == 8080
    assert dotted_data["server"]["options"]["tls"] is True
    print("[PASS] Dotted keys (server.options.tls) verified")

    # 4. Standard Tables [section] and Nested Tables [section.sub]
    toml_tables = """
    [database]
    server = "192.168.1.1"
    ports = [8001, 8001, 8002]
    connection_max = 5000
    enabled = true

    [database.credentials]
    user = "admin"
    password = "secret_password"
    """
    table_data = Toml.parse(toml_tables)
    assert table_data["database"]["server"] == "192.168.1.1"
    assert table_data["database"]["ports"] == [8001, 8001, 8002]
    assert table_data["database"]["credentials"]["user"] == "admin"
    assert table_data["database"]["credentials"]["password"] == "secret_password"
    print("[PASS] Standard tables and nested [database.credentials] verified")

    # 5. Array of Tables [[table]]
    toml_array_tables = """
    [[products]]
    name = "Hammer"
    sku = 738594937

    [[products]]
    name = "Nail"
    sku = 284758393
    color = "gray"
    """
    prod_data = Toml.parse(toml_array_tables)
    assert len(prod_data["products"]) == 2
    assert prod_data["products"][0]["name"] == "Hammer"
    assert prod_data["products"][0]["sku"] == 738594937
    assert prod_data["products"][1]["name"] == "Nail"
    assert prod_data["products"][1]["color"] == "gray"
    print("[PASS] Array of tables [[products]] verified")

    # 6. Serialization (Dumps) and Round-Trip Parity
    original_dict = {
        "title": "Config",
        "active": True,
        "count": 42,
        "tags": ["web", "api"],
        "server": {
            "host": "0.0.0.0",
            "port": 9000
        },
        "items": [
            {"id": 1, "name": "ItemA"},
            {"id": 2, "name": "ItemB"}
        ]
    }
    dumped_str = Toml.dumps(original_dict)
    reparsed = Toml.parse(dumped_str)

    assert reparsed["title"] == original_dict["title"]
    assert reparsed["active"] == original_dict["active"]
    assert reparsed["count"] == original_dict["count"]
    assert reparsed["tags"] == original_dict["tags"]
    assert reparsed["server"]["host"] == original_dict["server"]["host"]
    assert reparsed["server"]["port"] == original_dict["server"]["port"]
    assert len(reparsed["items"]) == 2
    assert reparsed["items"][0]["name"] == "ItemA"
    assert reparsed["items"][1]["name"] == "ItemB"
    print("[PASS] Dumps serialization and roundtrip parse parity verified")

    print("\nAll micro-toml verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

