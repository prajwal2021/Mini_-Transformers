"""Shared fixtures and markers for the model-stream tests."""

from pathlib import Path

import pytest
import torch

from slm.model import ModelConfig, Transformer
from slm.tokenizer import BPETokenizer, read_documents, train_tokenizer

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MOCK_CORPUS = FIXTURES / "mock_corpus_train.txt"


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: test that takes more than 30 s")
    config.addinivalue_line("markers", "gpu: needs a CUDA device (skipped otherwise)")


def pytest_collection_modifyitems(config, items):
    if torch.cuda.is_available():
        return
    skip = pytest.mark.skip(reason="CUDA is unavailable")
    for item in items:
        if "gpu" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def mock_docs() -> list[str]:
    return read_documents([MOCK_CORPUS])


@pytest.fixture(scope="session")
def tokenizer() -> BPETokenizer:
    return train_tokenizer([MOCK_CORPUS], vocab_size=4096, min_frequency=1)


def small_config(**kw) -> ModelConfig:
    base = dict(vocab_size=128, context_len=32, n_layer=2, n_head=4, d_model=64, d_ff=256,
                dropout=0.0)
    base.update(kw)
    return ModelConfig(**base)


@pytest.fixture()
def small_model() -> Transformer:
    torch.manual_seed(0)
    return Transformer(small_config()).eval()
