# 29_polars_dataframe

A modern fast tabular data analytics port demonstrating **Polars** integration in PythonSharp:
- Lazy query execution plans (`LazyFrame`, `filter`, `group_by`, `agg`)
- Column-based expression matching and aliasing
- Multi-column aggregation pipelines
- Zero-overhead compilation with Python 3.11+ AST emission

## Run Verification
```bash
python3 -m psc.cli build Samples/Ported/29_polars_dataframe/PolarsDataFrame.psproj -o Samples/Ported/29_polars_dataframe/dist
python3 Samples/Ported/29_polars_dataframe/run_polars.py
```

