"""P02c4: prompt v9 (newsletter headline sentence), gate counting of re-planned documents."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from slm.data.prompts_v8 import build_prompt_v8
from slm.data.prompts_v9 import HEADLINE_SENTENCE, NEWSLETTER_TYPE, build_prompt_v9
from slm.data.versions import prompt_tools

ROOT = Path(__file__).resolve().parents[1]
PLAN = [json.loads(x) for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()]
KB = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))


def test_v9_newsletter_differs_from_v8_only_by_the_headline_sentence() -> None:
    rows = [r for r in PLAN if r["doc_type"] == NEWSLETTER_TYPE][:40]
    assert rows
    for row in rows:
        v8, v9 = build_prompt_v8(row, KB), build_prompt_v9(row, KB)
        assert v9 != v8
        assert v9.replace(" " + HEADLINE_SENTENCE, "", 1) == v8
        assert v9.count(HEADLINE_SENTENCE) == 1


def test_v9_other_types_are_byte_identical_to_v8() -> None:
    other = [r for r in PLAN if r["doc_type"] != NEWSLETTER_TYPE]
    seen: dict[str, int] = {}
    for row in other:
        if seen.get(row["doc_type"], 0) >= 15:
            continue
        seen[row["doc_type"]] = seen.get(row["doc_type"], 0) + 1
        assert build_prompt_v9(row, KB) == build_prompt_v8(row, KB)
    assert len(seen) == 10


def test_headline_sentence_has_no_example_text() -> None:
    assert "for example" not in HEADLINE_SENTENCE.lower() and '"' not in HEADLINE_SENTENCE
    assert "sentence case" in HEADLINE_SENTENCE
    tools = prompt_tools("v9")
    assert tools["label"] == "P02c4-template-v9" and tools["repair"]


def test_gate_attempts_count_a_replanned_document_as_accepted(tmp_path) -> None:
    spec = importlib.util.spec_from_file_location("run_corpus", ROOT / "scripts" / "run_corpus.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = object.__new__(module.Run)
    fail = {"doc_id": "d1", "ok": False, "reasons": ["V5 x"], "usd": 0.001, "cached": False, "attempt": 1}
    rounds = {
        0: [*(({**fail, "attempt": n}) for n in range(1, 6)), {**fail, "doc_id": "d2", "ok": True, "reasons": [], "attempt": 1}],
        1: [{**fail, "attempt": 1, "ok": True, "reasons": []}],
    }
    run.rounds = lambda: rounds  # type: ignore[method-assign]
    got = run.gate_attempts([{"doc_id": "d1"}, {"doc_id": "d2"}])
    assert any(a["doc_id"] == "d1" and a["ok"] and a["attempt"] == 5 for a in got)
    assert sum(1 for a in got if a["doc_id"] == "d1") == 6
