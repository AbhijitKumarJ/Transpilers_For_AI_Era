#!/usr/bin/env python3
"""Tier 12: Modern AI Inference & Vector Search — Optuna Hyperparameter Optimization Study Verification Runner."""

from __future__ import annotations

import random
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable

# Setup zero-dependency mock for environments without native optuna installed
try:
    import optuna
except ImportError:
    class MockTrial:
        def __init__(self, number: int):
            self.number = number
            self.params: dict[str, object] = {}
            self.value: float = 0.0

        def suggest_float(self, name: str, low: float, high: float) -> float:
            # Deterministic heuristic search approaching 0.05
            val = low + (high - low) * (0.2 + (self.number * 0.03) % 0.6)
            self.params[name] = val
            return val

        def suggest_int(self, name: str, low: int, high: int) -> int:
            val = low + int((high - low) * (0.3 + (self.number * 0.05) % 0.5))
            self.params[name] = val
            return val

    class MockStudy:
        def __init__(self, direction: str = "minimize"):
            self.direction = direction
            self.trials: list[MockTrial] = []
            self.best_trial: MockTrial | None = None

        def optimize(self, objective: Callable[[MockTrial], float], n_trials: int = 20) -> None:
            best_val = float("inf") if self.direction == "minimize" else float("-inf")
            for i in range(n_trials):
                t = MockTrial(i)
                val = objective(t)
                t.value = val
                self.trials.append(t)
                if (self.direction == "minimize" and val < best_val) or (self.direction == "maximize" and val > best_val):
                    best_val = val
                    self.best_trial = t

    mock_optuna = ModuleType("optuna")
    mock_optuna.create_study = lambda direction="minimize": MockStudy(direction)  # type: ignore[attr-defined]
    sys.modules["optuna"] = mock_optuna
    optuna = mock_optuna  # type: ignore[assignment]


def main() -> int:
    sample_dir = Path(__file__).resolve().parent
    dist_dir = sample_dir / "dist"
    sys.path.insert(0, str(dist_dir))

    try:
        from python_sharp.samples.optuna_tuning import OptunaEngine, TrialResult  # type: ignore
    except ImportError:
        import subprocess
        res = subprocess.run(
            [sys.executable, "-m", "psc.cli", "build", str(sample_dir / "OptunaTuning.psproj"), "-o", str(dist_dir)],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            print(f"Build failed:\n{res.stderr}")
            return 1
        from python_sharp.samples.optuna_tuning import OptunaEngine, TrialResult  # type: ignore

    print("================================================================================")
    print("PythonSharp Tier 12 Sample: 31_optuna_tuning Verification")
    print("================================================================================")

    # 1. Create optimization study (minimize loss)
    study = OptunaEngine.create_study("minimize")
    print(f"[1] Study Created: Direction = {study.direction}")
    assert study.direction == "minimize"

    # 2. Benchmark isolated objective evaluation
    ideal_loss = OptunaEngine.evaluate_objective(0.05, 6)
    suboptimal_loss = OptunaEngine.evaluate_objective(0.15, 9)
    print(f"[2] Objective Function Verification: Ideal Loss = {ideal_loss:.4f}, Suboptimal = {suboptimal_loss:.4f}")
    assert ideal_loss < suboptimal_loss
    assert abs(ideal_loss - 0.12) < 1e-6

    # 3. Execute 25 Optimization Trials
    num_trials = 25
    OptunaEngine.optimize(study, num_trials)
    print(f"[3] Executed {len(study.trials)} Optimization Trials.")
    assert len(study.trials) == num_trials

    # 4. Inspect Best Trial Result
    best = OptunaEngine.get_best_trial(study)
    print(f"[4] Best Trial #{best.trial_number}: Value = {best.value:.5f}")
    print(f"    Parameters: learning_rate = {best.learning_rate:.4f}, max_depth = {best.max_depth}")
    assert best.value < 1.0, f"Expected converged value < 1.0, got {best.value}"
    assert 0.001 <= best.learning_rate <= 0.2
    assert 3 <= best.max_depth <= 10

    print("--------------------------------------------------------------------------------")
    print("ALL 31_optuna_tuning VERIFICATIONS PASSED (100% Zero-Tax)")
    print("================================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())

