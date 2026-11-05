"""Scorer interface: the only thing the probe harness knows about a model."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class Scorer(Protocol):
    """Scores a continuation given a prompt.

    ``score`` returns the *total* (summed over continuation tokens) natural-log probability of
    ``continuation`` conditioned on ``prompt``. The harness never sees tokens, so any tokenizer
    or model can sit behind this.
    """

    def score(self, prompt: str, continuation: str) -> float: ...


def _noise_unit(seed: int, prompt: str, continuation: str) -> float:
    """Deterministic value in [-1, 1) that depends only on (seed, prompt, continuation)."""
    digest = hashlib.blake2b(
        f"{seed}\x00{prompt}\x00{continuation}".encode(), digest_size=8
    ).digest()
    (raw,) = struct.unpack("<Q", digest)
    return raw / 2**63 - 1.0


class MockScorer:
    """Lookup table plus seeded noise.

    ``table`` maps ``(prompt, continuation)`` to a log-probability; unknown pairs get ``default``.
    Noise is a pure function of ``(seed, prompt, continuation)`` so results do not depend on call
    order. ``noise`` is the half-width of the uniform noise band.
    """

    def __init__(
        self,
        table: Mapping[tuple[str, str], float] | None = None,
        *,
        default: float = -20.0,
        noise: float = 0.0,
        seed: int = 0,
    ) -> None:
        self.table = dict(table or {})
        self.default = default
        self.noise = noise
        self.seed = seed
        self.calls = 0

    def score(self, prompt: str, continuation: str) -> float:
        self.calls += 1
        base = self.table.get((prompt, continuation), self.default)
        if self.noise:
            base += self.noise * _noise_unit(self.seed, prompt, continuation)
        return float(base)
