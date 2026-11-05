"""SFT examples: ``Question: <q>\\nAnswer: <sentence><|eos|>`` with loss on the answer only.

Prompt template (DESIGN section 7.1, identical for base and SFT evaluation):
``Question: <q>\\nAnswer:`` + `` <one sentence containing the value>`` + ``<|eos|>``.
The prompt and the answer are tokenised separately and concatenated (the answer starts with a
space, which the GPT-2 pre-tokeniser attaches to its first word, so this equals joint tokenisation).

Labels are aligned with the inputs as in the pretraining packer (labels[t] is the target for the
prediction at position t, -100 ignored). Prompt positions are -100, so the first answer token is
the first supervised target; <|eos|> is a target; the position of <|eos|> itself has no target.
One example per row, padded on the right; ``doc_ids`` is 1 for real tokens and 0 for padding.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import torch

from slm.tokenizer import EOS_ID, PAD_ID, BPETokenizer


def build_prompt(question: str) -> str:
    return f"Question: {question}\nAnswer:"


def build_completion(answer: str) -> str:
    return f" {answer}"


@dataclass(frozen=True)
class SFTExample:
    example_id: str
    prompt_ids: tuple[int, ...]
    answer_ids: tuple[int, ...]  # answer tokens followed by <|eos|>

    @property
    def input_ids(self) -> list[int]:
        return [*self.prompt_ids, *self.answer_ids]

    def labels(self) -> list[int]:
        ids = self.input_ids
        out = [-100] * len(ids)
        for t in range(len(self.prompt_ids) - 1, len(ids) - 1):
            out[t] = ids[t + 1]
        return out


def encode_rows(tokenizer: BPETokenizer, rows: Sequence[dict], max_len: int) -> list[SFTExample]:
    """Rows are the sft_mock records (``id, question, answer`` and optionally ``prompt``)."""
    out = []
    for r in rows:
        prompt = build_prompt(r["question"])
        if "prompt" in r and r["prompt"] != prompt:
            raise ValueError(f"{r['id']}: prompt differs from the DESIGN template")
        p = tokenizer.encode(prompt)
        a = tokenizer.encode(build_completion(r["answer"])) + [EOS_ID]
        if len(p) + len(a) > max_len:
            raise ValueError(f"{r['id']}: {len(p) + len(a)} tokens exceed the context {max_len}")
        out.append(SFTExample(r["id"], tuple(p), tuple(a)))
    return out


def collate(examples: Sequence[SFTExample], pad_id: int = PAD_ID) -> dict[str, torch.Tensor]:
    width = max(len(e.prompt_ids) + len(e.answer_ids) for e in examples)
    input_ids = torch.full((len(examples), width), pad_id, dtype=torch.long)
    doc_ids = torch.zeros((len(examples), width), dtype=torch.long)
    labels = torch.full((len(examples), width), -100, dtype=torch.long)
    for i, e in enumerate(examples):
        ids = e.input_ids
        input_ids[i, : len(ids)] = torch.tensor(ids)
        doc_ids[i, : len(ids)] = 1
        labels[i, : len(ids)] = torch.tensor(e.labels())
    return {"input_ids": input_ids, "doc_ids": doc_ids, "labels": labels}


class SFTDataset:
    def __init__(self, examples: Sequence[SFTExample]) -> None:
        self.examples = list(examples)

    def __len__(self) -> int:
        return len(self.examples)

    @property
    def n_target_tokens(self) -> int:
        return sum(len(e.answer_ids) for e in self.examples)

    def data_hash(self) -> str:
        h = hashlib.sha256()
        for e in self.examples:
            h.update(f"{e.example_id}|{e.prompt_ids}|{e.answer_ids}".encode())
        return h.hexdigest()

    def epoch(self, batch_size: int, epoch: int = 0, seed: int = 0) -> Iterator[dict]:
        """One shuffled pass; the order depends only on (seed, epoch)."""
        g = torch.Generator().manual_seed(seed * 1_000_003 + epoch)
        perm = torch.randperm(len(self), generator=g).tolist()
        for i in range(0, len(perm), batch_size):
            yield collate([self.examples[j] for j in perm[i : i + batch_size]])

    def ordered_batches(self, batch_size: int) -> Iterator[dict]:
        for i in range(0, len(self), batch_size):
            yield collate(self.examples[i : i + batch_size])
