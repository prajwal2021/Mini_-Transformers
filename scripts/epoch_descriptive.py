# ruff: noqa: E501
"""R06: descriptive stored rate by freq x div at init, epoch 12 (validation-loss-optimal), E*=30 and epoch 60 (TEST probes).

    python scripts/epoch_descriptive.py --probe runs/real/analysis_inputs_secondary/probe.csv --steps-per-epoch 99 --out reports/integration/epoch_descriptive_R06.md

PREREG v5 section 10 item 9: descriptive only, no hypothesis tests, outside the Holm family. Rate = mean over probes, then over seeds,
per fact; the +- is the fact-clustered standard error (facts are the unit). ``chance`` is the mean ``null_stored_rate`` of the same rows.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", required=True)
    ap.add_argument("--steps-per-epoch", type=int, required=True)
    ap.add_argument("--epochs", type=int, nargs="+", default=[12, 30, 60])
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    p = pd.read_csv(a.probe)
    p = p[p["split"] == "test"].copy()
    p["checkpoint"] = p["checkpoint"].astype(str)
    cps = [("init", "init")] + [(f"epoch {e}", str(e * a.steps_per_epoch)) for e in a.epochs]
    lines = ["# Stored rate by freq x div, TEST probes (descriptive; no tests; outside the Holm family)", "",
             "Rate +- fact-clustered SE; `chance` = mean null_stored_rate of the same rows. 3 seeds.", ""]
    cells = sorted(p.groupby(["freq_bin", "div_bin"]).size().index.tolist())
    head = "| checkpoint | all | " + " | ".join(f"{f} x {d}" for f, d in cells) + " |"
    lines += [head, "|" + "---|" * (len(cells) + 2)]
    for name, c in cps:
        r = p[p["checkpoint"] == c]
        if r.empty:
            lines.append(f"| {name} | missing |")
            continue

        def cell(x: pd.DataFrame) -> str:
            f = x.groupby("fact_id")["stored"].mean()
            se = f.std(ddof=1) / np.sqrt(len(f)) if len(f) > 1 else float("nan")
            return f"{x['stored'].mean():.3f} +- {se:.3f} (chance {x['null_stored_rate'].mean():.3f}, {len(f)} facts)"

        lines.append(f"| {name} | {cell(r)} | " + " | ".join(cell(r[(r['freq_bin'] == f) & (r['div_bin'] == d)]) for f, d in cells) + " |")
    text = "\n".join(lines) + "\n"
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
