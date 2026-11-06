# ruff: noqa: E501
"""R04: E* rule v2 (smoothed, 1 SE, chance guard), separate sweep seed, identical schedule, two-stage sweep + ETA, dirty-tree freeze."""

import json
import math
import subprocess
from pathlib import Path

import pytest
import yaml

from slm.integration import freeze as F
from slm.integration.budget_sweep import SweepTooLong, project_hours
from slm.train.budget import (
    SCHEDULE,
    SWEEP_SEED,
    clustered_se,
    decision_markdown,
    schedule_hash,
    schedule_upto,
    select_budget,
    smooth,
)

ROOT = Path(__file__).resolve().parents[1]
SE = 0.02


def rows(cfg, rates, losses, epochs=SCHEDULE, se=SE):
    return [{"config": cfg, "epoch": e, "stored_rate": r, "val_loss": v, "se": se} for e, r, v in zip(epochs, rates, losses, strict=False)]


# ---- (a) a clear plateau picks the plateau start ----------------------------------------------------


def test_clear_plateau_picks_the_plateau_start_not_the_noisy_peak():
    ep = (1, 2, 3, 5, 8, 12, 16, 20, 25, 30)
    rate = [0.10, 0.12, 0.25, 0.45, 0.60, 0.61, 0.60, 0.62, 0.60, 0.60]  # rises, plateau ~0.60-0.62 from epoch 8
    loss = [5.0, 4.0, 3.5, 3.2, 3.0, 3.1, 3.3, 3.6, 3.9, 4.2]
    sel = select_budget(rows("a", rate, loss, ep), {"a": 0.10})
    assert sel["no_val_storage"] is False and sel["config"] == "a"
    # smoothed: .553 at epoch 8 (more than 1 SE = 0.02 below the best smoothed .61), .603 at epoch 12 (within): E* = 12
    assert sel["e_star"] == 12 and sel["e_star"] > sel["val_loss_optimal_epoch"] == 8
    assert sel["best_rate"] == pytest.approx(0.61) and sel["peak_rate_epoch"] == 16


def test_plateau_start_is_reported_next_to_the_val_loss_optimum():
    ep = (1, 2, 3, 5, 8, 12, 16)
    rate = [0.05, 0.10, 0.30, 0.50, 0.55, 0.56, 0.55]
    loss = [3.0, 3.1, 3.3, 3.6, 3.9, 4.2, 4.5]  # validation loss bottoms out at epoch 1
    sel = select_budget(rows("a", rate, loss, ep), {"a": 0.05})
    assert sel["val_loss_optimal_epoch"] == 1 and sel["e_star"] == 8  # storage keeps improving after the val-loss minimum


# ---- (b) a noisy at-chance curve triggers the guard -------------------------------------------------


def test_noisy_at_chance_curve_triggers_the_guard_and_uses_min_val_loss():
    ep = (1, 2, 3, 5, 8, 12, 16, 20)
    rate = [0.117, 0.058, 0.108, 0.100, 0.117, 0.092, 0.110, 0.104]  # the R03 mock pattern: everything at chance
    loss = [5.0, 4.4, 4.0, 3.8, 3.5, 3.7, 4.0, 4.5]
    sel = select_budget(rows("a", rate, loss, ep, se=0.02), {"a": 0.108})
    assert sel["no_val_storage"] is True
    assert sel["e_star"] == 8 == sel["val_loss_optimal_epoch"]  # not the noisy-best epoch 1
    md = decision_markdown(rows("a", rate, loss, ep, se=0.02), sel, {"a": 0.108}, {"a": 0.10}, "MOCK")
    assert "WARNING" in md and "`no_val_storage`: **true**" in md and "minimum validation loss" in md


def test_guard_does_not_fire_when_the_best_exceeds_init_by_more_than_two_se():
    r = rows("a", [0.10, 0.30, 0.40], [5, 4, 4.5], epochs=(1, 2, 3))
    assert select_budget(r, {"a": 0.108})["no_val_storage"] is False
    r = rows("a", [0.10, 0.12, 0.13], [5, 4, 4.5], epochs=(1, 2, 3), se=0.03)  # smoothed best 0.12 - 0.108 < 2 x 0.03
    assert select_budget(r, {"a": 0.108})["no_val_storage"] is True


# ---- (c) determinism ------------------------------------------------------------------------------


def test_the_rule_is_deterministic_and_ignores_everything_but_its_keys():
    ep = (1, 2, 3, 5, 8)
    a = rows("a", [0.1, 0.3, 0.45, 0.5, 0.5], [5, 4, 3.5, 3.6, 3.9], ep)
    b = rows("b", [0.1, 0.25, 0.4, 0.46, 0.48], [5, 4, 3.4, 3.3, 3.5], ep)
    init = {"a": 0.1, "b": 0.1}
    s1 = select_budget(a + b, init)
    assert s1 == select_budget(a + b, init) == select_budget([dict(r) for r in a + b], init)
    noisy = [{**r, "test_stored_rate": 0.99, "qa": 1.0} for r in a + b]
    assert select_budget(noisy, init) == s1
    assert select_budget(b + a, init)["config"] == s1["config"]  # near-ties go to the lower validation loss, not to input order


def test_near_ties_within_one_se_go_to_the_lower_validation_loss_else_the_better_rate_wins():
    ep = (1, 2, 3)
    a = rows("a", [0.1, 0.40, 0.40], [5, 4.0, 4.5], ep)
    b = rows("b", [0.1, 0.395, 0.395], [5, 3.5, 4.0], ep)  # within 1 SE of a, lower val loss
    c = rows("c", [0.1, 0.30, 0.30], [5, 2.0, 2.0], ep)  # clearly worse: low loss does not rescue it
    init = {"a": 0.1, "b": 0.1, "c": 0.1}
    assert select_budget(a + b + c, init)["config"] == "b"
    assert select_budget(a + c, init)["config"] == "a"


def test_smoothing_is_a_centred_three_point_average_shortened_at_the_ends():
    out = smooth(rows("a", [0.0, 0.3, 0.6, 0.9], [1, 1, 1, 1], (1, 2, 3, 4)))
    assert [round(x, 3) for x, _ in out] == [0.15, 0.3, 0.6, 0.75]
    assert all(se == pytest.approx(SE) for _, se in out)


def test_se_falls_back_to_binomial_and_clusters_by_fact():
    r = [{"config": "a", "epoch": 1, "stored_rate": 0.5, "val_loss": 1.0, "n_probes": 100}]
    assert smooth(r)[0][1] == pytest.approx(0.05)
    assert clustered_se([0.0, 1.0, 0.0, 1.0]) == pytest.approx(math.sqrt((4 * 0.25) / 3 / 4))  # sd 0.577 / sqrt(4)
    assert math.isnan(clustered_se([0.5]))
    with pytest.raises(ValueError):
        smooth([{"config": "a", "epoch": 1, "stored_rate": 0.5, "val_loss": 1.0}])


# ---- sweep seed, identical schedule, two-stage run list, ETA -----------------------------------------


@pytest.mark.parametrize("name", ["real.yaml", "real_mock.yaml", "partial_dryrun.yaml"])
def test_sweep_seed_is_not_among_the_final_seeds(name):
    cfg = yaml.safe_load((ROOT / "configs" / name).read_text(encoding="utf-8"))
    assert cfg["sweep"]["seed"] == SWEEP_SEED == 100
    assert cfg["sweep"]["seed"] not in cfg["final_seeds"]
    assert len(cfg["sweep"]["grid"].get("batch_size", [32])) == 1  # stage 1 at ONE batch size


def test_the_sweep_function_refuses_a_final_seed():
    from slm.integration.budget_sweep import run_budget_sweep

    with pytest.raises(ValueError, match="must not be one of the final seeds"):
        run_budget_sweep(None, None, None, None, None, ROOT / "data" / "kb" / "kb.json", ROOT / "runs" / "never", seed=1, final_seeds=(0, 1, 2))


def test_real_config_is_the_two_stage_grid_with_the_ceiling():
    sw = yaml.safe_load((ROOT / "configs" / "real.yaml").read_text(encoding="utf-8"))["sweep"]
    assert sw["grid"] == {"lr": [3e-4, 6e-4, 1e-3], "dropout": [0.0, 0.1], "batch_size": [32]}
    assert sw["stage2_batch"] == 16 and sw["epochs"] == 60 and sw["max_hours"] == 3


def test_eta_projection_and_abort_message():
    # first run 20 min: (6 + 1 + 2.3) x 20 min = 3.1 h > 3 h
    assert project_hours(1200, 6, 1, 2.3) == pytest.approx(1200 * 9.3 / 3600)
    assert project_hours(600, 6, 1, 2.3) < 3
    assert issubclass(SweepTooLong, RuntimeError)


def test_sweep_aborts_after_the_first_run_when_the_projection_exceeds_the_limit(tmp_path, monkeypatch):
    from slm.integration import budget_sweep as B

    calls = []

    def fake_run_config(name, *a, **k):
        calls.append(name)
        return {"config": name, "status": "ok", "rows": [], "init": {"stored_rate": 0.1, "null_rate": 0.1}, "seconds": 5000.0}

    monkeypatch.setattr(B, "run_config", fake_run_config)
    monkeypatch.setattr(B, "val_probes", lambda kb: None)
    cfg = type("C", (), {"batch_size": 32, "with_": lambda self, **k: self})()
    with pytest.raises(SweepTooLong, match="exceeds the 3 h limit"):
        B.run_budget_sweep(None, cfg, None, None, None, "kb", tmp_path, grid={"lr": [1e-3, 3e-4], "dropout": [0.0], "batch_size": [32]},
                           max_epochs=2, schedule=(1, 2), large_factor=2.3, max_hours=3, log=lambda *a: None)
    assert len(calls) == 1  # aborted before the second run
    assert json.loads((tmp_path / "eta.json").read_text())["projected_hours"] > 3


def test_final_runs_use_the_sweeps_schedule_and_no_2e_star_remains():
    h = schedule_hash(60, schedule_upto(60), 0.05, 10, 0.1)
    assert h == schedule_hash(60, list(SCHEDULE), 0.05, 10, 0.1) and h != schedule_hash(120, schedule_upto(60), 0.05, 10, 0.1)
    import slm.train.budget as budget

    assert not hasattr(budget, "final_schedule")
    for rel in ("scripts/run_real.py", "docs/PREREG.md", "docs/README.md", "src/slm/integration/report_inputs.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "2E\\*" not in text and "2E*" not in text, rel
    run_real = (ROOT / "scripts" / "run_real.py").read_text(encoding="utf-8")
    assert 'total, ck = sw["epochs"], sched' in run_real


# ---- the freeze refuses a dirty tree and records the clean commit ------------------------------------------


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "docs").mkdir(parents=True)
    (r / "docs" / "PREREG.md").write_text("# prereg\n", encoding="utf-8")
    (r / "code.py").write_text("x = 1\n", encoding="utf-8")
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "t")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "init")
    return r


def test_freeze_refuses_a_dirty_tree_and_names_the_file(repo, tmp_path):
    (repo / "code.py").write_text("x = 2\n", encoding="utf-8")
    with pytest.raises(F.FreezeRefused, match=r"working tree is dirty.*code\.py"):
        F.freeze(repo / "docs" / "PREREG.md", tmp_path / "run", None, repo)
    assert "FREEZE:BEGIN" not in (repo / "docs" / "PREREG.md").read_text(encoding="utf-8")


def test_freeze_accepts_a_clean_tree_and_records_the_commit_hash(repo, tmp_path):
    rec = F.freeze(repo / "docs" / "PREREG.md", tmp_path / "run", None, repo)
    assert rec["git"]["dirty"] is False and rec["git"]["commit"] == git(repo, "rev-parse", "HEAD") and len(rec["git"]["commit"]) == 40


def test_freeze_accepts_a_change_to_the_prereg_file_only(repo, tmp_path):
    (repo / "docs" / "PREREG.md").write_text("# prereg\nedited and not yet committed\n", encoding="utf-8")
    rec = F.freeze(repo / "docs" / "PREREG.md", tmp_path / "run", None, repo)
    assert rec["git"]["dirty"] is False and F.verify(repo / "docs" / "PREREG.md")["git"]["commit"] == rec["git"]["commit"]


def test_freeze_cli_refuses_a_dirty_tree_unless_allowed(repo, tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("freeze_prereg", ROOT / "scripts" / "freeze_prereg.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (repo / "code.py").write_text("x = 3\n", encoding="utf-8")
    mod.ROOT = repo
    args = ["--prereg", str(repo / "docs" / "PREREG.md"), "--run-dir", str(tmp_path / "run"), "--ledger", str(tmp_path / "l.jsonl")]
    assert mod.main(args) == 1
    assert mod.main([*args, "--allow-dirty"]) == 0


# ---- the real-mode report gate (path test, not results) -----------------------------------------------


def test_build_report_real_needs_a_verified_freeze(repo, tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_report", ROOT / "scripts" / "build_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    built = []
    monkeypatch.setattr(mod, "build", lambda out, **k: built.append(k["real"]) or type("R", (), {"backend": "x", "pages": 6, "banner": not k["real"], "pdf": "p"})())
    prereg = repo / "docs" / "PREREG.md"
    args = ["--real", "--prereg", str(prereg), "--results-dir", str(tmp_path), "--inputs-dir", str(tmp_path), "--out", str(tmp_path / "o")]
    assert mod.main(args) == 3 and built == []  # no freeze record
    F.freeze(prereg, tmp_path / "run", None, repo)
    assert mod.main(args) == 0 and built == [True]  # verified: banner off
    prereg.write_text(prereg.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8", newline="\n")
    assert mod.main(args) == 3 and built == [True]  # hash mismatch: refused, nothing built
