"""P02b pilot-tooling tests; mock backend only, no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slm.data.budget import BudgetExceeded, GlobalBudgetGuard
from slm.data.doc_types import DOC_TYPES
from slm.data.pilot import (
    PROBE_CONFIGS,
    MockBackend,
    analyze_model,
    check_models,
    probe_model,
    run_pilot,
    select_pilot_rows,
)

ROOT = Path(__file__).resolve().parents[1]
PRICING = {
    "gpt-5.4-nano": {"input_usd_per_million": 0.2, "output_usd_per_million": 1.25},
    "gpt-5.4-mini": {"input_usd_per_million": 0.75, "output_usd_per_million": 4.5},
}
MODELS = ["gpt-5.4-nano", "gpt-5.4-mini"]


def plan_rows() -> list[dict]:
    path = ROOT / "data" / "plan" / "plan.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def run_mock(tmp_path: Path, backend: MockBackend, models: list[str]) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = run_pilot(
        backend,
        models,
        30,
        tmp_path / "pilot",
        tmp_path,
        tmp_path / "reports",
        tmp_path / "API_NOTES.md",
        "mock",
        echo=lines.append,
    )
    return code, lines


def test_missing_model_id_stops_before_generation(tmp_path: Path) -> None:
    backend = MockBackend(models=["gpt-5.4-nano", "gpt-5.4-pro", "gpt-4o"])
    ok, missing, available = check_models(backend, MODELS)
    assert not ok and missing == ["gpt-5.4-mini"]
    assert available == ["gpt-5.4-nano", "gpt-5.4-pro"]
    code, lines = run_mock(tmp_path, backend, MODELS)
    assert code == 2
    assert any("gpt-5.4-pro" in line for line in lines)
    assert backend.calls == []
    assert not (tmp_path / "pilot" / "pilot_rows.jsonl").exists()


def test_probe_picks_first_working_configuration() -> None:
    errors = ["unsupported parameter: reasoning_effort 'minimal'", "bad low", None]
    probe = probe_model(MockBackend(probe_errors=errors), "gpt-5.4-nano")
    assert probe["config"] == PROBE_CONFIGS[2]
    assert [a["ok"] for a in probe["attempts"]] == [False, False, True]
    assert probe["attempts"][0]["error"] == errors[0]
    later = MockBackend(probe_errors=["e1", "e2", "e3", "e4", None])
    assert probe_model(later, "m")["config"] == PROBE_CONFIGS[4]
    assert probe_model(MockBackend(probe_errors=["a"] * 5), "m")["config"] is None


def test_pilot_rows_deterministic_and_cover_types() -> None:
    rows = plan_rows()
    first = select_pilot_rows(rows, 20261031)
    assert first == select_pilot_rows(rows, 20261031)
    assert len(first) == 30 and len({r["doc_id"] for r in first}) == 30
    counts: dict[str, int] = {}
    for r in first:
        counts[r["doc_type"]] = counts.get(r["doc_type"], 0) + 1
    assert set(counts) == set(DOC_TYPES)
    for name in (
        "employee email",
        "internal chat thread",
        "complaint letter + reply",
        "incident report",
    ):
        assert counts[name] >= 2
    cats = [r["pilot_category"] for r in first]
    names = ("templated", "paraphrased", "background", "val-iid", "val-novel")
    assert [cats.count(c) for c in names] == [10, 10, 4, 3, 3]
    templated = [r for r in first if r["pilot_category"] == "templated"]
    assert all(r["split"] == "train" and set(r["modes"]) == {"templated"} for r in templated)
    assert {len(r["fact_ids"]) for r in templated} == {1, 2, 3}


def test_global_budget_guard_counts_every_ledger(tmp_path: Path) -> None:
    (tmp_path / "raw").mkdir()
    main = tmp_path / "raw" / "ledger.jsonl"
    pilot = tmp_path / "pilot" / "ledger.jsonl"
    main.write_text(json.dumps({"usd": 9.5, "client": "openai"}) + "\n", encoding="utf-8")
    guard = GlobalBudgetGuard(tmp_path, pilot, 10.0, 1.0, PRICING)
    assert guard.global_spent() == pytest.approx(9.5)
    guard.reserve("gpt-5.4-nano", 1000, 900)
    with pytest.raises(BudgetExceeded):
        guard.reserve("gpt-5.4-mini", 100_000, 100_000)
    pilot.write_text(
        json.dumps({"usd": 0.45, "client": "openai"})
        + "\n"
        + json.dumps({"usd": 99.0, "client": "mock"})
        + "\n",
        encoding="utf-8",
    )
    assert guard.global_spent() == pytest.approx(9.95)
    with pytest.raises(BudgetExceeded):
        guard.reserve("gpt-5.4-nano", 1000, 90_000)
    main.write_text("", encoding="utf-8")
    pilot.write_text(json.dumps({"usd": 0.99, "client": "openai"}) + "\n", encoding="utf-8")
    with pytest.raises(BudgetExceeded):
        guard.reserve("gpt-5.4-mini", 10_000, 5_000)


def test_pilot_aborts_when_global_ledger_is_nearly_spent(tmp_path: Path) -> None:
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "ledger.jsonl").write_text(
        json.dumps({"usd": 9.999, "client": "openai"}) + "\n", encoding="utf-8"
    )
    backend = MockBackend()
    code, lines = run_mock(tmp_path, backend, MODELS)
    assert code == 3
    assert any("Refusing to start" in line for line in lines)
    assert backend.calls == []


def test_end_to_end_report_and_samples(tmp_path: Path) -> None:
    backend = MockBackend()
    code, lines = run_mock(tmp_path, backend, MODELS)
    assert code == 0
    assert any(line.startswith("Global spend") for line in lines)
    report = (tmp_path / "reports" / "pilot_report.md").read_text(encoding="utf-8")
    for key in ("C1", "C2", "C3", "C4", "C5", "C6"):
        assert f"| {key}:" in report
    assert "pending human" in report and "**Recommendation:**" in report
    samples = (tmp_path / "reports" / "pilot_samples.md").read_text(encoding="utf-8")
    for model in MODELS:
        section = samples.split(f"## {model}")[1].split("\n## ")[0]
        assert section.count("### Sample") == 5
        assert "(no accepted document of this kind)" not in section
        assert section.count("```text") == 5
    config = json.loads((tmp_path / "pilot" / "api_config.json").read_text(encoding="utf-8"))
    assert config["gpt-5.4-nano"]["config"] == PROBE_CONFIGS[0]
    assert (tmp_path / "API_NOTES.md").exists()
    ledger = (tmp_path / "pilot" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert ledger and all(json.loads(x)["client"] == "mock" for x in ledger)
    calls = len(backend.calls)
    again, _ = run_mock(tmp_path, backend, MODELS)
    assert again == 0 and len(backend.calls) == calls


def test_analysis_metrics_on_scripted_attempts() -> None:
    kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
    rows = select_pilot_rows(plan_rows(), 20261031)[:2]
    text = " ".join(["word"] * rows[0]["target_words"])
    base = {
        "doc_id": rows[0]["doc_id"],
        "input_tokens": 100,
        "output_tokens": 50,
        "reasoning_tokens": 5,
        "latency": 1.0,
        "usd": 0.001,
        "cached": False,
    }
    attempts = [
        {**base, "attempt": 1, "ok": False, "reasons": ["V3 x", "V8 y"], "text": ""},
        {**base, "attempt": 2, "ok": True, "reasons": [], "text": text},
    ]
    metrics = analyze_model("m", rows, attempts, kb)
    assert metrics["docs"] == 1 and metrics["first_attempt_pass"] == 0.0
    assert metrics["accepted_within_3"] == 1.0 and metrics["mean_attempts"] == 2.0
    assert metrics["reason_histogram"] == {"V3": 1, "V8": 1}
    assert metrics["projected_full_run"] == pytest.approx(0.002 * 2407)
    assert metrics["within_15pct"] == 1.0
    assert metrics["criteria"]["C1"] and not metrics["criteria"]["C2"]
