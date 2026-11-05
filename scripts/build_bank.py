"""Build the sentence bank (P02b7). Stages: pilot (6 facts) or full (all facts + allocation).

--client is required. A real run (openai) spends money, needs --i-understand-this-spends-money and
writes to data/bank_pilot or data/bank; a mock run writes to a mock folder and spends nothing.

Full stage (P02b7h): every fact is processed even if one raises; one refill pass (more refill rounds,
the earlier rounds replay from the cache for free) re-runs the facts that fail A2 (a)-(g); the stage
stops before allocation when facts still fail.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from slm.data import bank
from slm.data.budget import BudgetExceeded, GlobalBudgetGuard, mode_banner
from slm.data.pilot import OpenAIBackend, load_api_key

ROOT = Path(__file__).resolve().parents[1]
MODEL = "gpt-5.4-mini"
REFILL_PASS_ROUNDS = 6  # rounds allowed in the refill pass (the first three replay from the cache)
TIGHTENED = ("skyport_daily_pet_cap", "species_max_combined_weight", "species_min_age_weeks",
             "compensation_claim_window_days", "skyport_quarantine_room_capacity",
             "airship_onboard_handler_name")


def pilot_facts(needs: dict[str, dict[str, int]]) -> list[str]:
    """Three highest-need facts, one mid (19), one low (9) and one templated-bin fact (4)."""
    ordered = sorted(needs, key=lambda f: (-needs[f]["total"], f))
    top = ordered[:3]
    pick = lambda total: next(f for f in ordered if needs[f]["total"] == total)  # noqa: E731
    return top + [pick(19), pick(9), pick(4)]


def status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def ledger_costs(path: Path) -> Counter:
    """Real (non-mock) cost per fact tag from a ledger file."""
    costs: Counter = Counter()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                if entry.get("client") != "mock":
                    costs[entry.get("doc_id")] += entry.get("usd", 0.0)
    return costs


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


def summary(results: list[dict], cost: float, cost_gen: float, cost_judge: float) -> dict:
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
        "cost": cost, "cost_gen": cost_gen, "cost_judge": cost_judge,
    }


def word_jaccard(a: str, b: str) -> float:
    x, y = set(a.split()), set(b.split())
    return len(x & y) / len(x | y) if x | y else 0.0


def core_stats(result: dict, fact: dict) -> dict:
    """Share of unique core clauses and mean pairwise Jaccard of the cores of one fact."""
    cores = [bank.core_clause(x["text"], fact["entity"], fact["value"]) for x in result["sentences"]]
    pairs = [word_jaccard(a, b) for i, a in enumerate(cores) for b in cores[i + 1 :]]
    return {"unique": len(set(cores)) / len(cores) if cores else 0.0,
            "mean_jaccard": sum(pairs) / len(pairs) if pairs else 0.0, "n": len(cores)}


def write_report(path: Path, results: list[dict], costs: Counter, totals: dict, client: str, stage: str,
                 doc_projection: float, spent_before: float, facts: dict, extra: list[str]) -> dict:
    s = summary(results, totals["cost"], totals["gen"], totals["judge"])
    sentences = [x for r in results for x in r["sentences"]]
    for_lead = sum(bank.starts_with_for_entity(x["text"], facts[r["fact_id"]]["entity"])
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
    lines += fact_table(results, costs)
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
        lines += core_and_attribute_sections(results, costs, facts)
        lines += extra
        sample = random.Random(20).sample(sentences, min(20, len(sentences)))
        lines += ["", "## 20 random sentences", ""]
        lines += [f"- {x['frame']} ({x['register']}): {x['text']}" for x in sample]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return s


def core_and_attribute_sections(results: list[dict], costs: Counter, facts: dict) -> list[str]:
    core = {r["fact_id"]: core_stats(r, facts[r["fact_id"]]) for r in results}
    uniq = [c["unique"] for c in core.values()]
    mean_j = [c["mean_jaccard"] for c in core.values()]
    lines = ["", "## Core-clause uniqueness (lead-in and carrier stripped)", "",
             "Core = the span from the first to the last of the entity and the value (both masked), "
             "lower-cased; Jaccard is over the words of two cores.", "",
             f"Share of unique cores per fact: mean {sum(uniq) / len(uniq):.2f}, min {min(uniq):.2f}; "
             f"mean pairwise core Jaccard per fact: mean {sum(mean_j) / len(mean_j):.2f}, "
             f"max {max(mean_j):.2f}.", "",
             "| fact | sentences | unique cores | mean core Jaccard |", "| --- | ---: | ---: | ---: |"]
    lines += [f"| {k} | {c['n']} | {c['unique']:.2f} | {c['mean_jaccard']:.2f} |" for k, c in sorted(core.items())]
    by_attr: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_attr[facts[r["fact_id"]]["attribute_id"]].append(r)
    lines += ["", "## Per-attribute table", "",
              "| attribute | facts | sentences | judge NO rate | refill rate (facts with a refill round) | cost |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for attr, rs in sorted(by_attr.items()):
        judged = sum(r["judged"] for r in rs)
        lines.append(
            f"| {attr} | {len(rs)} | {sum(len(r['sentences']) for r in rs)} | "
            f"{sum(r['judge_no'] for r in rs) / max(1, judged):.1%} | "
            f"{sum(r['refill_rounds'] > 0 for r in rs) / len(rs):.0%} | "
            f"${sum(costs[r['fact_id']] for r in rs):.4f} |")
    lines += ["", "## Yield of the attributes with bank cue groups (before = without the cue check)", "",
              "| attribute | generated | valid after the cue | would be valid without the cue | yield after | yield before |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for attr in TIGHTENED:
        rs = by_attr.get(attr, [])
        gen = sum(r["generated"] for r in rs)
        valid = sum(r["det_valid"] for r in rs)
        only = sum(r.get("cue_only", 0) for r in rs)
        lines.append(f"| {attr} | {gen} | {valid} | {valid + only} | {valid / max(1, gen):.1%} | "
                     f"{(valid + only) / max(1, gen):.1%} |")
    return lines


def backup_sentences(backup: Path, fact_id: str) -> list[dict]:
    return json.loads((backup / f"{fact_id}.json").read_text(encoding="utf-8"))["sentences"]


def write_realized_diversity(path: Path, results: list[dict], facts: dict, mentions: dict) -> None:
    """Per fact: distinct and reused sentences, core-clause uniqueness, mean skeleton Jaccard (covariate)."""
    lines = ["fact_id,attribute_id,mentions,n_distinct,n_reused,core_unique_share,mean_pair_skeleton_jaccard,"
             "mean_pair_core_jaccard,prefixes"]
    for r in results:
        fact = facts[r["fact_id"]]
        core = core_stats(r, fact)
        g = r["gates"]
        m = mentions[r["fact_id"]]
        lines.append(",".join(str(x) for x in (
            r["fact_id"], fact["attribute_id"], m["train"] + m["iid"] + m["novel"], g["n_distinct"], g["n_reused"],
            f"{core['unique']:.4f}", f"{g['mean_pair_jaccard']:.4f}", f"{core['mean_jaccard']:.4f}", g["prefixes"])))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def failing_details(results: list[dict], facts: dict) -> list[str]:
    lines = []
    for r in results:
        if r["gates"]["all"]:
            continue
        g = r["gates"]
        failed = ",".join(k for k in "abcdefg" if not g[k])
        lines += ["", f"### {r['fact_id']} ({facts[r['fact_id']]['attribute_id']}): filled {g['filled']}/{g['need']}, "
                  f"failed gates {failed}", "",
                  f"Top reject reasons: {json.dumps(r['top_reject_reasons'])}",
                  f"Per-frame reject reasons: {json.dumps(r.get('frame_rejects', {}))}",
                  f"Judge NO reasons: {json.dumps(Counter(x['reason'] for x in r['judge_log'] if x['answer'] == 'NO'))}"]
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["mock", "openai"], required=True)
    parser.add_argument("--stage", choices=["pilot", "full"], required=True)
    parser.add_argument("--cap", type=float, default=None, help="spend cap for this stage in USD")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--doc-projection", type=float, default=7.16)
    parser.add_argument("--seed", type=int, default=20261031)
    parser.add_argument("--no-refill-pass", action="store_true")
    parser.add_argument("--only", default="", help="comma list: restrict --refill-short to these facts")
    parser.add_argument("--refill-short", action="store_true",
                        help="P02b7i: refill only the saved facts short on (a), 2 new rounds, new prompts only")
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
    cap = args.cap if args.cap is not None else (0.10 if args.stage == "pilot" else 1.75)
    guard = GlobalBudgetGuard(ROOT / "data", out_dir / "ledger.jsonl", config["budget_usd"], cap, config["models"])
    print(mode_banner(args.client, guard.global_spent(), config["budget_usd"]))
    print(f"stage {args.stage}: cap ${cap:.2f}; spent so far ${guard.global_spent():.4f}")
    backend = bank.MockBankBackend() if mock else OpenAIBackend(load_api_key())
    runner = bank.Runner(backend, MODEL, guard, out_dir / "cache", client=args.client)
    wanted = pilot_facts(needs) if args.stage == "pilot" else sorted(facts)
    facts_dir = out_dir / "facts"
    facts_dir.mkdir(parents=True, exist_ok=True)
    spent_before = guard.global_spent()
    results: dict[str, dict] = {}
    errors: dict[str, str] = {}
    stopped = None

    def build(fact_id: str, save: bool = True) -> bool:
        """Build one fact; a failure is recorded and the run goes on. Returns False on a budget stop."""
        nonlocal stopped
        try:
            result = bank.build_fact(facts[fact_id], needs[fact_id], kb, frames, runner, args.seed)
        except BudgetExceeded as exc:
            stopped = str(exc)
            return False
        except Exception as exc:  # noqa: BLE001 - keep going and report the fact
            errors[fact_id] = f"{type(exc).__name__}: {exc}"
            print(f"{fact_id}: ERROR {errors[fact_id]}")
            return True
        results[fact_id] = result
        if save:
            (facts_dir / f"{fact_id}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        print(f"{fact_id}: need {needs[fact_id]['total']}, gates {'PASS' if result['gates']['all'] else 'FAIL'}, "
              f"cost so far ${sum(runner.usd.values()):.4f}")
        return True

    for fact_id in wanted:
        saved = facts_dir / f"{fact_id}.json"
        if saved.exists():
            results[fact_id] = json.loads(saved.read_text(encoding="utf-8"))
            continue
        if not build(fact_id):
            break

    refill_cost = 0.0
    refilled: list[str] = []
    if args.stage == "full" and stopped is None and not args.no_refill_pass:
        failing = [f for f in wanted if f in errors or not results.get(f, {"gates": {"all": False}})["gates"]["all"]]
        if failing:
            print(f"refill pass for {len(failing)} facts: {', '.join(failing)}")
            before = sum(runner.usd.values())
            bank.REFILL_ROUNDS = REFILL_PASS_ROUNDS
            for fact_id in failing:
                errors.pop(fact_id, None)
                refilled.append(fact_id)
                if not build(fact_id):
                    break
            refill_cost = sum(runner.usd.values()) - before
            print(f"refill pass cost ${refill_cost:.4f}")

    mentions = bank.mention_counts(plan)
    if args.refill_short and args.stage == "full" and stopped is None:
        short = [f for f in wanted if f in results and results[f]["gates"]["filled"] < results[f]["gates"]["need"]
                 and (not args.only or f in args.only.split(","))]
        backup = out_dir / "facts_p02b7h"
        if not backup.exists():
            backup.mkdir()
            for f in wanted:
                (backup / f"{f}.json").write_text((facts_dir / f"{f}.json").read_text(encoding="utf-8"), encoding="utf-8")
        print(f"short-fact refill (2 new rounds, new prompts only) for {len(short)} facts: {', '.join(short)}")
        runner.require_new_gen = True
        before = sum(runner.usd.values())
        for fact_id in short:
            try:
                result = bank.build_fact(facts[fact_id], needs[fact_id], kb, frames, runner, args.seed,
                                         prior=results[fact_id], max_rounds=2)
            except BudgetExceeded as exc:
                stopped = str(exc)
                break
            results[fact_id] = result
            (facts_dir / f"{fact_id}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            g = result["gates"]
            print(f"{fact_id}: filled {g['filled']}/{g['need']} (was {len(backup_sentences(backup, fact_id))}), "
                  f"cost so far ${sum(runner.usd.values()) - before:.4f}")
        refill_cost = sum(runner.usd.values()) - before
        refilled = short
        runner.require_new_gen = False
        print(f"short-fact refill cost ${refill_cost:.4f}; new generation calls {runner.new_gen_calls}")
    if args.stage == "full":  # A2c gates: (d) amended, (a) with controlled reuse inside train
        for fact_id in list(results):
            results[fact_id] = dict(results[fact_id], gates=bank.amended_gates(results[fact_id], mentions[fact_id]))
    ordered = [results[f] for f in wanted if f in results]
    costs = ledger_costs(out_dir / "ledger.jsonl")
    totals = {"cost": sum(costs.values()) if not mock else sum(runner.usd.values()),
              "gen": runner.usd["gen"], "judge": runner.usd["judge"]}
    still_failing = [f for f in wanted if f in errors or f not in results or not results[f]["gates"]["all"]]
    reused = [(r["fact_id"], r["gates"]["need"] - r["gates"]["n_distinct"], r["gates"]["n_reused"])
              for r in ordered if r["gates"].get("n_reused")]
    extra = ["", "## G2 summary (amended A2c)", "",
             f"Facts using controlled reuse in train: {len(reused)}; reused mentions in total: "
             f"{sum(n for _f, _s, n in reused)}. " + "; ".join(
                 f"{f}: shortfall {sf}, reused {n}" for f, sf, n in reused),
             "",
             f"Facts meeting A2 (a)-(g) as amended: {len(wanted) - len(still_failing)}/{len(wanted)}; "
             f"facts that went through the refill pass: {len(refilled)} ({', '.join(refilled) or 'none'}); "
             f"refill pass cost ${refill_cost:.4f}; errors: {errors or 'none'}"]
    if still_failing:
        extra += ["", "## Facts still failing after the refill pass"] + failing_details(
            [results[f] for f in still_failing if f in results], facts)
    stage_dir = ROOT / "reports" / "tables" / ("mock" if mock else "")
    report = args.report or stage_dir / ("bank_pilot.md" if args.stage == "pilot" else "bank_report.md")
    s = write_report(report, ordered, costs, totals, args.client, args.stage, args.doc_projection,
                     spent_before, facts, extra)
    if args.stage == "full" and stopped is None and not still_failing:
        rows = bank.write_bank_files(out_dir, ordered)
        write_realized_diversity(out_dir / "realized_diversity.csv", ordered, facts, mentions)
        by_fact: dict[str, list[dict]] = {r["fact_id"]: r["sentences"] for r in ordered}
        allocation = bank.allocate(plan, by_fact, args.seed)
        problems = bank.check_allocation(plan, [dict(r, reserved=r["reserved"]) for r in rows], allocation)
        (out_dir / "allocation.jsonl").write_text(
            "".join(json.dumps(a) + "\n" for a in allocation), encoding="utf-8")
        print(f"allocation: {len(allocation)} mentions; problems: {problems or 'none'}")
        if problems:
            return 5
    all_ok = not still_failing and len(ordered) == len(wanted)
    judge_ok = s["judge_no_rate"] <= 0.10
    gate = "G1" if args.stage == "pilot" else "G2"
    verdict = all_ok and (judge_ok if args.stage == "pilot" else True) and stopped is None
    print(f"GATE {gate}: {'PASS' if verdict else 'FAIL'} ({s['facts_all_gates']}/{len(wanted)} facts meet A2; "
          f"judge NO rate {s['judge_no_rate']:.1%}); stage cost ${s['cost']:.4f}"
          + (f"; stopped: {stopped}" if stopped else "")
          + (f"; still failing: {', '.join(still_failing)}" if still_failing else ""))
    return 0 if verdict else 3


if __name__ == "__main__":
    raise SystemExit(main())
