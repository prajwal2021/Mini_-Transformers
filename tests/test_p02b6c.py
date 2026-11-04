"""P02b6c: v5 cohort rows, A1 eligibility, computed recommendation, early abort, per-type samples."""

from __future__ import annotations

import json
from pathlib import Path

from slm.data.pilot import MockBackend, a1_eligibility, a1_recommendation, run_pilot

ROOT = Path(__file__).resolve().parents[1]


def rows() -> list[dict]:
    path = ROOT / "data" / "pilot_v5" / "pilot_rows.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_pilot_v5_cohort_is_fresh_and_stratified() -> None:
    cohort = rows()
    earlier = set()
    for name in ("pilot", "pilot_v3", "pilot_v4"):
        earlier |= {
            json.loads(x)["doc_id"]
            for x in (ROOT / "data" / name / "pilot_rows.jsonl").read_text().splitlines()
        }
    assert len(cohort) == 40 and len({r["doc_id"] for r in cohort}) == 40
    assert not {r["doc_id"] for r in cohort} & earlier
    count = lambda t: sum(r["doc_type"] == t for r in cohort)  # noqa: E731
    assert min(count(t) for t in ("meeting minutes", "training handbook page", "policy manual section")) >= 6
    assert min(count(t) for t in ("complaint letter + reply", "employee email")) >= 5
    assert sum(set(r["modes"]) == {"templated"} for r in cohort) >= 15
    assert sum(set(r["modes"]) == {"paraphrased"} for r in cohort) >= 15
    assert sum(not r["fact_ids"] for r in cohort) >= 3
    assert sum(r["split"] != "train" for r in cohort) >= 3
    assert [r["doc_id"] for r in cohort] == sorted(r["doc_id"] for r in cohort)


def metrics(**over) -> dict:
    base = {"accepted_within_5": 0.98, "accept_by_type": {"a": (5, 5), "b": (4, 5)},
            "first_attempt_pass": 0.61, "projected_at_observed_attempts": 6.9,
            "opening_5gram_dup": 0.10}
    return {**base, **over}


def test_a1_eligibility_boundaries_and_recommendation() -> None:
    ok = a1_eligibility(metrics())
    assert all(ok[k] for k in "abcd")
    assert not a1_eligibility(metrics(accepted_within_5=0.96))["a"]
    assert not a1_eligibility(metrics(accept_by_type={"a": (5, 5), "b": (2, 5)}))["a"]
    assert not a1_eligibility(metrics(accept_by_type={"a": (5, 5), "b": (0, 5)}))["a"]
    assert not a1_eligibility(metrics(first_attempt_pass=0.59))["b"]
    assert not a1_eligibility(metrics(projected_at_observed_attempts=7.01))["c"]
    assert not a1_eligibility(metrics(opening_5gram_dup=0.101))["d"]
    none = a1_recommendation([], False)
    assert "Neither model is eligible" in none and "gpt-5.4" not in none
    some = a1_recommendation(["gpt-5.4-nano"], True)
    assert "gpt-5.4-nano" in some and "stopped early" in some and "C6" in some


def run_mock(tmp_path: Path, **kwargs):
    out = tmp_path / "pilot_v5"
    out.mkdir(exist_ok=True)
    (out / "api_config.json").write_text(json.dumps({
        m: {"config": {"api": "chat", "reasoning_effort": "none"}, "max_output_tokens": 700}
        for m in ("gpt-5.4-nano", "gpt-5.4-mini")}), encoding="utf-8")
    lines: list[str] = []
    backend = kwargs.pop("backend", MockBackend())
    code = run_pilot(
        backend, ["gpt-5.4-nano", "gpt-5.4-mini"], 40, out, tmp_path, tmp_path / "reports",
        tmp_path / "API_NOTES.md", "mock", echo=lines.append, suffix="_v5",
        rows_from=ROOT / "data" / "pilot_v5" / "pilot_rows.jsonl", prompt_version="v5",
        validator_version="v4", use_saved_api_config=True, session_cap=5.0, extended=True,
        a1_report=True, **kwargs,
    )
    return code, lines, out


def test_mock_v5_run_report_sections_and_per_type_samples(tmp_path: Path) -> None:
    code, lines, out = run_mock(tmp_path, early_abort_after=20)
    assert code == 0 and lines[0] == "MODE: MOCK (no spend)"
    report = (tmp_path / "reports" / "pilot_report_v5.md").read_text(encoding="utf-8")
    assert report.splitlines()[0] == "Client: mock"
    for text in ("## C1 at 3 and at 5 attempts", "## Acceptance within 5 attempts by doc type",
                 "## Amendment A1 eligibility", "| (a) ", "| (b) ", "| (c) ", "| (d) ",
                 "| V18 |", "| V15 |", "| V11 |", "| V1p |", "## Confound audit",
                 "## Mean actual/target words by doc type", "## Additional measures",
                 "projected full run at 1.4 attempts/doc", "**Recommendation:**"):
        assert text in report, text
    assert "prompt v3" not in report and "validator v2" not in report
    assert "P02b6-template-v5" in report and "validator v4" in report
    samples = (tmp_path / "reports" / "pilot_samples_v5.md").read_text(encoding="utf-8")
    for model in ("gpt-5.4-nano", "gpt-5.4-mini"):
        section = samples.split(f"## {model}")[1].split("\n## ")[0]
        assert "### Sample 6: accepted" in section
    attempts = [json.loads(x) for x in (out / "gpt-5.4-nano" / "attempts.jsonl").read_text().splitlines()]
    assert {"ask_words", "insertion_mode"} <= set(attempts[0]) and attempts[0]["validator_version"] == "v4"


def test_early_abort_stops_after_twenty_docs_when_both_models_are_below_threshold(tmp_path: Path) -> None:
    code, lines, out = run_mock(tmp_path, early_abort_after=20, early_abort_below=1.01)
    assert code == 0 and any("Early abort" in line for line in lines)
    report = (tmp_path / "reports" / "pilot_report_v5.md").read_text(encoding="utf-8")
    assert "EARLY ABORT after 20 docs" in report and "The run stopped early" in report
    docs = {json.loads(x)["doc_id"] for x in (out / "gpt-5.4-mini" / "attempts.jsonl").read_text().splitlines()}
    assert len(docs) == 20 and docs <= {r["doc_id"] for r in rows()[:20]}
