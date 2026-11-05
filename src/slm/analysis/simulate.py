"""Seeded simulator for the long-format probe table with KNOWN planted effects.

Latent model for P(stored) at the final checkpoint (conditional on random effects):

    logit = intercept + b_freq*freq_c + b_div*div_c + b_freq_div*freq_c*div_c
            + b_regime*regime_c + covariate terms
            + u_fact + w_seed + e_fact_seed + z_fact_regime + v_variant

Coding (identical to the analysis, see models.py): freq_c = {-1, 0, +1} for low/mid/high (one
step = one tripling of exposure), div_c = +-0.5 (paraphrased minus templated), regime_c = +-0.5
(novel minus iid). Earlier checkpoints interpolate toward a floor logit by an acquisition
curve, so the final checkpoint carries exactly the planted model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .schema import DIV_BINS, FREQ_BINS, MAX_RANK, REGIMES

ATTR_TYPES = ("time", "count", "person", "code")


@dataclass(frozen=True)
class SimParams:
    n_facts_per_cell: int = 20
    n_seeds: int = 3
    n_variants: int = 3
    n_checkpoints: int = 15
    first_step: int = 200
    last_step: int = 20000
    # planted fixed effects (log-odds, conditional on the random effects)
    intercept: float = -0.3
    b_freq: float = 0.9
    b_div: float = 0.7
    b_freq_div: float = -0.4
    b_regime: float = -0.8
    b_value_len: float = -0.15
    b_entity_freq: float = 0.2
    b_attr: tuple[float, ...] = (0.0, 0.3, -0.3, 0.1)
    # random-effect SDs
    sd_fact: float = 0.8
    sd_seed: float = 0.2
    sd_fact_seed: float = 0.8
    sd_fact_regime: float = 0.3
    sd_variant: float = 0.15
    # acquisition curve
    floor_logit: float = -5.0
    curve_mid_frac: float = 0.55
    curve_width: float = 0.15
    # share of non-stored rows that rank first but have binding <= 0 (frequency-prior hits)
    prior_hit_share: float = 0.15

    def with_effects(self, **kw: float) -> SimParams:
        return SimParams(**{**asdict(self), **kw})

    def null(self) -> SimParams:
        return self.with_effects(b_freq=0.0, b_div=0.0, b_freq_div=0.0, b_regime=0.0)


def planted_conditional(p: SimParams) -> dict[str, float]:
    """Planted (conditional-on-random-effects) log-odds per hypothesis."""
    return {"H1": p.b_freq, "H2": p.b_div, "H3": p.b_freq_div, "H4": p.b_regime}


def checkpoint_steps(p: SimParams) -> np.ndarray:
    steps = np.geomspace(p.first_step, p.last_step, p.n_checkpoints)
    return np.unique(np.round(steps).astype(int))


def _progress(steps: np.ndarray, p: SimParams) -> np.ndarray:
    """Acquisition progress g in [0, 1], exactly 0 at the first and 1 at the last step."""
    x = (np.log(steps) - np.log(steps[0])) / (np.log(steps[-1]) - np.log(steps[0]))

    def s(v: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-(v - p.curve_mid_frac) / p.curve_width))

    g = (s(x) - s(np.array(0.0))) / (s(np.array(1.0)) - s(np.array(0.0)))
    return np.clip(g, 0.0, 1.0)


def _facts(p: SimParams, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    n = 0
    for fi, fb in enumerate(FREQ_BINS):
        for db in DIV_BINS:
            for _ in range(p.n_facts_per_cell):
                n += 1
                rows.append((f"F{n:05d}", fb, db, fi - 1, 0.5 if db == "paraphrased" else -0.5))
    facts = pd.DataFrame(rows, columns=["fact_id", "freq_bin", "div_bin", "freq_c", "div_c"])
    facts["attr_type"] = [ATTR_TYPES[i % len(ATTR_TYPES)] for i in range(len(facts))]
    facts["value_len"] = rng.integers(2, 9, len(facts))
    facts["entity_freq"] = np.round(rng.normal(4.0, 0.8, len(facts)), 3)
    facts["u_fact"] = rng.normal(0.0, p.sd_fact, len(facts))
    return facts


def simulate_probe_table(
    p: SimParams | None = None, seed: int = 0, final_only: bool = False
) -> pd.DataFrame:
    """Simulate the probe table. `final_only` keeps just the last checkpoint (fast, for power)."""
    p = p or SimParams()
    rng = np.random.default_rng(seed)
    facts = _facts(p, rng)
    n_f = len(facts)
    steps = checkpoint_steps(p)
    progress = _progress(steps, p)
    if final_only:
        steps, progress = steps[-1:], progress[-1:]
    variants = [f"v{i + 1}" for i in range(p.n_variants)]

    w_seed = rng.normal(0.0, p.sd_seed, p.n_seeds)
    e_fs = rng.normal(0.0, p.sd_fact_seed, (n_f, p.n_seeds))
    z_fr = rng.normal(0.0, p.sd_fact_regime, (n_f, len(REGIMES)))
    v_var = rng.normal(0.0, p.sd_variant, p.n_variants)

    z_len = (facts["value_len"] - 5.0) / 2.0
    z_ent = (facts["entity_freq"] - 4.0) / 0.8
    attr_idx = facts["attr_type"].map({a: i for i, a in enumerate(ATTR_TYPES)}).to_numpy()
    fact_part = (
        p.intercept
        + p.b_freq * facts["freq_c"]
        + p.b_div * facts["div_c"]
        + p.b_freq_div * facts["freq_c"] * facts["div_c"]
        + p.b_value_len * z_len
        + p.b_entity_freq * z_ent
        + np.array(p.b_attr)[attr_idx]
        + facts["u_fact"]
    ).to_numpy()

    regime_c = np.array([-0.5, 0.5])  # iid, novel
    # axes: fact, seed, regime, variant -> final-checkpoint logit
    eta = (
        fact_part[:, None, None, None]
        + w_seed[None, :, None, None]
        + e_fs[:, :, None, None]
        + (p.b_regime * regime_c)[None, None, :, None]
        + z_fr[:, None, :, None]
        + v_var[None, None, None, :]
    )
    g = progress[None, None, None, None, :]
    logit = p.floor_logit + g * (eta[..., None] - p.floor_logit)
    prob = 1.0 / (1.0 + np.exp(-logit))
    stored = (rng.random(prob.shape) < prob).astype(int)

    fi, si, ri, vi, ci = (a.ravel() for a in np.indices(stored.shape))
    df = pd.DataFrame(
        {
            "fact_id": facts["fact_id"].to_numpy()[fi],
            "seed": si,
            "checkpoint": steps[ci],
            "regime": np.array(REGIMES)[ri],
            "freq_bin": facts["freq_bin"].to_numpy()[fi],
            "div_bin": facts["div_bin"].to_numpy()[fi],
            "prompt_variant": np.array(variants)[vi],
        }
    )
    st = stored.ravel()
    n = len(df)
    prior_hit = rng.random(n) < p.prior_hit_share
    wrong_rank = 2 + np.minimum(rng.geometric(0.5, n) - 1, MAX_RANK - 2)
    rank = np.where(st == 1, 1, np.where(prior_hit, 1, wrong_rank))
    pos = np.abs(rng.normal(1.5, 1.0, n)) + 0.05
    neg = -(np.abs(rng.normal(0.8, 0.5, n)) + 0.05)
    other = rng.normal(0.0, 1.0, n)
    binding = np.where(st == 1, pos, np.where(prior_hit, neg, other))
    df["rank"] = rank.astype(int)
    df["binding_score"] = np.round(binding, 4)
    df["stored"] = ((df["rank"] == 1) & (df["binding_score"] > 0)).astype(int)
    for col in ("attr_type", "value_len", "entity_freq"):
        df[col] = facts[col].to_numpy()[fi]
    order = ["checkpoint", "fact_id", "seed", "regime", "prompt_variant"]
    return df.sort_values(order).reset_index(drop=True)
