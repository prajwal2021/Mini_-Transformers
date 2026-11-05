"""One-command analysis: probe table (+ QA table) -> H1-H4, effect sizes, tables, figures."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import descriptive as dsc
from . import figures
from .extraction import run_extraction
from .family import assemble_family
from .models import fit_bayes_mixed, fit_gee, prepare_primary
from .schema import PROBE_OPTIONAL, normalize_probe_table


def _read(path: Path | str) -> pd.DataFrame:
    path = Path(path)
    return pd.read_csv(path) if path.suffix == ".csv" else pd.read_parquet(path)


def _family_md(fam: pd.DataFrame) -> str:
    cols = ["hypothesis", "label", "scale", "estimate", "ci_low", "ci_high", "p_raw", "p_holm",
            "direction_ok", "status"]
    return dsc.to_markdown(fam[cols], "{:.4g}")


def run_analysis(
    input_path: Path | str,
    out_dir: Path | str = "reports",
    checkpoint: int | str = "final",
    qa_path: Path | str | None = None,
    mixed_sensitivity: bool = True,
) -> dict[str, Path]:
    """Run the full pre-registered analysis; return the paths written."""
    out = Path(out_dir)
    tables, fig_dir = out / "tables", out / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    path = Path(input_path)
    raw = _read(path)
    primary, ck, warns = prepare_primary(raw, checkpoint)
    n_val = int((raw["split"] == "val").sum()) if "split" in raw else 0
    norm = normalize_probe_table(raw)
    test_all = norm[norm["split"] == "test"]

    has_cov = any(c in primary.columns for c in PROBE_OPTIONAL + ("attribute_id",))
    res = fit_gee(primary, covariates=has_cov)
    ext = run_extraction(_read(qa_path)) if qa_path is not None else None
    fam = assemble_family(res.family, None if ext is None else ext.family)

    rd = dsc.risk_difference_table(primary)
    cells = dsc.cell_rates(primary)
    curves = dsc.curve_rates(test_all)
    acq = dsc.acquisition_table(test_all[test_all["checkpoint"] > 0])

    written: dict[str, Path] = {}
    lines = [
        "# Primary analysis: H1-H4",
        "",
        f"Probe table: `{path.name}`; test rows only ({n_val} val rows excluded); primary "
        f"checkpoint {ck}; rows {res.n_rows}; facts (clusters) {res.n_clusters}; "
        f"converged {res.converged}.",
        "",
        "## Confirmatory family (Holm across H1-H4)",
        "",
        _family_md(fam),
        "",
    ]
    if ext is None:
        lines += ["H3 and H4 were not run (no QA table); Holm treats their p-values as 1, so the "
                  "adjusted p-values above are provisional upper bounds.", ""]
    lines += [
        "## H1 / H2 model",
        "",
        f"Formula: `{res.formula}`",
        f"Estimator: logistic GEE, groups = fact_id, covariance `{res.covariance}`. Estimates "
        "are population-averaged log-odds; CIs and p-values use t with (clusters - parameters) "
        "degrees of freedom.",
        "",
        "Supporting simple effects of diversity within each frame (at mid exposure; "
        "paraphrased - templated, log-odds):",
        "",
        dsc.to_markdown(res.simple),
        "",
        "## Effect sizes on the risk-difference scale (95% fact-bootstrap CI)",
        "",
        dsc.to_markdown(rd),
        "",
        "## All coefficients",
        "",
        dsc.to_markdown(
            res.table[["term", "estimate", "se", "p_raw", "ci_low", "ci_high", "odds_ratio"]],
            "{:.4g}",
        ),
    ]
    if warns or res.warnings:
        lines += ["", "## Warnings", ""] + [f"- {w}" for w in warns + res.warnings]
    if mixed_sensitivity:
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
            "# Extraction tests: H3 and H4 (E2, held-out facts)",
            "",
            f"QA table: `{Path(qa_path).name}`; facts {ext.n_facts}. Unit = fact (majority of "
            "seeds x items); comparator = base_2shot.",
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

    figs = figures.plot_stored_by_cell(cells, fig_dir, ck) + figures.plot_learning_curves(
        curves[curves["checkpoint"] > 0], fig_dir
    )
    for p in figs:
        written[p.name] = p
    return written
