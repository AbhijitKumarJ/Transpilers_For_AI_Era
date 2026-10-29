# PythonSharp compiler benchmarks

`benchmark_compiler.py` generates a deterministic 1,000-class / 21-method
project, compiles it in memory, and reports compile time, emitted source size,
module count, and cold-import time.

## Usage

```bash
.venv/bin/python benchmarks/benchmark_compiler.py
.venv/bin/python benchmarks/benchmark_compiler.py --runs 5 --json
.venv/bin/python benchmarks/benchmark_compiler.py --classes 100 --methods 10 --no-import
```

The default workload is 1,000 classes with 21 methods each, including one LINQ
method per class. It produces 27,004 source lines, one emitted module, 70,002
emitted lines, and about 1.54 MB of Python source.

## Budget

- Default budget: **30 seconds** for the best of three compile runs.
- M6 reference baseline: **7.55 seconds** for 26,002 LOC on the original
  reference host.
- NFR-08 target: **under 10 seconds** for a 25k LOC project on a typical laptop.

The current local host is a 4-core Intel i5-7200U. Its measured best compile time
is about **20 seconds**, so the M6 baseline and NFR-08 target are hardware-sensitive
and remain performance follow-ups. The 30-second budget is the local regression
floor until a dedicated benchmark host is available.

Benchmarks belong in a dedicated CI job or nightly schedule, not every pull
request. Compare best-of-N results on the same host; a single run is noisy.
