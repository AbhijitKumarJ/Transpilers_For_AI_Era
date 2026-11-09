from __future__ import annotations

import json
from typing import BinaryIO


class JsonRpcProtocol:
    """Handles JSON-RPC 2.0 transport over binary streams with Content-Length framing."""

    @staticmethod
    def read_message(stream: BinaryIO) -> dict[str, object] | None:
        """Reads a single JSON-RPC message from a binary stream, or returns None on EOF."""
        content_length: int | None = None

        while True:
            line = stream.readline()
            if not line:
                return None
            line_str = line.decode("ascii", errors="replace").strip()
            if not line_str:
                break
            if line_str.lower().startswith("content-length:"):
                parts = line_str.split(":", 1)
                content_length = int(parts[1].strip())

        if content_length is None or content_length <= 0:
            return None

        body_bytes = stream.read(content_length)
        if len(body_bytes) < content_length:
            return None

        try:
            return json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return None

    @staticmethod
    def write_message(stream: BinaryIO, payload: dict[str, object]) -> None:
        """Serializes and writes a JSON-RPC message with Content-Length header to stream."""
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        stream.write(header)
        stream.write(body)
        stream.flush()

    @staticmethod
    def make_response(req_id: object, result: object) -> dict[str, object]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result,
        }

    @staticmethod
    def make_error(req_id: object, code: int, message: str) -> dict[str, object]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message,
            },
        }

    @staticmethod
    def make_notification(method: str, params: object) -> dict[str, object]:
        return {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

