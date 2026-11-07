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
from slm.bundle.release import Entry, build_release, verify_top_manifest  # noqa: E402

R = "reports/integration"
RELEASE_ENTRIES = [
    ("pretrained", "pretrained", "runs/real/pretrain/seed0/checkpoints/epoch_030.pt", None,
     "pretrained from scratch, seed 0, epoch 30 = E* (the primary analysis checkpoint)"),
    ("sft_early_stopped", "sft", "runs/real/sft/seed0/checkpoints/best.pt", "early_stopped_primary",
     "PRE-SPECIFIED primary SFT, seed 0: best epoch by SFT-validation loss (epoch 1), from the E*=30 pretrained checkpoint"),
    ("sft_fixed3", "sft", "runs/real/sft_fixed3/seed0/checkpoints/epoch_003.pt", "fixed3_posthoc",
     "POST-HOC secondary SFT, seed 0: fixed 3 epochs, no early stopping, from the E*=30 pretrained checkpoint"),
]
RELEASE_EXTRAS = [
    ("configs/model.yaml", "configs/model.yaml"), ("configs/train.yaml", "configs/train.yaml"), ("configs/sft.yaml", "configs/sft.yaml"),
    ("configs/real.yaml", "configs/real.yaml"), ("configs/base_prompts.yaml", "configs/base_prompts.yaml"),
    (f"{R}/r08/report.pdf", "report/report.pdf"), (f"{R}/r08/report.md", "report/report.md"),
    (f"{R}/r08/analysis_family_after_R08.csv", "results/analysis_family_corrected.csv"),
    (f"{R}/real_R06/results/tables/analysis_family.csv", "results/analysis_family_original_bugged_sign.csv"),
    (f"{R}/r07/sensitivity_corrected.md", "results/sensitivity_corrected.md"),
    (f"{R}/real_R06/results/tables/eval_accuracy.csv", "results/eval_accuracy_early_stopped_sft.csv"),
    (f"{R}/r08/error_taxonomy.csv", "results/error_taxonomy.csv"), (f"{R}/r08/ranking_accuracy.csv", "results/ranking_accuracy.csv"),
    (f"{R}/r08/supplementary_tables_R08.md", "results/supplementary_tables_R08.md"),
    (f"{R}/r08/value_length_check.json", "results/value_length_check.json"), (f"{R}/r08/fixed3_results.json", "results/fixed3_results.json"),
    (f"{R}/epoch_descriptive_R06.md", "results/stored_rate_by_epoch.md"), (f"{R}/heldout_loss_R06.json", "results/heldout_loss.json"),
    ("docs/FREEZE_ADDENDUM.json", "results/FREEZE_ADDENDUM.json"),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--pretrain-run", help="dir holding seed<k>/ pretraining runs")
    ap.add_argument("--sft-run", help="dir holding seed<k>/ SFT runs")
    ap.add_argument("--tokenizer", help="tokenizer.json used for both")
    ap.add_argument("--out", default="bundle")
    ap.add_argument("--seed", type=int, default=None, help="override the selection rule")
    ap.add_argument("--release", action="store_true", help="R09 release: pretrained (seed 0, E*=30) + early-stopped SFT + post-hoc fixed-3 SFT + report, tables, configs")
    ap.add_argument("--verify", metavar="DIR", help="re-hash every file listed in DIR/MANIFEST.json")
    a = ap.parse_args(argv)
    if a.verify:
        bad = verify_top_manifest(a.verify)
        print("MANIFEST OK" if not bad else "MANIFEST PROBLEMS:\n  " + "\n  ".join(bad))
        return 0 if not bad else 1
    if a.release:
        try:
            rep = build_release(a.out, ROOT / "runs/real/tokenizer.json", [Entry(n, k, ROOT / s, v, d) for n, k, s, v, d in RELEASE_ENTRIES],
                                [(ROOT / s, d) for s, d in RELEASE_EXTRAS])
        except (BundleError, FileNotFoundError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(json.dumps(rep, indent=2))
        print(f"total bundle size: {rep['total_bytes'] / 2**20:.1f} MiB in {rep['n_files']} files")
        return 0
    if not (a.pretrain_run and a.sft_run and a.tokenizer):
        ap.error("--pretrain-run, --sft-run and --tokenizer are required (or use --release / --verify)")
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