# 32_onnx_transformers

Dense Vector Search & ONNX Runtime Inference in PythonSharp:
- ONNX Runtime InferenceSession lifecycle management
- Exact L2 vector normalization and dot-product cosine similarity
- In-memory vector database indexing with typed document records
- Top-K semantic similarity ranking and retrieval

## Run Verification
```bash
python3 -m psc.cli build Samples/Ported/32_onnx_transformers/OnnxTransformers.psproj -o Samples/Ported/32_onnx_transformers/dist
python3 Samples/Ported/32_onnx_transformers/run_onnx.py
```

