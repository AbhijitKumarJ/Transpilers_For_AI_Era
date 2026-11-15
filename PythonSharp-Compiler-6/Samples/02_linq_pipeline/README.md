# Sample 02: Fused LINQ & Multi-File Project

Demonstrates:
- Decoupled virtual namespaces across folders:
  - `DataPipeline.Models` (`Models/Product.ps`)
  - `DataPipeline.Services` (`Services/InventoryAnalytics.ps`)
- C# records lowered to Python dataclasses.
- Fused LINQ expressions (`.Where()`, `.OrderByDescending()`, `.Take()`, `.Select()`, `.Sum()`).
- Seamless consumption from standard Python (`run_pipeline.py`).

## Compilation & Execution

### 1. Compile the project with `psc build`
```bash
psc build DataPipeline.psproj -o dist
```

### 2. Run the mixed Python pipeline
```bash
python3 run_pipeline.py
```

