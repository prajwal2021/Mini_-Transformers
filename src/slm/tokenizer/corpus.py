"""Corpus reading, the train-only guard, and tokenizer calibration."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

from .bpe import BPETokenizer

HELD_OUT_WORDS = frozenset({"val", "valid", "validation", "dev", "test", "heldout", "holdout"})
DOC_SEPARATOR = "\f"  # .txt files hold documents separated by a form feed


def assert_train_only(paths: Iterable[str | Path]) -> list[Path]:
    """Refuse any path whose file name marks it as validation/test data (D-003: train only)."""
    checked = []
    for raw in paths:
        path = Path(raw)
        bad = set(re.split(r"[^a-z0-9]+", path.name.lower())) & HELD_OUT_WORDS
        if bad:
            raise ValueError(
                f"refusing to fit the tokenizer on held-out data: {path} (name contains "
                f"{sorted(bad)}); the tokenizer is trained on the TRAIN split only"
            )
        checked.append(path)
    return checked


def _expand(path: Path) -> list[Path]:
    if path.is_dir():
        files = sorted(p for p in path.iterdir() if p.suffix in {".txt", ".jsonl"})
        return assert_train_only(files)
    return [path]


def read_documents(paths: Iterable[str | Path]) -> list[str]:
    """Read documents from .txt (form-feed separated) or .jsonl ({"text": ...}) files or dirs."""
    docs: list[str] = []
    for top in assert_train_only(paths):
        for path in _expand(top):
            text = path.read_text(encoding="utf-8")
            if path.suffix == ".jsonl":
                docs.extend(json.loads(line)["text"] for line in text.splitlines() if line.strip())
            else:
                docs.extend(d.strip() for d in text.split(DOC_SEPARATOR) if d.strip())
    return docs


def train_tokenizer(
    paths: Iterable[str | Path], vocab_size: int = 4096, min_frequency: int = 2
) -> BPETokenizer:
    """Train on the given files. Raises on val/test paths."""
    return BPETokenizer.train(read_documents(paths), vocab_size, min_frequency)


def calibrate(
    tokenizer: BPETokenizer, paths: Iterable[str | Path], context_len: int = 512
) -> dict[str, float]:
    """Corpus statistics used to size the context window.

    tokens_per_word counts whitespace-separated words against tokens without <|eos|>.
    share_over_context is the share of documents whose packed length (tokens + <|eos|>)
    exceeds ``context_len``.
    """
    docs = read_documents(paths)
    lengths = [len(tokenizer.encode(d)) for d in docs]
    n_words = sum(len(d.split()) for d in docs)
    n_tokens = sum(lengths)
    return {
        "n_docs": len(docs),
        "n_words": n_words,
        "n_tokens": n_tokens,
        "tokens_per_word": n_tokens / max(n_words, 1),
        "mean_doc_tokens": n_tokens / max(len(docs), 1),
        "max_doc_tokens": max(lengths, default=0) + 1,
        "share_over_context": sum(n + 1 > context_len for n in lengths) / max(len(docs), 1),
    }
