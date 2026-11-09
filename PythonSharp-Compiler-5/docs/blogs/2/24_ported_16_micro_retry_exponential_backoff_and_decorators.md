# Level 2 — Blog 24: Ported 16 — Micro-Retry (`16_micro_retry`): Exponential Backoff & Resilience Decorators

Distributed systems and cloud microservices are inherently unreliable: networks drop packets, databases hit connection limits, and third-party APIs return transient rate limits (`HTTP 429` / `503`).

Building resilient software requires retry loops with **exponential backoff**, **exception filtering**, and clean **decorator syntax**.

In this post, we examine **`16_micro_retry`**, ported from canonical concepts in the popular `retry` library:
1. **The Resilience Architecture**: Attempt quotas, initial delays, backoff multipliers, and max delay ceilings.
2. **Project Layout**: The `.psproj` structure.
3. **The C# Implementation (`Retry.ps`)**: Native exception re-throw semantics (`throw;` $\to$ `raise`), exception filtering, and higher-order decorator factories.
4. **The Transpiled Output (`micro_retry.py`)**: Direct emission of `@Retry.decorator` syntax.
5. **The Verification Test Harness (`run_retry.py`)**: Validating transient success, exhaustion re-throwing, unhandled exception bypassing, and decorator wrapping.

---

## 1. Resilience Patterns: Exponential Backoff & Jitter

When a network call fails, retrying immediately is dangerous: if 10,000 clients all retry simultaneously, they create a **thundering herd** that overloads the recovering service.

**Exponential backoff** scales delay exponentially after each failed attempt:
$$\text{delay}_{k} = \min(\text{delay}_0 \times \text{backoff}^k, \text{max\_delay})$$

Key requirements:
1. **Exception Filtering**: Only retry expected transient errors (`ConnectionError`, `TimeoutError`). Fatal logic errors (`ValueError`, `TypeError`) must fail immediately without wasting retry attempts.
2. **Exhaustion Semantics**: If all retry attempts fail, the utility must re-raise the *original* underlying exception with its full stack trace intact.
3. **Decorator Syntax**: Enable zero-boilerplate wrapping via `@Retry.decorator(tries=3, delay=0.1)`.

---

## 2. Project Layout

The project lives under [`Samples/Ported/16_micro_retry/`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/16_micro_retry/):

```
Samples/Ported/16_micro_retry/
├── MicroRetry.psproj      # Project configuration manifest
├── Retry.ps               # C# retry engine and decorator factory
├── README.md              # Documentation and build instructions
├── run_retry.py           # Automated verification test suite
└── dist/
    └── micro_retry.py     # Transpiled pure Python 3.11 module
```

---

## 3. The C# Source Implementation: `Retry.ps`

In [`Retry.ps`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/16_micro_retry/Retry.ps), notice the use of bare `throw;`:

```csharp
namespace MicroRetry;

extern using time;
using PythonSharp.Core;

public class Retry
{
    [InlineTemplate("time.sleep({0})")]
    public static extern void Sleep(double seconds);

    [InlineTemplate("(isinstance({0}, tuple({1})) if {1} is not None else isinstance({0}, Exception))")]
    public static extern bool MatchesException(object exc, List<object>? exceptions);

    [InlineTemplate("{0}(*{1})")]
    public static extern object InvokeWithList(object fn, List<object> args);

    [InlineTemplate("(lambda fn: (lambda *args: Retry.call(fn, list(args), {0}, {1}, {2}, {3}, {4})))")]
    private static extern object MakeDecorator(int tries, double delay, double maxDelay, double backoff, List<object>? exceptions);

    public static object Decorator(
        int tries = 3,
        double delay = 0.01,
        double maxDelay = 10.0,
        double backoff = 2.0,
        List<object>? exceptions = null
    )
    {
        return MakeDecorator(tries, delay, maxDelay, backoff, exceptions);
    }

    public static object Call(
        object fn,
        List<object>? args = null,
        int tries = 3,
        double delay = 0.01,
        double maxDelay = 10.0,
        double backoff = 2.0,
        List<object>? exceptions = null
    )
    {
        List<object> safeArgs = args ?? new List<object>();
        int attemptsRemaining = tries;
        double currentDelay = delay;

        while (attemptsRemaining > 0)
        {
            try
            {
                return InvokeWithList(fn, safeArgs);
            }
            catch (Exception ex)
            {
                attemptsRemaining = attemptsRemaining - 1;

                // If exhausted OR exception is not in allowed filter, rethrow!
                if (attemptsRemaining <= 0 || !MatchesException(ex, exceptions))
                {
                    throw;
                }

                if (currentDelay > 0.0)
                {
                    Sleep(currentDelay);
                }

                currentDelay = currentDelay * backoff;
                if (currentDelay > maxDelay)
                {
                    currentDelay = maxDelay;
                }
            }
        }

        throw new SystemException("Retry failed without capturing exception");
    }
}
```

### The Power of `throw;`
In C#, a bare `throw;` inside a `catch` block re-raises the caught exception without resetting its stack trace.
PythonSharp lowers `throw;` directly to Python's bare `raise` statement:

```python
# C#:
throw;

# Emitted Python:
raise
```
This ensures that the original traceback and line numbers are preserved perfectly!

---

## 4. The Transpiled Output: `micro_retry.py`

Compiling with:
```bash
psc build Samples/Ported/16_micro_retry -o Samples/Ported/16_micro_retry/dist
```
produces [`Samples/Ported/16_micro_retry/dist/micro_retry.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/16_micro_retry/dist/micro_retry.py).

### How to Use the Generated Decorator in Python:
```python
from micro_retry import Retry

# Using the transpiled decorator
@Retry.decorator(tries=4, delay=0.01, backoff=2.0, exceptions=[ConnectionError])
def fetch_user_data(user_id):
    # This flaky function will be retried up to 4 times with backoff
    return remote_api.get(f"/users/{user_id}")
```

---

## 5. Verification Test Suite

[`run_retry.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/16_micro_retry/run_retry.py) tests transient failures, exhaustion re-throwing, exception filtering, and decorator wrapping:

```python
# 1. Immediate Success
calls = 0
def fast_success():
    global calls; calls += 1; return "OK"
assert Retry.call(fast_success, tries=3) == "OK"
assert calls == 1

# 2. Transient Failure (Succeeds on attempt 3)
transient_calls = 0
def flaky():
    global transient_calls; transient_calls += 1
    if transient_calls < 3:
        raise ConnectionResetError("Network drop")
    return "Recovered"
assert Retry.call(flaky, tries=5, delay=0.005) == "Recovered"
assert transient_calls == 3

# 3. Exhaustion Rethrow
fail_calls = 0
def always_fail():
    global fail_calls; fail_calls += 1
    raise ValueError(f"Permanent validation error (attempt {fail_calls})")

try:
    Retry.call(always_fail, tries=3, delay=0.005)
    assert False, "Should have re-raised ValueError"
except ValueError as exc:
    assert fail_calls == 3
    assert "attempt 3" in str(exc)

# 4. Exception Filtering (Bypasses retry if exception type does not match)
unhandled_calls = 0
def fatal_error():
    global unhandled_calls; unhandled_calls += 1
    raise TypeError("Fatal type mismatch - do not retry")

try:
    Retry.call(fatal_error, tries=5, exceptions=[ConnectionResetError])
    assert False, "Should have bypassed retry immediately"
except TypeError:
    assert unhandled_calls == 1 # Only called once!
```

Running the runner:
```bash
python3 Samples/Ported/16_micro_retry/run_retry.py
```
Outputs:
```
=== Step 1: Building MicroRetry via `psc build` ===
Build is up to date: outputs in '.../dist' are fresh.

=== Step 2: Testing Ported Retry Functionality ===
[PASS] Immediate success without retry verified
[PASS] Transient failure retries and eventual success verified
[PASS] Retry exhaustion re-raised original exception after 3 attempts: Permanent validation error (attempt 3)
[PASS] Unhandled exception bypassed retry and raised immediately: Fatal type mismatch - do not retry
[PASS] Parametric decorator syntax (@Retry.decorator) verified

All micro-retry verification checks succeeded with 0 errors!
```

---

## Key Takeaways

1. **Native Rethrow Semantics**: C# `throw;` lowers directly to Python `raise`, keeping exception stack traces clean and uncorrupted.
2. **Parameterized Decorator Synthesis**: Easily create Python function decorators with full argument configurability.
3. **Resilience Engineering**: Clean implementation of exponential backoff and exception filtering without third-party libraries.

---

## Next Steps: Tier 7 — Concurrency & Async!

We now arrive at the final, most advanced porting target: **Tier 7: Concurrency & Async**.

In **[Blog 25: Ported 17 — Micro-EventLoop (`17_micro_eventloop`): Cooperative Multitasking, Tasks & Sleep Queues](./25_ported_17_micro_eventloop_tasks_queues_and_coros.md)**, we examine how to build a complete cooperative async event loop from scratch in PythonSharp!

