"""Hyper-parameter sweep, then the final seeds with the chosen setting.

    python scripts/sweep.py --manifest data/splits.json --tokenizer release/tokenizer.json \
        --name sweep1 [--epochs 20] [--batch-size 32] [--skip-final]

Protocol: docs/HPARAM_PROTOCOL.md. Selection uses validation loss only. On the mock corpus this is
plumbing only (see scripts/m02_dry_run.py for a ready-made mock invocation).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.model import ModelConfig  # noqa: E402
from slm.split_manifest import SplitManifest  # noqa: E402
from slm.tokenizer import BPETokenizer  # noqa: E402
from slm.train import TrainConfig  # noqa: E402
from slm.train.runner import prepare_data, run_seeds  # noqa: E402
from slm.train.sweep import DEFAULT_GRID, run_sweep  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--tokenizer", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--runs-root", type=Path, default=ROOT / "runs")
    ap.add_argument("--train-config", type=Path, default=ROOT / "configs" / "train.yaml")
    ap.add_argument("--model-config", type=Path, default=ROOT / "configs" / "model.yaml")
    ap.add_argument("--epochs", type=int, default=None)
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--warmup-steps", type=int, default=None)
    ap.add_argument("--val-every", type=int, default=None)
    ap.add_argument("--grid", type=json.loads, default=DEFAULT_GRID,
                    help='JSON, e.g. {"lr":[1e-3]}')
    ap.add_argument("--skip-final", action="store_true")
    a = ap.parse_args()

    cfg = TrainConfig.from_yaml(a.train_config)
    over = {k: v for k, v in dict(epochs=a.epochs, batch_size=a.batch_size,
                                  warmup_steps=a.warmup_steps, val_every=a.val_every).items()
            if v is not None}
    cfg = cfg.with_(**over)
    model_cfg = ModelConfig.from_yaml(a.model_config)
    manifest, tok = SplitManifest.load(a.manifest), BPETokenizer.load(a.tokenizer)
    root = a.runs_root / a.name
    cache = root / "token_cache"
    train_ds, val_ds, meta = prepare_data(manifest, tok, model_cfg, cfg, cache)

    sweep = run_sweep(model_cfg, cfg, train_ds, val_ds, root / "sweep", a.grid, seed=0, meta=meta)
    chosen = sweep["chosen"]
    print("chosen:", chosen)
    if a.skip_final:
        return
    final = cfg.with_(lr=chosen["lr"], dropout=chosen["dropout"])
    out = run_seeds("final", manifest, tok, model_cfg, final, runs_root=root, cache_dir=cache)
    text = json.dumps(out, indent=2, default=str)
    (root / "final_summary.json").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
