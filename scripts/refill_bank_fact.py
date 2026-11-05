"""P02b7f: rebuild one bank-pilot fact with the duplicate-aware refill and recompute its A2 row.

Judge calls and earlier generations are served from the run-3 cache; only new prompts cost money
(own ledger, own cap). Also reports offline how many cached candidates of other facts the new
pre-judge near-duplicate rule would have removed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from slm.data import bank
from slm.data.budget import GlobalBudgetGuard, mode_banner
from slm.data.pilot import OpenAIBackend, load_api_key

ROOT = Path(__file__).resolve().parents[1]
MODEL = "gpt-5.4-mini"


def near_duplicate_audit(src: Path, fact_ids: list[str], facts: dict, kb: dict) -> dict[str, dict]:
    """Replay each cached fact build offline; count candidates the new rule removes before judging."""
    out = {}
    for fact_id in fact_ids:
        data = json.loads((src / "facts_v3" / f"{fact_id}.json").read_text(encoding="utf-8"))
        fact = facts[fact_id]
        kept: list[frozenset] = []
        removed = 0
        texts = [x["text"] for x in data["judge_log"]]
        for text in texts:
            gram = bank.grams(bank.skeleton(text, fact["entity"], fact["value"]))
            if any(bank.jaccard(gram, g) >= bank.NEAR_DUPLICATE for g in kept):
                removed += 1
            else:
                kept.append(gram)
        out[fact_id] = {"judged": len(texts), "near_duplicates": removed,
                        "exact_duplicates_rejected_before_judge": data["top_reject_reasons"].get("duplicate", 0)}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["mock", "openai"], required=True)
    parser.add_argument("--fact", default="F008")
    parser.add_argument("--src-dir", type=Path, default=ROOT / "data" / "bank_pilot3")
    parser.add_argument("--cap", type=float, default=0.04)
    parser.add_argument("--i-understand-this-spends-money", action="store_true")
    args = parser.parse_args(argv)
    if args.client == "openai" and not args.i_understand_this_spends_money:
        raise SystemExit("Refusing to call the OpenAI API without --i-understand-this-spends-money")
    config = yaml.safe_load((ROOT / "configs" / "generation.yaml").read_text(encoding="utf-8"))
    kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
    plan = [json.loads(x) for x in (ROOT / "data/plan/plan.jsonl").read_text(encoding="utf-8").splitlines()]
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    needs = bank.needs_from_plan(plan)
    audit = near_duplicate_audit(args.src_dir, ["F001", "F017", "F008"], facts, kb)
    backend = bank.MockBankBackend() if args.client == "mock" else OpenAIBackend(load_api_key())
    guard = GlobalBudgetGuard(ROOT / "data", args.src_dir / "ledger_refill_p02b7f.jsonl",
                              config["budget_usd"], args.cap, config["models"])
    print(mode_banner(args.client, guard.global_spent(), config["budget_usd"]))
    runner = bank.Runner(backend, MODEL, guard, args.src_dir / "cache", client=args.client)
    result = bank.build_fact(facts[args.fact], needs[args.fact], kb, bank.load_frames(), runner, 20261031)
    spent = sum(runner.usd.values())
    (args.src_dir / "facts_v3" / f"{args.fact}.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8")
    g = result["gates"]
    print(json.dumps({"gates": g, "generated": result["generated"], "det_valid": result["det_valid"],
                      "judged": result["judged"], "judge_no": result["judge_no"],
                      "refill_rounds": result["refill_rounds"], "rejects": result["top_reject_reasons"],
                      "frame_counts": result["frame_counts"], "spent": round(spent, 4),
                      "calls": dict(runner.calls), "audit": audit}, indent=1))
    return 0 if g["all"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
