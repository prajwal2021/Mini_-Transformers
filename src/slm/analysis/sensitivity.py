"""Pre-registered sensitivity analyses (PREREG v3 section 10): one command, one table.

Every row re-estimates H1/H2 (probe table) or H3/H4 (QA table) under one alternative choice and
reports the estimate with its 95% CI next to the primary one. None of these rows is a test in
the Holm family. Rows that cannot run (missing column or file) are listed as skipped.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .aggregation import PRIMARY_RULE, RULES, stored_by_fact_seed
from .descriptive import to_markdown
from .extraction import run_extraction
from .models import (
    add_codes,
    add_realized_diversity,
    check_separation,
    fit_bayes_mixed,
    fit_gee,
    fit_gee_robust,
    prepare_primary,
)
from .schema import PROBE_OPTIONAL


def _gee_rows(label: str, res, hyps=("H1", "H2"), note: str = "") -> list[dict]:
    fam = res.family.set_index("hypothesis")
    return [
        {
            "analysis": label,
            "hypothesis": h,
            "scale": "log-odds",
            "estimate": float(fam.loc[h, "estimate"]),
            "ci_low": float(fam.loc[h, "ci_low"]),
            "ci_high": float(fam.loc[h, "ci_high"]),
            "p_raw": float(fam.loc[h, "p_raw"]),
            "note": note,
        }
        for h in hyps
    ]


def _skip(label: str, why: str) -> dict:
    return {"analysis": label, "hypothesis": "-", "scale": "-", "estimate": np.nan,
            "ci_low": np.nan, "ci_high": np.nan, "p_raw": np.nan, "note": f"skipped: {why}"}


def _ext_rows(label: str, ext, note: str = "") -> list[dict]:
    comp = ext.components.set_index("component")
    rows = []
    for h, c in (("H3", "H3a"), ("H4", "H4")):
        rows.append(
            {
                "analysis": label,
                "hypothesis": h if h == "H4" else "H3 (gain)",
                "scale": "risk diff",
                "estimate": float(comp.loc[c, "estimate"]),
                "ci_low": float(comp.loc[c, "ci_low"]),
                "ci_high": float(comp.loc[c, "ci_high"]),
                "p_raw": float(comp.loc[c, "p_raw"]),
                "note": note,
            }
        )
    return rows


def realized_gap(primary: pd.DataFrame) -> float:
    """Mean realized diversity (z) of paraphrased minus templated facts: converts a per-SD
    coefficient into the effect of the nominal contrast."""
    f = primary.groupby("fact_id")[["div_bin", "rdiv_z"]].first()
    return float(
        f.loc[f["div_bin"] == "paraphrased", "rdiv_z"].mean()
        - f.loc[f["div_bin"] == "templated", "rdiv_z"].mean()
    )


def run_sensitivity(
    probe_raw: pd.DataFrame,
    qa: pd.DataFrame | None = None,
    realized: pd.DataFrame | None = None,
    checkpoint: int | str = "final",
    n_boot: int = 500,
    n_perm: int = 2000,
) -> tuple[pd.DataFrame, dict]:
    """Run every sensitivity analysis. Returns (long table, extras incl. separation report)."""
    primary, ck, _ = prepare_primary(probe_raw, checkpoint)
    has_cov = any(c in primary.columns for c in PROBE_OPTIONAL + ("attribute_id",))
    rows: list[dict] = []
    extras: dict = {"checkpoint": ck}

    base_res, ladder_log = fit_gee_robust(primary, covariates=has_cov)
    extras["ladder_log"] = ladder_log
    extras["separation_cells"] = check_separation(primary)
    if base_res is None:
        rows.append(_skip("primary model", "all fallback fits failed (non-informative)"))
        return pd.DataFrame(rows), extras
    rows += _gee_rows("primary (GEE, log3 mentions if present, with templates)", base_res)

    # exposure coding: bins vs measured mentions
    if "train_mentions" in primary.columns:
        for mode in ("bins", "measured"):
            res = fit_gee(add_codes(primary, mode), covariates=has_cov)
            rows += _gee_rows(f"exposure coding: {mode}", res)
    else:
        rows.append(_skip("exposure coding: bins vs measured", "no train_mentions column"))

    # prompt variants
    rows += _gee_rows(
        "without prompt_variant terms", fit_gee(primary, covariates=has_cov, variant_terms=False)
    )

    # estimator: conditional mixed logit point estimates
    try:
        mixed = fit_bayes_mixed(primary, covariates=has_cov).set_index("term")
        for h, term in (("H1", "freq_c"), ("H2", "div_c:frame_c")):
            rows.append(
                {"analysis": "Bayesian mixed logit (fact, fact x seed; point estimate)",
                 "hypothesis": h, "scale": "log-odds (conditional)",
                 "estimate": float(mixed.loc[term, "estimate"]), "ci_low": np.nan,
                 "ci_high": np.nan, "p_raw": np.nan,
                 "note": "variational SDs unreliable; no CI"}
            )
    except Exception as exc:
        rows.append(_skip("Bayesian mixed logit", type(exc).__name__))

    # secondary outcome: token-normalised
    if "stored_tokennorm" in primary.columns:
        res = fit_gee(primary, covariates=has_cov, outcome="stored_tokennorm")
        rows += _gee_rows("outcome: stored_tokennorm", res)
    else:
        rows.append(_skip("outcome: stored_tokennorm", "no stored_tokennorm column"))

    # realized diversity
    if realized is not None:
        prz = add_realized_diversity(primary, realized)
        gap = realized_gap(prz)
        extras["realized_gap"] = gap
        for mode, label in (("realized", "realized diversity replaces div_bin"),
                            ("both", "div_bin and realized diversity together")):
            res = fit_gee(prz, covariates=has_cov, diversity=mode)
            fam = res.family.set_index("hypothesis")
            note = f"H2 per SD of realized diversity; x{gap:.2f} = per nominal contrast"
            if mode == "realized":
                scale = gap
                rows.append(
                    {"analysis": label, "hypothesis": "H2 (scaled to nominal contrast)",
                     "scale": "log-odds", "estimate": float(fam.loc["H2", "estimate"]) * scale,
                     "ci_low": float(fam.loc["H2", "ci_low"]) * scale,
                     "ci_high": float(fam.loc["H2", "ci_high"]) * scale,
                     "p_raw": float(fam.loc["H2", "p_raw"]), "note": note}
                )
                rows.append(
                    {"analysis": label, "hypothesis": "H1", "scale": "log-odds",
                     "estimate": float(fam.loc["H1", "estimate"]),
                     "ci_low": float(fam.loc["H1", "ci_low"]),
                     "ci_high": float(fam.loc["H1", "ci_high"]),
                     "p_raw": float(fam.loc["H1", "p_raw"]), "note": ""}
                )
            else:
                tab = res.table.set_index("term")
                rows.append(
                    {"analysis": label, "hypothesis": "H2 (nominal term given realized)",
                     "scale": "log-odds", "estimate": float(fam.loc["H2", "estimate"]),
                     "ci_low": float(fam.loc["H2", "ci_low"]),
                     "ci_high": float(fam.loc["H2", "ci_high"]),
                     "p_raw": float(fam.loc["H2", "p_raw"]),
                     "note": "nominal div_c:frame_c adjusted for realized diversity"}
                )
                rows.append(
                    {"analysis": label, "hypothesis": "H2 (realized term, per SD)",
                     "scale": "log-odds", "estimate": float(tab.loc["rdiv_z:frame_c", "estimate"]),
                     "ci_low": float(tab.loc["rdiv_z:frame_c", "ci_low"]),
                     "ci_high": float(tab.loc["rdiv_z:frame_c", "ci_high"]),
                     "p_raw": float(tab.loc["rdiv_z:frame_c", "p_raw"]), "note": ""}
                )
    else:
        rows.append(_skip("realized diversity", "no realized_diversity.csv given"))

    # extraction: aggregation rules (probe-level rule for stored, QA-level rule for correct)
    if qa is not None:
        for rule in RULES:
            stored = stored_by_fact_seed(primary, rule)
            ext = run_extraction(qa, n_perm=n_perm, n_boot=n_boot, rule=rule, stored=stored)
            tag = " (primary)" if rule == PRIMARY_RULE else ""
            rows += _ext_rows(f"fact-level rule: {rule}{tag}", ext)
        ext0 = run_extraction(qa, n_perm=n_perm, n_boot=n_boot, comparator="base_0shot")
        rows += _ext_rows("comparator: base_0shot (secondary)", ext0)
    else:
        rows.append(_skip("aggregation rules / comparator", "no QA table given"))

    return pd.DataFrame(rows), extras


def sensitivity_markdown(table: pd.DataFrame, extras: dict) -> str:
    lines = [
        "# Sensitivity analyses",
        "",
        f"Primary checkpoint: {extras['checkpoint']}. These are re-estimations under alternative "
        "choices (PREREG v3 section 10); none enters the Holm family. CIs are 95%.",
        "",
        to_markdown(table, "{:.4g}"),
    ]
    sep = extras.get("separation_cells")
    lines += ["", "## Complete separation", ""]
    if sep is not None and len(sep):
        lines += ["Design cells whose outcome is all 0 or all 1 at the primary checkpoint:", "",
                  to_markdown(sep)]
    else:
        lines += ["No design cell (freq x div x frame) has an all-0 or all-1 outcome."]
    for msg in extras.get("ladder_log", []):
        lines.append(f"- fit ladder: {msg}")
    if "realized_gap" in extras:
        lines += ["", f"Realized diversity gap (paraphrased minus templated, in SD units): "
                      f"{extras['realized_gap']:.3f}."]
    return "\n".join(lines) + "\n"
