"""Offline checks of configs/openers_v2.yaml (P02c2, no API): counts, validator checks over sampled
openers, and the simulated opening-5-gram duplicate share over the 2407 plan rows.
Writes reports/tables/openers_v2_report.md. Exit code 1 if any check fails.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from slm.data import openers_v2
from slm.data.doc_validator import capital_flags, meta_language_reasons, validate_doc
from slm.data.doc_validator_v1 import META_WORDS
from slm.data.doc_validator_v2 import NUMBER_WORDS

ROOT = Path(__file__).resolve().parents[1]
MAX_DUP = 0.03
SAMPLE = 20000
FULL_VALIDATOR_SAMPLE = 600
MIN_FRAME_GRAMS = 500
RESAMPLES = 20
SOFT_RULES = {"V8", "V10", "V11", "V13", "V14"}  # length and document-level structure, not opener-level


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=SAMPLE)
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "tables" / "openers_v2_report.md")
    args = parser.parse_args(argv)
    kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
    pools = json.loads((ROOT / "data" / "kb" / "filler_pools.json").read_text(encoding="utf-8"))
    plan = [json.loads(x) for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()]
    values = [f["value"].lower() for f in kb["measured_facts"]]
    entities = sorted({f["entity"].lower() for f in kb["measured_facts"]})
    types = sorted(openers_v2.load()["types"])
    row_of = {t: next(r for r in plan if r["doc_type"] == t) for t in types}
    problems: list[str] = []
    lines = ["# Openers v2 (prompt v7) offline checks", ""]

    lines += ["## Table: frames, possible openings, simulated duplicates", "",
              "| doc type | frames | distinct openings possible | distinct 5-grams possible (min per frame) | plan docs | simulated duplicate share (mean of "
              f"{RESAMPLES} resamples / worst) | assigned share |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    by_type = defaultdict(list)
    for r in plan:
        by_type[r["doc_type"]].append(r)
    totals = []
    for t in types:
        rows = by_type[t]
        shares = []
        for k in range(RESAMPLES):
            grams = [openers_v2.first_words(openers_v2.opener(t, f"sim{k}-{r['doc_id']}")) for r in rows]
            shares.append(1 - len(set(grams)) / len(grams))
        assigned = [openers_v2.first_words(openers_v2.opener_for_row(r)) for r in rows]
        a_share = 1 - len(set(assigned)) / len(assigned)
        per_frame = [len(openers_v2.frame_five_grams(f)) for f in openers_v2.frames(t)]
        possible, grams5 = openers_v2.possible_openings(t), len(openers_v2.distinct_five_grams(t))
        if min(per_frame) < MIN_FRAME_GRAMS:
            problems.append(f"{t}: a frame has only {min(per_frame)} distinct 5-grams (< {MIN_FRAME_GRAMS})")
        mean, worst = sum(shares) / len(shares), max(shares)
        lines.append(f"| {t} | {len(openers_v2.frames(t))} | {possible} | {grams5} ({min(per_frame)}) | {len(rows)} | {mean:.2%} / {worst:.2%} | {a_share:.2%} |")
        if possible < 5000 or grams5 < 5000:
            problems.append(f"{t}: fewer than 5000 possible openings/5-grams")
        if len(openers_v2.frames(t)) < 12:
            problems.append(f"{t}: fewer than 12 frames")
        if mean > MAX_DUP or a_share > MAX_DUP:
            problems.append(f"{t}: simulated duplicate share above {MAX_DUP:.0%}")
        totals.append(t)
    overall = []
    for k in range(RESAMPLES):
        grams = [openers_v2.first_words(openers_v2.opener(r["doc_type"], f"sim{k}-{r['doc_id']}")) for r in plan]
        overall.append(1 - len(set(grams)) / len(grams))
    assigned = [openers_v2.first_words(openers_v2.opener_for_row(r)) for r in plan]
    a_overall = 1 - len(set(assigned)) / len(assigned)
    lines += ["", f"Overall over all {len(plan)} plan rows: assigned {a_overall:.2%}; resamples mean {sum(overall) / len(overall):.2%}, "
              f"worst {max(overall):.2%} (limit {MAX_DUP:.0%}; Gate A limit 5% on the finished text)."]
    if a_overall > MAX_DUP or max(overall) > MAX_DUP:
        problems.append("overall simulated duplicate share above 3%")

    # validator checks
    lines += ["", f"## Checks over {args.sample} sampled openers per type (V1/V3/V4/V5/V7/V18, zero flagged required)", "",
              "| doc type | sampled | digits | KB value | KB entity | spelled number | capitals (V5) | meta words (V7) | V18 | full validator rules (non-length) |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for t in types:
        row = row_of[t]
        flagged = Counter()
        for i in range(args.sample):
            text = openers_v2.plain(openers_v2.opener(t, f"check-{t}-{i}"))
            low = text.lower()
            flagged["digits"] += bool(re.search(r"\d", text))
            flagged["value"] += any(v in low for v in values)
            flagged["entity"] += any(re.search(rf"(?<!\w){re.escape(e)}(?!\w)", low) for e in entities)
            flagged["number"] += bool(NUMBER_WORDS.search(text))
            flagged["capitals"] += bool(capital_flags(text, row, kb, pools))
            flagged["meta"] += bool(META_WORDS.search(text)) or bool(re.search(r"#|\*\*|`", text))
            flagged["v18"] += bool(meta_language_reasons(text, row, kb))
        rules = Counter()
        for i in range(FULL_VALIDATOR_SAMPLE):
            text = openers_v2.plain(openers_v2.opener(t, f"full-{t}-{i}"))
            _ok, reasons = validate_doc(text, {**row, "fact_ids": [], "modes": []}, kb, pools)
            for rule in {re.match(r"V\d+[bp]?(?:/V\d+)?", x).group(0) if re.match(r"V\d+", x) else x[:20] for x in reasons}:
                rules[rule] += 1
        hard = {k: v for k, v in rules.items() if k not in SOFT_RULES}
        lines.append(f"| {t} | {args.sample} | {flagged['digits']} | {flagged['value']} | {flagged['entity']} | {flagged['number']} | "
                     f"{flagged['capitals']} | {flagged['meta']} | {flagged['v18']} | {dict(sorted(hard.items())) or 'none'} |")
        for key, n in flagged.items():
            if n:
                problems.append(f"{t}: {n} openers flagged by {key}")
        if hard:
            problems.append(f"{t}: validator rules {hard}")
    lines += ["", f"Validator v5 was run in full on {FULL_VALIDATOR_SAMPLE} openers per type; length and document-level structure rules "
              f"({', '.join(sorted(SOFT_RULES))}) are expected to fire on a bare opening and are excluded."]

    # example openers
    lines += ["", "## Example openers", ""]
    for t in types:
        lines.append(f"- {t}: " + " // ".join(openers_v2.plain(openers_v2.opener(t, f"example-{i}")).replace("\n", " / ") for i in range(3)))
    lines += ["", f"Result: {'PASS' if not problems else 'FAIL ' + str(problems)}"]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
