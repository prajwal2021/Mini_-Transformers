"""One-command analysis: probe table -> model, effect sizes, descriptive tables, figures."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import descriptive as dsc
from . import figures
from .models import FAMILY, fit_bayes_mixed, fit_primary
from .schema import validate_table


def _family_md(res) -> str:
    fam = res.family.copy()
    fam["decision (Holm, alpha=0.05)"] = [
        "reject H0" if r else "not rejected" for r in fam["reject_holm"]
    ]
    cols = ["hypothesis", "label", "estimate", "ci_low", "ci_high", "odds_ratio",
            "p_raw", "p_holm", "direction_ok", "decision (Holm, alpha=0.05)"]
    return dsc.to_markdown(fam[cols], "{:.4g}")


def run_analysis(
    input_path: Path | str,
    out_dir: Path | str = "reports",
    checkpoint: int | str = "final",
    mixed_sensitivity: bool = True,
) -> dict[str, Path]:
    """Run the full pre-registered analysis; return the paths written."""
    out = Path(out_dir)
    tables, fig_dir = out / "tables", out / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    path = Path(input_path)
    df = pd.read_csv(path) if path.suffix == ".csv" else pd.read_parquet(path)
    warns = validate_table(df)

    res, ck = fit_primary(df, checkpoint)
    primary = df[df["checkpoint"] == ck]
    rd = dsc.risk_difference_table(primary)
    cells = dsc.cell_rates(primary)
    curves = dsc.curve_rates(df)
    acq = dsc.acquisition_table(df)

    written: dict[str, Path] = {}
    lines = [
        "# Primary storage model",
        "",
        f"Input: `{path.name}`; primary checkpoint: {ck}; rows: {res.n_rows}; "
        f"facts (clusters): {res.n_clusters}; converged: {res.converged}.",
        "",
        f"Formula: `{res.formula}`",
        f"Estimator: logistic GEE, groups = fact_id, covariance `{res.covariance}`. "
        "Estimates are population-averaged log-odds; CIs and p-values use t with "
        "(clusters - parameters) degrees of freedom.",
        "",
        "## Pre-registered family (Holm across H1-H4)",
        "",
        _family_md(res),
        "",
        "## Effect sizes on the risk-difference scale (95% fact-bootstrap CI)",
        "",
        dsc.to_markdown(rd),
        "",
        "## All coefficients",
        "",
        dsc.to_markdown(res.table[["term", "estimate", "se", "p_raw", "ci_low", "ci_high",
                                   "odds_ratio"]], "{:.4g}"),
    ]
    if warns or res.warnings:
        lines += ["", "## Warnings", ""] + [f"- {w}" for w in warns + res.warnings]
    if mixed_sensitivity:
        try:
            mixed = fit_bayes_mixed(primary)
            lines += [
                "",
                "## Sensitivity: conditional mixed logit (variational Bayes, point estimates only)",
                "",
                "Fact and fact-by-seed random intercepts. Variational posterior SDs are too small "
                "and are shown for reference; no tests are based on this fit.",
                "",
                dsc.to_markdown(mixed, "{:.3f}"),
            ]
        except Exception as exc:  # sensitivity must never block the primary analysis
            lines += ["", f"Mixed-model sensitivity failed: {type(exc).__name__}: {exc}"]
    written["model"] = tables / "analysis_model.md"
    written["model"].write_text("\n".join(lines) + "\n", encoding="utf-8")

    desc = [
        "# Descriptive tables",
        "",
        f"## Stored rate by cell at checkpoint {ck} (95% fact-bootstrap CI)",
        "",
        dsc.to_markdown(cells),
        "",
        "## Acquisition (first checkpoint with >= half of a fact-seed's probes stored)",
        "",
        dsc.to_markdown(acq),
    ]
    written["descriptive"] = tables / "analysis_descriptive.md"
    written["descriptive"].write_text("\n".join(desc) + "\n", encoding="utf-8")
    res.family.to_csv(tables / "analysis_family.csv", index=False, float_format="%.6g")
    written["family_csv"] = tables / "analysis_family.csv"

    figs = figures.plot_stored_by_cell(cells, fig_dir, ck) + figures.plot_learning_curves(
        curves, fig_dir
    )
    for p in figs:
        written[p.name] = p
    return written


__all__ = ["FAMILY", "run_analysis"]
