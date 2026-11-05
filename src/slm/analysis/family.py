"""The confirmatory family H1-H4: Holm correction and decision labels.

DESIGN.md names the four hypotheses but states no correction; docs/PREREG.md (v0, kept in v1)
applies Holm across H1-H4, so that is the family. If H3/H4 are not available (no QA table) the
missing p-values are treated as 1, which is the conservative bound for H1/H2 and is labelled
provisional.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .models import ALPHA, holm

HYPOTHESES = ("H1", "H2", "H3", "H4")
# PLACEHOLDER equivalence margins; to be set at the PREREG freeze (never claim "no effect"
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
    p_full = {h: 1.0 for h in HYPOTHESES}
    p_full.update(dict(zip(fam["hypothesis"], fam["p_raw"])))
    adj, rej = holm([p_full[h] for h in HYPOTHESES])
    adj_map = dict(zip(HYPOTHESES, adj))
    rej_map = dict(zip(HYPOTHESES, rej))
    fam["p_holm"] = [adj_map[h] for h in fam["hypothesis"]]
    fam["reject_holm"] = [bool(rej_map[h]) for h in fam["hypothesis"]]
    fam["status"] = [_status(r) for _, r in fam.iterrows()]
    fam["provisional"] = len(fam) < len(HYPOTHESES)
    return fam


def _status(row: pd.Series) -> str:
    if row["reject_holm"]:
        return "supported" if row["direction_ok"] else "reversed"
    margin = MARGIN_LOG_ODDS if row["scale"] == "log-odds" else MARGIN_RISK_DIFF
    lo, hi = row.get("ci_low", np.nan), row.get("ci_high", np.nan)
    if np.isfinite(lo) and np.isfinite(hi) and lo > -margin and hi < margin:
        return "not supported; CI inside margin (placeholder)"
    return "not supported; inconclusive"


__all__ = ["ALPHA", "HYPOTHESES", "assemble_family"]
