"""P02c5 analysis: meta-talk scan (step 1) and 13-gram leak breakdown (step 2). Read-only, no API."""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from slm.data import corpus
from slm.data.metatalk import PATTERNS, scan

ROOT = Path(__file__).resolve().parents[1]
docs = [json.loads(x) for s in ("train", "val", "test")
        for x in (ROOT / "data/corpus" / f"{s}.jsonl").read_text(encoding="utf-8").splitlines()]
by_id = {d["doc_id"]: d for d in docs}
out = []
hits = defaultdict(list)
for d in docs:
    for name, ctx in scan(d["text"]):
        hits[name].append((d["doc_id"], ctx))
out.append("## Meta-talk hits per pattern")
for name, _rx in PATTERNS:
    rows = hits.get(name, [])
    out.append(f"- {name!r}: {len(rows)} hits in {len({r[0] for r in rows})} docs")
    for doc_id, ctx in rows[:3]:
        out.append(f"    - {doc_id}: ...{ctx}...")
out.append(f"Docs with any hit: {len({r[0] for v in hits.values() for r in v})}")

# leak breakdown
train = defaultdict(set)
for d in docs:
    if d["split"] == "train":
        for g in corpus.grams13(d["text"]):
            train[g].add(d["doc_id"])
shared = Counter()
src = defaultdict(set)
where = defaultdict(set)
for d in docs:
    if d["split"] != "train":
        for g in corpus.grams13(d["text"]):
            if g in train:
                shared[g] += 1
                src[g].add(d["doc_type"])
                where[g].add(d["doc_id"])
out.append("")
out.append(f"## Distinct shared 13-grams: {len(shared)}; total occurrences {sum(shared.values())}")
for g, n in shared.most_common(15):
    out.append(f"- x{n} types={sorted(src[g])} train_docs={len(train[g])}: {' '.join(g)}")
Path(ROOT / "reports/tables/p02c5_scan.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))

rng = random.Random(5370)
by_type = defaultdict(list)
for d in docs:
    by_type[d["doc_type"]].append(d)
pick = [rng.choice(v) for _t, v in sorted(by_type.items())]
rest = [d for d in docs if d not in pick]
pick += rng.sample(rest, 20 - len(pick))
Path(ROOT / "reports/tables/p02c5_read20.md").write_text(
    "\n".join(f"## {d['doc_id']} ({d['doc_type']})\n\n{d['text']}\n" for d in pick), encoding="utf-8")
print("read20:", [d["doc_id"] for d in pick])
_ = re
