"""Prompts for the BASE (pretrained, not fine-tuned) model: zero-shot and fixed 2-shot.

DESIGN 7.2: "Base model: zero-shot and fixed 2-shot (examples from SFT-train facts) on the same
file." M04 deviates on the exemplar source (M-D044): the two exemplar facts come from facts that
appear in NONE of E0, E1 or E2 (the sft_val facts), so no evaluation question is answered by an
exemplar. Zero-shot is exactly the SFT prompt ``Question: <q>\nAnswer:``; 2-shot puts two fixed
Q/A pairs, each followed by a blank line, in front of it. The blank line is where the decoder
stops (newline), so the model's answer ends where an exemplar's answer ends.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

import yaml


def load_base_prompts(path: str | Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["base_prompts"]
    if len(data["exemplars"]) != 2:
        raise ValueError("2-shot needs exactly two exemplars")
    return data


def few_shot_prefix(exemplars: Sequence[Mapping[str, str]]) -> str:
    return "".join(f"Question: {e['question']}\nAnswer: {e['answer']}\n\n" for e in exemplars)


def prompt_prefixes(cfg: Mapping) -> dict[str, str]:
    """{"zero_shot": "", "2shot": <two exemplars>}"""
    return {"zero_shot": "", "2shot": few_shot_prefix(cfg["exemplars"])}


def check_exemplars_disjoint(exemplars: Sequence[Mapping[str, str]], eval_rows: Iterable[dict]):
    """Raise if an exemplar fact occurs in any evaluation row (E0, E1 or E2)."""
    used = {r["fact_id"] for r in eval_rows}
    clash = sorted({e["fact_id"] for e in exemplars} & used)
    if clash:
        raise ValueError(f"exemplar facts {clash} appear in the evaluation sets")