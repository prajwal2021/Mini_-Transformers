"""Shared pytest configuration for the whole repo: markers and the GPU skip rule.

The package is imported from the editable install (`pip install -e .`), so no sys.path edits.
"""

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: test that takes more than 30 s")
    config.addinivalue_line("markers", "gpu: needs a CUDA device (skipped otherwise)")


def pytest_collection_modifyitems(config, items):
    try:
        import torch

        if torch.cuda.is_available():
            return
    except ImportError:  # pragma: no cover
        pass
    skip = pytest.mark.skip(reason="CUDA is unavailable")
    for item in items:
        if "gpu" in item.keywords:
            item.add_marker(skip)
