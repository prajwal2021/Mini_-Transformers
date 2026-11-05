"""Fact-level aggregation rules (PREREG v3 section 4).

A fact is "stored" when it is stored on at least 2 of its 3 test probes at the final checkpoint,
and "QA-correct" when it is correct on at least 2 of its 3 E2 phrasings. With n items that is
"more than half". `any` and `all` are the sensitivity rules. The same rule is applied at both
levels (items within a seed, then seeds within a fact).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RULES = ("any", "majority", "all")
PRIMARY_RULE = "majority"


def apply_rule(share: pd.Series | np.ndarray, rule: str = PRIMARY_RULE) -> pd.Series | np.ndarray:
    """Map a share of positive items in [0, 1] to a 0/1 decision."""
    if rule == "any":
        out = share > 1e-12
    elif rule == "majority":
        out = share > 0.5 + 1e-12
    elif rule == "all":
        out = share >= 1.0 - 1e-12
    else:
        raise ValueError(f"unknown rule {rule!r}; expected one of {RULES}")
    return out.astype(int)


def stored_by_fact_seed(probe: pd.DataFrame, rule: str = PRIMARY_RULE) -> pd.DataFrame:
    """Per fact x seed stored status from the probe rows already restricted to the primary
    checkpoint and the test split. Returns fact_id, seed, stored_pretrain."""
    share = probe.groupby(["fact_id", "seed"])["stored"].mean()
    return apply_rule(share, rule).rename("stored_pretrain").reset_index()
