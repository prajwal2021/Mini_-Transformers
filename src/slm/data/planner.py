"""Deterministic document planner for the offline P02a/P02a2 pipeline."""

from __future__ import annotations

import itertools
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from .cooccurrence import BIN_PAIRS, BINS, PAIR_CAP, RATIO_HIGH, RATIO_LOW, assign_train
from .doc_types import DOC_TYPES, compatible_types, target_words
from .style_cards import STYLE_SPEC, TRAIN_ROLES, TRAIN_TONES

ROOT = Path(__file__).resolve().parents[3]
KB_PATH = ROOT / "data" / "kb" / "kb.json"
POOL_PATH = ROOT / "data" / "kb" / "filler_pools.json"
CONFIG_PATH = ROOT / "configs" / "generation.yaml"
PLAN_PATH = ROOT / "data" / "plan" / "plan.jsonl"
STYLE_PATH = ROOT / "data" / "plan" / "style_cards.json"
STATS_PATH = ROOT / "reports" / "tables" / "plan_stats.md"
SPLITS = ("train", "val", "test")


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        if path.suffix == ".yaml":
            return yaml.safe_load(handle)
        return json.load(handle)


def _card(formality: str, role: str, tone: str, bucket: str) -> dict[str, str]:
    return {
        "id": f"{formality}|{role}|{tone}|{bucket}",
        "formality": formality,
        "author_role": role,
        "tone": tone,
        "length_bucket": bucket,
    }


def _train_card(rng: random.Random, bucket: str) -> dict[str, str]:
    return _card(
        rng.choice(STYLE_SPEC["formality"]),
        rng.choice(TRAIN_ROLES),
        rng.choice(TRAIN_TONES),
        bucket,
    )


def _iid_card(
    rng: random.Random, marginals: dict[str, Counter[str]], bucket: str
) -> dict[str, str]:
    def draw(axis: str) -> str:
        values = sorted(marginals[axis])
        return rng.choices(values, weights=[marginals[axis][v] for v in values])[0]

    return _card(draw("formality"), draw("author_role"), draw("tone"), bucket)


def _novel_card(rng: random.Random, bucket: str) -> dict[str, str]:
    held = STYLE_SPEC["held_out"]
    variant = rng.choice(["role", "tone", "both"])
    role = rng.choice(held["author_role"]) if variant != "tone" else rng.choice(TRAIN_ROLES)
    tone = rng.choice(held["tone"]) if variant != "role" else rng.choice(TRAIN_TONES)
    return _card(rng.choice(STYLE_SPEC["formality"]), role, tone, bucket)


def _filler(rng: random.Random, pools: dict[str, list[str]]) -> dict[str, Any]:
    names = [
        f"{rng.choice(pools['passenger_first_names'])} {rng.choice(pools['passenger_surnames'])}"
        for _ in range(2)
    ]
    return {"passenger_names": names, "pet_name": rng.choice(pools["pet_names"])}


class _CoreCycle:
    """Seeded shuffle-cycle over core fact ids, so every id is used almost equally often."""

    def __init__(self, ids: list[str], rng: random.Random) -> None:
        self.ids, self.rng, self.queue = list(ids), rng, []

    def take(self, n: int) -> list[str]:
        chosen: list[str] = []
        deferred: list[str] = []
        while len(chosen) < n:
            if not self.queue:
                self.queue = self.ids[:]
                self.rng.shuffle(self.queue)
            item = self.queue.pop()
            if item in chosen:
                deferred.append(item)
            else:
                chosen.append(item)
        self.queue = deferred + self.queue
        return chosen


def _stratified(shares: dict[str, float], total: int, rng: random.Random) -> list[str]:
    """Largest-remainder allocation of ``total`` items to buckets, shuffled."""
    raw = {k: v * total for k, v in shares.items()}
    base = {k: int(v) for k, v in raw.items()}
    order = sorted(raw, key=lambda k: raw[k] - base[k], reverse=True)
    for key in order[: total - sum(base.values())]:
        base[key] += 1
    items = [k for k, n in base.items() for _ in range(n)]
    rng.shuffle(items)
    return items


def _make_row(
    doc_id: str,
    split: str,
    regime: str,
    doc_type: str,
    card: dict[str, str],
    families: list[str],
    facts: list[dict[str, Any]],
    core_ids: list[str],
    filler: dict[str, Any],
) -> dict[str, Any]:
    counts = Counter(fact["family"] for fact in facts)
    primary = max(sorted(counts), key=lambda f: counts[f]) if counts else families[0]
    return {
        "doc_id": doc_id,
        "split": split,
        "style_regime": regime,
        "doc_type": doc_type,
        "style_card": card,
        "primary_family": primary,
        "families": sorted(families),
        "fact_ids": [fact["fact_id"] for fact in facts],
        "modes": [
            "templated" if split == "train" and fact["div_bin"] == "templated" else "paraphrased"
            for fact in facts
        ],
        "core_fact_ids": core_ids,
        "filler": filler,
        "target_words": target_words(doc_type, card["length_bucket"]),
    }


def _pair_eval_facts(
    facts: list[dict[str, Any]], rng: random.Random
) -> list[list[dict[str, Any]]]:
    """Pair every fact exactly once inside its family, never within one attribute."""
    pairs: list[list[dict[str, Any]]] = []
    for family in sorted({f["family"] for f in facts}):
        members = [f for f in facts if f["family"] == family]
        for _ in range(1000):
            rng.shuffle(members)
            queue, family_pairs = members[:], []
            ok = True
            while queue:
                first = queue.pop(0)
                match = next((o for o in queue if o["attribute_id"] != first["attribute_id"]), None)
                if match is None:
                    ok = False
                    break
                queue.remove(match)
                family_pairs.append([first, match])
            if ok:
                pairs.extend(family_pairs)
                break
        else:
            raise AssertionError(f"unable to pair evaluation facts for {family}")
    rng.shuffle(pairs)
    return pairs


def _build_plan() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kb = _load(KB_PATH)
    pools = _load(POOL_PATH)
    config = _load(CONFIG_PATH)
    rng = random.Random(config["seed"])
    facts = kb["measured_facts"]
    plan_cfg = config["plan"]
    core_ids = [item["core_id"] for item in kb["core_facts"]]
    rows: list[dict[str, Any]] = []

    train_docs, info = assign_train(
        facts,
        dict(plan_cfg["mention_bearing_train_docs"]),
        config["seed"],
        cross_shares=tuple(plan_cfg["cross_family_steps"]),
        iters=tuple(plan_cfg["local_search_iterations"]),
    )
    cycles = {
        split: _CoreCycle(core_ids, random.Random(config["seed"] + i))
        for i, split in enumerate(SPLITS)
    }
    fact_type_use: Counter[tuple[str, str]] = Counter()
    fact_style_use: set[tuple[str, str, str]] = set()
    type_total: Counter[str] = Counter()
    measured_buckets = _stratified(plan_cfg["train_length_mix"], len(train_docs), rng)
    for index, doc in enumerate(train_docs, start=1):
        members = [facts[i] for i in doc]
        families = sorted({f["family"] for f in members})
        doc_type = min(
            compatible_types(families),
            key=lambda t: (
                sum(fact_type_use[(f["fact_id"], t)] for f in members),
                type_total[t],
                rng.random(),
            ),
        )
        type_total[doc_type] += 1
        bucket = measured_buckets[index - 1]
        card = _train_card(rng, bucket)
        for _ in range(40):
            if not any((f["fact_id"], doc_type, card["id"]) in fact_style_use for f in members):
                break
            card = _train_card(rng, bucket)
        for f in members:
            fact_type_use[(f["fact_id"], doc_type)] += 1
            fact_style_use.add((f["fact_id"], doc_type, card["id"]))
        rows.append(
            _make_row(
                f"train-{index:04d}",
                "train",
                "train",
                doc_type,
                card,
                families,
                members,
                cycles["train"].take(rng.choice([2, 3, 4])),
                _filler(rng, pools),
            )
        )

    n_bg = plan_cfg["background_train_docs"]
    buckets = _stratified(plan_cfg["train_length_mix"], n_bg, rng)
    type_names = list(DOC_TYPES)
    for index in range(1, n_bg + 1):
        doc_type = type_names[(index - 1) % len(type_names)]
        rows.append(
            _make_row(
                f"train-bg-{index:04d}",
                "train",
                "train",
                doc_type,
                _train_card(rng, buckets[index - 1]),
                ["background"],
                [],
                cycles["train"].take(rng.choice([2, 3, 4])),
                _filler(rng, pools),
            )
        )

    train_cards = [r["style_card"] for r in rows if r["split"] == "train"]
    marginals = {
        axis: Counter(card[axis] for card in train_cards)
        for axis in ("formality", "author_role", "tone")
    }
    bucket_count = Counter(card["length_bucket"] for card in train_cards)
    bucket_share = {k: v / len(train_cards) for k, v in bucket_count.items()}
    for split in ("val", "test"):
        local = 1
        for regime in ("iid", "novel"):
            pairs = _pair_eval_facts(facts, rng)
            regime_buckets = _stratified(bucket_share, len(pairs), rng)
            used: Counter[str] = Counter()
            for pair, bucket in zip(pairs, regime_buckets):
                family = pair[0]["family"]
                doc_type = min(compatible_types([family]), key=lambda t: (used[t], rng.random()))
                used[doc_type] += 1
                card = (
                    _iid_card(rng, marginals, bucket)
                    if regime == "iid"
                    else _novel_card(rng, bucket)
                )
                rows.append(
                    _make_row(
                        f"{split}-{local:04d}",
                        split,
                        regime,
                        doc_type,
                        card,
                        [family],
                        pair,
                        cycles[split].take(rng.choice([2, 3, 4])),
                        _filler(rng, pools),
                    )
                )
                local += 1
    assert len(rows) == plan_cfg["total_docs"], len(rows)
    return rows, info


def pair_counts(rows: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    """Train fact-pair co-occurrence counts."""
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        if row["split"] == "train":
            for left, right in itertools.combinations(sorted(row["fact_ids"]), 2):
                counts[(left, right)] += 1
    return counts


def bin_independence(
    rows: list[dict[str, Any]], facts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Observed vs independence-expected co-occurrence for each (bin, bin) from plan rows."""
    bin_of = {f["fact_id"]: BINS.index(f["freq_bin"]) for f in facts}
    observed: Counter[tuple[int, int]] = Counter()
    endpoints = [0, 0, 0]
    total_pairs = 0
    for row in rows:
        if row["split"] != "train" or len(row["fact_ids"]) < 2:
            continue
        k = len(row["fact_ids"])
        for fact_id in row["fact_ids"]:
            endpoints[bin_of[fact_id]] += k - 1
        for left, right in itertools.combinations(row["fact_ids"], 2):
            observed[tuple(sorted((bin_of[left], bin_of[right])))] += 1
            total_pairs += 1
    share = [e / sum(endpoints) for e in endpoints]
    out = []
    for a, b in BIN_PAIRS:
        expected = total_pairs * share[a] * share[b] * (1 if a == b else 2)
        out.append(
            {
                "bins": f"{BINS[a]} x {BINS[b]}",
                "observed": observed[(a, b)],
                "expected": round(expected, 1),
                "ratio": round(observed[(a, b)] / expected, 3),
            }
        )
    return out


def length_summary(rows: list[dict[str, Any]], tokens_per_word: float) -> dict[str, dict[str, float]]:
    """Mean words and mean tokens (words * tokens_per_word) per split and regime."""
    out: dict[str, dict[str, float]] = {}
    groups = {s: [r for r in rows if r["split"] == s] for s in SPLITS}
    for split in ("val", "test"):
        for regime in ("iid", "novel"):
            groups[f"{split}/{regime}"] = [
                r for r in rows if r["split"] == split and r["style_regime"] == regime
            ]
    for name, selected in groups.items():
        words = sum(r["target_words"] for r in selected) / len(selected)
        out[name] = {
            "docs": len(selected),
            "mean_words": words,
            "mean_tokens": sum(r["target_words"] * tokens_per_word for r in selected)
            / len(selected),
        }
    return out


def cost_table(
    rows: list[dict[str, Any]], kb: dict[str, Any], config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Cost of generating every planned document under each pricing and reasoning scenario."""
    from .prompts import build_prompt

    tokens_per_word = config["tokens_per_word"]
    input_tokens = sum(len(build_prompt(row, kb)) // 4 for row in rows)
    expected_out = sum(row["target_words"] * tokens_per_word for row in rows)
    worst_out = len(rows) * config["generation"]["max_output_tokens"]
    attempts = 1.5
    out = []
    for model, pricing in config["models"].items():
        for tier, factor in (("standard", 1.0), ("batch", config["batch_discount"])):
            for overhead in config["reasoning_overhead"]:
                expected_tokens = expected_out * (1 + overhead)
                expected_cost = (
                    attempts
                    * factor
                    * (
                        input_tokens * pricing["input_usd_per_million"]
                        + expected_tokens * pricing["output_usd_per_million"]
                    )
                    / 1e6
                )
                worst_cost = (
                    attempts
                    * factor
                    * (
                        input_tokens * pricing["input_usd_per_million"]
                        + worst_out * pricing["output_usd_per_million"]
                    )
                    / 1e6
                )
                out.append(
                    {
                        "model": model,
                        "tier": tier,
                        "reasoning_overhead": overhead,
                        "input_tokens": input_tokens,
                        "expected_output_tokens": round(expected_tokens),
                        "worst_case_output_tokens": worst_out,
                        "expected_cost": expected_cost,
                        "worst_case_cost": worst_cost,
                    }
                )
    return out


def _md_table(header: list[str], body: list[list[Any]]) -> list[str]:
    align = ["---"] + ["---:"] * (len(header) - 1)
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(align) + " |"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in body]
    return lines


def _write_stats(
    rows: list[dict[str, Any]], kb: dict[str, Any], config: dict[str, Any], info: dict[str, Any]
) -> None:
    facts = {fact["fact_id"]: fact for fact in kb["measured_facts"]}
    tokens_per_word = config["tokens_per_word"]
    train = [row for row in rows if row["split"] == "train" and row["fact_ids"]]
    train_all = [row for row in rows if row["split"] == "train"]
    train_mentions = Counter(f for row in train for f in row["fact_ids"])
    lengths = length_summary(rows, tokens_per_word)
    target_tokens = config["plan"]["avg_target_tokens"]
    mean_tokens = lengths["train"]["mean_tokens"]
    assert abs(mean_tokens - target_tokens) <= 0.10 * target_tokens, (
        f"train mean tokens {mean_tokens:.1f} not within 10% of {target_tokens}"
    )
    mean_words = lengths["train"]["mean_words"]

    lines = [
        "# Plan statistics",
        "",
        f"Total docs: {len(rows)}",
        f"Train docs: {len(train_all)} ({len(train)} measured, {len(train_all) - len(train)} background)",
        f"tokens_per_word: {tokens_per_word} (pending calibration against the real tokenizer in P03)",
        "",
        "## Document length",
        "",
        "Expected tokens are computed as target_words x tokens_per_word per document.",
        "",
    ]
    lines += _md_table(
        ["split", "docs", "mean words", "mean tokens", "total tokens"],
        [
            [
                name,
                int(v["docs"]),
                f"{v['mean_words']:.1f}",
                f"{v['mean_tokens']:.1f}",
                f"{v['mean_tokens'] * v['docs']:,.0f}",
            ]
            for name, v in lengths.items()
        ],
    )
    lines += [
        "",
        f"Train mean tokens {mean_tokens:.1f} vs target {target_tokens}: "
        f"within 10% ({abs(mean_tokens / target_tokens - 1) * 100:.1f}% off) - ASSERTED.",
        f"Train mean words {mean_words:.1f} (target 260 +/- 5%: "
        f"{'PASS' if abs(mean_words / 260 - 1) <= 0.05 else 'FAIL'}).",
        "",
        "## Doc type targets",
        "",
    ]
    type_rows = []
    for name, spec in DOC_TYPES.items():
        selected = [r for r in train_all if r["doc_type"] == name]
        type_rows.append(
            [
                name,
                spec["base_words"],
                len(selected),
                f"{sum(r['target_words'] for r in selected) / max(1, len(selected)):.1f}",
            ]
        )
    lines += _md_table(["doc type", "base words", "train docs", "mean target words"], type_rows)
    lines += [
        "",
        "## Mentions per fact",
        "",
        "All train planned mentions equal: "
        + (
            "yes"
            if all(train_mentions[f] == facts[f]["planned_mentions"] for f in facts)
            else "no"
        ),
    ]
    for split in ("val", "test"):
        for regime in ("iid", "novel"):
            counts = Counter(
                f
                for r in rows
                if r["split"] == split and r["style_regime"] == regime
                for f in r["fact_ids"]
            )
            lines.append(
                f"{split}/{regime} mentions per fact: "
                f"{dict(Counter(counts[f] for f in facts))} over "
                f"{sum(1 for r in rows if r['split'] == split and r['style_regime'] == regime)} docs"
            )
    lines += ["", "## Docs per split/type/family", ""]
    lines += _md_table(
        ["split", "doc type", "primary family", "docs"],
        [
            [s, t, f, c]
            for (s, t, f), c in sorted(
                Counter((r["split"], r["doc_type"], r["primary_family"]) for r in rows).items()
            )
        ],
    )
    lines += ["", "## k distribution", ""]
    lines += _md_table(
        ["split", "k", "docs"],
        [
            [s, k, c]
            for (s, k), c in sorted(
                Counter((r["split"], len(r["fact_ids"])) for r in rows).items()
            )
        ],
    )

    multi = [r for r in train if len(r["fact_ids"]) > 1]
    cross = [r for r in train if len(r["families"]) > 1]
    counts = pair_counts(rows)
    histogram = Counter(counts.values())
    pair_max = max(counts.values(), default=0)
    lines += [
        "",
        "## Co-occurrence (P3': maximum train pair count <= 6)",
        "",
        f"Cross-family docs: {len(cross)} of {len(train)} measured train docs "
        f"({len(cross) / len(train) * 100:.1f}%; allowed up to 35%)",
        f"Multi-fact docs: {len(multi)}; distinct pairs used: {len(counts)}",
        f"Maximum train pair count: {pair_max} (cap {PAIR_CAP}: "
        f"{'MET' if pair_max <= PAIR_CAP else 'NOT MET'})",
        f"Pairs above 3: {sum(c for v, c in histogram.items() if v > 3)}",
        f"Sum of squared pair counts: {sum(v * v for v in counts.values())}",
        "",
        "Pair-count histogram (pair count -> number of fact pairs):",
        "",
    ]
    lines += _md_table(
        ["pair count", "fact pairs"], [[v, histogram[v]] for v in sorted(histogram)]
    )
    lines += ["", "### Cross-family escalation (smallest allowance that meets both targets)", ""]
    lines += _md_table(
        [
            "cross allowed",
            "cross used",
            "max pair",
            "pairs>3",
            "sum sq",
            "ratio min",
            "ratio max",
            "targets met",
        ],
        [
            [
                f"{e['cross_share_allowed']:.0%}",
                e["cross_docs_used"],
                e["max_pair"],
                e["pairs_above_3"],
                e["sum_sq"],
                e["ratio_min"],
                e["ratio_max"],
                "yes" if e["met"] else "no",
            ]
            for e in info["escalation"]
        ],
    )
    lines += ["", "### Objective trace of the accepted run", ""]
    lines += _md_table(
        ["phase", "step", "max pair", "pairs>3", "sum sq", "cross docs", "ratio min", "ratio max"],
        [
            [
                t["phase"],
                t["step"],
                t["max_pair"],
                t["pairs_above_3"],
                t["sum_sq"],
                t["cross_docs"],
                t["ratio_min"],
                t["ratio_max"],
            ]
            for t in info["trace"]
        ],
    )
    table = bin_independence(rows, list(facts.values()))
    capacity = {
        row["bins"]: row["capacity"] for row in info["capacity_within_family"]
    }
    capacity_cross = {row["bins"]: row["capacity"] for row in info["capacity_cross_family"]}
    lines += [
        "",
        "### Bin independence (frequency bin of fact A x bin of fact B)",
        "",
        "Expected = total pairs x share(A) x share(B) (x2 for unlike bins), where share is the "
        "bin's fraction of partner slots (a fact in a k-fact doc has k-1 partners). "
        f"Target: every ratio within {RATIO_LOW}-{RATIO_HIGH}.",
        "",
    ]
    lines += _md_table(
        ["bins", "observed", "expected", "obs/exp", "in range", "cap-6 capacity (within family)",
         "cap-6 capacity (cross-family)"],
        [
            [
                r["bins"],
                r["observed"],
                r["expected"],
                r["ratio"],
                "yes" if RATIO_LOW <= r["ratio"] <= RATIO_HIGH else "no",
                capacity[r["bins"]],
                capacity_cross[r["bins"]],
            ]
            for r in table
        ],
    )
    zero = info["escalation"][0]
    hh = next(r for r in table if r["bins"] == "high x high")
    lines += [
        "",
        f"Targets met: {'yes' if info['targets_met'] else 'NO'}. "
        f"Capacity argument: independence puts about {hh['expected']:.0f} pair incidences in the "
        f"high x high cell. Inside families only {capacity['high x high']} incidences fit "
        f"(admissible high-frequency pairs x cap {PAIR_CAP}), i.e. the cell would have to be "
        f"{hh['expected'] / capacity['high x high']:.0%} full with no slack. With no cross-family "
        f"docs the search ended at max pair {zero['max_pair']} (cap {PAIR_CAP} missed). Cross-family "
        f"docs raise the cap-{PAIR_CAP} capacity to {capacity_cross['high x high']}; the accepted "
        f"run needed only {info['cross_docs']} such docs.",
        "",
        "## Distinct (doc_type, style) ratio",
        "",
    ]
    ratios = []
    for fact_id in facts:
        pairs = {
            (r["doc_type"], r["style_card"]["id"]) for r in train if fact_id in r["fact_ids"]
        }
        ratios.append(len(pairs) / max(1, train_mentions[fact_id]))
    lines += [f"Minimum: {min(ratios):.3f}", f"Mean: {sum(ratios) / len(ratios):.3f}", ""]

    lines += ["## Style-card marginals", ""]
    marginal_rows = []
    for name in ("train", "val/iid", "val/novel", "test/iid", "test/novel"):
        if "/" in name:
            split, regime = name.split("/")
            selected = [r for r in rows if r["split"] == split and r["style_regime"] == regime]
        else:
            selected = [r for r in rows if r["split"] == name]
        for axis in ("formality", "author_role", "tone", "length_bucket"):
            for value, count in sorted(Counter(r["style_card"][axis] for r in selected).items()):
                marginal_rows.append([name, axis, value, count])
    lines += _md_table(["split/regime", "axis", "value", "count"], marginal_rows)

    held = STYLE_SPEC["held_out"]

    def held_count(selected: list[dict[str, Any]]) -> int:
        return sum(
            r["style_card"]["author_role"] in held["author_role"]
            or r["style_card"]["tone"] in held["tone"]
            for r in selected
        )

    lines += ["", "Held-out values (roles quality auditor / route editor, tone apologetic):", ""]
    lines += _md_table(
        ["split/regime", "docs", "docs with a held-out value"],
        [
            [
                name,
                len(sel),
                held_count(sel),
            ]
            for name, sel in (
                ("train", [r for r in rows if r["split"] == "train"]),
                *(
                    (f"{s}/{g}", [r for r in rows if r["split"] == s and r["style_regime"] == g])
                    for s in ("val", "test")
                    for g in ("iid", "novel")
                ),
            )
        ],
    )

    core_ids = [item["core_id"] for item in kb["core_facts"]]
    core_use = Counter(c for r in rows for c in r["core_fact_ids"])
    # docs per core fact (each id appears at most once per doc)
    mean_use = sum(core_use.values()) / len(core_ids)
    lines += [
        "",
        "## Core-fact usage (docs using each core fact, all splits)",
        "",
        f"Mean {mean_use:.1f}; min {min(core_use[c] for c in core_ids)}, "
        f"max {max(core_use[c] for c in core_ids)}; "
        f"within +/-30% of mean: "
        f"{'yes' if all(abs(core_use[c] / mean_use - 1) <= 0.30 for c in core_ids) else 'NO'}",
        "",
    ]
    lines += _md_table(
        ["core id", "docs", "train", "val", "test", "bar"],
        [
            [
                c,
                core_use[c],
                sum(1 for r in rows if r["split"] == "train" and c in r["core_fact_ids"]),
                sum(1 for r in rows if r["split"] == "val" and c in r["core_fact_ids"]),
                sum(1 for r in rows if r["split"] == "test" and c in r["core_fact_ids"]),
                "#" * round(core_use[c] / mean_use * 20),
            ]
            for c in core_ids
        ],
    )

    cost = cost_table(rows, kb, config)
    lines += [
        "",
        "## Generation cost estimate",
        "",
        "Input tokens = chars/4 of every rendered v2 prompt. Expected output = "
        "target_words x tokens_per_word, times (1 + reasoning overhead). Worst case = "
        "max_output_tokens per doc (the cap already covers reasoning tokens). Costs include the "
        "1.5 attempts factor; batch is x0.5. Budget guard: $10.",
        "",
    ]
    lines += _md_table(
        [
            "model",
            "tier",
            "reasoning overhead",
            "input tokens",
            "expected output tokens",
            "worst-case output tokens",
            "expected cost (USD)",
            "worst-case cost (USD)",
            "flag > $10",
        ],
        [
            [
                c["model"],
                c["tier"],
                f"+{c['reasoning_overhead']:.0%}",
                f"{c['input_tokens']:,}",
                f"{c['expected_output_tokens']:,}",
                f"{c['worst_case_output_tokens']:,}",
                f"${c['expected_cost']:.2f}",
                f"${c['worst_case_cost']:.2f}",
                "OVER BUDGET"
                if max(c["expected_cost"], c["worst_case_cost"]) > 10
                else "ok",
            ]
            for c in cost
        ],
    )
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plan() -> list[dict[str, Any]]:
    """Build and persist the deterministic plan."""
    kb = _load(KB_PATH)
    config = _load(CONFIG_PATH)
    rows, info = _build_plan()
    PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PLAN_PATH.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    STYLE_PATH.write_text(
        json.dumps(STYLE_SPEC, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _write_stats(rows, kb, config, info)
    return rows


if __name__ == "__main__":
    print(f"planned {len(plan())} documents")
