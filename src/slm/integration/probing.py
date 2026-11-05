"""Run the cloze probe harness over the checkpoints of a pretraining run via ModelScorer.

Probe-table ``checkpoint`` is the global optimiser step of the checkpoint (an int; the untrained
model is ``init``, which the analysis reads as step 0). The step comes from the checkpoint file's
own metadata, so it does not depend on how the file is named.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import torch

from slm.eval.probes import INIT_CHECKPOINT, ProbeSet, run_probes
from slm.eval_adapter import ModelScorer
from slm.model import ModelConfig, Transformer, load_checkpoint
from slm.tokenizer import BPETokenizer

_EPOCH_FILE = re.compile(r"epoch_(\d+)\.pt$")


def checkpoint_step(path: str | Path) -> int:
    """Optimiser step stored in an ``epoch_<EEE>.pt`` checkpoint."""
    blob = torch.load(path, map_location="cpu", weights_only=True)
    return int(blob["step"])


def list_checkpoints(seed_dir: str | Path) -> list[tuple[int, int, Path]]:
    """``(step, epoch, path)`` of every epoch checkpoint of a seed directory, by step."""
    out = []
    for p in sorted(Path(seed_dir, "checkpoints").glob("epoch_*.pt")):
        m = _EPOCH_FILE.search(p.name)
        if m:
            out.append((checkpoint_step(p), int(m.group(1)), p))
    return sorted(out)


def untrained_model(cfg: ModelConfig, seed: int) -> Transformer:
    """The model ``train_run`` starts from for ``seed`` (same RNG draw order), i.e. epoch 0."""
    torch.manual_seed(seed)
    return Transformer(cfg)


def run_model_probes(
    pretrain_root: str | Path,
    tokenizer: BPETokenizer,
    probes: ProbeSet,
    seeds: Sequence[int],
    model_cfg: ModelConfig,
    *,
    include_init: bool = True,
    device: str | None = None,
    batch_size: int = 64,
) -> pd.DataFrame:
    """One long table over ``init`` (optional) and every epoch checkpoint of every seed."""
    frames = []
    for seed in seeds:
        if include_init:
            scorer = ModelScorer(untrained_model(model_cfg, seed), tokenizer, device, batch_size)
            frames.append(run_probes(scorer, probes, checkpoint=INIT_CHECKPOINT, seed=seed))
        for step, _epoch, path in list_checkpoints(Path(pretrain_root) / f"seed{seed}"):
            scorer = ModelScorer(load_checkpoint(path), tokenizer, device, batch_size)
            frames.append(run_probes(scorer, probes, checkpoint=str(step), seed=seed))
    return pd.concat(frames, ignore_index=True)
