"""Simulated-data validation of the analysis: recovery, null false positives, power.

    python scripts/validate_analysis.py [--null-reps 500] [--power-reps 300]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.analysis.simulate import SimParams  # noqa: E402
from slm.analysis.validate import build_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--null-reps", type=int, default=500)
    ap.add_argument("--power-reps", type=int, default=300)
    ap.add_argument("--out", default=str(ROOT / "reports" / "tables" / "analysis_validation.md"))
    args = ap.parse_args(argv)
    text = build_report(SimParams(), n_null=args.null_reps, n_power=args.power_reps)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
