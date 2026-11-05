"""Build the project report from the analysis outputs.

    python scripts/build_report.py --simulate                 # simulated build, always bannered
    python scripts/build_report.py --real --results-dir reports --inputs-dir <run inputs>

The SIMULATED banner is on in every page and figure unless --real is given. --simulate and
--real cannot be combined. The build fails if the PDF is outside the page range (5-7 pages).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.report.build import build  # noqa: E402
from slm.report.pdf import PageCountError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--simulate", action="store_true", help="generate simulated inputs and build")
    ap.add_argument("--real", action="store_true", help="turn the SIMULATED banner off")
    ap.add_argument("--results-dir", default=str(ROOT / "reports"),
                    help="analysis outputs (tables/, figures/)")
    ap.add_argument("--inputs-dir", default=None,
                    help="dir with run_facts.json, loss_curves.csv, samples.csv")
    ap.add_argument("--out", default=None, help="default: docs/report[/simulated]")
    ap.add_argument("--backend", default="auto", choices=("auto", "chrome", "matplotlib"))
    ap.add_argument("--min-pages", type=int, default=5)
    ap.add_argument("--max-pages", type=int, default=7)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--banner-label", default=None, choices=("SIMULATED", "MOCK"),
                    help="banner text (default SIMULATED; the mock pipeline uses MOCK)")
    args = ap.parse_args(argv)
    simulate = args.simulate or not (args.real or args.inputs_dir)
    out = Path(args.out) if args.out else ROOT / "docs" / "report" / (
        "simulated" if simulate else ""
    )
    try:
        res = build(
            out, simulate=simulate, real=args.real,
            results_dir=None if simulate else Path(args.results_dir),
            inputs_dir=None if simulate else Path(args.inputs_dir) if args.inputs_dir else None,
            backend=args.backend, min_pages=args.min_pages, max_pages=args.max_pages,
            seed=args.seed, banner_label=args.banner_label,
        )
    except PageCountError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return 2
    print(f"backend: {res.backend}; pages: {res.pages}; banner: {res.banner}; pdf: {res.pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
