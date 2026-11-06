# ruff: noqa: E501
"""Real-run orchestrator with stages and resume (R00 3). Config: configs/real.yaml.

    python scripts/run_real.py --config configs/real.yaml [--only S ...] [--from S] [--until S] [--force] [--list]

Stages, in order: tokenizer, token_cache, sweep, sizing, freeze, pretrain, probes, sft, qa_eval,
samples, tables, analysis, report. Each writes <out_dir>/stages/<name>.json (status, seconds, summary) and is
skipped on a rerun when that file says ok for the same config; --force reruns, and running a stage
invalidates every later one. Nothing before ``freeze`` reads test data. ``freeze`` refuses when any
test probe, QA test prediction or ledger entry exists. No network, no API call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import replace
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
STAGES = ["tokenizer", "token_cache", "sweep", "sizing", "freeze", "pretrain", "probes", "sft",
          "qa_eval", "samples", "tables", "analysis", "report"]


class Ctx:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.mock = cfg["mode"] == "mock"
        self.out = ROOT / cfg["out_dir"]
        self.kb_path = ROOT / cfg["kb"]
        self.ledger = ROOT / cfg["ledger"]
        self.prereg = ROOT / cfg["prereg"]

    def p(self, key: str) -> Path:
        return ROOT / self.cfg[key]

    # ---- shared objects ------------------------------------------------------------------
    def manifest(self):
        from slm.split_manifest import SplitManifest

        return SplitManifest.load(self.out / "data" / "splits.json" if self.mock else self.p("corpus_manifest"))

    def tokenizer(self):
        from slm.tokenizer import BPETokenizer

        return BPETokenizer.load(self.out / "tokenizer.json")

    def model_cfg(self, which: str = "small"):
        from slm.model import ModelConfig

        base = ModelConfig.from_yaml(self.p("model_config"))
        if which == "large":
            base = replace(base, **self.cfg["model_large"])
        return replace(base, vocab_size=self.cfg["tokenizer"]["vocab_size"])

    def train_cfg(self):
        from slm.train import TrainConfig

        return TrainConfig.from_yaml(self.p("train_config")).with_(**{
            k: (tuple(v) if isinstance(v, list) else v) for k, v in self.cfg["train_overrides"].items()})

    def sft_cfg(self):
        from slm.sft_train import SFTConfig

        return SFTConfig.from_yaml(self.p("sft_config")).with_(
            seeds=tuple(self.cfg["final_seeds"]), **self.cfg["sft_overrides"])

    def stage_json(self, name: str) -> Path:
        return self.out / "stages" / f"{name}.json"

    def read(self, name: str) -> dict:
        return json.loads((self.out / name).read_text(encoding="utf-8"))

    def final(self) -> dict:
        path = self.out / "final_config.json"
        if not path.exists():
            raise SystemExit("final_config.json is missing: run the sizing stage first")
        return json.loads(path.read_text(encoding="utf-8"))

    def require_freeze(self) -> dict:
        from slm.integration.freeze import FreezeRefused, verify

        try:
            return verify(self.prereg)
        except FreezeRefused as exc:
            raise SystemExit(f"stage needs a valid freeze: {exc}") from exc


def run_cli(args: list[str]) -> str:
    p = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(args)}\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}")
    return p.stdout


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


# ---- stages ------------------------------------------------------------------------------------


def st_tokenizer(c: Ctx) -> dict:
    from slm.split_manifest import build_manifest
    from slm.tokenizer import train_tokenizer

    c.out.mkdir(parents=True, exist_ok=True)
    if c.mock:
        d = c.out / "data"
        d.mkdir(parents=True, exist_ok=True)
        for n in ("mock_corpus_train.txt", "mock_corpus_val.txt"):
            shutil.copy(FIX / n, d / n)
        build_manifest({d / "mock_corpus_train.txt": "train", d / "mock_corpus_val.txt": "val"}, d / "splits.json")
        shutil.copy(ROOT / "docs" / "PREREG.md", c.prereg)  # a mock copy; the real file is never frozen here
    elif not c.p("corpus_manifest").exists():
        raise SystemExit(f"corpus manifest {c.p('corpus_manifest')} does not exist yet (P02c on main)")
    tc = c.cfg["tokenizer"]
    tok = train_tokenizer(c.manifest(), tc["vocab_size"], min_frequency=tc["min_frequency"])  # train files only
    tok.save(c.out / "tokenizer.json")
    return {"vocab_size": tok.vocab_size, "tokenizer_hash": tok.hash(), "fit_on": "train files of the manifest only"}


def st_token_cache(c: Ctx) -> dict:
    from slm.train.runner import prepare_data

    _, _, meta = prepare_data(c.manifest(), c.tokenizer(), c.model_cfg(), c.train_cfg(), c.out / "token_cache")
    stats = c.read("token_cache/token_stats.json")
    summary = {
        "tokens_per_word": {s: stats[s]["tokens_per_word"] for s in ("train", "val")},
        "share_docs_over_context": {s: stats[s]["share_docs_over_context"] for s in ("train", "val")},
        "context_len": stats["train"]["context_len"],
        "corpus_tokens_per_split": {s: stats[s]["n_tokens_with_eos"] for s in ("train", "val")} | {"test": None},
        "test_tokens_note": "not counted: that would be a test read, which only the probe and QA stages do (ledger)",
        "packing": meta["packing"],
    }
    write_json(c.out / "token_cache" / "stats_summary.json", summary)
    return summary


def st_sweep(c: Ctx) -> dict:
    from slm.train.runner import prepare_data
    from slm.train.sweep import run_sweep

    sw = c.cfg["sweep"]
    cfg = c.train_cfg().with_(epochs=sw["epochs"])
    train_ds, val_ds, meta = prepare_data(c.manifest(), c.tokenizer(), c.model_cfg(), cfg, c.out / "token_cache")
    res = run_sweep(c.model_cfg(), cfg, train_ds, val_ds, c.out / "sweep", sw["grid"], seed=sw["seed"], meta=meta)
    return {"n_configs": len(res["results"]), "chosen": res["chosen"], "selection": "validation loss only"}


def st_sizing(c: Ctx) -> dict:
    from slm.model import Transformer
    from slm.model.transformer import count_parameters
    from slm.train.pretrain import train_run
    from slm.train.runner import prepare_data
    from slm.train.sweep import select_best

    sw, chosen = c.cfg["sweep"], c.read("sweep/chosen.json")
    cfg = c.train_cfg().with_(epochs=sw["epochs"], lr=chosen["lr"], dropout=chosen["dropout"])
    small, large = c.model_cfg("small"), c.model_cfg("large")
    train_ds, val_ds, meta = prepare_data(c.manifest(), c.tokenizer(), large, cfg, c.out / "token_cache")
    s = train_run(large, cfg, train_ds, val_ds, c.out / "sizing" / "large", sw["seed"], meta=meta, resume=False)
    scheduled = set(cfg.save_epochs())
    row = {"status": "ok", "val_by_epoch": {str(e): v for e, v in s["val_by_epoch"].items() if e in scheduled}}
    big = select_best([row])
    small_best = {"best_val": chosen["best_val"], "best_epoch": chosen["best_epoch"]}
    pick = "large" if big["best_val"] < small_best["best_val"] else "small"  # validation loss only
    win = big if pick == "large" else small_best
    schedule = [e for e in cfg.checkpoint_epochs if e <= win["best_epoch"]]
    final = {"model": (large if pick == "large" else small).to_dict(), "size": pick,
             "lr": chosen["lr"], "dropout": chosen["dropout"], "epochs": int(win["best_epoch"]),
             "checkpoint_epochs": sorted(set(schedule) | {int(win["best_epoch"])})}
    write_json(c.out / "final_config.json", final)
    out = {"small": {"params": count_parameters(Transformer(small)), **small_best},
           "large": {"params": count_parameters(Transformer(large)), "best_val": big["best_val"], "best_epoch": big["best_epoch"]},
           "selected": pick, "rule": "lower best validation loss, same lr/dropout/epochs/token budget; no probes", "final_config": final}
    write_json(c.out / "sizing" / "chosen.json", out)
    return out


def st_freeze(c: Ctx) -> dict:
    from slm.integration.freeze import FreezeRefused, freeze

    try:
        rec = freeze(c.prereg, c.out, c.ledger, ROOT)
    except FreezeRefused as exc:
        raise SystemExit(f"FREEZE REFUSED: {exc}") from exc
    write_json(c.out / "freeze.json", rec)
    return {"prereg": str(c.prereg), "prereg_sha256": rec["prereg_sha256"], "commit": rec["git"]["commit"],
            "dirty": rec["git"]["dirty"], "already_frozen": rec.get("already_frozen", False)}


def final_train_cfg(c: Ctx):
    f = c.final()
    return c.train_cfg().with_(seeds=tuple(c.cfg["final_seeds"]), epochs=f["epochs"], lr=f["lr"], dropout=f["dropout"],
                               checkpoint_epochs=tuple(f["checkpoint_epochs"]))


def st_pretrain(c: Ctx) -> dict:
    from slm.model import ModelConfig
    from slm.train.runner import run_seeds

    c.require_freeze()
    res = run_seeds("pretrain", c.manifest(), c.tokenizer(), ModelConfig.from_dict(c.final()["model"]),
                    final_train_cfg(c), runs_root=c.out, cache_dir=c.out / "token_cache")
    return {"seeds": {str(k): {"epochs_done": v.get("epochs_done"), "final_val": (list(v["val_by_epoch"].values()) or [None])[-1],
                              "wall_seconds": round(v["wall_seconds"], 1)} for k, v in res["seeds"].items()},
            "config": final_train_cfg(c).to_dict()}


def st_probes(c: Ctx) -> dict:
    from slm.eval.probes import assert_no_leakage, build_probes, load_facts
    from slm.guard import record_test_use
    from slm.integration.probing import run_model_probes
    from slm.model import ModelConfig

    c.require_freeze()
    seeds = tuple(c.cfg["final_seeds"])
    probes = build_probes(load_facts(c.kb_path), seed=0)
    assert_no_leakage(probes)
    record_test_use("R00 probes: test split at every checkpoint incl. init", log_path=c.ledger,
                    files=[{"path": str(c.kb_path), "sha256": hashlib.sha256(c.kb_path.read_bytes()).hexdigest()}],
                    caller="scripts/run_real.py:st_probes")
    cfg = replace(ModelConfig.from_dict(c.final()["model"]), dropout=c.final()["dropout"])
    raw = run_model_probes(c.out / "pretrain", c.tokenizer(), probes, seeds, cfg)  # include_init=True: untrained model
    (c.out / "probes").mkdir(exist_ok=True)
    raw.to_csv(c.out / "probes" / "probes_raw.csv", index=False, encoding="utf-8")
    t = raw[raw["split"] == "test"]
    by = t.groupby(t["checkpoint"].astype(str))["stored"].mean().to_dict()
    return {"rows": len(raw), "checkpoints": sorted(raw["checkpoint"].astype(str).unique(), key=lambda x: (x != "init", int(x) if x != "init" else 0)),
            "has_init": bool((raw["checkpoint"].astype(str) == "init").any()), "stored_rate_test_by_checkpoint": by,
            "ledger": str(c.ledger)}


def sft_manifest(c: Ctx):
    from slm.sft.build import verify_datasets
    from slm.split_manifest import build_manifest

    verify_datasets(c.kb_path, c.p("sft_dir"), c.p("eval_dir"))
    d = c.out / "sft_data"
    d.mkdir(parents=True, exist_ok=True)
    for n in ("sft_train.jsonl", "sft_val.jsonl", "fact_split.json"):
        shutil.copyfile(c.p("sft_dir") / n, d / n)
    shutil.copyfile(c.p("eval_dir") / "qa_test.jsonl", d / "qa_test.jsonl")
    return build_manifest({d / "sft_train.jsonl": "train", d / "sft_val.jsonl": "val", d / "qa_test.jsonl": "test"}, d / "splits.json")


def st_sft(c: Ctx) -> dict:
    from slm.model import ModelConfig
    from slm.sft_train import run_sft_seeds

    c.require_freeze()
    ctx_len = ModelConfig.from_dict(c.final()["model"]).context_len
    res = run_sft_seeds("sft", c.out / "pretrain", sft_manifest(c), c.tokenizer(), c.sft_cfg(), ctx_len, c.out)
    return {"seeds": {str(k): {"epochs_done": v["epochs_done"], "wall_seconds": round(v["wall_seconds"], 1)} for k, v in res["seeds"].items()}}


def st_qa_eval(c: Ctx) -> dict:
    from slm.sft_eval import (
        Taxonomy,
        check_exemplars_disjoint,
        compare_variants,
        comparison_table,
        load_attribute_values,
        load_base_prompts,
        load_qa_rows,
        prompt_prefixes,
    )
    from slm.sft_train import final_pretrain_checkpoint

    c.require_freeze()
    seeds = tuple(c.cfg["final_seeds"])
    rows = load_qa_rows(sft_manifest(c), "R00 QA eval: E0/E1/E2, base 0-shot, base 2-shot, SFT", log_path=c.ledger,
                        caller="scripts/run_real.py:st_qa_eval")
    base = load_base_prompts(c.p("base_prompts"))
    check_exemplars_disjoint(base["exemplars"], rows)
    prefixes = prompt_prefixes(base)
    lim = c.cfg["qa_limit"]
    if lim:
        seen: dict[str, int] = {}
        keep = []
        for r in rows:
            seen[r["subset"]] = seen.get(r["subset"], 0) + 1
            if seen[r["subset"]] <= lim:
                keep.append(r)
        rows = keep
    av = load_attribute_values(c.kb_path)
    tok, tabs = c.tokenizer(), []
    for seed in seeds:
        pre = final_pretrain_checkpoint(c.out / "pretrain" / f"seed{seed}")
        sft = c.out / "sft" / f"seed{seed}" / "checkpoints" / "best.pt"
        variants = [("pretrained", pre, "zero_shot", prefixes["zero_shot"]), ("pretrained", pre, "2shot", prefixes["2shot"]),
                    ("sft", sft, "zero_shot", prefixes["zero_shot"])]
        tabs.append(compare_variants(variants, tok, rows, seed, av, max_new_tokens=c.sft_cfg().max_new_tokens,
                                     taxonomy=Taxonomy.from_kb(c.kb_path), ranking=True))
    qa = pd.concat(tabs, ignore_index=True)
    (c.out / "qa").mkdir(exist_ok=True)
    qa.to_csv(c.out / "qa" / "qa_predictions.csv", index=False, encoding="utf-8")
    write_json(c.out / "qa" / "question_prompts.json", {r["id"]: r["prompt"] for r in rows})
    tab = comparison_table(qa)
    return {"rows": len(qa), "questions_per_set": {k: sum(1 for r in rows if r["subset"] == k) for k in ("E0", "E1", "E2")},
            "comparison": json.loads(tab.to_json(orient="records"))}


def st_samples(c: Ctx) -> dict:
    """R01: samples from every seed-0 checkpoint and `init`, flagged by the taxonomy; 6 + 6 selected."""
    import hashlib

    from slm.guard import record_test_use
    from slm.integration import samples as S

    c.require_freeze()
    label = "MOCK" if c.mock else "REAL"
    kb = json.loads(c.kb_path.read_text(encoding="utf-8"))
    record_test_use("R01 checkpoint samples: canonical prefixes and novel wordings of KB facts", log_path=c.ledger,
                    files=[{"path": str(c.kb_path), "sha256": hashlib.sha256(c.kb_path.read_bytes()).hexdigest()}],
                    caller="scripts/run_real.py:st_samples")
    df = S.run_samples(c.out / "pretrain", c.tokenizer(), kb, seed=0, data_status=label)
    sel = S.select_samples(df, 6)
    d = c.out / "samples"
    d.mkdir(exist_ok=True)
    df.to_csv(d / "samples.csv", index=False, encoding="utf-8")
    sel.to_csv(d / "samples_selected.csv", index=False, encoding="utf-8")
    (d / "samples.md").write_text(S.to_markdown(df, sel, 6, label), encoding="utf-8")
    return {"rows": len(df), "selected": sel["selected_as"].value_counts().to_dict(), "label": label}


def st_tables(c: Ctx) -> dict:
    d = c.out / "analysis_inputs"
    args = ["scripts/build_analysis_tables.py", "--probe", str(c.out / "probes" / "probes_raw.csv"),
            "--qa", str(c.out / "qa" / "qa_predictions.csv"), "--kb", str(c.kb_path), "--out-dir", str(d),
            "--plan", str(c.p("plan")), "--realized-diversity", str(c.p("realized_diversity")),
            "--fact-split", str(c.out / "sft_data" / "fact_split.json"), "--tokenizer", str(c.out / "tokenizer.json")]
    if not c.mock:
        args += ["--manifest", str(c.p("corpus_manifest"))]  # measured exposure from the train files
    run_cli(args)
    return c.read("analysis_inputs/tables_summary.json")


def st_analysis(c: Ctx) -> dict:
    d, res = c.out / "analysis_inputs", c.out / "results"
    flags = ["--banner-label", "MOCK", "--no-mixed"] if c.mock else ["--real"]
    run_cli(["scripts/run_analysis.py", "--input", str(d / "probe.csv"), "--qa-input", str(d / "qa.csv"), "--out", str(res), *flags])
    run_cli(["scripts/run_sensitivity.py", "--input", str(d / "probe.csv"), "--qa-input", str(d / "qa.csv"),
             "--realized-diversity", str(d / "realized_diversity.csv"), "--out", str(res)])
    return {"results_dir": str(res), "banner": "MOCK" if c.mock else "off (real)"}


def st_report(c: Ctx) -> dict:
    from slm.integration import report_inputs as RI
    from slm.integration import tables as T
    from slm.model import ModelConfig
    from slm.sft_train import final_pretrain_checkpoint
    from slm.tokenizer import read_split

    rec = c.require_freeze()  # --real only after the freeze step has run (and PREREG is unchanged)
    kb, tok, manifest, seeds = T.load_kb(c.kb_path), c.tokenizer(), c.manifest(), tuple(c.cfg["final_seeds"])
    qa = pd.read_csv(c.out / "qa" / "qa_predictions.csv")
    prompts = c.read("qa/question_prompts.json")
    train_docs, val_docs = read_split(manifest, "train"), read_split(manifest, "val")
    stats = c.read("token_cache/token_stats.json")
    f = c.final()
    sft_res = [json.loads(p.read_text(encoding="utf-8")) for p in (c.out / "sft").glob("seed*/summary.json")]
    facts = RI.run_facts(
        kb=kb, model_cfg=ModelConfig.from_dict(f["model"]), train_cfg=final_train_cfg(c).to_dict(), sft_cfg=c.sft_cfg().to_dict(),
        split_docs={"train": len(train_docs), "val": len(val_docs), "test": 0}, train_tokens=stats["train"]["n_tokens_with_eos"],
        templated_pct=RI.templated_share_pct(kb, train_docs, tok), n_doc_types=len({p["doc_type"] for p in T.load_plan(c.p("plan"))}),
        n_sweep_configs=len(c.read("sweep/results.json")), sft_epochs_run=max([s.get("epochs_done", 0) for s in sft_res] or [0]),
        seeds=seeds, n_params=RI.count_model_params(final_pretrain_checkpoint(c.out / "pretrain" / f"seed{seeds[0]}")),
        prereg_commit=rec["git"]["commit"], analysis_commit=RI.git_head(ROOT))
    chosen = pd.read_csv(c.out / "samples" / "samples_selected.csv", keep_default_na=False)
    from slm.integration.samples import categories

    samples = RI.balanced_samples(RI.qa_samples(qa, kb, prompts) + categories(chosen), per_category=3, limit=14)
    RI.write_report_inputs(c.out / "report_inputs", facts, RI.loss_curves(c.out / "pretrain", seeds), samples)
    flags = ["--banner-label", "MOCK"] if c.mock else ["--real"]
    out = run_cli(["scripts/build_report.py", "--results-dir", str(c.out / "results"), "--inputs-dir", str(c.out / "report_inputs"),
                   "--out", str(c.out / "report"), *flags])
    return {"build_output": out.strip().splitlines()[-1] if out.strip() else "", "banner": "MOCK" if c.mock else "off (real)"}


FUNCS = {"tokenizer": st_tokenizer, "token_cache": st_token_cache, "sweep": st_sweep, "sizing": st_sizing, "freeze": st_freeze,
         "pretrain": st_pretrain, "probes": st_probes, "sft": st_sft, "qa_eval": st_qa_eval, "samples": st_samples, "tables": st_tables,
         "analysis": st_analysis, "report": st_report}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "configs" / "real.yaml"))
    ap.add_argument("--only", nargs="+", choices=STAGES)
    ap.add_argument("--from", dest="from_", choices=STAGES)
    ap.add_argument("--until", choices=STAGES)
    ap.add_argument("--force", action="store_true", help="rerun the selected stages even when they are ok")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)
    cfg_text = Path(args.config).read_text(encoding="utf-8")
    cfg = yaml.safe_load(cfg_text)
    cfg_hash = hashlib.sha256(cfg_text.encode()).hexdigest()
    c = Ctx(cfg)
    if args.list:
        for s in STAGES:
            p = c.stage_json(s)
            print(f"{s:<12}{json.loads(p.read_text())['status'] if p.exists() else '-'}")
        return 0
    print("=" * 78 + f"\n  run_real: mode={cfg['mode']} out={cfg['out_dir']}"
          + ("  MOCK - NOTHING HERE IS A RESULT" if c.mock else "") + "\n" + "=" * 78)
    i0 = STAGES.index(args.from_) if args.from_ else 0
    i1 = STAGES.index(args.until) if args.until else len(STAGES) - 1
    chosen = [s for s in STAGES[i0:i1 + 1] if not args.only or s in args.only]
    seconds: dict[str, float] = {}
    for name in chosen:
        path = c.stage_json(name)
        if path.exists() and not args.force:
            old = json.loads(path.read_text(encoding="utf-8"))
            if old["status"] == "ok" and old["config_sha256"] == cfg_hash:
                print(f"[stage] {name}: ok already ({old['seconds']} s), skipped")
                seconds[name] = 0.0
                continue
        for later in STAGES[STAGES.index(name):]:  # a rerun makes every later stage stale
            c.stage_json(later).unlink(missing_ok=True)
        print(f"[stage] {name} ...", flush=True)
        t = time.perf_counter()
        rec = {"stage": name, "mode": cfg["mode"], "config_sha256": cfg_hash}
        try:
            summary = FUNCS[name](c)
        except BaseException as exc:
            rec |= {"status": "failed", "seconds": round(time.perf_counter() - t, 2),
                    "error": "".join(traceback.format_exception_only(type(exc), exc)).strip()}
            write_json(path, rec)
            print(f"[stage] {name}: FAILED - {rec['error']}", file=sys.stderr)
            raise
        seconds[name] = round(time.perf_counter() - t, 2)
        write_json(path, rec | {"status": "ok", "seconds": seconds[name], "summary": summary})
        print(f"[stage] {name}: {seconds[name]} s", flush=True)
    total = round(sum(seconds.values()), 2)
    write_json(c.out / "run_summary.json", {"mode": cfg["mode"], "stage_seconds": seconds, "total_seconds": total})
    print("\nstage seconds:" + ("  (MOCK)" if c.mock else ""))
    for k, v in seconds.items():
        print(f"  {k:<14}{v:>9.2f}")
    print(f"  {'total':<14}{total:>9.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
