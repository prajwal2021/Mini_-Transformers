# ruff: noqa: E501
"""Manifest for a PARTIAL corpus dry run (R02): copies data/corpus/{train,val}.jsonl, never the test file.

    python scripts/partial_manifest.py [--corpus data/corpus] [--out runs/partial_dryrun/data]

Writes <out>/train.jsonl, <out>/val.jsonl and <out>/splits.json (docs/SPLIT_MANIFEST.md, version 1).
test.jsonl is neither opened nor listed, so the test-access guard has nothing to log.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from slm.split_manifest import build_manifest

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=str(ROOT / "data" / "corpus"))
    ap.add_argument("--out", default=str(ROOT / "runs" / "partial_dryrun" / "data"))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    for split in ("train", "val"):
        shutil.copyfile(Path(args.corpus) / f"{split}.jsonl", out / f"{split}.jsonl")
        files[out / f"{split}.jsonl"] = split
    build_manifest(files, out / "splits.json")
    print(f"manifest: {out / 'splits.json'} (train, val only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
