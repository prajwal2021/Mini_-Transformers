"""P02b7g: the one real bank pilot (run 4) on F008 and F017 with the reworded frames.

Own directory and ledger (data/bank_pilot4), cap $0.10. Writes reports/tables/bank_pilot_run4.md with
the A2 rows, diversity numbers, per-frame fill counts and reject reasons, and 30 judge-YES samples
for F008. Stops (no iteration) when a fact cannot fill.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import yaml

from slm.data import bank
from slm.data.budget import GlobalBudgetGuard, mode_banner
from slm.data.pilot import OpenAIBackend, load_api_key

ROOT = Path(__file__).resolve().parents[1]
MODEL = "gpt-5.4-mini"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["mock", "openai"], required=True)
    parser.add_argument("--facts", nargs="+", default=["F008", "F017"])
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "bank_pilot4")
    parser.add_argument("--cap", type=float, default=0.10)
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "tables" / "bank_pilot_run4.md")
    parser.add_argument("--i-understand-this-spends-money", action="store_true")
    args = parser.parse_args(argv)
    if args.client == "openai" and not args.i_understand_this_spends_money:
        raise SystemExit("Refusing to call the OpenAI API without --i-understand-this-spends-money")
    config = yaml.safe_load((ROOT / "configs" / "generation.yaml").read_text(encoding="utf-8"))
    kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
    plan = [json.loads(x) for x in (ROOT / "data/plan/plan.jsonl").read_text(encoding="utf-8").splitlines()]
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    needs, frames = bank.needs_from_plan(plan), bank.load_frames()
    backend = bank.MockBankBackend() if args.client == "mock" else OpenAIBackend(load_api_key())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    guard = GlobalBudgetGuard(ROOT / "data", args.out_dir / "ledger_pilot.jsonl", config["budget_usd"],
                              args.cap, config["models"])
    print(mode_banner(args.client, guard.global_spent(), config["budget_usd"]))
    runner = bank.Runner(backend, MODEL, guard, args.out_dir / "cache", client=args.client)
    results: dict[str, dict] = {}
    stopped = ""
    for fact_id in args.facts:
        try:
            results[fact_id] = bank.build_fact(facts[fact_id], needs[fact_id], kb, frames, runner, 20261031)
        except Exception as error:  # budget guard stops the run; report what exists
            stopped = f"{fact_id}: {type(error).__name__}: {error}"
            break
        (args.out_dir / f"{fact_id}.json").write_text(json.dumps(results[fact_id], ensure_ascii=False),
                                                       encoding="utf-8")
    spent = sum(runner.usd.values())
    write_report(args, results, facts, spent, stopped, runner)
    ok = len(results) == len(args.facts) and all(r["gates"]["all"] for r in results.values())
    for fact_id, r in results.items():
        g = r["gates"]
        print(fact_id, f"filled {g['filled']}/{g['need']}", "A2:", "PASS" if g["all"] else "FAIL",
              {k: g[k] for k in "abcdefg"}, f"prefixes {g['prefixes']} meanJ {g['mean_pair_jaccard']:.3f} "
              f"pairs>=0.7 {g['share_pairs_ge_07']:.3f}")
    print(f"spent ${spent:.4f}; stopped: {stopped or 'no'}; G1 pilot part: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 3


def write_report(args, results, facts, spent, stopped, runner) -> None:
    lines = [f"Client: {args.client}", "", "# Sentence bank pilot run 4 (P02b7g): F008 and F017, reworded frames", "",
             f"Spend ${spent:.4f} (cap ${args.cap:.2f}); calls {dict(runner.calls)}." + (f" Stopped: {stopped}" if stopped else ""),
             "", "| fact | need | filled | a | b | c | d | e | f | g | prefixes | mean Jaccard | pairs >= 0.7 | generated | det-valid | judged | NO |",
             "| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for fid, r in results.items():
        g = r["gates"]
        lines.append(f"| {fid} | {r['need_plain']}+{r['need_novel']} | {g['filled']} | "
                     + " | ".join("PASS" if g[k] else "FAIL" for k in "abcdefg")
                     + f" | {g['prefixes']} | {g['mean_pair_jaccard']:.3f} | {g['share_pairs_ge_07']:.3f} | "
                       f"{r['generated']} | {r['det_valid']} | {r['judged']} | {r['judge_no']} |")
    for fid, r in results.items():
        lines += ["", f"## {fid}: selected sentences per frame", "", json.dumps(r["frame_counts"]),
                  "", f"Reject reasons per frame: {json.dumps(r['frame_rejects'])}", "",
                  f"Top reject reasons: {json.dumps(r['top_reject_reasons'])}"]
        nos = [x for x in r["judge_log"] if x["answer"] == "NO"]
        lines += ["", f"Judge NOs ({len(nos)}):"] + [f"- [{x['frame']}] {x['text']} -> {x['reason']}" for x in nos]
    if "F008" in results:
        yes = [x for x in results["F008"]["judge_log"] if x["answer"] == "YES"]
        sample = random.Random(30).sample(yes, min(30, len(yes)))
        lines += ["", "## 30 judge-YES samples for F008 (seed 30)", ""]
        lines += [f"{x['frame']} | {x['text']}" for x in sample]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
