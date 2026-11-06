# ruff: noqa: E501
"""Fail if any NOVEL probe prompt shares an 8-gram with the train corpus.

Usage: python scripts/check_probe_overlap.py --split-manifest path/to/split_manifest.json

The manifest lists the train corpus files. Accepted layouts (paths relative to the manifest):
  {"train": ["a.jsonl", ...]}  |  {"train_files": [...]}  |  {"splits": {"train": {"files": [...]}}}
  |  the split manifest of docs/SPLIT_MANIFEST.md: {"version": 1, "files": {path: {"split": "train", ...}}}
Files ending in .jsonl contribute their "text" field per line; any other file is read as text.
Each novel prompt is checked as prompt + " " + value, for every fact. Canonical prompts are
reported for information only (they are expected to overlap the templated sentences).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slm.eval.probes import build_probes, load_facts, ngram_set  # noqa: E402


def train_files(manifest_path: Path) -> list[Path]:
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    if m.get("version") == 1 and "files" in m:  # slm.split_manifest format; only train files are opened
        files = [k for k, v in m["files"].items() if v["split"] == "train"]
    elif "splits" in m:
        files = m["splits"]["train"]["files"]
    else:
        files = m.get("train_files", m.get("train"))
    if not files:
        raise SystemExit("manifest lists no train files")
    return [manifest_path.parent / f for f in files]


def corpus_texts(paths: list[Path]):
    for p in paths:
        if p.suffix == ".jsonl":
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    yield json.loads(line)["text"]
        else:
            yield p.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--split-manifest", required=True)
    ap.add_argument("--kb", default=str(ROOT / "data/kb/kb.json"))
    ap.add_argument("--n", type=int, default=8)
    args = ap.parse_args(argv)

    corpus = ngram_set(corpus_texts(train_files(Path(args.split_manifest))), args.n)
    probes = build_probes(load_facts(args.kb))
    bad: dict[str, set[str]] = {"canonical": set(), "novel": set()}
    shared: dict[str, set[tuple[str, ...]]] = {}
    for it in probes.items:
        text = f"{it.prompt} {it.value}"
        hit = ngram_set([text], args.n) & corpus
        if hit:
            bad[it.probe_frame].add(it.prompt)
            shared.setdefault(it.prompt, set()).update(hit)
    print(f"canonical prompts sharing a {args.n}-gram with train (informational): "
          f"{len(bad['canonical'])}")
    if bad["novel"]:
        print(f"FAIL: {len(bad['novel'])} novel prompts share a {args.n}-gram with train:")
        for p in sorted(bad["novel"])[:20]:
            print("  ", p)
            for g in sorted(shared[p])[:3]:
                print("       8-gram:", " ".join(g))
        return 1
    print("OK: no novel probe prompt shares an 8-gram with the train corpus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
