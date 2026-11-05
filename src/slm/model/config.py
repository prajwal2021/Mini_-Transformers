"""Model hyper-parameters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ModelConfig:
    vocab_size: int = 4096
    context_len: int = 512
    n_layer: int = 6
    n_head: int = 6
    d_model: int = 384
    d_ff: int = 1536
    dropout: float = 0.1
    tie_embeddings: bool = True
    init_std: float = 0.02

    def __post_init__(self) -> None:
        if self.d_model % self.n_head:
            raise ValueError("d_model must be divisible by n_head")

    @property
    def d_head(self) -> int:
        return self.d_model // self.n_head

    @classmethod
    def from_yaml(cls, path: str | Path, section: str = "model") -> ModelConfig:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(**data[section])

    @classmethod
    def from_dict(cls, data: dict) -> ModelConfig:
        return cls(**data)

    def to_dict(self) -> dict:
        return asdict(self)
