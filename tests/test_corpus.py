"""P02a planner, prompt, validator, budget, and mock-generator tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slm.data.budget import BudgetExceeded, BudgetGuard
from slm.data.doc_validator import validate_doc
from slm.data.generator import MockClient
from slm.data.planner import plan
from slm.data.prompts import build_prompt, template_hash

ROOT = Path(__file__).resolve().parents[1]


def load_kb() -> dict:
    return json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))


def load_pools() -> dict:
    return json.loads((ROOT / "data" / "kb" / "filler_pools.json").read_text(encoding="utf-8"))


def load_rows() -> list[dict]:
    return [
        json.loads(line)
        for line in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def good_case() -> tuple[str, dict, dict, dict]:
    kb = load_kb()
    row = next(row for row in load_rows() if row["split"] == "train" and row["fact_ids"])
    text, _usage = MockClient().generate(build_prompt(row, kb), row, kb)
    return text, row, kb, load_pools()


def test_plan_counts_deterministic_and_held_out() -> None:
    first = load_rows()
    second = plan()
    assert first == second
    train = [row for row in first if row["split"] == "train"]
    counts = {}
    kb = load_kb()
    for row in train:
        for fact_id in row["fact_ids"]:
            counts[fact_id] = counts.get(fact_id, 0) + 1
    assert all(counts[fact["fact_id"]] == fact["planned_mentions"] for fact in kb["measured_facts"])
    for split in ("val", "test"):
        counts = {fact["fact_id"]: 0 for fact in kb["measured_facts"]}
        for row in first:
            if row["split"] == split:
                for fact_id in row["fact_ids"]:
                    counts[fact_id] += 1
                    assert all(mode == "paraphrased" for mode in row["modes"])
        assert set(counts.values()) == {2}
    assert not any(
        row["split"] == "train"
        and row["style_card"]["author_role"] in {"quality auditor", "route editor"}
        for row in first
    )
    assert not any(
        row["split"] == "train" and row["style_card"]["tone"] == "apologetic" for row in first
    )


def test_prompt_hash_and_rendered_sections() -> None:
    text, row, kb, _pools = good_case()
    prompt = build_prompt(row, kb)
    assert template_hash()
    assert row["doc_type"] in prompt
    assert "Hard constraints" in prompt
    assert text


def test_validator_accepts_good_doc() -> None:
    text, row, kb, pools = good_case()
    assert validate_doc(text, row, kb, pools) == (True, [])


@pytest.mark.parametrize(
    ("rule", "mutate"),
    [
        (
            "V1",
            lambda text, row, kb: text.replace(
                next(
                    f["value"] for f in kb["measured_facts"] if f["fact_id"] == row["fact_ids"][0]
                ),
                "missing",
            ),
        ),
        (
            "V2",
            lambda text, row, kb: text.replace(
                next(
                    f["entity"] for f in kb["measured_facts"] if f["fact_id"] == row["fact_ids"][0]
                ),
                "the desk",
            ),
        ),
        (
            "V3",
            lambda text, row, kb: (
                text
                + " "
                + next(
                    f["value"] for f in kb["measured_facts"] if f["fact_id"] not in row["fact_ids"]
                )
            ),
        ),
        ("V4", lambda text, row, kb: text + " twenty"),
        ("V5", lambda text, row, kb: text + " Then Alpha Bravo Charlie arrived."),
        ("V6", lambda text, row, kb: text + " Question: why?"),
        ("V7", lambda text, row, kb: "# heading\n" + text),
        ("V8", lambda text, row, kb: "short"),
        ("V9", lambda text, row, kb: text + " " + "é" * (len(text) // 20)),
    ],
)
def test_validator_rejects_v_rules(rule: str, mutate) -> None:
    text, row, kb, pools = good_case()
    broken = mutate(text, row, kb)
    if rule == "V2":  # binding is judged at bank level since validator v5 (P02b7); v4 still has it
        from slm.data import doc_validator_v4

        ok, reasons = doc_validator_v4.validate_doc(broken, row, kb, pools)
    else:
        ok, reasons = validate_doc(broken, row, kb, pools)
    assert not ok
    assert any(reason.startswith(rule) for reason in reasons)


def test_budget_guard_rejects_before_spend(tmp_path: Path) -> None:
    guard = BudgetGuard(ledger_path=tmp_path / "ledger.jsonl", budget_usd=0.000001)
    with pytest.raises(BudgetExceeded):
        guard.reserve("gpt-5.4-nano", 1000, 900)


# ---- P02a2 additions -------------------------------------------------------------------------
import yaml  # noqa: E402

from slm.data.doc_types import DOC_TYPES, HARD_CAP_WORDS, target_words  # noqa: E402
from slm.data.planner import bin_independence, cost_table, pair_counts  # noqa: E402
from slm.data.prompts import TEMPLATE_VERSION  # noqa: E402

HELD_ROLES = {"quality auditor", "route editor"}


def load_config() -> dict:
    return yaml.safe_load((ROOT / "configs" / "generation.yaml").read_text(encoding="utf-8"))


def has_held_out(row: dict) -> bool:
    card = row["style_card"]
    return card["author_role"] in HELD_ROLES or card["tone"] == "apologetic"


def test_target_words_and_mean_tokens() -> None:
    config = load_config()
    rows = load_rows()
    assert all(r["target_words"] <= HARD_CAP_WORDS for r in rows)
    assert target_words("meeting minutes", "short") == round(240 * 0.7)
    assert target_words("complaint letter + reply", "long") == 330
    train = [r for r in rows if r["split"] == "train"]
    mean_words = sum(r["target_words"] for r in train) / len(train)
    mean_tokens = mean_words * config["tokens_per_word"]
    assert config["tokens_per_word"] == 1.35
    assert abs(mean_tokens - 350) <= 35
    assert abs(mean_words - 260) <= 13
    assert {k: v["base_words"] for k, v in DOC_TYPES.items()}["newsletter blurb"] == 150


def test_pair_cap_and_bin_independence() -> None:
    rows = load_rows()
    kb = load_kb()
    counts = pair_counts(rows)
    assert max(counts.values()) <= 6
    table = bin_independence(rows, kb["measured_facts"])
    assert len(table) == 6
    assert all(0.75 <= row["ratio"] <= 1.25 for row in table)
    train = [r for r in rows if r["split"] == "train" and r["fact_ids"]]
    cross = sum(len(r["families"]) > 1 for r in train)
    assert cross / len(train) <= 0.35
    for row in train:
        attrs = [
            f["attribute_id"] for f in kb["measured_facts"] if f["fact_id"] in row["fact_ids"]
        ]
        assert len(attrs) == len(set(attrs))


def test_iid_novel_regimes_and_held_out_rules() -> None:
    rows = load_rows()
    kb = load_kb()
    for split in ("val", "test"):
        for regime in ("iid", "novel"):
            docs = [r for r in rows if r["split"] == split and r["style_regime"] == regime]
            assert len(docs) == 60
            counts: dict[str, int] = {}
            for r in docs:
                assert len(r["fact_ids"]) == 2 and set(r["modes"]) == {"paraphrased"}
                for fid in r["fact_ids"]:
                    counts[fid] = counts.get(fid, 0) + 1
            assert set(counts.values()) == {1} and len(counts) == len(kb["measured_facts"])
            for r in docs:
                assert has_held_out(r) == (regime == "novel")
    assert not any(has_held_out(r) for r in rows if r["split"] == "train")
    assert {r["style_regime"] for r in rows if r["split"] == "train"} == {"train"}


def test_core_fact_uniformity() -> None:
    kb = load_kb()
    rows = load_rows()
    use: dict[str, int] = {item["core_id"]: 0 for item in kb["core_facts"]}
    for r in rows:
        for cid in r["core_fact_ids"]:
            use[cid] += 1
    mean = sum(use.values()) / len(use)
    assert len(use) == 25
    assert all(abs(v / mean - 1) <= 0.30 for v in use.values())


def test_prompt_v2_content() -> None:
    kb = load_kb()
    rows = load_rows()
    assert TEMPLATE_VERSION == "P02a2-template-v2"
    for row in (r for r in rows if r["fact_ids"] or r["doc_type"] == "internal chat thread"):
        prompt = build_prompt(row, kb)
        assert "{" not in prompt and "}" not in prompt
        assert "length_bucket" not in prompt and row["style_card"]["id"] not in prompt
        assert str(DOC_TYPES[row["doc_type"]]["guidance"]) in prompt
        assert f"about {row['target_words']} words" in prompt
        assert "you may mention these people and pet by name" in prompt
    for spec in DOC_TYPES.values():
        assert len(str(spec["guidance"]).split(". ")) in (2, 3)


def test_v5_allows_role_title_and_desk_phrases() -> None:
    text, row, kb, pools = good_case()
    role = row["style_card"]["author_role"].title()
    extra = f" {role}, Companion Animal Travel Desk, Aurelia Skyways."
    ok, reasons = validate_doc(text.replace("routine", "routine", 1) + extra, row, kb, pools)
    assert not any(reason.startswith("V5") for reason in reasons)


def test_cost_table_columns_and_tokens_from_words() -> None:
    kb, config, rows = load_kb(), load_config(), load_rows()
    table = cost_table(rows, kb, config)
    assert {
        "model", "tier", "reasoning_overhead", "input_tokens", "expected_output_tokens",
        "worst_case_output_tokens", "expected_cost", "worst_case_cost",
    } <= set(table[0])
    assert len(table) == 2 * 2 * 3
    base = next(t for t in table if t["reasoning_overhead"] == 0)
    expected = sum(r["target_words"] for r in rows) * config["tokens_per_word"]
    assert abs(base["expected_output_tokens"] - expected) <= 1
    text = (ROOT / "reports" / "tables" / "plan_stats.md").read_text(encoding="utf-8")
    for column in ("expected output tokens", "worst-case output tokens", "flag > $10"):
        assert column in text
