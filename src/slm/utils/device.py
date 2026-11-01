"""Compute-device selection."""

from typing import Optional

import torch


def get_device(prefer: Optional[str] = None) -> torch.device:
    """Return a usable device, honoring a requested available device when possible."""
    candidates = [prefer] if prefer else []
    candidates += ["cuda", "mps", "cpu"]
    for name in candidates:
        if name == "cuda" and torch.cuda.is_available():
            device = torch.device("cuda")
            capability = torch.cuda.get_device_capability(device)
            bf16 = torch.cuda.is_bf16_supported()
            print(
                "Using CUDA: "
                f"torch={torch.__version__}, cuda={torch.version.cuda}, "
                f"device={torch.cuda.get_device_name(device)}, "
                f"compute_capability={capability[0]}.{capability[1]}, bf16={bf16}"
            )
            return device
        if name == "mps" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = torch.device("mps")
            print("Using MPS: available Apple GPU detected")
            return device
        if name == "cpu":
            print("Using CPU: no preferred accelerator is available")
            return torch.device("cpu")
    print("Using CPU: requested device is unavailable")
    return torch.device("cpu")
