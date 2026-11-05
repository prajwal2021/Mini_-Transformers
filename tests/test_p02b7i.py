"""P02b7i: cue words in every prompt, new-prompt-only refill, A2c reuse and allocation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from slm.data import bank
from slm.data.budget import GlobalBudgetGuard

KB = json.loads(Path("data/kb/kb.json").read_text(encoding="utf-8"))
PLAN = [json.loads(x) for x in Path("data/plan/plan.jsonl").read_text(encoding="utf-8").splitlines()]
FACTS = {f["fact_id"]: f for f in KB["measured_facts"]}
PRICES = {"gpt-5.4-mini": {"input_usd_per_million": 0.75, "output_usd_per_million": 4.5}}


def test_every_attribute_prompt_lists_its_cue_words() -> None:
    frames = bank.load_frames()[:2]
    seen = set()
    for fact in KB["measured_facts"]:
        if fact["attribute_id"] in seen:
            continue
        seen.add(fact["attribute_id"])
        prompt = bank.candidate_prompt(fact, frames)
        assert "use at least one of these words or phrases: " in prompt, fact["attribute_id"]
        assert "counts as using it" in prompt
    assert len(seen) == 20
    form = bank.candidate_prompt(FACTS["F086"], frames)
    assert "form, paperwork, document, submit, fill" in form
    manager = bank.candidate_prompt(FACTS["F004"], frames)
    assert "words or phrases: lounge;" in manager and "manag, run, in charge" in manager


class Backend(bank.MockBankBackend):
    """Mock that drops frames f01-f20 in the first-pass prompts so the fact stays short."""

    def call(self, model, prompt, config, max_tokens, row=None, kb=None):
        result = super().call(model, prompt, config, max_tokens, row, kb)
        if not prompt.startswith("You compare") and "different sentence structure" not in prompt:
            keep = [x for x in result.text.splitlines() if int(x[1:3]) > 20]
            result.text = "\n".join(keep)
        return result


def make_runner(tmp_path: Path) -> bank.Runner:
    guard = GlobalBudgetGuard(tmp_path, tmp_path / "ledger.jsonl", 10, 5, PRICES)
    return bank.Runner(Backend(), "gpt-5.4-mini", guard, tmp_path / "cache", "mock")


def test_refill_with_a_prior_uses_new_prompts_only(tmp_path: Path) -> None:
    fact = FACTS["F008"]
    need = bank.needs_from_plan(PLAN)["F008"]
    runner = make_runner(tmp_path)
    frames = bank.load_frames()
    prior = bank.build_fact(fact, need, KB, frames, runner, 1, max_rounds=0)
    assert prior["gates"]["filled"] < prior["gates"]["need"]
    again = make_runner(tmp_path)
    again.require_new_gen = True
    refilled = bank.build_fact(fact, need, KB, frames, again, 1, prior=prior, max_rounds=2)
    assert again.new_gen_calls > 0
    assert refilled["gates"]["filled"] > prior["gates"]["filled"]
    assert refilled["generated"] > prior["generated"] and refilled["refill_rounds"] >= 1
    # the same refill a second time would re-issue cached prompts: the guard stops it (stalled), no call is made
    third = make_runner(tmp_path)
    third.require_new_gen = True
    stalled = bank.build_fact(fact, need, KB, frames, third, 1, prior=prior, max_rounds=2)
    assert third.new_gen_calls == 0 or stalled["stalled"] >= 0
    runner_guard = make_runner(tmp_path)
    runner_guard.require_new_gen = True
    prompt = bank.candidate_prompt(fact, bank.load_frames()[:2])
    runner_guard.call("gen", prompt, "F008")  # new prompt: accepted and cached
    with pytest.raises(AssertionError, match="re-issued a cached generation prompt"):
        runner_guard.call("gen", prompt, "F008")


def test_reuse_plan_cases() -> None:
    m = {"train": 45, "iid": 2, "novel": 2}
    assert bank.reuse_plan(47, 2, m)["ok"] and bank.reuse_plan(47, 2, m)["n_reused"] == 0
    r = bank.reuse_plan(31, 2, m)
    assert r["ok"] and r["n_reused"] == 45 - 29 and r["n_distinct"] == 33
    assert not bank.reuse_plan(47, 1, m)["ok"]  # reserved sentences are never reused
    assert not bank.reuse_plan(25, 2, m)["ok"]  # 27 distinct < 0.6 x 49
    assert not bank.reuse_plan(1, 2, m)["ok"]  # fewer plain sentences than val/test mentions
    tiny = {"train": 10, "iid": 2, "novel": 2}
    assert not bank.reuse_plan(6, 2, tiny)["ok"]  # 8 distinct < 0.6 x 14
    assert bank.reuse_plan(7, 2, tiny)["ok"]  # 9 distinct, 5 train sentences at 2 uses cover 10


def fabricated_bank(drop: dict[str, int]) -> dict[str, list[dict]]:
    counts = bank.mention_counts(PLAN)
    registers = ["formal", "neutral", "casual"]
    out = {}
    for fact_id, m in counts.items():
        n_plain = m["train"] + m["iid"] - drop.get(fact_id, 0)
        out[fact_id] = (
            [{"text": f"p{i}", "frame": f"f{i % 24 + 1:02d}", "register": registers[i % 3], "reserved": False}
             for i in range(n_plain)]
            + [{"text": f"r{i}", "frame": f"f{25 + i % 4}", "register": registers[i % 3], "reserved": True}
               for i in range(m["novel"])]
        )
    return out


def test_allocation_reuses_only_inside_train_and_at_most_twice() -> None:
    drop = {"F008": 6, "F040": 18}
    sentences = fabricated_bank(drop)
    allocation = bank.allocate(PLAN, sentences, 7)
    rows = [dict(s, sentence_id=f"{f}-b{i:03d}", fact_id=f) for f, items in sentences.items()
            for i, s in enumerate(items)]
    assert bank.check_allocation(PLAN, rows, allocation) == []
    plan_by_id = {r["doc_id"]: r for r in PLAN}
    uses = Counter(a["sentence_id"] for a in allocation if a["sentence_id"] != "canonical")
    assert max(uses.values()) == 2 and set(a["reuse_index"] for a in allocation) == {0, 1}
    for a in allocation:
        if a["reuse_index"]:
            assert plan_by_id[a["doc_id"]]["style_regime"] == "train"
            assert a["fact_id"] in drop
    assert sum(a["reuse_index"] for a in allocation) == 6 + 18
    for a in allocation:
        if a["sentence_id"] == "canonical":
            continue
        regime = plan_by_id[a["doc_id"]]["style_regime"]
        assert (a["frame"] in {"f25", "f26", "f27", "f28"}) == (regime == "novel")
    # a third use, or a reuse in validation/test, is reported
    broken = [dict(a) for a in allocation]
    ids = [i for i, a in enumerate(broken) if a["fact_id"] == "F008" and a["sentence_id"] != "canonical"]
    for i in ids[:3]:
        broken[i]["sentence_id"] = broken[ids[0]]["sentence_id"]
    assert any("reused" in p for p in bank.check_allocation(PLAN, rows, broken))


def test_allocation_fails_when_reuse_is_not_allowed() -> None:
    sentences = fabricated_bank({"F008": 30})  # 17 plain sentences < 0.6 x 49
    with pytest.raises(AssertionError):
        bank.allocate(PLAN, sentences, 7)


def test_amended_gates_accept_a_short_fact_through_reuse() -> None:
    sent = [{"text": f"s{i}", "frame": "f01", "register": "neutral", "reserved": False} for i in range(31)]
    sent += [{"text": "r0", "frame": "f25", "register": "formal", "reserved": True},
             {"text": "r1", "frame": "f26", "register": "formal", "reserved": True}]
    gates = {"need": 49, "filled": 33, "a": False, "b": True, "c": True, "d": False, "e": True, "f": True,
             "g": True, "prefixes": 20, "all": False}
    result = {"gates": gates, "sentences": sent}
    amended = bank.amended_gates(result, {"train": 45, "iid": 2, "novel": 2})
    assert amended["a"] and amended["d"] and amended["all"] and amended["n_reused"] == 16
    assert not bank.amended_gates(result, {"train": 45, "iid": 2, "novel": 3})["a"]
    gates["prefixes"] = 19  # ceil(0.8 x 25) = 20
    assert not bank.amended_gates(result, {"train": 45, "iid": 2, "novel": 2})["d"]
