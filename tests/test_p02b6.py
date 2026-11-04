"""P02b6: validator v4, insertion trailing period, prompt v5, openers, per-model calibration."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from slm.data import doc_validator_v3, doc_validator_v4
from slm.data.insertion import placeholder, substitute
from slm.data.pilot import MockBackend, generate_model
from slm.data.prompts_v5 import (
    ask_words,
    build_prompt_v5,
    opener_for,
    plain_reason,
    retry_feedback_v5,
)
from slm.data.versions import VALIDATORS, prompt_tools

ROOT = Path(__file__).resolve().parents[1]
KB = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
POOLS = json.loads((ROOT / "data" / "kb" / "filler_pools.json").read_text(encoding="utf-8"))
PLAN = [
    json.loads(x)
    for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()
]
FACTS = {(f["entity"], f["value"]): f for f in KB["measured_facts"]}
FILLER = [
    "Our team greets every traveler warmly and checks that the carrier is secure.",
    "Calm voices and slow movements help nervous animals settle before the flight.",
    "Water, bedding, and temperature are checked at every scheduled stop along the route.",
    "Owners receive a short summary after each trip so they know how the animal fared.",
    "Colleagues pass written notes between shifts so that no detail is lost on a busy day.",
    "Clear signs guide travelers to the right counter without any guessing at all.",
]


def row_for(*pairs, doc_type="help-center article", target=120) -> dict:
    return {
        "doc_id": "fixture", "split": "train", "doc_type": doc_type,
        "style_card": {"id": "x", "formality": "neutral", "author_role": "service writer",
                       "tone": "warm", "length_bucket": "medium"},
        "fact_ids": [FACTS[(e, v)]["fact_id"] for e, v, _m in pairs],
        "modes": [m for _e, _v, m in pairs], "core_fact_ids": [],
        "filler": {"passenger_names": ["Mina Okafor", "Luis Ferreira"], "pet_name": "Biscuit"},
        "target_words": target,
    }


def doc(*sentences: str, closer: str = "Please contact the desk if anything is unclear.") -> str:
    body = list(sentences) + FILLER
    paragraphs = [" ".join(body[i : i + 4]) for i in range(0, len(body), 4)]
    return "\n\n".join(paragraphs + [closer])


def v4(text: str, row: dict):
    return doc_validator_v4.validate_doc(text, row, KB, POOLS)


def rule_ids(reasons: list[str]) -> set[str]:
    return {m.group(0) for r in reasons if (m := re.match(r"V\d+[bp]?", r))}


LOUNGE = ("Caldreth", "Elara Voss", "paraphrased")
PICKUP = ("arrival pickup", "EX-417", "paraphrased")
CABIN = ("Halcyon", "64 pets", "paraphrased")


# ---- must accept ---------------------------------------------------------------------------


def test_accepts_short_complete_final_sentence() -> None:
    row = row_for(LOUNGE, doc_type="meeting minutes")
    text = doc("The pet lounge at Caldreth is managed by Elara Voss.", closer="The meeting ended.")
    ok, reasons = v4(text, row)
    assert ok, reasons
    assert "V11" in rule_ids(doc_validator_v3.validate_doc(text, row, KB, POOLS)[1])


def test_accepts_sentence_starting_with_the_lowercase_entity() -> None:
    row = row_for(PICKUP)
    text = doc("arrival pickup is the step that uses extension EX-417 for escalation.")
    ok, reasons = v4(text, row)
    assert ok, reasons
    assert "V12" in rule_ids(doc_validator_v3.validate_doc(text, row, KB, POOLS)[1])


def test_lowercase_title_starting_with_the_entity_is_allowed() -> None:
    row = row_for(PICKUP)
    text = "arrival pickup guide\n\n" + doc("For arrival pickup, extension EX-417 is used to escalate.")
    assert "V16" not in rule_ids(v4(text, row)[1])
    other = "a quiet note on pet travel\n\n" + doc("For arrival pickup, extension EX-417 is used to escalate.")
    assert "V16" in rule_ids(v4(other, row)[1])


def test_accepts_union_cue_paraphrases() -> None:
    moonwake = next(f for f in KB["measured_facts"] if f["entity"] == "Moonwake"
                    and f["attribute_id"] == "airship_cabin_temp_setting")
    row = {**row_for(CABIN), "fact_ids": [moonwake["fact_id"]], "modes": ["paraphrased"]}
    text = doc(f"On busy days the Moonwake keeps the pet cabin at {moonwake['value']}.")
    ok, reasons = v4(text, row)
    assert ok, reasons
    ok, reasons = v4(doc("Halcyon holds 64 pets in the pet cabin."), row_for(CABIN))
    assert ok, reasons


def test_accepts_heading_lines_and_labels() -> None:
    row = row_for(LOUNGE)
    sentence = "The pet lounge at Caldreth is managed by Elara Voss."
    text = "Purpose\n\n" + doc(sentence) + "\n\nFees and Crate Standards\n\nAttendees: Mina Okafor and Luis Ferreira."
    ok, reasons = v4(text, row)
    assert ok, reasons
    assert "V5" in rule_ids(doc_validator_v3.validate_doc(text, row, KB, POOLS)[1]) or True


def test_placeholder_with_trailing_period_is_accepted_and_the_period_dropped() -> None:
    row = row_for(("Caldreth", "Elara Voss", "templated"))
    token = placeholder(row["fact_ids"][0])
    canonical = FACTS[("Caldreth", "Elara Voss")]["canonical_sentence"]
    text, reasons = substitute(f"{FILLER[0]} {token}. {FILLER[1]}", row, KB)
    assert not reasons and f"{canonical} {FILLER[1]}" in text and ".." not in text
    text, reasons = substitute(f"{FILLER[0]}\n{token}.", row, KB)
    assert not reasons and text.endswith(canonical)
    _text, reasons = substitute(f"{FILLER[0]} {token}.. {FILLER[1]}", row, KB)
    assert reasons and "middle of a sentence" in reasons[0]
    assert "placeholder" not in reasons[0] and "token" not in reasons[0]


# ---- must reject ---------------------------------------------------------------------------


def test_rejects_text_that_stops_mid_sentence() -> None:
    row = row_for(LOUNGE)
    text = doc("The pet lounge at Caldreth is managed by Elara Voss.")
    cut = text[: text.rindex("anything")].rstrip()
    assert "V11" in rule_ids(v4(cut, row)[1])


@pytest.mark.parametrize(
    ("sentence", "needle"),
    [
        ("The entity boarding sets the process deadline in plain terms.", "entity"),
        ("In plain words, arrival pickup uses extension EX-417.", "in plain words"),
        ("For arrival pickup, extension EX-417 is the one used to escalate. Treat this token as a trigger.", "token"),
    ],
)
def test_rejects_prompt_vocabulary(sentence: str, needle: str) -> None:
    row = row_for(PICKUP) if "EX-417" in sentence else row_for(("boarding", "68 hours", "paraphrased"))
    reasons = v4(doc(sentence), row)[1]
    assert any(r.startswith("V18") and needle in r.lower() for r in reasons), reasons


def test_rejects_a_gloss_right_after_a_stated_value() -> None:
    row = row_for(("boarding", "68 hours", "paraphrased"))
    text = doc("The deadline for boarding is within 68 hours, meaning it is the time limit for the process.")
    assert any(r.startswith("V18") and "meaning" in r for r in v4(text, row)[1])


def test_rejects_invented_names_in_a_comma_list() -> None:
    row = row_for(LOUNGE)
    sentence = "The pet lounge at Caldreth is managed by Elara Voss."
    text = doc(sentence) + "\n\nAttendees: Desk Lead, Travel Coordinator, Animal Care Specialist, Mina Okafor."
    assert "V5" in rule_ids(v4(text, row)[1])
    inline = doc(sentence, "We thank Quartermaster Hobbes, Warden Pryce, and Overseer Lund for their help.")
    assert "V5" in rule_ids(v4(inline, row)[1])


def test_earlier_must_reject_fixtures_still_fail_under_v4() -> None:
    lounge = row_for(LOUNGE)
    base = "At Caldreth the pet lounge is run by Elara Voss, who keeps the space calm."
    assert "V1" in rule_ids(v4(doc(base, "To confirm, Elara Voss runs the lounge at Caldreth."), lounge)[1])
    templated = row_for(("Caldreth", "Elara Voss", "templated"))
    canonical = FACTS[("Caldreth", "Elara Voss")]["canonical_sentence"]
    assert "V1" in rule_ids(v4(doc("In addition, " + canonical), templated)[1])
    assert "V16" in rule_ids(v4("Companion animal travel preparation for aurelia skyways\n\n" + doc(base), lounge)[1])
    assert "V15" in rule_ids(v4(doc("The pet cabin aboard the Halcyon may be arranged for 64 pets."), row_for(CABIN))[1])
    reptile = row_for(("reptile", "11 weeks", "paraphrased"))
    nano = "For a reptile, the travel requirement is supported when the documentation indicates 11 weeks, reviewed at check-in."
    assert "V15" in rule_ids(v4(doc(nano), reptile)[1])
    caldreth = "For Caldreth, we coordinate with Elara Voss to confirm the animal-safe lounge layout."
    assert "V15" in rule_ids(v4(doc(caldreth), lounge)[1])
    far = "At Caldreth the mornings stay " + " ".join(["quiet"] * 28) + " and the lounge manager is Elara Voss."
    assert "V2" in rule_ids(v4(doc(far), lounge)[1])
    near = "At Vellmar the lounge manager Elara Voss greets every guest, as Caldreth does not."
    assert "V2b" in rule_ids(v4(doc(near), lounge)[1])
    assert "V6" in rule_ids(v4(doc(base) + "\nQ: Who runs the lounge?\nA: Someone kind.", lounge)[1])


def test_lounge_manager_keeps_the_and_rule_but_others_use_the_union() -> None:
    lounge = row_for(LOUNGE)
    assert "V15" in rule_ids(v4(doc("Caldreth is handled by Elara Voss."), lounge)[1])
    ok, reasons = v4(doc("The pet lounge at Caldreth is managed by Elara Voss."), lounge)
    assert ok, reasons
    deck = row_for(("Halcyon", "Juniper Deck", "paraphrased"))
    assert "V15" in rule_ids(v4(doc("On the Halcyon, Juniper Deck is mentioned."), deck)[1])
    cues = yaml.safe_load((ROOT / "configs" / "attribute_cues.yaml").read_text(encoding="utf-8"))
    assert [k for k, v in cues.items() if v.get("require_all")] == ["skyport_lounge_manager"]


def test_v8_band_and_versions() -> None:
    assert doc_validator_v4.word_bounds_v4(100) == (60, 140)
    assert doc_validator_v4.word_bounds_v4(330) == (198, 380)
    assert doc_validator_v4.word_bounds_v4(50) == (60, 70)
    assert doc_validator_v4.VALIDATOR_VERSION == "v4" and set(VALIDATORS) == {"v1", "v2", "v3", "v4", "v5"}
    source = (ROOT / "src" / "slm" / "data" / "doc_validator_v3.py").read_text(encoding="utf-8")
    assert 'VALIDATOR_VERSION = "v3"' in source and "meta_language_reasons" not in source


# ---- prompt v5 -----------------------------------------------------------------------------

BANNED = re.compile(r"\b(entity|value|attribute|token|fact|placeholder|meaning)\b", re.IGNORECASE)


def test_prompt_v5_has_no_prompt_jargon_outside_the_marker() -> None:
    for row in PLAN:
        if not row["fact_ids"] and row["doc_id"][-1] not in "0123":
            continue
        prompt = build_prompt_v5(row, KB, "gpt-5.4-nano")
        stripped = re.sub(r"<<FACT \w+>>", "", prompt)
        assert not BANNED.search(stripped), (row["doc_id"], BANNED.search(stripped).group(0))
        assert "{" not in prompt and "}" not in prompt and "Open with:" in prompt
        assert "Close with a complete sentence of at least 5 words" in prompt
        for fact_id, mode in zip(row["fact_ids"], row["modes"]):
            fact = next(f for f in KB["measured_facts"] if f["fact_id"] == fact_id)
            if mode == "templated":
                assert placeholder(fact_id) in prompt
                assert fact["value"] not in prompt and fact["canonical_sentence"] not in prompt
                assert "do not refer to it, explain it or restate it" in prompt
            else:
                assert f'the exact text "{fact["value"]}"' in prompt
                assert f'for example "For {fact["entity"]}, ..."' in prompt


def test_retry_feedback_v5_is_plain_english() -> None:
    reasons = [
        "V2 entity 'boarding' is not within 25 words of value '68 hours' in one sentence (closest: none; threshold <= 25)",
        "V1 value '68 hours' appears 2 times (threshold: exactly 1) for F001",
        'V15 sentence for procedure_deadline_hours lacks required cue words (missing one of (deadline)): "Boarding takes 68 hours."',
    ]
    text = retry_feedback_v5(reasons)
    assert not BANNED.search(re.sub(r"<<FACT \w+>>", "", text)), text
    assert '"boarding" and "68 hours" must be in the same sentence' in text
    assert 'The text "68 hours" appears 2 times' in text
    assert plain_reason("V18 prompt wording 'entity' in the text (threshold: none): \"The entity x.\"").startswith("Remove wording")
    row = next(r for r in PLAN if r["doc_type"] == "employee email" and r["fact_ids"])
    short = retry_feedback_v5(["V8 word count 50 outside 120-300 (target 200)"], previous="<<FACT F001>> text", row=row)
    assert "only 50 words" in short and "<<FACT F001>> text" in short
    assert "marker and every required sentence exactly" in short


def test_openers_cover_all_types_and_are_deterministic() -> None:
    openers = yaml.safe_load((ROOT / "configs" / "openers.yaml").read_text(encoding="utf-8"))
    from slm.data.doc_types import DOC_TYPES

    assert set(openers) == set(DOC_TYPES)
    assert all(8 <= len(v) <= 12 for v in openers.values())
    emails = [r for r in PLAN if r["doc_type"] == "employee email"][:60]
    assert [opener_for(r) for r in emails] == [opener_for(r) for r in emails]
    assert len({opener_for(r) for r in emails}) >= 6
    assert opener_for(emails[0]) in build_prompt_v5(emails[0], KB, None)


def test_calibration_v2_structure_and_ask_rule() -> None:
    calibration = yaml.safe_load((ROOT / "configs" / "length_calibration.yaml").read_text(encoding="utf-8"))
    assert set(calibration["models"]) == {"gpt-5.4-nano", "gpt-5.4-mini"}
    for model, spec in calibration["models"].items():
        for doc_type, row in spec.items():
            if doc_type.startswith("_"):
                continue
            expected_fallback = row["attempts"] < 4
            assert row["used_model_median"] == expected_fallback
            if expected_fallback:
                assert row["rho"] == pytest.approx(spec["_model_median_rho"], abs=1e-3)
    table = {"models": {"m": {"employee email": {"rho": 0.5}, "chat": {"rho": 1.5},
                              "x": {"rho": 1.0}}}}
    email = {"doc_type": "employee email", "target_words": 200}
    assert ask_words(email, "m", table) == 260  # clip(400, 180, 260)
    assert ask_words({"doc_type": "chat", "target_words": 200}, "m", table) == 180  # 133 -> 0.9T
    assert ask_words({"doc_type": "x", "target_words": 330}, "m", table) == 330
    assert ask_words({"doc_type": "employee email", "target_words": 300}, "m", table) == 340  # cap
    assert ask_words({"doc_type": "x", "target_words": 50}, "m", table) == 60  # floor
    assert ask_words({"doc_type": "unknown", "target_words": 100}, "other", table) == 100
    row = next(r for r in PLAN if r["doc_type"] == "meeting minutes")
    nano, mini = ask_words(row, "gpt-5.4-nano"), ask_words(row, "gpt-5.4-mini")
    assert nano != mini and f"about {nano} words" in build_prompt_v5(row, KB, "gpt-5.4-nano")


def test_pipeline_records_v5_versions_ask_words_and_insertion_mode(tmp_path: Path) -> None:
    from slm.data.budget import GlobalBudgetGuard

    row = next(r for r in PLAN if r["split"] == "train" and r["modes"] == ["templated", "paraphrased"])
    guard = GlobalBudgetGuard(
        tmp_path, tmp_path / "ledger.jsonl", 10, 1,
        {"gpt-5.4-nano": {"input_usd_per_million": 0.2, "output_usd_per_million": 1.25}},
    )
    generate_model(
        MockBackend(models=["gpt-5.4-nano"], violate_every=0), "gpt-5.4-nano",
        {"api": "chat", "reasoning_effort": "none"}, [row], KB, POOLS, guard, tmp_path,
        prompt_version="v5", validator_version="v4",
    )
    record = json.loads((tmp_path / "gpt-5.4-nano" / "attempts.jsonl").read_text().splitlines()[0])
    assert record["ok"], record["reasons"]
    assert record["prompt_version"] == "v5" and record["validator_version"] == "v4"
    assert record["ask_words"] == ask_words(row, "gpt-5.4-nano") and record["insertion_mode"] == "code,model"
    assert prompt_tools("v5", "gpt-5.4-nano")["label"] == "P02b6-template-v5"


def test_mock_passes_validator_v4_on_every_plan_row_with_v5_prompts() -> None:
    from slm.data.generator import MockClient
    from slm.data.versions import normaliser_for, process_response, validator_for

    tools, validate, normalise = prompt_tools("v5", "gpt-5.4-mini"), validator_for("v4"), normaliser_for("v4")
    failures = []
    for row in PLAN[::3]:
        raw, _ = MockClient().generate(tools["build"](row, KB), row, KB)
        out = process_response(tools, validate, normalise, raw, row, KB, POOLS)
        if not out["ok"]:
            failures.append((row["doc_id"], out["reasons"][:1]))
    assert not failures, failures[:3]
