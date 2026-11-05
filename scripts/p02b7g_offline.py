"""P02b7g offline analysis: attribute-cue audit and replay of cached candidates under the new rules.

Prints (and writes to reports/tables/bank_p02b7g_offline.md) the cue audit for the 20 attributes, how
many cached candidates of F001/F017/F008 the near-duplicate rule removes (0.9 and 0.8), and what
F008 and F017 could give under the new deterministic rules from the old-frame candidates in the cache.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import yaml

from slm.data import bank

ROOT = Path(__file__).resolve().parents[1]
REWORKED = {"f01", "f02", "f04", "f10", "f11", "f12", "f19"}

# reviewer-style flags: could a descriptive-quantity paraphrase pass without the attribute's meaning?
FLAGS = {
    "skyport_daily_pet_cap": "FLAG (fixed in bank): 'takes N a day' passed; bank_cue_groups now require a capacity cue",
    "skyport_lounge_opening_time": "weak: 'start' alone passes ('lounge staff start at 6')",
    "skyport_quarantine_room_capacity": "FLAG: 'kennel' alone passes ('the room has 12 kennels')",
    "airship_cabin_temp_setting": "weak: 'degrees' alone passes ('the cabin is 20 degrees today')",
    "airship_pet_deck_name": "FLAG: only 'deck' is required; no pet or travel cue",
    "airship_onboard_handler_name": "FLAG: 'aboard' or 'onboard' alone passes ('Maro Kest is aboard')",
    "species_max_combined_weight": "FLAG: 'weigh' or 'total' passes without a maximum ('the cat weighs 11 kg')",
    "species_min_age_weeks": "FLAG: 'old' or 'age' passes without a minimum ('the cat is 8 weeks old')",
    "procedure_deadline_hours": "weak: 'before' alone passes",
    "compensation_claim_window_days": "FLAG: 'claim' alone passes ('the claim takes 107 days')",
}


def audit() -> list[str]:
    cues = yaml.safe_load((ROOT / "configs" / "attribute_cues.yaml").read_text(encoding="utf-8"))
    lines = ["| # | attribute | cue_groups | bank_cue_groups | drift risk |", "| ---: | --- | --- | --- | --- |"]
    for i, (attr, spec) in enumerate(cues.items(), start=1):
        groups = " AND ".join("[" + ", ".join(g) + "]" for g in spec["cue_groups"])
        bank_groups = " AND ".join("[" + ", ".join(g) + "]" for g in spec.get("bank_cue_groups", [])) or "-"
        lines.append(f"| {i} | {attr} | {groups} | {bank_groups} | {FLAGS.get(attr, 'ok')} |")
    return lines


def cached_candidates(cache: Path, facts: dict) -> dict[str, list[tuple[str, str]]]:
    """(frame, sentence) per fact in cache order, from every cached generation output."""
    out: dict[str, list[tuple[str, str]]] = {k: [] for k in facts}
    files = sorted(cache.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for path in files:
        text = json.loads(path.read_text(encoding="utf-8"))["text"]
        for frame, sentence in bank.parse_candidates(text):
            for fact_id, fact in facts.items():
                if fact["value"] in sentence and fact["entity"] in sentence:
                    out[fact_id].append((frame, sentence))
    return out


def replay(fact: dict, items: list[tuple[str, str]], kb: dict, threshold: float, skip_reworked: bool) -> dict:
    canonical = bank.content_words(fact["canonical_sentence"])
    seen: set[str] = set()
    kept: list[frozenset] = []
    stats: Counter[str] = Counter()
    by_frame: Counter[str] = Counter()
    for frame, sentence in items:
        if skip_reworked and frame in REWORKED:
            continue
        stats["unique_input"] += 0
        norm = " ".join(bank._tokens(sentence))
        if norm in seen:
            stats["exact_duplicate"] += 1
            continue
        seen.add(norm)
        stats["unique"] += 1
        reasons = bank.check_candidate(sentence, fact, kb, canonical)
        if reasons:
            stats["rejected_by_checks"] += 1
            if "lacks the capacity-style cue for this attribute" in reasons:
                stats["rejected_by_cue"] += 1
            continue
        gram = bank.grams(bank.skeleton(sentence, fact["entity"], fact["value"]))
        if any(bank.jaccard(gram, g) >= threshold for g in kept):
            stats["near_duplicate"] += 1
            continue
        kept.append(gram)
        stats["survivors"] += 1
        by_frame[frame] += 1
    stats["by_frame"] = dict(sorted(by_frame.items()))  # type: ignore[assignment]
    return dict(stats)


def main() -> int:
    kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
    facts = {f["fact_id"]: f for f in kb["measured_facts"]}
    watch = {k: facts[k] for k in ("F001", "F017", "F008")}
    cands = cached_candidates(ROOT / "data" / "bank_pilot3" / "cache", watch)
    out = ["# P02b7g offline analysis", "", "## Attribute cue audit (20 attributes)", ""] + audit()
    out += ["", "## Cached candidates: near-duplicate removal (all cached frames)", "",
            "| fact | cached lines | unique | det-valid kept at 0.9 | removed at 0.9 | kept at 0.8 | removed at 0.8 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for fact_id, fact in watch.items():
        r9 = replay(fact, cands[fact_id], kb, 0.9, False)
        r8 = replay(fact, cands[fact_id], kb, 0.8, False)
        out.append(f"| {fact_id} | {len(cands[fact_id])} | {r8.get('unique', 0)} | {r9.get('survivors', 0)} | "
                   f"{r9.get('near_duplicate', 0)} | {r8.get('survivors', 0)} | {r8.get('near_duplicate', 0)} |")
    out += ["", "## What F008 and F017 would give under the new deterministic rules (old frames only)", "",
            "Frames f01, f02, f04, f10, f11, f12 and f19 are excluded (reworded; the cache holds only the old wording). "
            "Survivors are an upper bound on the fill: the judge has not run on them.", "",
            "| fact | need | unique | rejected by checks | of which capacity cue | near-dup (0.8) | survivors |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    plan = [json.loads(x) for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()]
    needs = bank.needs_from_plan(plan)
    for fact_id in ("F008", "F017"):
        r = replay(watch[fact_id], cands[fact_id], kb, bank.NEAR_DUPLICATE, True)
        need = needs[fact_id]["plain"] + needs[fact_id]["novel"]
        out.append(f"| {fact_id} | {need} | {r.get('unique', 0)} | {r.get('rejected_by_checks', 0)} | "
                   f"{r.get('rejected_by_cue', 0)} | {r.get('near_duplicate', 0)} | {r.get('survivors', 0)} |")
        out.append(f"|  | survivors by frame: {r['by_frame']} | | | | | |")
    text = "\n".join(out) + "\n"
    (ROOT / "reports" / "tables" / "bank_p02b7g_offline.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
