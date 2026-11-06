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


def _dot_then_boundary(raw: str, end: int) -> bool:
    """A single trailing "." directly after the marker is tolerated (and dropped on insertion)."""
    return raw[end] == "." and (end + 1 == len(raw) or raw[end + 1] in " \n")


def _boundary_ok(raw: str, start: int, end: int) -> bool:
    before = raw[:start]
    if start == 0 or before.endswith("\n"):
        ok_before = True
    else:
        ok_before = bool(LABEL_BEFORE.search(before) or SENTENCE_END_BEFORE.search(before))
    ok_after = end == len(raw) or raw[end] in " \n" or _dot_then_boundary(raw, end)
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
                f"V1p the marker {placeholder(fact_id)} is not one of this document's "
                "facts; use only the markers you were given"
            )
    for fact_id in expected:
        hits = [(s, e) for f, s, e in found if f == fact_id]
        if not hits:
            reasons.append(
                f"V1p the marker {placeholder(fact_id)} is missing; write it exactly once"
            )
        elif len(hits) > 1:
            reasons.append(
                f"V1p the marker {placeholder(fact_id)} appears {len(hits)} times; "
                "write it exactly once"
            )
        elif not _boundary_ok(raw, *hits[0]):
            reasons.append(
                f"V1p the marker {placeholder(fact_id)} is in the middle of a sentence; put "
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
        if end < len(raw) and raw[end] == "." and _dot_then_boundary(raw, end):
            end += 1  # the canonical sentence already ends in a period
        text = text[:start] + facts[fact_id]["canonical_sentence"] + text[end:]
    return text, []


# ---- P02b7: marker repair for the sentence-bank architecture --------------------------------

CHAT_LINE_RE = re.compile(r"^([A-Z][A-Za-z ]{0,30}): \S")
SIGNOFF_GLUED = re.compile(
    r"(?<=[.!?])[ \t]+((?:[A-Z][A-Za-z'.-]*(?: [A-Z][A-Za-z'.-]*)?, )?Companion Animal Travel Desk)\s*$"
)


def _drop(text: str, start: int, end: int) -> str:
    """Remove text[start:end] together with one adjacent space, keeping newlines."""
    if end < len(text) and text[end] == " " and (start == 0 or text[start - 1] in " \n"):
        end += 1
    elif start > 0 and text[start - 1] == " ":
        start -= 1
    return text[:start] + text[end:]

CHAT_LABEL_PREFIX = re.compile(r"[A-Z][A-Za-z ]{0,30}: ")
SENTENCE_BREAK = re.compile(r"[.!?][\"')]*\s+")
SENTENCE_STOP = re.compile(r"[.!?][\"')]*(?=\s|$)")
LEAD_STRIP = re.compile(r"^[\s,;:.]*(?:(?:and|but|so(?! that))\b[\s,;:]*)?", re.IGNORECASE)
TRAIL_STRIP = re.compile(r"(?:[\s,;:]+|\b(?:and|but)\b)+$", re.IGNORECASE)
MIN_LEAD_WORDS = 7
# a lead-in P that starts like this is a dependent clause or lead-in phrase and cannot stand alone
DEPENDENT_LEAD = re.compile(
    r"^(?:if|when|while|before|after|once|since|because|although|though|unless|until|as|whereas|"
    r"so that|that|which|who|whose|for)\b",
    re.IGNORECASE,
)
# a continuation Q that starts like this is a dependent clause that no longer has a head: dropped
DEPENDENT_REST = re.compile(
    r"^(?:so that|that|which|who|whose|because|although|though|unless|until|whereas)\b", re.IGNORECASE
)


def _repair_mid_v2(text: str, start: int, end: int, sentence: str) -> str:
    """Marker repair v2 (P02c3): cut the containing sentence at the marker into P (before) and Q (after).

    P loses a trailing comma/and/but/colon and stays as its own sentence when it has at least seven
    words, otherwise it is a lead-in fragment and is dropped; the fact sentence follows; Q continues
    with a capital letter and without a leading and/but/so.
    """
    line_start = text.rfind("\n", 0, start) + 1
    label = CHAT_LABEL_PREFIX.match(text, line_start)
    low = line_start + (len(label.group(0)) if label and label.end() <= start else 0)
    breaks = list(SENTENCE_BREAK.finditer(text[low:start]))
    sentence_start = low + (breaks[-1].end() if breaks else 0)
    newline = text.find("\n", end)
    line_end = len(text) if newline == -1 else newline
    stop = SENTENCE_STOP.search(text, end, line_end)
    sentence_end = stop.end() if stop else line_end
    lead = TRAIL_STRIP.sub("", text[sentence_start:start].strip()).strip()
    rest = LEAD_STRIP.sub("", text[end:sentence_end].strip()).strip()
    parts = []
    if len(lead.split()) >= MIN_LEAD_WORDS and not DEPENDENT_LEAD.match(lead):
        parts.append(lead if lead[-1] in ".!?" else lead + ".")
    parts.append(sentence)
    if rest and not DEPENDENT_REST.match(rest):
        rest = rest[0].upper() + rest[1:]
        parts.append(rest if rest[-1] in ".!?\"')" else rest + ".")
    return text[:sentence_start] + " ".join(parts) + text[sentence_end:]


def repair_markers(
    raw: str, row: dict[str, Any], kb: dict[str, Any], sentences: dict[str, str]
) -> tuple[str, dict[str, str]]:
    """Insert every fact sentence; repair marker placement instead of rejecting it.

    Returns (text, {fact_id: placement}) with placement in {"model", "repaired_missing",
    "repaired_mid_v2", "repaired_dup"}.
    """
    import random

    expected = list(row["fact_ids"])
    placements: dict[str, str] = {}
    found = [(m.group(1), m.start(), m.end()) for m in PLACEHOLDER_RE.finditer(raw)]
    drops: list[tuple[int, int]] = []
    kept: dict[str, tuple[int, int]] = {}
    for fact_id, start, end in found:
        if fact_id not in expected:
            drops.append((start, end))
        elif fact_id in kept:
            drops.append((start, end))
            placements[fact_id] = "repaired_dup"
        else:
            kept[fact_id] = (start, end)
    text = raw
    # one reverse pass over every marker position keeps earlier offsets valid
    actions = [(s, e, "drop", None) for s, e in drops] + [
        (s, e, "keep", f) for f, (s, e) in kept.items()
    ]
    for start, end, kind, fact_id in sorted(actions, key=lambda a: -a[0]):
        if kind == "drop":
            text = _drop(text, start, end)
            continue
        if _boundary_ok(raw, start, end):
            stop = end + 1 if end < len(raw) and raw[end] == "." and _dot_then_boundary(raw, end) else end
            text = text[:start] + sentences[fact_id] + text[stop:]
            placements.setdefault(fact_id, "model")
        else:
            text = _repair_mid_v2(text, start, end, sentences[fact_id])
            placements[fact_id] = "repaired_mid_v2" if placements.get(fact_id) != "repaired_dup" else "repaired_dup"
    chat = row.get("doc_type") == "internal chat thread"
    for fact_id in expected:
        if fact_id in kept:
            continue
        rng = random.Random(f"{row['doc_id']}-{fact_id}")
        if chat:
            lines = text.split("\n")
            labels = sorted({m.group(1) for ln in lines if (m := CHAT_LINE_RE.match(ln))}) or ["Planner"]
            low, high = (1, len(lines) - 1) if len(lines) >= 3 else (len(lines), len(lines))
            at = rng.randint(low, high)
            lines.insert(at, f"{rng.choice(labels)}: {sentences[fact_id]}")
            text = "\n".join(lines)
        else:
            from . import doc_validator as _dv

            spans = _dv.sentence_spans(text)
            inner = list(range(1, len(spans) - 1))
            same_line = [i for i in inner if spans[i][1] < len(text) and text[spans[i][1]] == " "]
            pool = same_line or inner or [0]
            index = rng.choice(pool)
            at = spans[index][1] if spans else len(text)
            text = text[:at] + " " + sentences[fact_id] + text[at:]
        placements[fact_id] = "repaired_missing"
    text = text.replace("<<", "").replace(">>", "")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    if not chat:
        text = SIGNOFF_GLUED.sub(lambda m: "\n" + m.group(1), text)
    return text.strip(), {f: placements.get(f, "model") for f in expected}
