# ruff: noqa: E501
"""Base-model prompts: fixed exemplars that appear in none of E0/E1/E2."""

import json
from pathlib import Path

import pytest

from slm.sft_eval import (
    check_exemplars_disjoint,
    few_shot_prefix,
    load_base_prompts,
    prompt_prefixes,
)

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "configs" / "base_prompts.yaml"
FIX = ROOT / "tests" / "fixtures" / "sft_mock_fact_split.json"
SIBLING = ROOT.parent / "slm-eval" / "data" / "sft_mock"


def test_config_has_two_fixed_exemplars():
    cfg = load_base_prompts(CFG)
    ex = cfg["exemplars"]
    assert [e["fact_id"] for e in ex] == ["F049", "F064"] and cfg["seed"] == 0
    assert len({e["attribute_id"].split("_")[0] for e in ex}) == 2  # different families
    for e in ex:
        assert e["question"] and e["answer"].endswith(".") and "\n" not in e["answer"]


def test_prompt_formats():
    ex = load_base_prompts(CFG)["exemplars"]
    p = prompt_prefixes(load_base_prompts(CFG))
    assert p["zero_shot"] == ""
    assert p["2shot"] == few_shot_prefix(ex)
    assert p["2shot"].count("Question: ") == 2 and p["2shot"].count("\nAnswer: ") == 2
    assert p["2shot"].endswith("\n\n")  # then the evaluation prompt "Question: <q>\nAnswer:"
    assert (p["2shot"] + "Question: x\nAnswer:").count("Answer:") == 3


def test_exemplar_facts_are_sft_val_only():
    split = json.loads(FIX.read_text(encoding="utf-8"))  # fact_id -> sft_train|sft_val|heldout
    ids = {e["fact_id"] for e in load_base_prompts(CFG)["exemplars"]}
    assert {split[i] for i in ids} == {"sft_val"}
    # E0/E1 use sft_train facts and E2 the heldout facts, so sft_val facts are in none of them
    in_eval = {f for f, s in split.items() if s in ("sft_train", "heldout")}
    assert not ids & in_eval


def test_disjointness_check_raises_on_overlap():
    ex = load_base_prompts(CFG)["exemplars"]
    check_exemplars_disjoint(ex, [{"fact_id": "F001"}, {"fact_id": "F002"}])
    with pytest.raises(ValueError, match="F049"):
        check_exemplars_disjoint(ex, [{"fact_id": "F001"}, {"fact_id": "F049"}])


@pytest.mark.skipif(not (SIBLING / "qa_test.jsonl").exists(), reason="slm-eval worktree absent")
def test_disjoint_from_the_real_evaluation_file():
    rows = [json.loads(x) for x in (SIBLING / "qa_test.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["subset"] for r in rows} == {"E0", "E1", "E2"}
    check_exemplars_disjoint(load_base_prompts(CFG)["exemplars"], rows)