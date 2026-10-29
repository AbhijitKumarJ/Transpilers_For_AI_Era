#!/usr/bin/env python3
"""
Test runner for Ported 08_micro_requests (Micro Requests HTTP client in PythonSharp).
Builds the project with `psc` and validates GET, POST, JSON decoding, status codes, and error handling
against a local in-process standard library HTTP server.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class MockHttpHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass  # Quiet logging during automated tests

    def do_GET(self) -> None:
        if self.path == "/hello":
            payload = json.dumps({"message": "Hello from PythonSharp!", "success": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.path == "/headers":
            self.send_response(200)
            self.send_header("X-PythonSharp-Test", "Verified")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"OK")
        elif self.path == "/not-found":
            self.send_response(404)
            self.send_header("Content-Length", "16")
            self.end_headers()
            self.wfile.write(b"Resource missing")
        else:
            self.send_response(400)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path == "/echo":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(400)
            self.end_headers()


def start_mock_server() -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), MockHttpHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building MicroRequests via `psc build` ===")
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

    print("\n=== Step 2: Testing Ported HttpClient Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_requests import HttpClient, HttpResponse
    except ImportError as e:
        print(f"Failed to import micro_requests: {e}", file=sys.stderr)
        return 1

    server, port = start_mock_server()
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. GET Request + JSON decoding
        get_res = HttpClient.get(f"{base_url}/hello")
        assert isinstance(get_res, HttpResponse)
        assert get_res.status_code == 200, f"Got: {get_res.status_code}"
        assert get_res.is_success_status_code
        data = get_res.json()
        assert data["message"] == "Hello from PythonSharp!"
        assert data["success"] is True
        print(f"[PASS] GET /hello -> status: {get_res.status_code}, json: {data}")

        # 2. POST Request with payload
        payload_str = json.dumps({"port": 8, "library": "micro_requests", "tier": "Networking"})
        post_res = HttpClient.post(
            f"{base_url}/echo",
            data=payload_str,
            headers={"Content-Type": "application/json"},
        )
        assert post_res.status_code == 201
        assert post_res.is_success_status_code
        post_data = post_res.json()
        assert post_data["library"] == "micro_requests"
        assert post_data["tier"] == "Networking"
        print(f"[PASS] POST /echo -> status: {post_res.status_code}, echoed: {post_data}")

        # 3. Custom Response Headers
        header_res = HttpClient.get(f"{base_url}/headers")
        assert header_res.status_code == 200
        headers_lower = {k.lower(): v for k, v in header_res.headers.items()}
        assert headers_lower.get("x-pythonsharp-test") == "Verified"
        print(f"[PASS] GET /headers -> header 'X-PythonSharp-Test': {headers_lower.get('x-pythonsharp-test')}")

        # 4. HTTP 404 Error handling
        not_found_res = HttpClient.get(f"{base_url}/not-found")
        assert not_found_res.status_code == 404
        assert not not_found_res.is_success_status_code
        assert "Resource missing" in not_found_res.text
        print(f"[PASS] GET /not-found -> status: {not_found_res.status_code}, text: {not_found_res.text}")

        # 5. Network Connection Failure Handling
        # Connecting to a closed port
        fail_res = HttpClient.get("http://127.0.0.1:1/nonexistent", timeout=1)
        assert fail_res.status_code == 0
        assert not fail_res.is_success_status_code
        print(f"[PASS] Network error safely caught -> status: {fail_res.status_code}, error captured in body")

    finally:
        server.shutdown()
        server.server_close()

    print("\nAll micro_requests verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
