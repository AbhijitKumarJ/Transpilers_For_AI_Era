# Sample 23: Shape-Safe Pandas DataFrame Analytics (Tier 10)

A ported enterprise data science module demonstrating strongly-typed tabular analytics in **PythonSharp** using `pandas` (`DataFrame<T>` and `Series<T>`).

---

## 1. Features Demonstrated

- **Strongly Typed Tabular Schemas**: Slotted immutable records (`EmployeeRecord`) mapped to typed DataFrame schemas.
- **Triple-Surface Architecture**:
  - **Surface 1 (Enterprise Architecture)**: Self-documenting domain methods (`CleanseMissingData`, `ImputeMissingValues`, `AggregateDepartmentalMeans`, `SortBySalaryRank`, `ExtractNumericalFeatureMatrix`).
  - **Surface 2 (Raw Python snake_case ABI)**: Direct interoperability with Jupyter Notebook patterns (`head`, `tail`, `describe`).
  - **Surface 3 (C# Standardized Bridge)**: Familiar PascalCase statistical methods (`Mean`, `Std`, `Sum`, `Min`, `Max`).
- **GroupBy Aggregations**: Grouping rows by categorical columns and computing arithmetic group means.
- **Missing Value Handling**: Cleansing with `dropna` and imputing defaults with `fillna`.
- **Zero Runtime Wrapper Tax**: Compiled Python code calls native `pandas` methods with no intermediate wrapper proxies or runtime translation overhead.

---

## 2. Compilation & Verification

### Build with PythonSharp Compiler (`psc`):
```bash
python3 -m psc.cli build DataFrameAnalytics.psproj -o dist
```

### Run Verification Harness:
```bash
python3 run_dataframe.py
```

