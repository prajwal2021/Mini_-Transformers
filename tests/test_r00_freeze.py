# ruff: noqa: E501
"""R00 3d/4: the PREREG freeze records hash + commit and refuses after any test read."""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from slm.guard import record_test_use
from slm.integration.freeze import FreezeRefused, find_test_evidence, freeze, verify

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    prereg = tmp_path / "PREREG.md"
    prereg.write_text("# Prereg\n\nbody\n", encoding="utf-8")
    run = tmp_path / "run"
    (run / "probes").mkdir(parents=True)
    return prereg, run, tmp_path / "ledger.jsonl"


def test_freeze_records_hash_commit_and_verifies(setup):
    prereg, run, ledger = setup
    rec = freeze(prereg, run, ledger, ROOT)
    assert len(rec["prereg_sha256"]) == 64 and rec["git"]["commit"]
    assert "Freeze record" in prereg.read_text(encoding="utf-8")
    assert verify(prereg)["prereg_sha256"] == rec["prereg_sha256"]
    assert freeze(prereg, run, ledger, ROOT)["already_frozen"] is True  # resume is a no-op


def test_editing_after_the_freeze_is_detected(setup):
    prereg, run, ledger = setup
    freeze(prereg, run, ledger, ROOT)
    prereg.write_text(prereg.read_text(encoding="utf-8").replace("body", "edited"), encoding="utf-8")
    with pytest.raises(FreezeRefused, match="edited after the freeze"):
        verify(prereg)


def test_refuses_after_a_ledger_entry(setup):
    prereg, run, ledger = setup
    record_test_use("a test read", log_path=ledger)
    with pytest.raises(FreezeRefused, match="ledger"):
        freeze(prereg, run, ledger, ROOT)
    assert "FREEZE:BEGIN" not in prereg.read_text(encoding="utf-8")


def test_refuses_after_a_test_split_probe_row(setup):
    prereg, run, ledger = setup
    pd.DataFrame({"split": ["val", "test"], "x": [1, 2]}).to_csv(run / "probes" / "probes_raw.csv", index=False)
    with pytest.raises(FreezeRefused, match="test-split rows"):
        freeze(prereg, run, ledger, ROOT)


def test_val_only_probes_do_not_block(setup):
    prereg, run, ledger = setup
    pd.DataFrame({"split": ["val"], "x": [1]}).to_csv(run / "probes" / "probes_raw.csv", index=False)
    assert find_test_evidence(run, ledger) == []


def test_refuses_after_qa_test_predictions(setup):
    prereg, run, ledger = setup
    (run / "qa").mkdir()
    (run / "qa" / "qa_predictions.csv").write_text("a\n1\n")
    with pytest.raises(FreezeRefused, match="QA test predictions"):
        freeze(prereg, run, ledger, ROOT)


def load_run_real():
    spec = importlib.util.spec_from_file_location("run_real", ROOT / "scripts" / "run_real.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_orchestrator_stage_list_and_configs():
    mod = load_run_real()
    assert mod.STAGES == ["tokenizer", "token_cache", "sweep", "sizing", "freeze", "pretrain", "probes",
                          "sft", "qa_eval", "tables", "analysis", "report"]
    assert set(mod.FUNCS) == set(mod.STAGES)
    import yaml
    real = yaml.safe_load((ROOT / "configs" / "real.yaml").read_text())
    assert real["mode"] == "real" and real["final_seeds"] == [0, 1, 2]
    assert real["sweep"]["grid"] == {"lr": [3e-4, 6e-4, 1e-3], "dropout": [0.0, 0.1, 0.2]}
    mock = yaml.safe_load((ROOT / "configs" / "real_mock.yaml").read_text())
    assert mock["mode"] == "mock" and "real_mock" in mock["ledger"] and mock["banner_label"] == "MOCK"


def test_real_mode_without_a_corpus_manifest_stops_cleanly(tmp_path):
    import yaml
    mod = load_run_real()
    cfg = yaml.safe_load((ROOT / "configs" / "real.yaml").read_text())
    cfg["out_dir"] = str(tmp_path / "out")
    cfg["corpus_manifest"] = str(tmp_path / "nope.json")
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg))
    # out_dir is joined to ROOT; an absolute path wins in pathlib
    with pytest.raises(SystemExit, match="does not exist"):
        mod.main(["--config", str(p), "--only", "tokenizer"])
    assert json.loads((tmp_path / "out" / "stages" / "tokenizer.json").read_text())["status"] == "failed"


def test_later_stages_refuse_without_a_freeze(tmp_path):
    import yaml
    mod = load_run_real()
    cfg = yaml.safe_load((ROOT / "configs" / "real_mock.yaml").read_text())
    cfg["out_dir"] = str(tmp_path / "o")
    cfg["prereg"] = str(tmp_path / "P.md")
    (tmp_path / "P.md").write_text("x\n")
    with pytest.raises(SystemExit, match="valid freeze"):
        mod.Ctx(cfg).require_freeze()
