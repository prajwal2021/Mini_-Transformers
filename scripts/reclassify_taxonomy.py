# ruff: noqa: E501
"""R08: re-apply the (R08) error taxonomy to already-written QA predictions. No decoding, no test file.

    python scripts/reclassify_taxonomy.py runs/real/qa/qa_predictions.csv [more.csv ...] [--keep-original-dir reports/integration/real_R06]

``format_failure`` used to hold two things: empty / repeating / value-free outputs, and well-formed answers that state a KB value of ANOTHER
attribute. The second is now ``wrong_attribute``; ``format_failure`` keeps only the true format failures. The original file is copied next to the
new one as ``<name>.original_taxonomy.csv`` (and into ``--keep-original-dir``), and the old label stays in the column ``error_class_r06``.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from slm.sft_eval import Taxonomy  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--keep-original-dir", default=None)
    a = ap.parse_args()
    tax = Taxonomy.from_kb(ROOT / "data" / "kb" / "kb.json")
    for f in a.files:
        p = Path(f)
        q = pd.read_csv(p, keep_default_na=False)
        orig = p.with_name(p.stem + ".original_taxonomy.csv")
        if not orig.exists():
            shutil.copyfile(p, orig)
        if a.keep_original_dir:
            shutil.copyfile(p if "error_class_r06" not in q.columns else orig, Path(a.keep_original_dir) / (p.stem + ".original_taxonomy.csv"))
        old = q["error_class"].copy()
        q["error_class"] = [
            tax.classify(str(r.prediction), r.attribute_id, r.gold_value, bool(r.exact_value_match)) for r in q.itertuples()
        ]
        q["error_class_r06"] = old
        assert ((old == "correct") == (q["error_class"] == "correct")).all()
        assert (old[old != "format_failure"] == q.loc[old != "format_failure", "error_class"]).all(), "only format_failure may change"
        q.to_csv(p, index=False, encoding="utf-8")
        print(p, "changed rows:", int((old != q.error_class).sum()))
        print(q.groupby(["checkpoint", "prompt_mode", "eval_set"]).error_class.value_counts().unstack(fill_value=0).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
