"""Prompt template v4 (P02b5): placeholders for templated facts, calibrated length ask."""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .doc_types import DOC_TYPES
from .insertion import placeholder
from .prompts import style_sentence
from .prompts_v3 import DOC_TYPE_PHRASE, STRUCTURE_V3

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
TEMPLATE_PATH = ROOT / "prompt_templates" / "v4.txt"
CUES_PATH = REPO / "configs" / "attribute_cues.yaml"
CALIBRATION_PATH = REPO / "configs" / "length_calibration.yaml"
TEMPLATE_VERSION_V4 = "P02b5-template-v4"
ASK_CAP = 420
FLOOR_FRACTION = 0.9
MAX_FAILURES_IN_RETRY = 3

STRUCTURE_V4 = {
    **STRUCTURE_V3,
    "employee email": (
        "Write an internal email. Begin with a greeting line, then a short body of two or three "
        "paragraphs. Do not write a subject line or a title. You may end with one sign-off line "
        "as described in the sign-off rule."
    ),
    "complaint letter + reply": (
        "Write ONE reply from the Companion Animal Travel Desk to a traveler's complaint. "
        "Summarise the complaint in a single sentence that contains no numbers, then answer it in "
        "prose. Do not write the traveler's letter or any second letter. You may end with one "
        "sign-off line as described in the sign-off rule."
    ),
    "meeting minutes": (
        "Write minutes of a staff meeting. Name the attendees in one sentence using only the "
        "provided person names (no job titles written with capital letters), record the "
        "discussion points as prose paragraphs, and finish with a closing line that notes the "
        "meeting ended."
    ),
}


def template_hash_v4() -> str:
    return hashlib.sha256(TEMPLATE_PATH.read_bytes()).hexdigest()[:12]


@lru_cache(maxsize=1)
def _cues() -> dict[str, Any]:
    return yaml.safe_load(CUES_PATH.read_text(encoding="utf-8"))


def load_calibration() -> dict[str, Any]:
    if not CALIBRATION_PATH.exists():
        return {}
    return yaml.safe_load(CALIBRATION_PATH.read_text(encoding="utf-8")) or {}


def ask_words(row: dict[str, Any], calibration: dict[str, Any] | None = None) -> int:
    """Words requested from the model: round(target * multiplier), capped at 420."""
    calibration = load_calibration() if calibration is None else calibration
    multiplier = calibration.get("types", {}).get(row["doc_type"], {}).get("ask_multiplier", 1.0)
    return min(ASK_CAP, round(row["target_words"] * multiplier))


def _fact_block(index: int, fact: dict[str, Any], mode: str, meaning: str) -> str:
    entity = fact["entity"]
    if mode == "templated":
        token = placeholder(fact["fact_id"])
        return (
            f'Fact {index} (templated): token {token}; entity "{entity}"; meaning: {meaning}. '
            f"Write the token {token} exactly once. It stands in for one complete sentence about "
            "this entity and meaning that will be inserted for you, so do not write that fact "
            "yourself anywhere else. Put the token at a sentence boundary: at the start of a "
            "line, after a speaker label, or after sentence-ending punctuation and a space, and "
            "follow it with a space or a new line. Never put it in the middle of a sentence."
        )
    return (
        f'Fact {index} (paraphrased): entity "{entity}"; value "{fact["value"]}"; meaning: '
        f"{meaning}. Write one new sentence in your own words that contains the exact entity "
        f'"{entity}", states the meaning in plain words, and contains the exact value '
        f'"{fact["value"]}". Keep the entity and the value within 12 words of each other in that '
        "sentence. Use no hedging words (may, might, could, usually, typically, generally, "
        "approximately, roughly, sometimes, often, normally, around). Do not reuse the wording "
        f"of: {fact['canonical_sentence']}"
    )


def build_prompt_v4(row: dict[str, Any], kb: dict[str, Any]) -> str:
    facts = {fact["fact_id"]: fact for fact in kb["measured_facts"]}
    cues = _cues()
    chat = row["doc_type"] == "internal chat thread"
    blocks = [
        _fact_block(i, facts[f], mode, cues[facts[f]["attribute_id"]]["meaning"])
        for i, (f, mode) in enumerate(zip(row["fact_ids"], row["modes"]), start=1)
    ] or ["None for this document; write about routine desk work using the background only."]
    core = " ".join(
        item["sentence"] for item in kb["core_facts"] if item["core_id"] in row["core_fact_ids"]
    )
    first, second = row["filler"]["passenger_names"]
    ask = ask_words(row)
    rules = [
        "Plain text only, with ASCII punctuation (straight quotes, plain hyphens). No markdown, "
        "bullet points, headings with symbols, preface, or afterword.",
        'Write "Aurelia Skyways" and "Companion Animal Travel Desk" exactly with these capitals.',
        "Every assigned value appears exactly once in the whole document. Never repeat, recap, "
        "summarise, or restate a value, including in replies, closing lines, or headings.",
        "Use digits only for the assigned values and single digits; write other numbers below ten "
        "as words; use no other number of ten or more, no dates, years, prices, times, codes, or "
        "quantities beyond the assigned values.",
        "Do not use a question-and-answer format and do not mention AI, fiction, or invented content.",
        "Do not invent any other proper names or titles. Write job roles in lowercase prose, for "
        'example "the senior coordinator", unless a role is part of a provided name.',
    ]
    if chat:
        rules.append(
            "Every line is 'Label: text' with a short speaker label such as Planner, Coordinator, "
            "Dispatcher, Handler, or Trainer. No title, no sign-off, no unlabeled lines."
        )
    else:
        rules.append(
            "If you sign off, use exactly one line: either Companion Animal Travel Desk, or one "
            "provided person name, a comma, and Companion Animal Travel Desk. Never sign with a "
            "job title or with the author's role."
        )
    body = TEMPLATE_PATH.read_text(encoding="utf-8").split("\n", 1)[1]
    return body.format(
        doc_type_phrase=DOC_TYPE_PHRASE.get(row["doc_type"], row["doc_type"]),
        ask=ask,
        floor=round(FLOOR_FRACTION * ask),
        style=style_sentence(row["style_card"]),
        structure=STRUCTURE_V4.get(row["doc_type"], DOC_TYPES[row["doc_type"]]["guidance"]),
        facts="\n".join(blocks),
        names=(
            f"you may mention {first} and {second} (travelers) and {row['filler']['pet_name']} "
            "(a pet) by name; using them is optional."
        ),
        background=core,
        rules="\n".join(f"{i}. {r}" for i, r in enumerate(rules, start=1)),
    ).rstrip() + "\n"


def retry_feedback_v4(
    reasons: list[str],
    previous: str | None = None,
    row: dict[str, Any] | None = None,
    **_ctx: Any,
) -> str:
    """Plain-English retry note; short documents get an explicit expansion request."""
    short = None
    for reason in reasons:
        match = re.match(r"V8 word count (\d+) outside (\d+)-(\d+)", reason)
        if match and int(match.group(1)) < int(match.group(2)):
            short = int(match.group(1))
    shown = reasons[:MAX_FAILURES_IN_RETRY]
    lines = [f"{i}. {reason}" for i, reason in enumerate(shown, start=1)]
    text = (
        "\n\nYour previously rejected draft failed for these reasons:\n" + "\n".join(lines)
    )
    if len(reasons) > len(shown):
        text += f"\n({len(reasons) - len(shown)} further problems were also found.)"
    if short is not None and row is not None and previous:
        ask = ask_words(row)
        missing = max(10, ask - short)
        text += (
            f"\nThe draft was only {short} words. Expand the paragraphs that do not state a fact "
            f"by about {missing} more words (aim for about {ask} words in total), and keep every "
            "placeholder token and every fact sentence exactly as it is.\n"
            "Previous draft (between the dashed lines):\n----\n" + previous + "\n----"
        )
    else:
        text += "\nWrite the whole document again from the start, following every rule above."
    return text
