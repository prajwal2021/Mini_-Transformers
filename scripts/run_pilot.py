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
    parser.add_argument("--prompt-version", choices=["v2", "v3"], default="v2")
    parser.add_argument("--validator-version", choices=["v1", "v2"], default="v2")
    parser.add_argument("--suffix", default="", help="report file suffix, e.g. _v3")
    parser.add_argument("--out-name", default=None, help="folder under data/ for real outputs")
    parser.add_argument("--rows-from", type=Path, default=None,
                        help="pilot_rows.jsonl whose doc ids are reused")
    parser.add_argument("--use-saved-api-config", action="store_true",
                        help="use api_config.json from scripts/preflight.py, skip the probe")
    parser.add_argument("--session-cap", type=float, default=None)
    parser.add_argument("--extended", action="store_true", help="extra v3 report sections")
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
        out_dir = ROOT / "data" / (args.out_name or "pilot")
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
        suffix=args.suffix,
        rows_from=args.rows_from,
        prompt_version=args.prompt_version,
        validator_version=args.validator_version,
        use_saved_api_config=args.use_saved_api_config,
        extra_pilot_ledgers=(
            [ROOT / "data" / "pilot" / "ledger.jsonl"] if out_dir.name != "pilot" else None
        ),
        session_cap=args.session_cap,
        extended=args.extended,
    )


if __name__ == "__main__":
    raise SystemExit(main())
