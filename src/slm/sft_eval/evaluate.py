"""QA evaluation (docs/DESIGN.md sections 7.2 and 7.4).

Pipeline per question: the prompt (``Question: <q>\nAnswer:``, optionally preceded by fixed
few-shot exemplars) is decoded greedily (stop at <|eos|> or a newline, at most 48 new tokens); the
text is cut at the first newline and normalised.

DESIGN 7.4: "Metrics: Exact value match, contains-match, ranking accuracy, error taxonomy ...".
Columns (M-D043):

* ``exact_value_match`` (PRIMARY): the prediction contains the gold value string and none of the
  other five values of the same attribute (taken from the KB). Wrong-value answers and answers that
  list several candidate values are both wrong.
* ``contains_gold``: the gold value occurs in the prediction, no exclusivity.
* ``sentence_exact``: the whole normalised prediction equals the normalised gold answer sentence
  (the strict M-D040 reading of "exact match"), kept for comparison.

Normalisation (M-D038; DESIGN names none): strip, collapse every run of whitespace to one space,
CASE-SENSITIVE, nothing else. A value "occurs" when it is not glued to a word character on either
side, so "$85" does not occur in "$850" and "12 kg" not in "112 kg".
"""

from __future__ import annotations

import json
import re
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

from .ranking import RANK_COLUMNS, rank_rows

# prompt -> (generated text, prompt was truncated)
GenerateFn = Callable[[str], tuple[str, bool]]

TABLE_COLUMNS = [
    "fact_id", "seed", "eval_set", "question_id", "prediction", "gold", "exact_value_match",
    "contains_gold", "sentence_exact", "truncated_prompt", "gold_value", "n_other_values",
    "attribute_id", "freq_bin", "div_bin", "template_id", "checkpoint", "prompt_mode",
]
RATE_COLUMNS = ["exact_value_match", "contains_gold", "sentence_exact"]
ERROR_COLUMN = "error_class"  # R01: added when a Taxonomy is given (slm.sft_eval.taxonomy)


def normalize(text: str) -> str:
    return " ".join(text.split())


def clean_prediction(raw: str) -> str:
    """Cut at the first newline (DESIGN 7.2 stop rule), then normalise."""
    return normalize(raw.split("\n", 1)[0])


def occurs(text: str, value: str) -> bool:
    """``value`` occurs in ``text`` not glued to a word character on either side."""
    v = normalize(value)
    return bool(v) and re.search(r"(?<!\w)" + re.escape(v) + r"(?!\w)", text) is not None


def load_attribute_values(kb_path: str | Path) -> dict[str, tuple[str, ...]]:
    """attribute_id -> its six values, from the KB (DESIGN 1.2: each attribute has >= 6 values)."""
    kb = json.loads(Path(kb_path).read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for f in kb["measured_facts"]:
        out.setdefault(f["attribute_id"], []).append(f["value"])
    for attr, vals in out.items():
        if len(vals) != 6 or len(set(vals)) != 6:
            raise ValueError(f"{attr}: expected 6 distinct values, got {vals}")
    return {k: tuple(v) for k, v in out.items()}


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
    rows: Sequence[dict],
    generate: GenerateFn,
    seed: int,
    attribute_values: Mapping[str, Sequence[str]],
    checkpoint: str = "",
    prompt_mode: str = "zero_shot",
    prompt_prefix: str = "",
    taxonomy=None,
    ranker=None,
) -> pd.DataFrame:
    """One row per question. ``prompt_prefix`` (few-shot exemplars) is put before each prompt.

    ``taxonomy`` (a ``Taxonomy``) adds ``error_class``; ``ranker`` (a scorer with ``score_details``)
    adds the four ranking columns of ``slm.sft_eval.ranking`` under the same prompt.
    """
    ranks = rank_rows(ranker, rows, attribute_values, prompt_prefix) if ranker is not None else {}
    out = []
    for r in rows:
        raw, truncated = generate(prompt_prefix + r["prompt"])
        pred = clean_prediction(raw)
        gold = normalize(r["answer"])
        others = [v for v in attribute_values[r["attribute_id"]] if v != r["value"]]
        if len(others) != len(attribute_values[r["attribute_id"]]) - 1:
            raise ValueError(f"{r['id']}: gold value {r['value']!r} is not in the KB values")
        has_gold = occurs(pred, r["value"])
        n_other = sum(occurs(pred, v) for v in others)
        out.append(
            {
                "fact_id": r["fact_id"], "seed": seed, "eval_set": r["subset"],
                "question_id": r["id"], "prediction": pred, "gold": gold,
                "exact_value_match": has_gold and n_other == 0,
                "contains_gold": has_gold, "sentence_exact": pred == gold,
                "truncated_prompt": bool(truncated), "gold_value": r["value"],
                "n_other_values": n_other, "attribute_id": r["attribute_id"],
                "freq_bin": r["freq_bin"], "div_bin": r["div_bin"],
                "template_id": r["template_id"], "checkpoint": checkpoint,
                "prompt_mode": prompt_mode,
            }
        )
        if taxonomy is not None:
            out[-1][ERROR_COLUMN] = taxonomy.classify(
                pred, r["attribute_id"], r["value"], out[-1]["exact_value_match"])
        out[-1].update(ranks.get(r["id"], {}))
    cols = [*TABLE_COLUMNS, *([ERROR_COLUMN] if taxonomy is not None else []),
            *(RANK_COLUMNS if ranker is not None else [])]
    return pd.DataFrame(out, columns=cols)


def summarize(table: pd.DataFrame, by: Sequence[str] = ("eval_set",)) -> pd.DataFrame:
    """The three rates (kept apart) per group."""
    g = table.groupby(list(by), sort=True)
    agg = {c: (c, "mean") for c in RATE_COLUMNS}
    return g.agg(n=("exact_value_match", "size"), **agg,
                 truncated=("truncated_prompt", "sum")).reset_index()


def evaluate_checkpoint(
    checkpoint, tokenizer: BPETokenizer, rows: Sequence[dict], seed: int,
    attribute_values: Mapping[str, Sequence[str]], device=None, max_new_tokens: int = 48,
    label: str | None = None, prompt_mode: str = "zero_shot", prompt_prefix: str = "",
    model: Transformer | None = None, taxonomy=None, ranking: bool = False,
) -> pd.DataFrame:
    """Works on ANY model checkpoint (pretrained or SFT): same prompts, same decoding."""
    from slm.model import load_checkpoint

    device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    if model is None:
        model = load_checkpoint(checkpoint, map_location=device).to(device).eval()
    ranker = None
    if ranking:
        from slm.eval_adapter import ModelScorer

        ranker = ModelScorer(model, tokenizer, device)
    return evaluate_qa(
        rows, make_generate_fn(model, tokenizer, device, max_new_tokens), seed, attribute_values,
        label if label is not None else str(checkpoint), prompt_mode, prompt_prefix,
        taxonomy=taxonomy, ranker=ranker,
    )


def assert_same_questions(table: pd.DataFrame) -> None:
    """Every (checkpoint, prompt_mode) in ``table`` was asked exactly the same questions."""
    per = {k: g["question_id"].tolist()
           for k, g in table.groupby(["checkpoint", "prompt_mode"], sort=False)}
    first = next(iter(per.values()))
    for k, ids in per.items():
        if ids != first:
            raise AssertionError(f"{k} saw a different question set")


def compare_variants(
    variants: Sequence[tuple[str, str | Path, str, str]],
    tokenizer: BPETokenizer,
    rows: Sequence[dict],
    seed: int,
    attribute_values: Mapping[str, Sequence[str]],
    device=None,
    max_new_tokens: int = 48,
    taxonomy=None,
    ranking: bool = False,
) -> pd.DataFrame:
    """Long table for ``(label, checkpoint path, prompt_mode, prompt_prefix)`` variants, all on the
    SAME rows with the same template (apart from the declared prefix) and decoding (M-D042/M-D045).
    A checkpoint used by several variants is loaded once."""
    from slm.model import load_checkpoint

    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    models: dict[str, Transformer] = {}
    tables = []
    for label, path, mode, prefix in variants:
        if str(path) not in models:
            models[str(path)] = load_checkpoint(path, map_location=dev).to(dev).eval()
        tables.append(evaluate_checkpoint(
            path, tokenizer, rows, seed, attribute_values, dev, max_new_tokens, label, mode,
            prefix, model=models[str(path)], taxonomy=taxonomy, ranking=ranking))
    out = pd.concat(tables, ignore_index=True)
    assert_same_questions(out)
    return out


def comparison_table(table: pd.DataFrame) -> pd.DataFrame:
    """Columns: checkpoint, prompt_mode, eval_set, n and the three rates."""
    s = summarize(table, ("checkpoint", "prompt_mode", "eval_set"))
    return s[["checkpoint", "prompt_mode", "eval_set", "n", *RATE_COLUMNS]]