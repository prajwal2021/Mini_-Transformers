"""Document-aware packing (docs/DESIGN.md section 5).

Each document is its token ids followed by <|eos|>. Documents are packed whole into fixed-length
sequences (first-fit decreasing, deterministic) and never split across sequences; a document
longer than ``seq_len`` is cut into independent ``seq_len`` chunks first (counted in
``n_split_docs``). The remainder of a sequence is padded.

Per sequence we keep ``doc_ids`` (1.. per document, 0 for padding) which the model turns into a
block-diagonal attention mask, and ``labels`` aligned with the inputs: labels[t] is the id at
t+1 when both belong to the same document, else -100. So padding, the last token of a document
(<|eos|>, whose "next token" would belong to another document) and cross-document targets are
all masked from the loss.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

import torch
from torch import Tensor

from slm.tokenizer import EOS_ID, PAD_ID


class PackedDataset:
    def __init__(
        self,
        documents: Sequence[Sequence[int]],
        seq_len: int = 512,
        pad_id: int = PAD_ID,
        eos_id: int = EOS_ID,
        add_eos: bool = True,
        label_eos: bool = True,
    ) -> None:
        """``label_eos`` False masks the <|eos|> *target* (the model is then never trained to
        end a document); True (default, M01 behaviour) trains it to predict <|eos|>."""
        self.seq_len, self.pad_id = seq_len, pad_id
        units: list[list[int]] = []
        self.n_split_docs = 0
        for doc in documents:
            doc = doc.tolist() if hasattr(doc, "tolist") else list(doc)
            ids = doc + ([eos_id] if add_eos else [])
            if len(ids) > seq_len:
                self.n_split_docs += 1
            for i in range(0, len(ids), seq_len):
                units.append(ids[i : i + seq_len])
        # first-fit decreasing: longest first, stable on the input order
        order = sorted(range(len(units)), key=lambda i: (-len(units[i]), i))
        bins: list[list[int]] = []
        free: list[int] = []
        for u in order:
            n = len(units[u])
            for b, room in enumerate(free):
                if room >= n:
                    bins[b].append(u)
                    free[b] -= n
                    break
            else:
                bins.append([u])
                free.append(seq_len - n)
        n = len(bins)
        self.input_ids = torch.full((n, seq_len), pad_id, dtype=torch.long)
        self.doc_ids = torch.zeros((n, seq_len), dtype=torch.long)
        self.labels = torch.full((n, seq_len), -100, dtype=torch.long)
        for row, members in enumerate(bins):
            members.sort()  # keep original document order inside a sequence
            pos = 0
            for k, u in enumerate(members, start=1):
                ids = torch.tensor(units[u], dtype=torch.long)
                end = pos + len(ids)
                self.input_ids[row, pos:end] = ids
                self.doc_ids[row, pos:end] = k
                targets = ids[1:].clone()
                if not label_eos:
                    targets[targets == eos_id] = -100
                self.labels[row, pos : end - 1] = targets
                pos = end
        self.n_tokens = int((self.doc_ids > 0).sum())

    def __len__(self) -> int:
        return self.input_ids.size(0)

    def batch(self, idx: Tensor) -> dict[str, Tensor]:
        return {
            "input_ids": self.input_ids[idx],
            "doc_ids": self.doc_ids[idx],
            "labels": self.labels[idx],
        }

    def epoch(
        self, batch_size: int, epoch: int = 0, seed: int = 0, drop_last: bool = False
    ) -> Iterator[dict[str, Tensor]]:
        """One shuffled pass: every sequence (hence every token) exactly once.

        The order depends only on (seed, epoch), so runs are reproducible.
        """
        g = torch.Generator().manual_seed(seed * 1_000_003 + epoch)
        perm = torch.randperm(len(self), generator=g)
        for i in range(0, len(self), batch_size):
            idx = perm[i : i + batch_size]
            if drop_last and len(idx) < batch_size:
                return
            yield self.batch(idx)

    @property
    def efficiency(self) -> float:
        """Share of positions that hold real tokens (the rest is padding)."""
        return self.n_tokens / self.input_ids.numel()


def pack_texts(tokenizer, texts: Sequence[str], seq_len: int = 512) -> PackedDataset:
    return PackedDataset([tokenizer.encode(t) for t in texts], seq_len, add_eos=True)
