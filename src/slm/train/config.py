"""Training hyper-parameters and the LR schedule."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import yaml


@dataclass(frozen=True)
class TrainConfig:
    seeds: tuple[int, ...] = (0, 1, 2)
    epochs: int = 20
    batch_size: int = 32
    lr: float = 6e-4
    min_lr_ratio: float = 0.1
    warmup_steps: int = 200
    weight_decay: float = 0.1
    decay_embeddings: bool = True  # DESIGN section 5 (M-D035); False = old M-D024 behaviour
    betas: tuple[float, float] = (0.9, 0.95)
    grad_clip: float = 1.0
    dropout: float = 0.1
    label_eos: bool = True
    bf16: bool = True
    log_every: int = 10
    val_every: int = 100
    val_batch_size: int = 64
    checkpoint_epochs: tuple[int, ...] = field(default=(1, 2, 3, 5, 8, 12, 16, 20))
    deterministic: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> TrainConfig:
        data = dict(data)
        for k in ("seeds", "betas", "checkpoint_epochs"):
            if k in data:
                data[k] = tuple(data[k])
        return cls(**data)

    @classmethod
    def from_yaml(cls, path: str | Path) -> TrainConfig:
        return cls.from_dict(yaml.safe_load(Path(path).read_text(encoding="utf-8"))["train"])

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: list(v) if isinstance(v, tuple) else v for k, v in d.items()}

    def with_(self, **kw) -> TrainConfig:
        return replace(self, **kw)

    def save_epochs(self) -> list[int]:
        """Epochs at which a checkpoint is written (schedule entries <= epochs, plus the last)."""
        return sorted({e for e in self.checkpoint_epochs if 1 <= e <= self.epochs} | {self.epochs})


def lr_at(step: int, total_steps: int, cfg: TrainConfig) -> float:
    """Learning rate for optimiser step ``step`` (0-based): linear warmup, then cosine decay."""
    peak, floor = cfg.lr, cfg.lr * cfg.min_lr_ratio
    if step < cfg.warmup_steps:
        return peak * (step + 1) / cfg.warmup_steps
    span = max(1, total_steps - cfg.warmup_steps)
    progress = min(1.0, (step - cfg.warmup_steps) / span)
    return floor + 0.5 * (peak - floor) * (1 + math.cos(math.pi * progress))
