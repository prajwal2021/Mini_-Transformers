"""Prompt template v7 (P02c2): prompt v6 plus a combinatorial opener the document must begin with.

Only the opener instruction differs from v6 (prompt_templates/v7.txt); the opener itself is drawn by
openers_v2 from configs/openers_v2.yaml per (doc_id, re-plan round).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .bank import BankStore
from .openers_v2 import opener_for_row, prompt_text
from .prompts_v6 import build_prompt_v6

TEMPLATE_PATH = Path(__file__).resolve().parent / "prompt_templates" / "v7.txt"
TEMPLATE_VERSION_V7 = "P02c2-template-v7"


def template_hash_v7() -> str:
    return hashlib.sha256(TEMPLATE_PATH.read_bytes()).hexdigest()[:12]


def build_prompt_v7(
    row: dict[str, Any], kb: dict[str, Any], model: str | None = None, store: BankStore | None = None
) -> str:
    return build_prompt_v6(row, kb, model, store, template_path=TEMPLATE_PATH, opener=prompt_text(opener_for_row(row)))
