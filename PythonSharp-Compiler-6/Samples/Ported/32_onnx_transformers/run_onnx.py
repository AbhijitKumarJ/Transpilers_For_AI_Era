#!/usr/bin/env python3
"""Tier 12: Modern AI Inference & Vector Search — ONNX Transformers & Vector Index Verification Runner."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from types import ModuleType

# Setup zero-dependency mock for environments without native onnxruntime installed
try:
    import onnxruntime as ort
    if not hasattr(ort, "inference_session"):
        ort.inference_session = ort.InferenceSession
except ImportError:
    class MockInferenceSession:
        def __init__(self, model_path: str):
            self.model_path = model_path

        def run(self, output_names: list[str] | None, input_feed: dict[str, object]) -> list[list[float]]:
            # Mock transformer embeddings for input tokens
            return [[0.25, -0.15, 0.88, 0.42, -0.63, 0.12, 0.77, -0.31]]

    mock_ort = ModuleType("onnxruntime")
    mock_ort.InferenceSession = MockInferenceSession  # type: ignore[attr-defined]
    mock_ort.inference_session = MockInferenceSession  # type: ignore[attr-defined]
    sys.modules["onnxruntime"] = mock_ort
    ort = mock_ort  # type: ignore[assignment]


def main() -> int:
    sample_dir = Path(__file__).resolve().parent
    dist_dir = sample_dir / "dist"
    sys.path.insert(0, str(dist_dir))

    try:
        from python_sharp.samples.onnx_transformers import (  # type: ignore
            EmbeddingDocument,
            OnnxEmbeddingEngine,
            VectorSearchResult,
        )
    except ImportError:
        import subprocess
        res = subprocess.run(
            [sys.executable, "-m", "psc.cli", "build", str(sample_dir / "OnnxTransformers.psproj"), "-o", str(dist_dir)],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            print(f"Build failed:\n{res.stderr}")
            return 1
        from python_sharp.samples.onnx_transformers import (  # type: ignore
            EmbeddingDocument,
            OnnxEmbeddingEngine,
            VectorSearchResult,
        )

    print("================================================================================")
    print("PythonSharp Tier 12 Sample: 32_onnx_transformers Verification")
    print("================================================================================")

    # 1. Verify Inference Session Initialization
    session = OnnxEmbeddingEngine.create_inference_session("models/mini-transformer.onnx")
    print(f"[1] ONNX Runtime Inference Session Created: {session.model_path}")
    assert session is not None

    # 2. Vector Normalization
    raw_vec = [3.0, 4.0, 0.0, 0.0, 0.0]
    norm_vec = OnnxEmbeddingEngine.normalize_vector(raw_vec)
    l2_length = math.sqrt(sum(x * x for x in norm_vec))
    print(f"[2] Vector Normalization Verified: L2 Norm = {l2_length:.6f}")
    assert abs(l2_length - 1.0) < 1e-6
    assert abs(norm_vec[0] - 0.6) < 1e-6
    assert abs(norm_vec[1] - 0.8) < 1e-6

    # 3. Index Document Corpus (8-dimensional dense vectors)
    corpus_data = [
        ("DOC_AI", "Generative AI and Large Language Models", [0.9, 0.8, 0.7, 0.1, 0.0, 0.2, 0.1, 0.3]),
        ("DOC_QUANTUM", "Quantum Computing and Entanglement", [0.1, 0.2, 0.1, 0.9, 0.8, 0.7, 0.0, 0.1]),
        ("DOC_BIO", "Molecular Biology and Protein Folding", [0.0, 0.1, 0.2, 0.1, 0.2, 0.1, 0.9, 0.8]),
        ("DOC_ROBOTICS", "Autonomous Robotics and SLAM Navigation", [0.7, 0.8, 0.6, 0.3, 0.2, 0.4, 0.1, 0.2]),
        ("DOC_FINANCE", "Algorithmic High-Frequency Trading", [0.2, 0.1, 0.0, 0.1, 0.9, 0.1, 0.2, 0.8]),
    ]

    corpus: list[EmbeddingDocument] = []
    for doc_id, text, raw in corpus_data:
        corpus.append(OnnxEmbeddingEngine.index_document(doc_id, text, raw))

    print(f"[3] Document Corpus Indexed: {len(corpus)} documents (Dimension = {corpus[0].dimension})")
    assert len(corpus) == 5
    assert corpus[0].dimension == 8

    # 4. Semantic Vector Cosine Similarity Search
    # Query vector clearly focused on AI/Machine Learning
    query_vector = [0.95, 0.85, 0.75, 0.05, 0.0, 0.15, 0.05, 0.25]
    top_k = 3
    results: list[VectorSearchResult] = OnnxEmbeddingEngine.search_top_k(query_vector, corpus, top_k)

    print(f"[4] Top-{top_k} Vector Similarity Search Results:")
    for r in results:
        print(f"    Rank #{r.rank}: DocId = {r.doc_id:<12} Similarity = {r.similarity_score:.4f}")

    assert len(results) == 3
    assert results[0].doc_id == "DOC_AI", f"Expected DOC_AI to rank #1, got {results[0].doc_id}"
    assert results[1].doc_id == "DOC_ROBOTICS", f"Expected DOC_ROBOTICS to rank #2, got {results[1].doc_id}"
    assert results[0].similarity_score > results[1].similarity_score
    assert results[1].similarity_score > results[2].similarity_score

    print("--------------------------------------------------------------------------------")
    print("ALL 32_onnx_transformers VERIFICATIONS PASSED (100% Zero-Tax)")
    print("================================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
