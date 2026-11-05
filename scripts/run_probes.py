"""Run the cloze probe harness over checkpoints and write the long-format table.

Real run:  python scripts/run_probes.py --scorer my_pkg.my_mod:make_scorer \
               --checkpoints runs/s0/ckpt_100 runs/s0/ckpt_200 --seeds 0 1 2
The factory is called as ``make_scorer(checkpoint: str, seed: int) -> Scorer``.

Mock run:  python scripts/run_probes.py --mock --out reports/tables/probes_mock.csv
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.eval.mock import oracle_scorer, random_ground_truth  # noqa: E402
from slm.eval.probes import (  # noqa: E402
    assert_no_leakage,
    build_probes,
    load_facts,
    load_meanings,
    run_many,
    write_table,
)


def load_factory(spec: str):
    module, _, attr = spec.partition(":")
    if not attr:
        raise SystemExit("--scorer must look like 'package.module:factory'")
    return getattr(importlib.import_module(module), attr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--scorer", help="module:factory returning a Scorer for (checkpoint, seed)")
    ap.add_argument("--checkpoints", nargs="+", default=[], help="checkpoint ids or paths")
    ap.add_argument("--seeds", nargs="+", type=int, default=[0])
    ap.add_argument("--mock", action="store_true", help="use oracle MockScorers, no model needed")
    ap.add_argument("--splits", nargs="+", default=["val", "test"], choices=["val", "test"])
    ap.add_argument("--probe-seed", type=int, default=0, help="fixes the val/test template split")
    ap.add_argument("--kb", default=str(ROOT / "data/kb/kb.json"))
    ap.add_argument("--cues", default=str(ROOT / "configs/attribute_cues.yaml"))
    ap.add_argument("--out", default=str(ROOT / "reports/tables/probes.csv"))
    args = ap.parse_args(argv)

    if not args.mock and not args.scorer:
        ap.error("give --scorer module:factory, or --mock")
    checkpoints = args.checkpoints or (["mock-0", "mock-1"] if args.mock else [])
    if not checkpoints:
        ap.error("give --checkpoints")

    probes = build_probes(
        load_facts(args.kb), load_meanings(args.cues), seed=args.probe_seed, splits=args.splits
    )
    assert_no_leakage(probes)

    runs = []
    factory = None if args.mock else load_factory(args.scorer)
    for ci, ckpt in enumerate(checkpoints):
        for seed in args.seeds:
            if args.mock:
                prior, bind = random_ground_truth(probes, seed=1000 * seed + ci)
                scorer = oracle_scorer(probes, prior, bind, noise=0.1, seed=seed)
            else:
                scorer = factory(ckpt, seed)
            runs.append((ckpt, seed, scorer))

    df = run_many(runs, probes)
    path = write_table(df, args.out)
    print(f"{len(df)} rows -> {path}; stored rate {df['stored'].mean():.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
