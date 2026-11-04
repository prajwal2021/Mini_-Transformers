"""P02b7e: judge label test, re-judge of the cached run-3 pilot candidates, A2 recompute, report.

Steps: (1) judge the hand-labelled pairs and require zero false YES and >= 90% of positives
accepted; (2) rebuild the six pilot facts from the cached generations with the current judge
(generation is cache-only; a fact that is still short may refill under its own cap with --refill);
(3) write reports/tables/bank_pilot.md with the A2 table, the judge NO rate before and after, a
seeded sample of 40 judge-YES sentences and every judge NO of F002 and F004 with its reason.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import yaml

from slm.data import bank
from slm.data.budget import GlobalBudgetGuard, mode_banner
from slm.data.pilot import OpenAIBackend, load_api_key

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "configs" / "judge_labels.json"
MODEL = "gpt-5.4-mini"


def label_test(runner: bank.Runner, labels: list[dict]) -> dict:
    """Judge the labelled pairs in batches of the production size; return the confusion table."""
    answers: list[tuple[str, str]] = []
    for start in range(0, len(labels), bank.JUDGE_BATCH):
        batch = labels[start : start + bank.JUDGE_BATCH]
        text = runner.call("judge", bank.judge_prompt([(x["ref"], x["cand"]) for x in batch]), "labels")
        answers += bank.parse_judge_full(text, len(batch))
    tp = fn = fp = tn = 0
    wrong = []
    for item, (answer, reason) in zip(labels, answers):
        if item["label"] == "YES":
            tp += answer == "YES"
            fn += answer == "NO"
        else:
            fp += answer == "YES"
            tn += answer == "NO"
        if answer != item["label"]:
            wrong.append({**item, "answer": answer, "reason": reason})
    positives, negatives = tp + fn, fp + tn
    return {
        "tp": tp, "fn": fn, "fp": fp, "tn": tn, "positives": positives, "negatives": negatives,
        "recall": tp / positives, "wrong": wrong,
        "passes": fp == 0 and tp / positives >= 0.9 and positives >= 15 and negatives >= 25,
    }


def confusion_lines(c: dict) -> list[str]:
    lines = ["| | judge YES | judge NO |", "| --- | ---: | ---: |",
             f"| labelled YES ({c['positives']}) | {c['tp']} | {c['fn']} |",
             f"| labelled NO ({c['negatives']}) | {c['fp']} | {c['tn']} |", "",
             f"Positives accepted: {c['tp']}/{c['positives']} ({c['recall']:.0%}); false YES: {c['fp']}; "
             f"label-set gate: {'PASS' if c['passes'] else 'FAIL'}."]
    for w in c["wrong"]:
        lines.append(f"- {w['kind']}: labelled {w['label']}, judge {w['answer']} ({w['reason']}): "
                     f"{w['cand']}  [reference: {w['ref']}]")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["mock", "openai"], required=True)
    parser.add_argument("--src-dir", type=Path, default=ROOT / "data" / "bank_pilot3")
    parser.add_argument("--cap", type=float, default=0.05, help="cap for the label test and re-judge")
    parser.add_argument("--refill-cap", type=float, default=0.05)
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "tables" / "bank_pilot.md")
    parser.add_argument("--labels-only", action="store_true")
    parser.add_argument("--i-understand-this-spends-money", action="store_true")
    args = parser.parse_args(argv)
    if args.client == "openai" and not args.i_understand_this_spends_money:
        raise SystemExit("Refusing to call the OpenAI API without --i-understand-this-spends-money")
    mock = args.client == "mock"
    config = yaml.safe_load((ROOT / "configs" / "generation.yaml").read_text(encoding="utf-8"))
    kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
    plan = [json.loads(x) for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()]
    needs, frames = bank.needs_from_plan(plan), bank.load_frames()
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    backend = bank.MockBankBackend() if mock else OpenAIBackend(load_api_key())
    guard = GlobalBudgetGuard(ROOT / "data", args.src_dir / "ledger_rejudge.jsonl", config["budget_usd"],
                              args.cap, config["models"])
    print(mode_banner(args.client, guard.global_spent(), config["budget_usd"]))
    runner = bank.Runner(backend, MODEL, guard, args.src_dir / "cache", client=args.client)
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    confusion = label_test(runner, labels)
    print(f"label test: TP {confusion['tp']} FN {confusion['fn']} FP {confusion['fp']} TN {confusion['tn']} "
          f"-> {'PASS' if confusion['passes'] else 'FAIL'}; spent ${sum(runner.usd.values()):.4f}")
    if args.labels_only or not confusion["passes"]:
        for line in confusion_lines(confusion):
            print(line)
        return 0 if confusion["passes"] else 3

    run3 = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (args.src_dir / "facts").glob("*.json")}
    out_facts = args.src_dir / "facts_v3"
    out_facts.mkdir(exist_ok=True)
    results: dict[str, dict] = {}
    runner.cache_only_gen = True
    judge_spent_before_facts = sum(runner.usd.values())
    for fact_id in run3:
        results[fact_id] = bank.build_fact(facts[fact_id], needs[fact_id], kb, frames, runner, 20261031)
    judge_cost = sum(runner.usd.values()) - judge_spent_before_facts
    short = [f for f, r in results.items() if not r["gates"]["all"]]
    refill_cost = 0.0
    if short:
        print("still short after the re-judge:", short)
        refill_guard = GlobalBudgetGuard(ROOT / "data", args.src_dir / "ledger_refill.jsonl",
                                         config["budget_usd"], args.refill_cap, config["models"])
        refill_runner = bank.Runner(backend, MODEL, refill_guard, args.src_dir / "cache", client=args.client)
        for fact_id in short:
            results[fact_id] = bank.build_fact(facts[fact_id], needs[fact_id], kb, frames, refill_runner, 20261031)
        refill_cost = sum(refill_runner.usd.values())
    for fact_id, result in results.items():
        (out_facts / f"{fact_id}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    write_report(args, results, run3, confusion, facts, judge_cost, refill_cost, runner)
    ok = all(r["gates"]["all"] for r in results.values()) and confusion["passes"]
    print(f"GATE G1 (A2b): {'PASS' if ok else 'FAIL'}; facts meeting A2: "
          f"{sum(r['gates']['all'] for r in results.values())}/{len(results)}; re-judge ${judge_cost:.4f}, refill ${refill_cost:.4f}")
    return 0 if ok else 3


def rate(results: dict[str, dict]) -> tuple[int, int]:
    return (sum(r["judge_no"] for r in results.values()), sum(r["judged"] for r in results.values()))


def write_report(args, results, run3, confusion, facts, judge_cost, refill_cost, runner) -> None:
    order = sorted(results)
    no3, judged3 = rate(run3)
    no_new, judged_new = rate(results)
    need_total = sum(r["need_plain"] + r["need_novel"] for r in results.values())
    per_candidate = judge_cost / judged_new if judged_new else 0.0
    full_need = 1780
    projected_judged = judged_new / need_total * full_need
    lines = [
        f"Client: {args.client}", "", "# Sentence bank pilot: judge v3 re-judge of the run-3 candidates", "",
        f"Judge NO rate before (run 3, old judge): {no3}/{judged3} ({no3 / judged3:.1%}); "
        f"after (judge v3): {no_new}/{judged_new} ({no_new / judged_new:.1%}).",
        f"Re-judge cost ${judge_cost:.4f} for {judged_new} candidates (${per_candidate:.5f} each); refill cost ${refill_cost:.4f}.",
        f"Projected full-bank judge cost: about {projected_judged:.0f} judged candidates x ${per_candidate:.5f} = "
        f"${projected_judged * per_candidate:.2f} (all 120 facts, need 1780 sentences, same candidate-to-need ratio).",
        "", "## Judge label set", ""] + confusion_lines(confusion) + [
        "", "## Per-fact A2 gates (a)-(g)", "",
        "| fact | need | filled | a | b | c | d | e | f | g | prefixes | mean Jaccard | judged | NO |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |"]
    for fid in order:
        r, g = results[fid], results[fid]["gates"]
        lines.append(
            f"| {fid} | {r['need_plain']}+{r['need_novel']} | {g['filled']} | "
            + " | ".join("PASS" if g[k] else "FAIL" for k in "abcdefg")
            + f" | {g['prefixes']} | {g['mean_pair_jaccard']:.2f} | {r['judged']} | {r['judge_no']} ({r['judge_no_rate']:.0%}) |")
    causes: Counter[str] = Counter()
    for r in results.values():
        causes.update(x["reason"] for x in r["judge_log"] if x["answer"] == "NO")
    lines += ["", "Judge NO reasons (all six facts): " + ", ".join(f"{k} {v}" for k, v in causes.most_common()), ""]
    yes_rows = [(fid, x) for fid in order for x in results[fid]["judge_log"] if x["answer"] == "YES"]
    sample = random.Random(40).sample(yes_rows, min(40, len(yes_rows)))
    lines += ["## 40 sampled judge-YES sentences (seed 40)", ""]
    for number, (fid, x) in enumerate(sample, start=1):
        lines.append(f"{number}. [{fid} {x['frame']}] {x['text']}  (canonical: {facts[fid]['canonical_sentence']})")
    for fid in ("F002", "F004"):
        if fid in results:
            nos = [x for x in results[fid]["judge_log"] if x["answer"] == "NO"]
            lines += ["", f"## All judge NOs of {fid} ({len(nos)}); canonical: {facts[fid]['canonical_sentence']}", ""]
            lines += [f"- [{x['frame']}] {x['text']}  -> reason: {x['reason']}" for x in nos]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
