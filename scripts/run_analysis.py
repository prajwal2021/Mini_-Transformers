"""Run the full pre-registered analysis (H1-H4) on a probe table and an optional QA table.

    python scripts/run_analysis.py --input <probe.csv|parquet> [--qa-input <qa.csv>] --out reports/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.analysis.pipeline import run_analysis  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="long-format probe table (.csv or .parquet)")
    ap.add_argument("--qa-input", default=None, help="SFT QA table (H3, H4); optional")
    ap.add_argument("--out", default="reports", help="output root (tables/ and figures/)")
    ap.add_argument("--checkpoint", default="final", help='primary checkpoint step or "final"')
    ap.add_argument("--no-mixed", action="store_true", help="skip the mixed-model sensitivity fit")
    ap.add_argument("--real", action="store_true",
                    help="inputs are real results: turn the SIMULATED banner off (default: on)")
    args = ap.parse_args(argv)
    ck = args.checkpoint if args.checkpoint == "final" else int(args.checkpoint)
    written = run_analysis(
        args.input, args.out, ck, qa_path=args.qa_input, mixed_sensitivity=not args.no_mixed,
        real=args.real,
    )
    for name, path in written.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
