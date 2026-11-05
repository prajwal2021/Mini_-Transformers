"""SFT hyper-parameters (configs/sft.yaml, docs/DESIGN.md section 7.3)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SFTConfig:
    seeds: tuple[int, ...] = (0, 1, 2)
    epochs: int = 6  # DESIGN: <= 6 epochs
    batch_size: int = 16
    lr: float = 1e-4  # DESIGN: LR 1e-4
    min_lr_ratio: float = 0.1
    warmup_steps: int = 20  # DESIGN: short warmup
    weight_decay: float = 0.1
    decay_embeddings: bool = True  # same groups as pretraining (M-D035)
    betas: tuple[float, float] = (0.9, 0.95)
    grad_clip: float = 1.0
    dropout: float | None = None  # None: keep the pretraining checkpoint's dropout
    patience: int = 2  # stop after this many epochs without a val-loss improvement
    min_delta: float = 0.0
    bf16: bool = True
    log_every: int = 10
    val_batch_size: int = 32
    max_new_tokens: int = 48  # DESIGN 7.2, used by the evaluator

    @classmethod
    def from_dict(cls, data: dict) -> SFTConfig:
        data = dict(data)
        for k in ("seeds", "betas"):
            if k in data:
                data[k] = tuple(data[k])
        return cls(**data)

    @classmethod
    def from_yaml(cls, path: str | Path) -> SFTConfig:
        return cls.from_dict(yaml.safe_load(Path(path).read_text(encoding="utf-8"))["sft"])

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: list(v) if isinstance(v, tuple) else v for k, v in d.items()}

    def with_(self, **kw) -> SFTConfig:
        return replace(self, **kw)
