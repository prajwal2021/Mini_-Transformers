# ruff: noqa: E501
"""R08 item 3: POST-HOC SECONDARY SFT with a FIXED 3 epochs and no early stopping, from the E*=30 checkpoint of each seed.

    python scripts/posthoc_sft_fixed3.py train    # SFT only (train/val files), writes runs/real/sft_fixed3/seed{0,1,2}
    python scripts/posthoc_sft_fixed3.py eval     # QA on the SAME questions as the primary SFT, ledgered:
                                                  # "post-hoc sensitivity: fixed 3-epoch SFT"

Everything else equals the primary SFT (configs/sft.yaml): only ``epochs=3`` and ``patience`` large. The primary (pre-specified) SFT, its QA numbers
and the base zero-shot / 2-shot numbers are NOT recomputed or changed. Output of ``eval``: runs/real/qa/qa_predictions_sft_fixed3.csv.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from scripts import run_real as RR  # noqa: E402

NAME = "sft_fixed3"
PURPOSE = "post-hoc sensitivity: fixed 3-epoch SFT"


def ctx():
    cfg = yaml.safe_load((ROOT / "configs" / "real.yaml").read_text(encoding="utf-8"))
    return RR.Ctx(cfg)


def train() -> None:
    from slm.model import ModelConfig
    from slm.sft_train import run_sft_seeds

    c = ctx()
    c.require_freeze()
    cfg = c.sft_cfg().with_(epochs=3, patience=99)  # no early stopping, 3 epochs; everything else as in configs/sft.yaml
    ctx_len = ModelConfig.from_dict(c.final()["model"]).context_len
    res = run_sft_seeds(NAME, c.out / "pretrain", RR.sft_manifest(c), c.tokenizer(), cfg, ctx_len, c.out,
                        pretrain_epoch=c.final()["primary_epoch"])
    for s, v in res["seeds"].items():
        print("seed", s, "epochs_done", v["epochs_done"], "best_epoch", v["best_epoch"], "stopped_early", v["stopped_early"], "val", {k: round(x, 3) for k, x in v["val_by_epoch"].items()})


def evaluate() -> None:
    from slm.sft_eval import (
        Taxonomy,
        compare_variants,
        load_attribute_values,
        load_base_prompts,
        load_qa_rows,
        prompt_prefixes,
    )

    c = ctx()
    c.require_freeze()
    out_csv = c.out / "qa" / "qa_predictions_sft_fixed3.csv"
    if out_csv.exists():
        raise SystemExit(f"{out_csv} exists: the post-hoc QA evaluation is run ONCE")
    seeds = tuple(c.cfg["final_seeds"])
    rows = load_qa_rows(RR.sft_manifest(c), PURPOSE, log_path=c.ledger, caller="scripts/posthoc_sft_fixed3.py:evaluate")  # the ledger entry
    prefixes = prompt_prefixes(load_base_prompts(c.p("base_prompts")))
    av = load_attribute_values(c.kb_path)
    tabs = []
    for seed in seeds:
        ck = c.out / NAME / f"seed{seed}" / "checkpoints" / "epoch_003.pt"  # the final epoch: no checkpoint selection
        tabs.append(compare_variants([("sft", ck, "zero_shot", prefixes["zero_shot"])], c.tokenizer(), rows, seed, av,
                                     max_new_tokens=c.sft_cfg().max_new_tokens, taxonomy=Taxonomy.from_kb(c.kb_path), ranking=True))
    qa = pd.concat(tabs, ignore_index=True)
    qa["checkpoint"] = "sft"  # same (checkpoint, prompt_mode) label as the primary SFT so that the analysis code reads it unchanged
    qa.to_csv(out_csv, index=False, encoding="utf-8")
    print(qa.groupby("eval_set").exact_value_match.mean().round(4).to_dict(), "rows", len(qa))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"train": train, "eval": evaluate}.get(cmd, lambda: sys.exit(__doc__))()
