"""Put this worktree's src/ ahead of any editable install so tests import the local package."""

import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: test that takes more than a few seconds")
