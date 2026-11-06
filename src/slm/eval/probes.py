"""Cloze probe harness (DESIGN.md section 6).

Probes are scored in groups: one group = one attribute x one prompt variant, i.e. the six
entities that have that attribute, each with its own prompt. Scoring the 6 x 6 matrix
``S[i][j] = score(prompt_i, " " + value_j)`` gives, for the fact of entity ``i``:

* ``rank`` = 1 + number of other values j scoring >= S[i][i] (a tie for first is never rank 1);
* ``binding_score`` = S[i][i] - mean_{k != i} S[k][i]   (the same value under the other
  entities' prompts, i.e. the same template with the entity swapped);
* ``stored`` = rank == 1 AND binding_score > 0   (DESIGN section 6).

Permutation null: the identical procedure with pseudo-truth ``o != i`` (the value that belongs
to another entity): rank of S[i][o] in row i, binding S[i][o] - mean_{k != i} S[k][o]. The mean
over the five pseudo-truths is ``null_stored_rate``.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from slm.eval.interface import Scorer
from slm.eval.wording import CANONICAL, ENTITY_REF, NOVEL_IDS, prefix  # noqa: F401  (ENTITY_REF re-exported)

SPLITS = ("val", "test")
PROBE_FRAMES = ("canonical", "novel")
N_NOVEL_VAL = 1  # val = canonical + 1 novel (2 templates); test = canonical + 2 novel (3)
CANONICAL_VARIANT = "canon"
INIT_CHECKPOINT = "init"  # the untrained model (epoch 0); chance level for a real model


@dataclass(frozen=True)
class Fact:
    fact_id: str
    entity_id: str
    entity: str
    attribute_id: str
    family: str
    value: str
    canonical_prefix: str
    freq_bin: str
    div_bin: str


@dataclass(frozen=True)
class ProbeItem:
    fact_id: str
    attribute_id: str
    split: str
    probe_frame: str  # "canonical" or "novel"
    variant: str  # e.g. "test-n2"
    prompt: str
    value: str
    candidates: tuple[str, ...]  # the 6 values of the attribute, true value first
    freq_bin: str
    div_bin: str


@dataclass
class ProbeSet:
    items: list[ProbeItem] = field(default_factory=list)
    seed: int = 0

    def __len__(self) -> int:
        return len(self.items)


def continuation(value: str) -> str:
    """Values follow the prompt after a single space (prompts never end in whitespace)."""
    return " " + value


def load_facts(kb_path: str | Path) -> list[Fact]:
    kb = json.loads(Path(kb_path).read_text(encoding="utf-8"))
    return [
        Fact(
            f["fact_id"], f["entity_id"], f["entity"], f["attribute_id"], f["family"],
            f["value"], f["canonical_prefix"], f["freq_bin"], f["div_bin"],
        )
        for f in kb["measured_facts"]
    ]


def split_novel(seed: int) -> dict[str, list[str]]:
    """Seeded, fixed assignment of the 3 novel templates: 1 to val, 2 to test."""
    ids = list(NOVEL_IDS)
    random.Random(f"novel:{seed}").shuffle(ids)
    return {"val": ids[:N_NOVEL_VAL], "test": ids[N_NOVEL_VAL:]}


def variants_for(split: str, seed: int) -> list[str]:
    return [CANONICAL_VARIANT, *split_novel(seed)[split]]


def build_probes(
    facts: Sequence[Fact], *, seed: int = 0, splits: Iterable[str] = SPLITS
) -> ProbeSet:
    by_attr: dict[str, list[Fact]] = {}
    for f in facts:
        by_attr.setdefault(f.attribute_id, []).append(f)
    for attr, group in by_attr.items():
        if len(group) != 6 or len({g.value for g in group}) != 6:
            raise ValueError(f"{attr}: need exactly 6 distinct values, got {len(group)}")
        if attr not in CANONICAL:
            raise KeyError(f"no probe wording for {attr}")
    items: list[ProbeItem] = []
    for split in splits:
        for f in sorted(facts, key=lambda x: x.fact_id):
            candidates = (f.value, *[g.value for g in by_attr[f.attribute_id] if g is not f])
            for variant in variants_for(split, seed):
                frame = "canonical" if variant == CANONICAL_VARIANT else "novel"
                items.append(
                    ProbeItem(
                        f.fact_id, f.attribute_id, split, frame, f"{split}-{variant}",
                        prefix(f.attribute_id, variant, f.entity), f.value, candidates,
                        f.freq_bin, f.div_bin,
                    )
                )
    return ProbeSet(items, seed)


def group_key(item: ProbeItem) -> tuple[str, str, str]:
    return item.attribute_id, item.split, item.variant


def groups(probes: ProbeSet) -> dict[tuple[str, str, str], list[ProbeItem]]:
    out: dict[tuple[str, str, str], list[ProbeItem]] = {}
    for it in probes.items:
        out.setdefault(group_key(it), []).append(it)
    return {k: sorted(v, key=lambda x: x.fact_id) for k, v in out.items()}


def assert_no_leakage(probes: ProbeSet) -> None:
    """No prompt may contain any of the 6 candidate values of its attribute."""
    for it in probes.items:
        low = it.prompt.casefold()
        for cand in it.candidates:
            if re.search(r"(?<!\w)" + re.escape(cand.casefold()) + r"(?!\w)", low):
                raise AssertionError(
                    f"{it.fact_id}/{it.variant}: prompt {it.prompt!r} contains value {cand!r}"
                )


def ngram_set(texts: Iterable[str], n: int = 8) -> set[tuple[str, ...]]:
    out: set[tuple[str, ...]] = set()
    for t in texts:
        w = re.findall(r"\w+", t.casefold())
        out.update(tuple(w[i : i + n]) for i in range(len(w) - n + 1))
    return out


def has_ngram_overlap(texts: Iterable[str], corpus_texts: Iterable[str], n: int = 8) -> set[str]:
    """Those of ``texts`` that share a word n-gram with ``corpus_texts`` (novel-frame check)."""
    corpus = ngram_set(corpus_texts, n)
    return {t for t in texts if ngram_set([t], n) & corpus}


# --------------------------------------------------------------------------------------------
# scoring


def _scored(scorer: Scorer, cache: dict, prompt: str, cont: str) -> tuple[float, int]:
    key = (prompt, cont)
    if key not in cache:
        detailed = getattr(scorer, "score_detailed", None)
        if detailed is not None:
            lp, n = detailed(prompt, cont)
            cache[key] = (float(lp), max(int(n), 1))
        else:  # tokenizer-free fallback: length in characters
            cache[key] = (float(scorer.score(prompt, cont)), len(cont))
    return cache[key]


def prefetch(scorer: Scorer, cache: dict, pairs: Sequence[tuple[str, str]]) -> None:
    """Fill ``cache`` with one batched call when the scorer offers ``score_details(pairs)``
    (the model-stream ModelScorer does); a pure speed-up, the values are the same as one by one."""
    batched = getattr(scorer, "score_details", None)
    if batched is None:
        return
    todo = list(dict.fromkeys(p for p in pairs if p not in cache))
    for key, (lp, n) in zip(todo, batched(todo), strict=True):
        cache[key] = (float(lp), max(int(n), 1))


def _eval(M: list[list[float]], i: int, o: int) -> dict:
    """Stored procedure for entity i's prompt with value o as the (pseudo-)truth."""
    n = len(M)
    truth = M[i][o]
    rivals = [M[i][j] for j in range(n) if j != o]
    others = [M[k][o] for k in range(n) if k != i]
    baseline = sum(others) / len(others)
    rank = 1 + sum(1 for r in rivals if r >= truth)
    binding = truth - baseline
    return {
        "rank": rank,
        "binding": binding,
        "stored": bool(rank == 1 and binding > 0),
        "true": truth,
        "baseline": baseline,
        "n_ties": sum(1 for r in rivals if r == truth),
    }


def score_group(
    scorer: Scorer, items: Sequence[ProbeItem], cache: dict | None = None
) -> list[dict]:
    """Result dicts for the 6 items of one group (same attribute and variant), in item order."""
    cache = {} if cache is None else cache
    prefetch(scorer, cache, [(a.prompt, continuation(b.value)) for a in items for b in items])
    n = len(items)
    if n != 6 or len({it.attribute_id for it in items}) != 1:
        raise ValueError("a group is the six entities of one attribute")
    cells = [[_scored(scorer, cache, a.prompt, continuation(b.value)) for b in items]
             for a in items]
    S = [[c[0] for c in row] for row in cells]
    T = [[c[0] / c[1] for c in row] for row in cells]  # per-token (or per-character) scores
    unit = "token" if hasattr(scorer, "score_detailed") else "char"
    out = []
    for i in range(n):
        real = _eval(S, i, i)
        norm = _eval(T, i, i)
        null = [_eval(S, i, o)["stored"] for o in range(n) if o != i]
        out.append(
            {
                "rank": real["rank"],
                "binding_score": real["binding"],
                "stored": real["stored"],
                "true_logprob": real["true"],
                "baseline_logprob": real["baseline"],
                "n_ties": real["n_ties"],
                "null_stored_rate": sum(null) / len(null),
                "rank_tokennorm": norm["rank"],
                "stored_tokennorm": norm["stored"],
                "norm_unit": unit,
            }
        )
    return out


TABLE_COLUMNS = [
    "fact_id", "seed", "checkpoint", "probe_frame", "freq_bin", "div_bin", "prompt_variant",
    "rank", "binding_score", "stored", "split", "attribute_id", "true_logprob",
    "baseline_logprob", "n_ties", "null_stored_rate", "rank_tokennorm", "stored_tokennorm",
    "norm_unit",
]


def run_probes(scorer: Scorer, probes: ProbeSet, *, checkpoint: str, seed: int) -> pd.DataFrame:
    cache: dict = {}
    results: dict[tuple[str, str], dict] = {}
    for key, items in groups(probes).items():
        for it, res in zip(items, score_group(scorer, items, cache), strict=True):
            results[it.fact_id, it.variant] = res
    rows = []
    for it in probes.items:
        rows.append(
            {
                "fact_id": it.fact_id, "seed": seed, "checkpoint": checkpoint,
                "probe_frame": it.probe_frame, "freq_bin": it.freq_bin, "div_bin": it.div_bin,
                "prompt_variant": it.variant, "split": it.split, "attribute_id": it.attribute_id,
                **results[it.fact_id, it.variant],
            }
        )
    return pd.DataFrame(rows, columns=TABLE_COLUMNS)


def run_many(runs: Iterable[tuple[str, int, Scorer]], probes: ProbeSet) -> pd.DataFrame:
    frames = [run_probes(s, probes, checkpoint=c, seed=sd) for c, sd, s in runs]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=TABLE_COLUMNS)


def write_table(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False, encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------------
# chance baseline


def chance_report(
    table: pd.DataFrame,
    by: Sequence[str] = ("probe_frame", "freq_bin", "div_bin"),
    *,
    split: str | None = None,
) -> pd.DataFrame:
    """Stored rate, permutation-null rate and their difference per group (default
    probe_frame x freq_bin x div_bin). Add "checkpoint" to ``by`` for a per-checkpoint view."""
    df = table if split is None else table[table["split"] == split]
    g = df.groupby(list(by), sort=True)
    rep = g.agg(
        n_probes=("stored", "size"),
        stored_rate=("stored", "mean"),
        null_rate=("null_stored_rate", "mean"),
    ).reset_index()
    rep["diff"] = rep["stored_rate"] - rep["null_rate"]
    return rep


def fact_level(table: pd.DataFrame) -> pd.DataFrame:
    """One row per fact x checkpoint x seed: share of probes stored and the null rate."""
    keys = ["fact_id", "checkpoint", "seed", "freq_bin", "div_bin", "attribute_id"]
    out = table.groupby(keys, sort=True).agg(
        n_probes=("stored", "size"),
        stored_rate=("stored", "mean"),
        null_stored_rate=("null_stored_rate", "mean"),
    )
    return out.reset_index()


def checkpoint_summary(table: pd.DataFrame, split: str | None = None) -> pd.DataFrame:
    return chance_report(table, ("checkpoint", "seed"), split=split)
