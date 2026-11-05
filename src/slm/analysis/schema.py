"""Input contracts: the probe table (H1, H2) and the SFT QA table (H3, H4).

See docs/ANALYSIS_INPUT.md. The probe table matches `slm.eval.probes.TABLE_COLUMNS`
(docs/EVAL_COLUMNS.md in the eval stream); the QA table is defined here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FREQ_BINS = ("low", "mid", "high")
DIV_BINS = ("templated", "paraphrased")
FRAMES = ("canonical", "novel")
EVAL_SETS = ("E0", "E1", "E2")
MODELS = ("base_0shot", "base_2shot", "sft")
SFT_SPLITS = ("train", "heldout")
MAX_RANK = 6  # the correct value is ranked against the 6 same-attribute values
INIT_CHECKPOINT = "init"  # untrained model; mapped to step 0

PROBE_REQUIRED = (
    "fact_id",
    "seed",
    "checkpoint",
    "probe_frame",
    "freq_bin",
    "div_bin",
    "prompt_variant",
    "rank",
    "binding_score",
    "stored",
    "split",
    "attribute_id",
    "true_logprob",
    "baseline_logprob",
)
# optional fact-level covariates / exposure; aliases follow the eval stream's proposal
PROBE_OPTIONAL = ("train_mentions", "value_len", "entity_freq", "stored_tokennorm")
REALIZED_REQUIRED = (
    "fact_id",
    "n_distinct",
    "n_reused",
    "core_uniqueness",
    "mean_pairwise_jaccard",
)
PROBE_ALIASES = {"value_len_tokens": "value_len", "entity_mentions": "entity_freq"}

QA_REQUIRED = (
    "fact_id",
    "seed",
    "eval_set",
    "question_id",
    "model",
    "exact_match",
    "stored_pretrain",
    "freq_bin",
    "div_bin",
    "sft_split",
)
QA_ALIASES = {"subset": "eval_set", "correct": "exact_match"}
BINDING_TOL = 5e-3


class SchemaError(ValueError):
    """A table violates its input contract."""


def _missing(df: pd.DataFrame, required: tuple[str, ...]) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SchemaError(f"missing required columns: {missing}")
    if df.empty:
        raise SchemaError("table is empty")
    na = [f"{c}: {int(df[c].isna().sum())} missing" for c in required if df[c].isna().any()]
    if na:
        raise SchemaError("; ".join(na))


def _levels(df: pd.DataFrame, col: str, allowed: tuple[str, ...]) -> None:
    bad = sorted(set(df[col].astype(str)) - set(allowed))
    if bad:
        raise SchemaError(f"{col}: unexpected levels {bad} (allowed {list(allowed)})")


def normalize_probe_table(df: pd.DataFrame) -> pd.DataFrame:
    """Apply aliases and map the `init` checkpoint to step 0; returns a copy."""
    out = df.rename(columns={k: v for k, v in PROBE_ALIASES.items() if k in df.columns}).copy()
    if "checkpoint" in out.columns:
        ck = out["checkpoint"].astype(str).str.strip().str.lower()
        out["checkpoint"] = ck.where(ck != INIT_CHECKPOINT, "0")
        out["checkpoint"] = pd.to_numeric(out["checkpoint"], errors="raise").astype(int)
    return out


def validate_probe_table(df: pd.DataFrame) -> list[str]:
    """Validate the probe-table contract (on a normalized table); return non-fatal warnings."""
    _missing(df, PROBE_REQUIRED)
    _levels(df, "freq_bin", FREQ_BINS)
    _levels(df, "div_bin", DIV_BINS)
    _levels(df, "probe_frame", FRAMES)
    _levels(df, "split", ("val", "test"))
    rank = pd.to_numeric(df["rank"], errors="coerce")
    if rank.isna().any() or ((rank < 1) | (rank > MAX_RANK) | (rank % 1 != 0)).any():
        raise SchemaError(f"rank must be an integer in 1..{MAX_RANK}")
    for col in ("binding_score", "true_logprob", "baseline_logprob"):
        if not np.isfinite(pd.to_numeric(df[col], errors="coerce")).all():
            raise SchemaError(f"{col} must be finite")
    gap = (df["true_logprob"] - df["baseline_logprob"] - df["binding_score"]).abs()
    if (gap > BINDING_TOL).any():
        raise SchemaError(
            "binding_score != true_logprob - baseline_logprob in "
            f"{int((gap > BINDING_TOL).sum())} rows"
        )
    stored = df["stored"].astype(int)
    if not stored.isin([0, 1]).all():
        raise SchemaError("stored must be 0/1")
    derived = ((rank == 1) & (df["binding_score"] > 0)).astype(int)
    if (derived != stored).any():
        raise SchemaError(
            "stored disagrees with (rank == 1 and binding_score > 0) in "
            f"{int((derived != stored).sum())} rows"
        )
    key = ["fact_id", "seed", "checkpoint", "split", "prompt_variant"]
    if df.duplicated(key).any():
        raise SchemaError(f"duplicate rows for key {key}")
    for col in ("freq_bin", "div_bin", "attribute_id"):
        if (df.groupby("fact_id")[col].nunique() > 1).any():
            raise SchemaError(f"{col} must be constant within a fact")
    if (df.groupby("prompt_variant")["probe_frame"].nunique() > 1).any():
        raise SchemaError("each prompt_variant must belong to exactly one probe_frame")
    warnings: list[str] = []
    test = df[df["split"] == "test"]
    if test.empty:
        raise SchemaError("no test-split rows (val probes are for checkpoint selection only)")
    counts = test.groupby(["freq_bin", "div_bin"])["fact_id"].nunique()
    if len(counts) < len(FREQ_BINS) * len(DIV_BINS):
        warnings.append("not all 6 freq_bin x div_bin cells are present in test rows")
    elif counts.min() < 0.5 * counts.max():
        warnings.append(f"unbalanced cells (facts per cell {counts.min()}..{counts.max()})")
    if test["probe_frame"].nunique() < 2:
        warnings.append("only one probe_frame present: H2 cannot be tested")
    return warnings


def validate_realized_diversity(rd: pd.DataFrame, facts: set[str] | None = None) -> None:
    """Validate data/bank/realized_diversity.csv (one row per fact)."""
    _missing(rd, REALIZED_REQUIRED)
    if rd["fact_id"].duplicated().any():
        raise SchemaError("realized_diversity: duplicate fact_id")
    for col in ("core_uniqueness", "mean_pairwise_jaccard"):
        if ((rd[col] < 0) | (rd[col] > 1)).any():
            raise SchemaError(f"realized_diversity: {col} must be in [0, 1]")
    for col in ("n_distinct", "n_reused"):
        if (rd[col] < 0).any():
            raise SchemaError(f"realized_diversity: {col} must be >= 0")
    if facts is not None:
        missing = facts - set(rd["fact_id"])
        if missing:
            raise SchemaError(f"realized_diversity: {len(missing)} analysed facts have no row")


def normalize_qa_table(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={k: v for k, v in QA_ALIASES.items() if k in df.columns}).copy()


def validate_qa_table(df: pd.DataFrame) -> list[str]:
    """Validate the SFT QA-table contract; return non-fatal warnings."""
    _missing(df, QA_REQUIRED)
    _levels(df, "eval_set", EVAL_SETS)
    _levels(df, "model", MODELS)
    _levels(df, "freq_bin", FREQ_BINS)
    _levels(df, "div_bin", DIV_BINS)
    _levels(df, "sft_split", SFT_SPLITS)
    for col in ("exact_match", "stored_pretrain"):
        if not df[col].astype(int).isin([0, 1]).all():
            raise SchemaError(f"{col} must be 0/1")
    if df.duplicated(["fact_id", "seed", "eval_set", "question_id", "model"]).any():
        raise SchemaError("duplicate rows for (fact_id, seed, eval_set, question_id, model)")
    expect = {"E0": "train", "E1": "train", "E2": "heldout"}
    for es, split in expect.items():
        sub = df[df["eval_set"] == es]
        if (sub["sft_split"] != split).any():
            raise SchemaError(f"{es} must contain only {split} facts (DESIGN section 7.2)")
    if set(df.loc[df["eval_set"] == "E2", "fact_id"]) & set(
        df.loc[df["eval_set"].isin(["E0", "E1"]), "fact_id"]
    ):
        raise SchemaError("a fact appears in both E2 (held-out) and E0/E1 (SFT-train)")
    for col in ("freq_bin", "div_bin", "sft_split"):
        if (df.groupby("fact_id")[col].nunique() > 1).any():
            raise SchemaError(f"{col} must be constant within a fact")
    e2 = df[df["eval_set"] == "E2"]
    if e2.empty:
        raise SchemaError("no E2 rows")
    warnings = []
    per_model = e2.groupby("model")["question_id"].nunique()
    if per_model.nunique() > 1:
        warnings.append(f"E2 question counts differ across models: {per_model.to_dict()}")
    return warnings
