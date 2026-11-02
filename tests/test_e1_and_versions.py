"""P02b4: API-level E1 handling, version stamps, v3 prompt content (mock backend only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slm.data.budget import GlobalBudgetGuard
from slm.data.pilot import MockBackend, analyze_model, generate_model, run_pilot
from slm.data.prompts_v3 import build_prompt_v3, length_range, retry_feedback_v3

ROOT = Path(__file__).resolve().parents[1]
KB = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
POOLS = json.loads((ROOT / "data" / "kb" / "filler_pools.json").read_text(encoding="utf-8"))
PLAN = [
    json.loads(x)
    for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()
]
PRICING = {"gpt-5.4-nano": {"input_usd_per_million": 0.2, "output_usd_per_million": 1.25}}
CONFIG = {"api": "chat", "reasoning_effort": "none"}


def one_row() -> dict:
    return next(r for r in PLAN if r["split"] == "train" and len(r["fact_ids"]) == 2)


def run(tmp_path: Path, backend: MockBackend, prompt_version: str = "v3") -> list[dict]:
    guard = GlobalBudgetGuard(tmp_path, tmp_path / "ledger.jsonl", 10, 1, PRICING)
    generate_model(
        backend, "gpt-5.4-nano", CONFIG, [one_row()], KB, POOLS, guard, tmp_path,
        prompt_version=prompt_version, validator_version="v2",
    )
    path = tmp_path / "gpt-5.4-nano" / "attempts.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_e1_empty_response_is_retried_with_original_prompt(tmp_path: Path) -> None:
    backend = MockBackend(models=["gpt-5.4-nano"], violate_every=0, empty_first_calls=2)
    attempts = run(tmp_path, backend)
    assert len(attempts) == 1 and attempts[0]["ok"] and attempts[0]["attempt"] == 1
    assert attempts[0]["api_events"] == 2
    prompts = {call["probe"] for call in backend.calls}
    assert prompts == {False} and len(backend.calls) == 3
    events = (tmp_path / "gpt-5.4-nano" / "api_events.jsonl").read_text(encoding="utf-8")
    assert len(events.splitlines()) == 2 and '"kind": "E1"' in events
    ledger = [json.loads(x) for x in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert sum(1 for e in ledger if e.get("e1")) == 2 and len(ledger) == 3


def test_e1_after_three_tries_is_not_a_validator_failure(tmp_path: Path) -> None:
    backend = MockBackend(models=["gpt-5.4-nano"], violate_every=0, empty_first_calls=3)
    attempts = run(tmp_path, backend)
    assert len(attempts) == 1 and attempts[0]["api_failure"] and not attempts[0]["ok"]
    assert attempts[0]["reasons"][0].startswith("E1")
    row = one_row()
    events = [
        json.loads(x)
        for x in (tmp_path / "gpt-5.4-nano" / "api_events.jsonl").read_text().splitlines()
    ]
    metrics = analyze_model("gpt-5.4-nano", [row], attempts, KB, events=events)
    assert metrics["reason_histogram"] == {}
    assert metrics["e1_failed_docs"] == 1 and metrics["e1_events"] == 3
    assert metrics["accepted_within_3"] == 0.0


def test_every_record_carries_prompt_and_validator_version(tmp_path: Path) -> None:
    backend = MockBackend(models=["gpt-5.4-nano"], violate_every=0)
    attempts = run(tmp_path, backend)
    assert attempts[0]["prompt_version"] == "v3" and attempts[0]["validator_version"] == "v2"
    assert "raw_text" in attempts[0]
    ledger = [json.loads(x) for x in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert all(e["prompt_version"] == "v3" and e["validator_version"] == "v2" for e in ledger)


def test_validator_feedback_reaches_the_retry_prompt(tmp_path: Path) -> None:
    backend = MockBackend(models=["gpt-5.4-nano"], violate_every=1)
    attempts = run(tmp_path, backend)
    assert [a["attempt"] for a in attempts] == [1, 2] and attempts[1]["ok"]


def test_prompt_v3_content() -> None:
    rows = [r for r in PLAN if r["fact_ids"]]
    seen_types = set()
    for row in rows[:400]:
        prompt = build_prompt_v3(row, KB)
        seen_types.add(row["doc_type"])
        low, high = length_range(row["target_words"])
        assert f"between {low} and {high} words" in prompt and high <= 340
        assert "{" not in prompt and "}" not in prompt
        for fact_id, mode in zip(row["fact_ids"], row["modes"]):
            fact = next(f for f in KB["measured_facts"] if f["fact_id"] == fact_id)
            assert f'entity "{fact["entity"]}"; value "{fact["value"]}"' in prompt
            assert f"({mode})" in prompt and "meaning:" in prompt
        assert '"Aurelia Skyways" and "Companion Animal Travel Desk" exactly' in prompt
        assert "exactly once in the whole document" in prompt
        if row["doc_type"] == "internal chat thread":
            assert "Do not write a title, a greeting, or a sign-off" in prompt
            assert "If you sign off" not in prompt
        if row["doc_type"] == "complaint letter + reply":
            assert "ONE reply" in prompt and "contains no numbers" in prompt
    assert {"internal chat thread", "complaint letter + reply"} <= seen_types


def test_retry_feedback_v3_lists_at_most_three_failures() -> None:
    text = retry_feedback_v3([f"V{i} problem {i}" for i in range(1, 7)])
    assert text.count("\n1. ") == 1 and "3. V3" in text and "4. V4" not in text
    assert "3 further problems" in text and "from the start" in text


def test_run_pilot_v3_options_use_separate_outputs(tmp_path: Path) -> None:
    from slm.data.pilot import select_pilot_rows

    rows = select_pilot_rows(PLAN, 20261031)
    source = tmp_path / "old_rows.jsonl"
    source.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    out = tmp_path / "pilot_v3"
    out.mkdir()
    (out / "api_config.json").write_text(
        json.dumps({m: {"config": CONFIG, "max_output_tokens": 700}
                    for m in ("gpt-5.4-nano", "gpt-5.4-mini")}),
        encoding="utf-8",
    )
    lines: list[str] = []
    code = run_pilot(
        MockBackend(), ["gpt-5.4-nano", "gpt-5.4-mini"], 30, out, tmp_path, tmp_path / "reports",
        tmp_path / "API_NOTES.md", "mock", echo=lines.append, suffix="_v3", rows_from=source,
        prompt_version="v3", validator_version="v2", use_saved_api_config=True,
        extra_pilot_ledgers=[tmp_path / "old" / "ledger.jsonl"], session_cap=0.5, extended=True,
    )
    assert code == 0 and lines[0] == "MODE: MOCK (no spend)"
    report = (tmp_path / "reports" / "pilot_report_v3.md").read_text(encoding="utf-8")
    assert report.splitlines()[0] == "Client: mock"
    assert "P02b4-template-v3" in report and "validator v2" in report
    for text in ("First-attempt pass by mode", "First-attempt pass by doc type",
                 "projected full run at 1.4 attempts/doc", "empty responses (expected 0)"):
        assert text in report
    samples = (tmp_path / "reports" / "pilot_samples_v3.md").read_text(encoding="utf-8")
    assert samples.splitlines()[0] == "Client: mock"
    assert "additional accepted email" in samples
    saved = [json.loads(x) for x in (out / "pilot_rows.jsonl").read_text().splitlines()]
    assert [r["doc_id"] for r in saved] == [r["doc_id"] for r in rows]


@pytest.mark.parametrize("rule", ["session", "pilot"])
def test_session_and_pilot_caps_count_earlier_ledgers(tmp_path: Path, rule: str) -> None:
    from slm.data.budget import BudgetExceeded

    old = tmp_path / "old" / "ledger.jsonl"
    old.parent.mkdir()
    old.write_text(json.dumps({"usd": 0.95, "client": "openai"}) + "\n", encoding="utf-8")
    new = tmp_path / "new" / "ledger.jsonl"
    guard = GlobalBudgetGuard(tmp_path, new, 10, 1.0, PRICING, [old], session_cap_usd=0.5)
    assert guard.pilot_spent() == pytest.approx(0.95)
    with pytest.raises(BudgetExceeded):
        guard.reserve("gpt-5.4-nano", 1000, 60_000)  # 0.075 would breach the pilot cap of 1.0
    if rule == "session":
        old.write_text("", encoding="utf-8")
        new.parent.mkdir(exist_ok=True)
        new.write_text(json.dumps({"usd": 0.49, "client": "openai"}) + "\n", encoding="utf-8")
        with pytest.raises(BudgetExceeded):
            guard.reserve("gpt-5.4-nano", 1000, 20_000)  # breaches the 0.50 session cap


def test_replay_covers_every_stored_attempt(tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "replay_validator", ROOT / "scripts" / "replay_validator.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = tmp_path / "replay.md"
    assert module.main(["--pilot-dir", str(ROOT / "data" / "pilot"), "--out", str(out)]) == 0
    report = out.read_text(encoding="utf-8")
    total = sum(
        len((ROOT / "data" / "pilot" / m / "attempts.jsonl").read_text().splitlines())
        for m in ("gpt-5.4-nano", "gpt-5.4-mini")
    )
    assert total == 148
    per_attempt = report.split("## Per-attempt table")[1]
    assert per_attempt.count("| gpt-5.4-") == total
    for heading in ("## Summary", "## Exact-rule reason histogram under v2", "## Flips",
                    "### pass -> fail: ALL flips", "word distance"):
        assert heading in report
