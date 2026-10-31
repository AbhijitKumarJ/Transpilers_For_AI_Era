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
    assert "00_core" in resp["result"]["uri"] or "PythonSharp.Core.d.ps" in resp["result"]["uri"]

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
    assert "00_core" in resp["result"]["uri"] or "PythonSharp.Core.d.ps" in resp["result"]["uri"]

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
    assert "00_core" in resp["result"]["uri"] or "PythonSharp.Core.d.ps" in resp["result"]["uri"]

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


def test_lsp_local_and_shadowed_type_navigation_and_hover() -> None:
    from pathlib import Path
    from psc.lsp.server import LanguageServer, path_to_uri

    server = LanguageServer(in_stream=io.BytesIO(), out_stream=io.BytesIO())
    ev_path = Path("Samples/Ported/17_micro_eventloop/EventLoop.ps").resolve()
    ev_uri = path_to_uri(ev_path)
    ev_text = ev_path.read_text(encoding="utf-8")

    server.handle_notification({
        "jsonrpc": "2.0",
        "method": "textDocument/didOpen",
        "params": {
            "textDocument": {
                "uri": ev_uri,
                "text": ev_text,
            }
        },
    })

    # 1. Hover on `Task` type on line 152: col 18
    hov_task = server.handle_request({
        "jsonrpc": "2.0",
        "id": 201,
        "method": "textDocument/hover",
        "params": {"textDocument": {"uri": ev_uri}, "position": {"line": 151, "character": 18}},
    })
    assert hov_task is not None and hov_task["result"] is not None
    val = hov_task["result"]["contents"]["value"]
    assert "public class Task" in val
    assert "EventLoop.ps" in val
    assert "primitive_class" not in val
    assert "PythonSharp Core Standard Library" not in val
    assert "Surface Tier" not in val

    # 2. Go to Definition on `Task` on line 152: col 18 -> jumps to local Task class (line 24)
    def_task = server.handle_request({
        "jsonrpc": "2.0",
        "id": 202,
        "method": "textDocument/definition",
        "params": {"textDocument": {"uri": ev_uri}, "position": {"line": 151, "character": 18}},
    })
    assert def_task is not None and def_task["result"] is not None
    assert def_task["result"]["uri"] == ev_uri
    assert def_task["result"]["range"]["start"]["line"] == 23

    # 3. Hover on local variable `current` on line 152: col 23
    hov_cur = server.handle_request({
        "jsonrpc": "2.0",
        "id": 203,
        "method": "textDocument/hover",
        "params": {"textDocument": {"uri": ev_uri}, "position": {"line": 151, "character": 23}},
    })
    assert hov_cur is not None and hov_cur["result"] is not None
    assert "(local variable) Task current" in hov_cur["result"]["contents"]["value"]

    # 4. Go to Definition on local variable `current`
    def_cur = server.handle_request({
        "jsonrpc": "2.0",
        "id": 204,
        "method": "textDocument/definition",
        "params": {"textDocument": {"uri": ev_uri}, "position": {"line": 151, "character": 23}},
    })
    assert def_cur is not None and def_cur["result"] is not None
    assert def_cur["result"]["uri"] == ev_uri
    assert def_cur["result"]["range"]["start"]["line"] == 151

    # 5. Type Definition on local variable `current` -> jumps to Task class (line 24)
    typedef_cur = server.handle_request({
        "jsonrpc": "2.0",
        "id": 205,
        "method": "textDocument/typeDefinition",
        "params": {"textDocument": {"uri": ev_uri}, "position": {"line": 151, "character": 23}},
    })
    assert typedef_cur is not None and typedef_cur["result"] is not None
    assert typedef_cur["result"]["uri"] == ev_uri
    assert typedef_cur["result"]["range"]["start"]["line"] == 23

    # 6. Definition for property `dt.Task` on line 139: col 46 -> jumps to property Task in DelayedTask (line 89)
    def_dttask = server.handle_request({
        "jsonrpc": "2.0",
        "id": 206,
        "method": "textDocument/definition",
        "params": {"textDocument": {"uri": ev_uri}, "position": {"line": 138, "character": 46}},
    })
    assert def_dttask is not None and def_dttask["result"] is not None
    assert def_dttask["result"]["uri"] == ev_uri
    assert def_dttask["result"]["range"]["start"]["line"] == 88

    # 7. Hover for property access `current.IsDone` on line 155: col 30
    hov_isdone = server.handle_request({
        "jsonrpc": "2.0",
        "id": 207,
        "method": "textDocument/hover",
        "params": {"textDocument": {"uri": ev_uri}, "position": {"line": 154, "character": 30}},
    })
    assert hov_isdone is not None and hov_isdone["result"] is not None
    assert "(property) bool Task.IsDone" in hov_isdone["result"]["contents"]["value"]

    # 8. Definition for property access `current.IsDone` -> jumps to IsDone in Task (line 43)
    def_isdone = server.handle_request({
        "jsonrpc": "2.0",
        "id": 208,
        "method": "textDocument/definition",
        "params": {"textDocument": {"uri": ev_uri}, "position": {"line": 154, "character": 30}},
    })
    assert def_isdone is not None and def_isdone["result"] is not None
    assert def_isdone["result"]["range"]["start"]["line"] == 42

    # 9. Hover on field `this._readyQueue` on line 150: col 28
    hov_rq = server.handle_request({
        "jsonrpc": "2.0",
        "id": 209,
        "method": "textDocument/hover",
        "params": {"textDocument": {"uri": ev_uri}, "position": {"line": 149, "character": 28}},
    })
    assert hov_rq is not None and hov_rq["result"] is not None
    assert "(field) List<Task> EventLoop._readyQueue" in hov_rq["result"]["contents"]["value"]


