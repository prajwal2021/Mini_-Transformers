"""Write every pre-registered sensitivity analysis to reports/tables/sensitivity.md (+ .csv).

    python scripts/run_sensitivity.py --input <probe> [--qa-input <qa>] \
        [--realized-diversity <realized_diversity.csv>] --out reports/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.analysis.pipeline import _read  # noqa: E402
from slm.analysis.schema import normalize_qa_table  # noqa: E402
from slm.analysis.sensitivity import run_sensitivity, sensitivity_markdown  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="probe table (.csv or .parquet)")
    ap.add_argument("--qa-input", default=None, help="SFT QA table")
    ap.add_argument("--realized-diversity", default=None, help="realized_diversity.csv")
    ap.add_argument("--out", default="reports")
    ap.add_argument("--checkpoint", default="final")
    args = ap.parse_args(argv)
    ck = args.checkpoint if args.checkpoint == "final" else int(args.checkpoint)
    qa = normalize_qa_table(_read(args.qa_input)) if args.qa_input else None
    realized = pd.read_csv(args.realized_diversity) if args.realized_diversity else None
    table, extras = run_sensitivity(_read(args.input), qa, realized, ck)
    out = Path(args.out) / "tables"
    out.mkdir(parents=True, exist_ok=True)
    (out / "sensitivity.md").write_text(sensitivity_markdown(table, extras), encoding="utf-8")
    table.to_csv(out / "sensitivity.csv", index=False, float_format="%.6g")
    print(out / "sensitivity.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
