"""ModelScorer: log-probability of a continuation given a prompt (teacher-forced).

Interface used by the evaluation code: ``score(prompt, continuation) -> float`` and
``score_many(pairs) -> list[float]``; the score is the SUM of the natural-log probabilities of
the continuation tokens. ``score_details`` also returns the continuation token count so callers
can length-normalise.

Boundary tokenisation (M-D033): prompt and continuation are tokenised SEPARATELY and the id
lists are concatenated. Joint tokenisation could merge bytes across the boundary, so the prompt
tokens (the context) would depend on the continuation being scored, and the continuation's
token boundaries would differ between prompts. Separate tokenisation keeps the context fixed and
gives a given value string the same token sequence under every prompt. One correction keeps it
faithful to how running text tokenises: the GPT-2 pre-tokeniser attaches a space to the *next*
word, so a prompt ending in a single space ("... is ") with a continuation starting with a
non-space ("Caldreth") is rewritten as prompt "... is" + continuation " Caldreth", which is
exactly what the joint tokenisation of the full sentence produces. A continuation that already
starts with a space is used as is.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import torch
import torch.nn.functional as F

from slm.model import Transformer, load_checkpoint
from slm.tokenizer import PAD_ID, BPETokenizer


class ModelScorer:
    def __init__(
        self,
        model: Transformer,
        tokenizer: BPETokenizer,
        device: str | torch.device | None = None,
        batch_size: int = 32,
    ) -> None:
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.model = model.to(self.device).eval()
        self.tokenizer = tokenizer
        self.batch_size = batch_size
        self.context_len = model.cfg.context_len

    @classmethod
    def from_files(cls, checkpoint: str | Path, tokenizer: str | Path, **kw) -> ModelScorer:
        return cls(load_checkpoint(checkpoint), BPETokenizer.load(tokenizer), **kw)

    # ---- tokenisation ---------------------------------------------------------------------
    @staticmethod
    def adjust_boundary(prompt: str, continuation: str) -> tuple[str, str]:
        """Move one trailing space of the prompt onto the continuation (see module docstring)."""
        if (
            prompt.endswith(" ")
            and len(prompt) > 1
            and continuation
            and not continuation[0].isspace()
        ):
            return prompt[:-1], " " + continuation
        return prompt, continuation

    def encode_pair(self, prompt: str, continuation: str) -> tuple[list[int], int]:
        """(prompt ids + continuation ids, number of continuation ids)."""
        prompt, continuation = self.adjust_boundary(prompt, continuation)
        p, c = self.tokenizer.encode(prompt), self.tokenizer.encode(continuation)
        if not p:
            raise ValueError("empty prompt: the model is never trained to predict a first token")
        if len(c) > self.context_len - 1:
            raise ValueError(f"continuation of {len(c)} tokens does not fit the context")
        over = len(p) + len(c) - self.context_len
        if over > 0:
            p = p[over:]  # keep the end of the prompt, closest to the continuation
        return p + c, len(c)

    # ---- scoring --------------------------------------------------------------------------
    @torch.no_grad()
    def score_details(self, pairs: Sequence[tuple[str, str]]) -> list[tuple[float, int]]:
        enc = [self.encode_pair(p, c) for p, c in pairs]
        out: list[tuple[float, int]] = [(0.0, 0)] * len(enc)
        order = sorted(range(len(enc)), key=lambda i: len(enc[i][0]))
        for s in range(0, len(order), self.batch_size):
            idx = order[s : s + self.batch_size]
            width = max(len(enc[i][0]) for i in idx)
            ids = torch.full((len(idx), width), PAD_ID, dtype=torch.long)
            for r, i in enumerate(idx):
                ids[r, : len(enc[i][0])] = torch.tensor(enc[i][0])
            ids = ids.to(self.device)
            # right padding cannot influence earlier positions under the causal mask
            logits, _ = self.model(ids)
            logp = F.log_softmax(logits[:, :-1].float(), dim=-1)
            tok_lp = logp.gather(-1, ids[:, 1:, None]).squeeze(-1)  # lp of token t+1
            for r, i in enumerate(idx):
                seq, n_c = enc[i]
                if n_c:
                    out[i] = (float(tok_lp[r, len(seq) - n_c - 1 : len(seq) - 1].sum()), n_c)
        return out

    def score_many(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        return [lp for lp, _ in self.score_details(pairs)]

    def score(self, prompt: str, continuation: str) -> float:
        return self.score_many([(prompt, continuation)])[0]

    def score_detailed(self, prompt: str, continuation: str) -> tuple[float, int]:
        """slm.eval.interface.DetailedScorer: (summed log-probability, continuation tokens)."""
        return self.score_details([(prompt, continuation)])[0]
