"""Build the release bundle from a pretraining run and an SFT run.

    python scripts/make_bundle.py --pretrain-run runs/final/pretrain --sft-run runs/final/sft \
        --tokenizer runs/final/tokenizer.json --out bundle [--seed 0]

Seed rule (documented, never test results): the seed with the lowest pretraining VALIDATION loss at
its final checkpoint among seeds that also have an SFT run; ties go to the lower seed. --seed
overrides it and is recorded as an explicit choice. Writes bundle/pretrained and bundle/sft (model
weights only, tokenizer, model config, bundle_manifest.json), README_BUNDLE.md and requirements.txt.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.bundle import BundleError, build_bundle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--pretrain-run", required=True, help="dir holding seed<k>/ pretraining runs")
    ap.add_argument("--sft-run", required=True, help="dir holding seed<k>/ SFT runs")
    ap.add_argument("--tokenizer", required=True, help="tokenizer.json used for both")
    ap.add_argument("--out", default="bundle")
    ap.add_argument("--seed", type=int, default=None, help="override the selection rule")
    a = ap.parse_args(argv)
    try:
        report = build_bundle(a.pretrain_run, a.sft_run, a.tokenizer, a.out, a.seed)
    except (BundleError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    print(f"total bundle size: {report['total_bytes'] / 2**20:.1f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())