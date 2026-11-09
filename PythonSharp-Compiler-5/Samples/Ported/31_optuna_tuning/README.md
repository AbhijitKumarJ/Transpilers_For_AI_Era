# 31_optuna_tuning

Hyperparameter Optimization Studies in PythonSharp using **Optuna**:
- Study creation with specified search directions (`minimize`, `maximize`)
- Structured objective function evaluation with parameter suggestions (`suggest_float`, `suggest_int`)
- Iterative multi-trial search optimization
- Best trial extraction and parameter inspection

## Run Verification
```bash
python3 -m psc.cli build Samples/Ported/31_optuna_tuning/OptunaTuning.psproj -o Samples/Ported/31_optuna_tuning/dist
python3 Samples/Ported/31_optuna_tuning/run_optuna.py
```

