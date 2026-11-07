# ruff: noqa: E501
"""R01 1-2: the error taxonomy (one fixture per class and attribute type) and ranking accuracy."""

import json
from pathlib import Path

import pandas as pd
import pytest

from slm.sft_eval import (
    CLASSES,
    Taxonomy,
    error_summary,
    is_degenerate,
    rank_of_first,
    rank_rows,
    ranking_summary,
)
from slm.sft_eval.evaluate import evaluate_qa

ROOT = Path(__file__).resolve().parents[1]
KB = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
TAX = Taxonomy.from_kb(KB)
FACTS = {f["attribute_id"]: f for f in reversed(KB["measured_facts"])}  # one fact per attribute

# an invented value of each class that is in no KB value list
HALLUCINATED = {
    "person_name": "Zed Quorrin", "count": "999 {u}", "code": "{p}-999", "time_of_day": "03:17",
    "temperature": "99 degrees Celsius", "place_name": "Violet Balcony", "money": "$9999",
    "weight": "999 kg", "dimension": "999 cm", "duration": "999 {u}", "role_title": "Hall Tamer",
}


def hallucination(fact: dict) -> str:
    v = fact["value"]
    return HALLUCINATED[fact["value_class"]].format(u=v.split(" ", 1)[1] if " " in v else "", p=v.split("-")[0])


def other_value(fact: dict) -> str:
    return next(v for v in TAX.values_of[fact["attribute_id"]] if v != fact["value"])


def cls(fact: dict, prediction: str) -> str:
    return TAX.classify(prediction, fact["attribute_id"], fact["value"])


def test_the_kb_has_eleven_value_classes_and_all_are_covered_by_fixtures():
    assert set(TAX.class_of.values()) == set(HALLUCINATED)
    assert len(FACTS) == 20


@pytest.mark.parametrize("attr", sorted(FACTS))
def test_correct(attr):
    f = FACTS[attr]
    assert cls(f, f["canonical_sentence"]) == "correct"
    assert cls(f, f"It is {f['value']}") == "correct"


@pytest.mark.parametrize("attr", sorted(FACTS))
def test_right_type_wrong_value(attr):
    f = FACTS[attr]
    assert cls(f, f"The answer is {other_value(f)}.") == "right_type_wrong_value"
    assert cls(f, f"Either {f['value']} or {other_value(f)}.") == "right_type_wrong_value"  # gold listed with a rival


@pytest.mark.parametrize("attr", sorted(FACTS))
def test_out_of_kb_hallucination(attr):
    f = FACTS[attr]
    assert cls(f, f"The answer is {hallucination(f)}.") == "out_of_kb_hallucination"


@pytest.mark.parametrize("attr", sorted(FACTS))
def test_format_failure(attr):
    f = FACTS[attr]
    assert cls(f, "") == "format_failure"
    assert cls(f, "I do not know.") == "format_failure"
    assert cls(f, "yes yes yes yes yes yes") == "format_failure"
    assert cls(f, f"{other_value(f)} {other_value(f)} {other_value(f)} {other_value(f)}") == "format_failure"  # repetition beats the value


def test_a_kb_value_of_another_attribute_with_the_same_class_is_right_type():
    f = FACTS["skyport_relief_gate"]
    other_code = FACTS["procedure_form_code"]["value"]
    assert cls(f, f"It is {other_code}.") == "right_type_wrong_value"


def test_a_kb_value_of_another_attribute_of_another_class_is_wrong_attribute_not_format_failure():
    """R08: a well-formed answer about the wrong attribute is not a format failure."""
    f = FACTS["skyport_relief_gate"]
    money = FACTS["species_pet_fee"]["value"]
    assert cls(f, f"It is {money}.") == "wrong_attribute"
    assert cls(f, f"The pet travel fee is {money}.") == "wrong_attribute"
    name = FACTS["skyport_lounge_manager"]["value"]
    assert cls(FACTS["species_pet_fee"], f"It is {name}.") == "wrong_attribute"


def test_a_value_like_string_that_is_no_kb_value_and_of_the_wrong_class_stays_a_format_failure():
    assert cls(FACTS["species_pet_fee"], "It is Zed Quarrelby.") == "format_failure"
    assert cls(FACTS["skyport_relief_gate"], "It is $9999.") == "format_failure"


def test_entity_names_and_sentence_openers_are_not_names():
    f = FACTS["skyport_lounge_manager"]
    assert cls(f, "The lounge manager at Port Isolde is unknown.") == "format_failure"
    assert cls(f, "The Elara is here") == "format_failure"  # a single capitalised word is not a name


def test_bare_number_matching_a_same_attribute_value_is_right_type_and_other_numbers_hallucinate():
    f = FACTS["skyport_daily_pet_cap"]
    n = other_value(f).split()[0]
    assert cls(f, f"About {n}.") == "right_type_wrong_value"
    assert cls(f, "About 777.") == "out_of_kb_hallucination"
    assert cls(f, "About 777 kennels.") == "out_of_kb_hallucination"


def test_time_is_not_read_as_a_number():
    f = FACTS["species_min_age_weeks"]
    assert cls(f, "It opens at 99:59.") == "format_failure"  # a time that is no KB value is not a number answer either
    assert cls(f, "It opens at 07:53.") in ("format_failure", "wrong_attribute")  # a KB time of another attribute is a wrong-attribute answer


@pytest.mark.parametrize(
    "text, expected",
    [("a b c d e f", False), ("a a a a b c", True), ("go to go to go to x", True), ("a b a b c d e f g h i j", False),
     ("a a a", False)],  # fewer than 4 words is never a loop
)
def test_degenerate_repetition_is_more_than_half_the_words(text, expected):
    assert is_degenerate(text) is expected


def test_exactly_one_class_for_a_grid_of_predictions():
    for f in FACTS.values():
        for pred in ["", "x", "The answer is 12.", f["canonical_sentence"], hallucination(f), other_value(f), "A B C D"]:
            assert cls(f, pred) in CLASSES


def test_evaluate_qa_adds_error_class_and_ranking_columns():
    f = FACTS["species_pet_fee"]
    rows = [{"id": "E2:1", "fact_id": f["fact_id"], "subset": "E2", "prompt": "Question: q\nAnswer:", "answer": f["canonical_sentence"],
             "value": f["value"], "attribute_id": f["attribute_id"], "freq_bin": f["freq_bin"], "div_bin": f["div_bin"], "template_id": "t"}]
    av = {a: tuple(v) for a, v in TAX.values_of.items()}

    class Scorer:  # prefers the gold value strongly
        def score_details(self, pairs):
            return [(-1.0 if f["value"] in c else -5.0, 2) for _, c in pairs]

    out = evaluate_qa(rows, lambda p: (" " + f["canonical_sentence"], False), 0, av, "sft", taxonomy=TAX, ranker=Scorer())
    assert out.loc[0, "error_class"] == "correct"
    assert out.loc[0, ["rank_value", "rank_value_norm", "rank_sentence", "rank_sentence_norm"]].tolist() == [1, 1, 1, 1]
    plain = evaluate_qa(rows, lambda p: ("", False), 0, av, "sft")
    assert "error_class" not in plain.columns and "rank_value" not in plain.columns


def test_error_summary_has_every_class_for_every_group():
    t = pd.DataFrame({"checkpoint": ["sft"] * 3, "prompt_mode": ["zero_shot"] * 3, "eval_set": ["E2"] * 3,
                      "error_class": ["correct", "format_failure", "format_failure"]})
    s = error_summary(t)
    assert list(s["error_class"]) == sorted(CLASSES) and s["n"].sum() == 3
    assert s.loc[s["error_class"] == "format_failure", "share"].iloc[0] == pytest.approx(2 / 3)


# ---- ranking ------------------------------------------------------------------------------------


def test_rank_of_first_ties_are_never_rank_one():
    assert rank_of_first([-1.0, -2.0, -3.0]) == 1
    assert rank_of_first([-2.0, -1.0, -3.0]) == 2
    assert rank_of_first([-1.0, -1.0, -3.0]) == 2


def test_rank_rows_scores_value_and_substituted_sentence_under_the_prompt_with_prefix():
    f = FACTS["species_pet_fee"]
    av = {f["attribute_id"]: tuple(TAX.values_of[f["attribute_id"]])}
    row = {"id": "q", "prompt": "Question: q\nAnswer:", "answer": f["canonical_sentence"], "value": f["value"], "attribute_id": f["attribute_id"]}
    seen = []

    class Scorer:
        def score_details(self, pairs):
            seen.extend(pairs)
            return [(-float(i), 1) for i, _ in enumerate(pairs)]  # candidate order: gold first, so gold wins each block

    res = rank_rows(Scorer(), [row], av, "PREFIX ")
    assert res["q"] == {"rank_value": 1, "rank_value_norm": 1, "rank_sentence": 1, "rank_sentence_norm": 1}
    assert len(seen) == 12 and all(p == "PREFIX Question: q\nAnswer:" for p, _ in seen)
    assert seen[0][1] == " " + f["value"] and seen[6][1] == " " + f["canonical_sentence"]
    assert all(c.startswith(" The pet travel fee for a ") for _, c in seen[6:])


def test_ranking_summary_accuracy_and_mrr():
    t = pd.DataFrame({"checkpoint": ["sft"] * 4, "prompt_mode": ["zero_shot"] * 4, "eval_set": ["E1"] * 4,
                      "rank_value": [1, 2, 4, 1], "rank_value_norm": [1] * 4, "rank_sentence": [1] * 4, "rank_sentence_norm": [1] * 4})
    s = ranking_summary(t).iloc[0]
    assert s["rank_value_acc"] == 0.5 and s["rank_value_mrr"] == pytest.approx((1 + 0.5 + 0.25 + 1) / 4)
