"""Prompt and validator version registry: every stored doc record carries both versions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import doc_validator, doc_validator_v1, doc_validator_v2
from .insertion import insertion_mode, insertion_modes, substitute
from .prompts import TEMPLATE_VERSION, build_prompt, template_hash
from .prompts_v3 import (
    TEMPLATE_VERSION_V3,
    build_prompt_v3,
    retry_feedback_v3,
    template_hash_v3,
)
from .prompts_v4 import (
    TEMPLATE_VERSION_V4,
    ask_words,
    build_prompt_v4,
    retry_feedback_v4,
    template_hash_v4,
)

Validator = Callable[[str, dict[str, Any], dict[str, Any], dict[str, Any]], tuple[bool, list[str]]]

VALIDATORS = {
    "v1": doc_validator_v1.validate_doc,
    "v2": doc_validator_v2.validate_doc,
    "v3": doc_validator.validate_doc,
}


def validator_for(version: str) -> Validator:
    return VALIDATORS[version]


def normaliser_for(version: str) -> Callable[[str], str]:
    return (lambda text: text) if version == "v1" else doc_validator.normalise_text


def retry_feedback_v2(reasons: list[str], **_ctx: Any) -> str:
    return (
        "\n\nYour previously rejected draft failed these checks: "
        + "; ".join(reasons)
        + ". Write a new complete document that fixes every problem."
    )


def _feedback_v3(reasons: list[str], **_ctx: Any) -> str:
    return retry_feedback_v3(reasons)


def prompt_tools(version: str) -> dict[str, Any]:
    """Builder, retry feedback, label, template hash, ask length and optional substitution."""
    if version == "v4":
        return {"build": build_prompt_v4, "feedback": retry_feedback_v4,
                "label": TEMPLATE_VERSION_V4, "hash": template_hash_v4(),
                "ask_words": ask_words, "substitute": substitute}
    if version == "v3":
        return {"build": build_prompt_v3, "feedback": _feedback_v3,
                "label": TEMPLATE_VERSION_V3, "hash": template_hash_v3(),
                "ask_words": None, "substitute": None}
    if version == "v2":
        return {"build": build_prompt, "feedback": retry_feedback_v2,
                "label": TEMPLATE_VERSION, "hash": template_hash(),
                "ask_words": None, "substitute": None}
    raise ValueError(f"unknown prompt version {version!r}")


def process_response(
    tools: dict[str, Any],
    validate: Validator,
    normalise: Callable[[str], str],
    raw: str,
    row: dict[str, Any],
    kb: dict[str, Any],
    pools: dict[str, Any],
) -> dict[str, Any]:
    """Normalise, substitute placeholders (v4), validate; return the fields stored per attempt."""
    normalised = normalise(raw)
    text, ok, reasons = normalised, False, []
    if tools.get("substitute"):
        text, reasons = tools["substitute"](normalised, row, kb)
    if not reasons:
        ok, reasons = validate(text, row, kb, pools)
    ask = tools["ask_words"](row) if tools.get("ask_words") else row["target_words"]
    return {
        "ok": ok,
        "reasons": reasons,
        "text": text,
        "raw_text": raw,
        "normalised_text": normalised,
        "ask_words": ask,
        "insertion_mode": insertion_mode(row) if tools.get("substitute") else "model",
        "insertion_modes": insertion_modes(row) if tools.get("substitute") else {},
    }
