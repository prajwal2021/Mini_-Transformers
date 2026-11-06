# ruff: noqa: E501
"""R02: dry run of run_real.py (tokenizer, token cache, tiny sweep) on the PARTIAL corpus + statistics.

    python scripts/partial_manifest.py                     # copies train/val only (never test)
    python scripts/partial_dryrun.py [--config configs/partial_dryrun.yaml]

Runs only the stages tokenizer, token_cache and sweep of scripts/run_real.py in this process, then
prints tokens/word, share of documents over the context length, corpus tokens, tokenizer statistics,
stage timings, the loss curves of the sweep configs, GPU memory and tokens/s, and 12 samples
(4 prompts x 3, temperature 0.8) of the best sweep run. Asserts that the test-access ledger was not
created (no test read). Writes <out_dir>/partial_stats.json.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]


def load_run_real():
    spec = importlib.util.spec_from_file_location("run_real", ROOT / "scripts" / "run_real.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "configs" / "partial_dryrun.yaml"))
    args = ap.parse_args(argv)
    import yaml

    from slm.generation import generate_text
    from slm.model import load_checkpoint
    from slm.tokenizer import BPETokenizer, read_split

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    out = ROOT / cfg["out_dir"]
    if cfg["out_dir"].replace("\\", "/").rstrip("/") in ("runs/real", "runs/real_mock"):
        raise SystemExit("the partial dry run must not write into runs/real")
    run_real = load_run_real()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if dev == "cuda":
        torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    run_real.main(["--config", args.config, "--until", "sweep", "--force"])
    wall = time.perf_counter() - t0
    peak_mb = torch.cuda.max_memory_allocated() / 2**20 if dev == "cuda" else None

    ledger = ROOT / cfg["ledger"]
    assert not ledger.exists(), f"a test read was logged: {ledger}"
    stats = json.loads((out / "token_cache" / "token_stats.json").read_text(encoding="utf-8"))
    ctx = run_real.Ctx(cfg)
    tok = BPETokenizer.load(out / "tokenizer.json")
    train_docs = read_split(ctx.manifest(), "train")
    counts: Counter = Counter()
    for d in train_docs:
        counts.update(tok.encode(d))
    total = sum(counts.values())
    top20 = [{"id": i, "bytes": tok.token_bytes(i).decode("utf-8", "replace"), "count": n, "share": round(n / total, 4)}
             for i, n in counts.most_common(20)]
    stage_secs = {s: json.loads((out / "stages" / f"{s}.json").read_text())["seconds"] for s in ("tokenizer", "token_cache", "sweep")}

    results = json.loads((out / "sweep" / "results.json").read_text())
    curves = {}
    for row in results:
        loss = pd.read_csv(out / "sweep" / row["name"] / "loss.csv")
        summ = json.loads((out / "sweep" / row["name"] / "summary.json").read_text())
        train = loss[loss["split"] == "train"]
        val = loss[loss["split"] == "val"]
        curves[row["name"]] = {
            "lr": row["lr"], "dropout": row["dropout"], "status": row["status"], "seconds": round(row["seconds"], 1),
            "val_by_epoch": row.get("val_by_epoch"), "tokens_seen": summ["tokens_seen"],
            "tokens_per_s": round(summ["tokens_seen"] / row["seconds"]),
            "train_loss_every": [[int(s), round(float(v), 3)] for s, v in zip(train["step"], train["loss"], strict=False)][:: max(1, len(train) // 8)],
            "val_loss_steps": [[int(s), round(float(v), 3)] for s, v in zip(val["step"], val["loss"], strict=False)],
        }
    chosen = json.loads((out / "sweep" / "chosen.json").read_text())

    # 12 samples (4 prompts x 3) of the best run at temperature 0.8: only to see that generation works
    kb = json.loads((ROOT / cfg["kb"]).read_text(encoding="utf-8"))
    from slm.eval.wording import prefix

    f1, f2 = kb["measured_facts"][0], kb["measured_facts"][40]
    prompts = [f1["canonical_prefix"].rstrip(), f2["canonical_prefix"].rstrip(),
               prefix(kb["measured_facts"][80]["attribute_id"], "n1", kb["measured_facts"][80]["entity"]),
               "Passengers travelling with pets should"]
    ck = sorted((out / "sweep" / chosen["run"] / "checkpoints").glob("epoch_*.pt"))[-1]
    model = load_checkpoint(ck, map_location=dev).to(dev).eval()
    samples = []
    for p in prompts:
        for i in range(3):
            text, _ = generate_text(model, tok, p, 40, (), dev, 0.8, None, i)
            samples.append({"prompt": p, "sample": i, "completion": text})

    summary = {
        "tokens_per_word": {s: stats[s]["tokens_per_word"] for s in ("train", "val")},
        "share_docs_over_context_train": stats["train"]["share_docs_over_context"],
        "docs": {s: stats[s]["n_docs"] for s in ("train", "val")},
        "words": {s: stats[s]["n_words"] for s in ("train", "val")},
        "tokens_with_eos": {s: stats[s]["n_tokens_with_eos"] for s in ("train", "val")},
        "tokenizer": {"vocab_size": tok.vocab_size, "n_merges": len(tok.merges), "top20_in_train": top20,
                      "n_distinct_tokens_in_train": len(counts)},
        "stage_seconds": stage_secs, "wall_seconds_incl_imports": round(wall, 1),
        "device": dev, "gpu_peak_memory_mb": None if peak_mb is None else round(peak_mb),
        "sweep": {"chosen": chosen, "curves": curves}, "samples_t0.8": samples, "samples_checkpoint": str(ck.name),
        "ledger_created": ledger.exists(),
    }
    (out / "partial_stats.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("samples_t0.8",)}, indent=1, ensure_ascii=False))
    for s in samples:
        print(f"[{s['sample']}] {s['prompt']} |{s['completion']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
