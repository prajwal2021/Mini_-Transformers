"""20 fact-sentence neighbourhoods (sentence before, inserted sentence, sentence after) from random
mention-bearing documents of the corpus. Writes reports/tables/fact_neighbourhoods.md."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from slm.data.bank import BankStore
from slm.data.doc_validator import sentence_list

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=ROOT / "data" / "corpus")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--seed", type=int, default=2025)
    parser.add_argument("--out", type=Path, default=ROOT / "reports" / "tables" / "fact_neighbourhoods.md")
    args = parser.parse_args(argv)
    kb = json.loads((ROOT / "data" / "kb" / "kb.json").read_text(encoding="utf-8"))
    plan = {r["doc_id"]: r for r in (json.loads(x) for x in
            (ROOT / "data" / "plan" / "plan.jsonl").read_text(encoding="utf-8").splitlines())}
    docs = [json.loads(x) for s in ("train", "val", "test")
            for x in (args.corpus_dir / f"{s}.jsonl").read_text(encoding="utf-8").splitlines()]
    bearing = [d for d in docs if d["fact_ids"]]
    store = BankStore.load()
    rng = random.Random(args.seed)
    lines = ["# Fact-sentence neighbourhoods", "",
             f"{args.count} random mention-bearing documents (seed {args.seed}); one random fact per document.", ""]
    for d in rng.sample(bearing, min(args.count, len(bearing))):
        fact = rng.choice(d["fact_ids"])
        inserted = store.inserted(plan[d["doc_id"]], kb)[fact]["text"]
        sentences = sentence_list(d["text"])
        index = next((i for i, s in enumerate(sentences) if inserted in s or s in inserted), None)
        lines.append(f"## {d['doc_id']} ({d['doc_type']}), {fact}")
        if index is None:
            lines += ["(inserted sentence not found as a sentence)", ""]
            continue
        before = sentences[index - 1] if index > 0 else "(start of document)"
        after = sentences[index + 1] if index + 1 < len(sentences) else "(end of document)"
        lines += [f"- before: {before}", f"- inserted: {sentences[index]}", f"- after: {after}", ""]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
