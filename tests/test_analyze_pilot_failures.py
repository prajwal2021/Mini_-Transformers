"""The pilot-failure analysis runs end to end on a tiny fixture (no API, no real pilot data)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from slm.data.generator import MockClient
from slm.data.mock_text import write_document

ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "analyze_pilot_failures", ROOT / "scripts" / "analyze_pilot_failures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_analysis_runs_on_tiny_fixture(tmp_path: Path) -> None:
    module = load_script()
    kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
    plan = [
        json.loads(x)
        for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    rows = [r for r in plan if r["split"] == "train" and len(r["fact_ids"]) == 2][:2]
    rows[0]["pilot_category"] = rows[1]["pilot_category"] = "paraphrased"
    pilot = tmp_path / "pilot"
    model_dir = pilot / "gpt-5.4-nano"
    model_dir.mkdir(parents=True)
    (pilot / "pilot_rows.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    attempts = []
    plan_attempts = [(rows[0], "V1"), (rows[0], None), (rows[1], "V8")]
    for n, (row, rule) in enumerate(plan_attempts, start=1):
        if rule:
            text = MockClient(violate=rule).generate("p", row, kb)[0]
        else:
            text = write_document(row, kb)
        reasons = []
        if rule:
            from slm.data.doc_validator import validate_doc

            reasons = validate_doc(text, row, kb, {})[1]
        attempts.append(
            {
                "doc_id": row["doc_id"],
                "attempt": 1 if n != 2 else 2,
                "ok": not reasons,
                "reasons": reasons,
                "text": text,
                "input_tokens": 500,
                "output_tokens": 600,
                "reasoning_tokens": 300,
                "latency": 1.0,
                "usd": 0.001,
                "cached": False,
            }
        )
    (model_dir / "attempts.jsonl").write_text(
        "".join(json.dumps(a) + "\n" for a in attempts), encoding="utf-8"
    )
    out = tmp_path / "failures.md"
    assert module.main(["--pilot-dir", str(pilot), "--out", str(out)]) == 0
    report = out.read_text(encoding="utf-8")
    for heading in (
        "## A. Attempt table",
        "## B. V1 sub-causes",
        "## C. V2",
        "## D. V5",
        "## E. V6",
        "## F. V8",
        "## G. Retry dynamics",
        "## H. Tokens and cost",
        "## I. Rejected attempts in full",
        "## J. Coverage gap",
    ):
        assert heading in report
    assert "HYPOTHETICAL" in report and "value missing" in report
    assert rows[0]["doc_id"] in report
