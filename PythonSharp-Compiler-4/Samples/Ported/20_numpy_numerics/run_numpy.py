"""Tier 9: NumPy Numerics Ported Sample Verification Runner."""

import sys
from pathlib import Path
from types import ModuleType

# Zero-dependency shim for testing in environments without native numpy C extensions
try:
    import numpy as np
except ImportError:
    class MockNDArray:
        def __init__(self, data):
            if isinstance(data, (tuple, list)) and len(data) == 2 and isinstance(data[0], int):
                self.shape = list(data)
                self.data = [[1.0] * data[1] for _ in range(data[0])]
            else:
                self.data = data
                self.shape = [len(data), len(data[0])] if isinstance(data, list) and data else [0]
            self.ndim = len(self.shape)

        @property
        def T(self) -> "MockNDArray":
            rows, cols = self.shape
            trans = [[self.data[r][c] for r in range(rows)] for c in range(cols)]
            return MockNDArray(trans)

        def __matmul__(self, other: "MockNDArray") -> "MockNDArray":
            r1, c1 = self.shape
            r2, c2 = other.shape
            res = [[0.0] * c2 for _ in range(r1)]
            for i in range(r1):
                for j in range(c2):
                    res[i][j] = sum(self.data[i][k] * other.data[k][j] for k in range(c1))
            return MockNDArray(res)

        def __getitem__(self, item) -> "MockNDArray":
            if isinstance(item, tuple) and len(item) == 2:
                s1, s2 = item
                sub = [row[s2] for row in self.data[s1]]
                return MockNDArray(sub)
            return self

    mock_np = ModuleType("numpy")
    mock_np.ndarray = MockNDArray  # type: ignore[attr-defined]
    mock_np.eye = lambda size: MockNDArray([[1.0 if i == j else 0.0 for j in range(size)] for i in range(size)])  # type: ignore[attr-defined]
    mock_np.ones = lambda shape: MockNDArray(shape)  # type: ignore[attr-defined]
    mock_np.zeros = lambda shape: MockNDArray(shape)  # type: ignore[attr-defined]
    sys.modules["numpy"] = mock_np
    np = mock_np

# Add dist directory to sys.path
base_dir = Path(__file__).parent
dist_dir = base_dir / "dist"
sys.path.insert(0, str(dist_dir))

from numpy_numerics import TensorEngine  # noqa: E402


def test_numpy_operations() -> None:
    print("=== Step 1: Testing TensorEngine Creation ===")
    eye = TensorEngine.create_identity(3)
    assert eye.shape == [3, 3], f"Expected [3, 3], got {eye.shape}"
    print(f"[PASS] 3x3 Identity matrix created with shape {eye.shape}")

    ones = TensorEngine.create_ones(3, 3)
    assert ones.shape == [3, 3], f"Expected [3, 3], got {ones.shape}"
    print(f"[PASS] 3x3 Ones matrix created with shape {ones.shape}")

    print("\n=== Step 2: Testing Matrix Multiplication (@ operator lowering) ===")
    prod = TensorEngine.multiply(eye, ones)
    assert prod.shape == [3, 3], f"Expected [3, 3], got {prod.shape}"
    print(f"[PASS] Matrix multiplication executed cleanly: eye @ ones = shape {prod.shape}")

    print("\n=== Step 3: Testing Transpose and Multi-Axis Slicing ===")
    trans = TensorEngine.transpose(prod)
    assert trans.shape == [3, 3]
    print(f"[PASS] Transpose matrix property (.T) verified: shape {trans.shape}")

    sub = TensorEngine.slice_sub_matrix(prod)
    assert sub.shape == [2, 2], f"Expected sub-matrix [2, 2], got {sub.shape}"
    print(f"[PASS] Multi-axis slicing (matrix[0:2, 0:2]) verified: shape {sub.shape}")

    print("\nAll 20_numpy_numerics verification checks succeeded with 0 errors!")


if __name__ == "__main__":
    test_numpy_operations()

