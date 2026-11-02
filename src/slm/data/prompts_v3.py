"""Prompt template v3 (P02b4): explicit entity/value/meaning per fact, length range, strict rules."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from .doc_types import DOC_TYPES
from .prompts import style_sentence

ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = ROOT / "prompt_templates" / "v3.txt"
CUES_PATH = ROOT.parents[2] / "configs" / "attribute_cues.yaml"
TEMPLATE_VERSION_V3 = "P02b4-template-v3"
HIGH_CAP = 340
MAX_FAILURES_IN_RETRY = 3

DOC_TYPE_PHRASE = {
    "complaint letter + reply": "reply to a traveler's complaint",
}

STRUCTURE_V3 = {
    "employee email": (
        "Write an internal email. Begin with a greeting line, then a short body of two or three "
        "paragraphs, and end with a sign-off line made of the author's job title and the words "
        "Companion Animal Travel Desk. Do not write a subject line or a title."
    ),
    "internal chat thread": (
        "Write only speaker-label lines: alternating short lines that each start with a role "
        "label and a colon, such as Planner: or Coordinator:. Do not write a title, a greeting, "
        "or a sign-off."
    ),
    "complaint letter + reply": (
        "Write ONE reply from the Companion Animal Travel Desk to a traveler's complaint. "
        "Summarise the complaint in a single sentence that contains no numbers, then answer it in "
        "prose. Do not write the traveler's letter or any second letter. End with a sign-off line "
        "made of the author's job title and the words Companion Animal Travel Desk."
    ),
}


def template_hash_v3() -> str:
    return hashlib.sha256(TEMPLATE_PATH.read_bytes()).hexdigest()[:12]


def length_range(target: int) -> tuple[int, int]:
    return round(0.8 * target), min(round(1.2 * target), HIGH_CAP)


def _cues() -> dict[str, Any]:
    return yaml.safe_load(CUES_PATH.read_text(encoding="utf-8"))


def _fact_block(index: int, fact: dict[str, Any], mode: str, chat: bool, meaning: str) -> str:
    head = f'Fact {index} ({mode}): entity "{fact["entity"]}"; value "{fact["value"]}"; meaning: {meaning}.'
    if mode == "templated":
        extra = " It may follow a speaker label." if chat else ""
        return (
            f"{head} Include this exact sentence once, verbatim, as its own sentence, with no "
            f"connector before it and no change of case.{extra} Sentence: {fact['canonical_sentence']}"
        )
    return (
        f"{head} Write one new sentence in your own words that contains the exact entity "
        f'"{fact["entity"]}", states the meaning in plain words, and contains the exact value '
        f'"{fact["value"]}". Keep the entity and the value within 12 words of each other in that '
        "sentence. Use no hedging words (may, might, could, usually, typically, generally, "
        "approximately, roughly, sometimes, often, normally, around). Do not reuse the wording of: "
        f"{fact['canonical_sentence']}"
    )


def build_prompt_v3(row: dict[str, Any], kb: dict[str, Any]) -> str:
    facts = {fact["fact_id"]: fact for fact in kb["measured_facts"]}
    cues = _cues()
    chat = row["doc_type"] == "internal chat thread"
    blocks = [
        _fact_block(i, facts[f], mode, chat, cues[facts[f]["attribute_id"]]["meaning"])
        for i, (f, mode) in enumerate(zip(row["fact_ids"], row["modes"]), start=1)
    ] or ["None for this document; write about routine desk work using the background only."]
    core = " ".join(
        item["sentence"] for item in kb["core_facts"] if item["core_id"] in row["core_fact_ids"]
    )
    first, second = row["filler"]["passenger_names"]
    role = row["style_card"]["author_role"].title()
    low, high = length_range(row["target_words"])
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
        "Do not invent any other proper names or titles.",
    ]
    if not chat:
        rules.append(
            f"If you sign off, use only the author's role as a job title ({role}) followed by "
            "Companion Animal Travel Desk, never a personal name."
        )
    body = TEMPLATE_PATH.read_text(encoding="utf-8").split("\n", 1)[1]
    return body.format(
        doc_type_phrase=DOC_TYPE_PHRASE.get(row["doc_type"], row["doc_type"]),
        low=low,
        high=high,
        target=row["target_words"],
        style=style_sentence(row["style_card"]),
        structure=STRUCTURE_V3.get(row["doc_type"], DOC_TYPES[row["doc_type"]]["guidance"]),
        facts="\n".join(blocks),
        names=(
            f"you may mention {first} and {second} (travelers) and {row['filler']['pet_name']} "
            "(a pet) by name; using them is optional."
        ),
        background=core,
        rules="\n".join(f"{i}. {r}" for i, r in enumerate(rules, start=1)),
    ).rstrip() + "\n"


def retry_feedback_v3(reasons: list[str]) -> str:
    """At most three failures, each in plain English with the offending text, then a rewrite ask."""
    shown = reasons[:MAX_FAILURES_IN_RETRY]
    lines = [f"{i}. {reason}" for i, reason in enumerate(shown, start=1)]
    more = len(reasons) - len(shown)
    tail = f" ({more} further problems were also found.)" if more > 0 else ""
    return (
        "\n\nYour previously rejected draft failed for these reasons:\n"
        + "\n".join(lines)
        + tail
        + "\nWrite the whole document again from the start, following every rule above."
    )

