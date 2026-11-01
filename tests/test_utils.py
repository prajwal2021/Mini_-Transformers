"""Tests for P00 utilities."""

import json

import torch

from slm.utils.config import config_hash
from slm.utils.device import get_device
from slm.utils.hashing import dir_sha256
from slm.utils.jsonl_logger import JsonlLogger
from slm.utils.manifest import write_manifest
from slm.utils.seed import set_seed


def test_seed_reproducibility() -> None:
    set_seed(7)
    first = torch.rand(4)
    set_seed(7)
    assert torch.equal(first, torch.rand(4))


def test_config_hash_key_order() -> None:
    assert config_hash({"a": 1, "b": {"c": 2}}) == config_hash({"b": {"c": 2}, "a": 1})


def test_manifest_required_keys(tmp_path) -> None:
    manifest = write_manifest(tmp_path, {"seed": 1, "model": {"layers": 2}})
    required = {
        "git_commit",
        "git_dirty",
        "config",
        "config_hash",
        "seed",
        "python_version",
        "torch_version",
        "platform",
        "device",
        "start_time_utc",
    }
    assert required <= manifest.keys()
    assert (tmp_path / "manifest.json").exists()


def test_jsonl_logger_round_trip(tmp_path) -> None:
    path = tmp_path / "metrics.jsonl"
    with JsonlLogger(path) as logger:
        logger.log(step=3, loss=1.25)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["step"] == 3 and record["loss"] == 1.25 and "timestamp" in record


def test_dir_hash_deterministic(tmp_path) -> None:
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    first = dir_sha256(tmp_path)
    assert first == dir_sha256(tmp_path)


def test_get_device_valid() -> None:
    assert get_device().type in {"cuda", "mps", "cpu"}
