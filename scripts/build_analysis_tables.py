# ruff: noqa: E501
"""Join the evaluation outputs into the analysis inputs (docs/INTERFACES.md sections 2-4).

    python scripts/build_analysis_tables.py --probe reports/tables/probes.csv \
        --qa runs/qa_predictions.csv --kb data/kb/kb.json --out-dir reports/analysis_inputs \
        --plan data/plan/plan.jsonl --realized-diversity data/bank/realized_diversity.csv \
        [--manifest data/corpus/manifest.json | --exposure exposure.csv] [--fact-split fact_split.json]

Writes probe.csv (probe table + train_mentions, entity_freq, value_len), qa.csv (the SFT-outcome
table) and realized_diversity.csv, plus tables_summary.json (probe counts per fact, exposure
source). Exposure comes from, in order: --exposure (a CSV), --manifest (string-match counts over
the train files of the split manifest), --plan (planned train mentions; labelled "planned").
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from slm.integration import tables as T

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--probe", required=True, help="probe table (CSV/parquet) from the probe harness")
    ap.add_argument("--qa", required=True, help="evaluator predictions (CSV), all seeds and variants")
    ap.add_argument("--kb", default=str(ROOT / "data/kb/kb.json"))
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--plan", default=None, help="corpus plan (jsonl); planned-exposure fallback")
    ap.add_argument("--manifest", default=None, help="split manifest of the corpus (train counts)")
    ap.add_argument("--exposure", default=None, help="exposure CSV: fact_id, train_mentions, ...")
    ap.add_argument("--realized-diversity", default=None)
    ap.add_argument("--fact-split", default=None,
                    help="JSON fact_id -> sft_train|sft_val|heldout (default: the KB's sft_split)")
    ap.add_argument("--tokenizer", default=None, help="tokenizer.json for value_len in tokens")
    ap.add_argument("--max-step", type=int, default=None,
                    help="keep probe rows up to this optimiser step (and init): makes it every seed's final checkpoint")
    args = ap.parse_args(argv)

    kb = T.load_kb(args.kb)
    probe = (pd.read_parquet(args.probe) if args.probe.endswith(".parquet")
             else pd.read_csv(args.probe))
    qa = pd.read_csv(args.qa)
    if args.max_step is not None:
        ck = probe["checkpoint"].astype(str)
        probe = probe[(ck == "init") | (pd.to_numeric(ck, errors="coerce") <= args.max_step)]

    tok = None
    if args.tokenizer:
        from slm.tokenizer import BPETokenizer

        tok = BPETokenizer.load(args.tokenizer)
    if args.exposure:
        exposure = T.read_exposure(args.exposure)
        source = "file"
    elif args.manifest:
        from slm.split_manifest import SplitManifest
        from slm.tokenizer import read_split

        exposure = T.exposure_from_corpus(kb, read_split(SplitManifest.load(args.manifest), "train"),
                                          tok)
        source = "measured"
    elif args.plan:
        exposure = T.exposure_from_plan(kb, T.load_plan(args.plan))
        source = "planned"
    else:
        exposure, source = None, "none"

    realized = pd.read_csv(args.realized_diversity) if args.realized_diversity else None
    fact_split = (json.loads(Path(args.fact_split).read_text(encoding="utf-8"))
                  if args.fact_split else None)
    paths = T.build_analysis_tables(probe, qa, kb, args.out_dir, exposure=exposure,
                                    realized=realized, fact_split=fact_split)

    counts = T.probe_counts(probe)
    per_fact = {f"{s}/{fr}": int(counts[(s, fr)].iloc[0]) for s, fr in counts.columns}
    summary = {
        "exposure_source": source,
        "probes_per_fact": per_fact,
        "n_facts": int(probe["fact_id"].nunique()),
        "n_seeds": int(probe["seed"].nunique()),
        "checkpoints": sorted(map(str, probe["checkpoint"].unique())),
        "qa_rows": int(len(pd.read_csv(paths["qa"]))),
    }
    (Path(args.out_dir) / "tables_summary.json").write_text(json.dumps(summary, indent=2),
                                                           encoding="utf-8")
    for name, path in paths.items():
        print(f"{name}: {path}")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
