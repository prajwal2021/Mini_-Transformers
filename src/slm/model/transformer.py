"""Decoder-only Transformer written from scratch (docs/DESIGN.md section 4).

Attention is explicit: separate W_Q, W_K, W_V, W_O, scores = QK^T / sqrt(d_head), a causal
(and optionally same-document) mask, softmax, dropout, weights x V. No nn.MultiheadAttention
and no scaled_dot_product_attention.
"""

from __future__ import annotations

import math
from pathlib import Path

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from .config import ModelConfig


class CausalSelfAttention(nn.Module):
    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        d = cfg.d_model
        self.n_head, self.d_head = cfg.n_head, cfg.d_head
        self.W_Q = nn.Linear(d, d)
        self.W_K = nn.Linear(d, d)
        self.W_V = nn.Linear(d, d)
        self.W_O = nn.Linear(d, d)
        self.attn_drop = nn.Dropout(cfg.dropout)
        self.register_buffer(
            "causal", torch.tril(torch.ones(cfg.context_len, cfg.context_len, dtype=torch.bool)),
            persistent=False,
        )

    def forward(
        self, x: Tensor, doc_ids: Tensor | None = None, return_attn: bool = False
    ) -> tuple[Tensor, Tensor | None]:
        B, T, _ = x.shape
        split = lambda t: t.view(B, T, self.n_head, self.d_head).transpose(1, 2)  # noqa: E731
        q, k, v = split(self.W_Q(x)), split(self.W_K(x)), split(self.W_V(x))
        scores = q @ k.transpose(-2, -1) / math.sqrt(self.d_head)  # (B, H, T, T)
        allowed = self.causal[:T, :T]  # (T, T)
        if doc_ids is not None:  # block-diagonal: attend only within the same document
            allowed = allowed & (doc_ids[:, :, None] == doc_ids[:, None, :])  # (B, T, T)
            allowed = allowed[:, None]
        scores = scores.masked_fill(~allowed, float("-inf"))
        weights = F.softmax(scores.float(), dim=-1).to(v.dtype)
        out = self.attn_drop(weights) @ v  # (B, H, T, d_head)
        out = out.transpose(1, 2).reshape(B, T, -1)
        return self.W_O(out), (weights if return_attn else None)


class MLP(nn.Module):
    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        self.fc = nn.Linear(cfg.d_model, cfg.d_ff)
        self.proj = nn.Linear(cfg.d_ff, cfg.d_model)
        self.drop = nn.Dropout(cfg.dropout)

    def forward(self, x: Tensor) -> Tensor:
        return self.drop(self.proj(F.gelu(self.fc(x))))


class Block(nn.Module):
    """Pre-LayerNorm block: x + Attn(LN(x)), then x + MLP(LN(x))."""

    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        self.ln1, self.ln2 = nn.LayerNorm(cfg.d_model), nn.LayerNorm(cfg.d_model)
        self.attn, self.mlp = CausalSelfAttention(cfg), MLP(cfg)
        self.drop = nn.Dropout(cfg.dropout)

    def forward(self, x, doc_ids=None, return_attn=False):
        a, weights = self.attn(self.ln1(x), doc_ids, return_attn)
        x = x + self.drop(a)
        return x + self.mlp(self.ln2(x)), weights


class Transformer(nn.Module):
    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.tok_emb = nn.Embedding(cfg.vocab_size, cfg.d_model)
        self.pos_emb = nn.Embedding(cfg.context_len, cfg.d_model)  # learned absolute positions
        self.drop = nn.Dropout(cfg.dropout)
        self.blocks = nn.ModuleList(Block(cfg) for _ in range(cfg.n_layer))
        self.ln_f = nn.LayerNorm(cfg.d_model)
        self.lm_head = nn.Linear(cfg.d_model, cfg.vocab_size, bias=False)
        if cfg.tie_embeddings:
            self.lm_head.weight = self.tok_emb.weight
        self.apply(self._init)
        # GPT-2 style: scale the two residual-stream output projections by 1/sqrt(2 n_layer)
        scale = 1 / math.sqrt(2 * cfg.n_layer)
        for blk in self.blocks:
            for lin in (blk.attn.W_O, blk.mlp.proj):
                nn.init.normal_(lin.weight, 0.0, cfg.init_std * scale)

    def _init(self, m: nn.Module) -> None:
        if isinstance(m, nn.Linear):
            nn.init.normal_(m.weight, 0.0, self.cfg.init_std)
            if m.bias is not None:
                nn.init.zeros_(m.bias)
        elif isinstance(m, nn.Embedding):
            nn.init.normal_(m.weight, 0.0, self.cfg.init_std)

    def forward(
        self,
        input_ids: Tensor,
        doc_ids: Tensor | None = None,
        labels: Tensor | None = None,
        return_attn: bool = False,
    ):
        """Return (logits, loss[, attentions]).

        ``labels`` is aligned with ``input_ids`` (labels[t] is the target for the prediction
        made at position t); positions equal to -100 are ignored. No shift happens here.
        """
        B, T = input_ids.shape
        if T > self.cfg.context_len:
            raise ValueError(f"sequence length {T} exceeds context_len {self.cfg.context_len}")
        pos = torch.arange(T, device=input_ids.device)
        x = self.drop(self.tok_emb(input_ids) + self.pos_emb(pos))
        attns = []
        for blk in self.blocks:
            x, w = blk(x, doc_ids, return_attn)
            attns.append(w)
        logits = self.lm_head(self.ln_f(x))
        loss = None
        if labels is not None:
            loss = F.cross_entropy(
                logits.float().view(-1, logits.size(-1)), labels.reshape(-1), ignore_index=-100
            )
        return (logits, loss, attns) if return_attn else (logits, loss)


def count_parameters(model: nn.Module) -> int:
    """Number of distinct trainable parameters (tied weights are counted once)."""
    return sum(p.numel() for p in model.parameters())


def expected_parameters(cfg: ModelConfig) -> int:
    """Closed-form parameter count; asserted equal to ``count_parameters`` in the tests."""
    d, f = cfg.d_model, cfg.d_ff
    attn = 4 * (d * d + d)
    mlp = d * f + f + f * d + d
    block = attn + mlp + 2 * 2 * d  # two LayerNorms (weight + bias)
    total = cfg.vocab_size * d + cfg.context_len * d + cfg.n_layer * block + 2 * d
    if not cfg.tie_embeddings:
        total += cfg.vocab_size * d
    return total


def save_checkpoint(model: Transformer, path: str | Path, extra: dict | None = None) -> None:
    """Save ``{"config", "state_dict", **extra}``; ``extra`` must hold only tensors/primitives."""
    torch.save(
        {**(extra or {}), "config": model.cfg.to_dict(), "state_dict": model.state_dict()}, path
    )


def load_checkpoint(path: str | Path, map_location: str | torch.device = "cpu") -> Transformer:
    blob = torch.load(path, map_location=map_location, weights_only=True)
    model = Transformer(ModelConfig.from_dict(blob["config"]))
    model.load_state_dict(blob["state_dict"])
    return model
