"""Length calibration (offline; no API calls).

v1 (P02b5, E8): per doc type, median actual/target over the prompt-v3 pilot, both models pooled;
  ask_multiplier = clip(1 / median, 1.0, 1.8). Kept in configs/length_calibration_v1.yaml.
v2 (P02b6, E15): per (model, doc type), rho = median(actual words / ask words) over the model's
  non-empty attempts in the prompt-v4 pilot (the model-level median when n < 4). The prompt then
  asks for clip(target / rho, 0.9 target, 1.3 target) words, within [60, 340]. Writes
  configs/length_calibration.yaml nested by model.
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


def _rows(pilot_dir: Path) -> dict[str, dict]:
    return {
        r["doc_id"]: r
        for r in (json.loads(x) for x in
                  (pilot_dir / "pilot_rows.jsonl").read_text(encoding="utf-8").splitlines() if x.strip())
    }


def _attempts(sub: Path) -> list[dict]:
    return [json.loads(x) for x in (sub / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()]


def calibrate(pilot_dir: Path) -> dict:
    """v1 calibration (pooled over models, relative to the target)."""
    rows = _rows(pilot_dir)
    ratios: dict[str, list[float]] = {}
    pooled: list[float] = []
    models = []
    for sub in sorted(p for p in pilot_dir.iterdir() if (p / "attempts.jsonl").exists()):
        models.append(sub.name)
        for attempt in _attempts(sub):
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


def calibrate_v2(pilot_dir: Path) -> dict:
    """v2 calibration: per model and doc type, rho = median(actual words / ask words)."""
    rows = _rows(pilot_dir)
    out: dict[str, dict] = {}
    for sub in sorted(p for p in pilot_dir.iterdir() if (p / "attempts.jsonl").exists()):
        per_type: dict[str, list[float]] = {}
        everything: list[float] = []
        for attempt in _attempts(sub):
            if not attempt["text"].strip() or not attempt.get("ask_words"):
                continue
            rho = len(WORD_RE.findall(attempt["text"])) / attempt["ask_words"]
            per_type.setdefault(rows[attempt["doc_id"]]["doc_type"], []).append(rho)
            everything.append(rho)
        model_median = statistics.median(everything)
        out[sub.name] = {
            "_model_median_rho": round(model_median, 4),
            "_attempts": len(everything),
            **{
                doc_type: {
                    "attempts": len(values),
                    "rho": round(statistics.median(values) if len(values) >= MIN_ATTEMPTS else model_median, 4),
                    "used_model_median": len(values) < MIN_ATTEMPTS,
                }
                for doc_type, values in sorted(per_type.items())
            },
        }
    return {
        "source": str(pilot_dir.relative_to(ROOT)) if pilot_dir.is_relative_to(ROOT) else str(pilot_dir),
        "rule": "rho = median(actual words / ask words) per (model, doc type), model median when "
                "n < 4; ask = min(340, max(60, clip(target / rho, 0.9 target, 1.3 target)))",
        "models": out,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--mode", choices=["v1", "v2"], default="v2")
    args = parser.parse_args(argv)
    if args.mode == "v1":
        pilot = args.pilot_dir or ROOT / "data" / "pilot_v3"
        result = calibrate(pilot)
        out = args.out or ROOT / "configs" / "length_calibration_v1.yaml"
        out.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
        print(f"v1: calibrated {result['attempts']} attempts -> {out}")
        return 0
    pilot = args.pilot_dir or ROOT / "data" / "pilot_v4"
    result = calibrate_v2(pilot)
    out = args.out or ROOT / "configs" / "length_calibration.yaml"
    out.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
    for model, spec in result["models"].items():
        print(f"{model}: {spec['_attempts']} attempts, model median rho {spec['_model_median_rho']}")
        for doc_type, row in spec.items():
            if not doc_type.startswith("_"):
                print(f"  {doc_type:28s} n={row['attempts']:3d} rho={row['rho']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
