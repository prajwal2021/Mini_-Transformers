"""Glue: manifest + tokenizer -> cached tokens -> packed datasets -> one run per seed."""

from __future__ import annotations

import time
from pathlib import Path

from slm.data_loading import PackedDataset, tokenize_split, write_stats
from slm.model import ModelConfig
from slm.split_manifest import SplitManifest
from slm.tokenizer import BPETokenizer

from .config import TrainConfig
from .pretrain import train_run


def prepare_data(
    manifest: SplitManifest,
    tokenizer: BPETokenizer,
    model_cfg: ModelConfig,
    cfg: TrainConfig,
    cache_dir: str | Path,
) -> tuple[PackedDataset, PackedDataset, dict]:
    """Tokenise train+val once (cached), pack them, return datasets and run metadata."""
    t0 = time.perf_counter()
    tr = tokenize_split(manifest, "train", tokenizer, cache_dir, model_cfg.context_len)
    va = tokenize_split(manifest, "val", tokenizer, cache_dir, model_cfg.context_len)
    write_stats([tr, va], Path(cache_dir) / "token_stats.json")
    t1 = time.perf_counter()
    kw = dict(seq_len=model_cfg.context_len, label_eos=cfg.label_eos)
    train_ds = PackedDataset(tr.documents(), **kw)
    val_ds = PackedDataset(va.documents(), **kw)
    meta = {
        "tokenizer_hash": tokenizer.hash(),
        "tokenizer_vocab_size": tokenizer.vocab_size,
        "data_hash": {"train": tr.data_hash, "val": va.data_hash},
        "manifest": str(manifest.source),
        "token_stats": {"train": tr.stats, "val": va.stats},
        "packing": {"train_sequences": len(train_ds), "val_sequences": len(val_ds),
                    "train_efficiency": train_ds.efficiency,
                    "train_split_docs": train_ds.n_split_docs},
        "seconds_tokenize": t1 - t0,
        "seconds_pack": time.perf_counter() - t1,
    }
    return train_ds, val_ds, meta


def run_seeds(
    name: str,
    manifest: SplitManifest,
    tokenizer: BPETokenizer,
    model_cfg: ModelConfig,
    cfg: TrainConfig,
    runs_root: str | Path = "runs",
    cache_dir: str | Path | None = None,
    seeds: tuple[int, ...] | None = None,
    device: str | None = None,
) -> dict:
    """Train every seed into ``<runs_root>/<name>/seed<k>/``; returns per-seed summaries."""
    root = Path(runs_root) / name
    cache_dir = Path(cache_dir) if cache_dir else root / "token_cache"
    train_ds, val_ds, meta = prepare_data(manifest, tokenizer, model_cfg, cfg, cache_dir)
    out = {"prepare": meta, "seeds": {}}
    for seed in seeds if seeds is not None else cfg.seeds:
        t0 = time.perf_counter()
        summary = train_run(
            model_cfg, cfg, train_ds, val_ds, root / f"seed{seed}", seed, meta=meta, device=device
        )
        summary["wall_seconds"] = time.perf_counter() - t0
        out["seeds"][seed] = summary
    return out
