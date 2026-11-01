"""P01 knowledge-base and validator tests."""

import json
from pathlib import Path

import scripts.validate_kb as validator
from scripts.validate_kb import DEFAULT_PATH, validate


def load_kb() -> dict:
    with DEFAULT_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_built_kb_valid() -> None:
    assert validate(load_kb()) == []


def test_validator_rejects_duplicate_value() -> None:
    kb = load_kb()
    kb["measured_facts"][1]["value"] = kb["measured_facts"][0]["value"]
    assert any("R1" in error for error in validate(kb))


def test_validator_rejects_reused_digit_run() -> None:
    kb = load_kb()
    kb["measured_facts"][1]["value"] = "RG-731"
    assert any("R2" in error for error in validate(kb))


def test_validator_rejects_substring_value() -> None:
    kb = load_kb()
    kb["measured_facts"][0]["value"] = "85"
    assert any("R4" in error for error in validate(kb))


def test_validator_rejects_missing_fact() -> None:
    kb = load_kb()
    kb["measured_facts"].pop()
    assert any("120" in error for error in validate(kb))


def test_validator_rejects_bad_prefix() -> None:
    kb = load_kb()
    kb["measured_facts"][0]["canonical_prefix"] = "Wrong prefix "
    assert any("canonical prefix" in error for error in validate(kb))


def test_validator_rejects_shared_capitalized_name_token() -> None:
    kb = load_kb()
    kb["measured_facts"][1]["value"] = "Elara Vale"
    assert any("R5" in error for error in validate(kb))


def test_validator_rejects_arithmetic_progression() -> None:
    kb = load_kb()
    values = ["120 pets", "140 pets", "160 pets", "180 pets", "200 pets", "220 pets"]
    for fact, value in zip(kb["measured_facts"][6:12], values):
        fact["value"] = value
    assert any("R10" in error for error in validate(kb))


def test_validator_rejects_out_of_range_value() -> None:
    kb = load_kb()
    kb["measured_facts"][6]["value"] = "999 pets"
    assert any("R7" in error for error in validate(kb))


def test_validator_rejects_quarantine_over_daily_fraction() -> None:
    kb = load_kb()
    kb["measured_facts"][27]["value"] = "57 kennels"
    assert any("quarter" in error for error in validate(kb))


def test_validator_rejects_core_digit_and_meta_word() -> None:
    kb = load_kb()
    kb["core_facts"][0]["sentence"] = "The study uses 2 records."
    errors = validate(kb)
    assert any("digit" in error for error in errors)
    assert any("meta vocabulary" in error for error in errors)


def test_validator_rejects_filler_collision(tmp_path, monkeypatch) -> None:
    kb = load_kb()
    with validator.FILLER_PATH.open(encoding="utf-8") as handle:
        pools = json.load(handle)
    pools["pet_names"][0] = "Elara"
    filler_path = Path(tmp_path) / "filler_pools.json"
    filler_path.write_text(json.dumps(pools), encoding="utf-8")
    monkeypatch.setattr(validator, "FILLER_PATH", filler_path)
    assert any("filler value collides" in error for error in validate(kb))


def test_validator_rejects_decimal_zero() -> None:
    kb = load_kb()
    kb["measured_facts"][60]["value"] = "32.0 kg"
    assert any("R11" in error for error in validate(kb))


def test_validator_rejects_any_decimal_value() -> None:
    kb = load_kb()
    kb["measured_facts"][60]["value"] = "22.5 kg"
    assert any("R11" in error for error in validate(kb))


def test_validator_rejects_weight_outside_range() -> None:
    kb = load_kb()
    kb["measured_facts"][60]["value"] = "49.5 kg"
    assert any("per-entity range" in error for error in validate(kb))


def test_validator_rejects_per_entity_weight_range() -> None:
    kb = load_kb()
    kb["measured_facts"][60]["value"] = "30 kg"
    assert any("per-entity range" in error for error in validate(kb))


def test_validator_rejects_per_entity_crate_range() -> None:
    kb = load_kb()
    kb["measured_facts"][66]["value"] = "75 cm"
    assert any("per-entity range" in error for error in validate(kb))


def test_validator_rejects_weight_ordering() -> None:
    kb = load_kb()
    kb["measured_facts"][64]["value"] = "48.5 kg"
    assert any("ordering bird < rabbit" in error for error in validate(kb))


def test_validator_rejects_crate_ordering() -> None:
    kb = load_kb()
    kb["measured_facts"][69]["value"] = "120 cm"
    assert any("ordering rabbit < cat" in error for error in validate(kb))


def test_validator_rejects_fee_ordering() -> None:
    kb = load_kb()
    kb["measured_facts"][54]["value"] = "$150"
    assert any("ordering cat < small dog" in error for error in validate(kb))


def test_validator_rejects_payout_ordering() -> None:
    kb = load_kb()
    kb["measured_facts"][109]["value"] = "$300"
    assert any("ordering missed connection < lost crate" in error for error in validate(kb))


def test_validator_rejects_payout_severity_ordering() -> None:
    kb = load_kb()
    kb["measured_facts"][108]["value"] = "$900"
    assert any("ordering delayed departure < missed connection" in error for error in validate(kb))


def test_validator_rejects_consecutive_handler_initials() -> None:
    kb = load_kb()
    names = ["Aster One", "Beryl Two", "Cinder Three", "Dara Four", "Eris Five", "Fenn Six"]
    handler_facts = [
        fact
        for fact in kb["measured_facts"]
        if fact["attribute_id"] == "airship_onboard_handler_name"
    ]
    for fact, value in zip(handler_facts, names):
        fact["value"] = value
    assert any("consecutive alphabetical run" in error for error in validate(kb))


def test_validator_rejects_lowercase_canonical_sentence() -> None:
    kb = load_kb()
    sentence = kb["measured_facts"][0]["canonical_sentence"]
    kb["measured_facts"][0]["canonical_sentence"] = sentence.lower()
    assert any("does not start uppercase" in error for error in validate(kb))


def test_validator_rejects_duplicate_canonical_pattern() -> None:
    kb = load_kb()
    kb["measured_facts"][0]["canonical_sentence"] = (
        "The daily pet capacity at Caldreth is Elara Voss."
    )
    kb["measured_facts"][1]["canonical_sentence"] = (
        "The daily pet capacity at Vellmar is Miren Quill."
    )
    errors = validate(kb)
    assert any("canonical sentence pattern" in error for error in errors)


def test_validator_rejects_alphabetical_filler_pool(tmp_path, monkeypatch) -> None:
    kb = load_kb()
    with validator.FILLER_PATH.open(encoding="utf-8") as handle:
        pools = json.load(handle)
    pools["pet_names"][:10] = sorted(pools["pet_names"][:10])
    filler_path = Path(tmp_path) / "filler_pools.json"
    filler_path.write_text(json.dumps(pools), encoding="utf-8")
    monkeypatch.setattr(validator, "FILLER_PATH", filler_path)
    assert any("filler pool pet_names is alphabetical" in error for error in validate(kb))
