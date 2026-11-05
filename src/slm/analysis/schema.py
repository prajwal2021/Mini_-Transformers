"""Input contract for the long-format probe table (see docs/ANALYSIS_INPUT.md)."""

from __future__ import annotations

import numpy as np
import pandas as pd

FREQ_BINS = ("low", "mid", "high")
DIV_BINS = ("templated", "paraphrased")
REGIMES = ("iid", "novel")

REQUIRED_COLUMNS = (
    "fact_id",
    "seed",
    "checkpoint",
    "regime",
    "freq_bin",
    "div_bin",
    "prompt_variant",
    "rank",
    "binding_score",
    "stored",
)
OPTIONAL_COVARIATES = ("attr_type", "value_len", "entity_freq")
MAX_RANK = 6  # the correct value is ranked against the 6 same-attribute values


class SchemaError(ValueError):
    """The probe table violates the input contract."""


def validate_table(df: pd.DataFrame) -> list[str]:
    """Validate the contract; raise SchemaError on a violation, return non-fatal warnings."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaError(f"missing required columns: {missing}")
    if df.empty:
        raise SchemaError("probe table is empty")
    problems: list[str] = []
    for col in REQUIRED_COLUMNS:
        if df[col].isna().any():
            problems.append(f"{col}: {int(df[col].isna().sum())} missing values")
    for col, allowed in (("freq_bin", FREQ_BINS), ("div_bin", DIV_BINS), ("regime", REGIMES)):
        bad = sorted(set(df[col].dropna().astype(str)) - set(allowed))
        if bad:
            problems.append(f"{col}: unexpected levels {bad} (allowed {list(allowed)})")
    if problems:
        raise SchemaError("; ".join(problems))
    rank = pd.to_numeric(df["rank"], errors="coerce")
    if rank.isna().any() or ((rank < 1) | (rank > MAX_RANK) | (rank % 1 != 0)).any():
        raise SchemaError(f"rank must be an integer in 1..{MAX_RANK}")
    if not np.isfinite(pd.to_numeric(df["binding_score"], errors="coerce")).all():
        raise SchemaError("binding_score must be finite")
    stored = df["stored"].astype(int)
    if not stored.isin([0, 1]).all():
        raise SchemaError("stored must be 0/1")
    derived = ((rank == 1) & (df["binding_score"] > 0)).astype(int)
    if (derived != stored).any():
        raise SchemaError(
            f"stored disagrees with (rank == 1 and binding_score > 0) in "
            f"{int((derived != stored).sum())} rows"
        )
    key = ["fact_id", "seed", "checkpoint", "regime", "prompt_variant"]
    if df.duplicated(key).any():
        raise SchemaError(f"duplicate rows for key {key}")
    warnings: list[str] = []
    for col in ("freq_bin", "div_bin"):
        if (df.groupby("fact_id")[col].nunique() > 1).any():
            raise SchemaError(f"{col} must be constant within a fact")
    counts = df.groupby(["freq_bin", "div_bin"])["fact_id"].nunique()
    if len(counts) < len(FREQ_BINS) * len(DIV_BINS):
        warnings.append("not all 6 freq_bin x div_bin cells are present")
    elif counts.min() < 0.5 * counts.max():
        warnings.append(f"unbalanced cells (facts per cell {counts.min()}..{counts.max()})")
    return warnings


def enforce_stored(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with `stored` recomputed from rank and binding_score."""
    out = df.copy()
    out["stored"] = ((out["rank"] == 1) & (out["binding_score"] > 0)).astype(int)
    return out
