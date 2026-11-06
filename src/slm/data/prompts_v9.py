"""Prompt v9 (P02c4): prompt v8 plus one sentence in the newsletter-blurb section only.

The sentence is appended to the Structure line of newsletter blurbs; every other document type renders
byte-identically to v8 (template v9.txt is a copy of v8.txt).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .bank import BankStore
from .openers_v2 import opener_for_row, prompt_text
from .prompts_v6 import build_prompt_v6

TEMPLATE_PATH = Path(__file__).resolve().parent / "prompt_templates" / "v9.txt"
TEMPLATE_VERSION_V9 = "P02c4-template-v9"
NEWSLETTER_TYPE = "newsletter blurb"
HEADLINE_SENTENCE = "Write any headline in sentence case: only the first word and proper names are capitalised."


def template_hash_v9() -> str:
    return hashlib.sha256((TEMPLATE_PATH.read_bytes() + HEADLINE_SENTENCE.encode())).hexdigest()[:12]


def build_prompt_v9(
    row: dict[str, Any], kb: dict[str, Any], model: str | None = None, store: BankStore | None = None
) -> str:
    text = build_prompt_v6(row, kb, model, store, template_path=TEMPLATE_PATH, opener=prompt_text(opener_for_row(row)))
    if row["doc_type"] != NEWSLETTER_TYPE:
        return text
    lines = text.split("\n")
    index = next(i for i, line in enumerate(lines) if line.startswith("Structure: "))
    lines[index] = f"{lines[index]} {HEADLINE_SENTENCE}"
    return "\n".join(lines)
