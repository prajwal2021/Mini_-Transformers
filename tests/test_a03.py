"""A03: aggregation rules, realized diversity, sensitivity, separation, banner, report builder."""

import json
import re
import shutil

import numpy as np
import pandas as pd
import pytest

from slm.analysis import figures
from slm.analysis.aggregation import RULES, apply_rule
from slm.analysis.models import (
    add_codes,
    add_realized_diversity,
    check_separation,
    fit_gee,
    fit_gee_robust,
    prepare_primary,
)
from slm.analysis.pipeline import run_analysis
from slm.analysis.schema import SchemaError, validate_realized_diversity
from slm.analysis.sensitivity import run_sensitivity, sensitivity_markdown
from slm.analysis.simulate import (
    SimParams,
    simulate_probe_table,
    simulate_qa_table,
    simulate_realized_diversity,
)
from slm.analysis.validate import manipulation_study
from slm.report import markup, pdf
from slm.report.build import TEMPLATE, build, run_simulated_analysis
from slm.report.inputs import InputError, load_inputs
from slm.report.numbers import NumbersError, collect_numbers

# --- aggregation rules -------------------------------------------------------------------------


def test_rules_match_the_prereg_definitions():
    share = np.array([0.0, 1 / 3, 2 / 3, 1.0])
    assert list(apply_rule(share, "any")) == [0, 1, 1, 1]
    assert list(apply_rule(share, "majority")) == [0, 0, 1, 1]  # >= 2 of 3
    assert list(apply_rule(share, "all")) == [0, 0, 0, 1]
    assert RULES == ("any", "majority", "all")
    with pytest.raises(ValueError):
        apply_rule(share, "most")


# --- realized diversity ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def weak():
    p = SimParams(exposure_noise_sd=0.25, manipulation_strength=0.6)
    probe = simulate_probe_table(p, seed=3, include_val=True)
    qa = simulate_qa_table(p, probe[probe["split"] == "test"], seed=4)
    return p, probe, qa, simulate_realized_diversity(p, 3)


def test_realized_diversity_schema(weak):
    _, probe, _, rd = weak
    validate_realized_diversity(rd, set(probe["fact_id"]))
    with pytest.raises(SchemaError, match="duplicate"):
        validate_realized_diversity(pd.concat([rd, rd.iloc[:1]]))
    with pytest.raises(SchemaError, match="\\[0, 1\\]"):
        validate_realized_diversity(rd.assign(mean_pairwise_jaccard=1.5))
    with pytest.raises(SchemaError, match="no row"):
        validate_realized_diversity(rd.iloc[:-5], set(probe["fact_id"]))
    with pytest.raises(SchemaError, match="missing required"):
        validate_realized_diversity(rd.drop(columns=["n_reused"]))


def test_realized_diversity_tracks_condition_and_is_standardised(weak):
    _, probe, _, rd = weak
    sub, _, _ = prepare_primary(probe)
    z = add_realized_diversity(sub, rd)
    per_fact = z.groupby("fact_id")[["div_bin", "rdiv_z"]].first()
    assert abs(per_fact["rdiv_z"].mean()) < 1e-9 and abs(per_fact["rdiv_z"].std(ddof=0) - 1) < 1e-9
    gap = (per_fact[per_fact["div_bin"] == "paraphrased"]["rdiv_z"].mean()
           - per_fact[per_fact["div_bin"] == "templated"]["rdiv_z"].mean())
    assert gap > 0.5
    assert (rd["n_distinct"] + rd["n_reused"]).gt(0).all()


def test_weak_manipulation_biases_nominal_h2_toward_null_and_realized_recovers():
    study = manipulation_study(
        SimParams(n_facts_per_cell=40), strengths=(1.0, 0.3), n_rep=24, seed0=7_000
    ).set_index("manipulation_strength")
    assert study.loc[0.3, "nominal_H2_mean"] < 0.6 * study.loc[1.0, "nominal_H2_mean"]
    assert study.loc[0.3, "nominal_H2_power"] < study.loc[1.0, "nominal_H2_power"]
    assert study.loc[0.3, "realized_x_full_contrast"] > 1.5 * study.loc[0.3, "nominal_H2_mean"]


def test_realized_models_fit_and_variants_change_the_formula(weak):
    _, probe, _, rd = weak
    sub, _, _ = prepare_primary(probe)
    z = add_realized_diversity(sub, rd)
    nominal = fit_gee(z)
    realized = fit_gee(z, diversity="realized")
    both = fit_gee(z, diversity="both")
    assert "rdiv_z" in realized.formula and "div_c" not in realized.formula
    assert "div_c" in both.formula and "rdiv_z" in both.formula
    assert "pv_1" in nominal.formula and "pv_1" not in fit_gee(z, variant_terms=False).formula
    assert realized.simple.empty


# --- exposure coding, per-seed final checkpoint ------------------------------------------------


def test_measured_and_bin_exposure_codes_differ_only_with_noise(weak):
    _, probe, _, _ = weak
    sub, _, _ = prepare_primary(probe)
    bins = add_codes(sub, "bins")["freq_c"]
    measured = add_codes(sub, "measured")["freq_c"]
    assert not np.allclose(bins, measured) and np.corrcoef(bins, measured)[0, 1] > 0.9
    clean = simulate_probe_table(seed=2, final_only=True)
    assert np.allclose(add_codes(clean, "bins")["freq_c"], add_codes(clean, "measured")["freq_c"])


def test_primary_rows_are_the_final_checkpoint_of_each_seed():
    df = simulate_probe_table(seed=6)
    drop = (df["seed"] == 2) & (df["checkpoint"] == df["checkpoint"].max())
    sub, ck, warns = prepare_primary(df[~drop])
    finals = sub.groupby("seed")["checkpoint"].first()
    assert finals[0] == finals[1] == df["checkpoint"].max() and finals[2] < finals[0]
    assert ck == df["checkpoint"].max() and any("differ across seeds" in w for w in warns)


# --- complete separation -----------------------------------------------------------------------


def test_separation_is_detected_and_the_ladder_does_not_crash():
    df = simulate_probe_table(seed=8, final_only=True)
    sub = add_codes(df[df["split"] == "test"])
    assert len(check_separation(sub)) == 0
    sep = sub.copy()
    cell = (sep["freq_bin"] == "low") & (sep["div_bin"] == "templated") & (
        sep["probe_frame"] == "novel")
    sep.loc[cell, "stored"] = 0
    flagged = check_separation(sep)
    assert len(flagged) == 1 and flagged.iloc[0]["freq_bin"] == "low"
    res, log = fit_gee_robust(sep)
    assert any("separation risk" in m for m in log)
    assert res is None or np.isfinite(res.table["estimate"]).all()
    all_zero = sub.assign(stored=0)  # total separation: every fit must fail gracefully
    res0, log0 = fit_gee_robust(all_zero)
    assert res0 is None and any("non-informative" in m for m in log0)


def test_run_analysis_survives_total_separation(tmp_path):
    df = simulate_probe_table(seed=9, include_val=True)
    last = df["checkpoint"].max()
    df.loc[df["checkpoint"] == last, ["rank", "binding_score"]] = [2, -0.5]
    df.loc[df["checkpoint"] == last, "stored"] = 0
    df.loc[df["checkpoint"] == last, "true_logprob"] = (
        df.loc[df["checkpoint"] == last, "baseline_logprob"] - 0.5
    )
    path = tmp_path / "p.csv"
    df.to_csv(path, index=False)
    written = run_analysis(path, tmp_path / "o", mixed_sensitivity=False)
    fam = pd.read_csv(written["family_csv"]).set_index("hypothesis")
    assert fam.loc["H1", "p_raw"] == 1.0 and fam.loc["H1", "p_holm"] == 1.0


# --- sensitivity -------------------------------------------------------------------------------


def test_sensitivity_runs_all_analyses(weak, tmp_path):
    _, probe, qa, rd = weak
    table, extras = run_sensitivity(probe, qa, rd, n_boot=100, n_perm=300)
    names = set(table["analysis"])
    for expected in (
        "exposure coding: bins", "exposure coding: measured", "without prompt_variant terms",
        "outcome: stored_tokennorm", "realized diversity replaces div_bin",
        "div_bin and realized diversity together", "fact-level rule: any",
        "fact-level rule: all", "comparator: base_0shot (secondary)",
    ):
        assert expected in names, expected
    assert any(n.startswith("Bayesian mixed logit") for n in names)
    assert any(n.startswith("fact-level rule: majority") for n in names)
    is_rule = table["analysis"].str.startswith("fact-level rule")
    rules = table[is_rule & table["hypothesis"].eq("H4")]
    assert len(rules) == 3
    md = sensitivity_markdown(table, extras)
    assert "# Sensitivity analyses" in md and "Complete separation" in md


def test_sensitivity_reports_what_it_skipped(weak):
    _, probe, _, _ = weak
    table, _ = run_sensitivity(probe.drop(columns=["stored_tokennorm", "train_mentions"]))
    skipped = table[table["note"].str.startswith("skipped")]["analysis"].tolist()
    assert any("tokennorm" in s for s in skipped) and any("exposure coding" in s for s in skipped)
    assert any("realized" in s for s in skipped) and any("aggregation" in s for s in skipped)


# --- banner on figures -------------------------------------------------------------------------


def test_banner_is_on_by_default_and_off_only_when_real(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(figures, "add_banner", lambda fig: calls.append(1))
    loss = pd.DataFrame(
        {
            "seed": 0,
            "step": [1, 10, 1, 10],
            "split": ["train", "train", "val", "val"],
            "loss": [3.0, 2.0, 3.1, 2.2],
        }
    )
    figures.plot_loss_curves(loss, tmp_path / "a")
    assert len(calls) == 1
    figures.plot_loss_curves(loss, tmp_path / "b", banner=False)
    assert len(calls) == 1


def test_add_banner_marks_the_figure():
    import matplotlib.pyplot as plt

    fig = plt.figure()
    assert not figures.has_banner(fig)
    figures.add_banner(fig)
    assert figures.has_banner(fig)
    plt.close(fig)


# --- report: macros, lint, pdf -----------------------------------------------------------------


def test_template_has_no_bare_numbers():
    assert markup.lint_template(TEMPLATE.read_text(encoding="utf-8")) == []


def test_lint_flags_typed_numbers_and_allows_names_and_macros():
    assert markup.lint_template("H1 and E2, base_2shot, {{key:.2f}} and the 2-shot base") == []
    bad = markup.lint_template("accuracy was 0.82 and 120 facts")
    assert len(bad) == 2 and "0.82" in bad[0]


def test_unknown_macro_and_typed_number_are_build_errors():
    ctx = markup.RenderContext({"a": {"value": 1.5, "source": "x"}}, None, pd.DataFrame(), True)
    assert markup.render_template("value {{a:.2f}}", ctx) == "value 1.50"
    with pytest.raises(markup.TemplateError, match="no source"):
        markup.render_template("value {{b}}", ctx)
    with pytest.raises(markup.TemplateError, match="numbers typed"):
        markup.render_template("value 3", ctx)


def test_page_count_parser_and_gate(tmp_path):
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    path = tmp_path / "x.pdf"
    with PdfPages(path) as pp:
        for _ in range(3):
            fig = plt.figure()
            pp.savefig(fig)
            plt.close(fig)
    assert pdf.pdf_page_count(path) == 3
    assert pdf.check_page_count(path, 3, 3) == 3
    with pytest.raises(pdf.PageCountError, match="3 pages"):
        pdf.check_page_count(path, 5, 7)


def test_matplotlib_pages_all_carry_the_banner(tmp_path):
    import matplotlib.pyplot as plt

    blocks = markup.parse_blocks("# T\n\n" + "\n\n".join(["word " * 150] * 30))
    pages = pdf.render_pages(blocks, True, tmp_path)
    assert len(pages) > 1
    assert all(any(markup.BANNER_TEXT in t.get_text() for t in f.texts) for f in pages)
    off = pdf.render_pages(blocks, False, tmp_path)
    assert not any(markup.BANNER_TEXT in t.get_text() for f in off for t in f.texts)
    for f in pages + off:
        plt.close(f)


def test_html_banner_is_in_every_printed_page_header():
    blocks = markup.parse_blocks("# T\n\ntext")
    on = markup.blocks_to_html(blocks, True)
    assert markup.BANNER_TEXT in on and "<thead>" in on and "SIMULATED" in on
    assert markup.BANNER_TEXT not in markup.blocks_to_html(blocks, False)


def test_inputs_and_numbers_fail_loudly(tmp_path):
    with pytest.raises(InputError, match="missing report inputs"):
        load_inputs(tmp_path)
    with pytest.raises(NumbersError, match="missing result files"):
        collect_numbers(tmp_path, tmp_path)


@pytest.fixture(scope="module")
def sim_work(tmp_path_factory):
    work = tmp_path_factory.mktemp("sim_report")
    inputs, results = run_simulated_analysis(work, seed=0)
    return inputs, results


@pytest.mark.slow
def test_simulated_build_is_bannered_sourced_and_within_page_range(sim_work, tmp_path):
    inputs, results = sim_work
    res = build(tmp_path / "sim", simulate=False, real=False, results_dir=results,
                inputs_dir=inputs, backend="matplotlib")
    assert res.banner and 5 <= res.pages <= 7 and res.backend == "matplotlib"
    md = res.markdown.read_text(encoding="utf-8")
    assert markup.BANNER_TEXT in md and markup.BANNER_TEXT in res.html.read_text(encoding="utf-8")
    numbers = json.loads(res.numbers.read_text(encoding="utf-8"))
    assert numbers and all(v["source"] for v in numbers.values())
    # every number quoted for H1-H4 in the text is the formatted value of a sourced result
    for h in ("H1", "H2", "H3", "H4"):
        assert numbers[f"sentence.{h}"]["value"] in md
    # no macro is left unresolved and every figure file exists
    assert "{{" not in md
    for fig in re.findall(r"\]\((figures/[^)]+)\)", md):
        assert (res.markdown.parent / fig).exists()
    assert len(re.findall(r"\*\*Table \d+\.\*\*", md)) >= 4


@pytest.mark.slow
def test_page_gate_fails_the_build_outside_the_range(sim_work, tmp_path):
    inputs, results = sim_work
    with pytest.raises(pdf.PageCountError):
        build(tmp_path / "gate", simulate=False, results_dir=results, inputs_dir=inputs,
              backend="matplotlib", min_pages=1, max_pages=2)


@pytest.mark.slow
def test_real_flag_removes_the_banner_and_simulate_refuses_it(sim_work, tmp_path):
    inputs, results = sim_work
    real_results = tmp_path / "results"
    shutil.copytree(results, real_results)
    real = build(tmp_path / "real", simulate=False, real=True, results_dir=real_results,
                 inputs_dir=inputs, backend="matplotlib", min_pages=1, max_pages=20)
    assert not real.banner
    assert markup.BANNER_TEXT not in real.markdown.read_text(encoding="utf-8")
    assert markup.BANNER_TEXT not in real.html.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="mutually exclusive"):
        build(tmp_path / "bad", simulate=True, real=True)


@pytest.mark.slow
@pytest.mark.skipif(pdf.find_chrome() is None, reason="no Chrome/Edge")
def test_chrome_backend_builds_a_pdf_in_range(sim_work, tmp_path):
    inputs, results = sim_work
    res = build(tmp_path / "chrome", simulate=False, results_dir=results, inputs_dir=inputs,
                backend="chrome")
    assert res.backend == "chrome" and 5 <= res.pages <= 7
