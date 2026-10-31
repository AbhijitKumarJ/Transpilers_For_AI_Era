from __future__ import annotations

import io
from typing import Any, cast

from psc.lsp.server import LanguageServer


def test_lsp_initialize_and_shutdown() -> None:
    in_buf = io.BytesIO()
    out_buf = io.BytesIO()
    server = LanguageServer(in_stream=in_buf, out_stream=out_buf)

    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"capabilities": {}},
    }
    resp = server.handle_request(init_req)
    assert resp is not None
    assert resp["id"] == 1
    res = cast(dict[str, Any], resp["result"])
    assert "capabilities" in res
    assert res["capabilities"]["hoverProvider"] is True
    assert res["capabilities"]["definitionProvider"] is True

    shutdown_req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "shutdown",
        "params": None,
    }
    resp2 = server.handle_request(shutdown_req)
    assert resp2 is not None
    assert resp2["result"] is None

    server.handle_notification({"jsonrpc": "2.0", "method": "exit", "params": None})
    assert server.is_running is False


def test_lsp_diagnostics_on_open() -> None:
    out_buf = io.BytesIO()
    server = LanguageServer(in_stream=io.BytesIO(), out_stream=out_buf)

    # Valid code: 0 errors
    valid_source = "namespace TestApp; public class Greeter { public string Name { get; set; } }"
    server.handle_notification({
        "jsonrpc": "2.0",
        "method": "textDocument/didOpen",
        "params": {
            "textDocument": {
                "uri": "file:///workspace/Greeter.ps",
                "text": valid_source,
            }
        },
    })

    assert len(server.notifications_log) == 1
    notif = server.notifications_log[0]
    assert notif["method"] == "textDocument/publishDiagnostics"
    params = cast(dict[str, Any], notif["params"])
    assert params["uri"] == "file:///workspace/Greeter.ps"
    assert len(params["diagnostics"]) == 0

    # Code with syntax error: triggers diagnostic
    broken_source = "namespace TestApp; public class Broken { void foo( }"
    server.handle_notification({
        "jsonrpc": "2.0",
        "method": "textDocument/didOpen",
        "params": {
            "textDocument": {
                "uri": "file:///workspace/Broken.ps",
                "text": broken_source,
            }
        },
    })
    assert len(server.notifications_log) == 2
    broken_notif = server.notifications_log[1]
    broken_params = cast(dict[str, Any], broken_notif["params"])
    assert len(broken_params["diagnostics"]) > 0
    d0 = broken_params["diagnostics"][0]
    assert "range" in d0
    assert d0["severity"] == 1


def test_lsp_hover_and_definition() -> None:
    server = LanguageServer(in_stream=io.BytesIO(), out_stream=io.BytesIO())
    source = """namespace MyApp;

public class OrderService
{
    public void Process() {}
}
"""
    uri = "file:///workspace/OrderService.ps"
    server.handle_notification({
        "jsonrpc": "2.0",
        "method": "textDocument/didOpen",
        "params": {
            "textDocument": {
                "uri": uri,
                "text": source,
            }
        },
    })

    # Hover over 'class' keyword on line 3 (line index 2, char index 8)
    hover_req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "textDocument/hover",
        "params": {
            "textDocument": {"uri": uri},
            "position": {"line": 2, "character": 8},
        },
    }
    resp = server.handle_request(hover_req)
    assert resp is not None
    assert resp["result"] is not None
    res = cast(dict[str, Any], resp["result"])
    assert "class" in res["contents"]["value"]

    # Hover over OrderService identifier on line 3 (character 15)
    hover_cls_req = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "textDocument/hover",
        "params": {
            "textDocument": {"uri": uri},
            "position": {"line": 2, "character": 15},
        },
    }
    resp_cls = server.handle_request(hover_cls_req)
    assert resp_cls is not None
    res_cls = cast(dict[str, Any], resp_cls["result"])
    assert "OrderService" in res_cls["contents"]["value"]

    # Go-to-definition for OrderService
    def_req = {
        "jsonrpc": "2.0",
        "id": 12,
        "method": "textDocument/definition",
        "params": {
            "textDocument": {"uri": uri},
            "position": {"line": 2, "character": 15},
        },
    }
    def_resp = server.handle_request(def_req)
    assert def_resp is not None
    def_res = cast(dict[str, Any], def_resp["result"])
    assert def_res["uri"] == uri
    assert def_res["range"]["start"]["line"] == 2


def test_lsp_completion() -> None:
    server = LanguageServer(in_stream=io.BytesIO(), out_stream=io.BytesIO())
    comp_req = {
        "jsonrpc": "2.0",
        "id": 20,
        "method": "textDocument/completion",
        "params": {
            "textDocument": {"uri": "file:///workspace/Test.ps"},
            "position": {"line": 0, "character": 0},
        },
    }
    resp = server.handle_request(comp_req)
    assert resp is not None
    res = cast(dict[str, Any], resp["result"])
    items = res["items"]
    labels = {it["label"] for it in items}
    assert "class" in labels
    assert "interface" in labels
    assert "record" in labels
    assert "String" in labels
    assert "IEnumerable" in labels


def test_lsp_cross_file_and_stdlib_navigation() -> None:
    from pathlib import Path

    from psc.lsp.server import path_to_uri

    server = LanguageServer(in_stream=io.BytesIO(), out_stream=io.BytesIO())
    inv_path = Path("Samples/02_linq_pipeline/Services/InventoryAnalytics.ps").resolve()
    inv_uri = path_to_uri(inv_path)
    inv_text = inv_path.read_text(encoding="utf-8")

    server.handle_notification({
        "jsonrpc": "2.0",
        "method": "textDocument/didOpen",
        "params": {
            "textDocument": {
                "uri": inv_uri,
                "text": inv_text,
            }
        },
    })

    # 1. Definition for `using PythonSharp.Core;` (line 3, char 10)
    ns_def_req = {
        "jsonrpc": "2.0",
        "id": 100,
        "method": "textDocument/definition",
        "params": {
            "textDocument": {"uri": inv_uri},
            "position": {"line": 2, "character": 10},
        },
    }
    resp = server.handle_request(ns_def_req)
    assert resp is not None and resp["result"] is not None
    assert "PythonSharp.Core.d.ps" in resp["result"]["uri"]

    # 2. Definition for standard core class `List` (line 8, char 23: `private readonly List<Product>`)
    list_def_req = {
        "jsonrpc": "2.0",
        "id": 101,
        "method": "textDocument/definition",
        "params": {
            "textDocument": {"uri": inv_uri},
            "position": {"line": 7, "character": 23},
        },
    }
    resp = server.handle_request(list_def_req)
    assert resp is not None and resp["result"] is not None
    assert "PythonSharp.Core.d.ps" in resp["result"]["uri"]

    # 3. Cross-file definition for `Product` (line 8, char 28) -> should point to Product.ps
    prod_def_req = {
        "jsonrpc": "2.0",
        "id": 102,
        "method": "textDocument/definition",
        "params": {
            "textDocument": {"uri": inv_uri},
            "position": {"line": 7, "character": 28},
        },
    }
    resp = server.handle_request(prod_def_req)
    assert resp is not None and resp["result"] is not None
    assert "Product.ps" in resp["result"]["uri"]

    # 4. Cross-file member definition for `Category` (line 18, char 32: `p.Category == category`)
    cat_def_req = {
        "jsonrpc": "2.0",
        "id": 103,
        "method": "textDocument/definition",
        "params": {
            "textDocument": {"uri": inv_uri},
            "position": {"line": 17, "character": 32},
        },
    }
    resp = server.handle_request(cat_def_req)
    assert resp is not None and resp["result"] is not None
    assert "Product.ps" in resp["result"]["uri"]

    # 5. Type Definition on `_products` (line 8, char 38) -> points to `List` in stdlib
    type_def_req = {
        "jsonrpc": "2.0",
        "id": 104,
        "method": "textDocument/typeDefinition",
        "params": {
            "textDocument": {"uri": inv_uri},
            "position": {"line": 7, "character": 38},
        },
    }
    resp = server.handle_request(type_def_req)
    assert resp is not None and resp["result"] is not None
    assert "PythonSharp.Core.d.ps" in resp["result"]["uri"]

    # 6. Hover on `Product`
    hover_req = {
        "jsonrpc": "2.0",
        "id": 105,
        "method": "textDocument/hover",
        "params": {
            "textDocument": {"uri": inv_uri},
            "position": {"line": 7, "character": 28},
        },
    }
    resp = server.handle_request(hover_req)
    assert resp is not None and resp["result"] is not None
    val = resp["result"]["contents"]["value"]
    assert "public record Product" in val
    assert "Product.ps" in val

