# Sample 03: Pydantic v2 Schema Models

Demonstrates:
- `[SchemaModel]` attribute lowering to Pydantic v2 `BaseModel`.
- Automatic typing of fields, default values, and computed instance methods.
- Zero-runtime tax: `from pydantic import BaseModel` is emitted only when schemas are present. Non-schema code remains 100% dependency-free.
- Consumption in standard Python API frameworks (FastAPI, Flask, etc.).

## Compilation & Execution

### 1. Compile schemas with `psc build`
```bash
psc build Schemas.ps -o dist
```

### 2. Run the Python application
```bash
python3 app.py
```
*(Optional: `pip install pydantic` to activate full Pydantic v2 runtime validation and serialization).*

