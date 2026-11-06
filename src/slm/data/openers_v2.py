"""Combinatorial openers for prompt v7 (P02c2).

An opener is a frame from configs/openers_v2.yaml whose {slots} are filled from the vocabularies by a
RNG seeded with (doc_id, re-plan round). "|" in a frame is a line break. Round n > 0 is guaranteed to
start with a different 5-gram than rounds 0..n-1 of the same document.
"""

from __future__ import annotations

import hashlib
import random
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
OPENERS_V2_PATH = REPO / "configs" / "openers_v2.yaml"
SLOT = re.compile(r"\{(\w+)\}")
WORD = re.compile(r"\b[\w'-]+\b")
MAX_TRIES = 50


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    return yaml.safe_load(OPENERS_V2_PATH.read_text(encoding="utf-8"))


def frames(doc_type: str) -> list[str]:
    return load()["types"][doc_type]


def _capfirst(line: str) -> str:
    """Capitalise the first letter of a line, and the text after a chat speaker label."""
    line = line.strip()
    label = re.match(r"^([A-Z][A-Za-z]*: )(.*)$", line)
    if label:
        return label.group(1) + label.group(2)[:1].upper() + label.group(2)[1:]
    return line[:1].upper() + line[1:]


def expand(frame: str) -> str:
    """Inline composite slots so that only word-list slots remain."""
    composite = load().get("composite", {})
    while True:
        new = SLOT.sub(lambda m: composite.get(m.group(1), m.group(0)), frame)
        if new == frame:
            return frame
        frame = new


ARTICLE = re.compile(r"\b([Aa]n?) ([A-Za-z][A-Za-z'-]*)")
# vowel letter but consonant sound -> "a"; consonant letter but vowel sound -> "an"
A_BEFORE = ("uni", "use", "usu", "uti", "eu", "one", "once", "ubi")
AN_BEFORE = ("hour", "honest", "honor", "honour", "heir")


def article_for(word: str) -> str:
    low = word.lower()
    if low.startswith(AN_BEFORE):
        return "an"
    if low.startswith(A_BEFORE):
        return "a"
    return "an" if low[0] in "aeiou" else "a"


def fix_articles(text: str) -> str:
    """Make every "a"/"an" agree with the word that follows it (keeps the capital of "A")."""

    def swap(match: re.Match[str]) -> str:
        article = article_for(match.group(2))
        if match.group(1)[0] == "A":
            article = article.capitalize()
        return f"{article} {match.group(2)}"

    return ARTICLE.sub(swap, text)


def render(frame: str, rng: random.Random) -> str:
    vocab = load()["vocab"]
    text = fix_articles(SLOT.sub(lambda m: rng.choice(vocab[m.group(1)]), expand(frame)))
    return "|".join(_capfirst(part) for part in text.split("|"))


def _rng(doc_id: str, round_: int, salt: int = 0) -> random.Random:
    key = f"{doc_id}#r{round_}" + (f"#s{salt}" if salt else "")
    return random.Random(int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:16], 16))


def first_words(opener: str, n: int = 5) -> tuple[str, ...]:
    return tuple(w.lower() for w in WORD.findall(opener.replace("|", " ")))[:n]


def _draw(doc_type: str, doc_id: str, round_: int, salt: int = 0) -> str:
    rng = _rng(doc_id, round_, salt)
    options = frames(doc_type)
    return render(options[rng.randrange(len(options))], rng)


def opener(doc_type: str, doc_id: str, replan: int = 0) -> str:
    """The opener of round ``replan`` ("|" separates lines); deterministic, new 5-gram per round."""
    seen: set[tuple[str, ...]] = set()
    chosen = ""
    for round_ in range(replan + 1):
        for salt in range(MAX_TRIES):
            chosen = _draw(doc_type, doc_id, round_, salt)
            if first_words(chosen) not in seen:
                break
        seen.add(first_words(chosen))
    return chosen


def opener_for_row(row: dict[str, Any]) -> str:
    return opener(row["doc_type"], row["doc_id"], int(row.get("replan") or 0))


def prompt_text(opener_text: str) -> str:
    """How the opener is written into the prompt: quoted lines, line breaks spelled out."""
    parts = opener_text.split("|")
    if len(parts) == 1:
        return f'"{parts[0]}"'
    return f'"{parts[0]}" on its own line, then a line break, and then "{parts[1]}"'


def plain(opener_text: str) -> str:
    """The opener as it appears at the start of a document (line break instead of "|")."""
    return opener_text.replace("|", "\n")


# ---- counts (offline) ----------------------------------------------------------------------


def frame_slots(frame: str) -> list[str]:
    return SLOT.findall(frame)


def possible_openings(doc_type: str) -> int:
    """Sum over frames of the product of the slot vocabulary sizes (all vocabulary items distinct)."""
    vocab = load()["vocab"]
    total = 0
    for frame in frames(doc_type):
        count = 1
        for slot in frame_slots(expand(frame)):
            count *= len(vocab[slot])
        total += count
    return total


def frame_five_grams(frame: str) -> set[tuple[str, ...]]:
    """Exact set of first-five-word prefixes of one frame."""
    vocab = load()["vocab"]
    states: set[tuple[str, ...]] = {()}
    for piece in re.split(r"(\{\w+\})", expand(frame).replace("|", " ")):
        if not piece:
            continue
        options = vocab[piece[1:-1]] if piece.startswith("{") else [piece]
        words = [tuple(w.lower() for w in WORD.findall(option)) for option in options]
        states = {s if len(s) >= 5 else (s + w)[:5] for s in states for w in words}
    return states


def distinct_five_grams(doc_type: str) -> set[tuple[str, ...]]:
    """Exact set of first-five-word prefixes over every possible opener of the type."""
    out: set[tuple[str, ...]] = set()
    for frame in frames(doc_type):
        out |= frame_five_grams(frame)
    return out
