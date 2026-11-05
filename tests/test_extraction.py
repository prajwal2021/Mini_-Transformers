"""Extraction tests (H3, H4) and the QA-table contract (simulated data only)."""

import numpy as np
import pandas as pd
import pytest

from slm.analysis.extraction import (
    _perm_p,
    fact_level,
    fisher_stored,
    mcnemar_exact,
    run_extraction,
)
from slm.analysis.family import assemble_family
from slm.analysis.schema import SchemaError, normalize_qa_table, validate_qa_table
from slm.analysis.simulate import SimParams, simulate_probe_table, simulate_qa_table


@pytest.fixture(scope="module")
def probe() -> pd.DataFrame:
    return simulate_probe_table(seed=21, final_only=True)


@pytest.fixture(scope="module")
def qa(probe) -> pd.DataFrame:
    return simulate_qa_table(SimParams(), probe, seed=22)


def test_qa_table_follows_design_split(qa):
    assert validate_qa_table(qa) == []
    split = qa.drop_duplicates("fact_id").groupby(["freq_bin", "div_bin"])["sft_split"]
    # 20 facts per cell -> 8 train, 2 val (never evaluated), 10 held-out
    assert (split.apply(lambda s: (s == "train").sum()) == 8).all()
    assert (split.apply(lambda s: (s == "heldout").sum()) == 10).all()
    e2 = qa[qa["eval_set"] == "E2"]
    assert set(e2["sft_split"]) == {"heldout"}
    assert set(qa.loc[qa["eval_set"].isin(["E0", "E1"]), "sft_split"]) == {"train"}
    assert e2["fact_id"].nunique() == 60
    assert set(qa["model"]) == {"base_0shot", "base_2shot", "sft"}


def test_qa_stored_pretrain_matches_probe_table(qa, probe):
    t = probe[probe["split"] == "test"].groupby(["fact_id", "seed"])["stored"].mean().ge(0.5)
    chk = qa.drop_duplicates(["fact_id", "seed"]).set_index(["fact_id", "seed"])["stored_pretrain"]
    assert (t.loc[chk.index].astype(int) == chk).all()


def test_simulator_is_seeded(probe):
    a = simulate_qa_table(SimParams(), probe, seed=5)
    pd.testing.assert_frame_equal(a, simulate_qa_table(SimParams(), probe, seed=5))
    assert not a.equals(simulate_qa_table(SimParams(), probe, seed=6))


@pytest.mark.parametrize(
    "mutate, msg",
    [
        (lambda d: d.drop(columns=["stored_pretrain"]), "missing required"),
        (lambda d: d.assign(model="gpt"), "unexpected levels"),
        (lambda d: d.assign(exact_match=2), "exact_match"),
        (lambda d: pd.concat([d, d.iloc[:1]]), "duplicate"),
        (
            lambda d: d.assign(
                sft_split=np.where(d["eval_set"] == "E2", "train", d["sft_split"])
            ),
            "E2 must contain only heldout",
        ),
    ],
)
def test_qa_schema_rejects_violations(qa, mutate, msg):
    with pytest.raises(SchemaError, match=msg):
        validate_qa_table(mutate(qa.copy()))


def test_qa_schema_rejects_fact_in_both_sets(qa):
    bad = qa.copy()
    train_fact = bad.loc[bad["eval_set"] == "E1", "fact_id"].iloc[0]
    bad.loc[bad["eval_set"] == "E2", "fact_id"] = train_fact
    with pytest.raises(SchemaError):
        validate_qa_table(bad)


def test_eval_stream_aliases(qa):
    renamed = qa.rename(columns={"eval_set": "subset", "exact_match": "correct"})
    norm = normalize_qa_table(renamed)
    assert {"eval_set", "exact_match"} <= set(norm.columns)
    assert validate_qa_table(norm) == []


def test_mcnemar_exact_known_values():
    base = np.array([0] * 10)
    sft = np.array([1] * 10)
    p, b, c = mcnemar_exact(base, sft)
    assert (b, c) == (0, 10) and p == pytest.approx(2 * 0.5**10)
    assert mcnemar_exact(np.array([1, 0]), np.array([1, 0]))[0] == 1.0


def test_fisher_known_values_and_degenerate():
    stored = np.array([1] * 5 + [0] * 5)
    correct = np.array([1] * 5 + [0] * 5)
    p, odds, degenerate = fisher_stored(stored, correct)
    assert p == pytest.approx(2 / 252) and degenerate == 0 and odds == np.inf
    p, _, degenerate = fisher_stored(np.ones(6, dtype=int), np.array([1, 0, 1, 0, 1, 0]))
    assert p == 1.0 and degenerate == 1


def test_permutation_p_is_valid_under_the_null_and_small_under_an_effect():
    rng = np.random.default_rng(0)
    n = 60
    para = np.tile([0, 1], n // 2)
    strata = np.repeat([0, 1, 2], n // 3)
    pvals = []
    for _ in range(300):
        d = rng.choice([-1.0, 0.0, 1.0], n, p=[0.1, 0.6, 0.3])  # same distribution in both arms
        pvals.append(_perm_p(d, para, strata, np.random.default_rng(1), 500))
    assert np.mean(np.array(pvals) < 0.05) < 0.09
    d = np.where(para == 1, 1.0, 0.0)
    assert _perm_p(d, para, strata, np.random.default_rng(1), 500) < 0.01


def test_fact_level_uses_majority_over_seeds_and_items(qa):
    f = fact_level(qa)
    assert len(f) == 60 and set(f.columns) >= {"stored", "correct_sft", "correct_base"}
    one = f.iloc[0]
    rows = qa[(qa["fact_id"] == one["fact_id"]) & (qa["eval_set"] == "E2")]
    sft_rate = rows[rows["model"] == "sft"]["exact_match"].mean()
    assert one["correct_sft"] == int(sft_rate > 0.5)


def test_run_extraction_detects_planted_effects_and_is_deterministic():
    p = SimParams(n_facts_per_cell=40)
    probe = simulate_probe_table(p, seed=31, final_only=True)
    qa = simulate_qa_table(p, probe, seed=32)
    a = run_extraction(qa, n_perm=1000, n_boot=300)
    b = run_extraction(qa, n_perm=1000, n_boot=300)
    pd.testing.assert_frame_equal(a.components, b.components)
    comp = a.components.set_index("component")
    assert comp.loc["H3a", "estimate"] > 0.2 and comp.loc["H3a", "p_raw"] < 0.001
    assert comp.loc["H3b", "estimate"] > 0.2 and comp.loc["H3b", "p_raw"] < 0.01
    assert comp.loc["H3a", "ci_low"] < comp.loc["H3a", "estimate"] < comp.loc["H3a", "ci_high"]
    fam = a.family.set_index("hypothesis")
    assert fam.loc["H3", "p_raw"] == pytest.approx(
        max(comp.loc["H3a", "p_raw"], comp.loc["H3b", "p_raw"])
    )
    assert set(a.per_condition["div_bin"]) == {"templated", "paraphrased"}
    assert a.tables_2x2["n_correct"].sum() + a.tables_2x2["n_wrong"].sum() == a.n_facts


def test_h3_is_not_supported_when_sft_equals_base():
    p = SimParams(n_facts_per_cell=40).null()
    probe = simulate_probe_table(p, seed=41, final_only=True)
    qa = simulate_qa_table(p, probe, seed=42)
    comp = run_extraction(qa, n_perm=500, ci=False).components.set_index("component")
    assert comp.loc["H3a", "p_raw"] > 0.01


def test_family_holm_and_provisional_flag():
    gee = pd.DataFrame(
        {
            "hypothesis": ["H1", "H2"],
            "label": ["a", "b"],
            "predicted_sign": [1, 1],
            "estimate": [0.5, -0.4],
            "ci_low": [0.2, -0.9],
            "ci_high": [0.8, 0.1],
            "p_raw": [0.001, 0.2],
            "direction_ok": [True, False],
        }
    )
    fam = assemble_family(gee)
    assert fam["provisional"].all()
    h1 = fam.set_index("hypothesis").loc["H1"]
    assert h1["p_holm"] == pytest.approx(0.004) and h1["status"] == "supported"
    ext = pd.DataFrame(
        {
            "hypothesis": ["H3", "H4"],
            "label": ["c", "d"],
            "scale": ["risk diff"] * 2,
            "predicted_sign": [1, 1],
            "estimate": [0.4, 0.1],
            "ci_low": [0.2, -0.05],
            "ci_high": [0.5, 0.3],
            "p_raw": [0.01, 0.04],
            "direction_ok": [True, True],
        }
    )
    full = assemble_family(gee, ext).set_index("hypothesis")
    assert not full["provisional"].any()
    # Holm over {0.001, 0.01, 0.04, 0.2}: 0.004, 0.03, 0.08, 0.2
    assert full.loc["H3", "p_holm"] == pytest.approx(0.03)
    assert full.loc["H4", "p_holm"] == pytest.approx(0.08) and not full.loc["H4", "reject_holm"]
    assert full.loc["H4", "status"].startswith("not supported")
