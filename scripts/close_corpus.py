"""P02c5: close the corpus. Steps (run one at a time):

  --step replan3     round 3: the still-unaccepted documents, fresh opener seed, max 2 attempts each
  --step retype6     round 6: test-0004 once as another document type (data/corpus/plan_overrides.json)
  --step regen4      round 4: regeneration set = leaking val/test docs + meta-talk docs
  --step regen5      round 5: the same set again (what is still leaking / has meta-talk)
  --step status      print the current regeneration set without calling the API
  --step finish      drop train meta-talk docs that still fail, assemble, write the split files

Hard budget: the global stop is --global-cap (8.90); a round is refused when the ledger plus a
conservative estimate of the round would exceed it. No API call is made by status/finish.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from slm.data import corpus
from slm.data.leakclass import analyse, exempt_docs
from slm.data.metatalk import genuine_hits

ROOT = Path(__file__).resolve().parents[1]
PER_DOC_ESTIMATE = 0.0035  # about 1.7 attempts at the observed $0.0021 per attempt


def load_run(args: argparse.Namespace):
    spec = importlib.util.spec_from_file_location("run_corpus", ROOT / "scripts" / "run_corpus.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_corpus"] = module
    spec.loader.exec_module(module)
    ns = argparse.Namespace(client="openai", out_dir=None, bank_dir=None, workers=12, cap=6.00,
                            global_cap=args.global_cap, limit=0)
    return module.Run(ns)


def regen_set(run) -> tuple[list[str], list[str], list[str]]:
    docs = run.current_docs()
    info = analyse(docs, run.plan_by_id, run.kb)
    leaking = sorted(exempt_docs(info))
    meta = sorted(d["doc_id"] for d in docs if genuine_hits(d["text"]))
    return sorted(set(leaking) | set(meta)), leaking, meta


def global_spent(run) -> float:
    return run.guard.global_spent()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", choices=["replan3", "retype6", "regen4", "regen5", "regen6", "status", "finish"], required=True)
    parser.add_argument("--global-cap", type=float, default=8.90)
    parser.add_argument("--i-understand-this-spends-money", action="store_true")
    args = parser.parse_args()
    if args.step in ("replan3", "retype6", "regen4", "regen5", "regen6") and not args.i_understand_this_spends_money:
        raise SystemExit("Refusing to call the OpenAI API without --i-understand-this-spends-money")
    run = load_run(args)
    if args.step == "status":
        ids, leaking, meta = regen_set(run)
        print(f"regeneration set {len(ids)}: leaking {len(leaking)}, meta-talk {len(meta)}; "
              f"unaccepted {[r['doc_id'] for r in run.unaccepted()]}; global spend ${global_spent(run):.4f}")
        return 0
    if args.step == "replan3":
        rows = run.unaccepted()
        number, attempts = 3, 2
    elif args.step == "retype6":
        rows = [r for r in run.unaccepted() if r["doc_id"] == "test-0004"]  # plan_overrides.json retypes it
        number, attempts = 6, 2
    elif args.step in ("regen4", "regen5", "regen6"):
        ids, leaking, meta = regen_set(run)
        rows = [run.plan_by_id[i] for i in ids]
        number, attempts = int(args.step[-1]), 5
    else:
        return finish(run)
    estimate = len(rows) * PER_DOC_ESTIMATE
    spent = global_spent(run)
    print(f"round {number}: {len(rows)} docs, global spend ${spent:.4f}, estimate +${estimate:.4f}, stop ${args.global_cap:.2f}")
    if spent + estimate > args.global_cap:
        print("REFUSED: the round could exceed the global budget; stopping.")
        return 3
    stopped = run.generate(number, rows, attempts)
    print(f"round {number} done; stopped={stopped}; global spend ${global_spent(run):.4f}; "
          f"corpus ledger ${run.ledger_spend():.4f}")
    ids, leaking, meta = regen_set(run)
    print(f"after round {number}: regeneration set {len(ids)} (leaking {len(leaking)}, meta-talk {len(meta)}); "
          f"unaccepted {[r['doc_id'] for r in run.unaccepted()]}")
    return 0


def finish(run) -> int:
    dropped_path = run.out / "dropped.json"
    dropped = json.loads(dropped_path.read_text(encoding="utf-8")) if dropped_path.exists() else []
    have = {x["doc_id"] for x in dropped}
    for row in run.unaccepted():
        if row["split"] == "train" and row["doc_id"] not in have:
            dropped.append({"doc_id": row["doc_id"], "reason": "unaccepted (V12) after rounds 0-3"})
            have.add(row["doc_id"])
    ids, _leaking, meta = regen_set(run)
    for doc_id in meta:
        if run.plan_by_id[doc_id]["split"] == "train" and doc_id not in have:
            dropped.append({"doc_id": doc_id, "reason": "meta-talk persists after 2 regeneration rounds"})
            have.add(doc_id)
    dropped_path.write_text(json.dumps(dropped, indent=1), encoding="utf-8")
    print(f"dropped {len(dropped)}: {[x['doc_id'] for x in dropped]}")
    run.assemble()
    write_flags(run)
    return 0


def write_flags(run) -> None:
    """P02c6: disclosed exceptions. leak_flag maps doc id -> its shared 13-grams; meta_flag lists genuine meta-talk docs."""
    docs = run.current_docs()
    info = analyse(docs, run.plan_by_id, run.kb)
    leak: dict[str, list[str]] = {}
    for gram, rec in info.items():
        for doc_id in rec["docs"]:
            if doc_id in exempt_docs(info):
                leak.setdefault(doc_id, []).append(" ".join(gram))
    meta = sorted(d["doc_id"] for d in docs if d["split"] != "train" and genuine_hits(d["text"]))
    flags = {"leak_flag": {k: sorted(v) for k, v in sorted(leak.items())}, "meta_flag": meta}
    (run.out / "flags.json").write_text(json.dumps(flags, indent=1), encoding="utf-8")
    print(f"flags: leak_flag {sorted(leak)}; meta_flag {meta}")


if __name__ == "__main__":
    sys.exit(main())
_ = corpus
