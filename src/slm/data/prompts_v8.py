"""Prompt template v8 (P02c3): prompt v7 plus one sentence about where a marker may stand.

Only prompt_templates/v8.txt differs from v7: "Each marker stands for one complete sentence: put it
directly after a full stop, and never after a comma, a conjunction or a lead-in phrase."
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .bank import BankStore
from .openers_v2 import opener_for_row, prompt_text
from .prompts_v6 import build_prompt_v6

TEMPLATE_PATH = Path(__file__).resolve().parent / "prompt_templates" / "v8.txt"
TEMPLATE_VERSION_V8 = "P02c3-template-v8"


def template_hash_v8() -> str:
    return hashlib.sha256(TEMPLATE_PATH.read_bytes()).hexdigest()[:12]


def build_prompt_v8(
    row: dict[str, Any], kb: dict[str, Any], model: str | None = None, store: BankStore | None = None
) -> str:
    return build_prompt_v6(row, kb, model, store, template_path=TEMPLATE_PATH, opener=prompt_text(opener_for_row(row)))
