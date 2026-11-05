"""E01: SFT fact split and QA builder."""

import json
from collections import Counter
from pathlib import Path

import pytest

from slm.sft.build import (
    build_datasets,
    build_fact_split,
    load_sft_facts,
    split_table,
    write_datasets,
)
from slm.sft.templates import BASES, TEMPLATE_SETS, WRAPPERS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def facts():
    return load_sft_facts(ROOT / "data/kb/kb.json")


def test_seeded_split_sizes_and_disjoint(facts) -> None:
    split = build_fact_split(facts, seed=0)
    assert set(split) == {f.fact_id for f in facts}  # every fact in exactly one split
    assert Counter(split.values()) == {"sft_train": 48, "sft_val": 12, "heldout": 60}


def test_seeded_split_is_stratified_by_cell(facts) -> None:
    split = build_fact_split(facts, seed=3)
    table = split_table(facts, split)
    for fb in ("low", "mid", "high"):
        for db in ("templated", "paraphrased"):
            assert (table[fb, db, "sft_train"], table[fb, db, "sft_val"],
                    table[fb, db, "heldout"]) == (8, 2, 10)


def test_split_depends_on_seed_only(facts) -> None:
    assert build_fact_split(facts, 1) == build_fact_split(facts, 1)
    assert build_fact_split(facts, 1) != build_fact_split(facts, 2)


def test_kb_recorded_split_has_the_same_shape(facts) -> None:
    split = {f.fact_id: f.kb_split for f in facts}
    table = split_table(facts, split)
    assert all(
        (table[fb, db, "sft_train"], table[fb, db, "sft_val"], table[fb, db, "heldout"])
        == (8, 2, 10)
        for fb in ("low", "mid", "high") for db in ("templated", "paraphrased")
    )


def test_template_sets_are_7_2_3_and_disjoint() -> None:
    sets = {k: set(v) for k, v in TEMPLATE_SETS.items()}
    assert [len(TEMPLATE_SETS[k]) for k in ("train", "val", "test")] == [7, 2, 3]
    assert not (sets["train"] & sets["val"] or sets["train"] & sets["test"]
                or sets["val"] & sets["test"])
    assert len(sets["train"] | sets["val"] | sets["test"]) == 12 == 4 * len(WRAPPERS)
    assert all(len(b) == 4 for b in BASES.values()) and len(BASES) == 20
    # test uses a base form (index 3) never seen in train
    assert 3 not in {b for b, _ in TEMPLATE_SETS["train"]}


@pytest.fixture(scope="module")
def data(facts):
    return build_datasets(facts, build_fact_split(facts, 0))


def test_dataset_sizes_and_format(data) -> None:
    assert {k: len(v) for k, v in data.items()} == {
        "sft_train": 48 * 7, "sft_val": 12 * 2, "E0": 48 * 7, "E1": 48 * 3, "E2": 60 * 3,
    }
    for rows in data.values():
        for r in rows:
            assert r["prompt"] == f"Question: {r['question']}\nAnswer:"
            assert r["completion"] == f" {r['answer']}<|eos|>"
            assert r["text"] == r["prompt"] + r["completion"]
            assert r["value"] in r["answer"]


def test_no_fact_leaks_across_splits(data) -> None:
    train = {r["fact_id"] for r in data["sft_train"]}
    val = {r["fact_id"] for r in data["sft_val"]}
    held = {r["fact_id"] for r in data["E2"]}
    assert not (train & val or train & held or val & held)
    assert {r["fact_id"] for r in data["E1"]} == train == {r["fact_id"] for r in data["E0"]}


def test_eval_phrasings_unseen_in_training(data) -> None:
    seen = {r["question"] for r in data["sft_train"]} | {r["question"] for r in data["sft_val"]}
    for r in data["E1"] + data["E2"]:
        assert r["question"] not in seen
    assert {r["question"] for r in data["E0"]} <= seen


def test_questions_never_contain_the_value(data) -> None:
    for rows in data.values():
        for r in rows:
            assert r["value"].casefold() not in r["question"].casefold()


def test_heldout_stratification_balance(data) -> None:
    per_cell = Counter(
        (r["freq_bin"], r["div_bin"]) for r in data["E2"] if r["template_id"].endswith("b3w2")
    )
    assert set(per_cell.values()) == {10} and len(per_cell) == 6


def test_write_is_deterministic_and_hashed(tmp_path, facts) -> None:
    split = build_fact_split(facts, 0)
    m1 = write_datasets(facts, split, tmp_path / "a_mock", seed=0, source="seeded")
    m2 = write_datasets(facts, split, tmp_path / "b_mock", seed=0, source="seeded")
    assert m1["sha256"] == m2["sha256"]
    rows = [json.loads(line) for line in (tmp_path / "a_mock/qa_test.jsonl").open(encoding="utf-8")]
    assert Counter(r["subset"] for r in rows) == {"E0": 336, "E1": 144, "E2": 180}
    assert len({r["id"] for r in rows}) == len(rows)
