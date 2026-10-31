# Ported 06: Micro TQDM (CLI Progress Bar)

A ported micro subset of the `tqdm` Python progress bar library implemented cleanly in PythonSharp (`.ps`). Demonstrates encapsulation of state, carriage return terminal overwrites (`Console.Write("\r...")`), real-time rate & ETA computation using standard `time` modules, and progress track formatting.

## Project Structure

- `MicroTqdm.psproj`: PythonSharp project file specifying assembly `MicroTqdmUtil` and target `py3.11`.
- `ProgressBar.ps`: Core implementation of `ProgressBar` with dynamic rate calculations and terminal rendering.
- `run_tqdm.py`: Verification harness testing formatting utilities, percentage tracks, and interactive simulation.

## Features

- **Dynamic Track Rendering**: Calculates percentage, completed steps, and track width (`[=========>....] 50%`).
- **Real-Time Timing**: Computes elapsed time, ETA, and throughput (iterations per second).
- **Zero Runtime Tax**: Compiles directly to standard Python 3.11+ using `time` and standard stdout writes.

## How to Build and Run

```bash
# Build the PythonSharp project
psc build Samples/Ported/06_micro_tqdm

# Run the test suite and visual demo
python3 Samples/Ported/06_micro_tqdm/run_tqdm.py
```

