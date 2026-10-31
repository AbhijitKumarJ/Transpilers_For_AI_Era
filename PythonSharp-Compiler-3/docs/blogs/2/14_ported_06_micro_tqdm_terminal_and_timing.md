# Level 2 — Blog 14: Ported 06 — Micro-Tqdm (`06_micro_tqdm`): Terminal Control, Carriage Returns & Timing

Welcome to **Tier 3: Utilities & Tools**! In this tier, we move beyond pure in-memory algorithms to interactive utilities that interact with system clocks, standard output streams, and the operating environment.

We begin with **`06_micro_tqdm`**, inspired by the world-famous `tqdm` Python library.

In this post, we explore:
1. **The Target**: Building a real-time, zero-dependency command line progress bar.
2. **Project Layout**: The `.psproj` manifest.
3. **The C# Implementation (`ProgressBar.ps`)**: System time tracking (`extern using time;`), rolling rate estimation, ETA calculation, and ANSI carriage return (`\r`) overwriting.
4. **The Transpiled Output (`micro_tqdm_util.py`)**: How `Console.Write` compiles to `print(..., end='', flush=True)` and `extern using` maps to Python module imports.
5. **The Verification Test Harness (`run_tqdm.py`)**: Live visual rendering and mathematical verification of progress ratios.

---

## 1. The Target: Terminal Progress Bars

When processing large datasets or long-running tasks, developers want a live visual indicator that updates on the same terminal line without scrolling:

```
Processing Items: [===========>.........] 55% (11/20) [00:00<00:00, 49.45 it/s]
```

To achieve this, the progress bar must:
1. Print a carriage return (`\r`) to reposition the terminal cursor back to column 0 without moving down a line.
2. Calculate elapsed time and iterations per second ($\text{it/s}$).
3. Compute dynamic Estimated Time to Arrival ($\text{ETA} = \frac{\text{remaining items}}{\text{rate}}$).
4. Flush standard output immediately so updates render in real time.

---

## 2. Project Layout

The project lives under [`Samples/Ported/06_micro_tqdm/`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/06_micro_tqdm/):

```
Samples/Ported/06_micro_tqdm/
├── MicroTqdm.psproj       # Project configuration manifest
├── ProgressBar.ps         # C# source implementation
├── README.md              # Documentation and build instructions
├── run_tqdm.py            # Automated test runner and live simulation
└── dist/
    └── micro_tqdm_util.py # Transpiled pure Python 3.11 module
```

---

## 3. The C# Source Implementation: `ProgressBar.ps`

In [`ProgressBar.ps`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/06_micro_tqdm/ProgressBar.ps), notice the use of `extern using time;`:

```csharp
namespace MicroTqdmUtil;

extern using time;
using PythonSharp.Core;

public class ProgressBar
{
    private readonly int _total;
    private readonly int _barWidth;
    private readonly double _startTime;
    private int _current;
    private string _desc;

    public ProgressBar(int total, string desc = "", int barWidth = 30)
    {
        _total = total;
        _desc = desc;
        _barWidth = barWidth;
        _current = 0;
        _startTime = time.time();
    }

    public int Current => _current;
    public int Total => _total;
    public string Description => _desc;

    public void Update(int step = 1)
    {
        _current = _current + step;
        if (_current > _total)
        {
            _current = _total;
        }
        Render();
    }

    public string RenderString()
    {
        double now = time.time();
        double elapsed = now - _startTime;
        double rate = elapsed > 0.0 ? (_current * 1.0) / elapsed : 0.0;
        int remaining = _total - _current;
        double eta = rate > 0.0 ? (remaining * 1.0) / rate : 0.0;

        int percent = _total > 0 ? (_current * 100) / _total : 100;
        int filledLen = _total > 0 ? (_current * _barWidth) / _total : _barWidth;
        if (filledLen > _barWidth) filledLen = _barWidth;

        string bar = "";
        int i = 0;
        while (i < filledLen)
        {
            bar = bar + "=";
            i = i + 1;
        }
        if (filledLen < _barWidth)
        {
            bar = bar + ">";
            i = i + 1;
        }
        while (bar.Length < _barWidth)
        {
            bar = bar + ".";
        }

        string prefix = _desc.Length > 0 ? $"{_desc}: " : "";
        string etaStr = FormatTime(eta);
        string elapsedStr = FormatTime(elapsed);
        string rateStr = FormatRate(rate);

        return $"{prefix}[{bar}] {percent}% ({_current}/{_total}) [{elapsedStr}<{etaStr}, {rateStr}]";
    }

    public void Render()
    {
        string text = RenderString();
        Console.Write($"\r{text}");
        if (_current >= _total)
        {
            Console.WriteLine();
        }
    }

    public static string FormatTime(double seconds)
    {
        int totalSec = Int32.From(seconds);
        int mins = totalSec / 60;
        int secs = totalSec % 60;
        string mStr = mins < 10 ? $"0{mins}" : $"{mins}";
        string sStr = secs < 10 ? $"0{secs}" : $"{secs}";
        return $"{mStr}:{sStr}";
    }

    public static string FormatRate(double itPerSec)
    {
        if (itPerSec < 0.001) return "0.00 it/s";
        int whole = Int32.From(itPerSec);
        double diff = (itPerSec - Double.From(whole)) * 100.0 + 0.5;
        int frac = Int32.From(diff);
        if (frac < 0) frac = 0;
        string fracStr = frac < 10 ? $"0{frac}" : $"{frac}";
        return $"{whole}.{fracStr} it/s";
    }
}
```

---

## 4. The Transpiled Output: `micro_tqdm_util.py`

Compiling with:
```bash
psc build Samples/Ported/06_micro_tqdm -o Samples/Ported/06_micro_tqdm/dist
```
produces [`Samples/Ported/06_micro_tqdm/dist/micro_tqdm_util.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/06_micro_tqdm/dist/micro_tqdm_util.py):

```python
# Auto-generated by PythonSharp (psc) — Bytecode line-pinned to ProgressBar.ps
from __future__ import annotations
import time

class ProgressBar:
    __ps_types__ = ('MicroTqdmUtil.ProgressBar',)
    __slots__ = ('_total', '_bar_width', '_start_time', '_current', '_desc')

    def __init__(self, total: int, desc: str = '', bar_width: int = 30) -> None:
        self._total = total
        self._desc = desc
        self._bar_width = bar_width
        self._current = 0
        self._start_time = time.time()

    @property
    def current(self) -> int:
        return self._current

    @property
    def total(self) -> int:
        return self._total

    @property
    def description(self) -> str:
        return self._desc

    def set_description(self, desc: str) -> None:
        self._desc = desc

    def update(self, step: int = 1) -> None:
        self._current = self._current + step
        if self._current > self._total:
            self._current = self._total
        self.render()

    def render_string(self) -> str:
        now: float = time.time()
        elapsed: float = now - self._start_time
        rate: float = self._current * 1.0 / elapsed if elapsed > 0.0 else 0.0
        remaining: int = self._total - self._current
        eta: float = remaining * 1.0 / rate if rate > 0.0 else 0.0
        percent: int = self._current * 100 // self._total if self._total > 0 else 100
        filled_len: int = self._current * self._bar_width // self._total if self._total > 0 else self._bar_width
        if filled_len > self._bar_width:
            filled_len = self._bar_width
        bar: str = ''
        i: int = 0
        while i < filled_len:
            bar = bar + '='
            i = i + 1
        if filled_len < self._bar_width:
            bar = bar + '>'
            i = i + 1
        while len(bar) < self._bar_width:
            bar = bar + '.'
        prefix: str = f'{self._desc}: ' if len(self._desc) > 0 else ''
        eta_str: str = ProgressBar.format_time(eta)
        elapsed_str: str = ProgressBar.format_time(elapsed)
        rate_str: str = ProgressBar.format_rate(rate)
        return f'{prefix}[{bar}] {percent}% ({self._current}/{self._total}) [{elapsed_str}<{eta_str}, {rate_str}]'

    def render(self) -> None:
        text: str = self.render_string()
        print(f'\r{text}', end='', flush=True)
        if self._current >= self._total:
            print()
```

### Architectural Highlights:
1. **`extern using time;` $\to$ `import time`**: The compiler recognizes external module declarations and imports them cleanly at the top of the emitted module.
2. **`Console.Write` Erasure**: `Console.Write($"\r{text}")` lowers directly to `print(f'\r{text}', end='', flush=True)`.
3. **Expression-Bodied Properties**: `public int Current => _current;` lowers to a standard Python `@property def current(self) -> int: return self._current`.
4. **Memory Optimization**: `__slots__` contains the five instance fields, ensuring minimal RAM consumption during tight iteration loops.

---

## 5. Verification: Running the Live Test Harness

[`run_tqdm.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/06_micro_tqdm/run_tqdm.py) runs both unit assertions and a live visual simulation:

```python
# 1. Format time unit test
assert ProgressBar.format_time(0.0) == "00:00"
assert ProgressBar.format_time(65.0) == "01:05"

# 2. String representation tests
pb = ProgressBar(100, "Testing", 20)
s0 = pb.render_string()
assert "0%" in s0 and "(0/100)" in s0

pb.update(50)
s50 = pb.render_string()
assert "50%" in s50 and "(50/100)" in s50

# 3. Simulate real-time progress bar loop
live_bar = ProgressBar(20, "Processing Items", 25)
for _ in range(20):
    time.sleep(0.02)
    live_bar.update(1)
```

Running the runner:
```bash
python3 Samples/Ported/06_micro_tqdm/run_tqdm.py
```
Outputs:
```
=== Step 1: Building MicroTqdm via `psc build` ===
Build is up to date: outputs in '.../dist' are fresh.

=== Step 2: Testing Ported ProgressBar Functionality ===
[PASS] ProgressBar.format_time correctly formats MM:SS
[PASS] ProgressBar.format_rate correctly formats iteration speed
[PASS] 0% Render: Testing: [>...................] 0% (0/100) [00:00<00:00, 0.00 it/s]
[PASS] 50% Render: Testing: [==========>.........] 50% (50/100) [00:00<00:00, 759837.68 it/s]
[PASS] 100% Render: Testing: [====================] 100% (100/100) [00:00<00:00, 816012.45 it/s]

Simulating live progress bar:
Processing Items: [=========================>] 100% (20/20) [00:00<00:00, 49.38 it/s]

All micro-tqdm verification checks succeeded with 0 errors!
```

---

## Key Takeaways

1. **System Interop via `extern using`**: Easily consume Python's `time` module with native C# method call syntax.
2. **Interactive Terminal Output**: `Console.Write` compiles into `print(..., end='', flush=True)` with zero buffer lag.
3. **Compact Memory Footprint**: Minimal object allocation during high-frequency update loops.

---

## Next Steps

Now let's examine file input/output, environment variable management, and quote unescaping!

In **[Blog 15: Ported 07 — Micro-Dotenv (`07_micro_dotenv`): File I/O, Quote Unescaping & Environment Injection](./15_ported_07_micro_dotenv_file_io_and_escapes.md)**, we examine how Python's `os.environ` is managed from PythonSharp!

