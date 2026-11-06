"""E01/E02: probe harness, scorer interface, mock ground truth, chance baseline."""

from dataclasses import replace
from pathlib import Path

import pytest

from slm.eval.interface import DetailedScorer, MockDetailedScorer, MockScorer, Scorer
from slm.eval.mock import oracle_scorer, random_ground_truth
from slm.eval.probes import (
    INIT_CHECKPOINT,
    TABLE_COLUMNS,
    assert_no_leakage,
    build_probes,
    chance_report,
    checkpoint_summary,
    continuation,
    fact_level,
    group_key,
    groups,
    has_ngram_overlap,
    load_facts,
    run_many,
    run_probes,
    score_group,
    split_novel,
    write_table,
)
from slm.eval.wording import CANONICAL, NOVEL, prefix

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def facts():
    return load_facts(ROOT / "data/kb/kb.json")


@pytest.fixture(scope="module")
def probes(facts):
    return build_probes(facts, seed=0)


def group_scorer(items, M, **kw):
    """MockScorer whose 6x6 score matrix for one group is M[i][j] = score(prompt_i, value_j)."""
    table = {
        (a.prompt, continuation(b.value)): M[i][j]
        for i, a in enumerate(items) for j, b in enumerate(items)
    }
    return MockScorer(table, **kw)


@pytest.fixture(scope="module")
def one_group(probes):
    return next(iter(groups(probes).values()))


def test_mock_is_a_scorer_and_deterministic() -> None:
    a = MockScorer({("p", "c"): -1.0}, noise=0.3, seed=5)
    b = MockScorer({("p", "c"): -1.0}, noise=0.3, seed=5)
    assert isinstance(a, Scorer) and not isinstance(a, DetailedScorer)
    assert isinstance(MockDetailedScorer(), DetailedScorer)
    assert a.score("p", "c") == b.score("p", "c") == a.score("p", "c")
    assert MockScorer({}, noise=0.3, seed=6).score("p", "c") != MockScorer(
        {}, noise=0.3, seed=5
    ).score("p", "c")
    assert MockScorer({}, default=-3.0).score("x", "y") == -3.0


# ---- probe construction ---------------------------------------------------------------------


def test_candidate_sets_are_six_same_attribute_values(facts, probes) -> None:
    attr_of = {f.value: f.attribute_id for f in facts}
    for it in probes.items:
        assert len(it.candidates) == 6 == len(set(it.candidates))
        assert it.candidates[0] == it.value
        assert {attr_of[c] for c in it.candidates} == {it.attribute_id}
    attr_values = {}
    for f in facts:
        attr_values.setdefault(f.attribute_id, set()).add(f.value)
    assert all(set(it.candidates) == attr_values[it.attribute_id] for it in probes.items)


def test_probe_counts_and_frames(facts, probes) -> None:
    # per fact: val = canonical + 1 novel, test = canonical + 2 novel
    assert len(probes) == len(facts) * 5
    assert {i.probe_frame for i in probes.items} == {"canonical", "novel"}
    per = {}
    for it in probes.items:
        per.setdefault((it.split, it.probe_frame), set()).add(it.variant)
    assert {k: len(v) for k, v in per.items()} == {
        ("val", "canonical"): 1, ("val", "novel"): 1, ("test", "canonical"): 1,
        ("test", "novel"): 2,
    }
    assert all(len(g) == 6 for g in groups(probes).values())


def test_no_regime_column_on_the_probe_side() -> None:
    assert "regime" not in TABLE_COLUMNS and "probe_frame" in TABLE_COLUMNS


def test_no_probe_prompt_contains_a_candidate_value(probes) -> None:
    assert_no_leakage(probes)
    for it in probes.items:
        assert it.value.casefold() not in it.prompt.casefold()


def test_leakage_check_catches_a_leak(facts) -> None:
    bad = build_probes(facts)
    first = bad.items[0]
    bad.items[0] = replace(first, prompt=f"{first.prompt} {first.value}")
    with pytest.raises(AssertionError):
        assert_no_leakage(bad)


def test_novel_templates_val_test_disjoint_and_seeded() -> None:
    a = split_novel(0)
    assert a == split_novel(0)
    assert len(a["val"]) == 1 and len(a["test"]) == 2 and not set(a["val"]) & set(a["test"])
    assert any(split_novel(s) != a for s in range(1, 6))


def test_build_is_deterministic(facts) -> None:
    assert build_probes(facts, seed=3).items == build_probes(facts, seed=3).items


def test_handwritten_canonical_prefixes_match_the_kb(facts) -> None:
    for f in facts:
        assert prefix(f.attribute_id, "canon", f.entity) == f.canonical_prefix.strip(), f.fact_id


def test_wording_is_complete_and_novel_is_not_canonical() -> None:
    assert set(CANONICAL) == set(NOVEL) and len(CANONICAL) == 20
    def norm(t: str) -> str:  # "{a_e}" / "{A_e}" are the article + entity placeholders (R00)
        return t.replace("{a_e}", "{e}").replace("{A_e}", "{e}")

    for attr, canon in CANONICAL.items():
        canon = norm(canon)
        novel = [norm(n) for n in NOVEL[attr]]
        assert len(novel) == 3 and len(set(novel)) == 3
        stem = canon.split("{e}")[0] + "{e}"
        for n in novel:
            assert n.count("{e}") == 1 and n != canon and not n.startswith(stem)
            assert "Question:" not in n and "Answer:" not in n


# ---- exact recovery -------------------------------------------------------------------------


@pytest.mark.parametrize("truth_seed", [0, 1, 2])
def test_harness_recovers_ground_truth_exactly(probes, truth_seed) -> None:
    prior, bind = random_ground_truth(probes, truth_seed)
    df = run_probes(oracle_scorer(probes, prior, bind), probes, checkpoint="ck", seed=7)
    assert list(df.columns) == TABLE_COLUMNS and len(df) == len(probes)
    by_item = {(i.fact_id, i.variant): i for i in probes.items}
    members = groups(probes)
    n_stored = n_tie_top = n_zero_bind = 0
    for row in df.itertuples():
        it = by_item[row.fact_id, row.prompt_variant]
        b = bind[row.fact_id, it.prompt]
        mine = prior[row.fact_id] + b
        rivals = [prior[g.fact_id] for g in members[group_key(it)] if g.fact_id != it.fact_id]
        exp_rank = 1 + sum(1 for r in rivals if r >= mine)
        assert row.rank == exp_rank
        assert row.binding_score == b
        assert row.stored == (exp_rank == 1 and b > 0)
        n_stored += row.stored
        n_tie_top += any(r == mine for r in rivals)
        n_zero_bind += b == 0
    assert n_stored > 0 and n_tie_top > 0 and n_zero_bind > 0


def test_noise_below_gap_does_not_change_outcomes(probes) -> None:
    prior, bind = random_ground_truth(probes, 4)
    clean = run_probes(oracle_scorer(probes, prior, bind), probes, checkpoint="c", seed=0)
    noisy = run_probes(oracle_scorer(probes, prior, bind, noise=0.1, seed=9), probes,
                       checkpoint="c", seed=0)
    ok = (clean["n_ties"] == 0) & (clean["binding_score"] != 0)
    assert ok.sum() > 100
    assert (clean["rank"] == noisy["rank"])[ok].all()
    assert (clean["stored"] == noisy["stored"])[ok].all()


def test_ties_count_against_the_fact(one_group) -> None:
    M = [[-5.0] * 6 for _ in range(6)]  # six-way tie in every row, binding 0
    r = score_group(group_scorer(one_group, M), one_group)[0]
    assert r["rank"] == 6 and r["n_ties"] == 5 and r["stored"] is False
    M[0][0] = -4.0  # strictly best for entity 0, others unchanged -> binding +1
    r = score_group(group_scorer(one_group, M), one_group)[0]
    assert r["rank"] == 1 and r["binding_score"] == 1.0 and r["stored"] is True
    M[0][0] = -5.0  # tie for first again, but with positive binding via the baseline
    for k in range(1, 6):
        M[k][0] = -9.0
    r = score_group(group_scorer(one_group, M), one_group)[0]
    assert r["binding_score"] == 4.0 and r["rank"] == 6 and r["stored"] is False


def test_frequency_prior_is_not_stored(one_group) -> None:
    M = [[-9.0] * 6 for _ in range(6)]
    for i in range(6):
        M[i][0] = -1.0  # value 0 is the top candidate for every entity
    r = score_group(group_scorer(one_group, M), one_group)
    assert r[0]["rank"] == 1 and r[0]["binding_score"] == 0.0 and r[0]["stored"] is False
    assert not any(x["stored"] for x in r) and all(x["null_stored_rate"] == 0 for x in r)


def test_table_is_reproducible_and_written(tmp_path, probes) -> None:
    prior, bind = random_ground_truth(probes, 0)
    make = lambda: run_probes(  # noqa: E731
        oracle_scorer(probes, prior, bind, noise=0.1, seed=1), probes, checkpoint="c", seed=1
    )
    a, b = make(), make()
    assert a.equals(b)
    path = write_table(a, tmp_path / "t.csv")
    assert path.read_text(encoding="utf-8").splitlines()[0].split(",")[:4] == [
        "fact_id", "seed", "checkpoint", "probe_frame"
    ]


def test_ngram_overlap_helper() -> None:
    corpus = ["one two three four five six seven eight nine ten"]
    assert has_ngram_overlap(["two three four five six seven eight nine"], corpus)
    assert not has_ngram_overlap(["two three four five six seven eight X"], corpus)


# ---- permutation null -----------------------------------------------------------------------


def test_null_uses_every_other_entity_as_pseudo_truth(one_group) -> None:
    # Entity 0 prefers values 0 (own) and 3 (another entity's), both bound only to their owner.
    M = [[-8.0] * 6 for _ in range(6)]
    M[0][0] = -1.0
    M[3][3] = -1.0
    r = score_group(group_scorer(one_group, M), one_group)
    assert r[0]["stored"] and r[3]["stored"]
    # pseudo-truth o=3 for entity 0: row 0 has -8 for value 3 vs -1 for value 0 -> rank 2.
    assert r[0]["null_stored_rate"] == 0.0
    # Now make entity 0 score value 3 best of its row with a positive binding:
    M2 = [[-8.0] * 6 for _ in range(6)]
    M2[0][3] = -1.0
    r2 = score_group(group_scorer(one_group, M2), one_group)
    assert r2[0]["null_stored_rate"] == pytest.approx(1 / 5)  # exactly one of 5 pseudo-truths
    assert not r2[0]["stored"]


def test_no_knowledge_scorer_has_stored_rate_near_null_rate(probes) -> None:
    for seed in range(3):
        prior, _ = random_ground_truth(probes, 10 + seed)
        # value prior only (no binding to entities) + noise comparable to the prior spread
        df = run_probes(oracle_scorer(probes, prior, None, noise=3.0, seed=seed), probes,
                        checkpoint="init", seed=seed)
        stored, null = df["stored"].mean(), df["null_stored_rate"].mean()
        assert 0.02 < stored < 0.4, stored
        assert abs(stored - null) < 0.04, (stored, null)


def test_pure_value_prior_never_stores_and_null_is_zero(probes) -> None:
    prior, _ = random_ground_truth(probes, 1)
    df = run_probes(oracle_scorer(probes, prior, None), probes, checkpoint="init", seed=0)
    assert not df["stored"].any() and (df["null_stored_rate"] == 0).all()


def test_planted_binding_beats_null(probes) -> None:
    prior = {i.fact_id: -3.0 for i in probes.items}
    bind = {(i.fact_id, i.prompt): 2.0 for i in probes.items}
    # plant binding for the first half of the facts only
    ids = sorted(prior)
    for k, v in list(bind.items()):
        if k[0] in ids[60:]:
            bind[k] = 0.0
    df = run_probes(oracle_scorer(probes, prior, bind, noise=0.1, seed=2), probes,
                    checkpoint="ck", seed=0)
    rep = chance_report(df)
    assert set(rep.columns) >= {"probe_frame", "freq_bin", "div_bin", "stored_rate",
                                "null_rate", "diff"}
    assert len(rep) == 2 * 3 * 2
    planted = df["fact_id"].isin(ids[:60])
    assert df[planted]["stored"].mean() > 0.95
    assert df[~planted]["stored"].mean() < 0.2  # chance: ~ P(rank 1) * P(binding > 0 | rank 1)
    assert df[planted]["null_stored_rate"].mean() == 0.0
    assert df["null_stored_rate"].mean() < 0.1
    assert df["stored"].mean() > 5 * df["null_stored_rate"].mean()
    assert (rep["diff"] > 0.2).all()


def test_init_checkpoint_summary_and_fact_level(probes) -> None:
    prior, bind = random_ground_truth(probes, 5)
    runs = [
        (INIT_CHECKPOINT, 0, oracle_scorer(probes, prior, None)),
        ("ckpt-100", 0, oracle_scorer(probes, prior, {k: abs(v) + 1 for k, v in bind.items()})),
    ]
    df = run_many(runs, probes)
    summ = checkpoint_summary(df, split="test").set_index("checkpoint")
    assert summ.loc["init", "stored_rate"] == 0.0
    assert summ.loc["ckpt-100", "diff"] > summ.loc["init", "diff"]
    fl = fact_level(df)
    assert len(fl) == 120 * 2 and fl["null_stored_rate"].between(0, 1).all()
    assert set(fl["n_probes"]) == {5}


# ---- length normalisation -------------------------------------------------------------------


def test_token_norm_uses_score_detailed_and_can_disagree(one_group) -> None:
    # Entity 0's own value has a long continuation (many tokens) with a poor total score, a rival
    # is short: the summed score ranks the rival first; per token the own value wins.
    n_tokens = {continuation(it.value): 1 for it in one_group}
    own = continuation(one_group[0].value)
    n_tokens[own] = 10
    M = [[-20.0] * 6 for _ in range(6)]
    M[0][0] = -10.0  # -1.0 per token
    M[0][1] = -5.0  # -5.0 per token, better total
    scorer = group_scorer(one_group, M)
    det = MockDetailedScorer(scorer.table, n_tokens_fn=lambda c: n_tokens[c])
    r = score_group(det, one_group)[0]
    assert r["norm_unit"] == "token"
    assert r["rank"] == 2 and r["stored"] is False  # DESIGN: stored stays on summed scores
    assert r["rank_tokennorm"] == 1 and r["stored_tokennorm"] is True


def test_fallback_is_per_character(one_group) -> None:
    M = [[-20.0] * 6 for _ in range(6)]
    r = score_group(group_scorer(one_group, M), one_group)[0]
    assert r["norm_unit"] == "char"
    chars = [len(continuation(it.value)) for it in one_group]
    M2 = [row[:] for row in M]
    M2[0][0] = -2.0 * chars[0]  # exactly -2 per character
    for j in range(1, 6):
        M2[0][j] = -3.0 * chars[j]
    r2 = score_group(group_scorer(one_group, M2), one_group)[0]
    assert r2["rank_tokennorm"] == 1


def test_stored_is_unchanged_by_the_detailed_interface(probes) -> None:
    prior, bind = random_ground_truth(probes, 2)
    a = run_probes(oracle_scorer(probes, prior, bind), probes, checkpoint="c", seed=0)
    b = run_probes(oracle_scorer(probes, prior, bind, detailed=True), probes, checkpoint="c",
                   seed=0)
    assert a[["rank", "binding_score", "stored"]].equals(b[["rank", "binding_score", "stored"]])
    assert set(b["norm_unit"]) == {"token"} and set(a["norm_unit"]) == {"char"}
