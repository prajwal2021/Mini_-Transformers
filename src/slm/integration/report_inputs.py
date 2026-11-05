"""Emit the report builder's inputs from real training and evaluation runs.

``run_facts.json``, ``loss_curves.csv`` and ``samples.csv`` in the format of
docs/ANALYSIS_INPUT.md section 4 (validated with ``slm.report.inputs.load_inputs``).
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd
import torch

from slm.generation import generate_text, newline_token_ids
from slm.integration.probing import list_checkpoints
from slm.model import ModelConfig, count_parameters, load_checkpoint
from slm.report.inputs import REQUIRED_RUN_FACTS, SAMPLE_COLUMNS, load_inputs
from slm.sft_eval.evaluate import normalize, occurs
from slm.tokenizer import BPETokenizer


def git_head(cwd: str | Path | None = None, path: str | None = None) -> str:
    """Short commit hash of HEAD, or of the last commit touching ``path``."""
    cmd = ["git", "log", "-1", "--format=%h"] + (["--", path] if path else [])
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.strip() or "unknown"


# ------------------------------------------------------------------------------ loss curves


def loss_curves(pretrain_root: str | Path, seeds: Sequence[int]) -> pd.DataFrame:
    """seed, step, split (train|val), loss from every seed's loss.csv."""
    frames = []
    for seed in seeds:
        df = pd.read_csv(Path(pretrain_root) / f"seed{seed}" / "loss.csv")
        frames.append(df.assign(seed=seed)[["seed", "step", "split", "loss"]])
    return pd.concat(frames, ignore_index=True)


# ------------------------------------------------------------------------------ run facts


def templated_share_pct(
    kb: Mapping, train_texts: Sequence[str], tokenizer: BPETokenizer | None = None
) -> float:
    """Share (%) of train tokens (characters without a tokenizer) inside verbatim canonical
    sentences of templated facts."""
    size = (lambda s: len(tokenizer.encode(s))) if tokenizer else len
    total = sum(size(t) for t in train_texts) or 1
    hit = 0
    for f in kb["measured_facts"]:
        if f["div_bin"] != "templated":
            continue
        n = sum(t.count(f["canonical_sentence"]) for t in train_texts)
        hit += n * size(f["canonical_sentence"])
    return 100.0 * hit / total


def run_facts(
    *,
    kb: Mapping,
    model_cfg: ModelConfig,
    train_cfg: Mapping,
    sft_cfg: Mapping,
    split_docs: Mapping[str, int],
    train_tokens: int,
    templated_pct: float,
    n_doc_types: int,
    n_sweep_configs: int,
    sft_epochs_run: int,
    seeds: Sequence[int],
    n_params: int,
    prereg_commit: str,
    analysis_commit: str,
) -> dict:
    cells = {(f["freq_bin"], f["div_bin"]) for f in kb["measured_facts"]}
    n_facts = len(kb["measured_facts"])
    facts = {
        "n_measured_facts": n_facts, "n_cells": len(cells),
        "facts_per_cell": n_facts // max(len(cells), 1), "n_doc_types": n_doc_types,
        "n_train_docs": split_docs["train"], "n_val_docs": split_docs["val"],
        "n_test_docs": split_docs["test"], "train_tokens": int(train_tokens),
        "templated_token_share_pct": round(templated_pct, 3), "vocab_size": model_cfg.vocab_size,
        "n_layers": model_cfg.n_layer, "d_model": model_cfg.d_model, "n_heads": model_cfg.n_head,
        "context_len": model_cfg.context_len, "n_params": int(n_params), "n_seeds": len(seeds),
        "epochs_chosen": train_cfg["epochs"], "n_sweep_configs": n_sweep_configs,
        "lr": train_cfg["lr"], "sft_epochs": sft_epochs_run, "sft_lr": sft_cfg["lr"],
        "prereg_commit": prereg_commit, "analysis_commit": analysis_commit,
    }
    missing = [k for k in REQUIRED_RUN_FACTS if k not in facts]
    if missing:  # keeps this emitter in step with the report builder's contract
        raise KeyError(f"run_facts lacks {missing}")
    return facts


def count_model_params(any_checkpoint: str | Path) -> int:
    return count_parameters(load_checkpoint(any_checkpoint))


# ------------------------------------------------------------------------------ samples

_WORD = re.compile(r"\w+")


def is_repetition_loop(text: str, min_repeats: int = 3) -> bool:
    """The same word trigram (or one word, 4 times in a row) repeats."""
    w = _WORD.findall(text.casefold())
    grams: dict[tuple[str, ...], int] = {}
    for i in range(len(w) - 2):
        g = tuple(w[i : i + 3])
        grams[g] = grams.get(g, 0) + 1
    if any(c >= min_repeats for c in grams.values()):
        return True
    return any(len(set(w[i : i + 4])) == 1 for i in range(len(w) - 3))


def classify(text: str, value: str, others: Sequence[str]) -> tuple[str, str]:
    """(category, note); category is ``success: ...`` or ``failure: ...`` (DESIGN section 6)."""
    text = normalize(text)
    has_gold = occurs(text, value)
    n_other = sum(occurs(text, v) for v in others)
    if has_gold and n_other == 0:
        return "success: recalled fact", "value matches the KB and no rival value appears"
    if is_repetition_loop(text):
        return "failure: repetition loop", "a phrase repeats"
    if n_other:
        return "failure: entity confusion", "a value of another entity of the same attribute"
    if not text:
        return "failure: format drift", "empty completion"
    return "failure: wrong fact", "no value of this attribute, or not the right one"


def _attr_values(kb: Mapping) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in kb["measured_facts"]:
        out.setdefault(f["attribute_id"], []).append(f["value"])
    return out


def qa_samples(
    predictions: pd.DataFrame,
    kb: Mapping,
    questions: Mapping[str, str] | None = None,
    model_label: str = "sft",
    per_category: int = 2,
) -> list[dict]:
    """Classified SFT answers (E2 held-out facts, seed 0 first) as report samples."""
    values = _attr_values(kb)
    sub = predictions[(predictions["checkpoint"] == model_label)
                      & (predictions["eval_set"] == "E2")].sort_values(["seed", "question_id"])
    rows: list[dict] = []
    seen: dict[str, int] = {}
    for r in sub.itertuples():
        others = [v for v in values[r.attribute_id] if v != r.gold_value]
        cat, note = classify(r.prediction, r.gold_value, others)
        if seen.get(cat, 0) >= per_category:
            continue
        seen[cat] = seen.get(cat, 0) + 1
        prompt = (questions or {}).get(r.question_id, r.question_id)
        rows.append({"category": cat, "prompt": prompt, "completion": r.prediction,
                     "note": f"SFT, held-out fact {r.fact_id}, seed {r.seed}: {note}"})
    return rows


def checkpoint_samples(
    pretrain_root: str | Path,
    tokenizer: BPETokenizer,
    kb: Mapping,
    seed: int = 0,
    facts_per_checkpoint: int = 3,
    max_new_tokens: int = 24,
    device: str | None = None,
) -> list[dict]:
    """Greedy continuations of canonical prefixes at each saved checkpoint, flagged success/fail."""
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    values = _attr_values(kb)
    stop = newline_token_ids(tokenizer)
    picked = kb["measured_facts"][:: max(1, len(kb["measured_facts"]) // facts_per_checkpoint)]
    picked = picked[:facts_per_checkpoint]
    rows = []
    for step, epoch, path in list_checkpoints(Path(pretrain_root) / f"seed{seed}"):
        model = load_checkpoint(path, map_location=dev).to(dev).eval()
        for f in picked:
            prompt = f["canonical_prefix"].rstrip()
            text, _ = generate_text(model, tokenizer, prompt, max_new_tokens, stop, dev)
            others = [v for v in values[f["attribute_id"]] if v != f["value"]]
            cat, note = classify(text.split("\n", 1)[0], f["value"], others)
            rows.append({"category": cat, "prompt": prompt, "completion": text.strip(),
                         "note": f"pretrained seed {seed}, step {step} (epoch {epoch}): {note}"})
    return rows


def balanced_samples(rows: Sequence[dict], per_category: int = 2, limit: int = 14) -> pd.DataFrame:
    """Keep at most ``per_category`` per category label, successes first, at most ``limit``."""
    kept: list[dict] = []
    seen: dict[str, int] = {}
    for r in sorted(rows, key=lambda r: (not r["category"].startswith("success"), r["category"])):
        key = r["category"]
        if seen.get(key, 0) < per_category:
            kept.append(r)
            seen[key] = seen.get(key, 0) + 1
    return pd.DataFrame(kept[:limit], columns=list(SAMPLE_COLUMNS))


def write_report_inputs(
    out_dir: str | Path, facts: Mapping, loss: pd.DataFrame, samples: pd.DataFrame
) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {"run_facts": out / "run_facts.json", "loss": out / "loss_curves.csv",
             "samples": out / "samples.csv"}
    paths["run_facts"].write_text(json.dumps(dict(facts), indent=2), encoding="utf-8")
    loss.to_csv(paths["loss"], index=False, encoding="utf-8")
    samples.to_csv(paths["samples"], index=False, encoding="utf-8")
    load_inputs(out)  # raises InputError when the builder would refuse them
    return paths
