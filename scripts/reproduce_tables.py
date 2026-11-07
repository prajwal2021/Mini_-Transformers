# ruff: noqa: E501
"""Reproduce the H1-H4 table from the saved analysis inputs in the release bundle, without retraining, and compare it with the bundled result.

    python scripts/reproduce_tables.py --bundle bundle [--out reproduced]

Runs ``scripts/run_analysis.py`` on ``bundle/reproduce/probe.csv`` (test probes at E* = epoch 30 and the init checkpoint) and ``bundle/reproduce/qa.csv``
(QA predictions of the pre-specified early-stopped SFT, base zero-shot and 2-shot), then checks every estimate, CI bound and p-value of
``analysis_family.csv`` against ``bundle/results/analysis_family_corrected.csv``. Needs the full package: ``pip install -e .`` (pandas, statsmodels, scipy).
Takes about one minute on a CPU. Exit code 0 = reproduced, 1 = differs.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--bundle", default="bundle")
    ap.add_argument("--out", default="reproduced")
    ap.add_argument("--tol", type=float, default=1e-6)
    a = ap.parse_args()
    b, out = Path(a.bundle), Path(a.out)
    for f in ("reproduce/probe.csv", "reproduce/qa.csv", "results/analysis_family_corrected.csv"):
        if not (b / f).is_file():
            print(f"error: {b / f} is missing", file=sys.stderr)
            return 2
    cmd = [sys.executable, str(ROOT / "scripts" / "run_analysis.py"), "--input", str(b / "reproduce" / "probe.csv"), "--qa-input", str(b / "reproduce" / "qa.csv"),
           "--out", str(out), "--real", "--no-mixed"]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if p.returncode:
        print(p.stderr[-800:], file=sys.stderr)
        return 2
    new = pd.read_csv(out / "tables" / "analysis_family.csv").set_index("hypothesis")
    old = pd.read_csv(b / "results" / "analysis_family_corrected.csv").set_index("hypothesis")
    bad = []
    for h in old.index:
        for c in ("estimate", "ci_low", "ci_high", "p_raw", "p_holm"):
            x, y = new.loc[h, c], old.loc[h, c]
            if not (pd.isna(x) and pd.isna(y)) and not abs(x - y) <= a.tol:
                bad.append(f"{h} {c}: reproduced {x} vs bundled {y}")
    print(new[["estimate", "ci_low", "ci_high", "p_raw", "p_holm", "status"]].round(4).to_string())
    print("REPRODUCED: every estimate, CI bound and p-value matches the bundled table" if not bad else "DIFFERENCES:\n  " + "\n  ".join(bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
