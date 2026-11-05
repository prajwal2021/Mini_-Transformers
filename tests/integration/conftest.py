"""Fixtures for the integration tests: a tiny tokenizer, a tiny model and the real KB."""

from pathlib import Path

import pytest
import torch

from slm.model import ModelConfig, Transformer
from slm.split_manifest import build_manifest
from slm.tokenizer import train_tokenizer

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
KB_PATH = ROOT / "data" / "kb" / "kb.json"


@pytest.fixture(scope="session")
def tokenizer(tmp_path_factory):
    d = tmp_path_factory.mktemp("integration_data")
    for name in ("mock_corpus_train.txt", "mock_corpus_val.txt"):
        (d / name).write_bytes((FIXTURES / name).read_bytes())
    manifest = build_manifest(
        {d / "mock_corpus_train.txt": "train", d / "mock_corpus_val.txt": "val"}, d / "splits.json"
    )
    return train_tokenizer(manifest, vocab_size=1024, min_frequency=1)


@pytest.fixture(scope="session")
def tiny_cfg(tokenizer) -> ModelConfig:
    return ModelConfig(vocab_size=tokenizer.vocab_size, context_len=96, n_layer=1, n_head=2,
                       d_model=32, d_ff=64, dropout=0.0)


@pytest.fixture()
def tiny_model(tiny_cfg) -> Transformer:
    torch.manual_seed(0)
    return Transformer(tiny_cfg).eval()


@pytest.fixture(scope="session")
def kb():
    from slm.integration.tables import load_kb

    return load_kb(KB_PATH)
