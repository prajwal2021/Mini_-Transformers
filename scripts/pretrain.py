"""Pretrain one or more seeds from a split manifest and a tokenizer file.

    python scripts/pretrain.py --manifest data/splits.json --tokenizer release/tokenizer.json \
        --name main [--seeds 0 1 2] [--lr 6e-4 --dropout 0.1 --epochs 20]

Writes runs/<name>/seed<k>/ (config.yaml, meta.json, loss.csv, checkpoints/). Re-running the same
command resumes each seed from its last completed epoch.
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
from slm.train.runner import run_seeds  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--tokenizer", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--runs-root", type=Path, default=ROOT / "runs")
    ap.add_argument("--train-config", type=Path, default=ROOT / "configs" / "train.yaml")
    ap.add_argument("--model-config", type=Path, default=ROOT / "configs" / "model.yaml")
    ap.add_argument("--seeds", type=int, nargs="*", default=None)
    for k, t in [("epochs", int), ("batch_size", int), ("lr", float), ("dropout", float),
                 ("warmup_steps", int), ("val_every", int)]:
        ap.add_argument("--" + k.replace("_", "-"), type=t, default=None)
    ap.add_argument("--label-eos", type=lambda s: s.lower() == "true", default=None)
    a = ap.parse_args()
    over = {k: getattr(a, k) for k in ("epochs", "batch_size", "lr", "dropout", "warmup_steps",
                                       "val_every", "label_eos") if getattr(a, k) is not None}
    cfg = TrainConfig.from_yaml(a.train_config).with_(**over)
    out = run_seeds(a.name, SplitManifest.load(a.manifest), BPETokenizer.load(a.tokenizer),
                    ModelConfig.from_yaml(a.model_config), cfg, a.runs_root,
                    seeds=tuple(a.seeds) if a.seeds else None)
    print(json.dumps({s: {k: v for k, v in r.items() if k != "val_by_epoch"}
                      for s, r in out["seeds"].items()}, indent=2, default=str))


if __name__ == "__main__":
    main()
