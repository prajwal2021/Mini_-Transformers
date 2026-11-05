"""One-command analysis: probe table (+ QA table) -> H1-H4, effect sizes, tables, figures."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import banner as banner_mod
from . import descriptive as dsc
from . import figures
from .extraction import run_extraction
from .family import assemble_family
from .models import fit_bayes_mixed, fit_gee_robust, prepare_primary
from .schema import PROBE_OPTIONAL, normalize_probe_table, normalize_qa_table


def _read(path: Path | str) -> pd.DataFrame:
    path = Path(path)
    return pd.read_csv(path) if path.suffix == ".csv" else pd.read_parquet(path)


def _family_md(fam: pd.DataFrame) -> str:
    cols = ["hypothesis", "label", "scale", "estimate", "ci_low", "ci_high", "p_raw", "p_holm",
            "direction_ok", "status"]
    return dsc.to_markdown(fam[cols], "{:.4g}")


def _noninformative_family() -> pd.DataFrame:
    """H1/H2 rows when every GEE fit in the fallback ladder failed (p = 1, no claim)."""
    rows = [
        {"hypothesis": h, "label": label, "predicted_sign": 1, "estimate": np.nan,
         "ci_low": np.nan, "ci_high": np.nan, "p_raw": 1.0, "direction_ok": False}
        for h, label in (("H1", "storage rises with log exposure (non-informative)"),
                         ("H2", "diversity x frame (non-informative)"))
    ]
    return pd.DataFrame(rows)


def run_analysis(
    input_path: Path | str,
    out_dir: Path | str = "reports",
    checkpoint: int | str = "final",
    qa_path: Path | str | None = None,
    mixed_sensitivity: bool = True,
    real: bool = False,
    banner_label: str | None = None,
) -> dict[str, Path]:
    """Run the full pre-registered analysis; return the paths written.

    Figures carry a SIMULATED banner unless `real=True` (the explicit --real flag).
    """
    if banner_label is not None:
        banner_mod.set_label(banner_label)
    out = Path(out_dir)
    tables, fig_dir = out / "tables", out / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    banner = not real
    path = Path(input_path)
    raw = _read(path)
    primary, ck, warns = prepare_primary(raw, checkpoint)
    n_val = int((raw["split"] == "val").sum()) if "split" in raw else 0
    norm = normalize_probe_table(raw)
    test_all = norm[norm["split"] == "test"]

    has_cov = any(c in primary.columns for c in PROBE_OPTIONAL + ("attribute_id",))
    res, ladder = fit_gee_robust(primary, covariates=has_cov)
    warns = warns + ladder
    gee_family = res.family if res is not None else _noninformative_family()
    qa = normalize_qa_table(_read(qa_path)) if qa_path is not None else None
    ext = run_extraction(qa) if qa is not None else None
    fam = assemble_family(gee_family, None if ext is None else ext.family)

    rd = dsc.risk_difference_table(primary)
    cells = dsc.cell_rates(primary)
    curves = dsc.curve_rates(test_all)
    acq = dsc.acquisition_table(test_all[test_all["checkpoint"] > 0])

    written: dict[str, Path] = {}
    lines = [
        "# Primary analysis: H1-H3 confirmatory, H4 secondary",
        "",
        f"Probe table: `{path.name}`; test rows only ({n_val} val rows excluded); primary "
        f"checkpoint {ck} (final checkpoint of each seed); rows "
        f"{len(primary) if res is None else res.n_rows}; facts (clusters) "
        f"{primary['fact_id'].nunique()}; converged {res is not None and res.converged}.",
        "",
        "## Family (Holm across H1, H2, H3; H4 is secondary: effect and CI only)",
        "",
        _family_md(fam),
        "",
    ]
    if ext is None:
        lines += ["H3 was not run (no QA table); Holm treats its p-value as 1, so the adjusted "
                  "p-values above are provisional upper bounds.", ""]
    if res is not None:
        lines += [
            "## H1 / H2 model",
            "",
            f"Formula: `{res.formula}`",
            f"Estimator: logistic GEE, groups = fact_id, covariance `{res.covariance}`. "
            "Estimates are population-averaged log-odds; CIs and p-values use t with "
            "(clusters - parameters) degrees of freedom.",
            "",
            "Supporting simple effects of diversity within each frame (at mid exposure; "
            "paraphrased - templated, log-odds):",
            "",
            dsc.to_markdown(res.simple),
            "",
        ]
    lines += [
        "## Effect sizes on the risk-difference scale (95% fact-bootstrap CI)",
        "",
        dsc.to_markdown(rd),
    ]
    if res is not None:
        lines += [
            "",
            "## All coefficients",
            "",
            dsc.to_markdown(
                res.table[["term", "estimate", "se", "p_raw", "ci_low", "ci_high", "odds_ratio"]],
                "{:.4g}",
            ),
        ]
    all_warns = warns + (res.warnings if res is not None else [])
    if all_warns:
        lines += ["", "## Warnings", ""] + [f"- {w}" for w in all_warns]
    if mixed_sensitivity and res is not None:
        try:
            mixed = fit_bayes_mixed(primary, covariates=has_cov)
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

    if ext is not None:
        elines = [
            "# Extraction tests: H3 (confirmatory) and H4 (secondary), E2 held-out facts",
            "",
            f"QA table: `{Path(qa_path).name}`; facts {ext.n_facts}. Unit = fact (stored / "
            "correct on >= 2 of 3 items within a seed, majority of seeds); comparator = "
            "base_2shot.",
            "",
            "## Tests and effect sizes (95% stratified fact-bootstrap CIs)",
            "",
            dsc.to_markdown(ext.components, "{:.4g}"),
            "",
            "## McNemar (base vs SFT) and Fisher (stored x correct) per diversity condition",
            "",
            dsc.to_markdown(ext.per_condition),
            "",
            "## 2x2 counts: stored x QA-correct (SFT model) per diversity condition",
            "",
            dsc.to_markdown(ext.tables_2x2),
        ]
        if ext.warnings:
            elines += ["", "## Warnings", ""] + [f"- {w}" for w in ext.warnings]
        written["extraction"] = tables / "analysis_extraction.md"
        written["extraction"].write_text("\n".join(elines) + "\n", encoding="utf-8")
        acc = dsc.eval_accuracy(qa)
        for name, frame in (("analysis_components", ext.components),
                            ("analysis_per_condition", ext.per_condition),
                            ("analysis_2x2", ext.tables_2x2),
                            ("eval_accuracy", acc)):
            frame.to_csv(tables / f"{name}.csv", index=False, float_format="%.6g")
            written[name] = tables / f"{name}.csv"
        for p in figures.plot_eval_bars(acc, fig_dir, banner):
            written[p.name] = p

    desc = [
        "# Descriptive tables",
        "",
        f"## Stored rate by cell at checkpoint {ck} (test probes, 95% fact-bootstrap CI)",
        "",
        dsc.to_markdown(cells),
        "",
        "## Acquisition (first checkpoint with >= half of a fact-seed's probes stored)",
        "",
        dsc.to_markdown(acq),
    ]
    written["descriptive"] = tables / "analysis_descriptive.md"
    written["descriptive"].write_text("\n".join(desc) + "\n", encoding="utf-8")
    fam.to_csv(tables / "analysis_family.csv", index=False, float_format="%.6g")
    written["family_csv"] = tables / "analysis_family.csv"
    meta = {
        "checkpoint": int(ck),
        "n_facts": int(primary["fact_id"].nunique()),
        "n_probe_rows": int(len(primary)),
        "n_seeds": int(primary["seed"].nunique()),
        "n_val_rows_excluded": n_val,
        "gee_converged": bool(res is not None and res.converged),
    }
    (tables / "analysis_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    rd.to_csv(tables / "analysis_risk_differences.csv", index=False, float_format="%.6g")
    cells.to_csv(tables / "analysis_cell_rates.csv", index=False, float_format="%.6g")
    written["risk_differences"] = tables / "analysis_risk_differences.csv"
    written["cell_rates"] = tables / "analysis_cell_rates.csv"
    if res is not None:
        res.simple.to_csv(tables / "analysis_simple_effects.csv", index=False,
                          float_format="%.6g")
        written["simple_effects"] = tables / "analysis_simple_effects.csv"

    figs = figures.plot_stored_by_cell(cells, fig_dir, ck, banner) + figures.plot_learning_curves(
        curves[curves["checkpoint"] > 0], fig_dir, banner
    )
    for p in figs:
        written[p.name] = p
    return written
