"""P01 sizing calculator tests."""

import json

from scripts.size_corpus import calculate, load_config
from scripts.validate_kb import DEFAULT_PATH


def test_sizing_asserts_2600_and_columns() -> None:
    with DEFAULT_PATH.open(encoding="utf-8") as handle:
        kb = json.load(handle)
    rows = calculate(load_config(), kb["measured_facts"])
    assert len(rows) == 12
    assert all(row["train_docs"] > 0 for row in rows)
    assert {
        "k",
        "background_fraction",
        "mention_bearing_train_docs",
        "train_docs",
        "total_docs",
        "train_tokens",
        "val_tokens",
        "test_tokens",
        "api_calls",
        "estimated_cost",
        "mention_density",
        "flags",
    } <= rows[0].keys()


def test_sizing_reconciliation_and_background_flag() -> None:
    with DEFAULT_PATH.open(encoding="utf-8") as handle:
        kb = json.load(handle)
    rows = calculate(load_config(), kb["measured_facts"])
    assert all(row["mention_bearing_train_docs"] * row["k"] >= 2600 for row in rows)
    assert any(
        row["background_fraction"] == 0.66
        and "background fraction > 0.6" in row["flags"]
        for row in rows
    )
