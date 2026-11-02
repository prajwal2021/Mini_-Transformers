"""Validator v2 (P02b4): must-accept and must-reject fixtures, normalisation, v1 stays frozen."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from slm.data import doc_validator_v1
from slm.data import doc_validator_v2 as doc_validator
from slm.data.doc_validator_v2 import normalise_text, validate_doc, word_bounds_v2

ROOT = Path(__file__).resolve().parents[1]
KB = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
POOLS = json.loads((ROOT / "data" / "kb" / "filler_pools.json").read_text(encoding="utf-8"))
FACTS = {(f["entity"], f["value"]): f for f in KB["measured_facts"]}

FILLER = [
    "Our team greets every traveler warmly and checks that the carrier is secure.",
    "Calm voices and slow movements help nervous animals settle before the flight.",
    "Water, bedding, and temperature are checked at every scheduled stop along the route.",
    "Owners receive a short summary after each trip so they know how the animal fared.",
    "Colleagues pass written notes between shifts so that no detail is lost on a busy day.",
    "Clear signs guide travelers to the right counter without any guessing at all.",
    "Feedback from travelers is shared at the weekly team meeting and acted on quickly.",
    "New staff shadow experienced colleagues until they feel confident with the routine.",
]


def row_for(*pairs: tuple[str, str, str], doc_type: str = "help-center article", target: int = 120,
            role: str = "service writer") -> dict:
    ids = [FACTS[(entity, value)]["fact_id"] for entity, value, _mode in pairs]
    return {
        "doc_id": "fixture",
        "split": "train",
        "doc_type": doc_type,
        "style_card": {"id": "x", "formality": "neutral", "author_role": role,
                       "tone": "warm", "length_bucket": "medium"},
        "fact_ids": ids,
        "modes": [mode for _e, _v, mode in pairs],
        "core_fact_ids": [],
        "filler": {"passenger_names": ["Mina Okafor", "Luis Ferreira"], "pet_name": "Biscuit"},
        "target_words": target,
    }


def doc(*sentences: str, filler: int = 6) -> str:
    """Three short paragraphs: the given sentences plus filler, ending with a closer."""
    body = list(sentences) + FILLER[:filler]
    paragraphs = [" ".join(body[i : i + 4]) for i in range(0, len(body), 4)]
    return "\n\n".join(paragraphs + ["Please contact the desk if anything is unclear."])


def check(text: str, row: dict) -> tuple[bool, list[str]]:
    return validate_doc(text, row, KB, POOLS)


def rule_ids(reasons: list[str]) -> set[str]:
    return {m.group(0) for r in reasons if (m := re.match(r"V\d+b?", r))}


LOUNGE = ("Caldreth", "Elara Voss", "paraphrased")
CABIN = ("Halcyon", "64 pets", "paraphrased")
WORD28 = (
    "Caldreth's lounge manager Elara Voss greets every guest at the door, answers every worry "
    "from nervous owners with patience, and keeps the whole space calm for every animal."
)


# ---- must accept ---------------------------------------------------------------------------


def test_accepts_28_word_sentence_with_entity_three_words_away() -> None:
    assert len(re.findall(r"\b[\w'-]+\b", WORD28)) == 28
    row = row_for(LOUNGE, target=130)
    ok, reasons = check(doc(WORD28, filler=7), row)
    assert ok, reasons
    assert doc_validator.bind_distances(WORD28, row, KB) == [3]


def test_accepts_entity_capitalised_at_sentence_start() -> None:
    row = row_for(("cat", "61 cm", "paraphrased"))
    sentence = "Cat owners should know that the longest crate side allowed is 61 cm."
    ok, reasons = check(doc(sentence), row)
    assert ok, reasons


def test_accepts_assigned_code_value() -> None:
    row = row_for(("transfer", "EX-832", "paraphrased"))
    sentence = "For a transfer, the extension used to escalate the process is EX-832."
    ok, reasons = check(doc(sentence), row)
    assert ok, reasons


def test_accepts_i_this_and_the_word_answer() -> None:
    row = row_for(LOUNGE)
    sentences = [
        "At Caldreth the pet lounge is run by Elara Voss, who keeps the space calm.",
        "When owners ask, I explain that this is the easiest route to take.",
        "This keeps the answer simple for everyone on the team, and I think it works.",
        "Remember: This matters most on busy mornings.",
    ]
    ok, reasons = check(doc(*sentences, filler=4), row)
    assert ok, reasons


def test_accepts_chat_with_speaker_labels_and_no_signoff() -> None:
    chat = "\n".join(
        [
            "Planner: The pet lounge at Caldreth is run by Elara Voss and stays calm.",
            "Coordinator: Good, and the cabin aboard the Halcyon is arranged for 64 pets.",
            "Planner: Mina Okafor and Luis Ferreira are bringing Biscuit this week.",
            "Coordinator: Then we should greet them early and keep the carriers close.",
            "Planner: Agreed, and we will pass the note to the evening team today.",
        ]
    )
    row = row_for(LOUNGE, CABIN, doc_type="internal chat thread", target=80)
    ok, reasons = check(chat, row)
    assert ok, reasons


def test_accepts_curly_quotes_dashes_and_trailing_spaces_after_normalisation() -> None:
    row = row_for(LOUNGE)
    sentence = "At Caldreth the pet lounge is run by Elara Voss — who doesn’t rest."
    raw = doc(sentence).replace("\n\n", "  \n\n\n\n")
    assert not any(ord(c) > 127 for c in normalise_text(raw))
    ok, reasons = check(raw, row)
    assert ok, reasons


def test_normalise_never_changes_words_and_strips_fences() -> None:
    raw = "```\nHello “there” – friends.  \n\n\n\nNext line.\n```"
    clean = normalise_text(raw)
    assert clean == 'Hello "there" - friends.\n\nNext line.'
    words = lambda t: re.findall(r"[A-Za-z]+", t)  # noqa: E731
    assert words(clean) == words(raw)


# ---- must reject ---------------------------------------------------------------------------


def test_rejects_value_repeated_across_letter_and_reply() -> None:
    row = row_for(LOUNGE)
    letter = "At Caldreth the pet lounge is run by Elara Voss, who keeps the space calm."
    reply = "To confirm, Elara Voss runs the lounge at Caldreth."
    reasons = check(doc(letter, reply), row)[1]
    assert any(r.startswith("V1 value 'Elara Voss' appears 2 times") for r in reasons)


@pytest.mark.parametrize("prefix", ["In addition, ", "In addition, the "])
def test_rejects_templated_sentence_with_prepended_connector(prefix: str) -> None:
    row = row_for(("Caldreth", "Elara Voss", "templated"))
    canonical = FACTS[("Caldreth", "Elara Voss")]["canonical_sentence"]
    sentence = prefix + (canonical if prefix.endswith(", ") else canonical[4:])
    ok, reasons = check(doc(sentence), row)
    assert not ok and any(r.startswith("V1 templated sentence") for r in reasons)


def test_accepts_templated_sentence_standing_alone() -> None:
    row = row_for(("Caldreth", "Elara Voss", "templated"))
    canonical = FACTS[("Caldreth", "Elara Voss")]["canonical_sentence"]
    ok, reasons = check(doc(canonical), row)
    assert ok, reasons


def test_rejects_wrong_case_organisation_name() -> None:
    row = row_for(LOUNGE)
    sentence = "At Caldreth the pet lounge is run by Elara Voss, who keeps the space calm."
    text = "Companion animal travel preparation for aurelia skyways\n\n" + doc(sentence)
    reasons = check(text, row)[1]
    assert any(r.startswith("V16") for r in reasons)


def test_rejects_all_lowercase_title_line() -> None:
    row = row_for(LOUNGE)
    sentence = "At Caldreth the pet lounge is run by Elara Voss, who keeps the space calm."
    reasons = check("a quiet note on pet travel\n\n" + doc(sentence), row)[1]
    assert any(r.startswith("V16 title") for r in reasons)


def test_rejects_hedged_fact() -> None:
    row = row_for(CABIN)
    sentence = "The pet cabin aboard the Halcyon may be arranged for 64 pets on busy days."
    reasons = check(doc(sentence), row)[1]
    assert any(r.startswith("V15 hedge word 'may'") for r in reasons)
    around = "The pet cabin aboard the Halcyon is arranged for around 64 pets."
    assert any(r.startswith("V15 hedge") for r in check(doc(around), row)[1])


def test_rejects_paraphrases_without_attribute_cue() -> None:
    reptile = ("reptile", "11 weeks", "paraphrased")
    sentence = (
        "For a reptile, the travel requirement is supported when the documentation indicates "
        "11 weeks, reviewed at check-in."
    )
    reasons = check(doc(sentence), row_for(reptile))[1]
    assert any(r.startswith("V15 sentence for species_min_age_weeks lacks any cue") for r in reasons)
    nano = "For Caldreth, we coordinate with Elara Voss to confirm the animal-safe lounge layout."
    reasons = check(doc(nano), row_for(LOUNGE))[1]
    assert any(r.startswith("V15 sentence for skyport_lounge_manager lacks any cue") for r in reasons)


def test_rejects_value_thirty_words_from_entity() -> None:
    gap = " ".join(["quiet"] * 28)
    sentence = f"At Caldreth the mornings stay {gap} and the lounge manager is Elara Voss."
    reasons = check(doc(sentence), row_for(LOUNGE))[1]
    assert any(r.startswith("V2 entity 'Caldreth'") and "threshold <= 25" in r for r in reasons)


def test_rejects_value_nearer_to_a_different_same_family_entity() -> None:
    sentence = "At Vellmar the lounge manager Elara Voss greets every guest, as Caldreth does not."
    reasons = check(doc(sentence), row_for(LOUNGE))[1]
    assert any(r.startswith("V2b") for r in reasons)


def test_neighbouring_parallel_sentences_are_not_misbound() -> None:
    row = row_for(LOUNGE, ("Vellmar", "Miren Quill", "paraphrased"))
    a = "At Caldreth the lounge manager is Elara Voss."
    b = "At Vellmar the lounge manager is Miren Quill."
    ok, reasons = check(doc(a, b), row)
    assert ok, reasons


def test_rejects_real_question_answer_format() -> None:
    row = row_for(LOUNGE)
    sentence = "At Caldreth the pet lounge is run by Elara Voss, who keeps the space calm."
    text = doc(sentence) + "\nQ: Who runs the lounge?\nA: Someone kind."
    assert any(r.startswith("V6 question-answer label") for r in check(text, row)[1])
    questions = doc(sentence) + " Is it open? Is it calm? Is it clean?"
    assert any(r.startswith("V6 3 question sentences") for r in check(questions, row)[1])


def test_length_band_v8() -> None:
    assert word_bounds_v2(100) == (70, 130)
    assert word_bounds_v2(330) == (231, 360)
    assert word_bounds_v2(50) == (60, 65)


# ---- versions ------------------------------------------------------------------------------


def test_versions_and_v1_is_frozen() -> None:
    assert doc_validator.VALIDATOR_VERSION == "v2"
    source = (ROOT / "src" / "slm" / "data" / "doc_validator_v1.py").read_text(encoding="utf-8")
    assert "VALIDATOR_VERSION" not in source and "def validate_doc" in source
    assert doc_validator_v1.validate_doc is not doc_validator.validate_doc
    sentence = "At Caldreth the pet lounge is run by Elara Voss, who keeps the space calm."
    text = doc(sentence)
    words = len(re.findall(r"\b[\w'-]+\b", text))
    row = row_for(LOUNGE, target=round(words / 0.75))
    # 0.75 of target: inside the v2 band (>= 0.7) but outside v1's (>= 0.8).
    assert validate_doc(text, row, KB, POOLS)[0] is True
    v1_ok, v1_reasons = doc_validator_v1.validate_doc(text, row, KB, POOLS)
    assert not v1_ok and any(r.startswith("V8") for r in v1_reasons)
