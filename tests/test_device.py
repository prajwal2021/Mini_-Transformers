"""CUDA device smoke tests."""

import pytest
import torch


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is unavailable")
def test_cuda_matmul() -> None:
    """Verify a small CUDA matrix multiplication when a GPU is available."""
    left = torch.randn(32, 32, device="cuda")
    right = torch.randn(32, 32, device="cuda")
    result = left @ right
    assert result.device.type == "cuda"
    assert result.shape == (32, 32)
