"""The confirmatory family H1-H3 (Holm, m = 3) and the secondary H4 (PREREG v3).

DESIGN.md names H1-H4 but states no correction; docs/PREREG.md applies Holm. PREREG v3 keeps
H1, H2, H3 confirmatory (m = 3) and pre-registers H4 as SECONDARY: effect size and CI are
reported with no significance claim (power 0.36 at 120 facts, KB split frozen). If H3 is
missing (no QA table) its p-value is treated as 1, which is the conservative bound for H1 and
H2 and is labelled provisional.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .models import ALPHA, holm

HYPOTHESES = ("H1", "H2", "H3", "H4")
CONFIRMATORY = ("H1", "H2", "H3")
SECONDARY = ("H4",)
# Equivalence margins of PREREG v4: researcher-chosen, not data-derived (never claim "no effect"
# unless the whole 95% CI lies inside the margin)
MARGIN_LOG_ODDS = float(np.log(1.25))
MARGIN_RISK_DIFF = 0.10


def assemble_family(
    gee_family: pd.DataFrame, extraction_family: pd.DataFrame | None = None
) -> pd.DataFrame:
    g = gee_family.copy()
    g["scale"] = "log-odds"
    parts = [g]
    if extraction_family is not None:
        parts.append(extraction_family)
    fam = pd.concat(parts, ignore_index=True)
    fam["hypothesis"] = pd.Categorical(fam["hypothesis"], HYPOTHESES, ordered=True)
    fam = fam.sort_values("hypothesis").reset_index(drop=True)
    fam["hypothesis"] = fam["hypothesis"].astype(str)

    p_full = {h: 1.0 for h in CONFIRMATORY}
    for h, p in zip(fam["hypothesis"], fam["p_raw"]):
        if h in CONFIRMATORY:
            p_full[h] = p
    adj, rej = holm([p_full[h] for h in CONFIRMATORY])
    adj_map = dict(zip(CONFIRMATORY, adj))
    rej_map = dict(zip(CONFIRMATORY, rej))
    secondary = fam["hypothesis"].isin(SECONDARY)
    fam["p_descriptive"] = np.where(secondary, fam["p_raw"], np.nan)
    fam.loc[secondary, "p_raw"] = np.nan  # no significance claim for secondary hypotheses
    fam["p_holm"] = [adj_map.get(h, np.nan) for h in fam["hypothesis"]]
    fam["reject_holm"] = [bool(rej_map.get(h, False)) for h in fam["hypothesis"]]
    fam["status"] = [_status(r) for _, r in fam.iterrows()]
    present = set(fam["hypothesis"]) & set(CONFIRMATORY)
    fam["provisional"] = len(present) < len(CONFIRMATORY)
    return fam


def _status(row: pd.Series) -> str:
    if row["hypothesis"] in SECONDARY:
        return "secondary: effect and CI only"
    if row["reject_holm"]:
        return "supported" if row["direction_ok"] else "reversed"
    margin = MARGIN_LOG_ODDS if row["scale"] == "log-odds" else MARGIN_RISK_DIFF
    lo, hi = row.get("ci_low", np.nan), row.get("ci_high", np.nan)
    if np.isfinite(lo) and np.isfinite(hi) and lo > -margin and hi < margin:
        return "not supported; CI inside margin"
    return "not supported; inconclusive"


__all__ = ["ALPHA", "CONFIRMATORY", "HYPOTHESES", "SECONDARY", "assemble_family"]
