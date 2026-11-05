"""Seeded simulators with KNOWN planted effects: the probe table (H1, H2) and QA table (H3, H4).

Probe model for P(stored) at the final checkpoint (logit, conditional on random effects):

    intercept + b_freq*freq_c + b_div*div_c + b_freq_div*freq_c*div_c
      + (b_frame + b_div_frame*div_c) * frame_c + covariate terms
      + u_fact + w_seed + e_fact_seed + z_fact_frame + v_variant

Coding (identical to the analysis): freq_c = {-1, 0, +1} for low/mid/high (one step = one
tripling of exposure), div_c = +-0.5 (paraphrased minus templated), frame_c = +-0.5 (novel minus
canonical). With b_frame < 0 and b_div_frame > 0 templated facts lose ground on novel-frame probes
while paraphrased facts do not (DESIGN H2). Earlier checkpoints interpolate toward a floor logit
along an acquisition curve, so the final checkpoint carries exactly the planted model.

QA model (DESIGN section 7): each fact is assigned to SFT-train / SFT-val / held-out (40/10/50,
stratified by cell); E0/E1 use train facts, E2 the held-out facts, 3 questions each. The same
fact x seed latent difficulty is shared by the base and SFT models; stored facts extract better,
SFT lifts accuracy, and paraphrased facts get an extra direct SFT benefit (H4).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .schema import DIV_BINS, FRAMES, FREQ_BINS, MAX_RANK

ATTR_IDS = ("time", "count", "person", "code")
TEST_VARIANTS = ("test-canon", "test-n1", "test-n2", "test-n3")
VAL_VARIANTS = ("val-canon", "val-n1")
FRAME_C = {"canonical": -0.5, "novel": 0.5}


def variant_frame(variant: str) -> str:
    return "canonical" if variant.endswith("canon") else "novel"


@dataclass(frozen=True)
class SimParams:
    n_facts_per_cell: int = 20
    n_seeds: int = 3
    n_checkpoints: int = 15
    first_step: int = 200
    last_step: int = 20000
    # planted probe effects (log-odds, conditional on the random effects)
    intercept: float = -0.3
    b_freq: float = 0.9
    b_div: float = 0.3
    b_frame: float = -0.5
    b_div_frame: float = 1.0
    b_freq_div: float = -0.4
    b_value_len: float = -0.15
    b_entity_freq: float = 0.2
    b_attr: tuple[float, ...] = (0.0, 0.3, -0.3, 0.1)
    # random-effect SDs
    sd_fact: float = 0.8
    sd_seed: float = 0.2
    sd_fact_seed: float = 0.8
    sd_fact_frame: float = 0.3
    sd_variant: float = 0.15
    # acquisition curve
    floor_logit: float = -5.0
    curve_mid_frac: float = 0.55
    curve_width: float = 0.15
    # share of non-stored rows that rank first but have binding <= 0 (frequency-prior hits)
    prior_hit_share: float = 0.15
    # QA / SFT model (logits)
    n_questions: int = 3
    base2_intercept: float = -3.0
    base2_stored: float = 1.0
    base0_intercept: float = -4.0
    base0_stored: float = 0.6
    sft_intercept: float = -1.5
    sft_stored: float = 2.2
    sft_div: float = 0.6  # direct SFT benefit of paraphrased facts (per unit of div_c)
    e0_offset: float = 2.5
    e1_offset: float = 1.5
    sd_fact_qa: float = 0.7
    sd_fact_seed_qa: float = 0.5

    def with_effects(self, **kw) -> SimParams:
        return SimParams(**{**asdict(self), **kw})

    def null_probe(self) -> SimParams:
        """No exposure, diversity, frame or interaction effects on storage."""
        return self.with_effects(
            b_freq=0.0, b_div=0.0, b_frame=0.0, b_div_frame=0.0, b_freq_div=0.0
        )

    def null_extraction(self) -> SimParams:
        """SFT identical to the base model: no gain, no stored effect beyond the base's, no div."""
        return self.with_effects(
            sft_intercept=self.base2_intercept, sft_stored=self.base2_stored, sft_div=0.0
        )

    def null(self) -> SimParams:
        return self.null_probe().null_extraction()

    def null_diversity_gain(self) -> SimParams:
        """Probe effects off and no direct diversity benefit; extraction itself stays active."""
        return self.null_probe().with_effects(sft_div=0.0)


def planted_conditional(p: SimParams) -> dict[str, float]:
    """Planted (conditional) log-odds for the two probe-table hypotheses."""
    return {"H1": p.b_freq, "H2": p.b_div_frame}


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
    facts["attribute_id"] = [ATTR_IDS[i % len(ATTR_IDS)] for i in range(len(facts))]
    facts["value_len"] = rng.integers(2, 9, len(facts))
    facts["entity_freq"] = np.round(rng.normal(4.0, 0.8, len(facts)), 3)
    facts["u_fact"] = rng.normal(0.0, p.sd_fact, len(facts))
    return facts


def simulate_probe_table(
    p: SimParams | None = None,
    seed: int = 0,
    final_only: bool = False,
    include_val: bool = False,
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
    variants = list(TEST_VARIANTS) + (list(VAL_VARIANTS) if include_val else [])
    frame_idx = np.array([FRAMES.index(variant_frame(v)) for v in variants])
    frame_c = np.array([FRAME_C[variant_frame(v)] for v in variants])

    w_seed = rng.normal(0.0, p.sd_seed, p.n_seeds)
    e_fs = rng.normal(0.0, p.sd_fact_seed, (n_f, p.n_seeds))
    z_ff = rng.normal(0.0, p.sd_fact_frame, (n_f, len(FRAMES)))
    v_var = rng.normal(0.0, p.sd_variant, len(variants))

    z_len = (facts["value_len"] - 5.0) / 2.0
    z_ent = (facts["entity_freq"] - 4.0) / 0.8
    attr_idx = facts["attribute_id"].map({a: i for i, a in enumerate(ATTR_IDS)}).to_numpy()
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
    frame_slope = p.b_frame + p.b_div_frame * facts["div_c"].to_numpy()  # per fact

    # axes: fact, seed, variant -> final-checkpoint logit
    eta = (
        fact_part[:, None, None]
        + w_seed[None, :, None]
        + e_fs[:, :, None]
        + frame_slope[:, None, None] * frame_c[None, None, :]
        + z_ff[:, frame_idx][:, None, :]
        + v_var[None, None, :]
    )
    g = progress[None, None, None, :]
    logit = p.floor_logit + g * (eta[..., None] - p.floor_logit)
    prob = 1.0 / (1.0 + np.exp(-logit))
    stored = (rng.random(prob.shape) < prob).astype(int)

    fi, si, vi, ci = (a.ravel() for a in np.indices(stored.shape))
    df = pd.DataFrame(
        {
            "fact_id": facts["fact_id"].to_numpy()[fi],
            "seed": si,
            "checkpoint": steps[ci],
            "probe_frame": np.array(FRAMES)[frame_idx[vi]],
            "freq_bin": facts["freq_bin"].to_numpy()[fi],
            "div_bin": facts["div_bin"].to_numpy()[fi],
            "prompt_variant": np.array(variants)[vi],
        }
    )
    df["split"] = np.where(df["prompt_variant"].str.startswith("val"), "val", "test")
    st = stored.ravel()
    n = len(df)
    prior_hit = rng.random(n) < p.prior_hit_share
    wrong_rank = 2 + np.minimum(rng.geometric(0.5, n) - 1, MAX_RANK - 2)
    rank = np.where(st == 1, 1, np.where(prior_hit, 1, wrong_rank))
    pos = np.abs(rng.normal(1.5, 1.0, n)) + 0.05
    neg = -(np.abs(rng.normal(0.8, 0.5, n)) + 0.05)
    other = rng.normal(0.0, 1.0, n)
    binding = np.round(np.where(st == 1, pos, np.where(prior_hit, neg, other)), 4)
    baseline = np.round(rng.normal(-7.0, 1.0, n), 4)
    df["rank"] = rank.astype(int)
    df["binding_score"] = binding
    df["baseline_logprob"] = baseline
    df["true_logprob"] = np.round(baseline + binding, 4)
    df["stored"] = ((df["rank"] == 1) & (df["binding_score"] > 0)).astype(int)
    for col in ("attribute_id", "value_len", "entity_freq"):
        df[col] = facts[col].to_numpy()[fi]
    order = ["checkpoint", "fact_id", "seed", "prompt_variant"]
    return df.sort_values(order).reset_index(drop=True)


def fact_seed_stored(probe: pd.DataFrame) -> pd.DataFrame:
    """Per fact x seed `stored_pretrain`: stored in at least half of the test probes, final ckpt."""
    test = probe[(probe["split"] == "test") & (probe["checkpoint"] == probe["checkpoint"].max())]
    out = test.groupby(["fact_id", "seed"])["stored"].mean().ge(0.5).astype(int)
    return out.rename("stored_pretrain").reset_index()


def assign_sft_split(facts: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    """40% SFT-train / 10% SFT-val / 50% held-out, stratified by freq x div cell."""
    labels = pd.Series("heldout", index=facts.index, dtype=object)
    for _, idx in facts.groupby(["freq_bin", "div_bin"]).groups.items():
        idx = np.array(list(idx))
        perm = rng.permutation(idx)
        n_train = int(round(0.4 * len(idx)))
        n_val = int(round(0.1 * len(idx)))
        labels.loc[perm[:n_train]] = "train"
        labels.loc[perm[n_train : n_train + n_val]] = "val"
    return labels


def simulate_qa_table(p: SimParams, probe: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Simulate E0/E1/E2 outcomes for base_0shot, base_2shot and sft given a probe table."""
    rng = np.random.default_rng(seed)
    facts = probe.groupby("fact_id")[["freq_bin", "div_bin"]].first().reset_index()
    facts["sft_split"] = assign_sft_split(facts, rng)
    facts = facts[facts["sft_split"] != "val"].reset_index(drop=True)  # SFT-val is never evaluated
    n_f = len(facts)
    seeds = np.arange(p.n_seeds)
    u = rng.normal(0.0, p.sd_fact_qa, n_f)
    e = rng.normal(0.0, p.sd_fact_seed_qa, (n_f, p.n_seeds))
    stored = (
        facts[["fact_id"]]
        .merge(fact_seed_stored(probe), on="fact_id", how="left")
        .pivot(index="fact_id", columns="seed", values="stored_pretrain")
        .reindex(facts["fact_id"])
        .to_numpy()
    )
    div_c = facts["div_bin"].map({"templated": -0.5, "paraphrased": 0.5}).to_numpy()
    offsets = {"E0": p.e0_offset, "E1": p.e1_offset, "E2": 0.0}
    parts = []
    for es in ("E0", "E1", "E2"):
        is_train = es != "E2"
        sel = np.where((facts["sft_split"] == "train").to_numpy() == is_train)[0]
        for j in range(p.n_questions):
            q_eff = rng.normal(0.0, 0.15)
            latent = u[sel, None] + e[sel, :] + q_eff
            st = stored[sel, :]
            logit = {
                "base_0shot": p.base0_intercept + p.base0_stored * st + latent,
                "base_2shot": p.base2_intercept + p.base2_stored * st + latent,
                "sft": p.sft_intercept
                + p.sft_stored * st
                + p.sft_div * div_c[sel, None]
                + offsets[es]
                + latent,
            }
            for model, lg in logit.items():
                correct = (rng.random(lg.shape) < 1.0 / (1.0 + np.exp(-lg))).astype(int)
                fi, si = np.indices(lg.shape)
                fi, si = fi.ravel(), si.ravel()
                parts.append(
                    pd.DataFrame(
                        {
                            "fact_id": facts["fact_id"].to_numpy()[sel][fi],
                            "seed": seeds[si],
                            "eval_set": es,
                            "question_id": [
                                f"{f}-{es}-q{j}" for f in facts["fact_id"].to_numpy()[sel][fi]
                            ],
                            "model": model,
                            "exact_match": correct.ravel(),
                            "stored_pretrain": st[fi, si].astype(int),
                            "freq_bin": facts["freq_bin"].to_numpy()[sel][fi],
                            "div_bin": facts["div_bin"].to_numpy()[sel][fi],
                            "sft_split": facts["sft_split"].to_numpy()[sel][fi],
                        }
                    )
                )
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values(["eval_set", "model", "fact_id", "seed", "question_id"]).reset_index(
        drop=True
    )
