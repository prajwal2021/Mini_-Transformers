"""Corpus reading through the split manifest, and tokenizer calibration."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from slm.split_manifest import SplitManifest

from .bpe import BPETokenizer

DOC_SEPARATOR = "\f"  # .txt files hold documents separated by a form feed


def parse_documents(raw: bytes, suffix: str) -> list[str]:
    """Documents from the bytes of a .txt (form-feed separated) or .jsonl ({"text": ...}) file."""
    text = raw.decode("utf-8")
    if suffix == ".jsonl":
        return [json.loads(line)["text"] for line in text.splitlines() if line.strip()]
    return [d.strip() for d in text.split(DOC_SEPARATOR) if d.strip()]


def read_split(
    manifest: SplitManifest, split: str, allowed: Sequence[str] = ("train", "val")
) -> list[str]:
    """All documents of ``split``; refuses a split outside ``allowed`` and verifies hashes."""
    if split not in allowed:
        raise ValueError(f"split {split!r} is not allowed here (allowed: {tuple(allowed)})")
    docs: list[str] = []
    for entry in manifest.files(split):
        docs.extend(parse_documents(manifest.read_verified(entry.path, allowed), entry.path.suffix))
    return docs


def train_tokenizer(
    manifest: SplitManifest | str | Path, vocab_size: int = 4096, min_frequency: int = 2
) -> BPETokenizer:
    """Fit the tokenizer on the manifest's TRAIN files only (hash-verified)."""
    if not isinstance(manifest, SplitManifest):
        manifest = SplitManifest.load(manifest)
    docs = read_split(manifest, "train", allowed=("train",))
    if not docs:
        raise ValueError("the manifest lists no train documents")
    return BPETokenizer.train(docs, vocab_size, min_frequency)


def calibrate(
    tokenizer: BPETokenizer, docs: Sequence[str], context_len: int = 512
) -> dict[str, float]:
    """Corpus statistics used to size the context window.

    tokens_per_word counts whitespace-separated words against tokens without <|eos|>.
    share_over_context is the share of documents whose packed length (tokens + <|eos|>)
    exceeds ``context_len``.
    """
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
