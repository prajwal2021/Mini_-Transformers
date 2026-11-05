"""Tokenise manifest splits once and cache the ids.

Cache key = (tokenizer hash, hash of the split's files). Per key we store
``<key>.ids.npy`` (all documents concatenated, each ending in <|eos|>, uint16) and
``<key>.offsets.npy`` (document boundaries) plus ``<key>.meta.json`` with corpus statistics.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from slm.split_manifest import SplitManifest
from slm.tokenizer import BPETokenizer
from slm.tokenizer.corpus import parse_documents

DEFAULT_CONTEXT = 512


@dataclass
class TokenizedSplit:
    split: str
    ids: np.ndarray  # uint16, documents concatenated, each ending in <|eos|>
    offsets: np.ndarray  # int64, len n_docs + 1
    stats: dict
    data_hash: str  # hash of ids + offsets

    def documents(self) -> list[np.ndarray]:
        """Documents WITHOUT their trailing <|eos|> (PackedDataset appends it)."""
        o = self.offsets
        return [self.ids[o[i] : o[i + 1] - 1] for i in range(len(o) - 1)]


def _split_hash(manifest: SplitManifest, split: str) -> str:
    h = hashlib.sha256()
    for e in manifest.files(split):
        h.update(e.sha256.encode())
    return h.hexdigest()


def tokenize_split(
    manifest: SplitManifest,
    split: str,
    tokenizer: BPETokenizer,
    cache_dir: str | Path,
    context_len: int = DEFAULT_CONTEXT,
    allowed: tuple[str, ...] = ("train", "val"),
) -> TokenizedSplit:
    """Tokenise (or load from cache) one split. ``test`` is refused unless explicitly allowed."""
    if split not in allowed:
        raise ValueError(f"split {split!r} is not allowed here (allowed: {allowed})")
    if tokenizer.vocab_size > 65535:
        raise ValueError("ids do not fit uint16")
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{tokenizer.hash()}:{_split_hash(manifest, split)}".encode()).hexdigest()
    key = key[:20]
    ids_p, off_p, meta_p = (cache / f"{key}.{s}" for s in ("ids.npy", "offsets.npy", "meta.json"))
    if ids_p.exists() and off_p.exists() and meta_p.exists():
        ids, offsets = np.load(ids_p), np.load(off_p)
        stats = json.loads(meta_p.read_text(encoding="utf-8"))
        stats["cache_hit"] = True
    else:
        docs: list[str] = []
        for e in manifest.files(split):
            docs.extend(parse_documents(manifest.read_verified(e.path, allowed), e.path.suffix))
        encoded = [tokenizer.encode_document(d) for d in docs]
        lengths = np.array([len(x) for x in encoded], dtype=np.int64)
        flat = (t for x in encoded for t in x)
        ids = np.fromiter(flat, dtype=np.uint16, count=int(lengths.sum()))
        offsets = np.concatenate([[0], np.cumsum(lengths)]).astype(np.int64)
        n_words = sum(len(d.split()) for d in docs)
        stats = {
            "split": split,
            "n_docs": len(docs),
            "n_words": n_words,
            "n_tokens": int(lengths.sum() - len(docs)),  # without <|eos|>
            "n_tokens_with_eos": int(lengths.sum()),
            "tokens_per_word": float((lengths.sum() - len(docs)) / max(n_words, 1)),
            "share_docs_over_context": float((lengths > context_len).mean()) if docs else 0.0,
            "context_len": context_len,
            "tokenizer_hash": tokenizer.hash(),
            "cache_hit": False,
        }
        np.save(ids_p, ids)
        np.save(off_p, offsets)
        meta_p.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    data_hash = hashlib.sha256(ids.tobytes() + offsets.tobytes()).hexdigest()
    return TokenizedSplit(split, ids, offsets, stats, data_hash)


def write_stats(splits: list[TokenizedSplit], path: str | Path) -> None:
    """JSON with tokens_per_word and the share of documents over the context, per split."""
    out = {s.split: {k: v for k, v in s.stats.items() if k != "cache_hit"} for s in splits}
    Path(path).write_text(json.dumps(out, indent=2), encoding="utf-8")
