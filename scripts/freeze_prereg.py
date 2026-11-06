# ruff: noqa: E501
"""Freeze the preregistration: record its hash and the git commit, refuse after any test read.

    python scripts/freeze_prereg.py [--prereg docs/PREREG.md] [--run-dir runs/real] \
        [--ledger reports/test_access_log.jsonl] [--verify]

Refuses (exit 1) when a test-split probe row, a QA test prediction file or a test-access ledger
entry already exists. ``--verify`` only checks an earlier freeze. Writes <run-dir>/freeze.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from slm.integration.freeze import FreezeRefused, freeze, verify

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--prereg", default=str(ROOT / "docs" / "PREREG.md"))
    ap.add_argument("--run-dir", default=str(ROOT / "runs" / "real"))
    ap.add_argument("--ledger", default=str(ROOT / "reports" / "test_access_log.jsonl"))
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args(argv)
    try:
        rec = verify(Path(args.prereg)) if args.verify else freeze(
            Path(args.prereg), Path(args.run_dir), Path(args.ledger), ROOT)
    except FreezeRefused as exc:
        print(f"FREEZE REFUSED: {exc}", file=sys.stderr)
        return 1
    if not args.verify:
        out = Path(args.run_dir) / "freeze.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rec, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: rec[k] for k in ("prereg_sha256", "frozen_at")} | {"commit": rec["git"]["commit"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
