"""End-to-end dry run on the mock corpus (plumbing only; the numbers mean nothing).

mock pretraining (2 seeds, as M02) -> SFT on sft_mock/sft_train (seed k from pretraining seed k)
-> greedy decoding + exact match on E0/E1/E2 of sft_mock/qa_test, read through the test-access
ledger (written to the run directory so the real reports/test_access_log.jsonl stays clean).

    python scripts/m03_dry_run.py --sft-dir ../slm-eval/data/sft_mock [--limit 40]

Writes reports/model/m03_dry_run.json and runs/m03_dry_run/.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.generation import generate_text, newline_token_ids  # noqa: E402
from slm.model import ModelConfig, load_checkpoint  # noqa: E402
from slm.sft_eval import compare_checkpoints, comparison_table, load_qa_rows  # noqa: E402
from slm.sft_train import SFTConfig, final_pretrain_checkpoint, run_sft_seeds  # noqa: E402
from slm.split_manifest import build_manifest  # noqa: E402
from slm.tokenizer import train_tokenizer  # noqa: E402
from slm.train import TrainConfig  # noqa: E402
from slm.train.runner import run_seeds  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "runs" / "m03_dry_run"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sft-dir", required=True, help="directory with sft_train/sft_val/qa_test")
    ap.add_argument("--limit", type=int, default=None, help="max questions per eval set")
    args = ap.parse_args()
    sft_src = Path(args.sft_dir).resolve()

    if OUT.exists():
        shutil.rmtree(OUT)
    data, sft_data = OUT / "data", OUT / "sft_data"
    data.mkdir(parents=True)
    sft_data.mkdir(parents=True)
    for n in ("mock_corpus_train.txt", "mock_corpus_val.txt"):
        shutil.copy(FIX / n, data / n)
    for n in ("sft_train.jsonl", "sft_val.jsonl", "qa_test.jsonl"):
        shutil.copyfile(sft_src / n, sft_data / n)  # read-only use of the sibling worktree
    phases: dict[str, float] = {}

    def timed(name, fn):
        t = time.perf_counter()
        r = fn()
        phases[name] = round(time.perf_counter() - t, 2)
        return r

    manifest = build_manifest(
        {data / "mock_corpus_train.txt": "train", data / "mock_corpus_val.txt": "val"},
        data / "splits.json")
    tok = timed("tokenizer_train", lambda: train_tokenizer(manifest, 4096, min_frequency=1))
    tok.save(OUT / "tokenizer.json")
    model_cfg = ModelConfig.from_yaml(ROOT / "configs" / "model.yaml")
    pre_cfg = TrainConfig.from_yaml(ROOT / "configs" / "train.yaml").with_(
        seeds=(0, 1), epochs=8, batch_size=8, warmup_steps=20, val_every=50)
    timed("pretrain_2_seeds", lambda: run_seeds(
        "pretrain", manifest, tok, model_cfg, pre_cfg, runs_root=OUT,
        cache_dir=OUT / "token_cache"))

    sft_manifest = build_manifest(
        {sft_data / "sft_train.jsonl": "train", sft_data / "sft_val.jsonl": "val",
         sft_data / "qa_test.jsonl": "test"},
        sft_data / "splits.json")
    sft_cfg = SFTConfig.from_yaml(ROOT / "configs" / "sft.yaml").with_(seeds=(0, 1))
    sft = timed("sft_2_seeds", lambda: run_sft_seeds(
        "sft", OUT / "pretrain", sft_manifest, tok, sft_cfg, model_cfg.context_len, OUT))

    log = OUT / "test_access_log.jsonl"
    rows = load_qa_rows(sft_manifest, "M03 dry run: mock E0/E1/E2 exact match", log_path=log)
    if args.limit:
        keep: dict[str, int] = {}
        picked = []
        for r in rows:
            keep[r["subset"]] = keep.get(r["subset"], 0) + 1
            if keep[r["subset"]] <= args.limit:
                picked.append(r)
        rows = picked
    report = {"phases_seconds": phases, "n_eval_rows": len(rows), "sft": {}, "eval": {}}
    tables = []
    for seed in (0, 1):
        s = sft["seeds"][seed]
        report["sft"][seed] = {k: s[k] for k in (
            "epochs_done", "steps", "best_epoch", "best_val_loss", "stopped_early",
            "train_seconds", "wall_seconds")}
        ckpts = {
            "pretrained": final_pretrain_checkpoint(OUT / "pretrain" / f"seed{seed}"),
            "sft": OUT / "sft" / f"seed{seed}" / "checkpoints" / "best.pt",
        }
        t = time.perf_counter()
        # same rows (hence the same questions and prompt template) and the same decoding
        table = compare_checkpoints(ckpts, tok, rows, seed, max_new_tokens=sft_cfg.max_new_tokens)
        phases[f"eval_seed{seed}_both_checkpoints"] = round(time.perf_counter() - t, 2)
        tables.append(table)
        report["eval"][seed] = comparison_table(table).to_dict("records")
    import pandas as pd

    full = pd.concat(tables, ignore_index=True)
    full.to_csv(OUT / "qa_predictions.csv", index=False, encoding="utf-8")
    report["comparison_mean_over_seeds"] = comparison_table(
        full.assign(checkpoint=full["checkpoint"])).to_dict("records")
    report["truncated_prompts"] = int(full["truncated_prompt"].sum())
    report["ledger_lines"] = len(log.read_text(encoding="utf-8").splitlines())
    # qualitative samples: temperature 0.8, top-k 20, seeded, from the SFT seed-0 model
    model = load_checkpoint(OUT / "sft" / "seed0" / "checkpoints" / "best.pt").eval()
    report["samples"] = []
    for r in rows[:3]:
        text, gen = generate_text(model, tok, r["prompt"], 48, newline_token_ids(tok),
                                  temperature=0.8, top_k=20, seed=0)
        report["samples"].append({"question": r["question"], "sampled": text,
                                  "stopped": gen.stopped})
    path = ROOT / "reports" / "model" / "m03_dry_run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
