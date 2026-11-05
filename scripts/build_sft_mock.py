"""Build the SFT fact split and QA datasets into data/sft_mock/ (never data/ proper)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.sft.build import (  # noqa: E402
    SPLIT_NAMES,
    build_fact_split,
    load_sft_facts,
    split_table,
    write_datasets,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kb", default=str(ROOT / "data/kb/kb.json"))
    ap.add_argument("--out", default=str(ROOT / "data/sft_mock"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--split-source", choices=["kb", "seeded"], default="kb",
        help="kb: reuse the sft_split recorded in kb.json; seeded: build a new stratified split",
    )
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    if not out.name.endswith("_mock"):
        raise SystemExit("refusing to write to a directory not named *_mock")

    facts = load_sft_facts(args.kb)
    if args.split_source == "kb":
        split = {f.fact_id: f.kb_split for f in facts}
    else:
        split = build_fact_split(facts, args.seed)
    manifest = write_datasets(facts, split, out, seed=args.seed, source=args.split_source)
    table = split_table(facts, split)
    print("freq_bin div_bin " + " ".join(SPLIT_NAMES))
    for (fb, db) in sorted({(a, b) for a, b, _ in table}):
        print(fb, db, *[table.get((fb, db, s), 0) for s in SPLIT_NAMES])
    print(json.dumps(manifest["rows"]), manifest["sha256"]["qa_test.jsonl"][:12])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
