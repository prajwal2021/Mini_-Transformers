"""Collect every number the report may quote, each with the file it came from.

The report text refers to numbers only through `{{key}}` macros; a number typed into the
template is a build error (see markup.lint_template). `collect_numbers` returns
{key: {"value": ..., "source": "<file>[:<locator>]"}} and the builder writes it to numbers.json
so any figure in the text can be traced to a result file.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .inputs import load_inputs

Numbers = dict[str, dict]

TABLE_FILES = (
    "analysis_family.csv",
    "analysis_simple_effects.csv",
    "analysis_components.csv",
    "analysis_per_condition.csv",
    "eval_accuracy.csv",
    "analysis_cell_rates.csv",
    "analysis_risk_differences.csv",
    "sensitivity.csv",
)


class NumbersError(ValueError):
    """A required result file or key is missing."""


def _put(out: Numbers, key: str, value, source: str) -> None:
    if isinstance(value, (np.integer,)):
        value = int(value)
    elif isinstance(value, (np.floating,)):
        value = float(value)
    out[key] = {"value": value, "source": source}


def finding_sentence(n: Numbers, hid: str) -> str:
    """One sentence per hypothesis, written from the numbers so it is true for any outcome."""
    v = lambda k: n[f"{hid}.{k}"]["value"]  # noqa: E731
    est, lo, hi = v("estimate"), v("ci_low"), v("ci_high")
    if hid in ("H1", "H2"):
        unit = "log-odds"
        what = {"H1": "per tripling of exposure",
                "H2": "for the diversity x frame interaction (paraphrased advantage, novel "
                      "minus canonical)"}[hid]
    elif hid == "H3":
        unit, what = "risk difference", "for the SFT gain on E2 (SFT minus 2-shot base)"
    else:
        unit, what = "risk difference", "for the gain difference (paraphrased minus templated)"
    head = f"{hid}: estimate {est:.2f} {unit} {what}, 95% CI {lo:.2f} to {hi:.2f}"
    if hid == "H4":
        return head + "; secondary hypothesis, effect and CI only (no significance claim)."
    return f"{head}; Holm-adjusted p {v('p_holm'):.3g}; outcome: {v('status')}."


def collect_numbers(results_dir: Path, inputs_dir: Path) -> Numbers:
    """Read the analysis tables and run inputs; return the sourced number dictionary."""
    tdir = results_dir / "tables"
    missing = [f for f in TABLE_FILES if not (tdir / f).exists()]
    if missing:
        raise NumbersError(f"missing result files in {tdir}: {missing}")
    out: Numbers = {}
    rel = lambda f: f"tables/{f}"  # noqa: E731

    fam = pd.read_csv(tdir / "analysis_family.csv").set_index("hypothesis")
    for h, r in fam.iterrows():
        for col in ("estimate", "ci_low", "ci_high", "p_raw", "p_holm", "status", "label"):
            _put(out, f"{h}.{col}", r[col], f"{rel('analysis_family.csv')}:{h}.{col}")
        _put(out, f"{h}.odds_ratio" if r["scale"] == "log-odds" else f"{h}.gain",
             math.exp(r["estimate"]) if r["scale"] == "log-odds" else r["estimate"],
             f"{rel('analysis_family.csv')}:{h}.estimate")
    for h in ("H1", "H2", "H3", "H4"):
        if f"{h}.estimate" not in out:
            raise NumbersError(f"analysis_family.csv has no row for {h}")
    _put(out, "n_holm", 3, "PREREG: Holm family H1-H3")
    _put(out, "ci_level", 95, "PREREG section 5: 95% confidence intervals")

    simple = pd.read_csv(tdir / "analysis_simple_effects.csv").set_index("frame")
    for frame, r in simple.iterrows():
        for col in ("div_effect_log_odds", "ci_low", "ci_high"):
            _put(out, f"simple.{frame}.{col}", r[col], f"{rel('analysis_simple_effects.csv')}")

    comp = pd.read_csv(tdir / "analysis_components.csv").set_index("component")
    for c, r in comp.iterrows():
        for col in ("estimate", "ci_low", "ci_high", "p_raw"):
            _put(out, f"{c}.{col}", r[col], f"{rel('analysis_components.csv')}:{c}.{col}")

    cond = pd.read_csv(tdir / "analysis_per_condition.csv").set_index("div_bin")
    for d, r in cond.iterrows():
        for col in ("n_facts", "acc_base", "acc_sft", "gain"):
            _put(out, f"cond.{d}.{col}", r[col], f"{rel('analysis_per_condition.csv')}:{d}")
    _put(out, "n_e2_facts", int(cond["n_facts"].sum()), rel("analysis_per_condition.csv"))

    acc = pd.read_csv(tdir / "eval_accuracy.csv")
    for _, r in acc.iterrows():
        for col in ("accuracy", "ci_low", "ci_high"):
            _put(out, f"acc.{r['eval_set']}.{r['model']}.{col}", r[col],
                 f"{rel('eval_accuracy.csv')}:{r['eval_set']}/{r['model']}")

    cells = pd.read_csv(tdir / "analysis_cell_rates.csv")
    _put(out, "stored_rate_overall", cells["stored_rate"].mean(), rel("analysis_cell_rates.csv"))
    for _, r in cells.iterrows():
        key = f"rate.{r['freq_bin']}.{r['div_bin']}.{r['probe_frame']}"
        _put(out, key, r["stored_rate"], f"{rel('analysis_cell_rates.csv')}")

    rd = pd.read_csv(tdir / "analysis_risk_differences.csv").set_index("contrast")
    for c, r in rd.iterrows():
        slug = c.split(" ")[0].replace("-", "_")
        for col in ("risk_difference", "ci_low", "ci_high"):
            _put(out, f"rd.{slug}.{col}", r[col], f"{rel('analysis_risk_differences.csv')}:{c}")

    sens = pd.read_csv(tdir / "sensitivity.csv")
    for key, mask in (
        ("sens.realized_H2", sens["analysis"].str.startswith("realized diversity replaces")
         & sens["hypothesis"].str.startswith("H2")),
        ("sens.primary_H2", sens["analysis"].str.startswith("primary")
         & (sens["hypothesis"] == "H2")),
        ("sens.bins_H1", sens["analysis"].eq("exposure coding: bins")
         & (sens["hypothesis"] == "H1")),
        ("sens.tokennorm_H1", sens["analysis"].eq("outcome: stored_tokennorm")
         & (sens["hypothesis"] == "H1")),
        ("sens.any_H3", sens["analysis"].str.startswith("fact-level rule: any")
         & sens["hypothesis"].str.startswith("H3")),
        ("sens.all_H3", sens["analysis"].str.startswith("fact-level rule: all")
         & sens["hypothesis"].str.startswith("H3")),
    ):
        rows = sens[mask]
        if len(rows):
            for col in ("estimate", "ci_low", "ci_high"):
                _put(out, f"{key}.{col}", rows.iloc[0][col], rel("sensitivity.csv"))

    meta_path = tdir / "analysis_meta.json"
    if not meta_path.exists():
        raise NumbersError(f"missing {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for k, v in meta.items():
        _put(out, f"meta.{k}", v, rel("analysis_meta.json"))

    facts, loss, samples = load_inputs(inputs_dir)
    for k, v in facts.items():
        _put(out, f"run.{k}", v, f"{inputs_dir.name}/run_facts.json:{k}")
    last = loss.sort_values("step").groupby(["seed", "split"]).tail(1)
    for split in ("train", "val"):
        _put(out, f"loss.{split}_final", last[last["split"] == split]["loss"].mean(),
             f"{inputs_dir.name}/loss_curves.csv: final step, mean over seeds")
    _put(out, "loss.val_perplexity", math.exp(out["loss.val_final"]["value"]),
         "exp(loss.val_final)")
    val = loss[loss["split"] == "val"].groupby("step")["loss"].mean()
    _put(out, "loss.val_min_step", int(val.idxmin()), f"{inputs_dir.name}/loss_curves.csv")
    kinds = samples["category"].str.split(":").str[0]
    _put(out, "n_success", int((kinds == "success").sum()), f"{inputs_dir.name}/samples.csv")
    _put(out, "n_failure", int((kinds == "failure").sum()), f"{inputs_dir.name}/samples.csv")

    for h in ("H1", "H2", "H3", "H4"):
        _put(out, f"sentence.{h}", finding_sentence(out, h), "derived from analysis_family.csv")
    return out
