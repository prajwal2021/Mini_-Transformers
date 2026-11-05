"""P02b7h: tightened bank-only cue groups, core clauses, cue statistics."""

from __future__ import annotations

import json
from pathlib import Path

from slm.data import bank
from slm.data import doc_validator as dv

KB = json.loads(Path("data/kb/kb.json").read_text(encoding="utf-8"))
BY_ATTR = {}
for _fact in KB["measured_facts"]:
    BY_ATTR.setdefault(_fact["attribute_id"], _fact)

TIGHTENED = {
    "species_max_combined_weight": [["maximum", "limit", "no more than", "cannot exceed", "at most", "not exceed"]],
    "species_min_age_weeks": [["minimum", "at least", "no younger", "must be at least"]],
    "compensation_claim_window_days": [["claim"], ["window", "within", "period", "days", "deadline"]],
    "skyport_quarantine_room_capacity": [["quarantine"], ["capacity", "holds", "accommodat", "room for", "can hold", "can take"]],
    "airship_onboard_handler_name": [["handler", "handles", "looks after", "cares for", "in charge"]],
}


def sentence(attr: str, middle: str) -> str:
    fact = BY_ATTR[attr]
    return f"Note that {fact['entity']} {middle} {fact['value']} today."


def test_exactly_six_attributes_have_bank_cue_groups_and_the_five_match_the_spec() -> None:
    cues = dv.load_cues()
    with_bank = {a for a, spec in cues.items() if "bank_cue_groups" in spec}
    assert with_bank == set(TIGHTENED) | {"skyport_daily_pet_cap"}
    for attr, groups in TIGHTENED.items():
        assert cues[attr]["bank_cue_groups"] == groups
    assert len(cues) == 20


def test_validator_cue_groups_are_untouched() -> None:
    cues = dv.load_cues()
    assert cues["airship_onboard_handler_name"]["cue_groups"][0][-2:] == ["onboard", "aboard"]
    assert cues["species_max_combined_weight"]["cue_groups"] == [
        ["weight", "weigh", "heav", "combined", "maximum", "limit", "total"]]
    assert cues["compensation_claim_window_days"]["cue_groups"] == [
        ["claim", "window", "file", "filing", "submit", "period"]]


def test_drift_sentences_fail_and_cued_sentences_pass() -> None:
    cases = [
        ("species_max_combined_weight", "weighs", "has a maximum combined weight of"),
        ("species_min_age_weeks", "is", "must be at least"),
        ("compensation_claim_window_days", "takes", "has a claim window of"),
        ("skyport_quarantine_room_capacity", "has", "quarantine room capacity is"),
        ("airship_onboard_handler_name", "is aboard", "is the handler for"),
    ]
    for attr, bad, good in cases:
        fact = BY_ATTR[attr]
        assert not bank.bank_cues_met(sentence(attr, bad), fact), attr
    good_sentences = {
        "species_max_combined_weight": "The maximum combined weight for {entity} is {value}.",
        "species_min_age_weeks": "The minimum age for {entity} is {value}.",
        "compensation_claim_window_days": "The claim window for {entity} is {value}, within the period.",
        "skyport_quarantine_room_capacity": "The quarantine room at {entity} has a capacity of {value}.",
        "airship_onboard_handler_name": "The handler for {entity} is {value}.",
    }
    for attr, template in good_sentences.items():
        fact = BY_ATTR[attr]
        assert bank.bank_cues_met(template.format(entity=fact["entity"], value=fact["value"]), fact), attr


def test_onboard_or_aboard_alone_no_longer_counts_for_the_handler() -> None:
    fact = BY_ATTR["airship_onboard_handler_name"]
    assert not bank.bank_cues_met(f"{fact['value']} is aboard the {fact['entity']} today.", fact)
    assert not bank.bank_cues_met(f"{fact['value']} is onboard the {fact['entity']} today.", fact)


def test_generation_prompt_lists_the_cue_words_for_each_tightened_attribute() -> None:
    frames = bank.load_frames()[:2]
    for attr, groups in TIGHTENED.items():
        prompt = bank.candidate_prompt(BY_ATTR[attr], frames)
        for group in groups:
            assert "use at least one of these words or phrases: " + ", ".join(group) + ";" in prompt, attr


def test_other_attributes_have_no_extra_prompt_line() -> None:
    fact = BY_ATTR["skyport_relief_gate"]
    assert "use at least one of these words" not in bank.candidate_prompt(fact, bank.load_frames()[:2])


def test_core_clause_strips_the_lead_and_the_carrier() -> None:
    assert bank.core_clause("Please be aware that Vellmar can hold 195 pets a day.", "Vellmar", "195 pets") == "ent can hold val"
    assert bank.core_clause("Our guidance is that Vellmar can hold 195 pets, as the desk records it.", "Vellmar", "195 pets") == "ent can hold val"
