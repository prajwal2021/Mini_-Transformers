"""P01 experiment-cell assignment tests."""

import json

from scripts.assign_cells import _load_config, assign
from scripts.validate_kb import DEFAULT_PATH


def loaded() -> tuple[dict, dict]:
    with DEFAULT_PATH.open(encoding="utf-8") as handle:
        kb = json.load(handle)
    return kb, _load_config()


def test_latin_square_and_cell_sizes() -> None:
    kb, config = loaded()
    assigned, seed, _, p_value = assign(kb, config)
    assert 0 <= seed < 200
    assert p_value > 0.2
    facts = assigned["measured_facts"]
    cells = config["cells"]
    assert all(sum(fact["cell"] == cell for fact in facts) == 20 for cell in cells)
    for attribute in {fact["attribute_id"] for fact in facts}:
        assert {fact["cell"] for fact in facts if fact["attribute_id"] == attribute} == set(cells)
    for family in {fact["family"] for fact in facts}:
        entities = {fact["entity"] for fact in facts if fact["family"] == family}
        for entity in entities:
            entity_cells = [fact["cell"] for fact in facts if fact["family"] == family and fact["entity"] == entity]
            assert len(entity_cells) == len(set(entity_cells))
    for cell in cells:
        counts = {
            split: sum(fact["sft_split"] == split for fact in facts if fact["cell"] == cell)
            for split in ["sft_train", "sft_val", "heldout"]
        }
        assert counts == {"sft_train": 8, "sft_val": 2, "heldout": 10}


def test_assignment_deterministic() -> None:
    kb, config = loaded()
    first = assign(kb, config)
    second = assign(kb, config)
    fields = [
        (fact["fact_id"], fact["cell"], fact["sft_split"]) for fact in first[0]["measured_facts"]
    ]
    assert fields == [
        (fact["fact_id"], fact["cell"], fact["sft_split"]) for fact in second[0]["measured_facts"]
    ]


def test_entity_ratio_objective_is_computed_and_deterministic() -> None:
    kb, config = loaded()
    first = assign(kb, config)[0]["assignment"]
    second = assign(kb, config)[0]["assignment"]
    assert first["entity_ratio"] >= 1.0
    assert first["objective"] >= first["imbalance"]
    assert first["family_permutations"] == second["family_permutations"]
