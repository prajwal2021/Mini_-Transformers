# ruff: noqa: E501
"""R00 2: the real SFT / QA files follow the KB's own sft_split and match their manifest hashes."""

import json
import shutil
from pathlib import Path

import pytest

from slm.sft.build import read_jsonl, sha256_file, verify_datasets, write_real_datasets

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "data" / "kb" / "kb.json"


def test_committed_files_pass_every_split_assertion():
    report = verify_datasets(KB, ROOT / "data" / "sft", ROOT / "data" / "eval")
    assert all(report["checks"].values())
    assert report["rows"] == {"sft_train": 336, "sft_val": 24, "E0": 336, "E1": 144, "E2": 180}
    assert all(c == {"sft_train": 8, "sft_val": 2, "heldout": 10} for c in report["cell_counts"].values())


def test_manifest_hashes_match_the_files():
    m = json.loads((ROOT / "data" / "sft" / "manifest.json").read_text(encoding="utf-8"))
    for rel, digest in m["files"].items():
        assert sha256_file(ROOT / rel) == digest, rel
    assert m["kb_sha256"] == sha256_file(KB)


def test_rebuild_is_byte_identical(tmp_path):
    write_real_datasets(KB, tmp_path / "sft", tmp_path / "eval")
    for name in ("sft_train.jsonl", "sft_val.jsonl", "fact_split.json"):
        assert sha256_file(tmp_path / "sft" / name) == sha256_file(ROOT / "data" / "sft" / name)
    assert sha256_file(tmp_path / "eval" / "qa_test.jsonl") == sha256_file(
        ROOT / "data" / "eval" / "qa_test.jsonl")


@pytest.fixture
def copy(tmp_path):
    shutil.copytree(ROOT / "data" / "sft", tmp_path / "sft")
    shutil.copytree(ROOT / "data" / "eval", tmp_path / "eval")
    return tmp_path


def test_a_split_that_differs_from_the_kb_is_refused(copy):
    p = copy / "sft" / "fact_split.json"
    split = json.loads(p.read_text())
    a, b = [f for f, s in split.items() if s == "heldout"][:1][0], [f for f, s in split.items() if s == "sft_train"][0]
    split[a], split[b] = "sft_train", "heldout"
    p.write_text(json.dumps(split))
    with pytest.raises(AssertionError, match="fact_split.json equals kb"):
        verify_datasets(KB, copy / "sft", copy / "eval")


def test_an_e2_fact_leaking_into_sft_is_refused(copy):
    rows = read_jsonl(copy / "eval" / "qa_test.jsonl")
    train = read_jsonl(copy / "sft" / "sft_train.jsonl")
    leak = next(r for r in rows if r["subset"] == "E2")
    train.append({**train[0], "fact_id": leak["fact_id"]})
    (copy / "sft" / "sft_train.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in train), encoding="utf-8")
    with pytest.raises(AssertionError, match="E2 facts disjoint|sft_train facts"):
        verify_datasets(KB, copy / "sft", copy / "eval")


def test_an_e1_phrasing_seen_in_sft_is_refused(copy):
    rows = read_jsonl(copy / "eval" / "qa_test.jsonl")
    train = read_jsonl(copy / "sft" / "sft_train.jsonl")
    e1 = next(r for r in rows if r["subset"] == "E1")
    train.append({**train[0], "template_id": e1["template_id"], "question": e1["question"]})
    (copy / "sft" / "sft_train.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in train), encoding="utf-8")
    with pytest.raises(AssertionError, match="E1 templates unseen"):
        verify_datasets(KB, copy / "sft", copy / "eval")
