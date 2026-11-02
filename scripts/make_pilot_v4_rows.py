"""Select the pilot-v4 documents: the same 30 ids as earlier pilots plus 20 fresh ones.

Fresh 20: 4 documents of each of employee email, meeting minutes, complaint letter + reply,
training handbook page and policy manual section; per type 2 templated train documents, 1
paraphrased train document and 1 validation/test document. None of the ids was used by an
earlier pilot. Offline; no API calls. Writes data/pilot_v4/pilot_rows.jsonl and copies the
reasoning-none API configuration from data/pilot_v3.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FRESH_TYPES = [
    "employee email",
    "meeting minutes",
    "complaint letter + reply",
    "training handbook page",
    "policy manual section",
]
PER_TYPE = [("templated", 2), ("paraphrased", 1), ("valtest", 1)]


def load_rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def select_fresh(plan: list[dict], used: set[str], seed: int) -> list[dict]:
    rng = random.Random(seed)
    chosen: list[dict] = []
    taken = set(used)
    valtest_turn = 0
    for doc_type in FRESH_TYPES:
        k_cycle = 0
        for kind, count in PER_TYPE:
            for _ in range(count):
                if kind == "templated":
                    pool = [r for r in plan if r["split"] == "train" and r["doc_type"] == doc_type
                            and r["fact_ids"] and set(r["modes"]) == {"templated"}]
                    k_cycle = k_cycle % 3 + 1
                elif kind == "paraphrased":
                    pool = [r for r in plan if r["split"] == "train" and r["doc_type"] == doc_type
                            and r["fact_ids"] and set(r["modes"]) == {"paraphrased"}]
                else:
                    split = ("val", "test")[valtest_turn % 2]
                    valtest_turn += 1
                    pool = [r for r in plan if r["split"] == split and r["doc_type"] == doc_type]
                pool = [r for r in pool if r["doc_id"] not in taken]
                if not pool:
                    raise AssertionError(f"no fresh {kind} row for {doc_type}")
                rng.shuffle(pool)
                if kind == "templated":
                    pool.sort(key=lambda r: abs(len(r["fact_ids"]) - k_cycle))
                row = dict(pool[0])
                row["pilot_category"] = (
                    kind if kind != "valtest" else f"{row['split']}-{row['style_regime']}"
                )
                row["cohort"] = "fresh20"
                taken.add(row["doc_id"])
                chosen.append(row)
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "pilot_v4")
    args = parser.parse_args(argv)
    config = yaml.safe_load((ROOT / "configs" / "generation.yaml").read_text(encoding="utf-8"))
    plan = load_rows(ROOT / "data" / "plan" / "plan.jsonl")
    plan_by_id = {r["doc_id"]: r for r in plan}
    same30 = load_rows(ROOT / "data" / "pilot" / "pilot_rows.jsonl")
    used = {r["doc_id"] for r in same30}
    for earlier in sorted((ROOT / "data").glob("pilot*/pilot_rows.jsonl")):
        if earlier.parent.name not in {"pilot_mock", args.out_dir.name}:
            used |= {r["doc_id"] for r in load_rows(earlier)}
    rows = [
        {**plan_by_id[r["doc_id"]], "pilot_category": r["pilot_category"], "cohort": "same30"}
        for r in same30
    ]
    fresh = select_fresh(plan, used, config["seed"] + 4)
    assert not {r["doc_id"] for r in fresh} & used and len(fresh) == 20
    rows += fresh
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "pilot_rows.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    source = ROOT / "data" / "pilot_v3" / "api_config.json"
    if source.exists() and not (args.out_dir / "api_config.json").exists():
        shutil.copy(source, args.out_dir / "api_config.json")
    templated = sum(1 for r in fresh if set(r["modes"]) == {"templated"})
    paraphrased = sum(1 for r in fresh if set(r["modes"]) == {"paraphrased"})
    valtest = sum(1 for r in fresh if r["split"] != "train")
    print(f"{len(rows)} rows ({len(same30)} same + {len(fresh)} fresh); fresh: {templated} "
          f"templated, {paraphrased} paraphrased, {valtest} val/test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
