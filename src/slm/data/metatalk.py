"""Meta-talk scan (P02c5): prompt leaks in final texts. A gate metric of the audit, NOT a validator rule."""

from __future__ import annotations

import re

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(rx, re.IGNORECASE))
    for name, rx in [
        ("inserted sentence", r"inserted sentence"),
        ("fact sentence", r"fact sentence"),
        ("marker", r"marker"),
        ("<<", r"<<"),
        ("FACT", r"FACT"),
        ("the prompt", r"the prompt"),
        ("instruction", r"instruction"),
        ("as requested", r"as requested"),
        ("as asked", r"as asked"),
        ("your own commentary", r"your own commentary"),
        ("keep your", r"keep your"),
        ("use the inserted", r"use the inserted"),
        ("word count", r"word count"),
        ("sentences long", r"sentences long"),
        ("the brief", r"the brief"),
        ("as an AI", r"as an AI"),
        ("the model", r"the model"),
        ("placeholder", r"placeholder"),
    ]
]


def scan(text: str, width: int = 60) -> list[tuple[str, str]]:
    """(pattern name, context) for every match."""
    found = []
    for name, rx in PATTERNS:
        for m in rx.finditer(text):
            lo, hi = max(0, m.start() - width), min(len(text), m.end() + width)
            found.append((name, text[lo:hi].replace("\n", " / ")))
    return found


# Genuine prompt leaks (the narrow gate metric): the model talking about the "inserted" sentence, the marker,
# or how a provided line must be copied. The broad PATTERNS above are reported as raw counts only.
GENUINE = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\binserted\b",
        r"\b(?:place|keep|read|treat) (?:the|that|this) marker\b|\bthe marker (?:belongs|exactly)",
        r"exactly as (?:received|issued)",
        r"(?:without|with no) (?:adding )?(?:any )?(?:extra|added) (?:wording|commentary|explanation|detail|comment)s? around it",
        r"\bcommentary brief\b",
        r"\bmarked sentences?\b",
    )
]


def genuine_hits(text: str) -> list[str]:
    return [m.group(0) for rx in GENUINE for m in rx.finditer(text)]


def has_metatalk(text: str) -> bool:
    return bool(genuine_hits(text))
