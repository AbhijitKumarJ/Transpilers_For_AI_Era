# 30_xgboost_trees

Gradient Boosted Decision Trees in PythonSharp using **XGBoost**:
- DMatrix data structure construction
- Model training with customizable hyperparameters (`MaxDepth`, `LearningRate`, `NumRounds`, `Objective`)
- Probabilistic inference and classification accuracy calculations
- Feature importance ranking extraction

## Run Verification
```bash
python3 -m psc.cli build Samples/Ported/30_xgboost_trees/XGBoostTrees.psproj -o Samples/Ported/30_xgboost_trees/dist
python3 Samples/Ported/30_xgboost_trees/run_xgboost.py
```

