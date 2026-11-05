"""End-to-end dry run on the mock corpus (plumbing only, not a result).

manifest -> tokenizer (via the manifest guard) -> token cache -> 2 seeds x 8 epochs on the GPU
-> checkpoint -> ModelScorer -> toy probe pair; then a small sweep on the same data.
Writes reports/model/m02_dry_run.json and runs/m02_dry_run/.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.eval_adapter import ModelScorer  # noqa: E402
from slm.model import ModelConfig  # noqa: E402
from slm.split_manifest import SplitManifest, build_manifest  # noqa: E402
from slm.tokenizer import train_tokenizer  # noqa: E402
from slm.train import TrainConfig  # noqa: E402
from slm.train.runner import prepare_data, run_seeds  # noqa: E402
from slm.train.sweep import run_sweep  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "runs" / "m02_dry_run"


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    data = OUT / "data"
    data.mkdir(parents=True)
    for n in ("mock_corpus_train.txt", "mock_corpus_val.txt"):
        shutil.copy(FIX / n, data / n)
    phases: dict[str, float] = {}

    def timed(name, fn):
        t = time.perf_counter()
        r = fn()
        phases[name] = time.perf_counter() - t
        return r

    manifest = timed("manifest", lambda: build_manifest(
        {data / "mock_corpus_train.txt": "train", data / "mock_corpus_val.txt": "val"},
        data / "splits.json"))
    tok = timed("tokenizer_train", lambda: train_tokenizer(manifest, 4096, min_frequency=1))
    tok.save(OUT / "tokenizer.json")
    model_cfg = ModelConfig.from_yaml(ROOT / "configs" / "model.yaml")
    cfg = TrainConfig.from_yaml(ROOT / "configs" / "train.yaml").with_(
        seeds=(0, 1), epochs=8, batch_size=8, warmup_steps=20, val_every=50)
    cache = OUT / "token_cache"
    train_ds, val_ds, meta = timed("tokenize_and_pack", lambda: prepare_data(
        manifest, tok, model_cfg, cfg, cache))
    timed("tokenize_cache_hit", lambda: prepare_data(manifest, tok, model_cfg, cfg, cache))
    result = timed("train_all_seeds", lambda: run_seeds(
        "main", manifest, tok, model_cfg, cfg, runs_root=OUT, cache_dir=cache))
    report = {"phases_seconds": phases, "token_stats": meta["token_stats"],
              "packing": meta["packing"], "seeds": {}}
    for seed, s in result["seeds"].items():
        ckpts = sorted((OUT / "main" / f"seed{seed}" / "checkpoints").glob("*.pt"))
        report["seeds"][seed] = {
            "wall_seconds": s["wall_seconds"], "train_seconds": s["train_seconds"],
            "steps": s["steps"], "val_by_epoch": s["val_by_epoch"],
            "checkpoint_mb": {p.name: round(p.stat().st_size / 2**20, 1) for p in ckpts},
        }
    # toy probe pair through ModelScorer, loaded from a saved checkpoint
    ck = OUT / "main" / "seed0" / "checkpoints" / "epoch_008.pt"
    t = time.perf_counter()
    scorer = ModelScorer.from_files(ck, OUT / "tokenizer.json")
    prompt = "Meanwhile, the desk checks the morning list"
    pairs = [(prompt, " before the doors open."), (prompt, " zzqx wiggle plonk.")]
    scores = scorer.score_many(pairs)
    report["scorer"] = {"pairs": pairs, "log_probs": scores, "seconds": time.perf_counter() - t}
    # sweep plumbing on the same data
    sweep_cfg = cfg.with_(epochs=3, checkpoint_epochs=(1, 3), val_every=1000)
    sw = timed("sweep_4_configs", lambda: run_sweep(
        model_cfg, sweep_cfg, train_ds, val_ds, OUT / "sweep",
        {"lr": [3e-4, 1e-3], "dropout": [0.0, 0.1]}, seed=0, meta=meta))
    report["sweep_chosen"] = sw["chosen"]
    report["phases_seconds"] = phases
    path = ROOT / "reports" / "model" / "m02_dry_run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    SplitManifest.load(data / "splits.json")  # still valid


if __name__ == "__main__":
    main()
