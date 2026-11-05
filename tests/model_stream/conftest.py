"""Shared fixtures for the model-stream tests (markers live in tests/conftest.py)."""

from pathlib import Path

import pytest
import torch

from slm.model import ModelConfig, Transformer
from slm.split_manifest import SplitManifest, build_manifest
from slm.tokenizer import BPETokenizer, read_split, train_tokenizer

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MOCK_CORPUS = FIXTURES / "mock_corpus_train.txt"


@pytest.fixture(scope="session")
def mock_manifest(tmp_path_factory) -> SplitManifest:
    """Manifest over a copy of the mock files (hashes computed here, so line-endings can't bite)."""
    d = tmp_path_factory.mktemp("mock_data")
    for name in ("mock_corpus_train.txt", "mock_corpus_val.txt"):
        (d / name).write_bytes((FIXTURES / name).read_bytes())
    return build_manifest(
        {d / "mock_corpus_train.txt": "train", d / "mock_corpus_val.txt": "val"}, d / "splits.json"
    )


@pytest.fixture(scope="session")
def mock_docs(mock_manifest) -> list[str]:
    return read_split(mock_manifest, "train")


@pytest.fixture(scope="session")
def tokenizer(mock_manifest) -> BPETokenizer:
    return train_tokenizer(mock_manifest, vocab_size=4096, min_frequency=1)


def small_config(**kw) -> ModelConfig:
    base = dict(vocab_size=128, context_len=32, n_layer=2, n_head=4, d_model=64, d_ff=256,
                dropout=0.0)
    base.update(kw)
    return ModelConfig(**base)


@pytest.fixture()
def small_model() -> Transformer:
    torch.manual_seed(0)
    return Transformer(small_config()).eval()
