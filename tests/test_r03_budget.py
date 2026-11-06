# ruff: noqa: E501
"""R03: the E* rule, the 2E* schedule, step-scaled warmup/logging, the freeze record, SFT from E*."""

import json
import shutil
from pathlib import Path

import pytest

from slm.integration import freeze as F
from slm.train import TrainConfig
from slm.train.budget import (
    SCHEDULE,
    decision_markdown,
    final_schedule,
    schedule_upto,
    select_budget,
)

ROOT = Path(__file__).resolve().parents[1]


def rows(cfg, rates, losses, epochs=SCHEDULE):
    return [{"config": cfg, "epoch": e, "stored_rate": r, "val_loss": v} for e, r, v in zip(epochs, rates, losses, strict=False)]


# ---- the rule -----------------------------------------------------------------------------------


def test_e_star_is_the_earliest_checkpoint_within_the_tolerance_of_the_configs_best():
    r = rows("a", [0.10, 0.20, 0.30, 0.38, 0.395, 0.40, 0.40], [5, 4.5, 4.2, 4.0, 4.1, 4.3, 4.6])
    sel = select_budget(r)
    assert sel["config"] == "a" and sel["best_rate"] == 0.40
    assert sel["e_star"] == 8  # rate 0.395 at epoch 8 is the first within 0.01 of 0.40
    assert sel["val_loss_optimal_epoch"] == 5 and sel["val_loss_optimal_epoch"] != sel["e_star"]  # both reported
    assert sel["peak_rate_epoch"] == 12 and sel["rate_at_val_loss_optimal_epoch"] == pytest.approx(0.38)


def test_config_with_the_best_rate_wins_but_near_ties_go_to_the_lower_validation_loss():
    a = rows("a", [0.1, 0.30, 0.32], [5, 4.0, 4.5], epochs=(1, 2, 3))
    b = rows("b", [0.1, 0.30, 0.325], [5, 3.5, 4.0], epochs=(1, 2, 3))  # best 0.325 vs 0.32: within 0.01, lower val loss
    c = rows("c", [0.1, 0.2, 0.40], [5, 4.0, 3.0], epochs=(1, 2, 3))
    assert select_budget(a + b)["config"] == "b"
    assert select_budget(a + b + c)["config"] == "c"  # 0.40 is clearly better, its low loss is not even needed
    d = rows("d", [0.1, 0.2, 0.2], [5, 2.0, 2.0], epochs=(1, 2, 3))
    assert select_budget(a + b + d)["config"] == "b"  # a low loss does not rescue a clearly worse probe rate


def test_exact_ties_take_the_first_config_in_grid_order():
    a = rows("a", [0.2, 0.3], [4.0, 4.0], epochs=(1, 2))
    b = rows("b", [0.2, 0.3], [4.0, 4.0], epochs=(1, 2))
    assert select_budget(a + b)["config"] == "a"
    assert select_budget(b + a)["config"] == "b"


def test_val_loss_never_chooses_e_star_even_when_it_bottoms_out_early():
    r = rows("a", [0.05, 0.10, 0.20, 0.30, 0.35, 0.45], [3.0, 3.1, 3.3, 3.6, 3.9, 4.2], epochs=(1, 2, 3, 5, 8, 12))
    sel = select_budget(r)
    assert sel["val_loss_optimal_epoch"] == 1 and sel["e_star"] == 12


def test_selection_ignores_everything_but_the_four_keys():
    r = rows("a", [0.1, 0.4], [4, 3], epochs=(1, 2))
    r2 = [{**x, "test_stored_rate": 0.99, "qa": 1.0} for x in r]
    assert select_budget(r) == select_budget(r2)


def test_final_schedule_trains_to_two_e_star_capped_and_saves_both():
    assert final_schedule(8) == (16, [1, 2, 3, 5, 8, 12, 16])
    total, ck = final_schedule(40)
    assert total == 60 and ck[-1] == 60 and 40 in ck
    total, ck = final_schedule(60)
    assert total == 60 and ck.count(60) == 1
    total, ck = final_schedule(7)  # E* off the log schedule is still saved
    assert total == 14 and 7 in ck and 14 in ck
    assert schedule_upto(12) == [1, 2, 3, 5, 8, 12]


def test_decision_table_lists_every_config_and_checkpoint_and_marks_e_star():
    r = rows("a", [0.1, 0.4, 0.4], [5, 4, 4.5], epochs=(1, 2, 3)) + rows("b", [0.1, 0.2, 0.3], [5, 4, 3], epochs=(1, 2, 3))
    sel = select_budget(r)
    md = decision_markdown(r, sel, {"a": 0.08, "b": 0.08}, {"a": 0.13, "b": 0.13}, "MOCK")
    assert "NOTHING HERE IS A RESULT" in md and "**E\\* = 2**" in md and "| **a** |" in md
    assert "0.400 / 4.00*E" in md and "0.080" in md and "0.130" in md
    assert md.count("\n| ") == 3  # header row + one row per config


# ---- step-scaled schedule -------------------------------------------------------------------------


def test_warmup_is_five_percent_of_the_steps_with_a_floor_and_a_ceiling():
    base = TrainConfig(batch_size=32, warmup_frac=0.05, min_warmup_steps=10, val_evals_per_run=40, log_points_per_run=200)
    c = base.resolve(45 * 60)  # partial-corpus numbers: ~45 steps per epoch, 60 epochs
    assert (c.warmup_steps, c.val_every, c.log_every) == (135, 67, 13)
    assert base.resolve(100).warmup_steps == 10 and base.resolve(100).val_every == 2
    assert base.resolve(12).warmup_steps == 6  # never more than half the run
    assert base.resolve(1).val_every == 1 and base.resolve(1).log_every == 1


def test_unset_per_run_fields_keep_the_given_values():
    cfg = TrainConfig(warmup_steps=7, val_every=9, log_every=3)
    assert cfg.resolve(1000) == cfg


def test_steps_per_epoch_is_the_ceiling_of_sequences_over_batch():
    assert TrainConfig(batch_size=32).steps_per_epoch(1441) == 46
    assert TrainConfig(batch_size=16).steps_per_epoch(1441) == 91


def test_train_yaml_is_the_single_source_of_the_scaling():
    cfg = TrainConfig.from_yaml(ROOT / "configs" / "train.yaml")
    assert (cfg.warmup_frac, cfg.min_warmup_steps, cfg.val_evals_per_run, cfg.log_points_per_run) == (0.05, 10, 40, 200)
    assert cfg.min_lr_ratio == 0.1  # cosine to 10% of peak


# ---- freeze: config hash and E* recorded; test-split ledger entries refuse -------------------------


@pytest.fixture
def frz(tmp_path):
    prereg = tmp_path / "P.md"
    prereg.write_text("# prereg\n", encoding="utf-8")
    return prereg, tmp_path / "run", tmp_path / "ledger.jsonl"


def test_freeze_records_the_config_hash_and_e_star(frz):
    prereg, run, ledger = frz
    rec = F.freeze(prereg, run, ledger, ROOT, extra={"config_sha256": "ab" * 32, "e_star": 8, "total_epochs": 16})
    text = prereg.read_text(encoding="utf-8")
    assert "| e_star | `8` |" in text and "`" + "ab" * 32 + "`" in text
    assert F.verify(prereg)["extra"]["e_star"] == 8 and rec["extra"]["total_epochs"] == 16


def test_ledger_with_a_test_split_entry_refuses_and_other_lines_do_not(frz):
    prereg, run, ledger = frz
    ledger.write_text(json.dumps({"split": "val", "purpose": "x"}) + "\n", encoding="utf-8")
    assert F.find_test_evidence(run, ledger) == []
    ledger.write_text(json.dumps({"split": "test", "purpose": "QA test read"}) + "\n", encoding="utf-8")
    with pytest.raises(F.FreezeRefused, match="1 test-split entry"):
        F.freeze(prereg, run, ledger, ROOT, extra={"e_star": 3})
    assert "FREEZE:BEGIN" not in prereg.read_text(encoding="utf-8")
    ledger.write_text("not json\n", encoding="utf-8")  # unreadable = treated as a test read
    with pytest.raises(F.FreezeRefused):
        F.freeze(prereg, run, ledger, ROOT)


def test_freeze_cli_reads_the_config_and_final_config(frz, tmp_path):
    import importlib.util

    prereg, run, ledger = frz
    cfgf = tmp_path / "c.yaml"
    cfgf.write_text("mode: real\n")
    fin = tmp_path / "final_config.json"
    fin.write_text(json.dumps({"primary_epoch": 12, "epochs": 24, "size": "small", "lr": 0.001, "dropout": 0.0, "batch_size": 16, "val_loss_optimal_epoch": 3}))
    spec = importlib.util.spec_from_file_location("freeze_prereg", ROOT / "scripts" / "freeze_prereg.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--prereg", str(prereg), "--run-dir", str(run), "--ledger", str(ledger), "--config", str(cfgf), "--final-config", str(fin)]) == 0
    extra = F.verify(prereg)["extra"]
    assert extra["e_star"] == 12 and extra["val_loss_optimal_epoch"] == 3 and len(extra["config_sha256"]) == 64
    ledger.write_text(json.dumps({"split": "test"}) + "\n")
    fresh = tmp_path / "P2.md"
    fresh.write_text("# x\n")
    assert mod.main(["--prereg", str(fresh), "--run-dir", str(run), "--ledger", str(ledger)]) == 1


# ---- SFT starts from the checkpoint of E* ----------------------------------------------------------


def test_sft_starts_from_the_requested_pretraining_epoch(tmp_path, monkeypatch):
    from slm.sft_train import runner

    seen = []
    monkeypatch.setattr(runner, "prepare_sft_data", lambda *a, **k: (None, None))
    monkeypatch.setattr(runner, "sft_run", lambda ckpt, *a, **k: seen.append(Path(ckpt).name) or {"epochs_done": 1})
    for e in (8, 16):
        d = tmp_path / "pre" / "seed0" / "checkpoints"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"epoch_{e:03d}.pt").write_bytes(b"x")
    cfg = type("C", (), {"seeds": (0,)})()
    tok = type("T", (), {"hash": lambda self: "h"})()
    man = type("M", (), {"source": "m.json"})()
    runner.run_sft_seeds("sft", tmp_path / "pre", man, tok, cfg, 64, tmp_path, pretrain_epoch=8)
    runner.run_sft_seeds("sft", tmp_path / "pre", man, tok, cfg, 64, tmp_path)
    assert seen == ["epoch_008.pt", "epoch_016.pt"]  # E*, then (default) the last epoch


# ---- the sweep end to end on a tiny model ------------------------------------------------------------


@pytest.mark.slow
def test_budget_sweep_scores_validation_probes_only_and_removes_checkpoints(tmp_path):
    from slm.integration.budget_sweep import run_budget_sweep
    from slm.model import ModelConfig
    from slm.split_manifest import build_manifest
    from slm.tokenizer import train_tokenizer
    from slm.train.runner import prepare_data

    for n in ("mock_corpus_train.txt", "mock_corpus_val.txt"):
        shutil.copy(ROOT / "tests" / "fixtures" / n, tmp_path / n)
    man = build_manifest({tmp_path / "mock_corpus_train.txt": "train", tmp_path / "mock_corpus_val.txt": "val"}, tmp_path / "s.json")
    tok = train_tokenizer(man, 4096, min_frequency=1)
    cfg_m = ModelConfig(vocab_size=4096, context_len=64, n_layer=1, n_head=2, d_model=32, d_ff=64, dropout=0.0)
    cfg = TrainConfig(bf16=False, warmup_frac=0.05, val_evals_per_run=4, log_points_per_run=8)
    tr, va, meta = prepare_data(man, tok, cfg_m, cfg, tmp_path / "cache")
    res = run_budget_sweep(cfg_m, cfg, tr, va, tok, ROOT / "data" / "kb" / "kb.json", tmp_path / "sweep",
                           grid={"lr": [1e-3], "dropout": [0.0], "batch_size": [16, 32]}, max_epochs=2, schedule=(1, 2),
                           meta_for=meta, label="MOCK", decision_path=tmp_path / "decision.md")
    assert len(res["results"]) == 2 and {r["epoch"] for r in res["rows"]} == {1, 2}
    ch = res["chosen"]
    assert ch["e_star"] in (1, 2) and ch["batch_size"] in (16, 32) and 0 <= ch["init_stored_rate"] <= 1
    assert all(r["n_probes"] == 240 for r in res["rows"])  # 120 facts x 2 val probes, no test probe
    for r in res["results"]:
        assert not (tmp_path / "sweep" / r["config"] / "seed0" / "checkpoints").exists()
        assert r["steps_per_epoch"] > 0 and r["warmup_steps"] >= 1
    assert "NOTHING HERE IS A RESULT" in (tmp_path / "decision.md").read_text(encoding="utf-8")
    assert (tmp_path / "sweep" / "chosen.json").exists()


def test_decision_table_warns_when_the_best_rate_is_not_above_chance():
    r = rows("a", [0.10, 0.11, 0.105], [5, 4, 4.5], epochs=(1, 2, 3))
    md = decision_markdown(r, select_budget(r), {"a": 0.108}, {"a": 0.10}, "MOCK")
    assert "WARNING" in md and "no storage is detected" in md
    r = rows("a", [0.10, 0.30, 0.35], [5, 4, 4.5], epochs=(1, 2, 3))
    assert "WARNING" not in decision_markdown(r, select_budget(r), {"a": 0.108}, {"a": 0.10}, "REAL")
