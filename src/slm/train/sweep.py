"""Hyper-parameter sweep (docs/HPARAM_PROTOCOL.md): selection by validation loss ONLY."""

from __future__ import annotations

import itertools
import json
import time
from pathlib import Path

from slm.model import ModelConfig

from .config import TrainConfig
from .pretrain import TrainingAborted, train_run

DEFAULT_GRID = {"lr": [3e-4, 6e-4, 1e-3], "dropout": [0.0, 0.1, 0.2]}


def select_best(results: list[dict]) -> dict:
    """Config with the lowest validation loss over its scheduled checkpoint epochs.

    Reads only ``val_by_epoch`` (validation-split cross-entropy). Probe accuracies, test
    metrics, or anything else in a result row are ignored by construction. Aborted runs
    (non-finite loss) are excluded; ties go to the earlier row.
    """
    best = None
    for row in results:
        val = row.get("val_by_epoch") or {}
        if row.get("status") != "ok" or not val:
            continue
        epoch, loss = min(((int(e), v) for e, v in val.items()), key=lambda t: (t[1], t[0]))
        if best is None or loss < best["best_val"]:
            best = {**row, "best_val": loss, "best_epoch": epoch}
    if best is None:
        raise ValueError("no sweep run finished; nothing to select")
    return best


def run_sweep(
    model_cfg: ModelConfig,
    base: TrainConfig,
    train_ds,
    val_ds,
    out_dir: str | Path,
    grid: dict[str, list] | None = None,
    seed: int = 0,
    meta: dict | None = None,
    device: str | None = None,
) -> dict:
    """One seed per grid point; every configuration tried is written to results.json."""
    grid = grid or DEFAULT_GRID
    out_dir = Path(out_dir)
    keys = list(grid)
    results = []
    for i, values in enumerate(itertools.product(*(grid[k] for k in keys))):
        overrides = dict(zip(keys, values))
        cfg = base.with_(**overrides)
        name = f"cfg{i:02d}_" + "_".join(f"{k}{v}" for k, v in overrides.items())
        row = {"name": name, "seed": seed, **overrides}
        t0 = time.perf_counter()
        try:
            s = train_run(model_cfg, cfg, train_ds, val_ds, out_dir / name, seed, meta=meta,
                          device=device, resume=False)
            scheduled = set(cfg.save_epochs())
            row |= {"status": "ok", "val_by_epoch": {
                str(e): v for e, v in s["val_by_epoch"].items() if e in scheduled}}
        except TrainingAborted as exc:
            row |= {"status": "aborted", "message": str(exc)}
        row["seconds"] = time.perf_counter() - t0
        results.append(row)
        (out_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    best = select_best(results)
    chosen = {k: best[k] for k in keys} | {"best_epoch": best["best_epoch"],
                                          "best_val": best["best_val"], "run": best["name"]}
    (out_dir / "chosen.json").write_text(json.dumps(chosen, indent=2), encoding="utf-8")
    return {"results": results, "chosen": chosen}
