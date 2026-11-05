"""P02b7h report-back helper: bank diversity numbers (d) and the sentence samples (e) as markdown."""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from slm.data import bank

ROOT = Path(__file__).resolve().parents[1]
TIGHTENED = {"species_max_combined_weight", "species_min_age_weeks", "compensation_claim_window_days",
             "skyport_quarantine_room_capacity", "airship_onboard_handler_name"}


def load(bank_dir: Path) -> tuple[list[dict], dict]:
    kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    results = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((bank_dir / "facts").glob("F*.json"))]
    return results, facts


def diversity(results: list[dict], facts: dict) -> list[str]:
    sentences = [(r["fact_id"], x) for r in results for x in r["sentences"]]
    mean_j = [r["gates"]["mean_pair_jaccard"] for r in results]
    cores = []
    for r in results:
        texts = [bank.core_clause(x["text"], facts[r["fact_id"]]["entity"], facts[r["fact_id"]]["value"])
                 for x in r["sentences"]]
        cores.append(len(set(texts)) / len(texts) if texts else 0.0)
    for_lead = sum(bank.starts_with_for_entity(x["text"], facts[f]["entity"]) for f, x in sentences)
    frames, registers = Counter(x["frame"] for _f, x in sentences), Counter(x["register"] for _f, x in sentences)
    return [
        f"- Sentences: {len(sentences)} over {len(results)} facts.",
        f"- Mean pairwise skeleton Jaccard per fact: mean {sum(mean_j) / len(mean_j):.3f}, max {max(mean_j):.3f}.",
        f"- Core-clause uniqueness per fact (share of unique cores): mean {sum(cores) / len(cores):.3f}, min {min(cores):.3f}.",
        f"- Share starting 'For <entity>,': {for_lead / len(sentences):.2%}.",
        "- Frame distribution: " + ", ".join(f"{k} {v}" for k, v in sorted(frames.items())),
        "- Register distribution: " + ", ".join(f"{k} {v}" for k, v in sorted(registers.items())),
    ]


def samples(results: list[dict], facts: dict, seed: int = 40) -> list[str]:
    rng = random.Random(seed)
    by_attr: dict[str, list[tuple[str, dict]]] = {}
    for r in results:
        for x in r["sentences"]:
            by_attr.setdefault(facts[r["fact_id"]]["attribute_id"], []).append((r["fact_id"], x))
    lines = ["fact_id | attribute | frame id | canonical sentence | candidate"]
    for attr in sorted(by_attr):
        k = 6 if attr in TIGHTENED else 2
        for fact_id, x in rng.sample(by_attr[attr], min(k, len(by_attr[attr]))):
            lines.append(f"{fact_id} | {attr} | {x['frame']} | {facts[fact_id]['canonical_sentence']} | {x['text']}")
    return lines


def main() -> int:
    results, facts = load(ROOT / "data" / "bank")
    print("\n".join(diversity(results, facts)))
    print()
    print("\n".join(samples(results, facts)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
