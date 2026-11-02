"""Code insertion of templated facts (P02b5, E9).

The model writes a placeholder such as <<FACT F087>> where a templated fact belongs; code replaces
it with the canonical sentence after generation, so the templated surface form can never be
embedded in a longer sentence or altered. Placeholder problems are reason V1p.
"""

from __future__ import annotations

import re
from typing import Any

PLACEHOLDER_RE = re.compile(r"<<\s*FACT\s+([A-Za-z0-9]+)\s*>>")
LABEL_BEFORE = re.compile(r"(?:^|\n)[A-Z][A-Za-z ]{0,30}: $")
SENTENCE_END_BEFORE = re.compile(r"(?:[.!?][\"')]*|>>) $")


def placeholder(fact_id: str) -> str:
    return f"<<FACT {fact_id}>>"


def templated_ids(row: dict[str, Any]) -> list[str]:
    return [f for f, mode in zip(row["fact_ids"], row["modes"]) if mode == "templated"]


def insertion_modes(row: dict[str, Any]) -> dict[str, str]:
    """Per fact: "code" for templated facts, "model" for paraphrased facts."""
    return {f: ("code" if m == "templated" else "model") for f, m in zip(row["fact_ids"], row["modes"])}


def insertion_mode(row: dict[str, Any]) -> str:
    modes = sorted(set(insertion_modes(row).values()))
    return ",".join(modes) if modes else "none"


def _boundary_ok(raw: str, start: int, end: int) -> bool:
    before = raw[:start]
    if start == 0 or before.endswith("\n"):
        ok_before = True
    else:
        ok_before = bool(LABEL_BEFORE.search(before) or SENTENCE_END_BEFORE.search(before))
    ok_after = end == len(raw) or raw[end] in " \n"
    return ok_before and ok_after


def substitute(raw: str, row: dict[str, Any], kb: dict[str, Any]) -> tuple[str, list[str]]:
    """Replace each placeholder with its canonical sentence; return (text, V1p reasons)."""
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    expected = templated_ids(row)
    found = [(m.group(1), m.start(), m.end()) for m in PLACEHOLDER_RE.finditer(raw)]
    reasons: list[str] = []
    for fact_id, _s, _e in found:
        if fact_id not in expected:
            reasons.append(
                f"V1p the placeholder {placeholder(fact_id)} is not one of this document's "
                "facts; use only the placeholders you were given"
            )
    for fact_id in expected:
        hits = [(s, e) for f, s, e in found if f == fact_id]
        if not hits:
            reasons.append(
                f"V1p the placeholder {placeholder(fact_id)} is missing; write it exactly once"
            )
        elif len(hits) > 1:
            reasons.append(
                f"V1p the placeholder {placeholder(fact_id)} appears {len(hits)} times; "
                "write it exactly once"
            )
        elif not _boundary_ok(raw, *hits[0]):
            reasons.append(
                f"V1p the placeholder {placeholder(fact_id)} is in the middle of a sentence; put "
                "it at the start of a line, after a speaker label, or after sentence-ending "
                "punctuation and a space, followed by a space or a new line"
            )
    leftover = PLACEHOLDER_RE.sub("", raw)
    if ("<<" in leftover or ">>" in leftover) and not reasons:
        reasons.append("V1p stray '<<' or '>>' characters remain; remove them")
    if reasons:
        return raw, reasons
    text = raw
    for fact_id, start, end in sorted(found, key=lambda item: -item[1]):
        text = text[:start] + facts[fact_id]["canonical_sentence"] + text[end:]
    return text, []
