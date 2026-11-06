"""P02c4: 8 sample documents (2 newsletters) and 15 fact-sentence neighbourhoods from documents generated
after the resume (positions 351+ in the hashed order). Writes reports/tables/p02c4_samples.md."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from slm.data.bank import BankStore
from slm.data.doc_validator import sentence_list

ROOT = Path(__file__).resolve().parents[1]
kb = json.loads((ROOT / "data/kb/kb.json").read_text(encoding="utf-8"))
plan = [json.loads(x) for x in (ROOT / "data/plan/plan.jsonl").read_text(encoding="utf-8").splitlines()]
by_id = {r["doc_id"]: r for r in plan}
order = sorted(plan, key=lambda r: hashlib.sha256(("p02c" + r["doc_id"]).encode()).hexdigest())
late = {r["doc_id"] for r in order[350:]}
docs = [json.loads(x) for s in ("train", "val", "test") for x in (ROOT / f"data/corpus/{s}.jsonl").read_text(encoding="utf-8").splitlines()]
docs = [d for d in docs if d["doc_id"] in late]
rng = random.Random(2026)
news = [d for d in docs if d["doc_type"] == "newsletter blurb"]
others = [d for d in docs if d["doc_type"] != "newsletter blurb"]
picks = rng.sample(news, 2) + rng.sample(others, 6)
out = ["# P02c4 samples (documents generated after the resume)", ""]
for d in picks:
    out += [f"## {d['doc_id']} ({d['doc_type']}, {d['mode']})", "", "```text", d["text"], "```", ""]
out += ["# 15 fact-sentence neighbourhoods", ""]
store = BankStore.load()
bearing = [d for d in docs if d["fact_ids"]]
for d in rng.sample(bearing, 15):
    fact = rng.choice(d["fact_ids"])
    inserted = store.inserted(by_id[d["doc_id"]], kb)[fact]["text"]
    sents = sentence_list(d["text"])
    i = next((k for k, s in enumerate(sents) if inserted in s or s in inserted), None)
    out.append(f"## {d['doc_id']} ({d['doc_type']}), {fact}")
    if i is None:
        out += ["(inserted sentence not found as a sentence)", ""]
        continue
    out += [f"- before: {sents[i - 1] if i else '(start)'}", f"- inserted: {sents[i]}",
            f"- after: {sents[i + 1] if i + 1 < len(sents) else '(end)'}", ""]
(ROOT / "reports/tables/p02c4_samples.md").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
