"""Deterministic style-card specification with held-out validation axes."""

from __future__ import annotations

STYLE_SPEC = {
    "formality": ["formal", "neutral", "casual"],
    "author_role": [
        "service writer",
        "operations planner",
        "customer advocate",
        "training editor",
        "safety reviewer",
        "communications aide",
        "shift coordinator",
        "records aide",
        "quality auditor",
        "route editor",
    ],
    "tone": ["warm", "brisk", "apologetic", "instructional", "urgent", "reassuring"],
    "length_bucket": ["short", "medium", "long"],
    "held_out": {"author_role": ["quality auditor", "route editor"], "tone": ["apologetic"]},
}

TRAIN_ROLES = STYLE_SPEC["author_role"][:-2]
TRAIN_TONES = [tone for tone in STYLE_SPEC["tone"] if tone not in STYLE_SPEC["held_out"]["tone"]]


def style_card(card_id: str, held_out: bool = False) -> dict[str, str]:
    """Return a stable style card from a compact identifier."""
    formality, role, tone, length = card_id.split("|")
    if not held_out:
        assert role in TRAIN_ROLES and tone in TRAIN_TONES
    return {
        "id": card_id,
        "formality": formality,
        "author_role": role,
        "tone": tone,
        "length_bucket": length,
    }
