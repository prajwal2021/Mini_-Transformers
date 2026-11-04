"""Select the pilot-v5 cohort: 40 fresh documents never used by an earlier pilot (offline).

Strata (type: templated / paraphrased / validation-or-test / background):
  meeting minutes 3/2/1/0, training handbook page 3/2/1/0, policy manual section 3/2/1/0,
  complaint letter + reply 2/2/1/0, employee email 2/2/1/0, customer notice 1/0/0/1,
  help-center article 0/1/0/1, internal chat thread 1/0/0/1, incident report 1/1/0/0,
  newsletter blurb 1/1/0/0, monthly ops report 1/1/0/0.
Writes data/pilot_v5/pilot_rows.jsonl and copies the reasoning-none API configuration.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
# type -> (templated, paraphrased, valtest, background)
STRATA = {
    "meeting minutes": (3, 2, 1, 0),
    "training handbook page": (3, 2, 1, 0),
    "policy manual section": (3, 2, 1, 0),
    "complaint letter + reply": (2, 2, 1, 0),
    "employee email": (2, 2, 1, 0),
    "customer notice": (1, 0, 0, 1),
    "help-center article": (0, 1, 0, 1),
    "internal chat thread": (1, 0, 0, 1),
    "incident report": (1, 1, 0, 0),
    "newsletter blurb": (1, 1, 0, 0),
    "monthly ops report": (1, 1, 0, 0),
}
VALTEST_PLAN = [("val", "novel"), ("val", "iid"), ("test", "novel"), ("test", "iid"), ("val", "novel")]


def load_rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def select(plan: list[dict], used: set[str], seed: int) -> list[dict]:
    rng = random.Random(seed)
    taken = set(used)
    chosen: list[dict] = []
    valtest_turn = 0
    for doc_type, (n_t, n_p, n_v, n_b) in STRATA.items():
        k = 0
        wanted = [("templated", n_t), ("paraphrased", n_p), ("valtest", n_v), ("background", n_b)]
        for kind, count in wanted:
            for _ in range(count):
                if kind == "templated":
                    pool = [r for r in plan if r["split"] == "train" and r["doc_type"] == doc_type
                            and r["fact_ids"] and set(r["modes"]) == {"templated"}]
                    k = k % 3 + 1
                elif kind == "paraphrased":
                    pool = [r for r in plan if r["split"] == "train" and r["doc_type"] == doc_type
                            and r["fact_ids"] and set(r["modes"]) == {"paraphrased"}]
                elif kind == "background":
                    pool = [r for r in plan if r["split"] == "train" and r["doc_type"] == doc_type
                            and not r["fact_ids"]]
                else:
                    split, regime = VALTEST_PLAN[valtest_turn % len(VALTEST_PLAN)]
                    valtest_turn += 1
                    pool = [r for r in plan if r["split"] == split and r["style_regime"] == regime
                            and r["doc_type"] == doc_type]
                    if not [r for r in pool if r["doc_id"] not in taken]:
                        pool = [r for r in plan if r["split"] in ("val", "test") and r["doc_type"] == doc_type]
                pool = [r for r in pool if r["doc_id"] not in taken]
                if not pool:
                    raise AssertionError(f"no fresh {kind} row for {doc_type}")
                rng.shuffle(pool)
                if kind == "templated":
                    pool.sort(key=lambda r: abs(len(r["fact_ids"]) - k))
                row = dict(pool[0])
                row["pilot_category"] = (
                    f"{row['split']}-{row['style_regime']}" if kind == "valtest" else kind
                )
                row["cohort"] = "fresh40"
                taken.add(row["doc_id"])
                chosen.append(row)
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "pilot_v5")
    args = parser.parse_args(argv)
    config = yaml.safe_load((ROOT / "configs" / "generation.yaml").read_text(encoding="utf-8"))
    plan = load_rows(ROOT / "data" / "plan" / "plan.jsonl")
    used: set[str] = set()
    for earlier in sorted((ROOT / "data").glob("pilot*/pilot_rows.jsonl")):
        if earlier.parent.name not in {"pilot_mock", args.out_dir.name}:
            used |= {r["doc_id"] for r in load_rows(earlier)}
    rows = select(plan, used, config["seed"] + 5)
    assert len(rows) == 40 and not {r["doc_id"] for r in rows} & used
    rows.sort(key=lambda r: r["doc_id"])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "pilot_rows.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    source = ROOT / "data" / "pilot_v3" / "api_config.json"
    if source.exists() and not (args.out_dir / "api_config.json").exists():
        shutil.copy(source, args.out_dir / "api_config.json")
    templated = sum(set(r["modes"]) == {"templated"} for r in rows)
    paraphrased = sum(set(r["modes"]) == {"paraphrased"} for r in rows)
    background = sum(not r["fact_ids"] for r in rows)
    valtest = sum(r["split"] != "train" for r in rows)
    print(f"{len(rows)} fresh rows; templated {templated}, paraphrased {paraphrased} "
          f"(incl. {valtest} val/test), background {background}")
    print("types:", dict(Counter(r["doc_type"] for r in rows)))
    print("ids:", " ".join(r["doc_id"] for r in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
