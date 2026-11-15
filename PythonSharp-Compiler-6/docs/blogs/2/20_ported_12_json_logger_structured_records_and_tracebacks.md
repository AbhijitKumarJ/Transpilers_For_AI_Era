# Level 2 — Blog 20: Ported 12 — JSON-Logger (`12_json_logger`): Structured Log Formatting & Tracebacks

We conclude **Tier 5: Data Structures & Parsing** with **`12_json_logger`**, inspired by the ubiquitous `python-json-logger` library.

In production microservices and cloud environments (AWS CloudWatch, Datadog, Elasticsearch/Kibana), plain text logs are an anti-pattern. Systems require **Structured JSON Logging**, where each log entry is a single JSON object with standardized fields (`timestamp`, `severity`, `logger`, `message`, `traceback`) along with arbitrary contextual metadata.

In this post, we explore:
1. **The Target**: Implementing a custom `logging.Formatter` for Python's standard library `logging` module in PythonSharp.
2. **Project Layout**: The `.psproj` setup.
3. **The C# Implementation (`JsonFormatter.ps`)**: Record attribute reflection, timestamp formatting, field remapping, and exception traceback serialization.
4. **C# vs. Python Keyword Disambiguation**: Why naming a variable `logRecord` instead of `record` matters.
5. **The Verification Test Harness (`run_logger.py`)**: Validating JSON formatting, custom key renaming (`@timestamp`), dynamic `extra={...}` dictionary merging, and traceback serialization.

---

## 1. The Target: Structured JSON Logging

Standard Python logging outputs formatted strings:
```
2026-10-31 12:00:00,123 - app.auth - INFO - User ada logged in successfully
```

Log ingestion engines cannot easily query string logs without complex regular expressions.
Structured logging outputs newline-delimited JSON:
```json
{
  "@timestamp": "2026-10-31T12:00:00.123Z",
  "severity": "INFO",
  "logger": "app.auth",
  "message": "User ada logged in successfully",
  "user_id": 90210,
  "ip_address": "192.168.1.1"
}
```

To achieve this in PythonSharp:
1. Intercept Python's `logging.LogRecord` objects.
2. Extract standard fields (`created`, `levelname`, `name`, `msg`, `exc_info`).
3. Merge arbitrary extra keys passed via `logger.info("msg", extra={"user_id": 90210})`.
4. Support configurable key renaming (e.g. `levelname` $\to$ `severity`, `asctime` $\to$ `@timestamp`).
5. Serialize exception tracebacks cleanly into string fields.

---

## 2. Project Layout

The project lives under [`Samples/Ported/12_json_logger/`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/12_json_logger/):

```
Samples/Ported/12_json_logger/
├── JsonLogger.psproj      # Project manifest
├── JsonFormatter.ps       # C# JSON formatter implementation
├── README.md              # Documentation and build instructions
├── run_logger.py          # Automated verification test suite
└── dist/
    └── micro_json_logger.py # Transpiled pure Python 3.11 module
```

---

## 3. The C# Source Implementation: `JsonFormatter.ps`

In [`JsonFormatter.ps`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/12_json_logger/JsonFormatter.ps), notice the keyword discipline:

```csharp
namespace MicroJsonLogger;

extern using json;
extern using time;
extern using logging;
using PythonSharp.Core;

public class JsonFormatter
{
    private Dict<string, string> _renameFields;
    private string _timeFormat;

    public JsonFormatter(Dict<string, string>? renameFields = null, string timeFormat = "%Y-%m-%dT%H:%M:%S")
    {
        this._renameFields = renameFields ?? new Dict<string, string>();
        this._timeFormat = timeFormat;
    }

    [InlineTemplate("getattr({0}, {1}, {2})")]
    public static extern object? GetRecordAttr(object logRecord, string attr, object? defaultVal = null);

    [InlineTemplate("json.dumps({0}, default=str)")]
    public static extern string JsonDumps(Dict<string, object> payload);

    [InlineTemplate("time.strftime({0}, time.localtime({1}))")]
    public static extern string FormatTime(string fmt, double timestamp);

    [InlineTemplate("logging.Formatter.formatException(self, {0}) if {0} else ''")]
    public extern string FormatException(object? excInfo);
```

### The Keyword Trap: `record` vs. `logRecord`
In C# 9+, `record` is a contextual keyword used to declare record types (`public record User(...)`).
If you name a method parameter `record`:
```csharp
public string Format(object record) // SYNTAX ERROR in C#!
```
The C# parser expects a record type declaration! We name the parameter `logRecord` to ensure clean parsing across both languages.

### Formatting and Merging Extra Payloads
```csharp
    public string Format(object logRecord)
    {
        Dict<string, object> logDict = new Dict<string, object>();

        // 1. Format Timestamp with milliseconds
        object? createdObj = GetRecordAttr(logRecord, "created", 0.0);
        double created = ConvertToDouble(createdObj!);
        string baseTime = FormatTime(this._timeFormat, created);
        double msecPart = (created - ConvertToInt(created)) * 1000.0;
        int msec = ConvertToInt(msecPart);
        string msecStr = msec < 10 ? $"00{msec}" : (msec < 100 ? $"0{msec}" : $"{msec}");
        string timestamp = $"{baseTime}.{msecStr}Z";

        string timeKey = this.ResolveKey("asctime");
        logDict[timeKey] = timestamp;

        // 2. Format Level & Name
        logDict[this.ResolveKey("levelname")] = AsString(GetRecordAttr(logRecord, "levelname", "INFO")!);
        logDict[this.ResolveKey("name")] = AsString(GetRecordAttr(logRecord, "name", "root")!);
        logDict[this.ResolveKey("message")] = GetMessage(logRecord);

        // 3. Merge Extra attributes from logRecord.__dict__
        Dict<string, object> recordDict = GetRecordDict(logRecord);
        List<string> standardKeys = GetStandardFields();
        List<string> allKeys = GetDictKeys(recordDict);

        int k = 0;
        while (k < allKeys.Count)
        {
            string key = allKeys[k];
            if (!standardKeys.Contains(key) && !key.StartsWith("_"))
            {
                logDict[key] = recordDict[key];
            }
            k = k + 1;
        }

        // 4. Format Traceback if present
        object? excInfo = GetRecordAttr(logRecord, "exc_info", null);
        if (excInfo != null)
        {
            string tb = this.FormatException(excInfo);
            if (tb.Length > 0)
            {
                logDict["exc_info"] = tb;
            }
        }

        return JsonDumps(logDict);
    }
```

---

## 4. The Transpiled Output: `micro_json_logger.py`

Compiling with:
```bash
psc build Samples/Ported/12_json_logger -o Samples/Ported/12_json_logger/dist
```
produces [`Samples/Ported/12_json_logger/dist/micro_json_logger.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/12_json_logger/dist/micro_json_logger.py).

### Integration with Python `logging`
Because `JsonFormatter` implements `format(record) -> str`, it can be passed directly to Python's standard `logging.StreamHandler`:

```python
import logging
from micro_json_logger import JsonFormatter

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter(rename_fields={"levelname": "severity", "asctime": "@timestamp"}))

logger = logging.getLogger("checkout")
logger.addHandler(handler)
logger.info("Order processed successfully", extra={"order_id": 49201, "amount": 99.50})
```

Output:
```json
{"@timestamp": "2026-10-31T12:00:00.142Z", "severity": "INFO", "name": "checkout", "message": "Order processed successfully", "order_id": 49201, "amount": 99.5}
```

---

## 5. Verification Test Suite

[`run_logger.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/12_json_logger/run_logger.py) verifies formatting, extra payload merging, and exception tracebacks:

```python
# 1. Standard log format
logger.info("System initialized")
record_json = json.loads(stream.getvalue().strip())
assert record_json["message"] == "System initialized"
assert record_json["levelname"] == "INFO"

# 2. Key remapping & extra metadata
custom_formatter = JsonFormatter(rename_fields={"levelname": "severity", "asctime": "@timestamp", "message": "msg"})
logger.info("User checkout", extra={"user_id": "usr_42", "cart_total": 128.50, "is_vip": True})
data = json.loads(stream.getvalue().strip())
assert data["severity"] == "INFO"
assert "@timestamp" in data
assert data["user_id"] == "usr_42"
assert data["cart_total"] == 128.50
assert data["is_vip"] is True

# 3. Exception traceback serialization
try:
    1 / 0
except ZeroDivisionError:
    logger.exception("Math calculation failed")

err_data = json.loads(stream.getvalue().strip().split("\n")[-1])
assert "ZeroDivisionError: division by zero" in err_data["exc_info"]
```

Running the runner:
```bash
python3 Samples/Ported/12_json_logger/run_logger.py
```
Outputs:
```
=== Step 1: Building JsonLogger via `psc build` ===
Build is up to date: outputs in '.../dist' are fresh.

=== Step 2: Testing Ported JsonFormatter Functionality ===
[PASS] Standard record formatting and JSON parsing verified
[PASS] Custom field renaming (@timestamp, severity, msg) verified
[PASS] Extra payload dictionary merging (user_id, cart_total, is_vip) verified
[PASS] Exception traceback serialization verified

All json-logger verification checks succeeded with 0 errors!
```

---

## Key Takeaways

1. **Seamless Standard Library Extension**: Extend Python's `logging.Formatter` seamlessly from typed C#.
2. **Keyword Discipline**: Avoiding collisions with contextual keywords like `record` preserves syntax clarity.
3. **Structured Cloud Observability**: Native JSON log serialization with custom key mappings and traceback extraction.

---

## Next Steps: Tier 6 Begins!

We have completed Tiers 1 through 5! Now we enter **Tier 6: Core Language Features & Metaprogramming**.

In **[Blog 21: Ported 13 — Micro-Fn (`13_micro_fn`): Functional Programming, Currying & Composition](./21_ported_13_micro_fn_currying_and_composition.md)**, we examine higher-order functions, partial application, currying, and functional pipelines!

