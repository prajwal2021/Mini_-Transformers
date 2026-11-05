"""Validation on simulated data: recovery of planted effects, null false positives, power."""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from .descriptive import to_markdown
from .models import ALPHA, FAMILY, add_codes, build_formula, fit_gee
from .simulate import SimParams, planted_conditional, simulate_probe_table

HYPS = list(FAMILY)


def marginal_truth(p: SimParams, n_facts_per_cell: int = 3000, seed: int = 987) -> dict[str, float]:
    """Population-averaged log-odds of the planted model (what the GEE targets).

    The planted coefficients are conditional on the random effects; a marginal logistic fit has
    smaller coefficients. Estimated by an independence-logit fit on one very large simulation.
    """
    big = simulate_probe_table(
        p.with_effects(n_facts_per_cell=n_facts_per_cell), seed=seed, final_only=True
    )
    big = add_codes(big)
    res = smf.glm(build_formula(big), data=big, family=sm.families.Binomial()).fit()
    return {h: float(res.params[term]) for h, (term, _, _) in FAMILY.items()}


def run_replicates(p: SimParams, n_rep: int, seed0: int = 1000) -> pd.DataFrame:
    """Simulate + fit n_rep times; one row per replicate x hypothesis."""
    rows = []
    for r in range(n_rep):
        df = add_codes(simulate_probe_table(p, seed=seed0 + r, final_only=True))
        res = fit_gee(df)
        for _, row in res.family.iterrows():
            rows.append(
                {
                    "rep": r,
                    "hypothesis": row["hypothesis"],
                    "estimate": row["estimate"],
                    "ci_low": row["ci_low"],
                    "ci_high": row["ci_high"],
                    "p_raw": row["p_raw"],
                    "p_holm": row["p_holm"],
                    "converged": res.converged,
                }
            )
    return pd.DataFrame(rows)


def null_summary(reps: pd.DataFrame) -> pd.DataFrame:
    """Per-hypothesis and family-wise rejection rates at alpha, before and after Holm."""
    n = reps["rep"].nunique()
    rows = []
    for h in HYPS:
        s = reps[reps["hypothesis"] == h]
        rows.append(
            {
                "test": h,
                "rejection_raw": float((s["p_raw"] < ALPHA).mean()),
                "rejection_holm": float((s["p_holm"] <= ALPHA).mean()),
            }
        )
    any_raw = reps.groupby("rep")["p_raw"].min() < ALPHA
    any_holm = reps.groupby("rep")["p_holm"].min() <= ALPHA
    rows.append(
        {
            "test": "any of H1-H4 (family-wise)",
            "rejection_raw": float(any_raw.mean()),
            "rejection_holm": float(any_holm.mean()),
        }
    )
    out = pd.DataFrame(rows)
    out["n_replicates"] = n
    mc = 1.96 * np.sqrt(ALPHA * (1 - ALPHA) / n)
    out["mc_halfwidth_at_0.05"] = mc
    return out


def recovery_summary(
    reps: pd.DataFrame, planted: dict[str, float], marginal: dict[str, float]
) -> pd.DataFrame:
    rows = []
    for h in HYPS:
        s = reps[reps["hypothesis"] == h]
        rows.append(
            {
                "hypothesis": h,
                "planted_conditional": planted[h],
                "population_averaged_truth": marginal[h],
                "mean_estimate": float(s["estimate"].mean()),
                "bias_vs_pa_truth": float(s["estimate"].mean() - marginal[h]),
                "ci_coverage_of_pa_truth": float(
                    ((s["ci_low"] <= marginal[h]) & (marginal[h] <= s["ci_high"])).mean()
                ),
                "sign_correct": float((np.sign(s["estimate"]) == np.sign(marginal[h])).mean()),
            }
        )
    return pd.DataFrame(rows)


def power_summary(reps: pd.DataFrame, n_facts_per_cell: int) -> pd.DataFrame:
    rows = []
    for h in HYPS:
        s = reps[reps["hypothesis"] == h]
        rows.append(
            {
                "facts_per_cell": n_facts_per_cell,
                "total_facts": 6 * n_facts_per_cell,
                "hypothesis": h,
                "power_raw": float((s["p_raw"] < ALPHA).mean()),
                "power_holm": float((s["p_holm"] <= ALPHA).mean()),
            }
        )
    return pd.DataFrame(rows)


def single_dataset_table(
    p: SimParams, marginal: dict[str, float], seed: int = 1000
) -> pd.DataFrame:
    """One simulated dataset at the planned size: estimate, CI and whether truth is inside."""
    res = fit_gee(add_codes(simulate_probe_table(p, seed=seed, final_only=True)))
    fam = res.family.set_index("hypothesis")
    planted = planted_conditional(p)
    rows = []
    for h in HYPS:
        r = fam.loc[h]
        rows.append(
            {
                "hypothesis": h,
                "planted_conditional": planted[h],
                "population_averaged_truth": marginal[h],
                "estimate": r["estimate"],
                "ci_low": r["ci_low"],
                "ci_high": r["ci_high"],
                "truth_in_ci": bool(r["ci_low"] <= marginal[h] <= r["ci_high"]),
                "sign_ok": bool(np.sign(r["estimate"]) == np.sign(marginal[h])),
                "p_holm": r["p_holm"],
            }
        )
    return pd.DataFrame(rows)


def build_report(
    p: SimParams,
    n_null: int = 500,
    n_power: int = 300,
    sizes: tuple[int, ...] = (10, 20, 30),
) -> str:
    marginal = marginal_truth(p)
    planted = planted_conditional(p)
    single = single_dataset_table(p, marginal)
    planned = run_replicates(p, n_power)
    rec = recovery_summary(planned, planted, marginal)
    null = null_summary(run_replicates(p.null(), n_null, seed0=50_000))
    power_rows = []
    for k in sizes:
        reps = planned if k == p.n_facts_per_cell else run_replicates(
            p.with_effects(n_facts_per_cell=k), n_power
        )
        power_rows.append(power_summary(reps, k))
    power = pd.concat(power_rows, ignore_index=True)
    nonconv = int((~planned["converged"]).sum())

    lines = [
        "# Analysis validation on simulated data",
        "",
        "Generated by `scripts/validate_analysis.py` (all seeds fixed; simulated data only, no "
        "real result). Model: logistic GEE, fact clusters, exchangeable working correlation, "
        "bias-reduced covariance, t(G-p) intervals; Holm across H1-H4 (alpha = 0.05).",
        "",
        "## Simulation settings",
        "",
        f"- Planned size: {p.n_facts_per_cell} facts per cell x 6 cells = {6 * p.n_facts_per_cell} "
        f"facts; {p.n_seeds} seeds; {p.n_variants} prompt variants; 2 regimes "
        f"({6 * p.n_facts_per_cell * p.n_seeds * p.n_variants * 2} rows at the final checkpoint).",
        f"- Planted log-odds (conditional): freq {p.b_freq}, diversity {p.b_div}, "
        f"freq x diversity {p.b_freq_div}, regime (novel - iid) {p.b_regime}; intercept "
        f"{p.intercept}.",
        f"- Random-effect SDs: fact {p.sd_fact}, seed {p.sd_seed}, fact x seed {p.sd_fact_seed}, "
        f"fact x regime {p.sd_fact_regime}, prompt variant {p.sd_variant}.",
        "- The planted coefficients are conditional on the random effects. The GEE estimates "
        "population-averaged coefficients, which are smaller in magnitude; the "
        "'population-averaged truth' column is that target, obtained from an independence-logit "
        f"fit on a simulation with {3000 * 6} facts. Recovery is judged against it.",
        f"- Replicates: {n_power} per planted-effect scenario, {n_null} for the null. "
        f"Non-converged fits in the planned scenario: {nonconv}.",
        "",
        "## Recovery of planted effects: one dataset (seed 1000)",
        "",
        to_markdown(single, "{:.3f}"),
        "",
        f"## Recovery over {n_power} replicates at the planned size",
        "",
        to_markdown(rec, "{:.3f}"),
        "",
        f"## Null simulation ({n_null} replicates, all four effects set to 0)",
        "",
        "Fact, seed, fact x seed, fact x regime and prompt-variant random effects and the "
        "covariate effects stay on. Nominal rate 0.05 per test; the family-wise row is "
        "P(at least one of the four rejected).",
        "",
        to_markdown(null, "{:.3f}"),
        "",
        "## Power at the planned sample size",
        "",
        "Planted effects as above; share of replicates in which the effect is rejected at "
        "alpha 0.05 (raw) and after Holm across H1-H4. The planned size is 20 facts per cell.",
        "",
        to_markdown(power, "{:.3f}"),
        "",
    ]
    return "\n".join(lines)
