# ruff: noqa: E501
"""Sweep with validation probes at every checkpoint (R03; rule in ``slm.train.budget``).

One seed per grid point, trained for ``max_epochs`` with log-spaced checkpoints. After a run the
checkpoints are scored on the VALIDATION probes only (``ProbeSet`` built with ``splits=("val",)``,
asserted) and then deleted, so that a 12-config sweep does not keep 12 x 13 checkpoints.
"""

from __future__ import annotations

import itertools
import json
import shutil
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

from slm.eval.probes import assert_no_leakage, build_probes, load_facts
from slm.integration.probing import list_checkpoints, run_model_probes
from slm.model import ModelConfig
from slm.train import TrainConfig
from slm.train.budget import MAX_EPOCHS, SCHEDULE, decision_markdown, schedule_upto, select_budget
from slm.train.pretrain import TrainingAborted, train_run

GRID_KEYS = ("lr", "dropout", "batch_size")
DEFAULT_GRID = {"lr": [3e-4, 6e-4, 1e-3], "dropout": [0.0, 0.1], "batch_size": [16, 32]}


def val_probes(kb_path: str | Path):
    probes = build_probes(load_facts(kb_path), seed=0, splits=("val",))
    assert_no_leakage(probes)
    assert {i.split for i in probes.items} == {"val"}, "the budget sweep may only score validation probes"
    return probes


def config_name(i: int, over: dict) -> str:
    return f"cfg{i:02d}_" + "_".join(f"{k}{v}" for k, v in over.items())


def score_run(run_root: Path, tokenizer, probes, model_cfg: ModelConfig, seed: int, val_by_epoch: dict) -> tuple[list[dict], dict]:
    """Rows (epoch, val_loss, stored_rate, null_rate) for every checkpoint of ``run_root/seed<k>`` + init."""
    raw = run_model_probes(run_root, tokenizer, probes, (seed,), model_cfg, include_init=True)
    raw["checkpoint"] = raw["checkpoint"].astype(str)
    step_epoch = {str(step): epoch for step, epoch, _ in list_checkpoints(run_root / f"seed{seed}")}
    init = raw[raw["checkpoint"] == "init"]
    init_row = {"stored_rate": float(init["stored"].mean()), "null_rate": float(init["null_stored_rate"].mean())}
    rows = []
    for ck, g in raw[raw["checkpoint"] != "init"].groupby("checkpoint"):
        e = step_epoch[ck]
        rows.append({"epoch": e, "step": int(ck), "val_loss": float(val_by_epoch[e]),
                     "stored_rate": float(g["stored"].mean()), "null_rate": float(g["null_stored_rate"].mean()),
                     "n_probes": int(len(g))})
    return sorted(rows, key=lambda r: r["epoch"]), init_row


def run_config(name, model_cfg, cfg, train_ds, val_ds, tokenizer, probes, out_dir, seed, meta, schedule,
               device=None, keep_checkpoints=False) -> dict:
    """Train one config, score its checkpoints on validation probes; the result row of the sweep."""
    root = Path(out_dir) / name
    cfg = cfg.with_(seeds=(seed,), epochs=max(schedule), checkpoint_epochs=tuple(schedule))
    t0 = time.perf_counter()
    try:
        s = train_run(model_cfg, cfg, train_ds, val_ds, root / f"seed{seed}", seed, meta=meta, device=device, resume=False)
    except TrainingAborted as exc:
        return {"config": name, "status": "aborted", "message": str(exc), "rows": [], "init": None}
    sched = set(schedule)
    val_by_epoch = {e: v for e, v in s["val_by_epoch"].items() if e in sched}
    rows, init = score_run(root, tokenizer, probes, replace(model_cfg, dropout=cfg.dropout), seed, val_by_epoch)
    if not keep_checkpoints:
        shutil.rmtree(root / f"seed{seed}" / "checkpoints", ignore_errors=True)
    return {"config": name, "status": "ok", "rows": rows, "init": init, "seconds": round(time.perf_counter() - t0, 1),
            "steps_per_epoch": s["steps_per_epoch"], "total_steps": s["total_steps"], "warmup_steps": s["warmup_steps"],
            "val_every": s["val_every"], "log_every": s["log_every"]}


def flat_rows(results: list[dict], extra: dict[str, dict] | None = None) -> list[dict]:
    out = []
    for r in results:
        if r["status"] != "ok":
            continue
        for row in r["rows"]:
            out.append({"config": r["config"], **(extra or {}).get(r["config"], {}), **row})
    return out


def run_budget_sweep(model_cfg, base_cfg: TrainConfig, train_ds, val_ds, tokenizer, kb_path, out_dir, *,
                     grid=None, max_epochs=MAX_EPOCHS, schedule=SCHEDULE, seed=0, meta_for=None, device=None,
                     label="REAL", decision_path=None) -> dict:
    """The sweep: ``train_ds_for(batch_size)``-independent datasets, one run per grid point, E* selection."""
    grid = grid or DEFAULT_GRID
    sched = schedule_upto(max_epochs, schedule)
    probes = val_probes(kb_path)
    keys = [k for k in GRID_KEYS if k in grid]
    results, hyper = [], {}
    out_dir = Path(out_dir)
    for i, values in enumerate(itertools.product(*(grid[k] for k in keys))):
        over = dict(zip(keys, values))
        name = config_name(i, over)
        hyper[name] = over
        res = run_config(name, model_cfg, base_cfg.with_(**over), train_ds, val_ds, tokenizer, probes, out_dir,
                         seed, (meta_for or {}), sched, device)
        results.append(res)
        (out_dir).mkdir(parents=True, exist_ok=True)
        (out_dir / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    rows = flat_rows(results, hyper)
    sel = select_budget(rows)
    init_rates = {r["config"]: r["init"]["stored_rate"] for r in results if r["status"] == "ok"}
    null_rates = {r["config"]: r["init"]["null_rate"] for r in results if r["status"] == "ok"}
    md = decision_markdown(rows, sel, init_rates, null_rates, label)
    if decision_path:
        Path(decision_path).parent.mkdir(parents=True, exist_ok=True)
        Path(decision_path).write_text(md, encoding="utf-8")
    base = {"lr": base_cfg.lr, "dropout": base_cfg.dropout, "batch_size": base_cfg.batch_size}
    chosen = {**base, **hyper[sel["config"]], **sel, "run": sel["config"], "schedule": sched,
              "init_stored_rate": init_rates[sel["config"]], "null_stored_rate": null_rates[sel["config"]]}
    (out_dir / "chosen.json").write_text(json.dumps(chosen, indent=1), encoding="utf-8")
    pd.DataFrame(rows).to_csv(out_dir / "decision_rows.csv", index=False)
    return {"results": results, "rows": rows, "chosen": chosen, "markdown": md}
