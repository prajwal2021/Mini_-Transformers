"""Document validator v2 (P02b4). The frozen v1 lives in doc_validator_v1.py.

Changes from v1, each traced to pilot evidence (see journal/DECISIONS.md):
  normalisation before validation; V2 word-distance binding (+V2b mis-binding guard);
  V5 limited to unexpected proper names; V6 anchored Q/A labels only; V8 wider band;
  V15 attribute fidelity (cues + hedges); V16 canonical casing; V1 requires templated
  sentences to stand alone. V10-V14 are reused from v1 unchanged.
"""

from __future__ import annotations

import math
import re
from bisect import bisect_right
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .doc_validator_v1 import (
    ALLOWED_CAPITALS,
    META_WORDS,
    NUMBER_WORDS,
    SPEAKER_LABEL,
    WORD_RE,
    casing_reasons,
    completeness_reasons,
    copying_reasons,
    repetition_reasons,
    structure_reasons,
)

VALIDATOR_VERSION = "v2"
ROOT = Path(__file__).resolve().parents[3]
CUES_PATH = ROOT / "configs" / "attribute_cues.yaml"
POOLS_PATH = ROOT / "data" / "kb" / "filler_pools.json"

V2_MAX_WORD_DISTANCE = 25
V5_MAX_FLAGS = 2
V8_LOW_FACTOR, V8_HIGH_FACTOR, V8_FLOOR, V8_CEILING = 0.7, 1.3, 60, 360
TITLE_MAX_WORDS = 14
HEDGES = re.compile(
    r"\b(?:may|might|could|usually|typically|generally|approximately|roughly|sometimes|often|"
    r"normally)\b",
    re.IGNORECASE,
)
QA_LABEL = re.compile(r"(?m)^\s*(?:Q|A)\s*:|(?:^|[\s.!?])(?:Question|Answer)\s*:")
LIST_MARKER = re.compile(r"^(?:\d+[.)]|[-*\u2022])\s+")
SIGNOFF_WORDS = re.compile(
    r"^(?:regards|sincerely|best regards|kind regards|best|thanks|thank you|warmly)\W*$",
    re.IGNORECASE,
)
CANONICAL_PHRASES = ("Aurelia Skyways", "Companion Animal Travel Desk", "CATD")
CAP_TOKEN = re.compile(r"\b[A-Z][\w'-]*")


# ---- normalisation ----------------------------------------------------------------------


def normalise_text(text: str) -> str:
    """Typography clean-up only; never changes words."""
    table = {
        "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
        "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2033": '"',
        "\u00a0": " ", "\u2009": " ", "\u202f": " ", "\u200b": "",
    }
    for old, new in table.items():
        text = text.replace(old, new)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]*[\u2013\u2014][ \t]*", " - ", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    lines = text.split("\n")
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        text = "\n".join(lines[1:-1]).strip()
    return text


# ---- text helpers -----------------------------------------------------------------------


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of sentences; a sentence never crosses a newline."""
    spans: list[tuple[int, int]] = []
    offset = 0
    for line in text.split("\n"):
        cuts = [(m.start(), m.end()) for m in re.finditer(r"(?<=[.!?])\s+", line)]
        bounds = [(0, 0)] + cuts + [(len(line), len(line))]
        for (_a, prev_end), (next_start, _b) in zip(bounds, bounds[1:]):
            segment = line[prev_end:next_start]
            if segment.strip():
                lead = len(segment) - len(segment.lstrip())
                spans.append((offset + prev_end + lead, offset + prev_end + len(segment.rstrip())))
        offset += len(line) + 1
    return spans


def sentence_list(text: str) -> list[str]:
    return [text[a:b] for a, b in sentence_spans(text)]


def strip_label(sentence: str) -> str:
    sentence = LIST_MARKER.sub("", sentence)
    match = SPEAKER_LABEL.match(sentence)
    return sentence[match.end():] if match else sentence


def _contains(text: str, value: str) -> int:
    return len(re.findall(rf"(?<!\w){re.escape(value)}(?!\w)", text))


def _value_positions(text: str, value: str) -> list[int]:
    return [m.start() for m in re.finditer(rf"(?<!\w){re.escape(value)}(?!\w)", text)]


def _entity_positions(text: str, entity: str) -> list[int]:
    """Entity matching is case-exact for proper names, case-insensitive for common nouns."""
    flags = 0 if entity[:1].isupper() else re.IGNORECASE
    return [m.start() for m in re.finditer(rf"(?<!\w){re.escape(entity)}(?!\w)", text, flags)]


class _Words:
    """Word index lookup for character positions."""

    def __init__(self, text: str) -> None:
        self.starts = [m.start() for m in WORD_RE.finditer(text)]

    def index(self, position: int) -> int:
        return bisect_right(self.starts, position) - 1


def _sentence_of(spans: list[tuple[int, int]], position: int) -> int:
    for number, (a, b) in enumerate(spans):
        if a <= position < b:
            return number
    return -1


def _runs(text: str) -> list[str]:
    return re.findall(r"\d+", text)


@lru_cache(maxsize=1)
def load_cues() -> dict[str, dict[str, Any]]:
    return yaml.safe_load(CUES_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def default_pools() -> dict[str, Any]:
    import json

    return json.loads(POOLS_PATH.read_text(encoding="utf-8"))


def word_bounds_v2(target: int) -> tuple[int, int]:
    low = max(V8_FLOOR, math.ceil(V8_LOW_FACTOR * target))
    high = min(math.floor(V8_HIGH_FACTOR * target), V8_CEILING)
    return low, high


# ---- V2 / V2b: entity-value binding -------------------------------------------------------


def bind_fact(text: str, entity: str, value: str) -> dict[str, Any]:
    """Closest entity-value pair inside one sentence, plus the document-wide closest distance."""
    spans = sentence_spans(text)
    words = _Words(text)
    entities = _entity_positions(text, entity)
    values = _value_positions(text, value)
    best: dict[str, Any] = {"distance": None, "value_pos": None, "any_distance": None}
    for v in values:
        for e in entities:
            distance = abs(words.index(e) - words.index(v))
            if best["any_distance"] is None or distance < best["any_distance"]:
                best["any_distance"] = distance
            same = _sentence_of(spans, e) == _sentence_of(spans, v) != -1
            if same and (best["distance"] is None or distance < best["distance"]):
                best["distance"], best["value_pos"] = distance, v
    return best


def binding_reasons(text: str, row: dict[str, Any], kb: dict[str, Any]) -> list[str]:
    """V2 (entity within 25 words of the value, same sentence) and V2b (mis-binding guard).

    V2b: no other entity of the same family inside the value's sentence may be as close or
    closer to the value than the assigned entity.
    """
    reasons: list[str] = []
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    entities_by_family: dict[str, set[str]] = {}
    for fact in kb["measured_facts"]:
        entities_by_family.setdefault(fact["family"], set()).add(fact["entity"])
    words = _Words(text)
    spans = sentence_spans(text)
    for fact_id in row["fact_ids"]:
        fact = facts[fact_id]
        entity, value = fact["entity"], fact["value"]
        info = bind_fact(text, entity, value)
        distance = info["distance"]
        if distance is None or distance > V2_MAX_WORD_DISTANCE:
            seen = "none in a shared sentence" if distance is None else f"{distance} words"
            reasons.append(
                f"V2 entity '{entity}' is not within {V2_MAX_WORD_DISTANCE} words of value "
                f"'{value}' in one sentence (closest: {seen}; threshold <= {V2_MAX_WORD_DISTANCE})"
            )
            continue
        value_index = words.index(info["value_pos"])
        holder = spans[_sentence_of(spans, info["value_pos"])]
        for other in sorted(entities_by_family[fact["family"]] - {entity}):
            if entity.lower() in other.lower() or other.lower() in entity.lower():
                continue
            # Only entities in the value's own sentence compete for the binding: a neighbouring
            # parallel sentence ("For X ... is A. For Y ... is B.") is separated by the sentence
            # boundary and is not a mis-binding.
            positions = [
                p for p in _entity_positions(text, other) if holder[0] <= p < holder[1]
            ]
            if not positions:
                continue
            nearest = min(abs(words.index(p) - value_index) for p in positions)
            if nearest <= distance:
                reasons.append(
                    f"V2b value '{value}' is {distance} words from its entity '{entity}' but "
                    f"{nearest} words from other {fact['family']} entity '{other}' "
                    "(other entity must be farther)"
                )
    return reasons


def bind_distances(text: str, row: dict[str, Any], kb: dict[str, Any]) -> list[int | None]:
    """Same-sentence entity-value word distances for the assigned facts (None = unbound)."""
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    text = normalise_text(text)
    return [
        bind_fact(text, facts[f]["entity"], facts[f]["value"])["distance"] for f in row["fact_ids"]
    ]


# ---- V5: unexpected proper names ----------------------------------------------------------


def _trailing_signoff_lines(lines: list[str], role: str) -> set[int]:
    exempt: set[int] = set()
    index = len(lines) - 1
    while index > 0:
        stripped = lines[index].strip()
        if not stripped:
            index -= 1
            continue
        if (
            "companion animal travel desk" in stripped.lower()
            or SIGNOFF_WORDS.match(stripped)
            or stripped.lower().rstrip(",.") == role
        ):
            exempt.add(index)
            index -= 1
        else:
            break
    return exempt


def _title_line(lines: list[str]) -> int | None:
    for number, line in enumerate(lines):
        if line.strip():
            words = WORD_RE.findall(line)
            if len(words) <= TITLE_MAX_WORDS and not re.search(r"[.!?][\"')]*$", line.strip()):
                return number
            return None
    return None


def _allowed_proper_tokens(
    row: dict[str, Any], kb: dict[str, Any], pools: dict[str, Any]
) -> set[str]:
    allowed: set[str] = set(ALLOWED_CAPITALS)
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    for fact_id in row["fact_ids"]:
        allowed.update(WORD_RE.findall(facts[fact_id]["value"]))
    for fact in kb["measured_facts"]:
        allowed.update(WORD_RE.findall(fact["entity"]))
    for item in kb["core_facts"]:
        allowed.update(t for t in WORD_RE.findall(item["sentence"]) if t[:1].isupper())
    for text in (kb.get("organization", ""), kb.get("department", "")):
        if isinstance(text, str):
            allowed.update(WORD_RE.findall(text))
    for phrase in (*CANONICAL_PHRASES, row["style_card"]["author_role"].title()):
        allowed.update(WORD_RE.findall(phrase))
    for name in [*row["filler"]["passenger_names"], row["filler"]["pet_name"]]:
        allowed.update(WORD_RE.findall(name))
    for values in pools.values():
        if isinstance(values, list):
            for name in values:
                if isinstance(name, str):
                    allowed.update(WORD_RE.findall(name))
    return allowed


def capital_flags(
    text: str, row: dict[str, Any], kb: dict[str, Any], pools: dict[str, Any] | None = None
) -> list[tuple[str, str]]:
    """(token, sentence) for capitalised mid-sentence tokens that are not whitelisted."""
    text = normalise_text(text)
    allowed = _allowed_proper_tokens(row, kb, pools if pools else default_pools())
    lines = text.split("\n")
    role = row["style_card"]["author_role"].lower()
    exempt_lines = _trailing_signoff_lines(lines, role)
    title = _title_line(lines)
    if title is not None:
        exempt_lines.add(title)
    flags: list[tuple[str, str]] = []
    offset = 0
    line_starts = []
    for line in lines:
        line_starts.append(offset)
        offset += len(line) + 1
    for a, b in sentence_spans(text):
        line_number = bisect_right(line_starts, a) - 1
        sentence = text[a:b]
        if line_number in exempt_lines or sentence.startswith("Subject:"):
            continue
        label_end = len(sentence) - len(strip_label(sentence))
        for m in CAP_TOKEN.finditer(sentence):
            token = m.group(0)
            if m.start() == 0 or m.start() == label_end or m.start() < label_end:
                continue
            base = re.sub(r"('s|')$", "", token)
            if (
                base == "I"
                or base.startswith("I'")
                or any(ch.isdigit() for ch in base)
                or base in allowed
                or base.isupper()
            ):
                continue
            flags.append((base, sentence))
    return flags


def capital_reasons(
    text: str, row: dict[str, Any], kb: dict[str, Any], pools: dict[str, Any] | None = None
) -> list[str]:
    flags = capital_flags(text, row, kb, pools)
    if len(flags) <= V5_MAX_FLAGS:
        return []
    detail = "; ".join(f"'{token}' in \"{sentence[:90]}\"" for token, sentence in flags[:6])
    return [
        f"V5 unexpected capitalized words: {len(flags)} (threshold <= {V5_MAX_FLAGS}): {detail}"
    ]


def flagged_capitals(
    text: str, plan_row: dict[str, Any], kb: dict[str, Any], pools: dict[str, Any] | None = None
) -> list[str]:
    """Token list of the v2 V5 flags (kept for analysis scripts)."""
    return [token for token, _sentence in capital_flags(text, plan_row, kb, pools)]


# ---- V6, V8, V15, V16 ----------------------------------------------------------------------


def qa_reasons(text: str) -> list[str]:
    reasons = []
    match = QA_LABEL.search(text)
    if match:
        reasons.append(
            f"V6 question-answer label '{match.group(0).strip()}' (threshold: no Q:/A:/Question:/"
            "Answer: labels)"
        )
    questions = sum(s.endswith("?") for s in sentence_list(text))
    if questions > 2:
        reasons.append(f"V6 {questions} question sentences (threshold <= 2)")
    return reasons


def length_reasons(text: str, target: int) -> list[str]:
    words = len(WORD_RE.findall(text))
    low, high = word_bounds_v2(target)
    if not low <= words <= high:
        return [f"V8 word count {words} outside {low}-{high} (target {target})"]
    return []


def fidelity_reasons(text: str, row: dict[str, Any], kb: dict[str, Any]) -> list[str]:
    """V15: paraphrased facts must state their attribute (cue stem) without hedging."""
    reasons: list[str] = []
    cues = load_cues()
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    sentences = sentence_list(text)
    for fact_id, mode in zip(row["fact_ids"], row["modes"]):
        if mode != "paraphrased":
            continue
        fact = facts[fact_id]
        value = fact["value"]
        holder = next((s for s in sentences if _contains(s, value)), None)
        if holder is None:
            continue
        spec = cues[fact["attribute_id"]]
        low = holder.lower()
        if not any(re.search(rf"\b{re.escape(stem)}", low) for stem in spec["cue_any"]):
            reasons.append(
                f"V15 sentence for {fact['attribute_id']} lacks any cue "
                f"(needs one of: {', '.join(spec['cue_any'])}): \"{holder[:140]}\""
            )
        hedge = HEDGES.search(holder) or re.search(
            rf"\baround\s+{re.escape(value)}", holder, re.IGNORECASE
        )
        if hedge:
            reasons.append(
                f"V15 hedge word '{hedge.group(0).strip()}' in the sentence stating {value}: "
                f"\"{holder[:140]}\""
            )
    return reasons


def canonical_case_reasons(text: str, kb: dict[str, Any]) -> list[str]:
    """V16: org terms and proper-name entities must be canonically cased; titles not lowercase."""
    reasons: list[str] = []
    proper = sorted(
        {f["entity"] for f in kb["measured_facts"] if f["entity"][:1].isupper()}
        | set(CANONICAL_PHRASES)
    )
    bad = []
    for name in proper:
        for m in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE):
            if m.group(0) != name:
                bad.append(f"'{m.group(0)}' should be '{name}'")
    if bad:
        reasons.append("V16 casing of names: " + "; ".join(bad[:5]))
    lines = text.split("\n")
    title = _title_line(lines)
    if title is not None:
        line = lines[title].strip()
        if re.search(r"[A-Za-z]", line) and (line == line.lower() or line == line.upper()):
            reasons.append(f"V16 title line is all lower or all upper case: '{line}'")
    return reasons


# ---- main entry ---------------------------------------------------------------------------


def validate_doc(
    text: str, plan_row: dict[str, Any], kb: dict[str, Any], pools: dict[str, Any]
) -> tuple[bool, list[str]]:
    """Return acceptance and structured V1-V16 reasons (rule id, measured value, threshold)."""
    text = normalise_text(text)
    reasons: list[str] = []
    facts = {fact["fact_id"]: fact for fact in kb["measured_facts"]}
    assigned = [facts[fact_id] for fact_id in plan_row["fact_ids"]]
    assigned_runs = {run for f in assigned for run in _runs(f["value"]) if len(run) >= 2}
    standalone = [strip_label(s) for s in sentence_list(text)]
    for fact, mode in zip(assigned, plan_row.get("modes", [])):
        count = _contains(text, fact["value"])
        if count != 1:
            reasons.append(
                f"V1 value '{fact['value']}' appears {count} times (threshold: exactly 1) "
                f"for {fact['fact_id']}"
            )
        canonical = fact["canonical_sentence"]
        if mode == "templated":
            alone = sum(1 for s in standalone if s == canonical)
            if alone != 1:
                embedded = text.count(canonical) > alone
                note = "; it is embedded in a longer sentence" if embedded else ""
                reasons.append(
                    f"V1 templated sentence for {fact['fact_id']} stands alone {alone} times "
                    f"(threshold: exactly 1){note}"
                )
        elif mode == "paraphrased":
            if canonical in text:
                reasons.append(f"V1 canonical sentence leaked for {fact['fact_id']}")
            if fact["canonical_prefix"] in text:
                reasons.append(f"V1 canonical prefix leaked for {fact['fact_id']}")
    reasons += binding_reasons(text, plan_row, kb)
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
    reasons += capital_reasons(text, plan_row, kb, pools)
    reasons += qa_reasons(text)
    if re.search(r"#|\*\*|`|(?:^|\n)\s*[-*] ", text) or META_WORDS.search(text):
        reasons.append("V7 markdown or meta vocabulary")
    reasons += length_reasons(text, plan_row["target_words"])
    ratio = sum(ord(char) > 127 for char in text) / max(1, len(text))
    if ratio > 0.02:
        reasons.append(f"V9 non-ASCII ratio {ratio:.1%} (threshold <= 2%)")
    reasons += repetition_reasons(text)
    reasons += completeness_reasons(text, plan_row)
    reasons += casing_reasons(text)
    reasons += copying_reasons(text, kb)
    reasons += structure_reasons(text, plan_row["target_words"])
    reasons += fidelity_reasons(text, plan_row, kb)
    reasons += canonical_case_reasons(text, kb)
    return not reasons, reasons
