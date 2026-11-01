# Sample 07: Triple-Surface AI/ML Customer Churn Pipeline

Demonstrates an end-to-end Machine Learning training pipeline written in **PythonSharp (`psc`)** showcasing how **Surface 1 (Enterprise FQN)**, **Surface 2 (Raw Python ABI)**, and **Surface 3 (C# Bridge)** collaborate seamlessly in a single enterprise solution without runtime wrapper overhead.

---

## 1. Architectural Highlights

1. **Surface 2 (Raw Python ABI)**:
   - Copy-pasted notebook style workflows with snake_case method names (`pd.read_csv`, `model_selection.train_test_split`, `ensemble.RandomForestClassifier`).
   - Zero translation friction for data scientists porting existing Python scripts.

2. **Surface 3 (C# Bridge)**:
   - Clean, idiomatic PascalCase signatures (`pd.ReadCsv<CustomerChurnRow>`, `sk.ModelSelection.TrainTestSplit`, `sk.Ensemble.RandomForestClassifier`).
   - Strong compile-time generic types for C# / .NET engineers.

3. **Surface 1 (Enterprise Domain FQN)**:
   - Highly maintainable, self-documenting domain services (`TabularDataReader.ReadCsvFile`, `TensorFactory.FromNumPyArray`, `AcceleratorRuntime.SelectOptimalDeviceName`).
   - Decorator lowering with `[DisableGradientTracking]` emitting `@torch.no_grad()`.

4. **Zero Runtime Wrapper Tax**:
   - Every surface call erases directly into native CPython AST nodes.
   - Emits pure, native imports (`import pandas as pd`, `import sklearn.ensemble as _ens`, `import torch as _torch`).

---

## 2. Project Layout

```text
Samples/07_ai_ml_triple_surface/
├── CustomerChurnPipeline.psproj     # Project manifest with AI/ML dependencies
├── CustomerChurnPipeline.ps         # Multi-surface C# source implementation
├── run_churn_pipeline.py            # Automated compilation and verification runner
└── README.md                        # Documentation and architecture guide
```

---

## 3. Running the Showcase

Compile and verify the pipeline:

```bash
python3 Samples/07_ai_ml_triple_surface/run_churn_pipeline.py
```

