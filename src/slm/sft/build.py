"""SFT fact split and QA data builder (DESIGN.md section 7).

Format (identical for base and SFT evaluation): ``Question: <q>\\nAnswer: <sentence><|eos|>``.
Loss is on the answer tokens only, so each row carries the prompt and the completion separately.
Fact split: SFT-train 40% / SFT-val 10% / held-out 50%, stratified by freq_bin x div_bin.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from slm.sft.templates import TEMPLATE_SETS, render_question, template_id

SPLIT_NAMES = ("sft_train", "sft_val", "heldout")
SPLIT_FRACTIONS = {"sft_train": 0.4, "sft_val": 0.1, "heldout": 0.5}
EOS = "<|eos|>"


@dataclass(frozen=True)
class SftFact:
    fact_id: str
    attribute_id: str
    family: str
    entity: str
    value: str
    canonical_sentence: str
    freq_bin: str
    div_bin: str
    kb_split: str

    @property
    def cell(self) -> str:
        return f"{self.freq_bin}_{self.div_bin}"


def load_sft_facts(kb_path: str | Path) -> list[SftFact]:
    kb = json.loads(Path(kb_path).read_text(encoding="utf-8"))
    return [
        SftFact(
            f["fact_id"], f["attribute_id"], f["family"], f["entity"], f["value"],
            f["canonical_sentence"], f["freq_bin"], f["div_bin"], f["sft_split"],
        )
        for f in kb["measured_facts"]
    ]


def build_fact_split(facts: list[SftFact], seed: int) -> dict[str, str]:
    """Seeded 40/10/50 split, stratified by (freq_bin, div_bin). Returns fact_id -> split."""
    cells: dict[tuple[str, str], list[str]] = defaultdict(list)
    for f in facts:
        cells[f.freq_bin, f.div_bin].append(f.fact_id)
    out: dict[str, str] = {}
    for key in sorted(cells):
        ids = sorted(cells[key])
        random.Random(f"{seed}:{key}").shuffle(ids)
        n = len(ids)
        n_train = round(SPLIT_FRACTIONS["sft_train"] * n)
        n_val = round(SPLIT_FRACTIONS["sft_val"] * n)
        for i, fid in enumerate(ids):
            if i < n_train:
                out[fid] = "sft_train"
            elif i < n_train + n_val:
                out[fid] = "sft_val"
            else:
                out[fid] = "heldout"
    return out


def split_table(facts: list[SftFact], split: dict[str, str]) -> dict[tuple[str, str, str], int]:
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for f in facts:
        counts[f.freq_bin, f.div_bin, split[f.fact_id]] += 1
    return dict(counts)


def make_row(fact: SftFact, subset: str, template_set: str, base: int, wrapper: int) -> dict:
    question = render_question(fact.family, fact.attribute_id, fact.entity, base, wrapper)
    prompt = f"Question: {question}\nAnswer:"
    completion = f" {fact.canonical_sentence}{EOS}"
    return {
        "id": f"{subset}:{fact.fact_id}:{template_id(fact.attribute_id, base, wrapper)}",
        "subset": subset,
        "fact_id": fact.fact_id,
        "attribute_id": fact.attribute_id,
        "freq_bin": fact.freq_bin,
        "div_bin": fact.div_bin,
        "template_set": template_set,
        "template_id": template_id(fact.attribute_id, base, wrapper),
        "question": question,
        "answer": fact.canonical_sentence,
        "value": fact.value,
        "prompt": prompt,
        "completion": completion,
        "text": prompt + completion,
    }


def make_rows(facts: list[SftFact], subset: str, template_set: str) -> list[dict]:
    rows = []
    for f in sorted(facts, key=lambda x: x.fact_id):
        for base, wrapper in TEMPLATE_SETS[template_set]:
            rows.append(make_row(f, subset, template_set, base, wrapper))
    return rows


def build_datasets(facts: list[SftFact], split: dict[str, str]) -> dict[str, list[dict]]:
    """Training, validation and the frozen evaluation subsets (E0 sanity, E1, E2)."""
    by = {name: [f for f in facts if split[f.fact_id] == name] for name in SPLIT_NAMES}
    return {
        "sft_train": make_rows(by["sft_train"], "train", "train"),
        "sft_val": make_rows(by["sft_val"], "val", "val"),
        "E0": make_rows(by["sft_train"], "E0", "train"),
        "E1": make_rows(by["sft_train"], "E1", "test"),
        "E2": make_rows(by["heldout"], "E2", "test"),
    }


def _write_jsonl(path: Path, rows: list[dict]) -> str:
    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    path.write_bytes(text.encode("utf-8"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_datasets(
    facts: list[SftFact], split: dict[str, str], out_dir: str | Path, *, seed: int, source: str
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = build_datasets(facts, split)
    qa_test = data["E0"] + data["E1"] + data["E2"]
    hashes = {
        "sft_train.jsonl": _write_jsonl(out / "sft_train.jsonl", data["sft_train"]),
        "sft_val.jsonl": _write_jsonl(out / "sft_val.jsonl", data["sft_val"]),
        "qa_test.jsonl": _write_jsonl(out / "qa_test.jsonl", qa_test),
    }
    (out / "fact_split.json").write_text(
        json.dumps(dict(sorted(split.items())), indent=1) + "\n", encoding="utf-8"
    )
    table = split_table(facts, split)
    manifest = {
        "seed": seed,
        "split_source": source,
        "rows": {k: len(v) for k, v in data.items()},
        "sha256": hashes,
        "split_sizes": {n: sum(1 for v in split.values() if v == n) for n in SPLIT_NAMES},
        "split_by_cell": {f"{a}_{b}": {} for a, b, _ in table},
    }
    for (a, b, s), n in sorted(table.items()):
        manifest["split_by_cell"][f"{a}_{b}"][s] = n
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


# ---- real data (R00): data/sft/{sft_train,sft_val}.jsonl, data/eval/qa_test.jsonl --------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_jsonl(path: str | Path) -> list[dict]:
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def write_real_datasets(kb_path: str | Path, sft_dir: str | Path, eval_dir: str | Path) -> dict:
    """Write the SFT files and the QA test file from the KB's own ``sft_split`` (never re-drawn).

    ``sft_dir`` gets ``sft_train.jsonl``, ``sft_val.jsonl``, ``fact_split.json``, ``manifest.json``;
    ``eval_dir`` gets ``qa_test.jsonl`` (E0 + E1 + E2). The manifest holds the sha256 of each file.
    """
    sft_dir, eval_dir = Path(sft_dir), Path(eval_dir)
    sft_dir.mkdir(parents=True, exist_ok=True)
    eval_dir.mkdir(parents=True, exist_ok=True)
    facts = load_sft_facts(kb_path)
    split = {f.fact_id: f.kb_split for f in facts}
    bad = sorted(set(split.values()) - set(SPLIT_NAMES))
    if bad:
        raise ValueError(f"kb.json has unknown sft_split values: {bad}")
    data = build_datasets(facts, split)
    _write_jsonl(sft_dir / "sft_train.jsonl", data["sft_train"])
    _write_jsonl(sft_dir / "sft_val.jsonl", data["sft_val"])
    _write_jsonl(eval_dir / "qa_test.jsonl", data["E0"] + data["E1"] + data["E2"])
    (sft_dir / "fact_split.json").write_text(
        json.dumps(dict(sorted(split.items())), indent=1) + "\n", encoding="utf-8")
    report = verify_datasets(kb_path, sft_dir, eval_dir)
    manifest = {
        "kb": str(kb_path), "kb_sha256": sha256_file(kb_path), "split_source": "kb.json sft_split",
        "files": {
            "data/sft/sft_train.jsonl": sha256_file(sft_dir / "sft_train.jsonl"),
            "data/sft/sft_val.jsonl": sha256_file(sft_dir / "sft_val.jsonl"),
            "data/sft/fact_split.json": sha256_file(sft_dir / "fact_split.json"),
            "data/eval/qa_test.jsonl": sha256_file(eval_dir / "qa_test.jsonl"),
        },
        "rows": report["rows"], "cell_counts": report["cell_counts"], "checks": report["checks"],
    }
    (sft_dir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


def verify_datasets(kb_path: str | Path, sft_dir: str | Path, eval_dir: str | Path) -> dict:
    """Assert the files on disk against the KB; raises AssertionError naming the failed check."""
    kb = json.loads(Path(kb_path).read_text(encoding="utf-8"))["measured_facts"]
    kb_split = {f["fact_id"]: f["sft_split"] for f in kb}
    on_disk = json.loads((Path(sft_dir) / "fact_split.json").read_text(encoding="utf-8"))
    train = read_jsonl(Path(sft_dir) / "sft_train.jsonl")
    val = read_jsonl(Path(sft_dir) / "sft_val.jsonl")
    qa = read_jsonl(Path(eval_dir) / "qa_test.jsonl")
    ids = lambda rows: {r["fact_id"] for r in rows}  # noqa: E731
    by = lambda name: {f for f, s in kb_split.items() if s == name}  # noqa: E731
    e = {k: [r for r in qa if r["subset"] == k] for k in ("E0", "E1", "E2")}
    tmpl = lambda rows: {r["template_id"] for r in rows}  # noqa: E731
    checks = {
        "fact_split.json equals kb.json sft_split": on_disk == kb_split,
        "sft_train facts == kb sft_train": ids(train) == by("sft_train"),
        "sft_val facts == kb sft_val": ids(val) == by("sft_val"),
        "E0 facts == kb sft_train": ids(e["E0"]) == by("sft_train"),
        "E1 facts == kb sft_train": ids(e["E1"]) == by("sft_train"),
        "E2 facts == kb heldout": ids(e["E2"]) == by("heldout"),
        "E2 facts disjoint from all SFT facts": not (ids(e["E2"]) & (ids(train) | ids(val))),
        "E1 templates unseen in SFT train and val": not (tmpl(e["E1"]) & (tmpl(train) | tmpl(val))),
        "E2 templates unseen in SFT train and val": not (tmpl(e["E2"]) & (tmpl(train) | tmpl(val))),
        "E0 templates are SFT-train templates": tmpl(e["E0"]) <= tmpl(train),
        "E1 questions differ from SFT questions": not (
            {r["question"] for r in e["E1"]} & {r["question"] for r in train + val}),
        "no SFT or QA row asks with the value in the question": not [
            r for r in train + val + qa if r["value"].lower() in r["question"].lower()],
        "sft_val facts disjoint from sft_train facts": not (ids(val) & ids(train)),
    }
    cells: dict[str, dict[str, int]] = {}
    for f in kb:
        cells.setdefault(f"{f['freq_bin']}_{f['div_bin']}", {}).setdefault(f["sft_split"], 0)
        cells[f"{f['freq_bin']}_{f['div_bin']}"][f["sft_split"]] += 1
    checks["8/2/10 facts per freq x div cell (sft_train/sft_val/heldout)"] = all(
        (c.get("sft_train"), c.get("sft_val"), c.get("heldout")) == (8, 2, 10)
        for c in cells.values()
    ) and len(cells) == 6
    failed = [k for k, ok in checks.items() if not ok]
    if failed:
        raise AssertionError("dataset checks failed: " + "; ".join(failed))
    return {"checks": {k: True for k in checks}, "cell_counts": cells,
            "rows": {"sft_train": len(train), "sft_val": len(val),
                     **{k: len(v) for k, v in e.items()}}}
