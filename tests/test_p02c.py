"""P02c: retrying backend, re-plan opener, rounds, 13-gram audit, manifest, run gates."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from slm.data import corpus
from slm.data.pilot import ApiError, CallResult
from slm.data.prompts_v5 import opener_for

ROOT = Path(__file__).resolve().parents[1]
PLAN = [json.loads(x) for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()]


class Flaky:
    def __init__(self, errors: list[str]) -> None:
        self.errors, self.calls = list(errors), 0

    def call(self, *args, **kwargs):
        self.calls += 1
        if self.errors:
            raise ApiError(self.errors.pop(0))
        return CallResult("ok", 1, 1, 0, 0.0)


def test_retry_backs_off_on_rate_limits_and_raises_other_errors() -> None:
    delays: list[float] = []
    backend = corpus.RetryingBackend(Flaky(["RateLimitError: 429", "APIConnectionError: x"]), sleep=delays.append)
    assert backend.call("m", "p", {}, 10).text == "ok" and delays == [2.0, 4.0] and backend.retries == 2
    with pytest.raises(ApiError):
        corpus.RetryingBackend(Flaky(["BadRequestError: nope"]), sleep=delays.append).call("m", "p", {}, 10)
    always = corpus.RetryingBackend(Flaky(["RateLimitError: 429"] * 9), tries=3, sleep=lambda s: None)
    with pytest.raises(ApiError):
        always.call("m", "p", {}, 10)
    assert always.inner.calls == 3


def test_replan_changes_the_opener_and_round_zero_is_unchanged() -> None:
    row = next(r for r in PLAN if r["doc_type"] == "employee email")
    base = opener_for(row)
    assert opener_for({**row, "replan": 0}) == base
    openers = {opener_for({**row, "replan": n}) for n in range(1, 8)}
    assert len(openers | {base}) > 1


def attempt(doc: str, ok: bool, n: int = 1, text: str = "t") -> dict:
    return {"doc_id": doc, "attempt": n, "ok": ok, "text": text, "reasons": [] if ok else ["V7 x"], "usd": 0.01}


def test_latest_accepted_round_wins_and_attempts_are_summed() -> None:
    rounds = {0: [attempt("a", True, text="first"), attempt("b", False), attempt("b", False, 2)],
              1: [attempt("b", True, text="redo")], 3: [attempt("a", True, text="regen")]}
    got = corpus.accepted_by_doc(rounds)
    assert got["a"][0] == 3 and got["a"][1]["text"] == "regen" and got["a"][2] == 2
    assert got["b"][0] == 1 and got["b"][2] == 3
    docs, missing = corpus.final_docs(PLAN[:2], {0: [attempt(PLAN[0]["doc_id"], True)]})
    assert [d["doc_id"] for d in docs] == [PLAN[0]["doc_id"]] and missing == [PLAN[1]["doc_id"]]
    assert set(docs[0]) >= {"doc_id", "split", "doc_type", "mode", "regime", "role", "tone", "fact_ids", "text", "attempts"}


WORDS = " ".join(f"w{i}" for i in range(30))


def test_leakage_and_near_duplicates_use_13_grams_after_normalisation() -> None:
    train = {"doc_id": "t1", "split": "train", "text": "intro " + WORDS + " outro"}
    clean = {"doc_id": "v1", "split": "val", "text": "other words entirely " + " ".join(f"z{i}" for i in range(20))}
    leaky = {"doc_id": "v2", "split": "test", "text": "x " + " ".join(f"w{i}" for i in range(5, 20)) + " y"}
    short = {"doc_id": "v3", "split": "val", "text": " ".join(f"w{i}" for i in range(5, 17))}  # only 12 words
    leaks = corpus.leakage([train, clean, leaky, short])
    assert leaks == {"v2": 3}
    typographic = {"doc_id": "v4", "split": "val", "text": WORDS.replace("w3 ", "w3 ")}
    assert corpus.leakage([train, typographic])["v4"] > 0
    twin = {"doc_id": "t2", "split": "train", "text": "intro " + WORDS + " different ending"}
    other = {"doc_id": "t3", "split": "train", "text": " ".join(f"q{i}" for i in range(40))}
    pairs = corpus.train_near_duplicates([train, twin, other])
    assert [(a, b) for a, b, _j in pairs] == [("t1", "t2")] and pairs[0][2] > 0.5
    assert corpus.exact_duplicates([train, {**train, "doc_id": "t9"}, other]) == [["t1", "t9"]]


def test_manifest_has_the_exact_format_and_hashes_match(tmp_path: Path) -> None:
    docs = [{"doc_id": f"{s}-1", "split": s, "doc_type": "x", "mode": "none", "regime": "train", "role": "r",
             "tone": "t", "fact_ids": [], "text": f"text {s}", "attempts": 1} for s in ("train", "val", "test")]
    corpus.write_split_files(tmp_path, docs)
    manifest = corpus.write_manifest(tmp_path)
    assert list(manifest) == ["version", "files"] and manifest["version"] == 1
    assert list(manifest["files"]) == ["train.jsonl", "val.jsonl", "test.jsonl"]
    for name, entry in manifest["files"].items():
        assert entry["split"] == name.split(".")[0]
        assert entry["sha256"] == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8")) == manifest


def test_the_committed_corpus_manifest_matches_the_files() -> None:
    path = ROOT / "data" / "corpus" / "manifest.json"
    if not path.exists():
        pytest.skip("corpus not generated yet")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["version"] == 1 and set(manifest["files"]) == {"train.jsonl", "val.jsonl", "test.jsonl"}
    for name, entry in manifest["files"].items():
        assert hashlib.sha256((path.parent / name).read_bytes()).hexdigest() == entry["sha256"], name
        assert entry["split"] == name.split(".")[0]


def load_runner():
    spec = importlib.util.spec_from_file_location("run_corpus", ROOT / "scripts" / "run_corpus.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gates_flag_each_threshold() -> None:
    module = load_runner()
    good = {"accepted_within_5": 0.97, "mean_attempts": 1.2, "projected_full_run": 5.0, "opening_5gram_dup": 0.03,
            "accept_by_type": {"a": (9, 10), "b": (10, 10)}}
    assert all(module.evaluate(good, 1.0).values())
    for key, value, flag in (("accepted_within_5", 0.94, "accepted_within_5"), ("mean_attempts", 1.5, "mean_attempts"),
                             ("projected_full_run", 6.5, "projected_cost"), ("opening_5gram_dup", 0.06, "opening_dup"),
                             ("accept_by_type", {"a": (16, 20)}, "every_type")):
        assert not module.evaluate({**good, key: value}, 1.0)[flag]
    assert not module.evaluate(good, 6.0)["spend"]


def test_sample_docs_cover_each_type_once_then_fill_up() -> None:
    docs = [{"doc_id": f"d{i}", "doc_type": f"type{i % 11}"} for i in range(200)]
    picks = corpus.sample_docs(docs)
    assert len(picks) == 12 and len({p["doc_type"] for p in picks}) == 11 and len({p["doc_id"] for p in picks}) == 12
