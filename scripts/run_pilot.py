"""Paid-pilot CLI. Real API calls happen only with --client openai and the spend flag."""

from __future__ import annotations

import argparse
from pathlib import Path

from slm.data.pilot import MockBackend, OpenAIBackend, load_api_key, run_pilot

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["mock", "openai"], required=True)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--i-understand-this-spends-money", action="store_true")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="allow replacing reports written by the other client",
    )
    args = parser.parse_args(argv)
    if args.client == "openai" and not args.i_understand_this_spends_money:
        raise SystemExit("Refusing to call the OpenAI API without --i-understand-this-spends-money")
    if args.n != 30:
        print("Warning: type/category coverage is only guaranteed for --n 30.")
    if args.client == "mock":
        backend = MockBackend(models=args.models)
        out_dir = ROOT / "data" / "pilot_mock"
        reports = ROOT / "reports" / "tables" / "mock"
        notes = out_dir / "API_NOTES.md"
    else:
        backend = OpenAIBackend(load_api_key())
        out_dir = ROOT / "data" / "pilot"
        reports = ROOT / "reports" / "tables"
        notes = ROOT / "journal" / "API_NOTES.md"
    return run_pilot(
        backend,
        args.models,
        args.n,
        out_dir,
        ROOT / "data",
        reports,
        notes,
        args.client,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    raise SystemExit(main())
