"""Descriptive tables and fact-level cluster-bootstrap effect sizes (risk-difference scale)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import DIV_BINS, FREQ_BINS, REGIMES

BOOT_B = 2000
BOOT_SEED = 20261105


def _fact_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Per fact: cell labels and mean stored rate in each regime (over seeds x variants)."""
    cell = df.groupby("fact_id")[["freq_bin", "div_bin"]].first()
    rates = df.pivot_table(index="fact_id", columns="regime", values="stored", aggfunc="mean")
    return cell.join(rates[list(REGIMES)])


def _boot_cell_means(facts: pd.DataFrame, b: int, rng: np.random.Generator) -> np.ndarray:
    """Stratified (within-cell) fact bootstrap. Returns array (b, 3, 2, 2) of cell means.

    Axes: replicate, freq_bin, div_bin, regime. Sampling is over facts, so seed and prompt
    variant noise stays attached to the resampled fact.
    """
    out = np.empty((b, len(FREQ_BINS), len(DIV_BINS), len(REGIMES)))
    for i, fb in enumerate(FREQ_BINS):
        for j, db in enumerate(DIV_BINS):
            vals = facts[(facts["freq_bin"] == fb) & (facts["div_bin"] == db)][list(REGIMES)]
            arr = vals.to_numpy()
            idx = rng.integers(0, len(arr), (b, len(arr)))
            out[:, i, j, :] = arr[idx].mean(axis=1)
    return out


def _contrasts(m: np.ndarray) -> dict[str, np.ndarray]:
    """Risk-difference contrasts from cell means with trailing axes (freq, div, regime)."""
    freq = m.mean(axis=(-2, -1))  # per freq bin
    dp = m[..., 1, :] - m[..., 0, :]  # paraphrased - templated, per freq/regime
    return {
        "H1": freq[..., 2] - freq[..., 0],
        "H2": dp.mean(axis=(-2, -1)),
        "H3": dp.mean(axis=-1)[..., 2] - dp.mean(axis=-1)[..., 0],
        "H4": m[..., 1].mean(axis=(-2, -1)) - m[..., 0].mean(axis=(-2, -1)),
    }


RD_LABELS = {
    "H1": "high - low frequency",
    "H2": "paraphrased - templated",
    "H3": "(para - templ) at high minus at low",
    "H4": "novel - iid",
}


def risk_difference_table(df: pd.DataFrame, b: int = BOOT_B, seed: int = BOOT_SEED) -> pd.DataFrame:
    """Risk differences in stored rate with 95% percentile bootstrap CIs (resampling facts)."""
    facts = _fact_matrix(df)
    rng = np.random.default_rng(seed)
    boots = _contrasts(_boot_cell_means(facts, b, rng))
    point_cells = np.empty((len(FREQ_BINS), len(DIV_BINS), len(REGIMES)))
    for i, fb in enumerate(FREQ_BINS):
        for j, db in enumerate(DIV_BINS):
            sel = facts[(facts["freq_bin"] == fb) & (facts["div_bin"] == db)]
            point_cells[i, j, :] = sel[list(REGIMES)].to_numpy().mean(axis=0)
    point = _contrasts(point_cells)
    rows = []
    for hid, label in RD_LABELS.items():
        lo, hi = np.percentile(boots[hid], [2.5, 97.5])
        rows.append(
            {
                "hypothesis": hid,
                "contrast": label,
                "risk_difference": float(point[hid]),
                "ci_low": float(lo),
                "ci_high": float(hi),
            }
        )
    return pd.DataFrame(rows)


def cell_rates(df: pd.DataFrame, b: int = 1000, seed: int = BOOT_SEED) -> pd.DataFrame:
    """Stored rate per freq_bin x div_bin x regime with fact-bootstrap 95% CIs."""
    facts = _fact_matrix(df)
    rng = np.random.default_rng(seed)
    rows = []
    for fb in FREQ_BINS:
        for db in DIV_BINS:
            sel = facts[(facts["freq_bin"] == fb) & (facts["div_bin"] == db)]
            arr = sel[list(REGIMES)].to_numpy()
            idx = rng.integers(0, len(arr), (b, len(arr)))
            boot = arr[idx].mean(axis=1)
            lo, hi = np.percentile(boot, [2.5, 97.5], axis=0)
            for k, rg in enumerate(REGIMES):
                rows.append(
                    {
                        "freq_bin": fb,
                        "div_bin": db,
                        "regime": rg,
                        "n_facts": len(arr),
                        "stored_rate": float(arr[:, k].mean()),
                        "ci_low": float(lo[k]),
                        "ci_high": float(hi[k]),
                    }
                )
    return pd.DataFrame(rows)


def curve_rates(df: pd.DataFrame, b: int = 300, seed: int = BOOT_SEED) -> pd.DataFrame:
    """Stored rate per checkpoint x freq_bin x div_bin x regime with fact-bootstrap CIs."""
    rng = np.random.default_rng(seed)
    rows = []
    for ck, sub in df.groupby("checkpoint"):
        facts = _fact_matrix(sub)
        for fb in FREQ_BINS:
            for db in DIV_BINS:
                sel = facts[(facts["freq_bin"] == fb) & (facts["div_bin"] == db)]
                arr = sel[list(REGIMES)].to_numpy()
                idx = rng.integers(0, len(arr), (b, len(arr)))
                lo, hi = np.percentile(arr[idx].mean(axis=1), [2.5, 97.5], axis=0)
                for k, rg in enumerate(REGIMES):
                    rows.append(
                        {
                            "checkpoint": int(ck),
                            "freq_bin": fb,
                            "div_bin": db,
                            "regime": rg,
                            "stored_rate": float(arr[:, k].mean()),
                            "ci_low": float(lo[k]),
                            "ci_high": float(hi[k]),
                        }
                    )
    return pd.DataFrame(rows)


def acquisition_table(df: pd.DataFrame) -> pd.DataFrame:
    """First checkpoint at which a fact x seed is stored in >= half of its probes."""
    fs = df.groupby(["fact_id", "seed", "checkpoint"])["stored"].mean().reset_index()
    fs = fs[fs["stored"] >= 0.5]
    first = fs.groupby(["fact_id", "seed"])["checkpoint"].min().rename("acq_step")
    keys = df.groupby(["fact_id", "seed"])[["freq_bin", "div_bin"]].first()
    allfs = keys.join(first)
    rows = []
    for (fb, db), g in allfs.groupby(["freq_bin", "div_bin"]):
        rows.append(
            {
                "freq_bin": fb,
                "div_bin": db,
                "n_fact_seeds": len(g),
                "never_acquired": float(g["acq_step"].isna().mean()),
                "median_acq_step": float(g["acq_step"].median()) if g["acq_step"].notna().any()
                else float("nan"),
            }
        )
    out = pd.DataFrame(rows)
    out["freq_bin"] = pd.Categorical(out["freq_bin"], FREQ_BINS, ordered=True)
    return out.sort_values(["freq_bin", "div_bin"]).reset_index(drop=True)


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
