"""Post-generation audit of the corpus (P02c): exposure, 2+2 val/test, bank sharing, sizes, validator
regression, 13-gram leakage, near-duplicates and exact duplicates. Writes reports/tables/corpus_audit.md,
data/corpus/exposure.csv and (with --manifest) data/corpus/manifest.json. Exit code 1 if a hard check fails.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from slm.data import corpus, openers_v2
from slm.data.artifacts import artifact_by_type, artifact_rate
from slm.data.versions import validator_for

ROOT = Path(__file__).resolve().parents[1]


def load_split(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=ROOT / "data" / "corpus")
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "tables" / "corpus_audit.md")
    parser.add_argument("--bank-dir", type=Path, default=ROOT / "data" / "bank")
    parser.add_argument("--manifest", action="store_true")
    args = parser.parse_args(argv)
    kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
    pools = json.loads((ROOT / "data" / "kb" / "filler_pools.json").read_text(encoding="utf-8"))
    plan = [json.loads(x) for x in (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines()]
    plan_by_id = {r["doc_id"]: r for r in plan}
    docs = [d for s in ("train", "val", "test") for d in load_split(args.corpus_dir / f"{s}.jsonl")]
    problems: list[str] = []
    lines = ["# Corpus audit", ""]

    # (d) counts, words, estimated tokens
    lines += ["## (d) Documents, words and estimated tokens (words x 1.35)", "",
              "| split | docs planned | docs in corpus | words | est. tokens | mean words/doc |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for split in ("train", "val", "test"):
        planned = sum(r["split"] == split for r in plan)
        sub = [d for d in docs if d["split"] == split]
        words = sum(len(corpus.tokens(d["text"])) for d in sub)
        lines.append(f"| {split} | {planned} | {len(sub)} | {words} | {round(words * 1.35)} | {words / max(1, len(sub)):.1f} |")
    total_words = sum(len(corpus.tokens(d["text"])) for d in docs)
    lines.append(f"| all | {len(plan)} | {len(docs)} | {total_words} | {round(total_words * 1.35)} | {total_words / max(1, len(docs)):.1f} |")
    types = sorted({d["doc_type"] for d in docs})
    lines += ["", "| doc type | train | val | test |", "| --- | ---: | ---: | ---: |"]
    for t in types:
        lines.append(f"| {t} | " + " | ".join(str(sum(d["doc_type"] == t and d["split"] == s for d in docs)) for s in ("train", "val", "test")) + " |")
    modes = Counter((d["split"], d["mode"]) for d in docs)
    lines += ["", "Documents by split and mode: " + ", ".join(f"{s}/{m} {n}" for (s, m), n in sorted(modes.items()))]

    # (h) opening 5-grams on the final corpus (P02c2): duplicate share per type and split, top openings
    def opening(doc: dict) -> tuple[str, ...]:
        return tuple(corpus.tokens(doc["text"])[:5])

    def dup_share(sub: list[dict]) -> float:
        grams = [opening(d) for d in sub]
        return 1 - len(set(grams)) / len(grams) if grams else 0.0

    lines += ["", "## (h) Opening-5-gram duplicate share on the final corpus (Gate A metric)", "",
              f"Overall {dup_share(docs):.2%} over {len(docs)} documents (limit 5%).", "",
              "| group | docs | duplicate share |", "| --- | ---: | ---: |"]
    for t in types:
        sub = [d for d in docs if d["doc_type"] == t]
        lines.append(f"| type: {t} | {len(sub)} | {dup_share(sub):.2%} |")
    for split in ("train", "val", "test"):
        sub = [d for d in docs if d["split"] == split]
        lines.append(f"| split: {split} | {len(sub)} | {dup_share(sub):.2%} |")
    top = Counter(opening(d) for d in docs).most_common(10)
    lines += ["", "Ten most common openings (first five words): " + "; ".join(f"'{' '.join(g)}' x{n}" for g, n in top)]
    followed = sum(
        opening(d) in {openers_v2.first_words(openers_v2.opener(d["doc_type"], d["doc_id"], r)) for r in range(3)}
        for d in docs)
    lines.append(f"Documents whose first five words equal the assigned opener of round 0, 1 or 2: {followed} of {len(docs)} "
                 f"({followed / max(1, len(docs)):.1%}; informational, not a gate).")

    # (i) artifact rate and marker placements (P02c3)
    by_type_art = artifact_by_type(docs)
    rate, bad_docs, bearing_docs = artifact_rate(docs)
    lines += ["", "## (i) Artifact rate and marker placements on the final corpus", "",
              f"Artifact rate (detector in slm/data/artifacts.py) {rate:.2%} = {bad_docs} of {bearing_docs} mention-bearing "
              "documents (gate limit 2%).", "", "| doc type | mention-bearing docs | with artifact | rate |", "| --- | ---: | ---: | ---: |"]
    for t, (nbad, n) in by_type_art.items():
        lines.append(f"| {t} | {n} | {nbad} | {nbad / n:.1%} |")
    records_file = args.corpus_dir / "raw" / "records.jsonl"
    type_of = {d["doc_id"]: d["doc_type"] for d in docs}
    place = Counter()
    if records_file.exists():
        for line in records_file.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec["doc_id"] not in type_of:
                continue
            final = [a for a in rec["attempts"] if a["ok"]]
            for fact_place in (final[-1]["placements"].values() if final else []):
                place[(type_of[rec["doc_id"]], fact_place["placement"])] += 1
        lines += ["", "Placement counts per mention in the accepted attempt:", "",
                  "| doc type | model | repaired_missing | repaired_mid_v2 | repaired_dup |", "| --- | ---: | ---: | ---: | ---: |"]
        for t in types:
            lines.append(f"| {t} | " + " | ".join(str(place[(t, p)]) for p in ("model", "repaired_missing", "repaired_mid_v2", "repaired_dup")) + " |")
        total = Counter()
        for (_t, p), n in place.items():
            total[p] += n
        lines.append(f"\nAll types: {dict(total)}.")

    # (a) exposure
    planned_t, planned_p = Counter(), Counter()
    meas_t, meas_p = Counter(), Counter()
    for row in plan:
        if row["split"] == "train":
            for f, m in zip(row["fact_ids"], row["modes"]):
                (planned_t if m == "templated" else planned_p)[f] += 1
    for d in docs:
        if d["split"] == "train":
            row = plan_by_id[d["doc_id"]]
            for f, m in zip(row["fact_ids"], row["modes"]):
                (meas_t if m == "templated" else meas_p)[f] += 1
    fact_ids = sorted({f["fact_id"] for f in kb["measured_facts"]})
    with (args.corpus_dir / "exposure.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["fact_id", "planned", "measured_templated", "measured_paraphrased"])
        for f in fact_ids:
            writer.writerow([f, planned_t[f] + planned_p[f], meas_t[f], meas_p[f]])
    diff = [f for f in fact_ids if (meas_t[f], meas_p[f]) != (planned_t[f], planned_p[f])]
    lines += ["", "## (a) Train exposure: planned vs measured mentions per fact (data/corpus/exposure.csv)", "",
              f"Planned train mentions {sum(planned_t.values()) + sum(planned_p.values())} "
              f"(templated {sum(planned_t.values())}, paraphrased {sum(planned_p.values())}); measured "
              f"{sum(meas_t.values()) + sum(meas_p.values())} (templated {sum(meas_t.values())}, paraphrased {sum(meas_p.values())}). "
              f"Facts with measured != planned: {len(diff)} of {len(fact_ids)}."]
    if diff:
        lines += ["", "| fact | planned T/P | measured T/P |", "| --- | --- | --- |"]
        lines += [f"| {f} | {planned_t[f]}/{planned_p[f]} | {meas_t[f]}/{meas_p[f]} |" for f in diff]
    unaccepted_path = args.corpus_dir / "unaccepted.json"
    unaccepted = json.loads(unaccepted_path.read_text(encoding="utf-8")) if unaccepted_path.exists() else []
    dropped_path = args.corpus_dir / "dropped.json"
    dropped = json.loads(dropped_path.read_text(encoding="utf-8")) if dropped_path.exists() else []
    lines += ["", f"Train documents unaccepted after re-planning: {len(unaccepted)} {unaccepted}. "
              f"Dropped as near-duplicates: {len(dropped)} {[x['doc_id'] for x in dropped]}."]

    # (b) 2+2 in val and test
    per = defaultdict(Counter)
    for d in docs:
        if d["split"] in ("val", "test"):
            row = plan_by_id[d["doc_id"]]
            for f, m in zip(row["fact_ids"], row["modes"]):
                if m == "paraphrased":
                    per[f][d["split"]] += 1
    bad = [f for f in fact_ids if per[f]["val"] != 2 or per[f]["test"] != 2]
    lines += ["", "## (b) Val/test paraphrased mentions per fact (must be exactly 2 + 2)", "",
              f"Facts with exactly 2 val and 2 test paraphrased mentions: {len(fact_ids) - len(bad)} of {len(fact_ids)}."
              + (f" Violations: {[(f, per[f]['val'], per[f]['test']) for f in bad]}" if bad else "")]
    problems += [f"val/test mentions of {f}" for f in bad]

    # (c) bank sentences across splits
    allocation = [json.loads(x) for x in (args.bank_dir / "allocation.jsonl").read_text(encoding="utf-8").splitlines()]
    split_of_doc = {d["doc_id"]: d["split"] for d in docs}
    seen: dict[str, set[str]] = defaultdict(set)
    for a in allocation:
        if a["sentence_id"] != "canonical" and a["doc_id"] in split_of_doc:
            seen[a["sentence_id"]].add(split_of_doc[a["doc_id"]])
    shared = [s for s, v in seen.items() if len(v) > 1]
    lines += ["", "## (c) Bank sentences in more than one split", "", f"{len(shared)} (must be 0): {shared[:10]}"]
    problems += [f"bank sentence {s} in two splits" for s in shared]

    # (e) validator regression
    validate = validator_for("v5")
    failures = []
    for d in docs:
        ok, reasons = validate(d["text"], plan_by_id[d["doc_id"]], kb, pools)
        if not ok:
            failures.append((d["doc_id"], reasons[:2]))
    lines += ["", "## (e) Validator v5 regression over the final texts", "", f"{len(failures)} failures of {len(docs)} (must be 0). {failures[:5]}"]
    problems += [f"validator failure {x[0]}" for x in failures]

    # (f) leakage, near-duplicates; (g) exact duplicates
    leaky = corpus.leakage(docs)
    near = corpus.train_near_duplicates(docs)
    lines += ["", "## (f) 13-gram leakage (after validator normalisation)", "",
              f"Val/test documents sharing at least one 13-gram with train: {len(leaky)} (total shared {sum(leaky.values())}); must be 0. {leaky}",
              f"Train near-duplicate pairs (13-gram Jaccard > 0.5): {len(near)}. {near[:5]}"]
    problems += [f"leak {d}" for d in leaky]
    problems += [f"near-duplicate {a}/{b}" for a, b, _j in near]
    dup = corpus.exact_duplicates(docs)
    lines += ["", "## (g) Exact duplicate documents across all splits", "", f"{len(dup)} (must be 0): {dup[:5]}"]
    problems += [f"exact duplicate {x}" for x in dup]

    # records (cost, attempts)
    records_path = args.corpus_dir / "raw" / "records.jsonl"
    if records_path.exists():
        records = [json.loads(x) for x in records_path.read_text(encoding="utf-8").splitlines()]
        cost = sum(r["cost"] for r in records)
        attempts = Counter(len([a for a in r["attempts"]]) for r in records)
        lines += ["", "## Cost and attempts (raw records)", "",
                  f"Cost of all attempts ${cost:.4f}; attempts per document (all rounds): {dict(sorted(attempts.items()))}; "
                  f"mean {sum(k * v for k, v in attempts.items()) / max(1, len(records)):.3f}."]
    lines += ["", f"Result: {'PASS' if not problems else 'FAIL (' + str(len(problems)) + ' problems)'}"]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if args.manifest:
        corpus.write_manifest(args.corpus_dir)
    print("\n".join(lines[:60]))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
