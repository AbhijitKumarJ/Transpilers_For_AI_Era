# Level 2 — Blog 16: Ported 08 — Micro-Requests (`08_micro_requests`): HTTP Networking, Sockets & JSON

We conclude the foundational tiers with **Tier 4: Networking**: **`08_micro_requests`**, inspired by the world-famous `requests` HTTP client library.

Writing networking code in a transpiled language tests several advanced compiler capabilities:
1. **Aliased External Module Imports**: `extern using urllib.request as ureq;` mapping directly to `import urllib.request as ureq`.
2. **Immutable Response Records**: `HttpResponse(StatusCode, Text, Headers, Url)` as a frozen dataclass with computed helper properties (`IsSuccessStatusCode`).
3. **HTTP Protocol Semantics**: Handling status codes, headers, chunked streaming, request timeouts, and error response bodies.
4. **JSON Deserialization**: `.Json()` helper inlining directly to `json.loads(self.text)`.

In this post, we explore:
1. **The Target**: Providing a minimalist, dependency-free HTTP client API (`HttpClient.Get`, `HttpClient.Post`).
2. **Project Layout**: The `.psproj` configuration.
3. **The C# Implementation (`HttpClient.ps`)**: Aliased imports, `HttpResponse` record, and exception-safe request dispatching.
4. **The Transpiled Output (`micro_requests.py`)**: Zero-overhead lowering to Python's standard `urllib` and `json` libraries.
5. **The Verification Test Harness (`run_requests.py`)**: Testing HTTP GET, POST payloads, headers, status codes, and JSON parsing against a mock HTTP server.

---

## 1. The Target: A Zero-Dependency HTTP Client

Python's `requests` library is famous for its elegant, human-friendly API:

```python
resp = requests.get("https://httpbin.org/get")
if resp.status_code == 200:
    data = resp.json()
```

However, `requests` pulls in multiple heavy dependencies (`urllib3`, `charset_normalizer`, `idna`, `certifi`).

In `08_micro_requests`, our goal is to achieve the same clean API in PythonSharp using Python's standard library (`urllib.request` and `json`), with full compile-time type safety.

---

## 2. Project Layout

The project lives under [`Samples/Ported/08_micro_requests/`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/08_micro_requests/):

```
Samples/Ported/08_micro_requests/
├── HttpClient.ps          # C# HTTP client implementation
├── README.md              # Documentation and build instructions
├── run_requests.py        # Automated test harness with mock HTTP server
└── dist/
    └── micro_requests.py  # Transpiled pure Python 3.11 module
```

---

## 3. The C# Source Implementation: `HttpClient.ps`

In [`HttpClient.ps`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/08_micro_requests/HttpClient.ps), notice how aliased imports and inline templates work together:

```csharp
namespace MicroRequests;

extern using urllib.request as ureq;
extern using urllib.error as uerr;
extern using json;
using PythonSharp.Core;

public record HttpResponse(int StatusCode, string Text, Dict<string, string> Headers, string Url)
{
    public bool IsSuccessStatusCode => StatusCode >= 200 && StatusCode < 300;

    public object Json()
    {
        return ParseJson(Text);
    }

    [InlineTemplate("json.loads({0})")]
    private static extern object ParseJson(string text);
}

public class HttpClient
{
    [InlineTemplate("ureq.Request({0}, data={1}.encode('utf-8') if {1} is not None else None, headers={2} if {2} is not None else {}, method={3})")]
    private static extern object CreateRequest(string url, string? data, Dict<string, string>? headers, string method);

    [InlineTemplate("ureq.urlopen({0}, timeout={1})")]
    private static extern object OpenUrl(object request, int timeout);

    [InlineTemplate("{0}.status")]
    private static extern int GetStatus(object response);

    [InlineTemplate("{0}.read().decode('utf-8', errors='replace')")]
    private static extern string ReadBody(object response);

    [InlineTemplate("dict({0}.headers)")]
    private static extern Dict<string, string> GetHeaders(object response);

    [InlineTemplate("{0}.geturl()")]
    private static extern string GetUrl(object response);

    public static HttpResponse Send(string url, string method = "GET", string? data = null, Dict<string, string>? headers = null, int timeout = 10)
    {
        object req = CreateRequest(url, data, headers, method);
        try
        {
            object resp = OpenUrl(req, timeout);
            int status = GetStatus(resp);
            string body = ReadBody(resp);
            Dict<string, string> respHeaders = GetHeaders(resp);
            string respUrl = GetUrl(resp);
            return new HttpResponse(status, body, respHeaders, respUrl);
        }
        catch (Exception ex)
        {
            int errStatus = ExtractErrorStatus(ex);
            string errBody = ExtractErrorBody(ex);
            Dict<string, string> errHeaders = ExtractErrorHeaders(ex);
            return new HttpResponse(errStatus, errBody, errHeaders, url);
        }
    }

    public static HttpResponse Get(string url, Dict<string, string>? headers = null, int timeout = 10)
    {
        return Send(url, "GET", null, headers, timeout);
    }

    public static HttpResponse Post(string url, string data = "", Dict<string, string>? headers = null, int timeout = 10)
    {
        return Send(url, "POST", data, headers, timeout);
    }
}
```

---

## 4. The Transpiled Output: `micro_requests.py`

Compiling with:
```bash
psc build Samples/Ported/08_micro_requests -o Samples/Ported/08_micro_requests/dist
```
produces [`Samples/Ported/08_micro_requests/dist/micro_requests.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/08_micro_requests/dist/micro_requests.py):

```python
# Auto-generated by PythonSharp (psc) — Bytecode line-pinned to HttpClient.ps
from __future__ import annotations
from dataclasses import dataclass
import urllib.request as ureq
import urllib.error as uerr
import json

@dataclass(slots=True, frozen=True)
class HttpResponse:
    __ps_types__ = ('MicroRequests.HttpResponse',)
    status_code: int
    text: str
    headers: dict[str, str]
    url: str

    @property
    def is_success_status_code(self) -> bool:
        return self.status_code >= 200 and self.status_code < 300

    def json(self) -> object:
        return json.loads(self.text)

class HttpClient:
    __ps_types__ = ('MicroRequests.HttpClient',)
    __slots__ = ()

    @staticmethod
    def send(url: str, method: str = 'GET', data: str | None = None, headers: dict[str, str] | None = None, timeout: int = 10) -> HttpResponse:
        req: object = ureq.Request(url, data=data.encode('utf-8') if data is not None else None, headers=headers if headers is not None else {}, method=method)
        try:
            resp: object = ureq.urlopen(req, timeout=timeout)
            status: int = resp.status
            body: str = resp.read().decode('utf-8', errors='replace')
            resp_headers: dict[str, str] = dict(resp.headers)
            resp_url: str = resp.geturl()
            return HttpResponse(status, body, resp_headers, resp_url)
        except Exception as ex:
            err_status: int = getattr(ex, 'code', 0)
            err_body: str = ex.read().decode('utf-8', errors='replace') if hasattr(ex, 'read') else str(ex)
            err_headers: dict[str, str] = dict(ex.headers) if hasattr(ex, 'headers') else {}
            return HttpResponse(err_status, err_body, err_headers, url)

    @staticmethod
    def get(url: str, headers: dict[str, str] | None = None, timeout: int = 10) -> HttpResponse:
        return HttpClient.send(url, 'GET', None, headers, timeout)

    @staticmethod
    def post(url: str, data: str = '', headers: dict[str, str] | None = None, timeout: int = 10) -> HttpResponse:
        return HttpClient.send(url, 'POST', data, headers, timeout)
```

### Architectural Breakdown:
1. **Aliased Module Imports**: `extern using urllib.request as ureq;` emits `import urllib.request as ureq` without extra runtime overhead.
2. **Inline Template Expansion**: Notice line 24 of `HttpClient.send`:
   ```python
   req = ureq.Request(url, data=data.encode('utf-8') if data is not None else None, headers=headers if headers is not None else {}, method=method)
   ```
   The compiler expanded the template directly into the assignment statement!
3. **Response Body Decoding**: `resp.read().decode('utf-8', errors='replace')` safely decodes UTF-8 strings.
4. **Exception Body Extraction**: If a `404` or `500` error occurs, `urllib.error.HTTPError` acts as both an exception and a readable stream; the transpiled code extracts the error body seamlessly.

---

## 5. Verification Test Suite

[`run_requests.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/08_micro_requests/run_requests.py) spins up an in-process local HTTP server on a random port and verifies real network requests:

```python
# 1. HTTP GET Request
resp = HttpClient.get(f"{server_url}/api/status")
assert resp.status_code == 200
assert resp.is_success_status_code
assert resp.json() == {"status": "ok", "version": "1.0.0"}

# 2. HTTP POST with JSON Payload
payload = json.dumps({"username": "ada_lovelace", "role": "admin"})
post_resp = HttpClient.post(f"{server_url}/api/users", payload)
assert post_resp.status_code == 201
assert post_resp.json()["user"]["username"] == "ada_lovelace"

# 3. HTTP 404 Error Handling
err_resp = HttpClient.get(f"{server_url}/not-found")
assert err_resp.status_code == 404
assert not err_resp.is_success_status_code
```

Running the runner:
```bash
python3 Samples/Ported/08_micro_requests/run_requests.py
```
Outputs:
```
=== Step 1: Building MicroRequests via `psc build` ===
Build is up to date: outputs in '.../dist' are fresh.

=== Step 2: Testing Ported HttpClient with Local HTTP Server ===
[PASS] GET /api/status -> 200 OK, JSON parsed successfully
[PASS] POST /api/users -> 201 Created, payload echoed in JSON
[PASS] GET /not-found -> 404 Handled with error body

All micro-requests verification checks succeeded with 0 errors!
```

---

## Key Takeaways

1. **Aliased Module Imports**: Seamlessly map Python's standard library packages into C# with custom aliases (`ureq`, `uerr`).
2. **Expressive Inline Templates**: Encode complex parameter handling (`data.encode('utf-8') if data is not None else None`) directly into template strings.
3. **Zero Dependencies**: Full HTTP client functionality with JSON parsing without pip-installing `requests` or `urllib3`.

---

## Next Steps: Tier 5 Begins!

We have completed Tiers 1 through 4! Now we advance to **Tier 5: Data Structures & Parsing**.

In **[Blog 17: Ported 09 — Micro-Toml (`09_micro_toml`): Scanner State Machines & TOML Serialization](./17_ported_09_micro_toml_scanner_and_state_machines.md)**, we examine recursive dictionary trees, nested section tables, and arrays of tables!

