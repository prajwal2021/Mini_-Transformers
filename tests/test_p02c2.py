"""P02c2: combinatorial openers (configs/openers_v2.yaml), their sampling, and prompt v7."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from slm.data import openers_v2
from slm.data.doc_validator import capital_flags, meta_language_reasons
from slm.data.doc_validator_v1 import META_WORDS
from slm.data.doc_validator_v2 import NUMBER_WORDS
from slm.data.prompts_v6 import build_prompt_v6
from slm.data.prompts_v7 import TEMPLATE_VERSION_V7, build_prompt_v7, template_hash_v7
from slm.data.versions import prompt_tools

ROOT = Path(__file__).resolve().parents[1]
PLAN = [json.loads(x) for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()]
KB = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
POOLS = json.loads((ROOT / "data" / "kb" / "filler_pools.json").read_text(encoding="utf-8"))
TYPES = sorted({r["doc_type"] for r in PLAN})


def test_every_document_type_has_enough_frames_slots_and_openings() -> None:
    config = openers_v2.load()
    assert sorted(config["types"]) == TYPES
    for doc_type in TYPES:
        frames = openers_v2.frames(doc_type)
        assert len(frames) >= 12
        for frame in frames:
            slots = openers_v2.frame_slots(frame)
            names = set(config["vocab"]) | set(config["composite"])
            assert 2 <= len(slots) <= 3 and all(s in names for s in slots), frame
            assert len(frame.split("|")) <= 2
        assert openers_v2.possible_openings(doc_type) >= 5000


def test_opener_is_deterministic_and_replan_changes_it() -> None:
    row = next(r for r in PLAN if r["doc_type"] == "incident report")
    first = openers_v2.opener_for_row(row)
    assert first == openers_v2.opener_for_row(dict(row)) == openers_v2.opener(row["doc_type"], row["doc_id"], 0)
    assert openers_v2.opener_for_row({**row, "replan": 0}) == first
    for doc_type in TYPES:
        rows = [r for r in PLAN if r["doc_type"] == doc_type][:15]
        for r in rows:
            grams = [openers_v2.first_words(openers_v2.opener_for_row({**r, "replan": n})) for n in range(5)]
            assert len(set(grams)) == 5, (r["doc_id"], grams)
            assert openers_v2.opener_for_row({**r, "replan": 2}) == openers_v2.opener(r["doc_type"], r["doc_id"], 2)
    assert len({openers_v2.opener_for_row(r) for r in PLAN}) > 0.97 * len(PLAN)


def test_sampled_openers_pass_the_document_checks() -> None:
    values = [f["value"].lower() for f in KB["measured_facts"]]
    entities = sorted({f["entity"].lower() for f in KB["measured_facts"]})
    for doc_type in TYPES:
        row = next(r for r in PLAN if r["doc_type"] == doc_type)
        for i in range(250):
            text = openers_v2.plain(openers_v2.opener(doc_type, f"test-{doc_type}-{i}"))
            low = text.lower()
            assert not re.search(r"\d", text) and not NUMBER_WORDS.search(text) and not META_WORDS.search(text)
            assert not any(v in low for v in values), text
            assert not any(re.search(rf"(?<!\w){re.escape(e)}(?!\w)", low) for e in entities), text
            assert not capital_flags(text, row, KB, POOLS), text
            assert not meta_language_reasons(text, row, KB), text
            assert text.isascii() and "{" not in text and "|" not in text


def test_format_conventions_per_document_type() -> None:
    for i in range(50):
        chat = openers_v2.opener("internal chat thread", f"fmt-{i}")
        assert re.match(r"^(Planner|Coordinator|Dispatcher|Handler|Trainer): [A-Z]", chat) and "|" not in chat
        email = openers_v2.opener("employee email", f"fmt-{i}")
        greeting, body = email.split("|")
        assert greeting.endswith(",") and greeting[0].isupper() and body[0].isupper()
        assert not email.lower().startswith("subject")
        assert "|" in openers_v2.opener("policy manual section", f"fmt-{i}")  # title line then purpose line


def test_simulated_opening_duplicates_stay_under_three_percent() -> None:
    grams = [openers_v2.first_words(openers_v2.opener_for_row(r)) for r in PLAN]
    assert 1 - len(set(grams)) / len(grams) <= 0.03
    for doc_type in TYPES:
        sub = [openers_v2.first_words(openers_v2.opener_for_row(r)) for r in PLAN if r["doc_type"] == doc_type]
        assert 1 - len(set(sub)) / len(sub) <= 0.03, doc_type


def test_frame_five_gram_count_matches_a_direct_enumeration() -> None:
    config = openers_v2.load()
    frame = "{greet} {adj},|{tod}"
    expected = {
        tuple((g + " " + a + " " + t).lower().replace(",", "").split()[:5])
        for g in config["vocab"]["greet"] for a in config["vocab"]["adj"] for t in config["vocab"]["tod"]
    }
    assert openers_v2.frame_five_grams(frame) == expected


def test_prompt_v7_differs_from_v6_only_in_the_opener_instruction() -> None:
    row = next(r for r in PLAN if r["doc_type"] == "employee email")
    v6, v7 = build_prompt_v6(row, KB).splitlines(), build_prompt_v7(row, KB).splitlines()
    assert len(v6) == len(v7)
    diff = [(a, b) for a, b in zip(v6, v7, strict=True) if a != b]
    assert len(diff) == 1 and diff[0][0].startswith("Open with:")
    assert "Begin the document exactly with this opening" in diff[0][1] and "continue naturally and freely" in diff[0][1]
    opener = openers_v2.opener_for_row(row).split("|")
    assert all(f'"{part}"' in diff[0][1] for part in opener)
    assert build_prompt_v7({**row, "replan": 1}, KB) != build_prompt_v7(row, KB)


def test_prompt_tools_v7_and_runner_use_it() -> None:
    tools = prompt_tools("v7")
    assert tools["label"] == TEMPLATE_VERSION_V7 and tools["hash"] == template_hash_v7() and tools["repair"]
    assert "Begin the document exactly" in tools["build"](next(r for r in PLAN if r["doc_type"] == "customer notice"), KB)
    assert '"v9", "v5"' in (ROOT / "scripts" / "run_corpus.py").read_text(encoding="utf-8")


def test_old_openers_file_is_unchanged_for_v5_and_v6() -> None:
    from slm.data.prompts_v5 import opener_for

    row = next(r for r in PLAN if r["doc_type"] == "employee email")
    assert opener_for(row).startswith("the greeting line")
    old = yaml.safe_load((ROOT / "configs" / "openers.yaml").read_text(encoding="utf-8"))
    assert all(8 <= len(v) <= 12 for v in old.values())


@pytest.mark.parametrize("doc_type", ["customer notice"])
def test_two_line_openers_are_quoted_per_line(doc_type: str) -> None:
    text = openers_v2.prompt_text(openers_v2.opener(doc_type, "q-1"))
    assert text.count('"') == 4 and "on its own line" in text
