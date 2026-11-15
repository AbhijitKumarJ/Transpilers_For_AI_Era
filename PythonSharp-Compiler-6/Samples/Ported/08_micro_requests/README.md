# Ported 08: Micro Requests

A ported micro subset of the `requests` HTTP client library implemented cleanly in PythonSharp (`.ps`). Demonstrates network I/O, C# 9+ records with computed properties (`IsSuccessStatusCode`), dictionary headers, JSON parsing (`response.Json()`), error handling, and zero runtime overhead interop with Python's standard `urllib.request`.

## Project Structure

- `MicroRequests.psproj`: PythonSharp project file specifying assembly `MicroRequests` and target `py3.11`.
- `HttpClient.ps`: Core implementation of `HttpResponse` record and `HttpClient` class.
- `run_requests.py`: Verification harness running an in-process mock HTTP server to test GET, POST, JSON decoding, status codes, and network error handling.

## Features

- **Typed HTTP Response**: `HttpResponse(int StatusCode, string Text, Dict<string, string> Headers, string Url)`
- **Success Checking**: `response.IsSuccessStatusCode` property.
- **Convenient JSON Parsing**: `response.Json()` parses response body using `json.loads`.
- **GET & POST**: `HttpClient.Get(url, headers, timeout)` and `HttpClient.Post(url, data, headers, timeout)`.
- **Resilient Error Handling**: Safely catches both HTTP status errors (4xx, 5xx) and network/socket transport errors (status 0).

## How to Build and Run

```bash
# Build the PythonSharp project
psc build Samples/Ported/08_micro_requests

# Run the test suite
python3 Samples/Ported/08_micro_requests/run_requests.py
```

