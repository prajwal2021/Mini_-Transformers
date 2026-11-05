"""E01: probe harness, scorer interface, mock ground truth."""

from dataclasses import replace
from pathlib import Path

import pytest

from slm.eval.interface import MockScorer, Scorer
from slm.eval.mock import oracle_scorer, random_ground_truth
from slm.eval.probes import (
    TABLE_COLUMNS,
    TEMPLATE_POOLS,
    assert_no_leakage,
    build_probes,
    continuation,
    has_ngram_overlap,
    load_facts,
    load_meanings,
    run_probes,
    score_item,
    split_templates,
    write_table,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def facts():
    return load_facts(ROOT / "data/kb/kb.json")


@pytest.fixture(scope="module")
def probes(facts):
    return build_probes(facts, load_meanings(ROOT / "configs/attribute_cues.yaml"), seed=0)


def test_mock_is_a_scorer_and_deterministic() -> None:
    a = MockScorer({("p", "c"): -1.0}, noise=0.3, seed=5)
    b = MockScorer({("p", "c"): -1.0}, noise=0.3, seed=5)
    assert isinstance(a, Scorer)
    assert a.score("p", "c") == b.score("p", "c") == a.score("p", "c")
    assert MockScorer({}, noise=0.3, seed=6).score("p", "c") != MockScorer(
        {}, noise=0.3, seed=5
    ).score("p", "c")
    assert MockScorer({}, default=-3.0).score("x", "y") == -3.0


def test_candidate_sets_are_six_same_attribute_values(facts, probes) -> None:
    attr_of = {f.value: f.attribute_id for f in facts}
    for it in probes.items:
        assert len(it.candidates) == 6 == len(set(it.candidates))
        assert it.candidates[0] == it.value
        assert {attr_of[c] for c in it.candidates} == {it.attribute_id}
        assert len(it.baseline_prompts) == 5


def test_probe_counts(facts, probes) -> None:
    # per fact: val = canon + 2 iid + 2 novel; test = canon + 3 iid + 3 novel
    n = len(facts)
    assert len(probes) == n * (5 + 7)
    assert {i.regime for i in probes.items} == {"iid", "novel"}
    assert {i.split for i in probes.items} == {"val", "test"}


def test_no_probe_prompt_contains_a_candidate_value(probes) -> None:
    assert_no_leakage(probes)  # every prompt, true and baseline entity, every candidate
    for it in probes.items:
        assert it.value.casefold() not in it.prompt.casefold()


def test_leakage_check_catches_a_leak(facts) -> None:
    bad = build_probes(facts, {a: "x" for a in {g.attribute_id for g in facts}})
    first = bad.items[0]
    bad.items[0] = replace(first, prompt=f"{first.prompt} {first.value}")
    with pytest.raises(AssertionError):
        assert_no_leakage(bad)


def test_val_and_test_templates_disjoint_and_seeded() -> None:
    a, b = split_templates(0), split_templates(0)
    assert a == b
    for regime in ("iid", "novel"):
        val, test = a["val", regime], a["test", regime]
        assert len(val) == 2 and len(test) == 3 and not set(val) & set(test)
        assert set(val) | set(test) == set(TEMPLATE_POOLS[regime])
    assert split_templates(1) != split_templates(0) or split_templates(2) != split_templates(0)


def test_build_is_deterministic(facts) -> None:
    m = load_meanings(ROOT / "configs/attribute_cues.yaml")
    assert build_probes(facts, m, seed=3).items == build_probes(facts, m, seed=3).items


def test_canonical_variant_is_the_canonical_prefix(facts, probes) -> None:
    by_id = {f.fact_id: f for f in facts}
    canon = [i for i in probes.items if i.frame == "canonical" and i.split == "test"]
    assert len(canon) == len(facts)
    for it in canon:
        assert it.prompt == by_id[it.fact_id].canonical_prefix.strip()


@pytest.mark.parametrize("truth_seed", [0, 1, 2])
def test_harness_recovers_ground_truth_exactly(probes, truth_seed) -> None:
    prior, bind = random_ground_truth(probes, truth_seed)
    scorer = oracle_scorer(probes, prior, bind)
    df = run_probes(scorer, probes, checkpoint="ck", seed=7)
    assert list(df.columns) == TABLE_COLUMNS
    assert len(df) == len(probes)
    by_item = {(i.fact_id, i.variant): i for i in probes.items}
    n_stored = n_tie_top = n_zero_bind = 0
    for row in df.itertuples():
        it = by_item[row.fact_id, row.prompt_variant]
        b = bind[row.fact_id, it.prompt]
        mine = prior[row.fact_id] + b
        rivals = [
            prior[g.fact_id]
            for g in probes.items
            if g.attribute_id == it.attribute_id and g.variant == it.variant
            and g.fact_id != it.fact_id
        ]
        exp_rank = 1 + sum(1 for r in rivals if r >= mine)
        assert row.rank == exp_rank
        assert row.binding_score == b
        assert row.stored == (exp_rank == 1 and b > 0)
        n_stored += row.stored
        n_tie_top += any(r == mine for r in rivals)
        n_zero_bind += b == 0
    assert n_stored > 0 and n_tie_top > 0 and n_zero_bind > 0  # the cases are actually exercised


def test_noise_below_gap_does_not_change_outcomes(probes) -> None:
    prior, bind = random_ground_truth(probes, 4)
    clean = run_probes(oracle_scorer(probes, prior, bind), probes, checkpoint="c", seed=0)
    noisy = run_probes(oracle_scorer(probes, prior, bind, noise=0.1, seed=9), probes,
                       checkpoint="c", seed=0)
    ok = (clean["n_ties"] == 0) & (clean["binding_score"] != 0)  # exact ties/zeros are fragile
    assert ok.sum() > 100
    assert (clean["rank"] == noisy["rank"])[ok].all()
    assert (clean["stored"] == noisy["stored"])[ok].all()


def test_ties_count_against_the_fact(probes) -> None:
    it = next(i for i in probes.items if i.split == "test")
    table = {(it.prompt, continuation(c)): -5.0 for c in it.candidates}  # six-way tie
    for p in it.baseline_prompts:
        table[(p, continuation(it.value))] = -9.0  # binding is +4
    r = score_item(MockScorer(table), it)
    assert r["rank"] == 6 and r["n_ties"] == 5 and r["binding_score"] == 4.0
    assert r["stored"] is False
    table[(it.prompt, continuation(it.value))] = -4.999  # strictly best
    r = score_item(MockScorer(table), it)
    assert r["rank"] == 1 and r["stored"] is True


def test_frequency_prior_is_not_stored(probes) -> None:
    # Value is top-ranked but scored identically for every entity: binding == 0 -> not stored.
    it = next(i for i in probes.items if i.split == "test")
    table = {(it.prompt, continuation(c)): -9.0 for c in it.candidates}
    table[(it.prompt, continuation(it.value))] = -1.0
    for p in it.baseline_prompts:
        table[(p, continuation(it.value))] = -1.0
    r = score_item(MockScorer(table), it)
    assert r["rank"] == 1 and r["binding_score"] == 0.0 and r["stored"] is False


def test_never_mixes_attributes(probes, facts) -> None:
    attr_values = {}
    for f in facts:
        attr_values.setdefault(f.attribute_id, set()).add(f.value)
    for it in probes.items:
        assert set(it.candidates) == attr_values[it.attribute_id]


def test_table_is_reproducible_and_written(tmp_path, probes) -> None:
    prior, bind = random_ground_truth(probes, 0)
    a = run_probes(oracle_scorer(probes, prior, bind, noise=0.1, seed=1), probes,
                   checkpoint="c", seed=1)
    b = run_probes(oracle_scorer(probes, prior, bind, noise=0.1, seed=1), probes,
                   checkpoint="c", seed=1)
    assert a.equals(b)
    path = write_table(a, tmp_path / "t.csv")
    assert path.read_text(encoding="utf-8").splitlines()[0].split(",")[:3] == [
        "fact_id", "seed", "checkpoint"
    ]


def test_ngram_overlap_helper() -> None:
    corpus = ["one two three four five six seven eight nine ten"]
    assert has_ngram_overlap(["two three four five six seven eight nine"], corpus)
    assert not has_ngram_overlap(["two three four five six seven eight X"], corpus)
