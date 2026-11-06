# ruff: noqa: E501
"""Samples from every saved checkpoint of one seed (and `init`), with flags and a selection (R01 4).

    python scripts/sample_checkpoints.py --pretrain-root runs/real/pretrain --tokenizer runs/real/tokenizer.json \
        [--out reports/tables/samples.csv] [--seed 0] [--label REAL|MOCK]

Per checkpoint: 10 fixed prompts (5 canonical prefixes across the freq x div cells, 3 novel
phrasings, 2 off-domain), greedy + temperature 0.8 (3 seeded samples). On the final checkpoint:
a temperature sweep (0, 0.4, 0.8, 1.2, 0.8 + top-k 40) over 20 prompts. Flags follow the taxonomy
rules (docs/ERROR_TAXONOMY.md): value_correct, wrong_value, hallucinated, gibberish (off-domain
prompts: gibberish or off_domain_ok). Writes <out>, <out stem>_selected.csv (6 successes + 6
failures spread over checkpoints) and <out stem>.md. --label MOCK puts a MOCK banner on the
Markdown and in the data_status column. The prompts are canonical prefixes and novel wordings of
KB facts, so a real run records the use in the test-access ledger (--ledger).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from slm.integration import samples as S
from slm.tokenizer import BPETokenizer

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--pretrain-root", required=True, help="folder holding seed<k>/checkpoints/epoch_*.pt")
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--kb", default=str(ROOT / "data" / "kb" / "kb.json"))
    ap.add_argument("--out", default=str(ROOT / "reports" / "tables" / "samples.csv"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--label", choices=("REAL", "MOCK"), default="REAL")
    ap.add_argument("--n-each", type=int, default=6)
    ap.add_argument("--max-new-tokens", type=int, default=32)
    ap.add_argument("--ledger", default=None, help="test-access ledger to record this use in (real runs)")
    args = ap.parse_args(argv)

    from slm.integration.tables import load_kb

    kb = load_kb(args.kb)
    if args.ledger:
        import hashlib

        from slm.guard import record_test_use

        record_test_use("R01 checkpoint samples: canonical prefixes and novel wordings of KB facts", log_path=args.ledger,
                        files=[{"path": args.kb, "sha256": hashlib.sha256(Path(args.kb).read_bytes()).hexdigest()}],
                        caller="scripts/sample_checkpoints.py")
    df = S.run_samples(args.pretrain_root, BPETokenizer.load(args.tokenizer), kb, seed=args.seed,
                       data_status=args.label, max_new_tokens=args.max_new_tokens)
    selected = S.select_samples(df, args.n_each, args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8")
    selected.to_csv(out.with_name(out.stem + "_selected.csv"), index=False, encoding="utf-8")
    md = S.to_markdown(df, selected, args.n_each, args.label)
    out.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
