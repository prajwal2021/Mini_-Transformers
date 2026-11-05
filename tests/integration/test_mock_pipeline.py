"""I01 3: the end-to-end mock pipeline (script loaded by path; no sys.path edits)."""

import importlib.util
import json
from pathlib import Path

import pytest

from slm.analysis import banner

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_all_mock.py"


def load_script():
    spec = importlib.util.spec_from_file_location("run_all_mock", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_real_flag_is_refused(capsys):
    with pytest.raises(SystemExit) as exc:
        load_script().main(["--real"])
    assert exc.value.code == 2
    assert "refused" in capsys.readouterr().err


@pytest.mark.slow
def test_mock_pipeline_runs_end_to_end(tmp_path):
    out = tmp_path / "mock"
    timings = tmp_path / "timings.json"
    try:
        load_script().main(["--out", str(out), "--limit", "6", "--epochs", "3",
                            "--timings", str(timings)])
    finally:
        banner.set_label("SIMULATED")
    summary = json.loads(timings.read_text())
    assert summary["label"] == "MOCK"
    for stage in ("tokenizer_train", "token_cache", "probes_modelscorer", "build_analysis_tables",
                  "run_analysis", "build_report"):
        assert stage in summary["stage_seconds"]
    report = (out / "report" / "report.md").read_text(encoding="utf-8")
    assert "MOCK DATA - NOT RESULTS" in report and "SIMULATED" not in report
    assert (out / "report" / "report.pdf").exists()
    tables = json.loads((out / "analysis_inputs" / "tables_summary.json").read_text())
    assert tables["probes_per_fact"]["test/canonical"] == 1
    assert tables["probes_per_fact"]["test/novel"] == 2
