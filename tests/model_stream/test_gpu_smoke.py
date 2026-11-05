"""Short GPU smoke test (full run: python scripts/gpu_smoke.py)."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gpu_smoke.py"


@pytest.mark.gpu
def test_gpu_smoke_trains_and_loss_drops():
    spec = importlib.util.spec_from_file_location("gpu_smoke", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    r = mod.train(steps=40, batch_size=16, use_compile=False)
    assert r["finite"] and r["loss_start"] > 7.5 and r["loss_end"] < r["loss_start"] - 1.0
    assert r["positions_per_s"] > 1000 and r["n_params"] == 12_417_024
