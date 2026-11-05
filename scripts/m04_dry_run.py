# ruff: noqa: E501
"""End-to-end dry run on the mock corpus (plumbing only; the numbers mean nothing).

pretrain (2 seeds) -> SFT -> before/after QA table (pretrained zero-shot, pretrained 2-shot, SFT
zero-shot on the same questions) -> make_bundle.py -> generate.py on both bundles (CPU, CUDA hidden)
-> fresh_clone_test.py.

    python scripts/m04_dry_run.py --sft-dir ../slm-eval/data/sft_mock [--limit 60] [--no-install]

Writes reports/model/m04_dry_run.json and runs/m04_dry_run/.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from slm.model import ModelConfig  # noqa: E402
from slm.sft_eval import (  # noqa: E402
    check_exemplars_disjoint,
    compare_variants,
    comparison_table,
    load_attribute_values,
    load_base_prompts,
    load_qa_rows,
    prompt_prefixes,
)
from slm.sft_train import SFTConfig, final_pretrain_checkpoint, run_sft_seeds  # noqa: E402
from slm.split_manifest import build_manifest  # noqa: E402
from slm.tokenizer import train_tokenizer  # noqa: E402
from slm.train import TrainConfig  # noqa: E402
from slm.train.runner import run_seeds  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "runs" / "m04_dry_run"
PY = sys.executable


def sh(cmd: list[str], **kw):
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}
    t = time.perf_counter()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env, **kw)
    return p, round(time.perf_counter() - t, 2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sft-dir", required=True)
    ap.add_argument("--limit", type=int, default=60, help="max questions per eval set")
    ap.add_argument("--no-install", action="store_true", help="fresh-clone test without pip")
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
        shutil.copyfile(sft_src / n, sft_data / n)
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
         sft_data / "qa_test.jsonl": "test"}, sft_data / "splits.json")
    sft_cfg = SFTConfig.from_yaml(ROOT / "configs" / "sft.yaml").with_(seeds=(0, 1))
    timed("sft_2_seeds", lambda: run_sft_seeds(
        "sft", OUT / "pretrain", sft_manifest, tok, sft_cfg, model_cfg.context_len, OUT))

    # ---- before/after QA: pretrained zero-shot, pretrained 2-shot, SFT zero-shot ------------
    log = OUT / "test_access_log.jsonl"
    rows = load_qa_rows(sft_manifest, "M04 dry run: mock E0/E1/E2", log_path=log)
    base = load_base_prompts(ROOT / "configs" / "base_prompts.yaml")
    check_exemplars_disjoint(base["exemplars"], rows)  # before any limiting
    prefixes = prompt_prefixes(base)
    if args.limit:
        seen: dict[str, int] = {}
        keep = []
        for r in rows:
            seen[r["subset"]] = seen.get(r["subset"], 0) + 1
            if seen[r["subset"]] <= args.limit:
                keep.append(r)
        rows = keep
    av = load_attribute_values(ROOT / "data" / "kb" / "kb.json")
    tables = []
    for seed in (0, 1):
        pre = final_pretrain_checkpoint(OUT / "pretrain" / f"seed{seed}")
        sft = OUT / "sft" / f"seed{seed}" / "checkpoints" / "best.pt"
        variants = [("pretrained", pre, "zero_shot", prefixes["zero_shot"]),
                    ("pretrained", pre, "2shot", prefixes["2shot"]),
                    ("sft", sft, "zero_shot", prefixes["zero_shot"])]
        tables.append(timed(f"eval_seed{seed}_3_variants", lambda v=variants, s=seed: (
            compare_variants(v, tok, rows, s, av, max_new_tokens=sft_cfg.max_new_tokens))))
    full = pd.concat(tables, ignore_index=True)
    full.to_csv(OUT / "qa_predictions.csv", index=False, encoding="utf-8")
    cmp = comparison_table(full)
    print(cmp.to_string(index=False))

    # ---- bundle, generate.py, fresh clone ---------------------------------------------------
    bundle = OUT / "bundle"
    mk = [PY, "scripts/make_bundle.py", "--pretrain-run", str(OUT / "pretrain"), "--sft-run",
          str(OUT / "sft"), "--tokenizer", str(OUT / "tokenizer.json"), "--out", str(bundle)]
    p, phases["make_bundle"] = sh(mk)
    assert p.returncode == 0, p.stderr
    size_line = p.stdout.strip().splitlines()[-1]
    gens = {}
    for kind, prompt in (("sft", "Who manages the pet lounge at Vellmar?"),
                         ("pretrained", "The pet lounge at Vellmar opens at")):
        cmd = [PY, "scripts/generate.py", "--bundle", str(bundle / kind), "--prompt", prompt,
               "--device", "cpu"]
        p, secs = sh(cmd)
        gens[kind] = {"command": " ".join(cmd), "returncode": p.returncode, "stdout": p.stdout,
                      "stderr": p.stderr, "seconds": secs}
    fc = [PY, "scripts/fresh_clone_test.py", "--bundle", str(bundle), "--source", "worktree"]
    if args.no_install:
        fc.append("--no-install")
    p, phases["fresh_clone_test"] = sh(fc, timeout=2400)
    try:
        fresh = json.loads(p.stdout)
    except json.JSONDecodeError:
        fresh = {"error": p.stdout[-800:] + p.stderr[-800:]}
    report = {
        "phases_seconds": phases, "n_eval_rows": len(rows),
        "comparison": cmp.to_dict("records"), "truncated_prompts": int(full["truncated_prompt"].sum()),
        "make_bundle_command": " ".join(mk), "make_bundle_last_line": size_line,
        "generate": gens, "fresh_clone": fresh, "fresh_clone_returncode": p.returncode,
        "bundle_files": {str(f.relative_to(bundle)): f.stat().st_size
                         for f in sorted(bundle.rglob("*")) if f.is_file()},
    }
    path = ROOT / "reports" / "model" / "m04_dry_run.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "comparison"}, indent=2,
                     default=str))


if __name__ == "__main__":
    main()