"""A01 analysis pipeline tests (simulated data only)."""

import hashlib

import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.multitest import multipletests

from scripts.run_analysis import main as run_main
from slm.analysis import descriptive as dsc
from slm.analysis.models import FAMILY, add_codes, fit_gee, fit_primary, holm, primary_checkpoint
from slm.analysis.schema import REQUIRED_COLUMNS, SchemaError, validate_table
from slm.analysis.simulate import SimParams, checkpoint_steps, simulate_probe_table
from slm.analysis.validate import marginal_truth, null_summary, run_replicates


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return simulate_probe_table(seed=3)


def test_simulator_is_seeded_and_matches_contract(table):
    again = simulate_probe_table(seed=3)
    pd.testing.assert_frame_equal(table, again)
    assert not table.equals(simulate_probe_table(seed=4))
    assert set(REQUIRED_COLUMNS) <= set(table.columns)
    assert validate_table(table) == []
    p = SimParams()
    assert len(table) == 6 * p.n_facts_per_cell * p.n_seeds * p.n_variants * 2 * len(
        checkpoint_steps(p)
    )


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
        (lambda d: d.drop(columns=["binding_score"]), "missing required"),
        (lambda d: d.assign(regime="weird"), "unexpected levels"),
        (lambda d: d.assign(rank=9), "rank"),
        (lambda d: d.assign(stored=1 - d["stored"]), "disagrees"),
        (lambda d: pd.concat([d, d.iloc[:1]]), "duplicate"),
    ],
)
def test_schema_rejects_violations(table, mutate, msg):
    with pytest.raises(SchemaError, match=msg):
        validate_table(mutate(table.copy()))


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


def test_gee_recovers_signs_and_directions():
    df = simulate_probe_table(SimParams(n_facts_per_cell=30), seed=11, final_only=True)
    res = fit_gee(add_codes(df))
    fam = res.family.set_index("hypothesis")
    assert res.converged and res.n_clusters == 180
    assert fam.loc["H1", "estimate"] > 0 and fam.loc["H1", "reject_holm"]
    assert fam.loc["H2", "estimate"] > 0
    assert fam.loc["H4", "estimate"] < 0 and fam.loc["H4", "reject_holm"]
    assert (fam["ci_low"] < fam["estimate"]).all() and (fam["estimate"] < fam["ci_high"]).all()
    assert set(fam.index) == set(FAMILY)


def test_marginal_truth_is_attenuated_but_same_sign():
    p = SimParams()
    truth = marginal_truth(p, n_facts_per_cell=300)
    assert 0 < truth["H1"] < p.b_freq
    assert truth["H4"] > p.b_regime and truth["H4"] < 0


def test_null_replicates_run_and_summarise():
    reps = run_replicates(SimParams().null(), 12, seed0=7)
    summ = null_summary(reps).set_index("test")
    assert summ.loc["any of H1-H4 (family-wise)", "rejection_holm"] <= summ.loc[
        "any of H1-H4 (family-wise)", "rejection_raw"
    ]


def test_risk_differences_are_deterministic_and_signed(table):
    last = table[table["checkpoint"] == table["checkpoint"].max()]
    a = dsc.risk_difference_table(last, b=300)
    b = dsc.risk_difference_table(last, b=300)
    pd.testing.assert_frame_equal(a, b)
    rd = a.set_index("hypothesis")
    assert rd.loc["H1", "risk_difference"] > 0 and rd.loc["H4", "risk_difference"] < 0
    assert (rd["ci_low"] <= rd["risk_difference"]).all()


def test_fit_primary_ignores_earlier_checkpoints(table):
    res, ck = fit_primary(table)
    assert ck == table["checkpoint"].max()
    assert res.n_rows == (table["checkpoint"] == ck).sum()


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_analysis_end_to_end_is_deterministic(table, tmp_path):
    inp = tmp_path / "probe.csv"
    table.to_csv(inp, index=False)
    out1, out2 = tmp_path / "a", tmp_path / "b"
    assert run_main(["--input", str(inp), "--out", str(out1), "--no-mixed"]) == 0
    assert run_main(["--input", str(inp), "--out", str(out2), "--no-mixed"]) == 0
    names = [
        "tables/analysis_model.md",
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


@pytest.mark.slow
def test_null_false_positive_rate_is_controlled():
    reps = run_replicates(SimParams().null(), 200, seed0=50_000)
    summ = null_summary(reps).set_index("test")
    assert summ.loc["any of H1-H4 (family-wise)", "rejection_holm"] <= 0.10
    for h in FAMILY:
        assert summ.loc[h, "rejection_raw"] <= 0.10
