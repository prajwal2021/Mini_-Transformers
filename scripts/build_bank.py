"""Build the sentence bank (P02b7). Stages: pilot (6 facts) or full (all facts + allocation).

--client is required. A real run (openai) spends money, needs --i-understand-this-spends-money and
writes to data/bank_pilot or data/bank; a mock run writes to a mock folder and spends nothing.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import yaml

from slm.data import bank
from slm.data.budget import BudgetExceeded, GlobalBudgetGuard, mode_banner
from slm.data.pilot import OpenAIBackend, load_api_key

ROOT = Path(__file__).resolve().parents[1]
MODEL = "gpt-5.4-mini"


def pilot_facts(needs: dict[str, dict[str, int]]) -> list[str]:
    """Three highest-need facts, one mid (19), one low (9) and one templated-bin fact (4)."""
    ordered = sorted(needs, key=lambda f: (-needs[f]["total"], f))
    top = ordered[:3]
    pick = lambda total: next(f for f in ordered if needs[f]["total"] == total)  # noqa: E731
    return top + [pick(19), pick(9), pick(4)]


def status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def fact_table(results: list[dict], costs: Counter) -> list[str]:
    lines = ["| fact | need (plain+novel) | filled | a | b | c | d | e | f | g | prefixes | "
             "For-lead | mean Jaccard | generated | det valid | judge NO | refills | cost |",
             "| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in results:
        g = r["gates"]
        lines.append(
            f"| {r['fact_id']} | {r['need_plain']}+{r['need_novel']} | {g['filled']} | "
            + " | ".join(status(g[k]) for k in "abcdefg")
            + f" | {g['prefixes']} | {g['for_share']:.0%} | {g['mean_pair_jaccard']:.2f} | "
            f"{r['generated']} | {r['det_valid']} ({r['det_rate']:.0%}) | "
            f"{r['judge_no']}/{r['judged']} ({r['judge_no_rate']:.0%}) | {r['refill_rounds']} | "
            f"${costs[r['fact_id']]:.4f} |"
        )
    return lines


def summary(results: list[dict], runner: bank.Runner) -> dict:
    generated = sum(r["generated"] for r in results)
    valid = sum(r["det_valid"] for r in results)
    judged = sum(r["judged"] for r in results)
    no = sum(r["judge_no"] for r in results)
    return {
        "facts": len(results), "facts_all_gates": sum(r["gates"]["all"] for r in results),
        "generated": generated, "det_valid": valid, "judged": judged, "judge_no": no,
        "det_rate": valid / generated if generated else 0.0,
        "judge_no_rate": no / judged if judged else 0.0,
        "judge_no_of_valid": no / valid if valid else 0.0,
        "cost": sum(runner.usd.values()), "cost_gen": runner.usd["gen"], "cost_judge": runner.usd["judge"],
    }


def write_report(path: Path, results: list[dict], runner: bank.Runner, client: str, stage: str,
                 doc_projection: float, spent_before: float) -> dict:
    s = summary(results, runner)
    sentences = [x for r in results for x in r["sentences"]]
    fact_by_id = {f["fact_id"]: f for f in json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))["measured_facts"]}
    for_lead = sum(bank.starts_with_for_entity(x["text"], fact_by_id[r["fact_id"]]["entity"])
                   for r in results for x in r["sentences"])
    lines = [
        f"Client: {client}", "",
        f"# Sentence bank report ({stage})", "",
        f"Facts built: {s['facts']}; facts meeting A2 (a)-(g): {s['facts_all_gates']}",
        f"Candidates generated {s['generated']}; deterministic acceptance {s['det_rate']:.1%}; "
        f"judged {s['judged']}; judge NO {s['judge_no']} ({s['judge_no_rate']:.1%} of judged, "
        f"{s['judge_no_of_valid']:.1%} of deterministic-valid candidates)",
        f"Cost this stage: ${s['cost']:.4f} (generation ${s['cost_gen']:.4f}, judge ${s['cost_judge']:.4f})",
        f"Share of sentences starting 'For <entity>,': {for_lead / max(1, len(sentences)):.1%}",
        f"A2 projection: spent before {spent_before:.4f} + bank {s['cost']:.4f} + documents "
        f"{doc_projection:.2f} = {spent_before + s['cost'] + doc_projection:.2f} (limit 9.00)",
        "", "## Per-fact gates (A2 a-g)", "",
    ]
    lines += fact_table(results, runner.by_tag)
    if stage == "pilot":
        ordered = sorted(results, key=lambda r: -r["need_plain"])
        for result, limit in ((ordered[0], None), (ordered[1], 12)):
            shown = result["sentences"][:limit]
            lines += ["", f"## Sentences of {result['fact_id']} ({len(shown)} of {len(result['sentences'])})", ""]
            lines += [f"- {x['frame']} ({x['register']}{', reserved' if x['reserved'] else ''}): {x['text']}"
                      for x in shown]
    else:
        frames = Counter(x["frame"] for x in sentences)
        registers = Counter(x["register"] for x in sentences)
        lines += ["", "## Frame distribution", "", "| frame | sentences |", "| --- | ---: |"]
        lines += [f"| {k} | {v} |" for k, v in sorted(frames.items())]
        lines += ["", "## Register distribution", "", "| register | sentences |", "| --- | ---: |"]
        lines += [f"| {k} | {v} |" for k, v in sorted(registers.items())]
        sample = random.Random(20).sample(sentences, min(20, len(sentences)))
        lines += ["", "## 20 random sentences", ""]
        lines += [f"- {x['frame']} ({x['register']}): {x['text']}" for x in sample]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return s


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["mock", "openai"], required=True)
    parser.add_argument("--stage", choices=["pilot", "full"], required=True)
    parser.add_argument("--cap", type=float, default=None, help="spend cap for this stage in USD")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--doc-projection", type=float, default=7.16)
    parser.add_argument("--seed", type=int, default=20261031)
    parser.add_argument("--i-understand-this-spends-money", action="store_true")
    args = parser.parse_args(argv)
    if args.client == "openai" and not args.i_understand_this_spends_money:
        raise SystemExit("Refusing to call the OpenAI API without --i-understand-this-spends-money")
    config = yaml.safe_load((ROOT / "configs" / "generation.yaml").read_text(encoding="utf-8"))
    kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
    plan = [json.loads(x) for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()]
    needs = bank.needs_from_plan(plan)
    frames = bank.load_frames()
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    mock = args.client == "mock"
    default_dir = ROOT / "data" / (("bank_mock_" if mock else "bank_") + ("pilot" if args.stage == "pilot" else "")).rstrip("_")
    if args.stage == "full" and not mock:
        default_dir = ROOT / "data" / "bank"
    out_dir = args.out_dir or default_dir
    cap = args.cap if args.cap is not None else (0.10 if args.stage == "pilot" else 1.20)
    guard = GlobalBudgetGuard(ROOT / "data", out_dir / "ledger.jsonl", config["budget_usd"], cap, config["models"])
    print(mode_banner(args.client, guard.global_spent(), config["budget_usd"]))
    print(f"stage {args.stage}: cap ${cap:.2f}; spent so far ${guard.global_spent():.4f}")
    backend = bank.MockBankBackend() if mock else OpenAIBackend(load_api_key())
    runner = bank.Runner(backend, MODEL, guard, out_dir / "cache", client=args.client)
    wanted = pilot_facts(needs) if args.stage == "pilot" else sorted(facts)
    facts_dir = out_dir / "facts"
    facts_dir.mkdir(parents=True, exist_ok=True)
    spent_before = guard.global_spent()
    results: list[dict] = []
    stopped = None
    for fact_id in wanted:
        saved = facts_dir / f"{fact_id}.json"
        if saved.exists():
            results.append(json.loads(saved.read_text(encoding="utf-8")))
            continue
        try:
            result = bank.build_fact(facts[fact_id], needs[fact_id], kb, frames, runner, args.seed)
        except BudgetExceeded as exc:
            stopped = str(exc)
            break
        saved.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        results.append(result)
        print(f"{fact_id}: need {needs[fact_id]['total']}, gates {'PASS' if result['gates']['all'] else 'FAIL'}, "
              f"cost so far ${sum(runner.usd.values()):.4f}")
    stage_dir = ROOT / "reports" / "tables" / ("mock" if mock else "")
    report = args.report or stage_dir / ("bank_pilot.md" if args.stage == "pilot" else "bank_report.md")
    s = write_report(report, results, runner, args.client, args.stage, args.doc_projection, spent_before)
    if args.stage == "full" and not stopped and len(results) == len(wanted):
        rows = bank.write_bank_files(out_dir, results)
        by_fact: dict[str, list[dict]] = {}
        for r in results:
            by_fact[r["fact_id"]] = r["sentences"]
        allocation = bank.allocate(plan, by_fact, args.seed)
        problems = bank.check_allocation(plan, [dict(r, reserved=r["reserved"]) for r in rows], allocation)
        (out_dir / "allocation.jsonl").write_text(
            "".join(json.dumps(a) + "\n" for a in allocation), encoding="utf-8")
        print(f"allocation: {len(allocation)} mentions; problems: {problems or 'none'}")
        if problems:
            return 5
    all_ok = s["facts_all_gates"] == s["facts"] == len(wanted)
    judge_ok = s["judge_no_rate"] <= 0.10
    gate = "G1" if args.stage == "pilot" else "G2"
    verdict = all_ok and (judge_ok if args.stage == "pilot" else True) and stopped is None
    print(f"GATE {gate}: {'PASS' if verdict else 'FAIL'} ({s['facts_all_gates']}/{len(wanted)} facts meet A2; "
          f"judge NO rate {s['judge_no_rate']:.1%}); stage cost ${s['cost']:.4f}"
          + (f"; stopped: {stopped}" if stopped else ""))
    return 0 if verdict else 3


if __name__ == "__main__":
    raise SystemExit(main())
