"""Length calibration from the prompt-v3 pilot (P02b5, E8). Offline; no API calls.

For each doc type: median of actual words / target words over the non-empty attempts of both
models pooled (pooled median when a type has fewer than 4 attempts), then
ask_multiplier = clip(1 / median, 1.0, 1.8). Writes configs/length_calibration.yaml.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import yaml

from slm.data.doc_validator_v1 import WORD_RE

ROOT = Path(__file__).resolve().parents[1]
MIN_ATTEMPTS = 4
LOW, HIGH = 1.0, 1.8


def calibrate(pilot_dir: Path) -> dict:
    rows = {
        r["doc_id"]: r
        for r in (json.loads(x) for x in
                  (pilot_dir / "pilot_rows.jsonl").read_text(encoding="utf-8").splitlines() if x.strip())
    }
    ratios: dict[str, list[float]] = {}
    pooled: list[float] = []
    models = []
    for sub in sorted(p for p in pilot_dir.iterdir() if (p / "attempts.jsonl").exists()):
        models.append(sub.name)
        for line in (sub / "attempts.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            attempt = json.loads(line)
            if not attempt["text"].strip():
                continue
            row = rows[attempt["doc_id"]]
            ratio = len(WORD_RE.findall(attempt["text"])) / row["target_words"]
            ratios.setdefault(row["doc_type"], []).append(ratio)
            pooled.append(ratio)
    pooled_median = statistics.median(pooled)
    types = {}
    for doc_type, values in sorted(ratios.items()):
        median = statistics.median(values) if len(values) >= MIN_ATTEMPTS else pooled_median
        types[doc_type] = {
            "attempts": len(values),
            "median_ratio": round(median, 4),
            "used_pooled_median": len(values) < MIN_ATTEMPTS,
            "ask_multiplier": round(min(HIGH, max(LOW, 1 / median)), 4),
        }
    return {
        "source": str(pilot_dir.relative_to(ROOT)) if pilot_dir.is_relative_to(ROOT) else str(pilot_dir),
        "models_pooled": models,
        "attempts": len(pooled),
        "pooled_median_ratio": round(pooled_median, 4),
        "rule": "ask_multiplier = clip(1 / median_ratio, 1.0, 1.8); ask = min(420, round(target * multiplier))",
        "types": types,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, default=ROOT / "data" / "pilot_v3")
    parser.add_argument("--out", type=Path, default=ROOT / "configs" / "length_calibration.yaml")
    args = parser.parse_args(argv)
    result = calibrate(args.pilot_dir)
    args.out.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
    print(f"Calibrated {result['attempts']} attempts; pooled median {result['pooled_median_ratio']}")
    for doc_type, spec in result["types"].items():
        print(f"  {doc_type:28s} n={spec['attempts']:3d} median={spec['median_ratio']:.3f} "
              f"x{spec['ask_multiplier']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
