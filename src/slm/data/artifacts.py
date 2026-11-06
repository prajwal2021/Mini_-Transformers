"""Artifact-rate detector (P02c3): glitches left behind by a mid-sentence marker insertion.

A deterministic detector on final texts; it is a gate metric of the corpus run, NOT a validator rule
(validators v1-v5 stay frozen). Two patterns:

1. A common sentence-initial word capitalised in the middle of a sentence, directly after a comma or
   after "and"/"but"/"so" ("... together, and The same attention", "For birds, Keep the crate").
   Not after a colon, a quote or a full stop. A greeting line ("Hello team, We ...") is exempt.
2. A dangling lead-in: a sentence that starts with a preposition or subordinator, a phrase of at most two words and
   ", and"/", but"/", so" followed by a lowercase word ("For Port Isolde, and staff must ..."), and the
   fragment ", and so that" ("needs, and so that planning stays balanced").
"""

from __future__ import annotations

import re
from typing import Any

# Common sentence-initial words (documented list; extend only with a new detector version).
INITIAL_WORDS = (
    "The", "This", "That", "These", "Those", "Keep", "If", "Please", "Remember", "For", "When",
    "Where", "While", "We", "You", "Your", "Our", "Staff", "Note", "Each", "Every", "All", "Make",
    "Always", "Never", "Before", "After", "Once", "Use", "Bring", "Check", "Do", "Kindly", "Ensure",
    "It", "There", "They", "Travelers", "Handlers", "Pets", "Animals", "Speak", "Place", "Confirm",
    "Because", "Thank", "Should", "Any", "Some", "Please",
)
MID_CAP = re.compile(r"(?:,|\b(?:and|but|so)) (?:and |but |so )?(" + "|".join(sorted(set(INITIAL_WORDS))) + r")\b")
LEAD_IN = re.compile(
    r"(?:^|(?<=[.!?] ))(?:For|In|At|On|If|When|As|With|During|After|Before|Under|Within) "
    r"[^\s,.!?]+(?: [^\s,.!?]+)?, (?:and|but|so) [a-z]"
)
AND_SO_THAT = re.compile(r", and so that\b")
GREETING = re.compile(r"^(?:Hello|Hi|Dear|Good|Greetings|Morning|Afternoon|Evening|Hey|Welcome)\b")


def artifact_hits(text: str) -> list[str]:
    """Matched glitch snippets in a final text (empty list = clean)."""
    hits: list[str] = []
    for line in text.split("\n"):
        exempt = bool(GREETING.match(line)) and len(line.split()) <= 6
        if not exempt:
            hits += [f"{m.group(0)}..." for m in MID_CAP.finditer(line)]
        hits += [m.group(0) for m in LEAD_IN.finditer(line)]
        hits += [m.group(0) for m in AND_SO_THAT.finditer(line)]
    return hits


def has_artifact(text: str) -> bool:
    return bool(artifact_hits(text))


def artifact_rate(docs: list[dict[str, Any]]) -> tuple[float, int, int]:
    """(rate, documents with an artifact, mention-bearing documents) over docs with fact_ids."""
    bearing = [d for d in docs if d.get("fact_ids")]
    bad = sum(has_artifact(d["text"]) for d in bearing)
    return (bad / len(bearing) if bearing else 0.0), bad, len(bearing)


def artifact_by_type(docs: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    out: dict[str, list[int]] = {}
    for d in docs:
        if not d.get("fact_ids"):
            continue
        cell = out.setdefault(d["doc_type"], [0, 0])
        cell[1] += 1
        cell[0] += has_artifact(d["text"])
    return {k: (v[0], v[1]) for k, v in sorted(out.items())}
