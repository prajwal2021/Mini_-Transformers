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


def test_other_attributes_list_their_validator_cue_words_in_the_prompt() -> None:
    fact = BY_ATTR["skyport_relief_gate"]  # P02b7i: every attribute lists its cue words
    prompt = bank.candidate_prompt(fact, bank.load_frames()[:2])
    assert "use at least one of these words or phrases: relief;" in prompt
    assert "use at least one of these words or phrases: gate, code;" in prompt
    assert not bank.bank_cue_groups(fact)  # the check itself is unchanged for these attributes


def test_core_clause_strips_the_lead_and_the_carrier() -> None:
    assert bank.core_clause("Please be aware that Vellmar can hold 195 pets a day.", "Vellmar", "195 pets") == "ent can hold val"
    assert bank.core_clause("Our guidance is that Vellmar can hold 195 pets, as the desk records it.", "Vellmar", "195 pets") == "ent can hold val"


def test_v6_report_sections_on_a_tiny_synthetic_pilot(tmp_path: Path) -> None:
    from slm.data.pilot import v6_lines

    plan = [json.loads(x) for x in Path("data/plan/plan.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = [r for r in plan if r["modes"] == ["paraphrased"]][:3]
    facts = {f["fact_id"]: f for f in KB["measured_facts"]}
    sentences, allocation, attempts = [], [], []
    for number, row in enumerate(rows):
        fact = facts[row["fact_ids"][0]]
        sid = f"{fact['fact_id']}-b{number:03d}"
        text = f"Please be aware that {fact['entity']} is listed as {fact['value']} number {number}."
        sentences.append({"sentence_id": sid, "fact_id": fact["fact_id"], "text": text, "frame": "f10"})
        allocation.append({"doc_id": row["doc_id"], "fact_id": fact["fact_id"], "sentence_id": sid, "frame": "f10"})
        attempts.append({
            "doc_id": row["doc_id"], "attempt": 1, "ok": number < 2, "reasons": [] if number < 2 else ["V7 x"],
            "text": text, "usd": 0.001, "cached": False, "input_tokens": 100, "output_tokens": 50,
            "reasoning_tokens": 0, "latency": 1.0, "stuck": number == 2,
            "placements": {fact["fact_id"]: {"placement": "model" if number == 0 else "repaired_append",
                                              "sentence_id": sid, "frame": "f10"}},
        })
    (tmp_path / "bank.jsonl").write_text("".join(json.dumps(x) + "\n" for x in sentences), encoding="utf-8")
    (tmp_path / "allocation.jsonl").write_text("".join(json.dumps(x) + "\n" for x in allocation), encoding="utf-8")
    lines = v6_lines({"m": (attempts, [])}, rows, KB, 5, tmp_path, 1.5, 1.4)
    text = "\n".join(lines)
    assert "| paraphrased | model | 1 |" in text and "| paraphrased | repaired_append | 1 |" in text
    assert "m: " + rows[2]["doc_id"] in text and "Stuck documents" in text
    assert "$1.50 | $1.40" in text and "at 1.4 attempts/doc" in text
    assert "Manipulation check" in text and "| m | 2 | 2/2 | 0 | 0 |" in text
