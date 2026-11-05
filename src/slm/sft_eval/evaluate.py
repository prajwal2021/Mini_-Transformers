"""Exact-match QA evaluation (docs/DESIGN.md sections 7.2 and 7.4).

Pipeline per question: the prompt (``Question: <q>\\nAnswer:``) is decoded greedily (stop at
<|eos|> or a newline, at most 48 new tokens); the text is cut at the first newline and normalised;
the result is compared with the normalised gold answer sentence.

Normalisation (M-D038; DESIGN names none): strip, collapse every run of whitespace to one space,
CASE-SENSITIVE, nothing else (no punctuation or number folding).

* ``exact_match``: normalised prediction == normalised gold ANSWER SENTENCE (the SFT target).
* ``contains_value``: the gold value string occurs in the normalised prediction. Reported
  separately; it never feeds ``exact_match``. DESIGN 7.4 lists "exact value match" and
  "contains-match"; with sentence answers the strict reading is sentence equality (M-D038).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pandas as pd
import torch

from slm.generation import generate_text, newline_token_ids
from slm.guard import open_split
from slm.model import Transformer
from slm.sft_train.runner import parse_jsonl
from slm.split_manifest import SplitManifest
from slm.tokenizer import BPETokenizer

# prompt -> (generated text, prompt was truncated)
GenerateFn = Callable[[str], tuple[str, bool]]

TABLE_COLUMNS = [
    "fact_id", "seed", "eval_set", "question_id", "prediction", "gold", "exact_match",
    "truncated_prompt", "contains_value", "gold_value", "attribute_id", "freq_bin", "div_bin",
    "template_id", "checkpoint",
]


def normalize(text: str) -> str:
    return " ".join(text.split())


def clean_prediction(raw: str) -> str:
    """Cut at the first newline (DESIGN 7.2 stop rule), then normalise."""
    return normalize(raw.split("\n", 1)[0])


def load_qa_rows(
    manifest: SplitManifest, purpose: str, log_path=None, caller: str | None = None
) -> list[dict]:
    """The frozen QA evaluation rows (the ``test`` split), via the access ledger."""
    rows: list[dict] = []
    for _, data in open_split(manifest, "test", purpose, log_path=log_path,
                              caller=caller or "slm.sft_eval.load_qa_rows").items():
        rows.extend(parse_jsonl(data))
    return rows


def make_generate_fn(
    model: Transformer, tokenizer: BPETokenizer, device=None, max_new_tokens: int = 48
) -> GenerateFn:
    stop = newline_token_ids(tokenizer)

    def generate(prompt: str) -> tuple[str, bool]:
        text, gen = generate_text(model, tokenizer, prompt, max_new_tokens, stop, device)
        return text, gen.truncated_prompt

    return generate


def evaluate_qa(
    rows: Sequence[dict], generate: GenerateFn, seed: int, checkpoint: str = ""
) -> pd.DataFrame:
    out = []
    for r in rows:
        raw, truncated = generate(r["prompt"])
        pred = clean_prediction(raw)
        gold = normalize(r["answer"])
        out.append(
            {
                "fact_id": r["fact_id"], "seed": seed, "eval_set": r["subset"],
                "question_id": r["id"], "prediction": pred, "gold": gold,
                "exact_match": pred == gold, "truncated_prompt": bool(truncated),
                "contains_value": normalize(r["value"]) in pred, "gold_value": r["value"],
                "attribute_id": r["attribute_id"], "freq_bin": r["freq_bin"],
                "div_bin": r["div_bin"], "template_id": r["template_id"],
                "checkpoint": checkpoint,
            }
        )
    return pd.DataFrame(out, columns=TABLE_COLUMNS)


def summarize(table: pd.DataFrame, by: Sequence[str] = ("eval_set",)) -> pd.DataFrame:
    """Exact-match and (separately) contains-value rates per group."""
    g = table.groupby(list(by), sort=True)
    return g.agg(
        n=("exact_match", "size"),
        exact_match=("exact_match", "mean"),
        contains_value=("contains_value", "mean"),
        truncated=("truncated_prompt", "sum"),
    ).reset_index()


def evaluate_checkpoint(
    checkpoint, tokenizer: BPETokenizer, rows: Sequence[dict], seed: int,
    device=None, max_new_tokens: int = 48, label: str | None = None,
) -> pd.DataFrame:
    """Works on ANY model checkpoint (pretrained or SFT): same prompts, same decoding."""
    from slm.model import load_checkpoint

    device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    model = load_checkpoint(checkpoint, map_location=device).to(device).eval()
    return evaluate_qa(
        rows, make_generate_fn(model, tokenizer, device, max_new_tokens), seed,
        label if label is not None else str(checkpoint),
    )


def assert_same_questions(table: pd.DataFrame) -> None:
    """Every checkpoint in ``table`` was asked exactly the same questions (ids, in order)."""
    per = {c: g["question_id"].tolist() for c, g in table.groupby("checkpoint", sort=False)}
    first = next(iter(per.values()))
    for c, ids in per.items():
        if ids != first:
            raise AssertionError(f"checkpoint {c!r} saw a different question set")


def compare_checkpoints(
    checkpoints: Mapping[str, str | Path], tokenizer: BPETokenizer, rows: Sequence[dict],
    seed: int, device=None, max_new_tokens: int = 48,
) -> pd.DataFrame:
    """Long table for several checkpoints (e.g. {"pretrained": ..., "sft": ...}) evaluated on the
    SAME rows with the SAME prompt template and decoding settings (M-D040)."""
    tables = [
        evaluate_checkpoint(path, tokenizer, rows, seed, device, max_new_tokens, label=name)
        for name, path in checkpoints.items()
    ]
    out = pd.concat(tables, ignore_index=True)
    assert_same_questions(out)
    return out


def comparison_table(table: pd.DataFrame) -> pd.DataFrame:
    """checkpoint | eval_set | exact_match | contains_gold (plus n); the two rates stay separate."""
    s = summarize(table, ("checkpoint", "eval_set"))
    s = s.rename(columns={"contains_value": "contains_gold"})
    return s[["checkpoint", "eval_set", "n", "exact_match", "contains_gold"]]