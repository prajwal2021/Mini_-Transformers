# ruff: noqa: E501
"""R07: write the report appendix that keeps the ORIGINAL (pre-correction) H1/H2 numbers visible beside the corrected ones.

    python scripts/make_report_appendix.py --original reports/integration/real_R06/results --corrected runs/real/results \
        --original-secondary reports/integration/real_R06/results_secondary --corrected-secondary runs/real/results_secondary \
        --out runs/real/report_inputs/appendix_correction.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

STAR = "E\\*"  # the report markup writes E* with a backslash


def row(f: pd.DataFrame, h: str) -> pd.Series:
    return f.set_index("hypothesis").loc[h]


def fmt(r: pd.Series) -> str:
    return f"{r['estimate']:+.3f} ({r['ci_low']:+.3f}, {r['ci_high']:+.3f}), Holm p {r['p_holm']:.2g}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--original", required=True)
    ap.add_argument("--corrected", required=True)
    ap.add_argument("--original-secondary", default=None)
    ap.add_argument("--corrected-secondary", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    o = pd.read_csv(Path(a.original) / "tables" / "analysis_family.csv")
    c = pd.read_csv(Path(a.corrected) / "tables" / "analysis_family.csv")
    lines = [
        "## Appendix: post-unblinding correction of H1 and H2",
        "",
        "After the results were seen, an audit found a coding bug: the probe outcome `stored` was a boolean column, and the formula interface "
        "then modelled the probability of NOT stored, so every logistic coefficient (H1, H2 and the sensitivity re-fits) had the wrong sign. "
        "The fix coerces the outcome to 0/1. It was validated on synthetic data with planted positive and negative effects "
        "(`tests/test_r07_sign.py`), not on these outcomes. The originally reported numbers are kept here; only the sign of each H1 and H2 "
        f"estimate changed (CIs mirror, p-values are identical). The hypotheses, model, margins and {STAR} were not changed. "
        "H3 and H4 do not use this model.",
        "",
        "| hypothesis | original (bugged, sign inverted) | corrected |",
        "|---|---|---|",
    ]
    for h in ("H1", "H2"):
        lines.append(f"| {h} (primary, {STAR}) | {fmt(row(o, h))} | {fmt(row(c, h))} |")
    if a.original_secondary and a.corrected_secondary:
        os_ = pd.read_csv(Path(a.original_secondary) / "tables" / "analysis_family.csv")
        cs = pd.read_csv(Path(a.corrected_secondary) / "tables" / "analysis_family.csv")
        for h in ("H1", "H2"):
            lines.append(f"| {h} (secondary, epoch 60) | {fmt(row(os_, h))} | {fmt(row(cs, h))} |")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
