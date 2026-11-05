"""Validation on simulated data: recovery, false positives and power for H1-H3, H4 secondary."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from .descriptive import to_markdown
from .extraction import run_extraction
from .family import CONFIRMATORY, HYPOTHESES, assemble_family
from .models import (
    ALPHA,
    PROBE_FAMILY,
    add_codes,
    add_realized_diversity,
    build_formula,
    fit_gee,
)
from .simulate import (
    SimParams,
    planted_conditional,
    simulate_probe_table,
    simulate_qa_table,
    simulate_realized_diversity,
)

N_PERM_REP = 2000
N_BOOT_REP = 500
RECOVERY_NAMES = {"H1": "freq_c", "H2": "div_c:frame_c"}


def probe_truth(p: SimParams, n_facts_per_cell: int = 3000, seed: int = 987) -> dict[str, float]:
    """Population-averaged log-odds of the planted probe model (what the GEE targets).

    Planted coefficients are conditional on the random effects; the marginal ones are smaller.
    Estimated by an independence-logit fit on one very large simulation.
    """
    big = simulate_probe_table(
        p.with_effects(n_facts_per_cell=n_facts_per_cell), seed=seed, final_only=True
    )
    big = add_codes(big)
    res = smf.glm(build_formula(big), data=big, family=sm.families.Binomial()).fit()
    return {h: float(res.params[term]) for h, term in RECOVERY_NAMES.items()}


def extraction_truth(
    p: SimParams, n_facts_per_cell: int = 1500, seed: int = 988
) -> dict[str, float]:
    """Population values of the three extraction estimands (same estimators, huge sample)."""
    q = p.with_effects(n_facts_per_cell=n_facts_per_cell)
    probe = simulate_probe_table(q, seed=seed, final_only=True)
    qa = simulate_qa_table(q, probe, seed=seed + 1)
    comp = run_extraction(qa, n_perm=10, ci=False, validate=False).components.set_index("component")
    return {
        "H3a": float(comp.loc["H3a", "estimate"]),
        "H3b": float(comp.loc["H3b", "estimate"]),
        "H4": float(comp.loc["H4", "estimate"]),
    }


def one_replicate(args: tuple[SimParams, int, bool]) -> list[dict]:
    p, seed, ci = args
    probe = simulate_probe_table(p, seed=seed, final_only=True)
    gee = fit_gee(add_codes(probe[probe["split"] == "test"]))
    qa = simulate_qa_table(p, probe, seed=seed + 7_000_000)
    ext = run_extraction(qa, n_perm=N_PERM_REP, n_boot=N_BOOT_REP, ci=ci, validate=False)
    fam = assemble_family(gee.family, ext.family)
    rows = []
    for _, r in fam.iterrows():
        rows.append(
            {
                "hypothesis": r["hypothesis"],
                "estimate": r["estimate"],
                "ci_low": r["ci_low"],
                "ci_high": r["ci_high"],
                # H4 is secondary: its p-value is descriptive and only used to check calibration
                "p_raw": r["p_raw"] if np.isfinite(r["p_raw"]) else r["p_descriptive"],
                "p_holm": r["p_holm"],
                "direction_ok": bool(r["direction_ok"]),
                "converged": gee.converged,
            }
        )
    for _, r in ext.components.iterrows():
        if r["component"] in ("H3a", "H3b"):
            rows.append(
                {
                    "hypothesis": r["component"],
                    "estimate": r["estimate"],
                    "ci_low": r["ci_low"],
                    "ci_high": r["ci_high"],
                    "p_raw": r["p_raw"],
                    "p_holm": np.nan,
                    "direction_ok": bool(r["direction_ok"]),
                    "converged": gee.converged,
                }
            )
    return rows


def run_replicates(
    p: SimParams, n_rep: int, seed0: int = 1000, ci: bool = False, workers: int = 1
) -> pd.DataFrame:
    """Simulate + analyse n_rep times; one row per replicate x hypothesis (and H3 components)."""
    jobs = [(p, seed0 + r, ci) for r in range(n_rep)]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one_replicate, jobs, chunksize=max(1, n_rep // (workers * 4))))
    else:
        results = [one_replicate(j) for j in jobs]
    rows = []
    for r, res in enumerate(results):
        for row in res:
            rows.append({"rep": r, **row})
    return pd.DataFrame(rows)


def null_summary(reps: pd.DataFrame) -> pd.DataFrame:
    """Per-test and family-wise rejection rates at alpha, before and after Holm."""
    n = reps["rep"].nunique()
    rows = []
    for h in list(HYPOTHESES) + ["H3a", "H3b"]:
        s = reps[reps["hypothesis"] == h]
        if s.empty:
            continue
        rows.append(
            {
                "test": h + (" (component)" if h in ("H3a", "H3b") else ""),
                "rejection_raw": float((s["p_raw"] < ALPHA).mean()),
                "rejection_holm": float((s["p_holm"] <= ALPHA).mean())
                if s["p_holm"].notna().all()
                else float("nan"),
            }
        )
    fam = reps[reps["hypothesis"].isin(CONFIRMATORY)]
    any_raw = fam.groupby("rep")["p_raw"].min() < ALPHA
    any_holm = fam.groupby("rep")["p_holm"].min() <= ALPHA
    rows.append(
        {
            "test": "any of H1-H3 (family-wise)",
            "rejection_raw": float(any_raw.mean()),
            "rejection_holm": float(any_holm.mean()),
        }
    )
    out = pd.DataFrame(rows)
    out["n_replicates"] = n
    out["mc_halfwidth_at_0.05"] = 1.96 * np.sqrt(ALPHA * (1 - ALPHA) / n)
    return out


def recovery_summary(reps: pd.DataFrame, truth: dict[str, float], planted: dict[str, float]):
    rows = []
    for h in HYPOTHESES:
        s = reps[reps["hypothesis"] == h]
        t = truth[h]
        has_ci = s["ci_low"].notna().all()
        rows.append(
            {
                "hypothesis": h,
                "scale": "log-odds" if h in PROBE_FAMILY else "risk diff",
                "planted_conditional": planted.get(h, float("nan")),
                "population_truth": t,
                "mean_estimate": float(s["estimate"].mean()),
                "bias": float(s["estimate"].mean() - t),
                "ci_coverage": float(((s["ci_low"] <= t) & (t <= s["ci_high"])).mean())
                if has_ci
                else float("nan"),
                "sign_correct": float((np.sign(s["estimate"]) == np.sign(t)).mean()),
            }
        )
    return pd.DataFrame(rows)


def power_summary(reps: pd.DataFrame, n_facts_per_cell: int) -> pd.DataFrame:
    n_train, n_val = round(0.4 * n_facts_per_cell), round(0.1 * n_facts_per_cell)
    n_e2 = n_facts_per_cell - n_train - n_val
    rows = []
    for h in HYPOTHESES:
        s = reps[reps["hypothesis"] == h]
        rows.append(
            {
                "facts_per_cell": n_facts_per_cell,
                "total_facts": 6 * n_facts_per_cell,
                "e2_facts": 6 * n_e2,
                "hypothesis": h,
                "power_raw": float(((s["p_raw"] < ALPHA) & s["direction_ok"]).mean()),
                "power_holm": float(((s["p_holm"] <= ALPHA) & s["direction_ok"]).mean())
                if h in CONFIRMATORY
                else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def manip_replicate(args: tuple[SimParams, int]) -> dict:
    """One replicate of the weak-manipulation study: nominal vs realized-diversity H2."""
    p, seed = args
    probe = simulate_probe_table(p, seed=seed, final_only=True)
    test = add_codes(probe[probe["split"] == "test"])
    nominal = fit_gee(test).family.set_index("hypothesis").loc["H2"]
    rd = simulate_realized_diversity(p, seed)
    prz = add_realized_diversity(test, rd)
    realized = fit_gee(prz, diversity="realized").family.set_index("hypothesis").loc["H2"]
    f = prz.groupby("fact_id")[["div_bin", "rdiv_z"]].first()
    gap = float(
        f.loc[f["div_bin"] == "paraphrased", "rdiv_z"].mean()
        - f.loc[f["div_bin"] == "templated", "rdiv_z"].mean()
    )
    return {
        "nominal_est": float(nominal["estimate"]),
        "nominal_sig": bool(nominal["p_raw"] < ALPHA and nominal["estimate"] > 0),
        "realized_est": float(realized["estimate"]),
        "realized_sig": bool(realized["p_raw"] < ALPHA and realized["estimate"] > 0),
        "gap": gap,
    }


def manipulation_study(
    p: SimParams,
    strengths: tuple[float, ...] = (1.0, 0.6, 0.3),
    n_rep: int = 200,
    seed0: int = 200_000,
    workers: int = 1,
) -> pd.DataFrame:
    """How H2 changes when the nominal div_bin only weakly tracks realized diversity.

    `realized x full-contrast` = per-SD coefficient times the realized-diversity gap between
    the two conditions at full manipulation strength (strength 1.0), i.e. the effect of a
    full-strength diversity contrast measured on the realized scale.
    """
    runs = {}
    for rho in strengths:
        q = p.with_effects(manipulation_strength=rho)
        jobs = [(q, seed0 + r) for r in range(n_rep)]
        if workers > 1:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                res = list(pool.map(manip_replicate, jobs, chunksize=max(1, n_rep // 16)))
        else:
            res = [manip_replicate(j) for j in jobs]
        runs[rho] = pd.DataFrame(res)
    full_gap = float(runs[max(strengths)]["gap"].mean())
    rows = []
    for rho, d in runs.items():
        rows.append(
            {
                "manipulation_strength": rho,
                "nominal_H2_mean": float(d["nominal_est"].mean()),
                "nominal_H2_power": float(d["nominal_sig"].mean()),
                "realized_H2_per_SD": float(d["realized_est"].mean()),
                "realized_x_full_contrast": float(d["realized_est"].mean() * full_gap),
                "realized_H2_power": float(d["realized_sig"].mean()),
            }
        )
    return pd.DataFrame(rows)


def verdict(power_holm: float) -> str:
    if power_holm >= 0.8:
        return "adequately powered (>= 0.80)"
    if power_holm >= 0.5:
        return "marginal (0.50-0.80)"
    return "underpowered (< 0.50)"


def build_report(
    p: SimParams,
    n_null: int = 500,
    n_power: int = 300,
    sizes: tuple[int, ...] = (10, 20, 30),
    workers: int = 1,
    n_manip: int = 200,
) -> tuple[str, dict]:
    """Run all validation scenarios; return (markdown, raw tables for the report-back)."""
    ptruth = probe_truth(p)
    etruth = extraction_truth(p)
    truth = {**ptruth, "H3": etruth["H3a"], "H4": etruth["H4"]}
    planted = planted_conditional(p)

    planned = run_replicates(p, n_power, ci=True, workers=workers)
    rec = recovery_summary(planned, truth, planted)
    comp_rows = []
    for comp, t in (("H3a", etruth["H3a"]), ("H3b", etruth["H3b"])):
        s = planned[planned["hypothesis"] == comp]
        comp_rows.append(
            {
                "component": comp,
                "population_truth": t,
                "mean_estimate": float(s["estimate"].mean()),
                "bias": float(s["estimate"].mean() - t),
                "ci_coverage": float(((s["ci_low"] <= t) & (t <= s["ci_high"])).mean()),
                "sign_correct": float((np.sign(s["estimate"]) == np.sign(t)).mean()),
            }
        )
    comp_tab = pd.DataFrame(comp_rows)

    null_all = null_summary(run_replicates(p.null(), n_null, seed0=50_000, workers=workers))
    null_div = null_summary(
        run_replicates(p.null_diversity_gain(), n_null, seed0=80_000, workers=workers)
    )
    power_parts = []
    for k in sizes:
        reps = planned if k == p.n_facts_per_cell else run_replicates(
            p.with_effects(n_facts_per_cell=k), n_power, workers=workers
        )
        power_parts.append(power_summary(reps, k))
    power = pd.concat(power_parts, ignore_index=True)
    at_plan = power[power["facts_per_cell"] == p.n_facts_per_cell].copy()
    at_plan["verdict"] = [
        verdict(w) if h in CONFIRMATORY else "secondary (effect and CI only)"
        for h, w in zip(at_plan["hypothesis"], at_plan["power_holm"])
    ]
    manip = manipulation_study(p, n_rep=n_manip, workers=workers)
    nonconv = int((~planned["converged"]).sum())

    lines = [
        "# Analysis validation on simulated data (A03)",
        "",
        "Generated by `scripts/validate_analysis.py` (all seeds fixed; simulated data only, no "
        "real result). H1/H2: logistic GEE with fact clusters (bias-reduced covariance, "
        "t(G-p)); H3/H4: DESIGN's Fisher exact and McNemar tests on facts (plus a stratified "
        "permutation test for the between-condition H4 contrast). H1-H3 are confirmatory with "
        "Holm (m = 3) at alpha 0.05; H4 is secondary (effect and CI only; its p-value below is "
        "descriptive, used to check calibration). \"Power\" counts a rejection only when the "
        "effect has the predicted sign.",
        "",
        "## Simulation settings",
        "",
        f"- Planned size: {p.n_facts_per_cell} facts per freq x div cell x 6 = "
        f"{6 * p.n_facts_per_cell} facts; {p.n_seeds} seeds; test probes per fact x seed: 1 "
        "canonical + 2 novel; fact-level rule: majority (>= 2 of 3); SFT fact split 40/10/50 "
        "(E2 = 10 facts per cell = 60 facts); "
        f"{p.n_questions} questions per fact and eval set.",
        f"- Planted probe log-odds (conditional): freq {p.b_freq}, diversity {p.b_div}, frame "
        f"(novel - canonical) {p.b_frame}, diversity x frame {p.b_div_frame}, freq x diversity "
        f"{p.b_freq_div}; intercept {p.intercept}. Templated novel-frame penalty "
        f"{p.b_frame - 0.5 * p.b_div_frame}, paraphrased {p.b_frame + 0.5 * p.b_div_frame}.",
        f"- Planted QA logits: base_2shot {p.base2_intercept} + {p.base2_stored}*stored; "
        f"sft {p.sft_intercept} + {p.sft_stored}*stored + {p.sft_div}*div_c (E2).",
        f"- Random-effect SDs (probe): fact {p.sd_fact}, seed {p.sd_seed}, fact x seed "
        f"{p.sd_fact_seed}, fact x frame {p.sd_fact_frame}, template {p.sd_variant}; (QA) fact "
        f"{p.sd_fact_qa}, fact x seed {p.sd_fact_seed_qa}.",
        "- Planted H1/H2 coefficients are conditional on the random effects, while the GEE "
        "targets population-averaged values (smaller in magnitude). Recovery is judged against "
        "the population truth, computed with the same estimator on a very large simulation "
        f"({3000 * 6} facts for H1/H2, {1500 * 6} for the extraction estimands). The H3/H4 "
        "estimands are risk differences of the fact-level (majority) outcomes.",
        f"- Replicates: {n_power} per planted-effect scenario, {n_null} per null scenario. "
        f"Non-converged GEE fits in the planned scenario: {nonconv}.",
        "",
        f"## Recovery over {n_power} replicates at the planned size",
        "",
        to_markdown(rec, "{:.3f}"),
        "",
        "H3 estimate = gain on E2 (SFT - base accuracy); H4 estimate = gain(paraphrased) - "
        "gain(templated). CIs for H3/H4 are percentile bootstrap (500 resamples, facts within "
        "cells); for H1/H2 t-based GEE intervals.",
        "",
        to_markdown(comp_tab, "{:.3f}"),
        "",
        "## Null simulation A: every effect zero (probe effects 0, SFT = base)",
        "",
        to_markdown(null_all, "{:.3f}"),
        "",
        "## Null simulation B: extraction active but no diversity effect on the gain "
        "(probe effects 0, SFT gain > 0, no direct diversity benefit)",
        "",
        "H3 is truly non-null here (a real gain bounded by storage), so its row is power, not a "
        "false-positive rate; H4 is the null of interest.",
        "",
        to_markdown(null_div, "{:.3f}"),
        "",
        "## Power at the planned sample sizes",
        "",
        "Share of replicates in which the effect is rejected at alpha 0.05 with the predicted "
        "sign, raw and after Holm across H1-H3 (H4 raw only, descriptive). Planned size = 20 "
        "facts per cell (120 facts; "
        "E2 = 60 facts).",
        "",
        to_markdown(power, "{:.3f}"),
        "",
        "## Verdict at the planned size (Holm power)",
        "",
        to_markdown(at_plan[["hypothesis", "power_raw", "power_holm", "verdict"]], "{:.3f}"),
        "",
        "## How to read these numbers",
        "",
        "- Power is conditional on the planted effects, which are assumptions, not predictions; "
        "treat it as a sensitivity analysis (what size of effect the design can detect), not as "
        "a forecast.",
        "- H1/H2 (GEE) hold the nominal false-positive rate (null A and B, per-test column "
        "'rejection_raw'). The H3/H4 tests are valid but conservative: their null rejection "
        "rates are below 0.05 because the fact-level outcomes are sparse and discrete (few "
        "discordant or non-zero-gain facts). The reported H3/H4 power is for these conservative "
        "tests. The family-wise raw rate in null A is therefore below the 1 - 0.95^4 = 0.185 of "
        "four exact tests.",
        "- H3 power is high partly because the majority rule leaves the 2-shot base near the "
        "floor at fact level (a fact is base-correct only if most of its items are), which makes "
        "the gain large; a different aggregation changes the estimand and the power.",
        "- Bootstrap CIs for H3/H4 (60 facts, percentile) under-cover somewhat (see the "
        "ci_coverage columns); treat them as approximate.",
        "- H4 is pre-registered as secondary because its power at 60 E2 facts is low; the H4 "
        "rows are reported for effect size and CI.",
        "",
        "## Weak manipulation: how H2 changes",
        "",
        f"{n_manip} replicates per row. The nominal div_bin tracks realized diversity with "
        "correlation `manipulation_strength` (1 = perfectly). The storage effect is driven by "
        "realized diversity, so a weak manipulation shrinks the nominal H2 estimate and its "
        "power toward the null; the realized-diversity covariate recovers the effect. "
        "`realized_x_full_contrast` converts the per-SD coefficient with the realized gap "
        "between conditions at strength 1.0. Population truth of H2 at full strength: "
        f"{ptruth['H2']:.3f}.",
        "",
        to_markdown(manip, "{:.3f}"),
        "",
    ]
    raw = {"manipulation": manip, "recovery": rec, "components": comp_tab,
           "null_all": null_all, "null_div": null_div,
           "power": power, "verdict": at_plan}
    return "\n".join(lines), raw
