"""Full-corpus helpers (P02c): retrying backend, round bookkeeping, final assembly and audits."""

from __future__ import annotations

import hashlib
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .doc_validator import WORD_RE, normalise_text
from .pilot import ApiError, CallResult, _load_attempts, _safe

MODEL = "gpt-5.4-mini"
GRAM = 13
RETRY_MARKERS = ("RateLimit", "429", "Timeout", "timed out", "APIConnection", "InternalServer", "502", "503", "504",
                 "overloaded")


class RetryingBackend:
    """Wraps a backend: transient provider errors are retried with exponential backoff."""

    def __init__(self, inner: Any, tries: int = 6, base_delay: float = 2.0, sleep=time.sleep) -> None:
        self.inner, self.tries, self.base_delay, self.sleep = inner, tries, base_delay, sleep
        self.retries = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def call(self, *args: Any, **kwargs: Any) -> CallResult:
        for attempt in range(self.tries):
            try:
                return self.inner.call(*args, **kwargs)
            except ApiError as exc:
                if attempt == self.tries - 1 or not any(m in str(exc) for m in RETRY_MARKERS):
                    raise
                self.retries += 1
                self.sleep(min(60.0, self.base_delay * 2 ** attempt))
        raise AssertionError("unreachable")


def apply_plan_overrides(plan: list[dict[str, Any]], out_dir: Path) -> list[dict[str, Any]]:
    """P02c5: documents re-planned as another type (data/corpus/plan_overrides.json) keep their facts and splits."""
    path = out_dir / "plan_overrides.json"
    if not path.exists():
        return plan
    over = json.loads(path.read_text(encoding="utf-8"))
    return [{**r, **{k: v for k, v in over[r["doc_id"]].items() if k == "doc_type"}} if r["doc_id"] in over else r
            for r in plan]


def round_dir(base: Path, number: int) -> Path:
    """Round 0 is ``base`` itself; re-plan and regeneration rounds are base_r1, base_r2, ..."""
    return base if number == 0 else base.with_name(f"{base.name}_r{number}")


def doc_mode(row: dict[str, Any]) -> str:
    modes = set(row["modes"])
    return "none" if not modes else (modes.pop() if len(modes) == 1 else "mixed")


def load_rounds(base: Path, rounds: int = 6) -> dict[int, list[dict[str, Any]]]:
    out = {}
    for number in range(rounds + 1):
        path = round_dir(base, number) / _safe(MODEL) / "attempts.jsonl"
        if path.exists():
            out[number] = _load_attempts(path)
    return out


def accepted_by_doc(rounds: dict[int, list[dict[str, Any]]]) -> dict[str, tuple[int, dict[str, Any], int]]:
    """doc_id -> (round, accepted attempt, total attempts over all rounds); latest accepted round wins."""
    total: Counter[str] = Counter()
    best: dict[str, tuple[int, dict[str, Any]]] = {}
    for number in sorted(rounds):
        for a in rounds[number]:
            total[a["doc_id"]] += 1
            if a["ok"]:
                best[a["doc_id"]] = (number, a)
    return {d: (n, a, total[d]) for d, (n, a) in best.items()}


def final_docs(
    plan: list[dict[str, Any]], rounds: dict[int, list[dict[str, Any]]], dropped: set[str] | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    """The corpus documents in plan order and the ids that have no accepted text."""
    accepted = accepted_by_doc(rounds)
    docs, missing = [], []
    for row in plan:
        if dropped and row["doc_id"] in dropped:
            continue
        if row["doc_id"] not in accepted:
            missing.append(row["doc_id"])
            continue
        number, attempt, total = accepted[row["doc_id"]]
        docs.append({
            "doc_id": row["doc_id"], "split": row["split"], "doc_type": row["doc_type"], "mode": doc_mode(row),
            "regime": row["style_regime"], "role": row["style_card"]["author_role"],
            "tone": row["style_card"]["tone"], "fact_ids": row["fact_ids"], "modes": row["modes"],
            "text": attempt["text"], "attempts": total,
        })
    return docs, missing


def record_for(row: dict[str, Any], rounds: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    """Full attempt record of one document across rounds (rule ids, placements, bank ids, cost)."""
    attempts = []
    for number in sorted(rounds):
        for a in rounds[number]:
            if a["doc_id"] != row["doc_id"]:
                continue
            attempts.append({
                "round": number, "attempt": a["attempt"], "ok": a["ok"], "stuck": a.get("stuck", False),
                "prompt_version": a.get("prompt_version"), "validator_version": a.get("validator_version"),
                "rule_ids": sorted({r.split()[0] for r in a["reasons"]}), "usd": a.get("usd", 0.0),
                "placements": a.get("placements", {}), "input_tokens": a.get("input_tokens"),
                "output_tokens": a.get("output_tokens"),
            })
    placements = next((x["placements"] for x in reversed(attempts) if x["ok"]), {})
    return {
        "doc_id": row["doc_id"], "split": row["split"], "attempts": attempts, "cost": sum(x["usd"] for x in attempts),
        "bank_sentence_ids": {f: p.get("sentence_id") for f, p in placements.items()},
        "frame_ids": {f: p.get("frame") for f, p in placements.items()},
    }


# ---- 13-gram audit ----------------------------------------------------------------------


def tokens(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(normalise_text(text))]


def grams13(text: str) -> set[tuple[str, ...]]:
    toks = tokens(text)
    return {tuple(toks[i : i + GRAM]) for i in range(len(toks) - GRAM + 1)}


def leakage(docs: list[dict[str, Any]]) -> dict[str, int]:
    """Per val/test doc: number of 13-grams shared with the train split (only docs with >= 1)."""
    train: set[tuple[str, ...]] = set()
    for d in docs:
        if d["split"] == "train":
            train |= grams13(d["text"])
    out = {}
    for d in docs:
        if d["split"] != "train":
            shared = len(grams13(d["text"]) & train)
            if shared:
                out[d["doc_id"]] = shared
    return out


def train_near_duplicates(docs: list[dict[str, Any]], threshold: float = 0.5) -> list[tuple[str, str, float]]:
    """Train pairs whose 13-gram sets have Jaccard above the threshold."""
    sets = {d["doc_id"]: grams13(d["text"]) for d in docs if d["split"] == "train"}
    index: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for doc_id, grams in sets.items():
        for g in grams:
            index[g].append(doc_id)
    pairs: Counter[tuple[str, str]] = Counter()
    for ids in index.values():
        if 1 < len(ids) <= 200:
            for i, a in enumerate(ids):
                for b in ids[i + 1 :]:
                    pairs[(a, b) if a < b else (b, a)] += 1
    out = []
    for (a, b), shared in pairs.items():
        union = len(sets[a]) + len(sets[b]) - shared
        if union and shared / union > threshold:
            out.append((a, b, shared / union))
    return sorted(out)


def exact_duplicates(docs: list[dict[str, Any]]) -> list[list[str]]:
    by_hash: dict[str, list[str]] = defaultdict(list)
    for d in docs:
        by_hash[hashlib.sha256(d["text"].encode("utf-8")).hexdigest()].append(d["doc_id"])
    return [ids for ids in by_hash.values() if len(ids) > 1]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_split_files(out_dir: Path, docs: list[dict[str, Any]]) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for split in ("train", "val", "test"):
        path = out_dir / f"{split}.jsonl"
        keys = ("doc_id", "split", "doc_type", "mode", "regime", "role", "tone", "fact_ids", "text", "attempts")
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for d in docs:
                if d["split"] == split:
                    handle.write(json.dumps({k: d[k] for k in keys}, ensure_ascii=False) + "\n")
        paths[split] = path
    return paths


def write_manifest(out_dir: Path) -> dict[str, Any]:
    manifest = {"version": 1, "files": {
        f"{s}.jsonl": {"split": s, "sha256": sha256_file(out_dir / f"{s}.jsonl")} for s in ("train", "val", "test")}}
    flags_path = out_dir / "flags.json"
    if flags_path.exists():  # P02c6: disclosed leak_flag / meta_flag documents
        flags = json.loads(flags_path.read_text(encoding="utf-8"))
        manifest["leak_flag"] = flags["leak_flag"]
        manifest["meta_flag"] = flags["meta_flag"]
        manifest["flags_sha256"] = sha256_file(flags_path)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def sample_docs(docs: list[dict[str, Any]], seed: int = 150, count: int = 12) -> list[dict[str, Any]]:
    """One accepted document per document type (seeded), then random extras up to ``count``."""
    rng = random.Random(seed)
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in docs:
        by_type[d["doc_type"]].append(d)
    chosen = [rng.choice(by_type[t]) for t in sorted(by_type)][:count]
    rest = [d for d in docs if d not in chosen]
    chosen += rng.sample(rest, max(0, min(count - len(chosen), len(rest))))
    return chosen
