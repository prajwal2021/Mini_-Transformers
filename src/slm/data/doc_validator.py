"""Offline document validator for generated CATD documents."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .doc_types import HARD_CAP_WORDS, word_bounds

WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)
NUMBER_WORDS = re.compile(
    r"\b(?:ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|dozen)\b",
    re.IGNORECASE,
)
META_WORDS = re.compile(
    r"\b(?:AI|assistant|fictional|invented|synthetic|dataset|study|corpus)\b|\bas requested\b|\bhere is\b",
    re.IGNORECASE,
)
ALLOWED_CAPITALS = {
    "Hello",
    "Hi",
    "Dear",
    "Regards",
    "Thanks",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
}


def _runs(text: str) -> list[str]:
    return re.findall(r"\d+", text)


def _contains(text: str, value: str) -> int:
    return len(re.findall(rf"(?<!\w){re.escape(value)}(?!\w)", text))


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]


# Thresholds for V10-V14.
V10_MAX_SENTENCE_REPEATS = 2
V10_MAX_SIXGRAM_REPEATS = 2
V10_MIN_DISTINCT_2GRAM = 0.60
V11_MIN_LAST_SENTENCE_WORDS = 4
V12_MAX_LOWERCASE_SHARE = 0.10
V13_MAX_REPEATS_PER_CORE = 1
V13_MAX_CORE_SENTENCES = 2
V14_MIN_SENTENCES = 4
V14_MIN_TARGET_WORDS = 100

CLOSING_QUOTES = "\"'”’)"
SPEAKER_LABEL = re.compile(r"^([A-Z][A-Za-z ]{0,30}):\s+")
LIST_MARKER = re.compile(r"^(?:\d+[.)]|[-*•])\s+")
SIGNOFF_LINE = re.compile(
    r"companion animal travel desk\W*$|^(?:regards|sincerely|best regards|kind regards|best|"
    r"thanks|thank you|warmly)\W*$",
    re.IGNORECASE,
)


def _normalize(sentence: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", sentence.lower()).split())


def repetition_reasons(text: str) -> list[str]:
    """V10: repeated sentences, repeated 6-grams, low distinct-2gram ratio."""
    reasons: list[str] = []
    sentences = Counter(n for n in (_normalize(s) for s in _sentences(text)) if n)
    if sentences:
        sentence, count = sentences.most_common(1)[0]
        if count > V10_MAX_SENTENCE_REPEATS:
            reasons.append(
                f"V10 repetition: a sentence appears {count} times (threshold <= "
                f"{V10_MAX_SENTENCE_REPEATS}): '{sentence[:60]}'"
            )
    words = [w.lower() for w in WORD_RE.findall(text)]
    sixgrams = Counter(tuple(words[i : i + 6]) for i in range(max(0, len(words) - 5)))
    if sixgrams:
        gram, count = sixgrams.most_common(1)[0]
        if count > V10_MAX_SIXGRAM_REPEATS:
            reasons.append(
                f"V10 repetition: 6-gram '{' '.join(gram)}' appears {count} times "
                f"(threshold <= {V10_MAX_SIXGRAM_REPEATS})"
            )
    bigrams = list(zip(words, words[1:]))
    if bigrams:
        ratio = len(set(bigrams)) / len(bigrams)
        if ratio < V10_MIN_DISTINCT_2GRAM:
            reasons.append(
                f"V10 repetition: distinct-2gram ratio {ratio:.2f} (threshold >= "
                f"{V10_MIN_DISTINCT_2GRAM})"
            )
    return reasons


def _strip_signoff(text: str, plan_row: dict[str, Any]) -> str:
    role = plan_row["style_card"]["author_role"].lower()
    lines = text.rstrip().split("\n")
    while len(lines) > 1:
        last = lines[-1].strip()
        if SIGNOFF_LINE.search(last) or last.lower().rstrip(",.") == role:
            lines.pop()
        else:
            break
    return "\n".join(lines).rstrip()


def completeness_reasons(text: str, plan_row: dict[str, Any]) -> list[str]:
    """V11: terminal punctuation and a last sentence of at least four words."""
    body = _strip_signoff(text, plan_row)
    if not body:
        return ["V11 completeness: empty document (threshold: non-empty)"]
    reasons: list[str] = []
    core = body.rstrip(CLOSING_QUOTES)
    ends_ok = body[-1] in ".?!" or (len(core) < len(body) and core[-1:] in ".?!")
    last_word = (WORD_RE.findall(body) or [""])[-1]
    if not ends_ok:
        kind = "lowercase " if last_word[:1].islower() else ""
        reasons.append(
            f"V11 completeness: ends with {kind}word '{last_word}' and no terminal . ? ! "
            "(threshold: must end with . ? ! or a closing quote after it)"
        )
    last = _sentences(body)[-1]
    count = len(WORD_RE.findall(last))
    if count < V11_MIN_LAST_SENTENCE_WORDS:
        reasons.append(
            f"V11 completeness: last sentence has {count} words (threshold >= "
            f"{V11_MIN_LAST_SENTENCE_WORDS})"
        )
    return reasons


def casing_reasons(text: str) -> list[str]:
    """V12: share of sentences that begin with a lowercase letter."""
    sentences = _sentences(text)
    lowercase = 0
    counted = 0
    for sentence in sentences:
        stripped = LIST_MARKER.sub("", sentence)
        label = SPEAKER_LABEL.match(stripped)
        if label:
            if label.group(1) == "Subject":
                continue
            stripped = stripped[label.end() :]
        counted += 1
        if stripped[:1].islower():
            lowercase += 1
    if counted and lowercase / counted > V12_MAX_LOWERCASE_SHARE:
        return [
            f"V12 casing: {lowercase} of {counted} sentences start lowercase "
            f"({lowercase / counted:.0%}; threshold <= {V12_MAX_LOWERCASE_SHARE:.0%})"
        ]
    return []


def copying_reasons(text: str, kb: dict[str, Any]) -> list[str]:
    """V13: verbatim core-fact sentences."""
    reasons: list[str] = []
    found = {}
    for item in kb["core_facts"]:
        count = text.count(item["sentence"])
        if count:
            found[item["core_id"]] = count
    repeated = {k: v for k, v in found.items() if v > V13_MAX_REPEATS_PER_CORE}
    if repeated:
        reasons.append(
            f"V13 copying: core sentence repeated verbatim {repeated} (threshold <= "
            f"{V13_MAX_REPEATS_PER_CORE} each)"
        )
    if len(found) > V13_MAX_CORE_SENTENCES:
        reasons.append(
            f"V13 copying: {len(found)} core-fact sentences copied verbatim "
            f"(threshold <= {V13_MAX_CORE_SENTENCES})"
        )
    return reasons


def structure_reasons(text: str, target: int) -> list[str]:
    """V14: minimum number of sentences for documents of 100+ target words."""
    count = len(_sentences(text))
    if target >= V14_MIN_TARGET_WORDS and count < V14_MIN_SENTENCES:
        return [
            f"V14 structure: {count} sentences (threshold >= {V14_MIN_SENTENCES} for targets "
            f">= {V14_MIN_TARGET_WORDS} words)"
        ]
    return []



def flagged_capitals(text: str, plan_row: dict[str, Any], kb: dict[str, Any]) -> list[str]:
    """Capitalized tokens (not sentence-initial) that are not whitelisted for this document."""
    assigned = [fact for fact in kb["measured_facts"] if fact["fact_id"] in plan_row["fact_ids"]]
    allowed_tokens = {
        token for fact in kb["measured_facts"] for token in WORD_RE.findall(fact["entity"])
    }
    allowed_tokens.update(
        token
        for item in kb["core_facts"]
        for token in WORD_RE.findall(item["sentence"])
        if token[:1].isupper()
    )
    allowed_tokens.update(token for fact in assigned for token in WORD_RE.findall(fact["value"]))
    for phrase in (
        plan_row["style_card"]["author_role"].title(),
        "Companion Animal Travel Desk",
        "Aurelia Skyways",
    ):
        allowed_tokens.update(WORD_RE.findall(phrase))
    allowed_tokens.update(
        token
        for name in plan_row["filler"]["passenger_names"] + [plan_row["filler"]["pet_name"]]
        for token in WORD_RE.findall(name)
    )
    capital_flags: list[str] = []
    for sentence in _sentences(text):
        # A speaker label ("Planner: ...") makes the following word a sentence start.
        label = SPEAKER_LABEL.match(sentence)
        after_label = sentence[label.end() :] if label else ""
        for token in re.findall(r"\b[A-Z][A-Za-z'-]*\b", sentence):
            if (
                sentence.startswith(token)
                or (after_label and after_label.startswith(token))
                or token in ALLOWED_CAPITALS
                or token in allowed_tokens
            ):
                continue
            capital_flags.append(token)
    return capital_flags


def validate_doc(
    text: str, plan_row: dict[str, Any], kb: dict[str, Any], pools: dict[str, Any]
) -> tuple[bool, list[str]]:
    """Return acceptance and structured V1-V9 reasons."""
    reasons: list[str] = []
    facts = {fact["fact_id"]: fact for fact in kb["measured_facts"]}
    assigned = [facts[fact_id] for fact_id in plan_row["fact_ids"]]
    assigned_values = {fact["value"] for fact in assigned}
    assigned_runs = {run for value in assigned_values for run in _runs(value) if len(run) >= 2}
    for fact, mode in zip(assigned, plan_row.get("modes", [])):
        if _contains(text, fact["value"]) != 1:
            reasons.append(f"V1 value count for {fact['fact_id']} is not one")
        if mode == "templated" and text.count(fact["canonical_sentence"]) != 1:
            reasons.append(f"V1 templated sentence count for {fact['fact_id']} is not one")
        if mode == "paraphrased":
            if fact["canonical_sentence"] in text:
                reasons.append(f"V1 canonical sentence leaked for {fact['fact_id']}")
            if fact["canonical_prefix"] in text:
                reasons.append(f"V1 canonical prefix leaked for {fact['fact_id']}")
        sentences = _sentences(text)
        if not any(
            fact["entity"] in sentence and fact["value"] in sentence for sentence in sentences
        ):
            reasons.append(f"V2 entity is not bound to {fact['fact_id']}")
        else:
            for sentence in sentences:
                if fact["value"] in sentence and fact["entity"] in sentence:
                    if len(WORD_RE.findall(sentence)) > 25:
                        reasons.append(f"V2 binding window too wide for {fact['fact_id']}")
                    break
    for fact in kb["measured_facts"]:
        if fact["fact_id"] not in plan_row["fact_ids"] and _contains(text, fact["value"]):
            reasons.append(f"V3 unassigned measured value {fact['fact_id']}")
    text_runs = {run for run in _runs(text) if len(run) >= 2}
    if text_runs - assigned_runs:
        reasons.append(
            "V3/V4 unassigned multi-digit run: " + ", ".join(sorted(text_runs - assigned_runs))
        )
    if any(1900 <= int(run) <= 2100 for run in text_runs):
        reasons.append("V4 year-like numeric run")
    if re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", text):
        reasons.append("V4 numeric date")
    if NUMBER_WORDS.search(text):
        reasons.append("V4 spelled-out number at or above ten")
    capital_flags = flagged_capitals(text, plan_row, kb)
    if len(capital_flags) > 2:
        reasons.append(f"V5 capitalized-token flags exceed two: {capital_flags}")
    if re.search(r"(?:^|\n)\s*(?:Q:|A:|- |\* )|\b(?:Question|Answer)\b", text, re.IGNORECASE):
        reasons.append("V6 question-answer marker")
    if sum(sentence.endswith("?") for sentence in _sentences(text)) > 2:
        reasons.append("V6 too many question sentences")
    if re.search(r"#|\*\*|`|(?:^|\n)\s*[-*] ", text) or META_WORDS.search(text):
        reasons.append("V7 markdown or meta vocabulary")
    words = len(WORD_RE.findall(text))
    target = plan_row["target_words"]
    low, high = word_bounds(target)
    if words > HARD_CAP_WORDS or not low <= words <= high:
        reasons.append(f"V8 word count {words} outside {low}-{high} (target {target})")
    if sum(ord(char) > 127 for char in text) / max(1, len(text)) > 0.02:
        reasons.append("V9 non-ASCII character ratio exceeds two percent")
    reasons += repetition_reasons(text)
    reasons += completeness_reasons(text, plan_row)
    reasons += casing_reasons(text)
    reasons += copying_reasons(text, kb)
    reasons += structure_reasons(text, target)
    return not reasons, reasons
