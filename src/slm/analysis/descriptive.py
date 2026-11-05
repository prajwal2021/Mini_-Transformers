"""Descriptive tables and fact-level cluster-bootstrap effect sizes (risk-difference scale)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import DIV_BINS, FRAMES, FREQ_BINS

BOOT_B = 2000
BOOT_SEED = 20261105


def _fact_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Per fact: cell labels and mean stored rate in each probe frame (over seeds x variants)."""
    cell = df.groupby("fact_id")[["freq_bin", "div_bin"]].first()
    rates = df.pivot_table(index="fact_id", columns="probe_frame", values="stored", aggfunc="mean")
    return cell.join(rates.reindex(columns=list(FRAMES)))


def _cell_arrays(facts: pd.DataFrame, fb: str, db: str) -> np.ndarray:
    sel = facts[(facts["freq_bin"] == fb) & (facts["div_bin"] == db)]
    return sel[list(FRAMES)].to_numpy()


def _boot_cell_means(facts: pd.DataFrame, b: int, rng: np.random.Generator) -> np.ndarray:
    """Stratified (within-cell) fact bootstrap; (b, freq, div, frame) array of cell means."""
    out = np.empty((b, len(FREQ_BINS), len(DIV_BINS), len(FRAMES)))
    for i, fb in enumerate(FREQ_BINS):
        for j, db in enumerate(DIV_BINS):
            arr = _cell_arrays(facts, fb, db)
            idx = rng.integers(0, len(arr), (b, len(arr)))
            out[:, i, j, :] = arr[idx].mean(axis=1)
    return out


def _contrasts(m: np.ndarray) -> dict[str, np.ndarray]:
    """Risk-difference contrasts from cell means with trailing axes (freq, div, frame)."""
    freq = m.mean(axis=(-2, -1))
    dp = m[..., 1, :] - m[..., 0, :]  # paraphrased - templated, per freq and frame
    div_by_frame = dp.mean(axis=-2)  # (.., frame)
    return {
        "H1": freq[..., 2] - freq[..., 0],
        "H2": div_by_frame[..., 1] - div_by_frame[..., 0],
        "H2-novel": div_by_frame[..., 1],
        "H2-canonical": div_by_frame[..., 0],
        "freq x div (exploratory)": dp.mean(axis=-1)[..., 2] - dp.mean(axis=-1)[..., 0],
    }


RD_LABELS = {
    "H1": "high - low exposure",
    "H2": "(paraphrased - templated) at novel minus at canonical",
    "H2-novel": "paraphrased - templated, novel frame",
    "H2-canonical": "paraphrased - templated, canonical frame",
    "freq x div (exploratory)": "(para - templ) at high minus at low exposure",
}


def risk_difference_table(df: pd.DataFrame, b: int = BOOT_B, seed: int = BOOT_SEED) -> pd.DataFrame:
    """Risk differences in stored rate with 95% percentile bootstrap CIs (resampling facts)."""
    facts = _fact_matrix(df)
    rng = np.random.default_rng(seed)
    boots = _contrasts(_boot_cell_means(facts, b, rng))
    point_cells = np.empty((len(FREQ_BINS), len(DIV_BINS), len(FRAMES)))
    for i, fb in enumerate(FREQ_BINS):
        for j, db in enumerate(DIV_BINS):
            point_cells[i, j, :] = _cell_arrays(facts, fb, db).mean(axis=0)
    point = _contrasts(point_cells)
    rows = []
    for key, label in RD_LABELS.items():
        lo, hi = np.percentile(boots[key], [2.5, 97.5])
        rows.append(
            {
                "contrast": key,
                "description": label,
                "risk_difference": float(point[key]),
                "ci_low": float(lo),
                "ci_high": float(hi),
            }
        )
    return pd.DataFrame(rows)


def _rates(facts: pd.DataFrame, b: int, rng: np.random.Generator) -> list[dict]:
    rows = []
    for fb in FREQ_BINS:
        for db in DIV_BINS:
            arr = _cell_arrays(facts, fb, db)
            idx = rng.integers(0, len(arr), (b, len(arr)))
            lo, hi = np.percentile(arr[idx].mean(axis=1), [2.5, 97.5], axis=0)
            for k, fr in enumerate(FRAMES):
                rows.append(
                    {
                        "freq_bin": fb,
                        "div_bin": db,
                        "probe_frame": fr,
                        "n_facts": len(arr),
                        "stored_rate": float(arr[:, k].mean()),
                        "ci_low": float(lo[k]),
                        "ci_high": float(hi[k]),
                    }
                )
    return rows


def cell_rates(df: pd.DataFrame, b: int = 1000, seed: int = BOOT_SEED) -> pd.DataFrame:
    """Stored rate per freq_bin x div_bin x probe_frame with fact-bootstrap 95% CIs."""
    return pd.DataFrame(_rates(_fact_matrix(df), b, np.random.default_rng(seed)))


def curve_rates(df: pd.DataFrame, b: int = 300, seed: int = BOOT_SEED) -> pd.DataFrame:
    """Stored rate per checkpoint x cell x probe_frame with fact-bootstrap CIs."""
    rng = np.random.default_rng(seed)
    parts = []
    for ck, sub in df.groupby("checkpoint"):
        part = pd.DataFrame(_rates(_fact_matrix(sub), b, rng))
        part.insert(0, "checkpoint", int(ck))
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def acquisition_table(df: pd.DataFrame) -> pd.DataFrame:
    """First checkpoint at which a fact x seed is stored in >= half of its probes."""
    fs = df.groupby(["fact_id", "seed", "checkpoint"])["stored"].mean().reset_index()
    fs = fs[fs["stored"] >= 0.5]
    first = fs.groupby(["fact_id", "seed"])["checkpoint"].min().rename("acq_step")
    allfs = df.groupby(["fact_id", "seed"])[["freq_bin", "div_bin"]].first().join(first)
    rows = []
    for (fb, db), g in allfs.groupby(["freq_bin", "div_bin"]):
        rows.append(
            {
                "freq_bin": fb,
                "div_bin": db,
                "n_fact_seeds": len(g),
                "never_acquired": float(g["acq_step"].isna().mean()),
                "median_acq_step": float(g["acq_step"].median())
                if g["acq_step"].notna().any()
                else float("nan"),
            }
        )
    out = pd.DataFrame(rows)
    out["freq_bin"] = pd.Categorical(out["freq_bin"], FREQ_BINS, ordered=True)
    return out.sort_values(["freq_bin", "div_bin"]).reset_index(drop=True)


def eval_accuracy(qa: pd.DataFrame, b: int = 1000, seed: int = BOOT_SEED) -> pd.DataFrame:
    """Exact-match accuracy per eval set x model (mean of per-fact accuracy; fact bootstrap)."""
    rng = np.random.default_rng(seed)
    rows = []
    for (es, model), g in qa.groupby(["eval_set", "model"]):
        per_fact = g.groupby("fact_id")["exact_match"].mean().to_numpy()
        idx = rng.integers(0, len(per_fact), (b, len(per_fact)))
        lo, hi = np.percentile(per_fact[idx].mean(axis=1), [2.5, 97.5])
        rows.append({"eval_set": es, "model": model, "n_facts": len(per_fact),
                     "accuracy": float(per_fact.mean()), "ci_low": float(lo),
                     "ci_high": float(hi)})
    return pd.DataFrame(rows)


def to_markdown(df: pd.DataFrame, floatfmt: str = "{:.3f}") -> str:
    """Minimal GitHub markdown table (avoids a tabulate dependency)."""
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, (float, np.floating)):
                cells.append("nan" if np.isnan(v) else floatfmt.format(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
