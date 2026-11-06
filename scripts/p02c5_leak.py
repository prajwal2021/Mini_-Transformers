"""P02c5 step 2: classify the 13-grams shared by val/test docs with train (read-only, no API).

Classes per distinct shared gram:
 (i)   entirely inside a sign-off line (the last line of the document when it is the desk name, optionally
       preceded by a person name) -> exempt from the leak rule by decision (none expected: sign-offs are
       model-written lines of at most 8 words, shorter than a 13-gram);
 (i-b) overlaps a sign-off line but extends into the preceding sentence (reported, NOT exempt);
 (ii)  repeated generic phrase: occurs in >= 3 train documents and does not overlap an inserted bank sentence;
 (iii) other.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from slm.data.leakclass import analyse, exempt_docs

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    docs = [json.loads(x) for s in ("train", "val", "test")
            for x in (ROOT / "data/corpus" / f"{s}.jsonl").read_text(encoding="utf-8").splitlines()]
    plan = {r["doc_id"]: r for r in (json.loads(x) for x in (ROOT / "data/plan/plan.jsonl").read_text(encoding="utf-8").splitlines())}
    kb = json.loads((ROOT / "data/kb/kb.json").read_text(encoding="utf-8"))
    info = analyse(docs, plan, kb)
    classes = Counter(r["class"] for r in info.values())
    occ = Counter()
    for r in info.values():
        occ[r["class"]] += r["n"]
    lines = ["# Leak breakdown (P02c5)", "",
             f"Distinct shared 13-grams {len(info)}, occurrences {sum(r['n'] for r in info.values())}, "
             f"docs {len({d for r in info.values() for d in r['docs']})}.", "",
             "| class | distinct grams | occurrences |", "| --- | ---: | ---: |"]
    for c in ("i", "i-b", "ii", "iii"):
        lines.append(f"| {c} | {classes[c]} | {occ[c]} |")
    lines += ["", "Top 15 by frequency:", "", "| n | class | doc types | train docs | gram |", "| ---: | --- | --- | ---: | --- |"]
    for g, r in sorted(info.items(), key=lambda kv: (-kv[1]["n"], kv[0]))[:15]:
        lines.append(f"| {r['n']} | {r['class']} | {', '.join(sorted(r['types']))} | {r['train_docs']} | {' '.join(g)} |")
    leaking = {d for r in info.values() for d in r["docs"]}
    after = exempt_docs(info)
    lines += ["", f"Leaking val/test docs without exemption: {len(leaking)}; with the sign-off exemption: {len(after)}."]
    (ROOT / "reports/tables/p02c5_leak_breakdown.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
