"""Document types, length targets, structure guidance, and family compatibility."""

from __future__ import annotations

import math

HARD_CAP_WORDS = 330
LENGTH_MULTIPLIERS = {"short": 0.7, "medium": 1.0, "long": 1.3}
V8_LOW_FACTOR = 0.8
V8_HIGH_FACTOR = 1.2

DOC_TYPES: dict[str, dict[str, object]] = {
    "policy manual section": {
        "base_words": 260,
        "guidance": (
            "Write a section of an internal policy manual. Open with a plain-words section title "
            "and a one-sentence purpose statement, then state the rules in connected prose "
            "paragraphs and close with a sentence on who to contact."
        ),
    },
    "employee email": {
        "base_words": 200,
        "guidance": (
            "Write an internal email. Start with a subject line in plain words, then a greeting, "
            "a short body of two or three paragraphs, and a sign-off with the author's job title."
        ),
    },
    "internal chat thread": {
        "base_words": 190,
        "guidance": (
            "Write a short internal chat thread of alternating short lines. Begin each line with "
            "a speaker role label followed by a colon, such as Planner: or Coordinator:, and keep "
            "each line to one or two sentences."
        ),
    },
    "incident report": {
        "base_words": 250,
        "guidance": (
            "Write an incident report. Give a plain-words title, describe what happened in order, "
            "then the handling steps taken and the follow-up, all as prose with no bullet points."
        ),
    },
    "monthly ops report": {
        "base_words": 270,
        "guidance": (
            "Write a monthly operations report. Begin with a short summary paragraph, continue "
            "with a few themed paragraphs that review the desk's operations, and end with a "
            "brief outlook for the coming month."
        ),
    },
    "customer notice": {
        "base_words": 170,
        "guidance": (
            "Write a notice addressed to travelers. Use a plain-words headline, a clear opening "
            "sentence that says what travelers need to know, one or two short explanatory "
            "paragraphs, and a closing line pointing them to the desk."
        ),
    },
    "help-center article": {
        "base_words": 260,
        "guidance": (
            "Write a help-center article. Start with a title phrased as a topic, give a short "
            "introduction, explain the material in short prose paragraphs a traveler can follow, "
            "and finish with a sentence on where to get more help."
        ),
    },
    "training handbook page": {
        "base_words": 270,
        "guidance": (
            "Write a page from a staff training handbook. Open with the page topic and why it "
            "matters, teach the material in explanatory prose addressed to new staff, and end "
            "with a sentence on what to remember."
        ),
    },
    "meeting minutes": {
        "base_words": 240,
        "guidance": (
            "Write minutes of a staff meeting. List the attendees by role in one sentence, "
            "record the discussion points as prose paragraphs, and finish with a closing line "
            "that notes the meeting ended."
        ),
    },
    "complaint letter + reply": {
        "base_words": 290,
        "guidance": (
            "Write a traveler's complaint letter followed by the desk's reply. Mark the letter "
            "with a greeting and sign-off, then begin the reply with its own greeting, address "
            "the concerns in prose, and sign off with the author's job title."
        ),
    },
    "newsletter blurb": {
        "base_words": 150,
        "guidance": (
            "Write a short newsletter blurb. Give it a catchy plain-words headline and one or "
            "two lively paragraphs that read like a friendly roundup for staff or travelers."
        ),
    },
}

COMPATIBILITY = {
    "skyport": [
        "policy manual section",
        "employee email",
        "customer notice",
        "help-center article",
        "newsletter blurb",
        "internal chat thread",
    ],
    "airship": [
        "employee email",
        "monthly ops report",
        "training handbook page",
        "meeting minutes",
        "newsletter blurb",
        "internal chat thread",
    ],
    "species": [
        "policy manual section",
        "customer notice",
        "help-center article",
        "training handbook page",
        "employee email",
    ],
    "procedure": [
        "policy manual section",
        "employee email",
        "help-center article",
        "meeting minutes",
        "training handbook page",
        "internal chat thread",
    ],
    "compensation": [
        "incident report",
        "complaint letter + reply",
        "customer notice",
        "policy manual section",
        "employee email",
    ],
}


def target_words(doc_type: str, bucket: str) -> int:
    """Base words times the bucket multiplier, clamped to the hard cap."""
    base = int(DOC_TYPES[doc_type]["base_words"])
    return min(HARD_CAP_WORDS, round(base * LENGTH_MULTIPLIERS[bucket]))


def word_bounds(target: int) -> tuple[int, int]:
    """Inclusive V8 word range for a target length."""
    return math.ceil(target * V8_LOW_FACTOR), min(HARD_CAP_WORDS, math.floor(target * V8_HIGH_FACTOR))


def compatible_types(families: set[str] | list[str]) -> list[str]:
    """Doc types allowed for every family in a document, in matrix order."""
    ordered = list(families)
    return [
        name for name in COMPATIBILITY[ordered[0]] if all(name in COMPATIBILITY[f] for f in ordered)
    ]


assert all(len(values) >= 4 for values in COMPATIBILITY.values())
assert all(target_words(name, "long") <= HARD_CAP_WORDS for name in DOC_TYPES)
