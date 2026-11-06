"""P02c5: meta-talk scan, leak classes, plan overrides."""

from __future__ import annotations

import json
from pathlib import Path

from slm.data import corpus
from slm.data.leakclass import signoff_start
from slm.data.metatalk import genuine_hits, scan


def test_genuine_metatalk_hits_and_clean_text() -> None:
    assert genuine_hits("Keep the inserted sentence short.")
    assert genuine_hits("Please place the marker exactly as received.")
    assert not genuine_hits("Watch the queue markers near the gate. Keep your tone calm and factual.")
    assert {n for n, _ in scan("Keep your tone. The model of care.")} == {"keep your", "the model"}


def test_signoff_start_is_the_last_desk_line_only() -> None:
    text = "One two three.\n\nFour five six.\nCompanion Animal Travel Desk"
    assert signoff_start(text) == len(corpus.tokens("One two three.\n\nFour five six."))
    assert signoff_start("One two three.\nFour five.") is None


def test_plan_override_changes_only_the_doc_type(tmp_path: Path) -> None:
    (tmp_path / "plan_overrides.json").write_text(json.dumps({"a": {"doc_type": "employee email"}}), encoding="utf-8")
    plan = [{"doc_id": "a", "doc_type": "newsletter blurb", "split": "test"}, {"doc_id": "b", "doc_type": "x"}]
    out = corpus.apply_plan_overrides(plan, tmp_path)
    assert out[0] == {"doc_id": "a", "doc_type": "employee email", "split": "test"} and out[1] == plan[1]
    assert corpus.apply_plan_overrides(plan, tmp_path / "none") == plan


def test_flags_split_disclosed_from_unflagged(tmp_path):
    from slm.data import corpus

    (tmp_path / "train.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "val.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "test.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "flags.json").write_text('{"leak_flag": {"val-0001": ["a b"]}, "meta_flag": ["val-0002"]}', encoding="utf-8")
    manifest = corpus.write_manifest(tmp_path)
    assert manifest["leak_flag"] == {"val-0001": ["a b"]}
    assert manifest["meta_flag"] == ["val-0002"]
    assert set(manifest["files"]) == {"train.jsonl", "val.jsonl", "test.jsonl"}
