# ruff: noqa: E501
"""R01 3: the 2-shot exemplars come from the REAL KB's sft_val facts and touch no evaluated fact."""

import hashlib
import json
from pathlib import Path

import pytest

from slm.sft_eval import check_exemplars_disjoint, few_shot_prefix, load_base_prompts

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


CFG = load_base_prompts(ROOT / "configs" / "base_prompts.yaml")
EX = CFG["exemplars"]
KB = {f["fact_id"]: f for f in json.loads((ROOT / "data/kb/kb.json").read_text(encoding="utf-8"))["measured_facts"]}
VAL, TRAIN, QA = rows(ROOT / "data/sft/sft_val.jsonl"), rows(ROOT / "data/sft/sft_train.jsonl"), rows(ROOT / "data/eval/qa_test.jsonl")


def test_exemplars_are_kb_sft_val_facts_and_come_from_the_real_sft_val_file():
    assert {e["fact_id"] for e in EX} == {"F049", "F064"}
    for e in EX:
        assert KB[e["fact_id"]]["sft_split"] == "sft_val"
        match = [r for r in VAL if r["fact_id"] == e["fact_id"] and r["question"] == e["question"]]
        assert match and match[0]["answer"] == e["answer"] == KB[e["fact_id"]]["canonical_sentence"]
    assert CFG["source_sft_val_sha256"] == hashlib.sha256((ROOT / "data/sft/sft_val.jsonl").read_bytes()).hexdigest()


def test_exemplars_are_disjoint_from_every_evaluated_and_trained_fact():
    check_exemplars_disjoint(EX, QA)  # E0, E1, E2 of the real file
    ids = {e["fact_id"] for e in EX}
    assert not ids & {r["fact_id"] for r in TRAIN}
    assert {r["subset"] for r in QA} == {"E0", "E1", "E2"}
    assert not ids & {r["fact_id"] for r in QA if r["subset"] in ("E0", "E1", "E2")}


def test_exemplars_are_two_different_families_and_the_clash_check_fires():
    assert len({e["attribute_id"].split("_")[0] for e in EX}) == 2
    leaked = [{**QA[0]}]
    with pytest.raises(ValueError, match="appear in the evaluation sets"):
        check_exemplars_disjoint([{"fact_id": QA[0]["fact_id"]}, EX[0]], leaked)


def test_few_shot_prefix_has_no_evaluation_answer():
    prefix = few_shot_prefix(EX)
    assert not any(r["answer"] in prefix for r in QA)
    assert prefix.count("Question:") == 2 and prefix.endswith("\n\n")
