"""P02b5: cue groups with value masking, chat labels, code insertion, calibration, v4 prompt."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from slm.data import doc_validator, doc_validator_v2, doc_validator_v3
from slm.data.insertion import insertion_mode, placeholder, substitute
from slm.data.pilot import MockBackend, generate_model
from slm.data.prompts_v4 import ASK_CAP, ask_words, build_prompt_v4, retry_feedback_v4
from slm.data.versions import VALIDATORS, prompt_tools, validator_for

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


def doc(*sentences: str) -> str:
    body = list(sentences) + FILLER
    paragraphs = [" ".join(body[i : i + 4]) for i in range(0, len(body), 4)]
    return "\n\n".join(paragraphs + ["Please contact the desk if anything is unclear."])


def verdict(text: str, row: dict):
    return doc_validator_v3.validate_doc(text, row, KB, POOLS)


def v15(reasons: list[str]) -> list[str]:
    return [r for r in reasons if r.startswith("V15")]


# ---- 1.1 cue groups ------------------------------------------------------------------------


def test_masked_value_cannot_satisfy_the_deck_cue() -> None:
    row = row_for(("Halcyon", "Juniper Deck", "paraphrased"))
    bad = verdict(doc("On the Halcyon, Juniper Deck is mentioned."), row)[1]
    assert any("lacks required cue words" in r and "deck" in r for r in v15(bad))
    good = verdict(doc("The pet deck aboard the Halcyon is called Juniper Deck."), row)[1]
    assert not v15(good) or all("canonical" in r for r in good)  # only the leak rule may fire


def test_masked_value_cannot_satisfy_the_temperature_cue() -> None:
    row = row_for(("Windmere", "22 degrees Celsius", "paraphrased"))
    bad = verdict(doc("Windmere is kept at 22 degrees Celsius."), row)[1]
    assert v15(bad), bad  # "degrees" lives only inside the masked value, and no "cabin"
    ok = verdict(doc("On the Windmere, the pet cabin is kept at 22 degrees Celsius."), row)[1]
    assert not v15(ok), ok


def test_lounge_manager_needs_lounge_and_a_manager_stem() -> None:
    row = row_for(("Caldreth", "Elara Voss", "paraphrased"))
    ok = verdict(doc("The pet lounge at Caldreth is managed by Elara Voss."), row)[1]
    assert not v15(ok), ok
    bad = verdict(doc("Caldreth is handled by Elara Voss."), row)[1]
    assert any("lounge" in r for r in v15(bad))


def test_v2_validator_is_unchanged_by_the_new_cue_groups() -> None:
    row = row_for(("Caldreth", "Elara Voss", "paraphrased"))
    text = doc("Caldreth is run by Elara Voss and kept calm.")
    assert not v15(doc_validator_v2.validate_doc(text, row, KB, POOLS)[1])
    assert v15(verdict(text, row)[1])  # v3 (AND groups) rejects it


def test_every_attribute_has_groups_and_meaning_satisfies_its_own_groups() -> None:
    cues = yaml.safe_load((ROOT / "configs" / "attribute_cues.yaml").read_text(encoding="utf-8"))
    assert len(cues) == 20
    for name, spec in cues.items():
        assert spec["cue_groups"] and all(isinstance(g, list) and g for g in spec["cue_groups"])
        lone = [g for g in spec["cue_groups"] if len(g) == 1]
        assert all(stem not in sum(spec["cue_groups"], []) for stem in ("from", "room")) or name
        meaning = spec["meaning"].lower()
        for group in spec["cue_groups"]:
            assert any(re.search(rf"\b{re.escape(s)}", meaning) for s in group), (name, group)
        del lone


# ---- 1.2 chat format -----------------------------------------------------------------------


def chat_row() -> dict:
    return row_for(("Caldreth", "Elara Voss", "paraphrased"), doc_type="internal chat thread",
                   target=75)


CLEAN_CHAT = "\n".join([
    "Planner: The pet lounge at Caldreth is managed by Elara Voss and stays calm.",
    "Coordinator: Good, Mina Okafor and Luis Ferreira are bringing Biscuit this week.",
    "Planner: Then we should greet them early and keep the carriers close.",
    "Handler: Agreed, and I will pass the note to the evening team today.",
    "Planner: Please also remind the gate staff that nervous animals settle faster in quiet corners.",
    "Coordinator: Understood, and the cabin crew will receive the same reminder before boarding starts.",
])


def test_chat_accepts_labeled_lines_only() -> None:
    ok, reasons = verdict(CLEAN_CHAT, chat_row())
    assert ok, reasons


@pytest.mark.parametrize("variant", ["unlabeled", "title", "signoff"])
def test_chat_rejects_unlabeled_title_and_signoff(variant: str) -> None:
    lines = CLEAN_CHAT.split("\n")
    if variant == "unlabeled":
        lines[1] = "Good, Mina Okafor and Luis Ferreira are bringing Biscuit this week."
    elif variant == "title":
        lines.insert(0, "Pet lounge notes")
    else:
        lines.append("Service Writer, Companion Animal Travel Desk")
    reasons = verdict("\n".join(lines), chat_row())[1]
    assert any(r.startswith("V17") for r in reasons), reasons


# ---- 1.3 code insertion --------------------------------------------------------------------

TEMPLATED = ("Caldreth", "Elara Voss", "templated")


def test_valid_insertion_replaces_placeholder_with_the_canonical_sentence() -> None:
    row = row_for(TEMPLATED)
    token = placeholder(row["fact_ids"][0])
    canonical = FACTS[("Caldreth", "Elara Voss")]["canonical_sentence"]
    for raw in (
        f"{FILLER[0]} {token} {FILLER[1]}",
        f"{token}\n{FILLER[0]}",
        f"{FILLER[0]}\n{token} {FILLER[1]}",
    ):
        text, reasons = substitute(raw, row, KB)
        assert not reasons and canonical in text and "<<" not in text


def test_placeholder_after_speaker_label_is_allowed() -> None:
    row = row_for(TEMPLATED, doc_type="internal chat thread")
    raw = f"Planner: {placeholder(row['fact_ids'][0])}\nCoordinator: Good."
    text, reasons = substitute(raw, row, KB)
    assert not reasons and text.startswith("Planner: The lounge manager at Caldreth")


@pytest.mark.parametrize(
    ("raw_template", "expected"),
    [
        ("The lounge is run by {t} today.", "middle of a sentence"),
        ("Intro. {t}, said the team.", "middle of a sentence"),
        ("Intro. {t} and {t}", "appears 2 times"),
        ("Intro sentence only.", "is missing"),
        ("Intro. <<FACT F999>> {t}", "not one of this document's facts"),
        ("Intro. {t} Then <<oops>> here.", "stray"),
    ],
)
def test_bad_placeholders_are_rejected_with_plain_english(raw_template: str, expected: str) -> None:
    row = row_for(TEMPLATED)
    raw = raw_template.replace("{t}", placeholder(row["fact_ids"][0]))
    text, reasons = substitute(raw, row, KB)
    assert reasons and all(r.startswith("V1p") for r in reasons)
    assert any(expected in r for r in reasons), reasons
    assert text == raw


def test_v4_prompt_never_shows_the_templated_value_or_sentence() -> None:
    for row in [r for r in PLAN if "templated" in r["modes"]][:300]:
        prompt = build_prompt_v4(row, KB)
        for fact_id, mode in zip(row["fact_ids"], row["modes"]):
            fact = next(f for f in KB["measured_facts"] if f["fact_id"] == fact_id)
            if mode == "templated":
                assert placeholder(fact_id) in prompt
                assert fact["value"] not in prompt and fact["canonical_sentence"] not in prompt
                assert f'entity "{fact["entity"]}"' in prompt and "meaning:" in prompt
            else:
                assert f'value "{fact["value"]}"' in prompt
        assert "{" not in prompt and "}" not in prompt


def test_pipeline_stores_versions_ask_words_insertion_mode_and_hides_values(tmp_path: Path) -> None:
    from slm.data.budget import GlobalBudgetGuard

    row = next(r for r in PLAN if r["split"] == "train" and r["modes"] == ["templated", "paraphrased"])
    guard = GlobalBudgetGuard(
        tmp_path, tmp_path / "ledger.jsonl", 10, 1,
        {"gpt-5.4-nano": {"input_usd_per_million": 0.2, "output_usd_per_million": 1.25}},
    )
    backend = MockBackend(models=["gpt-5.4-nano"], violate_every=0)
    generate_model(
        backend, "gpt-5.4-nano", {"api": "chat", "reasoning_effort": "none"}, [row], KB, POOLS,
        guard, tmp_path, prompt_version="v4", validator_version="v3",
    )
    record = json.loads((tmp_path / "gpt-5.4-nano" / "attempts.jsonl").read_text().splitlines()[0])
    assert record["ok"], record["reasons"]
    assert record["prompt_version"] == "v4" and record["validator_version"] == "v3"
    assert record["ask_words"] == ask_words(row) and record["insertion_mode"] == "code,model"
    templated_value = next(
        f["value"] for f in KB["measured_facts"] if f["fact_id"] == row["fact_ids"][0]
    )
    assert templated_value not in record["raw_text"] and templated_value in record["text"]
    assert "<<FACT" in record["raw_text"] and "<<" not in record["text"]
    ledger = [json.loads(x) for x in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert ledger[0]["prompt_version"] == "v4" and ledger[0]["validator_version"] == "v3"


def test_placeholder_failure_triggers_retry_with_v1p_feedback(tmp_path: Path) -> None:
    from slm.data.budget import GlobalBudgetGuard

    row = next(r for r in PLAN if r["split"] == "train" and r["modes"] == ["templated", "templated"])
    guard = GlobalBudgetGuard(
        tmp_path, tmp_path / "ledger.jsonl", 10, 1,
        {"gpt-5.4-nano": {"input_usd_per_million": 0.2, "output_usd_per_million": 1.25}},
    )

    class Backend(MockBackend):
        def call(self, model, prompt, config, max_tokens, row=None, kb=None):
            result = super().call(model, prompt, config, max_tokens, row, kb)
            if "previously rejected" not in prompt and row is not None:
                result.text = result.text.replace(placeholder(row["fact_ids"][0]), "", 1)
            return result

    generate_model(
        Backend(models=["gpt-5.4-nano"], violate_every=0), "gpt-5.4-nano",
        {"api": "chat", "reasoning_effort": "none"}, [row], KB, POOLS, guard, tmp_path,
        prompt_version="v4", validator_version="v3",
    )
    attempts = [json.loads(x) for x in (tmp_path / "gpt-5.4-nano" / "attempts.jsonl").read_text().splitlines()]
    assert [a["attempt"] for a in attempts] == [1, 2] and not attempts[0]["ok"] and attempts[1]["ok"]
    assert attempts[0]["reasons"][0].startswith("V1p") and "is missing" in attempts[0]["reasons"][0]


# ---- 1.4 calibration -----------------------------------------------------------------------


def test_calibration_file_matches_the_rule() -> None:
    calibration = yaml.safe_load((ROOT / "configs" / "length_calibration_v1.yaml").read_text(encoding="utf-8"))
    assert calibration["models_pooled"] == ["gpt-5.4-mini", "gpt-5.4-nano"]
    for doc_type, spec in calibration["types"].items():
        median = calibration["pooled_median_ratio"] if spec["used_pooled_median"] else spec["median_ratio"]
        assert spec["ask_multiplier"] == pytest.approx(min(1.8, max(1.0, 1 / median)), abs=1e-3)
        assert spec["used_pooled_median"] == (spec["attempts"] < 4), doc_type
    assert max(s["ask_multiplier"] for s in calibration["types"].values()) <= 1.8


def test_ask_words_uses_multiplier_caps_at_420_and_keeps_original_target() -> None:
    calibration = {"types": {"employee email": {"ask_multiplier": 1.739}}}
    row = {"doc_type": "employee email", "target_words": 200}
    assert ask_words(row, calibration) == round(200 * 1.739)
    assert ask_words({"doc_type": "employee email", "target_words": 260}, calibration) == 420 == ASK_CAP
    assert ask_words({"doc_type": "newsletter blurb", "target_words": 100}, calibration) == 100
    plan_row = next(r for r in PLAN if r["doc_type"] == "employee email" and r["fact_ids"])
    prompt = build_prompt_v4(plan_row, KB)
    ask = ask_words(plan_row)
    assert f"about {ask} words, not fewer than {round(0.9 * ask)} words" in prompt
    # the validator band still uses the original target
    low, high = doc_validator_v3.word_bounds_v2(plan_row["target_words"])
    assert (low, high) == (max(60, -(-7 * plan_row["target_words"] // 10)), min(int(1.3 * plan_row["target_words"]), 360))


def test_short_document_retry_sends_previous_text_and_missing_words() -> None:
    row = next(r for r in PLAN if r["doc_type"] == "employee email" and r["fact_ids"])
    reasons = ["V8 word count 120 outside 182-338 (target 260)", "V1p the placeholder <<FACT F001>> is missing"]
    text = retry_feedback_v4(reasons, previous="PREVIOUS <<FACT F001>> TEXT", row=row)
    ask = ask_words(row)
    assert "PREVIOUS <<FACT F001>> TEXT" in text and "only 120 words" in text
    assert f"{ask - 120} more words" in text
    assert "keep every placeholder token and every fact sentence exactly" in text
    long_text = retry_feedback_v4(["V8 word count 400 outside 182-338 (target 260)"], previous="x", row=row)
    assert "Previous draft" not in long_text and "from the start" in long_text


# ---- 1.5 / versions ------------------------------------------------------------------------


def test_v4_template_rules_and_registry() -> None:
    chat = next(r for r in PLAN if r["doc_type"] == "internal chat thread" and r["fact_ids"])
    email = next(r for r in PLAN if r["doc_type"] == "employee email" and r["fact_ids"])
    minutes = next(r for r in PLAN if r["doc_type"] == "meeting minutes" and r["fact_ids"])
    chat_prompt, email_prompt = build_prompt_v4(chat, KB), build_prompt_v4(email, KB)
    assert "No title, no sign-off, no unlabeled lines" in chat_prompt
    assert "If you sign off" not in chat_prompt
    assert "Never sign with a job title" in email_prompt
    assert "the senior coordinator" in email_prompt
    assert "(no job titles written with capital letters)" in build_prompt_v4(minutes, KB)
    assert set(VALIDATORS) == {"v1", "v2", "v3", "v4"} and len(set(VALIDATORS.values())) == 4
    assert validator_for("v4") is doc_validator.validate_doc
    assert prompt_tools("v4")["label"] == "P02b5-template-v4" and prompt_tools("v3")["substitute"] is None
    assert doc_validator.VALIDATOR_VERSION == "v4" and doc_validator_v3.VALIDATOR_VERSION == "v3"
    assert doc_validator_v2.VALIDATOR_VERSION == "v2"
    for name in ("doc_validator_v1.py", "doc_validator_v2.py"):
        assert "chat_format_reasons" not in (ROOT / "src" / "slm" / "data" / name).read_text(encoding="utf-8")
    assert insertion_mode(next(r for r in PLAN if not r["fact_ids"])) == "none"


def test_gate_mock_passes_validator_v3_on_all_plan_rows_with_v4_prompts() -> None:
    from slm.data.generator import MockClient
    from slm.data.versions import normaliser_for, process_response

    tools, validate, normalise = prompt_tools("v4"), validator_for("v4"), normaliser_for("v4")
    failures = []
    for row in PLAN:
        raw, _ = MockClient().generate(tools["build"](row, KB), row, KB)
        out = process_response(tools, validate, normalise, raw, row, KB, POOLS)
        if not out["ok"]:
            failures.append((row["doc_id"], out["reasons"][:1]))
        for fact_id, mode in zip(row["fact_ids"], row["modes"]):
            if mode == "templated":
                value = next(f["value"] for f in KB["measured_facts"] if f["fact_id"] == fact_id)
                assert value not in raw
    assert len(PLAN) == 2407 and not failures, failures[:3]


def test_pilot_v4_rows_are_30_same_plus_20_fresh_and_stratified() -> None:
    rows = [json.loads(x) for x in (ROOT / "data" / "pilot_v4" / "pilot_rows.jsonl").read_text().splitlines()]
    old = {json.loads(x)["doc_id"] for x in (ROOT / "data" / "pilot" / "pilot_rows.jsonl").read_text().splitlines()}
    assert len(rows) == 50 and len({r["doc_id"] for r in rows}) == 50
    same = [r for r in rows if r["cohort"] == "same30"]
    fresh = [r for r in rows if r["cohort"] == "fresh20"]
    assert {r["doc_id"] for r in same} == old and len(fresh) == 20
    assert not {r["doc_id"] for r in fresh} & old
    for doc_type in ("employee email", "meeting minutes", "complaint letter + reply",
                     "training handbook page", "policy manual section"):
        assert sum(r["doc_type"] == doc_type for r in fresh) >= 4
    assert sum(set(r["modes"]) == {"templated"} for r in fresh) >= 8
    assert sum(set(r["modes"]) == {"paraphrased"} for r in fresh) >= 8
    assert sum(r["split"] != "train" for r in fresh) >= 2


def test_mock_v4_run_writes_cohort_report_and_confound_audit(tmp_path: Path) -> None:
    from slm.data.pilot import run_pilot

    out = tmp_path / "pilot_v4"
    out.mkdir()
    (out / "api_config.json").write_text(json.dumps({
        m: {"config": {"api": "chat", "reasoning_effort": "none"}, "max_output_tokens": 700}
        for m in ("gpt-5.4-nano", "gpt-5.4-mini")}), encoding="utf-8")
    lines: list[str] = []
    code = run_pilot(
        MockBackend(), ["gpt-5.4-nano", "gpt-5.4-mini"], 50, out, tmp_path, tmp_path / "reports",
        tmp_path / "API_NOTES.md", "mock", echo=lines.append, suffix="_v4",
        rows_from=ROOT / "data" / "pilot_v4" / "pilot_rows.jsonl", prompt_version="v4",
        validator_version="v3", use_saved_api_config=True, session_cap=0.4, extended=True,
        cohort_report=True,
    )
    assert code == 0 and lines[0] == "MODE: MOCK (no spend)"
    report = (tmp_path / "reports" / "pilot_report_v4.md").read_text(encoding="utf-8")
    assert report.splitlines()[0] == "Client: mock"
    for heading in ("## Criteria by cohort", "combined 50", "same 30", "fresh 20",
                    "## Mean actual/target words by doc type", "| V1p |", "| V17 |", "| V15 |",
                    "## Confound audit", "projected full run at 1.4 attempts/doc"):
        assert heading in report, heading
    assert "P02b5-template-v4" in report and "validator v3" in report
    first = json.loads((out / "gpt-5.4-nano" / "attempts.jsonl").read_text().splitlines()[0])
    assert first["prompt_version"] == "v4" and first["validator_version"] == "v3"
    assert {"ask_words", "insertion_mode"} <= set(first)
