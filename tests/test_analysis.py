"""Analysis pipeline tests, probe table / H1 / H2 (simulated data only)."""

import hashlib

import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.multitest import multipletests

from scripts.run_analysis import main as run_main
from slm.analysis import descriptive as dsc
from slm.analysis.models import (
    add_codes,
    fit_gee,
    fit_primary,
    holm,
    prepare_primary,
    primary_checkpoint,
)
from slm.analysis.schema import (
    PROBE_REQUIRED,
    SchemaError,
    normalize_probe_table,
    validate_probe_table,
)
from slm.analysis.simulate import (
    SimParams,
    checkpoint_steps,
    simulate_probe_table,
)
from slm.analysis.validate import null_summary, probe_truth, run_replicates


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return simulate_probe_table(seed=3, include_val=True)


def test_simulator_is_seeded_and_matches_contract(table):
    pd.testing.assert_frame_equal(table, simulate_probe_table(seed=3, include_val=True))
    assert not table.equals(simulate_probe_table(seed=4, include_val=True))
    assert set(PROBE_REQUIRED) <= set(table.columns)
    assert "regime" not in table.columns
    assert validate_probe_table(table) == []
    p = SimParams()
    # 6 cells x 20 facts x 3 seeds x (4 test + 2 val variants) x checkpoints
    assert len(table) == 120 * p.n_seeds * 6 * len(checkpoint_steps(p))
    assert set(table["probe_frame"]) == {"canonical", "novel"}
    nested = table.groupby("prompt_variant")["probe_frame"].nunique()
    assert (nested == 1).all()


def test_final_only_equals_last_checkpoint_shape():
    full = simulate_probe_table(seed=5)
    last = simulate_probe_table(seed=5, final_only=True)
    assert last["checkpoint"].nunique() == 1
    assert last["checkpoint"].iloc[0] == full["checkpoint"].max()


def test_learning_curve_rises(table):
    by_ck = table.groupby("checkpoint")["stored"].mean()
    assert by_ck.iloc[-1] > by_ck.iloc[0] + 0.2


@pytest.mark.parametrize(
    "mutate, msg",
    [
        (lambda d: d.drop(columns=["true_logprob"]), "missing required"),
        (lambda d: d.assign(probe_frame="weird"), "unexpected levels"),
        (lambda d: d.assign(rank=9), "rank"),
        (lambda d: d.assign(stored=1 - d["stored"]), "disagrees"),
        (lambda d: d.assign(true_logprob=d["true_logprob"] + 1.0), "binding_score !="),
        (lambda d: pd.concat([d, d.iloc[:1]]), "duplicate"),
        (lambda d: d.assign(split="val"), "no test-split"),
    ],
)
def test_schema_rejects_violations(table, mutate, msg):
    with pytest.raises(SchemaError, match=msg):
        validate_probe_table(mutate(table.copy()))


def test_variant_in_two_frames_is_rejected(table):
    bad = table.copy()
    first = bad.index[bad["prompt_variant"] == "test-n1"][0]
    bad.loc[first, "probe_frame"] = "canonical"
    with pytest.raises(SchemaError, match="exactly one probe_frame"):
        validate_probe_table(bad)


def test_init_checkpoint_maps_to_zero(table):
    t = table.copy()
    t["checkpoint"] = t["checkpoint"].astype(str)
    t.loc[t["checkpoint"] == str(t["checkpoint"].astype(int).min()), "checkpoint"] = "init"
    norm = normalize_probe_table(t)
    assert (norm["checkpoint"] == 0).any() and norm["checkpoint"].dtype.kind == "i"


def test_val_rows_never_enter_the_fit(table):
    sub, ck, _ = prepare_primary(table)
    assert set(sub["split"]) == {"test"}
    assert ck == table["checkpoint"].max()
    assert not sub["prompt_variant"].str.startswith("val").any()


def test_holm_matches_statsmodels():
    rng = np.random.default_rng(0)
    for _ in range(50):
        p = rng.uniform(0, 0.1, 4)
        adj, rej = holm(p)
        ref_rej, ref_adj, _, _ = multipletests(p, alpha=0.05, method="holm")
        np.testing.assert_allclose(adj, ref_adj)
        assert (rej == ref_rej).all()


def test_primary_checkpoint_is_final(table):
    assert primary_checkpoint(table) == table["checkpoint"].max()
    assert primary_checkpoint(table, 537) == 537


def test_gee_recovers_signs_and_h2_is_the_interaction():
    df = simulate_probe_table(SimParams(n_facts_per_cell=30), seed=11, final_only=True)
    res = fit_gee(add_codes(df))
    fam = res.family.set_index("hypothesis")
    assert res.converged and res.n_clusters == 180
    assert fam.loc["H1", "estimate"] > 0 and fam.loc["H2", "estimate"] > 0
    assert (fam["ci_low"] < fam["estimate"]).all() and (fam["estimate"] < fam["ci_high"]).all()
    assert "div_c:frame_c" in set(res.table["term"])
    # templated facts are penalised on novel probes more than paraphrased ones
    simple = res.simple.set_index("frame")["div_effect_log_odds"]
    assert simple["novel"] > simple["canonical"]
    assert "frame_c" in res.formula and "regime" not in res.formula


def test_template_dummies_are_not_collinear_with_frame(table):
    sub, _, _ = prepare_primary(table)
    pv = [c for c in sub.columns if c.startswith("pv_")]
    assert len(pv) == 2  # 3 novel variants -> 2 dummies; the single canonical variant -> none
    design = sub[["frame_c", *pv]].assign(const=1.0).to_numpy()
    assert np.linalg.matrix_rank(design) == design.shape[1]


def test_measured_mentions_replace_bin_codes(table):
    t = table.copy()
    t["train_mentions"] = t["freq_bin"].map({"low": 5, "mid": 15, "high": 45})
    coded = add_codes(t[t["checkpoint"] == t["checkpoint"].max()])
    # log3(5), log3(15), log3(45) are one tripling apart (up to centering)
    by_bin = coded.groupby("freq_bin")["freq_c"].first()
    assert abs((by_bin["high"] - by_bin["mid"]) - 1.0) < 1e-9
    assert abs((by_bin["mid"] - by_bin["low"]) - 1.0) < 1e-9


def test_probe_truth_is_attenuated_but_same_sign():
    p = SimParams()
    truth = probe_truth(p, n_facts_per_cell=300)
    assert 0 < truth["H1"] < p.b_freq
    assert 0 < truth["H2"] < p.b_div_frame


def test_risk_differences_are_deterministic_and_signed(table):
    sub, _, _ = prepare_primary(table)
    a = dsc.risk_difference_table(sub, b=300)
    b = dsc.risk_difference_table(sub, b=300)
    pd.testing.assert_frame_equal(a, b)
    rd = a.set_index("contrast")
    assert rd.loc["H1", "risk_difference"] > 0 and rd.loc["H2", "risk_difference"] > 0
    assert rd.loc["H2-novel", "risk_difference"] > rd.loc["H2-canonical", "risk_difference"]


def test_fit_primary_ignores_earlier_checkpoints(table):
    res, ck = fit_primary(table)
    sub, _, _ = prepare_primary(table)
    assert ck == table["checkpoint"].max() and res.n_rows == len(sub)


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_analysis_end_to_end_is_deterministic(table, tmp_path):
    from slm.analysis.simulate import simulate_qa_table

    probe = tmp_path / "probe.csv"
    qa = tmp_path / "qa.csv"
    table.to_csv(probe, index=False)
    simulate_qa_table(SimParams(), table[table["split"] == "test"], seed=9).to_csv(qa, index=False)
    out1, out2 = tmp_path / "a", tmp_path / "b"
    for out in (out1, out2):
        args = ["--input", str(probe), "--qa-input", str(qa), "--out", str(out), "--no-mixed"]
        assert run_main(args) == 0
    names = [
        "tables/analysis_model.md",
        "tables/analysis_extraction.md",
        "tables/analysis_descriptive.md",
        "tables/analysis_family.csv",
        "figures/stored_rate_by_cell.png",
        "figures/stored_rate_by_cell.pdf",
        "figures/learning_curves.png",
        "figures/learning_curves.pdf",
    ]
    for name in names:
        assert (out1 / name).exists(), name
        assert _digest(out1 / name) == _digest(out2 / name), name
    fam = pd.read_csv(out1 / "tables/analysis_family.csv")
    assert list(fam["hypothesis"]) == ["H1", "H2", "H3", "H4"]
    assert not fam["provisional"].any()


def test_run_analysis_without_qa_is_provisional(table, tmp_path):
    probe = tmp_path / "probe.csv"
    table.to_csv(probe, index=False)
    assert run_main(["--input", str(probe), "--out", str(tmp_path / "o"), "--no-mixed"]) == 0
    fam = pd.read_csv(tmp_path / "o/tables/analysis_family.csv")
    assert list(fam["hypothesis"]) == ["H1", "H2"] and fam["provisional"].all()


def test_null_replicates_run_and_summarise():
    reps = run_replicates(SimParams().null(), 6, seed0=7)
    summ = null_summary(reps).set_index("test")
    fw = summ.loc["any of H1-H4 (family-wise)"]
    assert fw["rejection_holm"] <= fw["rejection_raw"]
    assert {"H1", "H2", "H3", "H4"} <= set(summ.index)


@pytest.mark.slow
def test_null_false_positive_rate_is_controlled():
    reps = run_replicates(SimParams().null(), 200, seed0=50_000)
    summ = null_summary(reps).set_index("test")
    assert summ.loc["any of H1-H4 (family-wise)", "rejection_holm"] <= 0.10
    for h in ("H1", "H2", "H3", "H4"):
        assert summ.loc[h, "rejection_raw"] <= 0.12
