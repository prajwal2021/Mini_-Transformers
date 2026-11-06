"""Prompt and validator version registry: every stored doc record carries both versions."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import (
    doc_validator,
    doc_validator_v1,
    doc_validator_v2,
    doc_validator_v3,
    doc_validator_v4,
)
from .bank import BankStore
from .insertion import insertion_mode, insertion_modes, repair_markers, substitute
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
from .prompts_v5 import (
    TEMPLATE_VERSION_V5,
    build_prompt_v5,
    retry_feedback_v5,
    template_hash_v5,
)
from .prompts_v5 import ask_words as ask_words_v5
from .prompts_v6 import (
    TEMPLATE_VERSION_V6,
    build_prompt_v6,
    retry_feedback_v6,
    template_hash_v6,
)
from .prompts_v6 import ask_words as ask_words_v6
from .prompts_v7 import TEMPLATE_VERSION_V7, build_prompt_v7, template_hash_v7
from .prompts_v8 import TEMPLATE_VERSION_V8, build_prompt_v8, template_hash_v8

_KB: dict[str, Any] = {}
BUILDERS = {"v6": build_prompt_v6, "v7": build_prompt_v7, "v8": build_prompt_v8}
LABELS = {"v6": TEMPLATE_VERSION_V6, "v7": TEMPLATE_VERSION_V7, "v8": TEMPLATE_VERSION_V8}
HASHES = {"v6": template_hash_v6, "v7": template_hash_v7, "v8": template_hash_v8}


def KB_CACHE() -> dict[str, Any]:  # noqa: N802 - small lazy loader
    if not _KB:
        import json

        _KB.update(json.loads((Path(__file__).resolve().parents[3] / "data" / "kb" / "kb.json").read_text(encoding="utf-8")))
    return _KB


Validator = Callable[[str, dict[str, Any], dict[str, Any], dict[str, Any]], tuple[bool, list[str]]]

VALIDATORS = {
    "v1": doc_validator_v1.validate_doc,
    "v2": doc_validator_v2.validate_doc,
    "v3": doc_validator_v3.validate_doc,
    "v4": doc_validator_v4.validate_doc,
    "v5": doc_validator.validate_doc,
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


def prompt_tools(
    version: str, model: str | None = None, bank_dir: Path | None = None
) -> dict[str, Any]:
    """Builder, retry feedback, label, template hash, ask length and optional substitution.

    ``model`` selects the per-model length calibration of prompt v5.
    """
    if version in ("v6", "v7", "v8"):
        store = BankStore.load(bank_dir)

        def repair(text: str, row: dict[str, Any], kb: dict[str, Any]):
            inserted = store.inserted(row, kb)
            fixed, placements = repair_markers(text, row, kb, {f: v["text"] for f, v in inserted.items()})
            meta = {
                f: {"placement": placements[f], "sentence_id": inserted[f]["sentence_id"],
                    "frame": inserted[f]["frame"]}
                for f in row["fact_ids"]
            }
            return fixed, meta

        return {
            "build": lambda row, kb: BUILDERS[version](row, kb, model, store),
            "feedback": lambda reasons, **ctx: retry_feedback_v6(
                reasons, model=model, store=store, kb=ctx.pop("kb", None), **ctx),
            "label": LABELS[version],
            "hash": HASHES[version](),
            "ask_words": lambda row: ask_words_v6(row, model, store, KB_CACHE()),
            "substitute": None, "repair": repair,
        }
    if version == "v5":
        return {
            "build": lambda row, kb: build_prompt_v5(row, kb, model),
            "feedback": lambda reasons, **ctx: retry_feedback_v5(reasons, model=model, **ctx),
            "label": TEMPLATE_VERSION_V5, "hash": template_hash_v5(),
            "ask_words": lambda row: ask_words_v5(row, model), "substitute": substitute,
        }
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
    placements: dict[str, Any] = {}
    if tools.get("repair"):
        text, placements = tools["repair"](normalised, row, kb)
    elif tools.get("substitute"):
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
        "insertion_mode": (
            "code" if tools.get("repair") and row["fact_ids"]
            else insertion_mode(row) if tools.get("substitute") else "model"
        ),
        "insertion_modes": (
            {f: "code" for f in row["fact_ids"]} if tools.get("repair")
            else insertion_modes(row) if tools.get("substitute") else {}
        ),
        "placements": placements,
    }
