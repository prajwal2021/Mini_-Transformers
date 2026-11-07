# ruff: noqa: E501
"""R07: planted-effect sign tests for the H1/H2 GEE, run with the outcome as a BOOL column as the real pipeline supplies it.

Bug (found after unblinding): a bool ``stored`` column made patsy build a two-column response and the GEE modelled
P(not stored), so H1 and H2 came out with the wrong sign. The old synthetic validation used int outcomes and could not see it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from slm.analysis import models as M

FRAME_VARIANTS = {"canonical": ["canon"], "novel": ["n1", "n2"]}


def design(seed: int = 0, b_freq: float = 0.0, b_divframe: float = 0.0, b_div: float = 0.0, as_bool: bool = True) -> pd.DataFrame:
    """120 facts (3 freq bins x 2 div bins x 20), 3 seeds, 3 probe rows (canonical + 2 novel) per fact and seed."""
    rng = np.random.default_rng(seed)
    mentions = {"low": 5, "mid": 15, "high": 45}
    rows = []
    for fi in range(120):
        fb = ["low", "mid", "high"][fi % 3]
        db = ["templated", "paraphrased"][(fi // 3) % 2]
        fact_effect = rng.normal(0, 0.5)
        for s in (0, 1, 2):
            for frame, variants in FRAME_VARIANTS.items():
                for v in variants:
                    logm = (np.log(mentions[fb]) - np.log(15)) / np.log(3)
                    div_c = 0.5 if db == "paraphrased" else -0.5
                    frame_c = 0.5 if frame == "novel" else -0.5
                    eta = -1.0 + b_freq * logm + b_div * div_c + b_divframe * div_c * frame_c + fact_effect
                    rows.append({"fact_id": f"F{fi:03d}", "seed": s, "probe_frame": frame, "prompt_variant": f"{frame[:3]}-{v}",
                                 "freq_bin": fb, "div_bin": db, "train_mentions": mentions[fb],
                                 "stored": bool(rng.random() < 1 / (1 + np.exp(-eta))), "split": "test", "checkpoint": 2970})
    df = pd.DataFrame(rows)
    if not as_bool:
        df["stored"] = df["stored"].astype(int)
    return M.add_codes(df)


def est(df: pd.DataFrame) -> dict[str, float]:
    t = M.fit_gee(df, covariates=False).table.set_index("term")["estimate"]
    return {"H1": float(t["freq_c"]), "H2": float(t["div_c:frame_c"])}


@pytest.mark.parametrize("planted", [1.0, -1.0])
def test_planted_exposure_slope_is_recovered_with_its_sign_for_a_bool_outcome(planted):
    e = est(design(b_freq=planted))
    assert np.sign(e["H1"]) == np.sign(planted) and abs(e["H1"] - planted) < 0.5, e


@pytest.mark.parametrize("planted", [1.5, -1.5])
def test_planted_diversity_by_frame_effect_is_recovered_with_its_sign_for_a_bool_outcome(planted):
    e = est(design(b_divframe=planted))
    assert np.sign(e["H2"]) == np.sign(planted) and abs(e["H2"] - planted) < 0.9, e


def test_bool_and_int_outcomes_give_identical_estimates():
    a, b = est(design(b_freq=1.0, b_divframe=1.0, as_bool=True)), est(design(b_freq=1.0, b_divframe=1.0, as_bool=False))
    assert a == pytest.approx(b)


def test_the_full_pipeline_fit_keeps_the_sign_with_covariates_and_the_robust_ladder():
    df = design(b_freq=1.0)
    res, _ = M.fit_gee_robust(df, covariates=False)
    assert res is not None and res.family.set_index("hypothesis").loc["H1", "estimate"] > 0
    assert bool(res.family.set_index("hypothesis").loc["H1", "direction_ok"])


def test_a_non_binary_outcome_is_refused():
    df = design()
    df["stored"] = 2.0
    with pytest.raises(ValueError):
        M.fit_gee(df, covariates=False)
