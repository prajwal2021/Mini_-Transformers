"""Choose the two fixed 2-shot exemplar facts and write configs/base_prompts.yaml.

Exemplars are sft_val facts (so they are in none of E0/E1/E2), seeded, from two different
families, each with its plain (no wrapper) sft_val question and the canonical answer sentence.

    python scripts/choose_base_exemplars.py --sft-dir ../slm-eval/data/sft_mock [--seed 0]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.sft_eval import check_exemplars_disjoint  # noqa: E402


def rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sft-dir", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "configs" / "base_prompts.yaml"))
    args = ap.parse_args()
    d = Path(args.sft_dir)
    val_path, qa_path = d / "sft_val.jsonl", d / "qa_test.jsonl"
    val = [r for r in rows(val_path) if r["template_id"].endswith("w0")]  # plain question
    by_fact = {r["fact_id"]: r for r in val}
    rng = random.Random(f"base-exemplars:{args.seed}")
    ids = sorted(by_fact)
    rng.shuffle(ids)
    chosen = []
    for fid in ids:
        family = by_fact[fid]["attribute_id"].split("_")[0]
        if all(by_fact[c]["attribute_id"].split("_")[0] != family for c in chosen):
            chosen.append(fid)
        if len(chosen) == 2:
            break
    exemplars = [{"fact_id": f, "attribute_id": by_fact[f]["attribute_id"],
                  "question": by_fact[f]["question"], "answer": by_fact[f]["answer"]}
                 for f in chosen]
    check_exemplars_disjoint(exemplars, rows(qa_path))
    cfg = {"base_prompts": {
        "seed": args.seed,
        "rule": "sft_val facts (in none of E0/E1/E2), seeded shuffle, two different families, "
                "plain sft_val question",
        "source_sft_val_sha256": hashlib.sha256(val_path.read_bytes()).hexdigest(),
        "exemplars": exemplars,
    }}
    Path(args.out).write_text(
        "# Fixed exemplars for the base model's 2-shot prompt (DESIGN 7.2, M-D044).\n"
        + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(yaml.safe_dump(cfg, sort_keys=False))


if __name__ == "__main__":
    main()