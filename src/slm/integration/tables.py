"""Build the analysis inputs from the evaluation outputs (docs/INTERFACES.md sections 2-4).

Joins: probe table (eval stream) x exposure (corpus counts or the corpus plan) x KB, QA predictions
(model stream, one row per question and variant) x probe table x KB x SFT fact split, and the bank
stream's realized-diversity file. Everything is validated against the analysis stream's schema
before it is written, so a contract violation stops here and not inside a model fit.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

import pandas as pd

from slm.analysis.aggregation import PRIMARY_RULE, stored_by_fact_seed
from slm.analysis.models import final_by_seed
from slm.analysis.schema import (
    normalize_probe_table,
    normalize_qa_table,
    validate_probe_table,
    validate_qa_table,
    validate_realized_diversity,
)

# (checkpoint label, prompt_mode) of the evaluator's tables -> the analysis `model` level
MODEL_OF = {
    ("pretrained", "zero_shot"): "base_0shot",
    ("pretrained", "2shot"): "base_2shot",
    ("sft", "zero_shot"): "sft",
}
SFT_SPLIT_OF = {"sft_train": "train", "train": "train", "heldout": "heldout"}  # sft_val: refused
QA_COLUMNS = [
    "fact_id", "seed", "eval_set", "question_id", "model", "exact_value_match", "contains_gold",
    "sentence_exact", "stored_pretrain", "freq_bin", "div_bin", "sft_split", "attribute_id",
    "template_id",
]
# carried when the evaluator wrote them (R01): the error taxonomy and the ranking ranks
QA_EXTRA_COLUMNS = ["error_class", "rank_value", "rank_value_norm", "rank_sentence",
                    "rank_sentence_norm"]
# bank-stream file (data/bank/realized_diversity.csv) -> analysis names (ANALYSIS_INPUT section 3)
REALIZED_RENAME = {
    "core_unique_share": "core_uniqueness",
    "mean_pair_skeleton_jaccard": "mean_pairwise_jaccard",
}


def load_kb(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_plan(path: str | Path) -> list[dict]:
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


# ---------------------------------------------------------------------------------- exposure


def _count(pattern: str, texts: Iterable[str]) -> int:
    rx = re.compile(r"(?<!\w)" + re.escape(pattern) + r"(?!\w)")
    return sum(len(rx.findall(t)) for t in texts)


def exposure_from_plan(kb: Mapping, plan: Sequence[Mapping]) -> pd.DataFrame:
    """Planned exposure: train-split documents per fact (one mention each) and per entity."""
    per_fact: dict[str, int] = {}
    for doc in plan:
        if doc["split"] == "train":
            for fid in doc["fact_ids"]:
                per_fact[fid] = per_fact.get(fid, 0) + 1
    entity_total: dict[str, int] = {}
    for f in kb["measured_facts"]:
        entity_total[f["entity_id"]] = entity_total.get(f["entity_id"], 0) + per_fact.get(
            f["fact_id"], 0
        )
    rows = [
        {"fact_id": f["fact_id"], "train_mentions": per_fact.get(f["fact_id"], 0),
         "entity_freq": entity_total[f["entity_id"]], "value_len": int(f["char_len"]),
         "exposure_source": "planned"}
        for f in kb["measured_facts"]
    ]
    return pd.DataFrame(rows)


def exposure_from_corpus(kb: Mapping, train_texts: Sequence[str], tokenizer=None) -> pd.DataFrame:
    """Measured exposure: string-match counts of the value and of the entity name in train text.

    ``value_len`` is the token count of " " + value when a tokenizer is given, else the KB's
    character length.
    """
    rows = []
    for f in kb["measured_facts"]:
        n_val = int(f["char_len"])
        if tokenizer is not None:
            n_val = len(tokenizer.encode(" " + f["value"]))
        rows.append(
            {"fact_id": f["fact_id"], "train_mentions": _count(f["value"], train_texts),
             "entity_freq": _count(f["entity"], train_texts), "value_len": n_val,
             "exposure_source": "measured"}
        )
    return pd.DataFrame(rows)


def read_exposure(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    need = {"fact_id", "train_mentions"}
    if not need <= set(df.columns):
        raise ValueError(f"exposure file lacks columns {sorted(need - set(df.columns))}")
    return df


# ---------------------------------------------------------------------- realized diversity


def normalize_realized_diversity(raw: pd.DataFrame) -> pd.DataFrame:
    rd = raw.rename(columns={k: v for k, v in REALIZED_RENAME.items() if k in raw.columns})
    validate_realized_diversity(rd)
    keep = ["fact_id", "n_distinct", "n_reused", "core_uniqueness", "mean_pairwise_jaccard"]
    return rd[keep + [c for c in rd.columns if c not in keep]]


# ----------------------------------------------------------------------------- probe table


def probe_table(raw: pd.DataFrame, exposure: pd.DataFrame | None = None) -> pd.DataFrame:
    """The probe table plus per-fact exposure covariates; validated, ``init`` kept as is."""
    out = raw.copy()
    if exposure is not None:
        cols = [c for c in ("train_mentions", "entity_freq", "value_len") if c in exposure.columns]
        out = out.drop(columns=[c for c in cols if c in out.columns]).merge(
            exposure[["fact_id", *cols]], on="fact_id", how="left", validate="many_to_one"
        )
        missing = out[cols].isna().any(axis=1)
        if missing.any():
            facts = sorted(out.loc[missing, "fact_id"].unique())
            raise ValueError(f"no exposure row for facts {facts}")
    validate_probe_table(normalize_probe_table(out))
    return out


def probe_counts(probe: pd.DataFrame) -> pd.DataFrame:
    """Probes per fact, split x frame (one seed, one checkpoint; the same for every other)."""
    first = probe.iloc[0]
    sub = probe[(probe["seed"] == first["seed"]) & (probe["checkpoint"] == first["checkpoint"])]
    counts = sub.groupby(["fact_id", "split", "probe_frame"]).size()
    return counts.unstack(["split", "probe_frame"]).fillna(0).astype(int)


def stored_pretrain(probe: pd.DataFrame, rule: str = PRIMARY_RULE) -> pd.DataFrame:
    """fact_id, seed, stored_pretrain from the TEST probes at each seed's final checkpoint.

    The number of probes comes from the table (share of stored probes), never from a constant.
    """
    norm = normalize_probe_table(probe)
    test = norm[norm["split"] == "test"]
    finals = final_by_seed(test)
    final_rows = test[test["checkpoint"] == test["seed"].map(finals)]
    return stored_by_fact_seed(final_rows, rule)


# -------------------------------------------------------------------------------- QA table


def qa_table(
    predictions: pd.DataFrame,
    probe: pd.DataFrame,
    kb: Mapping,
    fact_split: Mapping[str, str] | None = None,
    rule: str = PRIMARY_RULE,
) -> pd.DataFrame:
    """The SFT-outcome table: evaluator rows x (stored_pretrain, bins, sft_split).

    ``predictions`` is the evaluator output (``slm.sft_eval.TABLE_COLUMNS``) over all seeds and
    the three variants. Rows of other variants are refused, so a label typo cannot drop data.
    """
    pred = predictions.copy()
    pairs = list(zip(pred["checkpoint"], pred["prompt_mode"], strict=True))
    unknown = sorted({p for p in pairs if p not in MODEL_OF})
    if unknown:
        raise ValueError(f"unknown (checkpoint, prompt_mode) variants {unknown}; "
                         f"known {list(MODEL_OF)}")
    pred["model"] = [MODEL_OF[p] for p in pairs]
    split = dict(fact_split) if fact_split is not None else {
        f["fact_id"]: f["sft_split"] for f in kb["measured_facts"]
    }
    pred["sft_split"] = pred["fact_id"].map(lambda f: SFT_SPLIT_OF.get(split.get(f, "?"), "?"))
    bad = pred[pred["sft_split"] == "?"]
    if len(bad):
        raise ValueError(f"{len(bad)} QA rows belong to facts that are not SFT-train or held-out: "
                         f"{sorted(bad['fact_id'].unique())[:5]}")
    stored = stored_pretrain(probe, rule)
    out = pred.merge(stored, on=["fact_id", "seed"], how="left", validate="many_to_one")
    if out["stored_pretrain"].isna().any():
        raise ValueError("QA rows without probe rows for the same fact and seed")
    for c in ("exact_value_match", "contains_gold", "sentence_exact"):
        out[c] = out[c].astype(int)
    out = out[[*QA_COLUMNS, *[c for c in QA_EXTRA_COLUMNS if c in out.columns]]].sort_values(["model", "seed", "eval_set", "question_id"])  # noqa: E501
    validate_qa_table(normalize_qa_table(out))
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------------- driver


def write_qa_summaries(qa_predictions: pd.DataFrame, out_dir: str | Path) -> dict[str, Path]:
    """R01: error-class counts (checkpoint x prompt_mode x eval_set) and ranking accuracy tables."""
    out, paths = Path(out_dir), {}
    out.mkdir(parents=True, exist_ok=True)
    if "error_class" in qa_predictions.columns:
        from slm.sft_eval.taxonomy import error_summary

        paths["error_taxonomy"] = out / "error_taxonomy.csv"
        error_summary(qa_predictions).to_csv(paths["error_taxonomy"], index=False, encoding="utf-8")
    if "rank_value" in qa_predictions.columns:
        from slm.sft_eval.ranking import ranking_summary

        paths["ranking"] = out / "ranking_accuracy.csv"
        ranking_summary(qa_predictions).to_csv(paths["ranking"], index=False, encoding="utf-8")
    return paths


def build_analysis_tables(
    probe_raw: pd.DataFrame,
    qa_predictions: pd.DataFrame,
    kb: Mapping,
    out_dir: str | Path,
    *,
    exposure: pd.DataFrame | None = None,
    realized: pd.DataFrame | None = None,
    fact_split: Mapping[str, str] | None = None,
) -> dict[str, Path]:
    """Write probe.csv, qa.csv and (when given) realized_diversity.csv into ``out_dir``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    probe = probe_table(probe_raw, exposure)
    qa = qa_table(qa_predictions, probe, kb, fact_split)
    paths = {"probe": out / "probe.csv", "qa": out / "qa.csv"}
    paths.update(write_qa_summaries(qa_predictions, out))
    probe.to_csv(paths["probe"], index=False, encoding="utf-8")
    qa.to_csv(paths["qa"], index=False, encoding="utf-8")
    if realized is not None:
        rd = normalize_realized_diversity(realized)
        validate_realized_diversity(rd, set(probe["fact_id"]))
        paths["realized"] = out / "realized_diversity.csv"
        rd.to_csv(paths["realized"], index=False, encoding="utf-8")
    return paths
