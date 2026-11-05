# ruff: noqa: E501
"""End-to-end MOCK pipeline: every stage from tokenizer to report, on toy data.

    python scripts/run_all_mock.py [--limit 40] [--out runs/i01_mock] [--corpus-manifest M]

tokenizer training -> token cache -> 2-seed pretraining -> probes at every checkpoint (ModelScorer)
-> SFT -> QA evaluation (base zero-shot, base 2-shot, SFT) -> build_analysis_tables ->
run_analysis (+ sensitivity) -> report inputs -> build_report.

The models are trained for seconds on a 200-document toy corpus, so every number is meaningless:
the banner says MOCK on the report and on every figure. ``--real`` is refused, always. No network
and no API call is made. ``--corpus-manifest`` points the tokenizer, the token cache and the
pretraining at a manifest of the real corpus instead of the toy files (format:
docs/SPLIT_MANIFEST.md); the models stay mock-sized either way.

Writes <out>/ (all stages) and reports/integration/mock_run.json (timings per stage).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
BANNER = "=" * 78 + "\n  MOCK RUN - toy corpus, tiny training budget. NOTHING HERE IS A RESULT.\n" + "=" * 78


def run_cli(args: list[str]) -> str:
    p = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"stage failed: {' '.join(args)}\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}")
    return p.stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "runs" / "i01_mock"))
    ap.add_argument("--limit", type=int, default=40, help="max questions per eval set")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1])
    ap.add_argument("--corpus-manifest", default=None, help="split manifest of a real corpus")
    ap.add_argument("--timings", default=str(ROOT / "reports" / "integration" / "mock_run.json"))
    ap.add_argument("--real", action="store_true", help="refused: this pipeline is mock only")
    args = ap.parse_args(argv)
    if args.real:
        ap.error("--real is refused: the mock pipeline never produces real results")
    print(BANNER)

    from slm.eval.probes import assert_no_leakage, build_probes, load_facts
    from slm.integration import report_inputs as RI
    from slm.integration import tables as T
    from slm.integration.probing import run_model_probes
    from slm.model import ModelConfig
    from slm.sft_eval import (
        check_exemplars_disjoint,
        compare_variants,
        comparison_table,
        load_attribute_values,
        load_base_prompts,
        load_qa_rows,
        prompt_prefixes,
    )
    from slm.sft_train import SFTConfig, final_pretrain_checkpoint, run_sft_seeds
    from slm.split_manifest import SplitManifest, build_manifest
    from slm.tokenizer import read_split, train_tokenizer
    from slm.train import TrainConfig
    from slm.train.runner import prepare_data, run_seeds

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    data, sft_data, tables_dir = out / "data", out / "sft_data", out / "analysis_inputs"
    data.mkdir(parents=True)
    sft_data.mkdir(parents=True)
    seeds = tuple(args.seeds)
    stages: dict[str, float] = {}

    def stage(name: str, fn):
        print(f"[stage] {name} ...", flush=True)
        t = time.perf_counter()
        res = fn()
        stages[name] = round(time.perf_counter() - t, 2)
        print(f"[stage] {name}: {stages[name]} s", flush=True)
        return res

    # ---- inputs ---------------------------------------------------------------------------
    if args.corpus_manifest:
        manifest = SplitManifest.load(args.corpus_manifest)
    else:
        for n in ("mock_corpus_train.txt", "mock_corpus_val.txt"):
            shutil.copy(FIX / n, data / n)
        manifest = build_manifest(
            {data / "mock_corpus_train.txt": "train", data / "mock_corpus_val.txt": "val"},
            data / "splits.json")
    for n in ("sft_train.jsonl", "sft_val.jsonl", "qa_test.jsonl", "fact_split.json"):
        shutil.copyfile(ROOT / "data" / "sft_mock" / n, sft_data / n)
    sft_manifest = build_manifest(
        {sft_data / "sft_train.jsonl": "train", sft_data / "sft_val.jsonl": "val",
         sft_data / "qa_test.jsonl": "test"}, sft_data / "splits.json")
    kb_path = ROOT / "data" / "kb" / "kb.json"
    kb = T.load_kb(kb_path)

    # ---- 1-2 tokenizer, token cache ---------------------------------------------------------
    tok = stage("tokenizer_train", lambda: train_tokenizer(manifest, 4096, min_frequency=1))
    tok.save(out / "tokenizer.json")
    model_cfg = ModelConfig.from_yaml(ROOT / "configs" / "model.yaml")
    pre_cfg = TrainConfig.from_yaml(ROOT / "configs" / "train.yaml").with_(
        seeds=seeds, epochs=args.epochs, batch_size=8, warmup_steps=20, val_every=50,
        checkpoint_epochs=tuple(e for e in (1, 2, 3, 5, 8) if e <= args.epochs))
    cache = out / "token_cache"
    stage("token_cache", lambda: prepare_data(manifest, tok, model_cfg, pre_cfg, cache))

    # ---- 3 pretraining ----------------------------------------------------------------------
    stage("pretrain_%d_seeds" % len(seeds), lambda: run_seeds(
        "pretrain", manifest, tok, model_cfg, pre_cfg, runs_root=out, cache_dir=cache))

    # ---- 4 probes at every checkpoint via ModelScorer ---------------------------------------
    probes = build_probes(load_facts(kb_path), seed=0)
    assert_no_leakage(probes)
    probe_raw = stage("probes_modelscorer", lambda: run_model_probes(
        out / "pretrain", tok, probes, seeds, model_cfg))
    probe_raw.to_csv(out / "probes_raw.csv", index=False, encoding="utf-8")

    # ---- 5 SFT ------------------------------------------------------------------------------
    sft_cfg = SFTConfig.from_yaml(ROOT / "configs" / "sft.yaml").with_(seeds=seeds)
    sft_res = stage("sft_%d_seeds" % len(seeds), lambda: run_sft_seeds(
        "sft", out / "pretrain", sft_manifest, tok, sft_cfg, model_cfg.context_len, out))

    # ---- 6 QA evaluation: base zero-shot, base 2-shot, SFT ----------------------------------
    rows = load_qa_rows(sft_manifest, "I01 mock run: E0/E1/E2", log_path=out / "test_access_log.jsonl")
    base = load_base_prompts(ROOT / "configs" / "base_prompts.yaml")
    check_exemplars_disjoint(base["exemplars"], rows)
    prefixes = prompt_prefixes(base)
    if args.limit:
        seen: dict[str, int] = {}
        keep = []
        for r in rows:
            seen[r["subset"]] = seen.get(r["subset"], 0) + 1
            if seen[r["subset"]] <= args.limit:
                keep.append(r)
        rows = keep
    av = load_attribute_values(kb_path)

    def evaluate_all() -> pd.DataFrame:
        tabs = []
        for seed in seeds:
            pre = final_pretrain_checkpoint(out / "pretrain" / f"seed{seed}")
            sft = out / "sft" / f"seed{seed}" / "checkpoints" / "best.pt"
            variants = [("pretrained", pre, "zero_shot", prefixes["zero_shot"]),
                        ("pretrained", pre, "2shot", prefixes["2shot"]),
                        ("sft", sft, "zero_shot", prefixes["zero_shot"])]
            tabs.append(compare_variants(variants, tok, rows, seed, av,
                                         max_new_tokens=sft_cfg.max_new_tokens))
        return pd.concat(tabs, ignore_index=True)

    qa_pred = stage("qa_eval_3_variants", evaluate_all)
    qa_pred.to_csv(out / "qa_predictions.csv", index=False, encoding="utf-8")
    print(comparison_table(qa_pred).to_string(index=False))

    # ---- 7 analysis tables ------------------------------------------------------------------
    build_args = [
        "scripts/build_analysis_tables.py", "--probe", str(out / "probes_raw.csv"),
        "--qa", str(out / "qa_predictions.csv"), "--kb", str(kb_path),
        "--out-dir", str(tables_dir), "--plan", str(ROOT / "data" / "plan" / "plan.jsonl"),
        "--realized-diversity", str(ROOT / "data" / "bank" / "realized_diversity.csv"),
        "--fact-split", str(sft_data / "fact_split.json"), "--tokenizer", str(out / "tokenizer.json"),
    ]
    stage("build_analysis_tables", lambda: run_cli(build_args))

    # ---- 8 analysis (primary + sensitivity), MOCK banner -------------------------------------
    results = out / "results"
    probe_csv, qa_csv = tables_dir / "probe.csv", tables_dir / "qa.csv"
    stage("run_analysis", lambda: (
        run_cli(["scripts/run_analysis.py", "--input", str(probe_csv), "--qa-input", str(qa_csv),
                 "--out", str(results), "--banner-label", "MOCK", "--no-mixed"]),
        run_cli(["scripts/run_sensitivity.py", "--input", str(probe_csv), "--qa-input", str(qa_csv),
                 "--realized-diversity", str(tables_dir / "realized_diversity.csv"),
                 "--out", str(results)])))

    # ---- 9 report inputs and report ----------------------------------------------------------
    def report_inputs() -> None:
        train_docs = read_split(manifest, "train")
        val_docs = read_split(manifest, "val")
        stats = json.loads((cache / "token_stats.json").read_text(encoding="utf-8"))
        train_tokens = stats["train"]["n_tokens_with_eos"]
        any_ckpt = final_pretrain_checkpoint(out / "pretrain" / f"seed{seeds[0]}")
        facts = RI.run_facts(
            kb=kb, model_cfg=model_cfg, train_cfg=pre_cfg.to_dict(), sft_cfg=sft_cfg.to_dict(),
            split_docs={"train": len(train_docs), "val": len(val_docs), "test": 0},
            train_tokens=train_tokens,
            templated_pct=RI.templated_share_pct(kb, train_docs, tok),
            n_doc_types=len({p["doc_type"] for p in T.load_plan(ROOT / "data/plan/plan.jsonl")}),
            n_sweep_configs=0,
            sft_epochs_run=max(s["epochs_done"] for s in sft_res["seeds"].values()),
            seeds=seeds, n_params=RI.count_model_params(any_ckpt),
            prereg_commit=RI.git_head(ROOT, "docs/PREREG.md"), analysis_commit=RI.git_head(ROOT))
        samples = RI.balanced_samples(
            RI.qa_samples(qa_pred, kb, {r["id"]: r["prompt"] for r in rows}) + RI.checkpoint_samples(out / "pretrain", tok, kb))
        RI.write_report_inputs(out / "report_inputs", facts, RI.loss_curves(out / "pretrain", seeds),
                               samples)

    stage("report_inputs", report_inputs)
    build_out = stage("build_report", lambda: run_cli([
        "scripts/build_report.py", "--results-dir", str(results),
        "--inputs-dir", str(out / "report_inputs"), "--out", str(out / "report"),
        "--banner-label", "MOCK"]))
    print(build_out.strip())

    total = round(sum(stages.values()), 2)
    summary = {"label": "MOCK", "seeds": list(seeds), "epochs": args.epochs,
               "eval_questions_per_set": args.limit, "stage_seconds": stages, "total_seconds": total,
               "report_build": build_out.strip().splitlines()[-1] if build_out.strip() else ""}
    Path(args.timings).parent.mkdir(parents=True, exist_ok=True)
    Path(args.timings).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\nstage seconds (MOCK):")
    for k, v in stages.items():
        print(f"  {k:<26}{v:>9.2f}")
    print(f"  {'total':<26}{total:>9.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
