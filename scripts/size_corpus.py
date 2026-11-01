"""Calculate P01b train-only exposure and corpus sizing scenarios."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "experiment.yaml"
KB_PATH = ROOT / "data" / "kb" / "kb.json"
REPORT_PATH = ROOT / "reports" / "tables" / "sizing.md"


def load_config() -> dict[str, Any]:
    """Load sizing inputs from YAML."""
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def calculate(config: dict[str, Any], measured_facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the complete k-by-background grid."""
    planned_mentions = sum(int(fact["planned_mentions"]) for fact in measured_facts)
    assert planned_mentions == 2600, f"planned mentions must equal 2600, found {planned_mentions}"
    rows: list[dict[str, Any]] = []
    avg_tokens = int(config["avg_tokens_per_doc"])
    for k in config["measured_facts_per_doc"]:
        for background_fraction in config["background_doc_fractions"]:
            mention_bearing = math.ceil(planned_mentions / int(k))
            train_docs = math.ceil(mention_bearing / (1.0 - float(background_fraction)))
            total_docs = math.ceil(train_docs / 0.90)
            val_docs = total_docs - train_docs
            test_docs = round(total_docs * float(config["test_doc_fraction"]))
            train_tokens = train_docs * avg_tokens
            val_tokens = val_docs * avg_tokens
            test_tokens = test_docs * avg_tokens
            prompt_tokens = total_docs * int(config["prompt_tokens_per_call"])
            completion_tokens = total_docs * int(config["completion_tokens_per_call"])
            input_price = config.get("price_input_usd_per_million")
            output_price = config.get("price_output_usd_per_million")
            if input_price is None or output_price is None:
                estimated_cost = None
                pricing = "UNKNOWN (pricing unset)"
            else:
                estimated_cost = (prompt_tokens / 1_000_000) * float(input_price)
                estimated_cost += (completion_tokens / 1_000_000) * float(output_price)
                pricing = f"${estimated_cost:.2f}"
            flags: list[str] = []
            if train_tokens < 500_000:
                flags.append("below minimum viable")
            if int(k) > 3:
                flags.append("k > 3")
            if float(background_fraction) > 0.6:
                flags.append("background fraction > 0.6")
            if estimated_cost is None:
                flags.append("cost unknown")
            elif estimated_cost > float(config["budget_usd"]):
                flags.append("cost above cap")
            assert mention_bearing * int(k) >= planned_mentions
            rows.append({
                "k": int(k),
                "background_fraction": float(background_fraction),
                "mention_bearing_train_docs": mention_bearing,
                "train_docs": train_docs,
                "total_docs": total_docs,
                "val_docs": val_docs,
                "test_docs": test_docs,
                "train_tokens": train_tokens,
                "val_tokens": val_tokens,
                "test_tokens": test_tokens,
                "api_calls": total_docs,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "pricing": pricing,
                "estimated_cost": estimated_cost,
                "mention_density": planned_mentions / mention_bearing,
                "flags": ", ".join(flags) or "none",
            })
    return rows


def write_report(rows: list[dict[str, Any]], config: dict[str, Any]) -> None:
    """Write a report with formulas and the full scenario grid."""
    lines = [
        "# Corpus sizing",
        "",
        "Exposure is counted in TRAIN documents only.",
        "",
        "- `mention_bearing_train_docs = ceil(2600 / k)`",
        "- `train_docs = ceil(mention_bearing_train_docs / (1 - b))`",
        "- `total_docs = ceil(train_docs / 0.90)`",
        "- `train_tokens = train_docs * avg_tokens` with `avg_tokens = 350`",
        "- Budget: `$10` hard cap (D-013); pricing is **VERIFY PRICING BEFORE USE**.",
        "",
        "| k | b | mention-bearing train docs | train docs | val docs | test docs | total docs | train tokens | val tokens | test tokens | API calls | prompt tokens | completion tokens | pricing | mention density | flags |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['k']} | {row['background_fraction']:.2f} | {row['mention_bearing_train_docs']} | "
            f"{row['train_docs']} | {row['val_docs']} | {row['test_docs']} | {row['total_docs']} | "
            f"{row['train_tokens']:,} | {row['val_tokens']:,} | {row['test_tokens']:,} | {row['api_calls']} | "
            f"{row['prompt_tokens']:,} | {row['completion_tokens']:,} | {row['pricing']} | "
            f"{row['mention_density']:.2f} | {row['flags']} |"
        )
        lines.append(
            f"  Reconciliation: `{row['mention_bearing_train_docs']} * {row['k']} >= 2600` PASS"
        )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    config = load_config()
    with KB_PATH.open(encoding="utf-8") as handle:
        kb = json.load(handle)
    rows = calculate(config, kb["measured_facts"])
    write_report(rows, config)
    print(f"PASS: sizing calculated for {len(rows)} scenarios; planned mentions=2600")


if __name__ == "__main__":
    main()
