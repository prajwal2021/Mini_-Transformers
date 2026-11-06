# ruff: noqa: E501
"""Glue: SFT manifest + tokenizer -> datasets -> one SFT run per seed (seed k starts from the final
checkpoint of pretraining seed k)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from slm.split_manifest import SplitManifest
from slm.tokenizer import BPETokenizer

from .config import SFTConfig
from .data import SFTDataset, encode_rows
from .trainer import final_pretrain_checkpoint, sft_run


def parse_jsonl(data: bytes) -> list[dict]:
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def load_rows(manifest: SplitManifest, split: str) -> list[dict]:
    """Rows of every file the manifest lists under ``split`` (``train`` or ``val`` only)."""
    if split not in ("train", "val"):
        raise ValueError("test rows are opened with slm.guard.open_split, not here")
    rows: list[dict] = []
    for e in manifest.files(split):
        rows.extend(parse_jsonl(manifest.read_verified(e.path, (split,))))
    return rows


def prepare_sft_data(
    manifest: SplitManifest, tokenizer: BPETokenizer, context_len: int
) -> tuple[SFTDataset, SFTDataset]:
    return (
        SFTDataset(encode_rows(tokenizer, load_rows(manifest, "train"), context_len)),
        SFTDataset(encode_rows(tokenizer, load_rows(manifest, "val"), context_len)),
    )


def run_sft_seeds(
    name: str,
    pretrain_root: str | Path,
    manifest: SplitManifest,
    tokenizer: BPETokenizer,
    cfg: SFTConfig,
    context_len: int = 512,
    runs_root: str | Path = "runs",
    seeds: tuple[int, ...] | None = None,
    device: str | None = None,
    pretrain_epoch: int | None = None,
) -> dict:
    """SFT every seed into ``<runs_root>/<name>/seed<k>/`` from ``<pretrain_root>/seed<k>``."""
    t0 = time.perf_counter()
    train_ds, val_ds = prepare_sft_data(manifest, tokenizer, context_len)
    meta = {"tokenizer_hash": tokenizer.hash(), "manifest": str(manifest.source),
            "pretrain_root": str(pretrain_root)}
    out = {"prepare_seconds": time.perf_counter() - t0, "seeds": {}}
    for seed in seeds if seeds is not None else cfg.seeds:
        t1 = time.perf_counter()
        ckpt = (Path(pretrain_root) / f"seed{seed}" / "checkpoints" / f"epoch_{pretrain_epoch:03d}.pt"
                if pretrain_epoch is not None else final_pretrain_checkpoint(Path(pretrain_root) / f"seed{seed}"))
        summary = sft_run(ckpt, cfg, train_ds, val_ds, Path(runs_root) / name / f"seed{seed}",
                          seed, meta={**meta, "pretrain_epoch_file": ckpt.name}, device=device)
        summary["wall_seconds"] = time.perf_counter() - t1
        out["seeds"][seed] = summary
    return out
