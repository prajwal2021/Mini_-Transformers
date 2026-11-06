# ruff: noqa: E501
"""Build data/sft/{sft_train,sft_val}.jsonl and data/eval/qa_test.jsonl from the KB's own sft_split.

    python scripts/build_sft_data.py [--kb data/kb/kb.json] [--sft-dir data/sft] [--eval-dir data/eval]

Writes only; the QA test file is not read here. Prints the counts table and 10 example Q/A pairs
per evaluation set, and fails when any split assertion fails (slm.sft.build.verify_datasets).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from slm.sft.build import read_jsonl, write_real_datasets

ROOT = Path(__file__).resolve().parents[1]


def examples(rows: list[dict], k: int = 10) -> list[dict]:
    step = max(1, len(rows) // k)
    return rows[::step][:k]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kb", default=str(ROOT / "data" / "kb" / "kb.json"))
    ap.add_argument("--sft-dir", default=str(ROOT / "data" / "sft"))
    ap.add_argument("--eval-dir", default=str(ROOT / "data" / "eval"))
    args = ap.parse_args(argv)
    m = write_real_datasets(args.kb, args.sft_dir, args.eval_dir)
    print("split assertions:")
    for k, ok in m["checks"].items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {k}")
    print("\nfacts per cell (sft_train / sft_val / heldout):")
    for cell, c in sorted(m["cell_counts"].items()):
        print(f"  {cell:<20}{c['sft_train']:>3}{c['sft_val']:>4}{c['heldout']:>5}")
    print("\nrows:", json.dumps(m["rows"]))
    qa = read_jsonl(Path(args.eval_dir) / "qa_test.jsonl")
    for sub in ("E0", "E1", "E2"):
        print(f"\n{sub} examples:")
        for r in examples([x for x in qa if x["subset"] == sub]):
            print(f"  [{r['fact_id']} {r['freq_bin']}/{r['div_bin']}] Q: {r['question']}\n      A: {r['answer']}")
    print("\nsha256:")
    for k, v in m["files"].items():
        print(f"  {v}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
