"""Storage model for H1 and H2 (DESIGN section 8, Part A): logistic GEE with fact clusters.

DESIGN's model:  stored ~ log(exposure) * diversity * frame + value_len + entity_freq + attr_type
                         + (1 | fact) + (1 | template) + (1 | seed)

Implemented as (fitted at the primary checkpoint, test probes only):

    stored ~ freq_c * div_c * frame_c + C(seed) + within-frame template dummies
             [+ value_len_z + entity_freq_z + C(attribute_id)]

    family = Binomial(logit); groups = fact_id; working correlation = exchangeable;
    covariance = bias-reduced robust sandwich (Mancl-DeRouen) with t(G - p) critical values.

Coding: freq_c = log3(measured train mentions) centred on its mean when `train_mentions` is in the
table, otherwise the design bin code {-1, 0, +1} (bins are ~5/15/45 documents, a factor of 3 apart,
so the code is log3-linear). div_c = +-0.5 (paraphrased minus templated), frame_c = +-0.5 (novel
minus canonical). With effect coding the main effects are averaged effects of the full factorial.

H1 = coefficient `freq_c`; H2 = coefficient `div_c:frame_c` (paraphrased advantage grows from the
canonical to the novel frame). Holm is applied across H1-H4 in `family.py`, not here.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

from .schema import (
    FRAMES,
    PROBE_OPTIONAL,
    normalize_probe_table,
    validate_probe_table,
    validate_realized_diversity,
)

# hypothesis id -> (coefficient name, predicted sign, label); H3/H4 live in extraction.py
PROBE_FAMILY: dict[str, tuple[str, int, str]] = {
    "H1": ("freq_c", +1, "storage rises with log exposure (per tripling)"),
    "H2": ("div_c:frame_c", +1, "diversity x frame (paraphrased advantage, novel - canonical)"),
}
ALPHA = 0.05
DIV_CODE = {"templated": -0.5, "paraphrased": 0.5}
FRAME_CODE = {"canonical": -0.5, "novel": 0.5}
FREQ_BIN_CODE = {"low": -1.0, "mid": 0.0, "high": 1.0}


@dataclass
class GeeResult:
    table: pd.DataFrame  # one row per coefficient
    family: pd.DataFrame  # H1, H2 with raw p (no multiplicity correction)
    simple: pd.DataFrame  # supporting simple effects of diversity within each frame
    n_rows: int
    n_clusters: int
    converged: bool
    covariance: str
    formula: str
    warnings: list[str]


def primary_checkpoint(df: pd.DataFrame, checkpoint: int | str = "final") -> int:
    """Resolve the primary checkpoint; "final" = largest checkpoint present in every seed."""
    if checkpoint != "final":
        return int(checkpoint)
    common = set.intersection(*(set(g) for g in df.groupby("seed")["checkpoint"].unique()))
    if not common:
        raise ValueError("no checkpoint is present in every seed")
    return int(max(common))


def final_by_seed(df: pd.DataFrame) -> pd.Series:
    """Final (largest) checkpoint of each seed."""
    return df.groupby("seed")["checkpoint"].max()


def add_realized_diversity(df: pd.DataFrame, rd: pd.DataFrame) -> pd.DataFrame:
    """Join realized diversity: rdiv_z = z(1 - mean_pairwise_jaccard), standardised over facts."""
    validate_realized_diversity(rd, set(df["fact_id"]))
    per_fact = (1.0 - rd.set_index("fact_id")["mean_pairwise_jaccard"]).loc[
        sorted(set(df["fact_id"]))
    ]
    z = (per_fact - per_fact.mean()) / (per_fact.std(ddof=0) or 1.0)
    out = df.copy()
    out["rdiv_z"] = out["fact_id"].map(z).astype(float)
    return out


def add_codes(df: pd.DataFrame, exposure: str = "auto") -> pd.DataFrame:
    """Add model columns: freq_c, div_c, frame_c, standardised covariates, template dummies.

    exposure: "auto" (log3 of `train_mentions` if present, else bin codes), "bins", "measured".
    """
    out = df.copy()
    use_measured = "train_mentions" in out and exposure in ("auto", "measured")
    if exposure == "measured" and "train_mentions" not in out:
        raise ValueError("exposure='measured' needs a train_mentions column")
    if use_measured:
        per_fact = out.groupby("fact_id")["train_mentions"].first()
        logm = np.log(per_fact.clip(lower=1)) / np.log(3.0)
        out["freq_c"] = out["fact_id"].map(logm - logm.mean()).astype(float)
    else:
        out["freq_c"] = out["freq_bin"].map(FREQ_BIN_CODE).astype(float)
    out["div_c"] = out["div_bin"].map(DIV_CODE).astype(float)
    out["frame_c"] = out["probe_frame"].map(FRAME_CODE).astype(float)
    for col in ("value_len", "entity_freq"):
        if col in out:
            sd = out[col].std(ddof=0) or 1.0
            out[f"{col}_z"] = (out[col] - out[col].mean()) / sd
    # (1 | template): variants are nested in frames, so use fixed dummies for all but the first
    # variant of each frame (a full set would be collinear with frame_c)
    k = 0
    for frame in FRAMES:
        variants = sorted(out.loc[out["probe_frame"] == frame, "prompt_variant"].unique())
        for v in variants[1:]:
            k += 1
            out[f"pv_{k}"] = (out["prompt_variant"] == v).astype(float)
    return out


DIVERSITY_MODES = ("nominal", "realized", "both")


def build_formula(
    df: pd.DataFrame,
    covariates: bool = True,
    outcome: str = "stored",
    variant_terms: bool = True,
    diversity: str = "nominal",
) -> str:
    if diversity not in DIVERSITY_MODES:
        raise ValueError(f"diversity must be one of {DIVERSITY_MODES}")
    core = {
        "nominal": "freq_c * div_c * frame_c",
        "realized": "freq_c * rdiv_z * frame_c",
        "both": "freq_c * div_c * frame_c + rdiv_z + rdiv_z:frame_c",
    }[diversity]
    terms = [core]
    if df["seed"].nunique() > 1:
        terms.append("C(seed)")
    if variant_terms:
        terms += [c for c in df.columns if c.startswith("pv_")]
    if covariates:
        for col in ("value_len_z", "entity_freq_z"):
            if col in df and df[col].nunique() > 1:
                terms.append(col)
        if "attribute_id" in df and df["attribute_id"].nunique() > 1:
            terms.append("C(attribute_id)")
    return f"{outcome} ~ " + " + ".join(terms)


def holm(pvalues: list[float] | np.ndarray, alpha: float = ALPHA) -> tuple[np.ndarray, np.ndarray]:
    """Holm step-down: return (adjusted p-values, reject flags) in the input order."""
    p = np.asarray(pvalues, dtype=float)
    m = len(p)
    order = np.argsort(p, kind="stable")
    adj_sorted = np.maximum.accumulate((m - np.arange(m)) * p[order])
    adj = np.empty(m)
    adj[order] = np.minimum(adj_sorted, 1.0)
    return adj, adj <= alpha


def _numeric_outcome(df: pd.DataFrame, outcome: str) -> pd.DataFrame:
    """The outcome column as float 0/1.

    A bool column makes patsy build a two-column response (``stored[False]``, ``stored[True]``) and
    the GEE then models the FIRST column, i.e. P(not stored): every coefficient comes out with the
    wrong sign (R07, a post-unblinding bug; tests/test_r07_sign.py).
    """
    if outcome not in df.columns:
        return df
    y = pd.to_numeric(df[outcome].astype(float))
    if not y.isin([0.0, 1.0]).all():
        raise ValueError(f"outcome {outcome!r} must be 0/1")
    return df.assign(**{outcome: y})


def fit_gee(
    df: pd.DataFrame,
    covariates: bool = True,
    covariance: str = "bias_reduced",
    cov_struct: str = "exchangeable",
    outcome: str = "stored",
    variant_terms: bool = True,
    diversity: str = "nominal",
) -> GeeResult:
    """Fit the logistic GEE on a single-checkpoint, test-split table."""
    if "freq_c" not in df:
        df = add_codes(df)
    df = _numeric_outcome(df, outcome)
    formula = build_formula(df, covariates, outcome, variant_terms, diversity)
    h2_term = "rdiv_z:frame_c" if diversity == "realized" else "div_c:frame_c"
    notes: list[str] = []
    cs = (
        sm.cov_struct.Exchangeable()
        if cov_struct == "exchangeable"
        else sm.cov_struct.Independence()
    )
    model = smf.gee(
        formula, groups="fact_id", data=df, family=sm.families.Binomial(), cov_struct=cs
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res = model.fit(cov_type=covariance)
    notes += sorted({str(w.message) for w in caught})
    converged = bool(getattr(res, "converged", True))
    if not converged:
        notes.append("GEE did not converge")
    n_clusters = int(df["fact_id"].nunique())
    dof = max(n_clusters - len(res.params), 1)
    se = res.bse
    tcrit = stats.t.ppf(0.975, dof)
    tval = res.params / se
    table = pd.DataFrame(
        {
            "term": res.params.index,
            "estimate": res.params.to_numpy(),
            "se": se.to_numpy(),
            "t": tval.to_numpy(),
            "p_raw": 2 * stats.t.sf(np.abs(tval), dof),
            "ci_low": (res.params - tcrit * se).to_numpy(),
            "ci_high": (res.params + tcrit * se).to_numpy(),
        }
    )
    table["odds_ratio"] = np.exp(table["estimate"])
    table["or_ci_low"] = np.exp(table["ci_low"])
    table["or_ci_high"] = np.exp(table["ci_high"])

    rows = []
    for hid, (term, sign, label) in PROBE_FAMILY.items():
        term = h2_term if hid == "H2" else term
        r = table.loc[table["term"] == term].iloc[0]
        rows.append(
            {
                "hypothesis": hid,
                "label": label,
                "predicted_sign": sign,
                "estimate": r["estimate"],
                "ci_low": r["ci_low"],
                "ci_high": r["ci_high"],
                "p_raw": r["p_raw"],
                "direction_ok": bool(np.sign(r["estimate"]) == sign),
            }
        )
    family = pd.DataFrame(rows)

    cov = res.cov_params()
    srows = []
    for frame, f in FRAME_CODE.items() if diversity != "realized" else []:
        est = res.params["div_c"] + f * res.params["div_c:frame_c"]
        var = (
            cov.loc["div_c", "div_c"]
            + f * f * cov.loc["div_c:frame_c", "div_c:frame_c"]
            + 2 * f * cov.loc["div_c", "div_c:frame_c"]
        )
        s = float(np.sqrt(max(var, 0.0)))
        srows.append(
            {
                "frame": frame,
                "div_effect_log_odds": float(est),
                "ci_low": float(est - tcrit * s),
                "ci_high": float(est + tcrit * s),
            }
        )
    label = f"{cov_struct}/{covariance}+t"
    return GeeResult(
        table,
        family,
        pd.DataFrame(srows, columns=["frame", "div_effect_log_odds", "ci_low", "ci_high"]),
        len(df),
        n_clusters,
        converged,
        label,
        formula,
        notes,
    )


SEPARATION_BOUND = 8.0  # |coefficient| or SE above this on the log-odds scale = separation


def check_separation(df: pd.DataFrame, outcome: str = "stored") -> pd.DataFrame:
    """Design cells (freq x div x frame) whose outcome is all 0 or all 1 (separation risk)."""
    cells = df.groupby(["freq_bin", "div_bin", "probe_frame"])[outcome].agg(["mean", "size"])
    return cells[(cells["mean"] <= 0.0) | (cells["mean"] >= 1.0)].reset_index()


def _fit_ok(res: GeeResult) -> bool:
    t = res.table
    finite = np.isfinite(t[["estimate", "se"]].to_numpy()).all()
    return bool(
        res.converged
        and finite
        and (t["estimate"].abs() < SEPARATION_BOUND).all()
        and (t["se"] < SEPARATION_BOUND).all()
    )


def fit_gee_robust(
    df: pd.DataFrame, covariates: bool = True, **kwargs
) -> tuple[GeeResult | None, list[str]]:
    """The pre-registered fallback ladder: primary fit; then independence working correlation;
    then no optional covariates. Returns (result or None, log). A fit that fails to converge, is
    non-finite or shows separation (|coef| or SE > 8) counts as failed. The order never depends
    on p-values. None = non-informative (the affected tests are reported as such)."""
    log: list[str] = []
    ladder = [
        ("primary", dict(covariates=covariates)),
        ("independence", dict(covariates=covariates, cov_struct="independence")),
        ("no covariates", dict(covariates=False, cov_struct="independence")),
    ]
    sep = check_separation(df, kwargs.get("outcome", "stored"))
    if len(sep):
        log.append(f"{len(sep)} design cell(s) with outcome all 0 or all 1 (separation risk)")
    for name, extra in ladder:
        try:
            res = fit_gee(df, **{**kwargs, **extra})
        except Exception as exc:  # singular design, etc.
            log.append(f"{name}: failed ({type(exc).__name__})")
            continue
        if _fit_ok(res):
            if name != "primary":
                log.append(f"fallback used: {name}")
            return res, log
        log.append(f"{name}: not usable (non-convergence, non-finite or separation)")
    log.append("all fits failed: H1/H2 are non-informative")
    return None, log


def prepare_primary(
    df: pd.DataFrame, checkpoint: int | str = "final", exposure: str = "auto"
) -> tuple[pd.DataFrame, int, list[str]]:
    """Normalize + validate the probe table; return (coded primary rows, checkpoint, warnings).

    "final" = the final checkpoint of each seed (PREREG v3); the returned checkpoint is the
    largest of them. An explicit step selects that checkpoint in every seed.
    """
    df = normalize_probe_table(df)
    warns = validate_probe_table(df)
    test = df[df["split"] == "test"]
    if checkpoint == "final":
        finals = final_by_seed(test)
        sub = test[test["checkpoint"] == test["seed"].map(finals)]
        ck = int(finals.max())
        if finals.nunique() > 1:
            warns.append(f"final checkpoints differ across seeds: {finals.to_dict()}")
    else:
        ck = int(checkpoint)
        sub = test[test["checkpoint"] == ck]
    return add_codes(sub, exposure), ck, warns


def fit_primary(df: pd.DataFrame, checkpoint: int | str = "final", covariates: bool = True):
    """Validate, subset to the primary checkpoint (test split), code and fit."""
    sub, ck, _ = prepare_primary(df, checkpoint)
    has_cov = covariates and any(c in sub.columns for c in PROBE_OPTIONAL + ("attribute_id",))
    return fit_gee(sub, covariates=has_cov), ck


def fit_bayes_mixed(
    df: pd.DataFrame,
    covariates: bool = True,
    variant_terms: bool = True,
    outcome: str = "stored",
) -> pd.DataFrame:
    """Sensitivity only: conditional logit with fact and fact-by-seed random intercepts (VB).

    Posterior SDs of the variational approximation are known to be too small, so this is
    reported as point estimates and is NOT part of the confirmatory family.
    """
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

    if "freq_c" not in df:
        df = add_codes(df)
    df = _numeric_outcome(df, outcome)
    formula = build_formula(df, covariates, outcome, variant_terms)
    df = df.assign(fact_seed=df["fact_id"].astype(str) + "/" + df["seed"].astype(str))
    model = BinomialBayesMixedGLM.from_formula(
        formula,
        {"fact": "0 + C(fact_id)", "fact_seed": "0 + C(fact_seed)"},
        df,
        vcp_p=1.0,
        fe_p=3.0,
    )
    res = model.fit_vb()
    out = pd.DataFrame(
        {"term": list(model.exog_names), "estimate": res.fe_mean, "posterior_sd": res.fe_sd}
    )
    out["fact_sd"] = float(np.exp(res.vcp_mean[0]))
    out["fact_seed_sd"] = float(np.exp(res.vcp_mean[1]))
    return out
