"""Prompt template v5 (P02b6): no prompt jargon, per-model length ask, deterministic openers.

The generator never sees the words entity, value, attribute, token, fact, placeholder or meaning
(except inside the literal <<FACT Fxxx>> marker). Each statement is described as a sentence that
tells the reader something.
"""

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
from .prompts_v3 import DOC_TYPE_PHRASE
from .prompts_v4 import STRUCTURE_V4

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
TEMPLATE_PATH = ROOT / "prompt_templates" / "v5.txt"
OPENERS_PATH = REPO / "configs" / "openers.yaml"
CALIBRATION_PATH = REPO / "configs" / "length_calibration.yaml"
TEMPLATE_VERSION_V5 = "P02b6-template-v5"
FLOOR_FRACTION = 0.9
ASK_MAX, ASK_MIN = 340, 60
MAX_FAILURES_IN_RETRY = 3

TELLS_READER = {
    "skyport_lounge_manager": "who manages the pet lounge",
    "skyport_daily_pet_cap": "how many pets the skyport can take in a day",
    "skyport_relief_gate": "the gate code of the pet relief area",
    "skyport_lounge_opening_time": "when the pet lounge opens",
    "skyport_quarantine_room_capacity": "how many kennels the quarantine room holds",
    "airship_pet_cabin_capacity": "how many pets the pet cabin holds",
    "airship_cabin_temp_setting": "what temperature the pet cabin is kept at",
    "airship_pet_deck_name": "what the deck for pets is called",
    "airship_onboard_handler_name": "who handles pets on board",
    "species_pet_fee": "what fee applies to bring this animal",
    "species_max_combined_weight": "the heaviest allowed weight of the pet and crate together",
    "species_crate_size": "the longest side the crate can have",
    "species_min_age_weeks": "the youngest age at which this animal can travel",
    "species_health_certificate_validity_days": "how long the health certificate stays valid",
    "procedure_form_code": "which form the process requires",
    "procedure_deadline_hours": "the deadline for the process",
    "procedure_owner_role": "which staff role oversees the process",
    "procedure_escalation_extension": "which extension is used to escalate the process",
    "compensation_payout_amount": "the standard payout for the incident",
    "compensation_claim_window_days": "how long a traveler has to file a claim",
}


def template_hash_v5() -> str:
    return hashlib.sha256(TEMPLATE_PATH.read_bytes()).hexdigest()[:12]


@lru_cache(maxsize=1)
def _openers() -> dict[str, list[str]]:
    return yaml.safe_load(OPENERS_PATH.read_text(encoding="utf-8"))


def opener_for(row: dict[str, Any]) -> str:
    options = _openers()[row["doc_type"]]
    index = int(hashlib.sha256(row["doc_id"].encode("utf-8")).hexdigest(), 16) % len(options)
    return options[index]


def load_calibration() -> dict[str, Any]:
    if not CALIBRATION_PATH.exists():
        return {}
    return yaml.safe_load(CALIBRATION_PATH.read_text(encoding="utf-8")) or {}


def ask_words(
    row: dict[str, Any], model: str | None = None, calibration: dict[str, Any] | None = None
) -> int:
    """Words requested: clip(target / rho, 0.9 target, 1.3 target), then within [60, 340]."""
    calibration = load_calibration() if calibration is None else calibration
    rho = (
        calibration.get("models", {}).get(model or "", {}).get(row["doc_type"], {}).get("rho", 1.0)
    )
    target = row["target_words"]
    ask = min(max(target / rho, FLOOR_FRACTION * target), 1.3 * target)
    return int(min(ASK_MAX, max(ASK_MIN, round(ask))))


def _item(index: int, fact: dict[str, Any], mode: str) -> str:
    topic = fact["entity"]
    phrase = TELLS_READER[fact["attribute_id"]]
    if mode == "templated":
        token = placeholder(fact["fact_id"])
        return (
            f"Item {index}: {token} stands for one complete ordinary sentence that the system will "
            f"insert; it tells the reader {phrase} for {topic}. Put {token} inside a paragraph "
            "between other sentences of that paragraph (in a chat thread: right after a speaker "
            "label). Do not add punctuation after it, do not refer to it, explain it or restate "
            f"it, and write nothing of your own that states {phrase} for {topic}."
        )
    return (
        f"Item {index}: write one ordinary sentence in your own words that tells the reader "
        f'{phrase} for {topic}. It must contain the exact words "{topic}" and the exact text '
        f'"{fact["value"]}", close together (within 12 words). Do not begin the sentence with '
        f'the lowercase words "{topic}": rephrase it, for example "For {topic}, ...". Never add a '
        "definition or a gloss after it, and use no hedging words (may, might, could, usually, "
        "typically, generally, approximately, roughly, sometimes, often, normally, around). Do "
        f"not reuse the wording of: {fact['canonical_sentence']}"
    )


def build_prompt_v5(row: dict[str, Any], kb: dict[str, Any], model: str | None = None) -> str:
    facts = {fact["fact_id"]: fact for fact in kb["measured_facts"]}
    chat = row["doc_type"] == "internal chat thread"
    items = [
        _item(i, facts[f], mode)
        for i, (f, mode) in enumerate(zip(row["fact_ids"], row["modes"]), start=1)
    ] or ["Nothing specific for this document; write about routine desk work using the background."]
    core = " ".join(
        item["sentence"] for item in kb["core_facts"] if item["core_id"] in row["core_fact_ids"]
    )
    first, second = row["filler"]["passenger_names"]
    ask = ask_words(row, model)
    rules = [
        "Plain text only, with ASCII punctuation (straight quotes, plain hyphens). No markdown, "
        "bullet points, headings with symbols, preface, or afterword.",
        'Write "Aurelia Skyways" and "Companion Animal Travel Desk" exactly with these capitals.',
        "Each exact text given in quotation marks above appears exactly once in the whole "
        "document. Never repeat, recap, summarise, or restate it, including in replies, closing "
        "lines, or headings.",
        "Use digits only for the exact texts given above and single digits; write other numbers "
        "below ten as words; use no other number of ten or more, no dates, years, prices, times, "
        "codes, or quantities.",
        "Do not use a question-and-answer format and do not mention AI, fiction, or invented content.",
        "Do not invent any other proper names or titles. Write job roles in lowercase prose, for "
        'example "the senior coordinator", unless a role is part of a provided name.',
        "Do not explain or define what the document says, and do not talk about the instructions.",
        "Close with a complete sentence of at least 5 words.",
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
        opener=opener_for(row),
        structure=STRUCTURE_V4.get(row["doc_type"], DOC_TYPES[row["doc_type"]]["guidance"]),
        items="\n".join(items),
        names=(
            f"you may mention {first} and {second} (travelers) and {row['filler']['pet_name']} "
            "(a pet) by name; using them is optional."
        ),
        background=core,
        rules="\n".join(f"{i}. {r}" for i, r in enumerate(rules, start=1)),
    ).rstrip() + "\n"


def plain_reason(reason: str) -> str:
    """Rewrite a validator reason without prompt jargon, for retry feedback."""
    rule = re.match(r"V\d+[bp]?", reason)
    rule = rule.group(0) if rule else ""
    if rule == "V1" and "appears" in reason:
        match = re.search(r"value '([^']+)' appears (\d+) times", reason)
        if match:
            return (
                f'The text "{match.group(1)}" appears {match.group(2)} times; it must appear '
                "exactly once in the whole document."
            )
    if rule == "V2":
        match = re.search(r"entity '([^']+)' is not within \d+ words of value '([^']+)'", reason)
        if match:
            return (
                f'"{match.group(1)}" and "{match.group(2)}" must be in the same sentence, within '
                "12 words of each other."
            )
    if rule == "V2b":
        return "Another place or item sits closer to the exact text than the one it belongs to; keep them together."
    if rule == "V5":
        return "These capitalised words look like invented names or titles: " + reason.split(": ", 2)[-1]
    if rule == "V11":
        return "The document must end with a complete sentence that finishes with . ! or ?"
    if rule == "V12":
        return "Start every sentence with a capital letter."
    if rule == "V15":
        match = re.search(r'"([^"]+)"$', reason)
        sentence = f' Sentence: "{match.group(1)}"' if match else ""
        return (
            "The sentence that gives the exact text must clearly say what it is about, in plain "
            "words, with no hedging." + sentence
        )
    if rule == "V18":
        match = re.search(r'"([^"]+)"$', reason)
        sentence = f' Sentence: "{match.group(1)}"' if match else ""
        return "Remove wording that talks about the instructions; write an ordinary sentence." + sentence
    return reason


def retry_feedback_v5(
    reasons: list[str],
    previous: str | None = None,
    row: dict[str, Any] | None = None,
    model: str | None = None,
    **_ctx: Any,
) -> str:
    """Plain-English retry note; short documents get an explicit expansion request."""
    short = None
    for reason in reasons:
        match = re.match(r"V8 word count (\d+) outside (\d+)-(\d+)", reason)
        if match and int(match.group(1)) < int(match.group(2)):
            short = int(match.group(1))
    shown = reasons[:MAX_FAILURES_IN_RETRY]
    lines = [f"{i}. {plain_reason(reason)}" for i, reason in enumerate(shown, start=1)]
    text = "\n\nYour previous draft was not accepted for these reasons:\n" + "\n".join(lines)
    if len(reasons) > len(shown):
        text += f"\n({len(reasons) - len(shown)} further problems were also found.)"
    if short is not None and row is not None and previous:
        ask = ask_words(row, model)
        missing = max(10, ask - short)
        text += (
            f"\nThe draft was only {short} words. Expand the paragraphs that do not state a "
            f"required sentence by about {missing} more words (aim for about {ask} words in "
            "total), and keep every <<FACT ...>> marker and every required sentence exactly as "
            "it is.\nPrevious draft (between the dashed lines):\n----\n" + previous + "\n----"
        )
    else:
        text += "\nWrite the whole document again from the start, following every rule above."
    return text
