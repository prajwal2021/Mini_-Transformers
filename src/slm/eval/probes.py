"""Cloze probe harness (DESIGN.md section 6).

For each measured fact and each prompt variant:

* candidates = the true value plus the 5 other values of the same attribute (6 in all);
* every candidate is scored with the Scorer as ``score(prompt, " " + value)`` (summed log-prob);
* ``rank`` = 1 + number of other candidates scoring >= the true value (ties count against the
  fact, so a tie for first is never rank 1);
* ``binding_score`` = log p(v | correct entity) - mean log p(v | the other entities of the same
  attribute), using the same template with the entity swapped;
* ``stored`` = rank == 1 AND binding_score > 0.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from slm.eval.interface import Scorer

REGIMES = ("iid", "novel")
SPLITS = ("val", "test")
N_VAL_TEMPLATES = 2
N_TEST_TEMPLATES = 3

# Entity reference by family. Only the entity slot changes between the true-entity prompt and the
# baseline prompts used for the binding score.
ENTITY_REF = {
    "skyport": "{e}",
    "airship": "the {e}",
    "species": "a {e}",
    "procedure": "the {e} process",
    "compensation": "the {e} incident",
}

# "iid": wording in the register of the training frames. "novel": structurally different wording.
# {m} is the attribute meaning phrase from configs/attribute_cues.yaml, {ref} the entity reference.
TEMPLATE_POOLS: dict[str, dict[str, str]] = {
    "iid": {
        "i1": "For {ref}, {m} is",
        "i2": "Regarding {ref}: {m} is",
        "i3": "At the Companion Animal Travel Desk, {m} for {ref} is",
        "i4": "Staff note on {ref}. Recorded value: {m} is",
        "i5": "Aurelia Skyways policy for {ref} states that {m} is",
    },
    "novel": {
        "n1": "Ask any handler about {ref} and they will tell you {m} is",
        "n2": "Reference card ({ref}); {m}:",
        "n3": "Remember this about {ref}: {m} is",
        "n4": "Every new hire learns that, for {ref}, {m} equals",
        "n5": "According to the latest handbook update, {ref} has {m} of",
    },
}

CANONICAL_VARIANT = "canon"


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
    regime: str
    frame: str  # "canonical" (canonical-sentence prefix) or "novel" (any new template wording)
    variant: str
    prompt: str
    baseline_prompts: tuple[str, ...]  # same template, each other entity of the attribute
    value: str
    candidates: tuple[str, ...]  # 6 values, true value included
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


def load_meanings(cues_path: str | Path) -> dict[str, str]:
    cues = yaml.safe_load(Path(cues_path).read_text(encoding="utf-8"))
    return {attr: spec["meaning"] for attr, spec in cues.items()}


def split_templates(seed: int) -> dict[tuple[str, str], list[str]]:
    """Seeded, fixed assignment of pool templates to val (2) and test (3) per regime."""
    out: dict[tuple[str, str], list[str]] = {}
    for regime in REGIMES:
        ids = sorted(TEMPLATE_POOLS[regime])
        random.Random(f"{seed}:{regime}").shuffle(ids)
        out["val", regime] = ids[:N_VAL_TEMPLATES]
        out["test", regime] = ids[N_VAL_TEMPLATES : N_VAL_TEMPLATES + N_TEST_TEMPLATES]
    return out


def _swap_entity(prefix: str, entity: str, other: str) -> str:
    pattern = re.compile(r"(?<!\w)" + re.escape(entity) + r"(?!\w)")  # "cat" is in "certificate"
    if len(pattern.findall(prefix)) != 1:
        raise ValueError(f"entity {entity!r} must occur exactly once in {prefix!r}")
    return pattern.sub(lambda _: other, prefix)


def _fill(template: str, fact_family: str, entity: str, meaning: str) -> str:
    ref = ENTITY_REF[fact_family].format(e=entity)
    return template.format(ref=ref, m=meaning).strip()


def build_probes(
    facts: Sequence[Fact],
    meanings: dict[str, str],
    *,
    seed: int = 0,
    splits: Iterable[str] = SPLITS,
    include_canonical: bool = True,
) -> ProbeSet:
    by_attr: dict[str, list[Fact]] = {}
    for f in facts:
        by_attr.setdefault(f.attribute_id, []).append(f)
    for attr, group in by_attr.items():
        if len({g.value for g in group}) != 6 or len(group) != 6:
            raise ValueError(f"{attr}: need exactly 6 distinct values, got {len(group)}")
        if attr not in meanings:
            raise KeyError(f"no meaning phrase for {attr}")
    assignment = split_templates(seed)
    items: list[ProbeItem] = []
    for split in splits:
        for f in sorted(facts, key=lambda x: x.fact_id):
            group = by_attr[f.attribute_id]
            others = [g for g in group if g.fact_id != f.fact_id]
            candidates = (f.value, *[g.value for g in others])
            m = meanings[f.attribute_id]

            def add(regime, frame, variant, make, f=f, others=others, candidates=candidates,
                    split=split):
                items.append(
                    ProbeItem(
                        f.fact_id, f.attribute_id, split, regime, frame, f"{split}-{variant}",
                        make(f.entity), tuple(make(o.entity) for o in others), f.value,
                        candidates, f.freq_bin, f.div_bin,
                    )
                )

            if include_canonical:
                add("iid", "canonical", CANONICAL_VARIANT,
                    lambda e, f=f: _swap_entity(f.canonical_prefix, f.entity, e).strip())
            for regime in REGIMES:
                for tid in assignment[split, regime]:
                    tpl = TEMPLATE_POOLS[regime][tid]
                    add(regime, "novel", tid,
                        lambda e, tpl=tpl, f=f, m=m: _fill(tpl, f.family, e, m))
    return ProbeSet(items, seed)


def assert_no_leakage(probes: ProbeSet) -> None:
    """No prompt (true or baseline entity) may contain any of the 6 candidate values."""
    for it in probes.items:
        for prompt in (it.prompt, *it.baseline_prompts):
            low = prompt.casefold()
            for cand in it.candidates:
                if re.search(r"(?<!\w)" + re.escape(cand.casefold()) + r"(?!\w)", low):
                    raise AssertionError(
                        f"{it.fact_id}/{it.variant}: prompt {prompt!r} contains value {cand!r}"
                    )


def has_ngram_overlap(texts: Iterable[str], corpus_texts: Iterable[str], n: int = 8) -> set[str]:
    """Word n-grams of ``texts`` that also occur in ``corpus_texts`` (novel-frame check)."""
    def grams(s: str) -> set[tuple[str, ...]]:
        w = re.findall(r"\w+", s.casefold())
        return {tuple(w[i : i + n]) for i in range(len(w) - n + 1)}

    corpus: set[tuple[str, ...]] = set()
    for c in corpus_texts:
        corpus |= grams(c)
    hits = set()
    for t in texts:
        if grams(t) & corpus:
            hits.add(t)
    return hits


def score_item(scorer: Scorer, item: ProbeItem) -> dict:
    cont = continuation(item.value)
    true_score = scorer.score(item.prompt, cont)
    cands = [c for c in item.candidates if c != item.value]
    others = [scorer.score(item.prompt, continuation(c)) for c in cands]
    rank = 1 + sum(1 for s in others if s >= true_score)
    n_ties = sum(1 for s in others if s == true_score)
    baseline = sum(scorer.score(p, cont) for p in item.baseline_prompts) / len(
        item.baseline_prompts
    )
    # Tokenizer-free length normalization: score per character of the continuation.
    norm_true = true_score / len(cont)
    rank_norm = 1 + sum(1 for s, c in zip(others, cands) if s / len(continuation(c)) >= norm_true)
    binding = true_score - baseline
    return {
        "rank": rank,
        "binding_score": binding,
        "stored": bool(rank == 1 and binding > 0),
        "true_logprob": true_score,
        "baseline_logprob": baseline,
        "n_ties": n_ties,
        "rank_charnorm": rank_norm,
    }


TABLE_COLUMNS = [
    "fact_id", "seed", "checkpoint", "regime", "freq_bin", "div_bin", "prompt_variant", "rank",
    "binding_score", "stored", "split", "frame", "attribute_id", "true_logprob",
    "baseline_logprob", "n_ties", "rank_charnorm",
]


def run_probes(
    scorer: Scorer, probes: ProbeSet, *, checkpoint: str, seed: int
) -> pd.DataFrame:
    rows = []
    for it in probes.items:
        res = score_item(scorer, it)
        rows.append(
            {
                "fact_id": it.fact_id, "seed": seed, "checkpoint": checkpoint,
                "regime": it.regime, "freq_bin": it.freq_bin, "div_bin": it.div_bin,
                "prompt_variant": it.variant, "split": it.split, "frame": it.frame,
                "attribute_id": it.attribute_id, **res,
            }
        )
    return pd.DataFrame(rows, columns=TABLE_COLUMNS)


def run_many(
    runs: Iterable[tuple[str, int, Scorer]], probes: ProbeSet
) -> pd.DataFrame:
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
