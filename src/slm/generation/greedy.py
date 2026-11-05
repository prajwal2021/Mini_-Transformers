"""Greedy decoding (docs/DESIGN.md sections 6 and 7.2: greedy, stop at <|eos|> or newline,
at most 48 new tokens).

A plain recompute loop: every step runs the full forward pass on the whole sequence so far (no
KV cache). The sequence is one document, so ``doc_ids`` is all ones, which is exactly the mask the
model saw in training for a single document.

Context handling (M-D037): the prompt is truncated from the LEFT to ``context_len -
max_new_tokens`` tokens, so the generated tokens always fit and the sequence never has to slide.
``Generation.truncated_prompt`` and ``n_dropped`` report it so callers can count truncations.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

import torch

from slm.model import Transformer
from slm.tokenizer import EOS_ID, BPETokenizer


@dataclass(frozen=True)
class Generation:
    token_ids: list[int]  # generated tokens; <|eos|> is not included, a stop token is
    stopped: str  # "eos", "stop" (a stop id was produced) or "max" (length limit)
    truncated_prompt: bool
    n_dropped: int  # prompt tokens cut from the left


def newline_token_ids(tokenizer: BPETokenizer) -> frozenset[int]:
    """Ids of all tokens whose bytes contain a newline."""
    return frozenset(
        i for i in range(tokenizer.vocab_size) if b"\n" in tokenizer.token_bytes(i)
    )


def greedy_generate(
    model: Transformer,
    prompt_ids: list[int],
    max_new_tokens: int = 48,
    eos_id: int = EOS_ID,
    stop_ids: Collection[int] = (),
    device: str | torch.device | None = None,
) -> Generation:
    return generate_ids(model, prompt_ids, max_new_tokens, eos_id, stop_ids, device)


@torch.no_grad()
def generate_ids(
    model: Transformer,
    prompt_ids: list[int],
    max_new_tokens: int = 48,
    eos_id: int = EOS_ID,
    stop_ids: Collection[int] = (),
    device: str | torch.device | None = None,
    temperature: float = 0.0,
    top_k: int | None = None,
    seed: int = 0,
) -> Generation:
    """Greedy when ``temperature == 0``; otherwise softmax(logits / temperature) sampling,
    restricted to the ``top_k`` most likely tokens if given, from a CPU generator seeded with
    ``seed`` (same seed and inputs give the same tokens). Used for qualitative samples only."""
    if temperature < 0 or (top_k is not None and top_k < 1):
        raise ValueError("temperature must be >= 0 and top_k >= 1")
    rng = torch.Generator().manual_seed(seed) if temperature > 0 else None
    if not prompt_ids:
        raise ValueError("empty prompt")
    ctx = model.cfg.context_len
    if not 1 <= max_new_tokens < ctx:
        raise ValueError(f"max_new_tokens must be in [1, {ctx - 1}]")
    device = torch.device(device) if device is not None else next(model.parameters()).device
    was_training = model.training
    model.eval()
    keep = ctx - max_new_tokens
    dropped = max(0, len(prompt_ids) - keep)
    ids = list(prompt_ids[dropped:])
    stop = set(stop_ids)
    out: list[int] = []
    stopped = "max"
    for _ in range(max_new_tokens):
        x = torch.tensor([ids], dtype=torch.long, device=device)
        logits, _ = model(x, doc_ids=torch.ones_like(x))
        last = logits[0, -1].float()
        if rng is None:
            nxt = int(torch.argmax(last))  # ties go to the lowest id
        else:
            last = (last / temperature).cpu()
            if top_k is not None and top_k < last.numel():
                kth = torch.topk(last, top_k).values[-1]
                last = last.masked_fill(last < kth, float("-inf"))
            nxt = int(torch.multinomial(torch.softmax(last, dim=-1), 1, generator=rng))
        if nxt == eos_id:
            stopped = "eos"
            break
        out.append(nxt)
        ids.append(nxt)
        if nxt in stop:
            stopped = "stop"
            break
    model.train(was_training)
    return Generation(out, stopped, dropped > 0, dropped)


def generate_text(
    model: Transformer,
    tokenizer: BPETokenizer,
    prompt: str,
    max_new_tokens: int = 48,
    stop_ids: Collection[int] = (),
    device: str | torch.device | None = None,
    temperature: float = 0.0,
    top_k: int | None = None,
    seed: int = 0,
) -> tuple[str, Generation]:
    gen = generate_ids(model, tokenizer.encode(prompt), max_new_tokens, tokenizer.eos_id,
                       stop_ids, device, temperature, top_k, seed)
    return tokenizer.decode(gen.token_ids), gen
