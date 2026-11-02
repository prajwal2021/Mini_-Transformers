"""Command-line entry point for guarded corpus generation."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import yaml

from .budget import GlobalBudgetGuard, mode_banner
from .generator import MockClient, OpenAIClient, generate_rows

ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", choices=["mock", "openai"], required=True)
    parser.add_argument("--model", default="gpt-5.4-nano")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--split", choices=["train", "val", "test"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--i-understand-this-spends-money", action="store_true")
    args = parser.parse_args()
    config = yaml.safe_load((ROOT / "configs" / "generation.yaml").read_text(encoding="utf-8"))
    spent = GlobalBudgetGuard(
        ROOT / "data", ROOT / "data" / "raw" / "ledger.jsonl", config["budget_usd"],
        config["budget_usd"], config["models"],
    ).global_spent()
    print(mode_banner(args.client, spent, config["budget_usd"]))
    if args.client == "openai" and not args.i_understand_this_spends_money:
        raise SystemExit("Refusing OpenAI client without --i-understand-this-spends-money")
    rows = [
        json.loads(line)
        for line in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.split:
        rows = [row for row in rows if row["split"] == args.split]
    if args.dry_run:
        print(f"dry-run: {len(rows[: args.limit])} rows, client={args.client}, model={args.model}")
        return 0
    client = MockClient() if args.client == "mock" else OpenAIClient(args.model)
    result = asyncio.run(generate_rows(rows, client, args.model, args.limit))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
