"""Pre-registered storage model: logistic GEE with fact clusters, plus Holm correction.

Primary model (fitted at the primary checkpoint, see PREREG):

    stored ~ freq_c * div_c * regime_c + C(seed) + C(prompt_variant)
             [+ value_len_z + entity_freq_z + C(attr_type)]      (optional covariates)

    family  = Binomial(logit); groups = fact_id; working correlation = exchangeable;
    covariance = bias-reduced robust sandwich (Mancl-DeRouen) with t(G - p) critical values.

Coding: freq_c in {-1, 0, +1} (low/mid/high; one step = one tripling of exposure, i.e.
log-exposure is linear in the code), div_c = +-0.5 (paraphrased minus templated), regime_c =
+-0.5 (novel minus iid). With this effect coding the four family coefficients are averaged
(main) effects of the full factorial and `freq_c:div_c` is the slope-by-diversity interaction.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

from .schema import OPTIONAL_COVARIATES, validate_table

# Pre-registered family: hypothesis id -> (coefficient name, predicted sign, label)
FAMILY: dict[str, tuple[str, int, str]] = {
    "H1": ("freq_c", +1, "frequency slope (per tripling of exposure)"),
    "H2": ("div_c", +1, "diversity (paraphrased - templated)"),
    "H3": ("freq_c:div_c", 0, "frequency x diversity interaction"),
    "H4": ("regime_c", -1, "regime (novel - iid)"),
}
ALPHA = 0.05
FREQ_CODE = {"low": -1.0, "mid": 0.0, "high": 1.0}
DIV_CODE = {"templated": -0.5, "paraphrased": 0.5}
REGIME_CODE = {"iid": -0.5, "novel": 0.5}


@dataclass
class GeeResult:
    table: pd.DataFrame  # one row per coefficient
    family: pd.DataFrame  # H1-H4 with raw and Holm p-values
    n_rows: int
    n_clusters: int
    converged: bool
    covariance: str
    formula: str
    warnings: list[str]


def primary_checkpoint(df: pd.DataFrame, checkpoint: int | str = "final") -> int:
    """Resolve the primary checkpoint; "final" is the largest checkpoint present in every seed."""
    if checkpoint != "final":
        return int(checkpoint)
    common = set.intersection(*(set(g) for g in df.groupby("seed")["checkpoint"].unique()))
    if not common:
        raise ValueError("no checkpoint is present in every seed")
    return int(max(common))


def add_codes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["freq_c"] = out["freq_bin"].map(FREQ_CODE).astype(float)
    out["div_c"] = out["div_bin"].map(DIV_CODE).astype(float)
    out["regime_c"] = out["regime"].map(REGIME_CODE).astype(float)
    if "value_len" in out:
        out["value_len_z"] = (out["value_len"] - out["value_len"].mean()) / (
            out["value_len"].std(ddof=0) or 1.0
        )
    if "entity_freq" in out:
        out["entity_freq_z"] = (out["entity_freq"] - out["entity_freq"].mean()) / (
            out["entity_freq"].std(ddof=0) or 1.0
        )
    return out


def build_formula(df: pd.DataFrame, covariates: bool = True) -> str:
    terms = ["freq_c * div_c * regime_c"]
    if df["seed"].nunique() > 1:
        terms.append("C(seed)")
    if df["prompt_variant"].nunique() > 1:
        terms.append("C(prompt_variant)")
    if covariates:
        if "value_len_z" in df and df["value_len_z"].nunique() > 1:
            terms.append("value_len_z")
        if "entity_freq_z" in df and df["entity_freq_z"].nunique() > 1:
            terms.append("entity_freq_z")
        if "attr_type" in df and df["attr_type"].nunique() > 1:
            terms.append("C(attr_type)")
    return "stored ~ " + " + ".join(terms)


def holm(pvalues: list[float] | np.ndarray, alpha: float = ALPHA) -> tuple[np.ndarray, np.ndarray]:
    """Holm step-down: return (adjusted p-values, reject flags) in the input order."""
    p = np.asarray(pvalues, dtype=float)
    m = len(p)
    order = np.argsort(p, kind="stable")
    adj_sorted = np.maximum.accumulate((m - np.arange(m)) * p[order])
    adj = np.empty(m)
    adj[order] = np.minimum(adj_sorted, 1.0)
    return adj, adj <= alpha


def fit_gee(
    df: pd.DataFrame,
    covariates: bool = True,
    covariance: str = "bias_reduced",
    cov_struct: str = "exchangeable",
) -> GeeResult:
    """Fit the logistic GEE on a single-checkpoint table (rows already coded)."""
    if "freq_c" not in df:
        df = add_codes(df)
    formula = build_formula(df, covariates)
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
    n_params = len(res.params)
    dof = max(n_clusters - n_params, 1)
    se = res.bse
    tcrit = stats.t.ppf(0.975, dof)
    z = res.params / se
    pvals = 2 * stats.t.sf(np.abs(z), dof)
    table = pd.DataFrame(
        {
            "term": res.params.index,
            "estimate": res.params.to_numpy(),
            "se": se.to_numpy(),
            "t": z.to_numpy(),
            "p_raw": pvals,
            "ci_low": (res.params - tcrit * se).to_numpy(),
            "ci_high": (res.params + tcrit * se).to_numpy(),
        }
    )
    table["odds_ratio"] = np.exp(table["estimate"])
    table["or_ci_low"] = np.exp(table["ci_low"])
    table["or_ci_high"] = np.exp(table["ci_high"])
    fam_rows = []
    for hid, (term, sign, label) in FAMILY.items():
        row = table.loc[table["term"] == term].iloc[0]
        fam_rows.append(
            {
                "hypothesis": hid,
                "term": term,
                "label": label,
                "predicted_sign": sign,
                **{k: row[k] for k in ("estimate", "se", "ci_low", "ci_high", "odds_ratio")},
                "p_raw": row["p_raw"],
            }
        )
    family = pd.DataFrame(fam_rows)
    family["p_holm"], family["reject_holm"] = holm(family["p_raw"].to_numpy())
    family["reject_raw"] = family["p_raw"] < ALPHA
    family["direction_ok"] = [
        (s == 0) or (np.sign(e) == s) for s, e in zip(family["predicted_sign"], family["estimate"])
    ]
    label = f"{cov_struct}/{covariance}+t"
    return GeeResult(table, family, len(df), n_clusters, converged, label, formula, notes)


def fit_primary(df: pd.DataFrame, checkpoint: int | str = "final", covariates: bool = True):
    """Validate, subset to the primary checkpoint, code and fit. Returns (result, checkpoint)."""
    validate_table(df)
    ck = primary_checkpoint(df, checkpoint)
    sub = add_codes(df[df["checkpoint"] == ck])
    has_cov = covariates and any(c in df.columns for c in OPTIONAL_COVARIATES)
    return fit_gee(sub, covariates=has_cov), ck


def fit_bayes_mixed(df: pd.DataFrame, covariates: bool = True) -> pd.DataFrame:
    """Sensitivity only: conditional logit with fact and fact-by-seed random intercepts (VB).

    Posterior SDs of the variational approximation are known to be too small, so this is
    reported as point estimates and is NOT part of the confirmatory family.
    """
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

    if "freq_c" not in df:
        df = add_codes(df)
    formula = build_formula(df, covariates)
    df = df.assign(fact_seed=df["fact_id"].astype(str) + "/" + df["seed"].astype(str))
    model = BinomialBayesMixedGLM.from_formula(
        formula,
        {"fact": "0 + C(fact_id)", "fact_seed": "0 + C(fact_seed)"},
        df,
        vcp_p=1.0,
        fe_p=3.0,
    )
    res = model.fit_vb()
    names = list(model.exog_names)
    out = pd.DataFrame(
        {"term": names, "estimate": res.fe_mean, "posterior_sd": res.fe_sd}
    )
    out["fact_sd"] = float(np.exp(res.vcp_mean[0]))
    out["fact_seed_sd"] = float(np.exp(res.vcp_mean[1]))
    return out
