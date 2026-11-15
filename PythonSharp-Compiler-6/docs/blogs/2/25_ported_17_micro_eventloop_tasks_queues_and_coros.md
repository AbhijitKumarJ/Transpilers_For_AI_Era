# Level 2 — Blog 25: Ported 17 — Micro-EventLoop (`17_micro_eventloop`): Cooperative Multitasking, Tasks & Sleep Queues

We arrive at the pinnacle of our porting roadmap: **Tier 7: Concurrency & Async**.

Async execution models are among the most intricate systems in computer science. Python's native `asyncio` is often treated as a mysterious black box. But fundamentally, an asynchronous event loop is simply a **cooperative multitasking scheduler** driven by generators and time-deadline queues.

In this post, we examine **`17_micro_eventloop`**, ported from core concepts in Python's `asyncio` and micro cooperative event loops:
1. **The Event Loop Mechanics**: Coroutines as state machines, generator stepping (`.send(None)`), and `StopIteration` return values.
2. **Project Layout**: The `.psproj` architecture.
3. **The C# Implementation (`EventLoop.ps`)**: `Task`, `StepResult`, `DelayedTask`, FIFO `ReadyQueue`, and time-deadline `SleepQueue`.
4. **The Transpiled Output (`micro_async.py`)**: Seamless interop with Python generator coroutines and exception propagation.
5. **The Verification Test Harness (`run_eventloop.py`)**: Interleaved concurrent execution, scheduled sleeps, and exception bubble-up.

---

## 1. How Cooperative Multitasking Works

In preemptive multitasking (threads/processes), the operating system forcibly interrupts execution to switch tasks.

In **cooperative multitasking** (coroutines/async):
1. A task runs until it explicitly **yields** control back to the event loop.
2. If a task yields a duration (e.g. `yield 0.04`), it requests the loop to sleep for 40 milliseconds.
3. The event loop moves the task to a `SleepQueue` with a deadline timestamp (`now + 0.04s`).
4. The loop immediately picks up the next ready task from its `ReadyQueue`.
5. When a sleeping task's deadline passes, the loop wakes it up and moves it back to the `ReadyQueue`.
6. When a coroutine returns, Python raises `StopIteration(value)`. The loop intercepts this to set `task.status = "COMPLETED"` and extract `task.result = value`.

```mermaid
sequenceDiagram
    participant Loop as EventLoop
    participant Ready as ReadyQueue (FIFO)
    participant SleepQ as SleepQueue (Deadlines)
    participant TaskA as Task A (sleep 40ms)
    participant TaskB as Task B (sleep 10ms)

    Loop->>Ready: Pop next ready task (Task A)
    Loop->>TaskA: Step() -> yields 0.04s
    Loop->>SleepQ: Insert Task A (deadline: now + 40ms)

    Loop->>Ready: Pop next ready task (Task B)
    Loop->>TaskB: Step() -> yields 0.01s
    Loop->>SleepQ: Insert Task B (deadline: now + 10ms)

    Note over Loop: 10ms pass... Task B deadline reached!
    Loop->>SleepQ: Wake Task B -> move to ReadyQueue
    Loop->>Ready: Pop Task B
    Loop->>TaskB: Step() -> returns "B_finished" (COMPLETED!)

    Note over Loop: 30ms pass... Task A deadline reached!
    Loop->>SleepQ: Wake Task A -> move to ReadyQueue
    Loop->>Ready: Pop Task A
    Loop->>TaskA: Step() -> returns "A_finished" (COMPLETED!)
```

Notice the power of cooperative multitasking: **Task B started after Task A, but woke up and completed BEFORE Task A finished**, without creating any operating system threads!

---

## 2. Project Layout

The project lives under [`Samples/Ported/17_micro_eventloop/`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/17_micro_eventloop/):

```
Samples/Ported/17_micro_eventloop/
├── MicroEventLoop.psproj   # Project configuration manifest
├── EventLoop.ps            # C# event loop & task scheduler (214 lines)
├── README.md               # Documentation and build instructions
├── run_eventloop.py        # Automated verification test suite
└── dist/
    └── micro_async.py      # Transpiled pure Python 3.11 module
```

---

## 3. The C# Source Implementation: `EventLoop.ps`

In [`EventLoop.ps`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/17_micro_eventloop/EventLoop.ps), three classes drive the entire architecture:

### 1. The `Task` Class
Encapsulates a generator coroutine with explicit lifecycle states (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`):

```csharp
namespace MicroAsync;

extern using time;
using PythonSharp.Core;

public class Task
{
    private object _coro;
    private string _status;
    private object? _result;
    private object? _exception;

    public Task(object coro)
    {
        this._coro = coro;
        this._status = "PENDING";
    }

    [InlineTemplate("{0}.send(None)")]
    private static extern object? SendNone(object coro);

    [InlineTemplate("getattr({0}, 'value', None)")]
    private static extern object? GetExceptionValue(object exc);

    [InlineTemplate("isinstance({0}, StopIteration)")]
    private static extern bool IsStopIteration(object exc);

    public StepResult Step()
    {
        this._status = "RUNNING";
        try
        {
            object? yielded = SendNone(this._coro);
            return new StepResult(false, yielded, null);
        }
        catch (Exception err)
        {
            // Generator returned value via StopIteration!
            if (IsStopIteration(err))
            {
                this._status = "COMPLETED";
                this._result = GetExceptionValue(err);
                return new StepResult(true, this._result, null);
            }
            // Unhandled exception inside coroutine!
            this._status = "FAILED";
            this._exception = err;
            return new StepResult(true, null, err);
        }
    }
}
```

### 2. The `EventLoop` Orchestrator
Manages `_readyQueue` and `_sleepQueue`:

```csharp
public class EventLoop
{
    private List<Task> _readyQueue;
    private List<DelayedTask> _sleepQueue;

    public EventLoop()
    {
        this._readyQueue = new List<Task>();
        this._sleepQueue = new List<DelayedTask>();
    }

    public object? RunUntilComplete(Task rootTask)
    {
        while (!rootTask.IsDone)
        {
            double now = GetTime();

            // 1. Move awakened tasks from sleep queue to ready queue
            List<DelayedTask> remainingSleep = new List<DelayedTask>();
            int s = 0;
            while (s < this._sleepQueue.Count)
            {
                DelayedTask dt = this._sleepQueue[s];
                if (dt.Deadline <= now)
                {
                    this._readyQueue.Add(dt.Task);
                }
                else
                {
                    remainingSleep.Add(dt);
                }
                s = s + 1;
            }
            this._sleepQueue = remainingSleep;

            // 2. Step the next ready task
            if (this._readyQueue.Count > 0)
            {
                Task current = this._readyQueue[0];
                this._readyQueue.RemoveAt(0);

                if (current.IsDone) continue;

                StepResult stepRes = current.Step();
                if (!stepRes.Done)
                {
                    object? y = stepRes.Value;
                    if (IsNumeric(y) && ToDouble(y) > 0.0)
                    {
                        // Task requested cooperative sleep!
                        this._sleepQueue.Add(new DelayedTask(GetTime() + ToDouble(y), current));
                    }
                    else
                    {
                        // Task yielded None: re-queue immediately
                        this._readyQueue.Add(current);
                    }
                }
            }
            else if (this._sleepQueue.Count > 0)
            {
                // Sleep until the earliest deadline
                double earliest = GetEarliestDeadline();
                double diff = earliest - GetTime();
                if (diff > 0.0)
                {
                    Sleep(diff < 0.05 ? diff : 0.05);
                }
            }
            else
            {
                throw new SystemException("Event loop deadlock: no tasks ready to execute");
            }
        }

        if (rootTask.Status == "FAILED" && rootTask.Exception != null)
        {
            RaiseException(rootTask.Exception);
        }

        return rootTask.Result;
    }
}
```

---

## 4. The Transpiled Output: `micro_async.py`

Compiling with:
```bash
psc build Samples/Ported/17_micro_eventloop -o Samples/Ported/17_micro_eventloop/dist
```
produces [`Samples/Ported/17_micro_eventloop/dist/micro_async.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/17_micro_eventloop/dist/micro_async.py).

### Transpiled Step Method:
```python
def step(self) -> StepResult:
    self._status = 'RUNNING'
    try:
        yielded: object | None = self._coro.send(None)
        return StepResult(False, yielded, None)
    except Exception as err:
        if isinstance(err, StopIteration):
            self._status = 'COMPLETED'
            self._result = getattr(err, 'value', None)
            return StepResult(True, self._result, None)
        self._status = 'FAILED'
        self._exception = err
        return StepResult(True, None, err)
```

Notice how `self._coro.send(None)` cleanly steps Python generator coroutines, and `getattr(err, 'value', None)` extracts the returned value from `StopIteration`.

---

## 5. Verification Test Suite

[`run_eventloop.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/17_micro_eventloop/run_eventloop.py) runs three rigorous tests:

### 1. Basic Coroutine Return
```python
def simple_coro():
    yield None
    yield None
    return "Async computation finished"

t1 = loop.create_task(simple_coro())
res = loop.run_until_complete(t1)
assert res == "Async computation finished"
assert t1.status == "COMPLETED"
```

### 2. Concurrent Interleaved Multitasking
Task A sleeps for 40ms (`yield 0.04`). Task B sleeps for 10ms (`yield 0.01`):
```python
timeline = []

def task_a():
    timeline.append("A_start")
    yield 0.04
    timeline.append("A_end")
    return "A_finished"

def task_b():
    timeline.append("B_start")
    yield 0.01
    timeline.append("B_end")
    return "B_finished"

def main():
    loop.create_task(task_b())
    val_a = yield from task_a()
    return val_a

res = loop.run_until_complete(loop.create_task(main()))
assert res == "A_finished"
# Task B started, finished, and logged B_end BEFORE A_end!
assert timeline == ["A_start", "B_start", "B_end", "A_end"]
```

### 3. Exception Propagation
```python
def failing_coroutine():
    yield 0.005
    raise ZeroDivisionError("Cooperative task division error")

fail_task = loop.create_task(failing_coroutine())
try:
    loop.run_until_complete(fail_task)
    assert False, "Should have raised"
except ZeroDivisionError as exc:
    assert "Cooperative task division error" in str(exc)
    assert fail_task.status == "FAILED"
```

Running the runner:
```bash
python3 Samples/Ported/17_micro_eventloop/run_eventloop.py
```
Outputs:
```
=== Step 1: Building MicroEventLoop via `psc build` ===
Build is up to date: outputs in '.../dist' are fresh.

=== Step 2: Testing Ported EventLoop Functionality ===
[PASS] Simple coroutine execution verified: Async computation finished
[PASS] Cooperative interleaved multitasking verified: ['A_start', 'B_start', 'B_end', 'A_end'] in 0.040s
[PASS] Exception correctly propagated from async task: Cooperative task division error

All micro-eventloop verification checks succeeded with 0 errors!
```

---

## Key Takeaways

1. **Async Event Loops Demystified**: An asynchronous event loop is simply a cooperative scheduler stepping coroutines via `.send(None)` with dual queues.
2. **Zero-Wrapper Coroutine Stepping**: Interacts with native Python generators and `yield from` syntax seamlessly.
3. **True Interleaved Concurrency**: Shorter sleeping tasks wake up and complete before longer ones without thread creation.

---

## Next Steps: The Retrospective!

We have completed all 17 ported libraries across all 7 tiers!

In our final post, **[Blog 26: Dogfooding Retrospective — Lessons from 17 Ports, Python Transpilation Gotchas & The Road Ahead](./26_dogfooding_retrospective_compiler_hardening_and_gotchas.md)**, we summarize everything we learned, the compiler hardening that took place, and what lies ahead for PythonSharp!

