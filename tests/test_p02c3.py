"""P02c3: marker repair v2, prompt v8, opener a/an agreement, artifact-rate detector, amended gates."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from slm.data import openers_v2
from slm.data.artifacts import artifact_by_type, artifact_hits, artifact_rate, has_artifact
from slm.data.insertion import repair_markers
from slm.data.prompts_v7 import build_prompt_v7
from slm.data.prompts_v8 import build_prompt_v8
from slm.data.versions import prompt_tools

ROOT = Path(__file__).resolve().parents[1]
PLAN = [json.loads(x) for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()]
KB = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
FID = "F001"
SENT = "SENTENCE ONE."
ROW = {"doc_id": "t-1", "doc_type": "policy manual section", "fact_ids": [FID]}
MARK = f"<<FACT {FID}>>"


def repair(raw: str, row: dict | None = None) -> tuple[str, dict]:
    return repair_markers(raw, row or ROW, KB, {FID: SENT})


# The five artifacts of run 1/2 as (model output with the marker where the model put it, clean expectation)
OLD_ARTIFACTS = [
    ("Please remember that the large dog allowance remains fixed for pet and crate together, "
     f"and {MARK} The same attention applies when a reptile booking is reviewed.",
     "Please remember that the large dog allowance remains fixed for pet and crate together. SENTENCE ONE. "
     "The same attention applies when a reptile booking is reviewed."),
    (f"If you are traveling with a bird, {MARK} Keep the crate secure and ask for help.",
     "SENTENCE ONE. Keep the crate secure and ask for help."),
    (f"For Port Isolde, {MARK} and staff must not promise acceptance beyond the authority given.",
     "SENTENCE ONE. Staff must not promise acceptance beyond the authority given."),
    (f"Staff also remain attentive to daily handling needs, {MARK} and so that planning stays balanced.",
     "Staff also remain attentive to daily handling needs. SENTENCE ONE."),
    (f"For cat travel, {MARK} Please speak with the desk right away if you need help.",
     "SENTENCE ONE. Please speak with the desk right away if you need help."),
]
OLD_OUTPUT = [
    "Please remember that the large dog allowance remains fixed, and The same attention applies when a booking is reviewed.",
    "If you are traveling with a bird, Keep the crate secure and ask for help.",
    "For Port Isolde, and staff must not promise acceptance beyond the authority given.",
    "Staff also remain attentive to daily handling needs, and so that planning stays balanced.",
    "For cat travel, Please speak with the desk right away if you need help.",
]


@pytest.mark.parametrize(("raw", "expected"), OLD_ARTIFACTS)
def test_repair_v2_fixes_the_old_artifacts(raw: str, expected: str) -> None:
    text, placements = repair(raw)
    assert text == expected
    assert placements == {FID: "repaired_mid_v2"} and not has_artifact(text)


@pytest.mark.parametrize("old", OLD_OUTPUT)
def test_detector_flags_the_old_artifacts(old: str) -> None:
    assert has_artifact(old), old


def test_repair_is_deterministic_and_leaves_no_markers() -> None:
    raw = OLD_ARTIFACTS[0][0] + " <<FACT F999>> Extra << stray >> words."
    first, second = repair(raw), repair(raw)
    assert first == second
    assert "<<" not in first[0] and ">>" not in first[0] and "F999" not in first[0]
    plain = "One calm line here. Another calm line follows it. A third line ends. A fourth ends too."
    assert repair(plain)[0].count(SENT) == 1 and repair(plain) == repair(plain)  # no marker: one insertion


def test_marker_at_paragraph_start_and_after_a_full_stop_is_model_placed() -> None:
    text, placements = repair(f"First paragraph ends here.\n\n{MARK} Second paragraph follows.")
    assert placements == {FID: "model"} and "\n\nSENTENCE ONE. Second paragraph follows." in text
    text, placements = repair(f"Desks are calm. {MARK} Staff stay kind.")
    assert placements == {FID: "model"} and "Desks are calm. SENTENCE ONE. Staff stay kind." in text


def test_marker_inside_a_chat_line_keeps_the_speaker_label() -> None:
    row = {**ROW, "doc_type": "internal chat thread"}
    raw = f"Planner: We checked the carriers and the lounge, and {MARK} then went on.\nHandler: Fine."
    text, placements = repair(raw, row)
    assert placements == {FID: "repaired_mid_v2"}
    assert text.split("\n")[0].startswith("Planner: ") and "SENTENCE ONE." in text.split("\n")[0]
    assert text.split("\n")[1] == "Handler: Fine."


def test_duplicate_markers_keep_one_sentence() -> None:
    raw = f"Alpha is calm. {MARK} Beta is steady and kind to every guest, {MARK} and gentle too."
    text, placements = repair(raw)
    assert text.count(SENT) == 1 and placements == {FID: "repaired_dup"} and "<<" not in text


def test_marker_glued_to_punctuation_and_empty_remainders() -> None:
    text, _ = repair(f"The whole desk team keeps calm routines for every traveler and pet each day {MARK}")
    assert text.endswith("SENTENCE ONE.") and text.startswith("The whole desk team")
    text, _ = repair(f"Short, {MARK}, and so on and so forth.")
    assert "SENTENCE ONE." in text and not has_artifact(text)


def test_detector_exemptions_and_clean_texts() -> None:
    assert not has_artifact("Hello team, We start now.\nThe desk is calm.")  # greeting line
    assert not has_artifact("Remember: Keep the crate closed. Staff say: The line moves.")  # colon, not comma
    assert not has_artifact("Travelers come from Windmere, Moonwake and Brightwater.")
    assert not has_artifact("The desk helps, and the team smiles.")
    rate, bad, bearing = artifact_rate([
        {"fact_ids": ["F1"], "text": OLD_OUTPUT[0], "doc_type": "a"},
        {"fact_ids": ["F1"], "text": "All clean here.", "doc_type": "a"},
        {"fact_ids": [], "text": OLD_OUTPUT[1], "doc_type": "b"},
    ])
    assert (rate, bad, bearing) == (0.5, 1, 2)
    assert artifact_by_type([{"fact_ids": ["F1"], "text": OLD_OUTPUT[0], "doc_type": "a"}]) == {"a": (1, 1)}
    assert artifact_hits(OLD_OUTPUT[3])


def vowel_sound(word: str) -> bool:
    low = word.lower()
    if low.startswith(("hour", "honest", "honor", "honour", "heir")):
        return True
    if low.startswith(("uni", "use", "usu", "uti", "eu", "one", "once", "ubi")):
        return False
    return low[0] in "aeiou"


def test_openers_use_a_and_an_correctly_over_20000_samples_per_type() -> None:
    types = sorted({r["doc_type"] for r in PLAN})
    for doc_type in types:
        for i in range(20000):
            text = openers_v2.plain(openers_v2.opener(doc_type, f"art-{doc_type}-{i}"))
            for article, word in re.findall(r"\b([Aa]n?) ([A-Za-z][A-Za-z'-]*)", text):
                assert (article.lower() == "an") == vowel_sound(word), text
    assert openers_v2.fix_articles("A earnest month, an cool unit, a hour") == "An earnest month, a cool unit, an hour"


def test_prompt_v8_adds_exactly_one_sentence_to_v7() -> None:
    row = next(r for r in PLAN if r["fact_ids"])
    v7, v8 = build_prompt_v7(row, KB).splitlines(), build_prompt_v8(row, KB).splitlines()
    added = [line for line in v8 if line not in v7]
    removed = [line for line in v7 if line not in v8]
    assert not removed and len(added) == 1 and len(v8) == len(v7) + 1
    assert added[0].startswith("Each marker stands for one complete sentence")
    assert "full stop" in added[0] and "comma" in added[0] and "conjunction" in added[0] and "lead-in" in added[0]
    assert "for example" not in added[0].lower() and '"' not in added[0]
    tools = prompt_tools("v8")
    assert tools["label"] == "P02c3-template-v8" and tools["repair"]


def load_runner():
    spec = importlib.util.spec_from_file_location("run_corpus", ROOT / "scripts" / "run_corpus.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_amended_gates_per_type_minimum_and_artifact_rate() -> None:
    module = load_runner()
    good = {"accepted_within_5": 0.97, "mean_attempts": 1.2, "projected_full_run": 5.0, "opening_5gram_dup": 0.01,
            "artifact_rate": 0.01, "accept_by_type": {"a": (9, 11), "b": (20, 20)}}
    assert all(module.evaluate(good, 1.0).values())  # type a has 11 docs: not evaluated
    assert not module.evaluate({**good, "accept_by_type": {"a": (17, 20)}}, 1.0)["every_type"]  # 85% at n = 20
    assert module.evaluate({**good, "accept_by_type": {"a": (18, 20)}}, 1.0)["every_type"]  # 90% passes
    assert not module.evaluate({**good, "artifact_rate": 0.03}, 1.0)["artifact_rate"]
    assert module.evaluate({**good, "artifact_rate": 0.02}, 1.0)["artifact_rate"]


def test_consecutive_markers_in_one_sentence_leave_no_fragment() -> None:
    row = {**ROW, "fact_ids": ["F001", "F002"]}
    sentences = {"F001": "ONE.", "F002": "TWO."}
    raw = ("Please route questions back to us so we keep the advice consistent. <<FACT F001>> If anyone is checking "
           "documents for a bird, <<FACT F002>> and that detail should stay aligned with the passenger.")
    text, placements = repair_markers(raw, row, KB, sentences)
    assert text == ("Please route questions back to us so we keep the advice consistent. ONE. TWO. "
                    "That detail should stay aligned with the passenger.")
    assert placements == {"F001": "model", "F002": "repaired_mid_v2"} and not has_artifact(text)


def test_signoff_style_label_before_a_marker_only_counts_in_chat() -> None:
    raw = f"We understand how upsetting that is.\n\nCompanion Animal Travel Desk: {MARK} We are placing this into review."
    text, placements = repair(raw, {**ROW, "doc_type": "complaint letter + reply"})
    assert "Companion Animal Travel Desk:" not in text and placements == {FID: "repaired_mid_v2"}
    assert text.endswith("SENTENCE ONE. We are placing this into review.")
    chat, placements = repair(f"Planner: {MARK} We are placing this into review.", {**ROW, "doc_type": "internal chat thread"})
    assert chat == "Planner: SENTENCE ONE. We are placing this into review." and placements == {FID: "model"}
