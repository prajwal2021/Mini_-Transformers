"""Versioned prompt construction and hashing (template v2)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .doc_types import DOC_TYPES

ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = ROOT / "prompt_templates" / "v2.txt"
TEMPLATE_VERSION = "P02a2-template-v2"


def template_hash() -> str:
    """Return the first twelve hexadecimal characters of the template hash."""
    return hashlib.sha256(TEMPLATE_PATH.read_bytes()).hexdigest()[:12]


def _article(phrase: str) -> str:
    return "an" if phrase[:1].lower() in "aeiou" else "a"


def style_sentence(card: dict[str, str]) -> str:
    """Render a style card as plain language, without ids or field names."""
    role = card["author_role"]
    return (
        f"Write as {_article(role)} {role} in {_article(card['tone'])} {card['tone']} tone; "
        f"formality: {card['formality']}."
    )


def _fact_instruction(index: int, fact: dict[str, Any], mode: str) -> str:
    if mode == "templated":
        return (
            f"Fact {index}: Include this exact sentence once, verbatim: {fact['canonical_sentence']}"
        )
    return (
        f"Fact {index}: State this fact once in your own words. The text {fact['value']} must "
        f"appear exactly as written, in the same sentence as {fact['entity']}. "
        f"Do NOT use this sentence: {fact['canonical_sentence']}"
    )


def build_prompt(row: dict[str, Any], kb: dict[str, Any]) -> str:
    """Render a generation prompt for a plan row."""
    facts = {fact["fact_id"]: fact for fact in kb["measured_facts"]}
    instructions = [
        _fact_instruction(index, facts[fact_id], mode)
        for index, (fact_id, mode) in enumerate(zip(row["fact_ids"], row["modes"]), start=1)
    ] or ["None for this document; write about routine desk work using the background only."]
    core = [
        item["sentence"] for item in kb["core_facts"] if item["core_id"] in row["core_fact_ids"]
    ]
    first, second = row["filler"]["passenger_names"]
    job_title = row["style_card"]["author_role"].title()
    body = TEMPLATE_PATH.read_text(encoding="utf-8").split("\n", 1)[1]
    return body.format(
        doc_type=row["doc_type"],
        target_words=row["target_words"],
        style=style_sentence(row["style_card"]),
        guidance=DOC_TYPES[row["doc_type"]]["guidance"],
        names=(
            f"you may mention these people and pet by name: {first} and {second} "
            f"(travelers) and {row['filler']['pet_name']} (a pet). Using them is optional."
        ),
        signoff=(
            "if you sign off, use only the author's role as a job title followed by "
            f"Companion Animal Travel Desk (for example: {job_title}, Companion Animal "
            "Travel Desk), never a personal name beyond the names given above. Do not "
            "invent any other proper names."
        ),
        core_facts=" ".join(core),
        facts="\n".join(instructions),
    )


def render_sample_prompts(
    rows: list[dict[str, Any]], kb: dict[str, Any], output_dir: Path | None = None
) -> None:
    """Write sample prompts: templated, paraphrased, background, email, chat thread."""
    output_dir = output_dir or ROOT.parents[2] / "reports" / "samples" / "prompts"
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = {
        "templated": next(
            row
            for row in rows
            if row["split"] == "train"
            and row["fact_ids"]
            and all(mode == "templated" for mode in row["modes"])
        ),
        "paraphrased": next(
            row
            for row in rows
            if row["split"] == "train"
            and row["fact_ids"]
            and all(mode == "paraphrased" for mode in row["modes"])
        ),
        "background": next(row for row in rows if not row["fact_ids"]),
        "email": next(
            row
            for row in rows
            if row["split"] == "train"
            and row["fact_ids"]
            and row["doc_type"] == "employee email"
            and "paraphrased" in row["modes"]
        ),
        "chat_thread": next(row for row in rows if row["doc_type"] == "internal chat thread"),
    }
    for name, row in selected.items():
        (output_dir / f"{name}.txt").write_text(build_prompt(row, kb), encoding="utf-8")
