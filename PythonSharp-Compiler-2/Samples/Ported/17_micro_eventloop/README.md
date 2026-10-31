# Ported: `17_micro_eventloop`

A lightweight cooperative asynchronous event loop and task scheduler implemented in **PythonSharp** (`.ps`), compiling to clean Python 3.11+.

Ported from core concepts in Python's `asyncio` and micro cooperative multitasking event loops.

---

## Features

- **Cooperative `Task` Model**: Encapsulates generator coroutines with lifecycle states (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`).
- **Generator Stepping**: Steps coroutines using `.send(None)`, seamlessly intercepting `StopIteration` for return value extraction and bubbling unhandled errors.
- **Ready & Sleep Queues**:
  - `ReadyQueue`: FIFO queue for tasks ready to resume immediately.
  - `SleepQueue`: Time-deadline queue for tasks yielding float durations (`yield 0.02`), waking them as deadlines elapse.
- **Interleaved Multitasking**: Concurrently steps multiple tasks, allowing shorter sleeping tasks to wake and finish before longer ones.
- **Error Propagation**: Unhandled exceptions inside coroutines fail the task and are re-thrown when awaiting completion via `EventLoop.RunUntilComplete(task)`.

---

## Build & Run

```bash
# 1. Compile the project
psc build Samples/Ported/17_micro_eventloop -o Samples/Ported/17_micro_eventloop/dist

# 2. Run the test harness
python3 Samples/Ported/17_micro_eventloop/run_eventloop.py
```

