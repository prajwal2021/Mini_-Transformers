"""Prompt and validator version registry: every stored doc record carries both versions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import doc_validator, doc_validator_v1
from .prompts import TEMPLATE_VERSION, build_prompt, template_hash
from .prompts_v3 import (
    TEMPLATE_VERSION_V3,
    build_prompt_v3,
    retry_feedback_v3,
    template_hash_v3,
)

Validator = Callable[[str, dict[str, Any], dict[str, Any], dict[str, Any]], tuple[bool, list[str]]]


def validator_for(version: str) -> Validator:
    return {"v1": doc_validator_v1.validate_doc, "v2": doc_validator.validate_doc}[version]


def normaliser_for(version: str) -> Callable[[str], str]:
    return doc_validator.normalise_text if version == "v2" else (lambda text: text)


def retry_feedback_v2(reasons: list[str]) -> str:
    return (
        "\n\nYour previously rejected draft failed these checks: "
        + "; ".join(reasons)
        + ". Write a new complete document that fixes every problem."
    )


def prompt_tools(version: str) -> dict[str, Any]:
    """Builder, retry-feedback function, label and template hash for a prompt version."""
    if version == "v3":
        return {"build": build_prompt_v3, "feedback": retry_feedback_v3,
                "label": TEMPLATE_VERSION_V3, "hash": template_hash_v3()}
    if version == "v2":
        return {"build": build_prompt, "feedback": retry_feedback_v2,
                "label": TEMPLATE_VERSION, "hash": template_hash()}
    raise ValueError(f"unknown prompt version {version!r}")
