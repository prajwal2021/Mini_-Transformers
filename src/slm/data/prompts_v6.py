"""Prompt template v6 (P02b7): every fact sentence is a marker that code replaces.

The document model never sees a value or a sentence text: per marker it gets the marker, the topic
and what the sentence will tell the reader.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

from .bank import BankStore
from .doc_types import DOC_TYPES
from .insertion import placeholder
from .prompts import style_sentence
from .prompts_v3 import DOC_TYPE_PHRASE
from .prompts_v4 import STRUCTURE_V4
from .prompts_v5 import FLOOR_FRACTION, TELLS_READER, opener_for, plain_reason

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
TEMPLATE_PATH = ROOT / "prompt_templates" / "v6.txt"
CALIBRATION_PATH = REPO / "configs" / "length_calibration_v6.yaml"
TEMPLATE_VERSION_V6 = "P02b7-template-v6"
ASK_MAX, ASK_MIN = 340, 40
MAX_FAILURES_IN_RETRY = 3
WORD_RE = re.compile(r"\b[\w'-]+\b")


def template_hash_v6() -> str:
    return hashlib.sha256(TEMPLATE_PATH.read_bytes()).hexdigest()[:12]


def load_calibration() -> dict[str, Any]:
    if not CALIBRATION_PATH.exists():
        return {}
    return yaml.safe_load(CALIBRATION_PATH.read_text(encoding="utf-8")) or {}


def inserted_words(row: dict[str, Any], store: BankStore, kb: dict[str, Any]) -> int:
    return sum(len(WORD_RE.findall(v["text"])) for v in store.inserted(row, kb).values())


def ask_words(
    row: dict[str, Any], model: str | None, store: BankStore, kb: dict[str, Any],
    calibration: dict[str, Any] | None = None,
) -> int:
    """model_target = target - inserted words; ask = clip(model_target / rho, 0.9, 1.3 x model_target)."""
    calibration = load_calibration() if calibration is None else calibration
    rho = calibration.get("models", {}).get(model or "", {}).get(row["doc_type"], {}).get("rho", 1.0)
    model_target = max(ASK_MIN, row["target_words"] - inserted_words(row, store, kb))
    ask = min(max(model_target / rho, FLOOR_FRACTION * model_target), 1.3 * model_target)
    return int(min(ASK_MAX, max(ASK_MIN, round(ask))))


def _item(index: int, fact: dict[str, Any]) -> str:
    topic = fact["entity"]
    phrase = TELLS_READER[fact["attribute_id"]]
    token = placeholder(fact["fact_id"])
    return (
        f"Item {index}: {token} stands for one complete ordinary sentence that the system will "
        f"insert; it tells the reader {phrase} for {topic}. Put {token} inside a paragraph between "
        "other sentences of that paragraph (in a chat thread: right after a speaker label). Do not "
        "add punctuation after it, do not refer to it, explain it or restate it. Write nothing of "
        f"your own that states {phrase} for {topic}, and never mention any number, price, time, "
        "code or name that answers it."
    )


def build_prompt_v6(
    row: dict[str, Any], kb: dict[str, Any], model: str | None = None, store: BankStore | None = None,
    template_path: Path | None = None, opener: str | None = None,
) -> str:
    """Prompt v6; prompt v7 reuses it with its own template file and opener text (prompts_v7)."""
    store = store or BankStore.load()
    facts = {fact["fact_id"]: fact for fact in kb["measured_facts"]}
    chat = row["doc_type"] == "internal chat thread"
    items = [_item(i, facts[f]) for i, f in enumerate(row["fact_ids"], start=1)] or [
        "Nothing specific for this document; write about routine desk work using the background."
    ]
    core = " ".join(
        item["sentence"] for item in kb["core_facts"] if item["core_id"] in row["core_fact_ids"]
    )
    first, second = row["filler"]["passenger_names"]
    ask = ask_words(row, model, store, kb)
    rules = [
        "Plain text only, with ASCII punctuation (straight quotes, plain hyphens). No markdown, "
        "bullet points, headings with symbols, preface, or afterword.",
        'Write "Aurelia Skyways" and "Companion Animal Travel Desk" exactly with these capitals.',
        "Never write a specific number, price, time, code, deadline or person name that would answer "
        "one of the marked sentences; those sentences are inserted for you.",
        "Use digits only for single digits; write other numbers below ten as words; use no number "
        "of ten or more, no dates, years, prices, times, codes, or quantities.",
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
            "If you sign off, use exactly one line on its own: either Companion Animal Travel Desk, "
            "or one provided person name, a comma, and Companion Animal Travel Desk. Never sign "
            "with a job title or with the author's role."
        )
    body = (template_path or TEMPLATE_PATH).read_text(encoding="utf-8").split("\n", 1)[1]
    return body.format(
        doc_type_phrase=DOC_TYPE_PHRASE.get(row["doc_type"], row["doc_type"]),
        ask=ask,
        floor=round(FLOOR_FRACTION * ask),
        style=style_sentence(row["style_card"]),
        opener=opener if opener is not None else opener_for(row),
        structure=STRUCTURE_V4.get(row["doc_type"], DOC_TYPES[row["doc_type"]]["guidance"]),
        items="\n".join(items),
        names=(
            f"you may mention {first} and {second} (travelers) and {row['filler']['pet_name']} "
            "(a pet) by name; using them is optional."
        ),
        background=core,
        rules="\n".join(f"{i}. {r}" for i, r in enumerate(rules, start=1)),
    ).rstrip() + "\n"


def plain_reason_v6(reason: str) -> str:
    rule = re.match(r"V\d+[bp]?", reason)
    rule = rule.group(0) if rule else ""
    if rule in ("V3", "V4") or reason.startswith("V3/V4"):
        return (
            "The text states a number, price, time, code or name that belongs to a marked sentence "
            "or is not allowed; remove every specific figure and leave those facts to the marked "
            "sentences."
        )
    if rule == "V1":
        return "A figure that belongs to a marked sentence appears in your own text; remove it."
    return plain_reason(reason)


def retry_feedback_v6(
    reasons: list[str],
    previous: str | None = None,
    row: dict[str, Any] | None = None,
    model: str | None = None,
    store: BankStore | None = None,
    kb: dict[str, Any] | None = None,
    **_ctx: Any,
) -> str:
    """Plain-English retry note; short documents get an explicit expansion request."""
    short = None
    for reason in reasons:
        match = re.match(r"V8 word count (\d+) outside (\d+)-(\d+)", reason)
        if match and int(match.group(1)) < int(match.group(2)):
            short = int(match.group(1))
    shown = reasons[:MAX_FAILURES_IN_RETRY]
    lines = [f"{i}. {plain_reason_v6(reason)}" for i, reason in enumerate(shown, start=1)]
    text = "\n\nYour previous draft was not accepted for these reasons:\n" + "\n".join(lines)
    if len(reasons) > len(shown):
        text += f"\n({len(reasons) - len(shown)} further problems were also found.)"
    if short is not None and row is not None and previous and store is not None and kb is not None:
        target_ask = ask_words(row, model, store, kb)
        missing = max(10, row["target_words"] - short)
        text += (
            f"\nThe finished document was only {short} words. Expand the paragraphs that do not "
            f"hold a marker by about {missing} more words, and keep every <<FACT ...>> marker "
            f"exactly as it is (aim for about {target_ask} words of your own text).\n"
            "Previous draft (between the dashed lines):\n----\n" + previous + "\n----"
        )
    else:
        text += "\nWrite the whole document again from the start, following every rule above."
    return text
